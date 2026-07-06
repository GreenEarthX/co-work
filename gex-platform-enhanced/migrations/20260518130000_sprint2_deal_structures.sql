-- ============================================================================
-- Sprint 2 / 1 of 4 — Deal structuring core
-- ============================================================================
-- Adds the canonical tables for v5.0 Deal Structuring Workbench:
--   deal_structures, debt_tranches, offtake_contracts,
--   deal_structure_offtake (junction), deal_policy_selections, deal_outputs.
--
-- Phase-aware from the start: every deal carries an explicit construction
-- period and operating period, every tranche declares which phase it draws in,
-- and the next migration (130002) adds the phased covenant + COD-test tables
-- on top of these.
--
-- Depends on:
--   - 20260518120000 (Sprint 1 — verification_state enum and function)
--   - public.plants (existing)
--   - public.financial_instruments (existing)
--
-- Reversibility:
--   This migration only adds. Down-migration would be:
--     drop table public.deal_outputs;
--     drop table public.deal_policy_selections;
--     drop table public.deal_structure_offtake;
--     drop table public.offtake_contracts;
--     drop table public.debt_tranches;
--     drop table public.deal_structures;
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 1. deal_structures — versioned bundle attached to a plant.
-- ----------------------------------------------------------------------------
create table public.deal_structures (
  id                      uuid primary key default gen_random_uuid(),
  plant_id                text not null,
  user_id                 uuid not null,                          -- creator
  name                    text not null,
  version                 int  not null default 1,
  status                  text not null default 'draft'
    check (status in ('draft','submitted','approved','superseded','archived')),

  -- ---------- phase boundaries (the heart of the model) ----------
  construction_start_date date not null,
  scheduled_cod_date      date not null,                          -- expected COD
  actual_cod_date         date,                                   -- null until COD passed
  operating_period_years  numeric not null
    check (operating_period_years > 0),

  -- ---------- discounting + tax + accounting ----------
  discount_rate_pct       numeric not null
    check (discount_rate_pct > 0 and discount_rate_pct < 100),
  tax_rate_pct            numeric not null default 25
    check (tax_rate_pct >= 0 and tax_rate_pct < 100),
  depreciation_years      numeric not null
    check (depreciation_years > 0),

  -- ---------- staleness detection ----------
  last_computed_at        timestamptz,
  last_computed_inputs_hash text,
  engine_version_used     text,                                   -- e.g. 'gex_pf_engine@sprint2'

  -- ---------- verification + deal-killer (Sprint 1 columns) ----------
  verification_state      public.verification_state not null default 'UNVERIFIED',
  deal_killer_flag        boolean not null default false,

  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),

  unique (plant_id, name, version),
  check (scheduled_cod_date > construction_start_date)
);

create index idx_deal_structures_plant on public.deal_structures (plant_id);
create index idx_deal_structures_user  on public.deal_structures (user_id);
create index idx_deal_structures_status on public.deal_structures (status)
  where status in ('draft','submitted');

comment on column public.deal_structures.scheduled_cod_date is
  'Expected Commercial Operation Date. The pre-COD / post-COD divide is anchored
   here. construction_start_date .. scheduled_cod_date is the construction window;
   scheduled_cod_date .. (scheduled_cod_date + operating_period_years) is the
   operations window. The Python engine refuses to compute DSCR/LLCR pre-COD.';

comment on column public.deal_structures.actual_cod_date is
  'Set only after the COD test (see cod_test_results) returns passed=true.
   Until then, the deal is governed by pre-COD tests, not operational covenants.';


-- ----------------------------------------------------------------------------
-- 2. debt_tranches — one row per tranche. Senior, mezz, subordinated, equity.
--    Each tranche declares which phase it draws in and how IDC is handled.
-- ----------------------------------------------------------------------------
create table public.debt_tranches (
  id                      uuid primary key default gen_random_uuid(),
  deal_structure_id       uuid not null references public.deal_structures(id) on delete cascade,
  seniority_rank          int not null,                           -- 1 = most senior
  tranche_type            text not null
    check (tranche_type in ('senior_bank','senior_bond','mezzanine',
                            'shareholder_loan','equity_bridge','equity',
                            'contingent_equity')),
  lender_class            text
    check (lender_class in ('commercial_bank','eca','multilateral','dfi',
                            'bond_market','sponsor','green_bond_fund')),
  lender_name             text,

  -- ---------- amounts + currency ----------
  commitment_eur          numeric not null check (commitment_eur >= 0),
  currency                text not null default 'EUR',
  fx_hedge_pct            numeric default 0
    check (fx_hedge_pct >= 0 and fx_hedge_pct <= 100),

  -- ---------- pricing ----------
  rate_type               text not null check (rate_type in ('fixed','floating')),
  base_rate_pct           numeric,                                -- e.g. EURIBOR forward
  spread_bps              numeric,
  fixed_rate_pct          numeric,                                -- used when rate_type='fixed'
  upfront_fee_bps         numeric default 0,
  commitment_fee_bps      numeric default 0,                      -- on undrawn balance

  -- ---------- repayment ----------
  tenor_years             numeric not null,
  grace_years             numeric not null default 0,
  repayment_profile       text not null
    check (repayment_profile in ('annuity','bullet','sculpted','custom','equity')),
  sculpted_schedule       jsonb,                                   -- [{year, principal_eur}, ...]

  -- ---------- the phase model (this is the v5.0 addition) ----------
  drawdown_phase          text not null
    check (drawdown_phase in ('construction','operations','both')),
  drawdown_schedule       jsonb,                                   -- [{date, amount_eur, milestone_ref}, ...]
  conditions_precedent    jsonb,                                   -- array of CP statements
  idc_treatment           text
    check (idc_treatment in ('capitalised_from_drawings',          -- accrue to principal
                             'capitalised_from_equity',            -- equity tops up
                             'capitalised_from_bridge',            -- equity-bridge loan
                             'paid_current',                       -- requires interim revenue
                             'not_applicable')),                   -- e.g. equity tranches
  conversion_at_cod_terms jsonb,                                   -- e.g. bridge -> long-term

  -- ---------- verification ----------
  verification_state      public.verification_state not null default 'UNVERIFIED',

  created_at              timestamptz not null default now()
);

create index idx_debt_tranches_deal on public.debt_tranches (deal_structure_id);
create index idx_debt_tranches_seniority on public.debt_tranches (deal_structure_id, seniority_rank);

comment on column public.debt_tranches.drawdown_phase is
  'Construction-phase tranches (e.g. equity bridge, construction loan) draw
   against milestones during build. Operations-phase tranches (e.g. bond
   take-out, long-term project loan) may refinance the construction stack
   at COD. ''both'' covers term facilities that span the lifecycle.';

comment on column public.debt_tranches.idc_treatment is
  'How Interest During Construction is funded. ''capitalised_from_drawings''
   accrues IDC to principal (loan grows during construction).
   ''capitalised_from_bridge'' uses a separate equity-bridge facility.
   ''paid_current'' is rare for green-field — requires interim revenue.';


-- ----------------------------------------------------------------------------
-- 3. offtake_contracts — revenue side, attached to the plant.
--    Carry verification state and deal-killer flag at the contract level.
-- ----------------------------------------------------------------------------
create table public.offtake_contracts (
  id                      uuid primary key default gen_random_uuid(),
  plant_id                text not null,
  counterparty_name       text not null,
  counterparty_class      text
    check (counterparty_class in ('investment_grade_corporate',
                                  'sub_investment_grade_corporate',
                                  'utility','airline','shipping_line',
                                  'industrial','government','aggregator')),

  -- ---------- product + volume ----------
  molecule                text not null,                          -- 'hydrogen','SAF','methanol',...
  volume_per_year         numeric not null check (volume_per_year > 0),
  volume_unit             text not null
    check (volume_unit in ('t_per_year','kt_per_year','GWh_per_year','m3_per_year')),

  -- ---------- pricing structure ----------
  price_type              text not null
    check (price_type in ('fixed','indexed','floor_collar','take_or_pay','cfd','spot')),
  -- price_formula examples:
  --   fixed:        { "price_eur_per_unit": 850 }
  --   indexed:      { "base": 850, "index": "Platts_H2_NWE",
  --                   "share": 0.6, "floor": 700, "cap": 1200 }
  --   take_or_pay:  { "fixed_minimum_pct": 0.85, "above_floor_pct": 0.5 }
  --   cfd:          { "strike": 950, "term_years": 15 }
  price_formula           jsonb not null,
  currency                text not null default 'EUR',

  -- ---------- timing ----------
  tenor_years             numeric not null check (tenor_years > 0),
  start_year_offset_months int not null default 0,                -- months after COD
  ramp_up_profile         jsonb,                                   -- [{year_offset, pct_of_nameplate}, ...]

  -- ---------- contract status ----------
  status                  text not null default 'draft'
    check (status in ('draft','loi','heads_of_terms',
                      'signed_conditional','signed_unconditional')),
  signed_date             date,
  binding_conditions      jsonb,                                   -- for signed_conditional

  -- ---------- verification + deal-killer ----------
  verification_state      public.verification_state not null default 'UNVERIFIED',
  -- A deal-killer offtake is one that, if not signed_unconditional by a date,
  -- breaks the financing. Surfaces in compute as a hard constraint.
  deal_killer_flag        boolean not null default false,
  evidence_doc_ids        text[],

  created_at              timestamptz not null default now()
);

create index idx_offtake_plant on public.offtake_contracts (plant_id);
create index idx_offtake_status on public.offtake_contracts (status);


-- ----------------------------------------------------------------------------
-- 4. deal_structure_offtake — many-to-many: which offtakes feed this deal.
-- ----------------------------------------------------------------------------
create table public.deal_structure_offtake (
  deal_structure_id       uuid references public.deal_structures(id) on delete cascade,
  offtake_contract_id     uuid references public.offtake_contracts(id) on delete cascade,
  -- Allocation: a given offtake may be partially attributed (e.g. 70%
  -- of the volume goes to this deal structure, 30% reserved for another).
  allocation_pct          numeric not null default 100
    check (allocation_pct > 0 and allocation_pct <= 100),
  primary key (deal_structure_id, offtake_contract_id)
);


-- ----------------------------------------------------------------------------
-- 5. deal_policy_selections — which financial instruments are claimed.
--    Snapshots the eligibility assessment at time of selection so the deal
--    output is reproducible even if instrument data changes later.
-- ----------------------------------------------------------------------------
create table public.deal_policy_selections (
  deal_structure_id       uuid references public.deal_structures(id) on delete cascade,
  instrument_id           text references public.financial_instruments(instrument_id),
  eligibility_status_snapshot text,
  expected_value_eur_per_year numeric,
  application_start_year_offset_months int default 0,
  selected_at             timestamptz not null default now(),
  primary key (deal_structure_id, instrument_id)
);


-- ----------------------------------------------------------------------------
-- 6. deal_outputs — written by gex_pf_engine, read by the UI.
--    The cashflow_schedule is rich (per-tranche, per-period) and the
--    summary metrics are computed against the active phase.
-- ----------------------------------------------------------------------------
create table public.deal_outputs (
  id                      uuid primary key default gen_random_uuid(),
  deal_structure_id       uuid not null references public.deal_structures(id) on delete cascade,
  computed_at             timestamptz not null default now(),

  -- Reproducibility
  inputs_hash             text not null,
  engine_version          text not null,

  -- ---------- full schedule, JSON array of period rows ----------
  -- Each row carries: period_index, period_start_date, phase,
  -- revenue_by_offtake, opex, ebitda, idc, drawn_by_tranche,
  -- debt_service_by_tranche, dsra_balance, lockup_active, cash_swept,
  -- pre_cod_ratios (or null in operations), dscr (or null in construction).
  cashflow_schedule       jsonb not null,

  -- ---------- pre-COD summary (null if no construction period evaluated) ----------
  precod_summary          jsonb,

  -- ---------- COD test snapshot (null until reached) ----------
  cod_test_summary        jsonb,

  -- ---------- post-COD summary metrics ----------
  project_irr             numeric,
  equity_irr              numeric,
  npv_eur                 numeric,
  min_dscr_operations     numeric,                                 -- explicitly operations-only
  avg_dscr_operations     numeric,
  llcr                    numeric,
  rating_band             text,
  binding_constraint      text,                                    -- 'dscr_floor','cost_to_complete', etc.
  covenant_breach_periods int[],

  -- ---------- diagnostics ----------
  warnings                jsonb,                                   -- non-fatal issues
  errors                  jsonb,                                   -- if computation degraded
  taghizadeh_hesary_assessment jsonb,                              -- bank/bond split commentary
  optimisation_log        jsonb                                    -- when /optimize was called
);

create index idx_deal_outputs_deal_time on public.deal_outputs (deal_structure_id, computed_at desc);


-- ----------------------------------------------------------------------------
-- 7. RLS — every table tenant-scoped to creator user. Cross-stakeholder
--    access (mandated lenders, certifiers, etc.) handled via the ABAC layer
--    rather than direct RLS, keeping RLS simple and correct.
-- ----------------------------------------------------------------------------
alter table public.deal_structures            enable row level security;
alter table public.debt_tranches              enable row level security;
alter table public.offtake_contracts          enable row level security;
alter table public.deal_structure_offtake     enable row level security;
alter table public.deal_policy_selections     enable row level security;
alter table public.deal_outputs               enable row level security;

-- deal_structures — owner read/write
create policy "deal_structures_owner_select"
  on public.deal_structures for select to authenticated
  using (user_id = auth.uid());
create policy "deal_structures_owner_insert"
  on public.deal_structures for insert to authenticated
  with check (user_id = auth.uid());
create policy "deal_structures_owner_update"
  on public.deal_structures for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "deal_structures_owner_delete"
  on public.deal_structures for delete to authenticated
  using (user_id = auth.uid());

-- Child tables: scope read/write to rows whose parent deal_structure is owned
create policy "debt_tranches_via_parent"
  on public.debt_tranches for all to authenticated
  using (exists (select 1 from public.deal_structures ds
                 where ds.id = debt_tranches.deal_structure_id
                   and ds.user_id = auth.uid()))
  with check (exists (select 1 from public.deal_structures ds
                      where ds.id = debt_tranches.deal_structure_id
                        and ds.user_id = auth.uid()));

create policy "offtake_via_plant_owner"
  on public.offtake_contracts for all to authenticated
  using (exists (select 1 from public.plants p
                 where p.id::text = offtake_contracts.plant_id
                   and auth.uid()::text = p.user_id))
  with check (exists (select 1 from public.plants p
                      where p.id::text = offtake_contracts.plant_id
                        and auth.uid()::text = p.user_id));

create policy "dso_via_parent"
  on public.deal_structure_offtake for all to authenticated
  using (exists (select 1 from public.deal_structures ds
                 where ds.id = deal_structure_offtake.deal_structure_id
                   and ds.user_id = auth.uid()))
  with check (exists (select 1 from public.deal_structures ds
                      where ds.id = deal_structure_offtake.deal_structure_id
                        and ds.user_id = auth.uid()));

create policy "policy_selections_via_parent"
  on public.deal_policy_selections for all to authenticated
  using (exists (select 1 from public.deal_structures ds
                 where ds.id = deal_policy_selections.deal_structure_id
                   and ds.user_id = auth.uid()))
  with check (exists (select 1 from public.deal_structures ds
                      where ds.id = deal_policy_selections.deal_structure_id
                        and ds.user_id = auth.uid()));

-- deal_outputs — owner reads; only service_role (engine) writes
create policy "deal_outputs_owner_select"
  on public.deal_outputs for select to authenticated
  using (exists (select 1 from public.deal_structures ds
                 where ds.id = deal_outputs.deal_structure_id
                   and ds.user_id = auth.uid()));
-- No insert/update/delete policy for authenticated — engine writes via service_role.


-- ----------------------------------------------------------------------------
-- 8. Extend the verification transition whitelist to include the new tables.
--    transition_verification_state() from Sprint 1 currently whitelists only
--    plants / equipment_equations / project_finance. Extend it to cover
--    deal_structures, debt_tranches, offtake_contracts.
-- ----------------------------------------------------------------------------
create or replace function public.transition_verification_state(
  p_target_table   text,
  p_target_id      text,
  p_target_field   text default 'verification_state',
  p_to_state       public.verification_state default null,
  p_reason         text default null,
  p_evidence_ids   text[] default null
) returns public.verification_state_transitions
language plpgsql
security definer
set search_path = public
as $$
declare
  v_current_state  public.verification_state;
  v_actor_user_id  uuid;
  v_actor_role     text;
  v_row            public.verification_state_transitions;
  v_sql            text;
  v_state_order    int[];
  v_from_idx       int;
  v_to_idx         int;
begin
  if p_to_state is null then
    raise exception 'p_to_state is required';
  end if;

  -- Extended whitelist now covers Sprint 2 tables.
  if p_target_table not in (
       'plants','equipment_equations','project_finance',
       'deal_structures','debt_tranches','offtake_contracts'
     ) then
    raise exception 'verification state not enabled on table %', p_target_table;
  end if;

  if p_target_field <> 'verification_state' then
    raise exception 'only verification_state field supported (got %)', p_target_field;
  end if;

  begin v_actor_user_id := auth.uid();
  exception when others then v_actor_user_id := null; end;

  begin v_actor_role := nullif(current_setting('request.jwt.claim.role', true), '');
  exception when others then v_actor_role := null; end;

  v_sql := format(
    'select verification_state from public.%I where id::text = $1',
    p_target_table
  );
  execute v_sql into v_current_state using p_target_id;
  if v_current_state is null and not found then
    raise exception 'row not found: %.id=%', p_target_table, p_target_id;
  end if;

  v_state_order := array['UNVERIFIED','SUBMITTED','CONFIRMED','AUDITED'];
  v_from_idx := coalesce(array_position(v_state_order, v_current_state::text), 1);
  v_to_idx   := array_position(v_state_order, p_to_state::text);
  if v_to_idx is null then
    raise exception 'invalid to_state %', p_to_state;
  end if;

  if v_to_idx < v_from_idx and (p_reason is null or length(trim(p_reason)) = 0) then
    raise exception 'reason required when transitioning backward (% -> %)',
      v_current_state, p_to_state;
  end if;

  v_sql := format(
    'update public.%I set verification_state = $1 where id::text = $2',
    p_target_table
  );
  execute v_sql using p_to_state, p_target_id;

  insert into public.verification_state_transitions
    (target_table, target_id, target_field, from_state, to_state,
     actor_user_id, actor_role, reason, evidence_doc_ids)
  values
    (p_target_table, p_target_id, p_target_field, v_current_state, p_to_state,
     v_actor_user_id, v_actor_role, p_reason, p_evidence_ids)
  returning * into v_row;

  return v_row;
end $$;

commit;
