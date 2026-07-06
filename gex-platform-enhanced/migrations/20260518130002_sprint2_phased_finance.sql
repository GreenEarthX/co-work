-- ============================================================================
-- Sprint 2 / 3 of 4 — Phased finance: pre-COD, COD test, post-COD covenants
-- ============================================================================
-- The professional core of v5.0: distinguish construction-phase governance
-- (milestone-gated drawdowns, completion guarantees, cost-to-complete) from
-- operations-phase governance (DSCR/LLCR/cash-sweep/lock-up), with the COD
-- test as the hard transition.
--
-- Tables added:
--   covenants            — phased; operations covenants AND construction covenants
--   precod_tests         — pre-COD tests that aren't expressible as covenants
--   drawdown_events      — recorded against milestones; gates next drawdown
--   cod_test_results     — the regime-transition gate
--
-- Depends on: 20260518130000 (deal_structures, debt_tranches).
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 1. covenants — explicitly phased.
--    A senior loan typically carries DIFFERENT covenants in construction vs
--    operations. Modelling them as a single set with a phase field is more
--    honest than the usual "one covenant package" assumption.
-- ----------------------------------------------------------------------------
create table public.covenants (
  id                      uuid primary key default gen_random_uuid(),
  deal_structure_id       uuid not null references public.deal_structures(id) on delete cascade,

  -- Which phase the covenant applies to.
  --   'construction'    — applies during build; not tested operationally
  --   'operations'      — applies post-COD
  --   'at_cod_test'     — single-shot test at COD transition
  phase                   text not null
    check (phase in ('construction','operations','at_cod_test')),

  covenant_type           text not null
    check (covenant_type in (
      -- Operations covenants
      'dscr_floor',                 -- below this -> event of default (typ. 1.05)
      'dscr_lockup',                -- below this -> dividend lock-up (typ. 1.20)
      'dscr_sweep',                 -- above this -> excess cash sweeps (typ. 1.40)
      'llcr_floor',
      'cash_sweep_pct',             -- pct of excess swept above threshold
      'debt_service_reserve_months',-- DSRA = N months of debt service
      'equity_cure_count',          -- max number of cures in loan life
      'equity_cure_consecutive_block', -- cannot cure consecutive periods
      -- Construction / single-shot
      'completion_guarantee',
      'cost_overrun_cap',           -- sponsor support cap as %
      'sponsor_undertaking',
      'epc_ld_cap_pct',             -- EPC liquidated damages cap (% contract value)
      'ie_certification_required'   -- Independent Engineer sign-off on milestones
    )),

  value                   numeric,                                -- numeric covenants
  value_text              text,                                   -- categorical / boolean covenants
  basis                   text
    check (basis in ('forward_12m','historical_6m','forward_life',
                     'rolling_24m','one_shot') or basis is null),
  test_frequency          text not null
    check (test_frequency in ('quarterly','semi_annual','annual',
                              'at_cod','per_drawdown','one_time')),
  applies_to_tranche_id   uuid references public.debt_tranches(id) on delete cascade,
  -- null means covenant applies to the whole deal; non-null means tranche-specific
  -- (mezz might have a tighter DSCR floor than senior, etc.)

  notes                   text,
  created_at              timestamptz not null default now()
);

create index idx_covenants_deal on public.covenants (deal_structure_id);
create index idx_covenants_phase on public.covenants (deal_structure_id, phase);

comment on column public.covenants.phase is
  'Pre-COD covenants (phase=construction) are completion-focused; pre-COD does
   not have DSCR — measuring it would be a category error. Operations covenants
   test cashflow. at_cod_test covenants fire exactly once at the COD gate.';


-- ----------------------------------------------------------------------------
-- 2. precod_tests — pre-COD measurements that need explicit thresholds.
--    These are not "covenants" in the loan-agreement sense, but they are
--    structurally identical: a measurable quantity, a threshold, a
--    consequence-on-breach.
-- ----------------------------------------------------------------------------
create table public.precod_tests (
  id                      uuid primary key default gen_random_uuid(),
  deal_structure_id       uuid not null references public.deal_structures(id) on delete cascade,

  test_type               text not null
    check (test_type in (
      'cost_to_complete_coverage',  -- (cash + undrawn commitments) / cost_remaining
      'equity_drawn_ratio',         -- equity_drawn / equity_committed at this point
      'pari_passu_ratio',           -- equity_drawn / debt_drawn matches target
      'physical_progress_pct',      -- per Independent Engineer certification
      'schedule_slippage_days',
      'sponsor_support_headroom',   -- guarantee_cap − utilisation
      'epc_ld_coverage',
      'lookforward_dscr_p90',       -- THE COD test: projected operating DSCR
      'lookforward_llcr_p90',
      'capacity_demonstration_pct', -- at COD: % of nameplate demonstrated
      'permits_in_force',
      'offtake_unconditional'
    )),

  threshold               numeric,
  threshold_text          text,
  comparison              text not null default 'gte'
    check (comparison in ('gte','lte','eq','ne','boolean_true')),

  test_frequency          text not null
    check (test_frequency in ('per_drawdown','quarterly','at_cod','one_time')),

  breach_consequence      text not null
    check (breach_consequence in (
      'block_next_drawdown',
      'cure_period_30d',
      'sponsor_cure_required',
      'event_of_default'
    )),

  notes                   text,
  created_at              timestamptz not null default now()
);

create index idx_precod_tests_deal on public.precod_tests (deal_structure_id);


-- ----------------------------------------------------------------------------
-- 3. drawdown_events — historical record of actual drawdowns + status of
--    the milestone they were gated on.
--    Construction-phase debt is consumed by drawing against milestones;
--    each drawdown should be paired with milestone evidence (Independent
--    Engineer certificate, EPC progress report, etc.).
-- ----------------------------------------------------------------------------
create table public.drawdown_events (
  id                      uuid primary key default gen_random_uuid(),
  tranche_id              uuid not null references public.debt_tranches(id) on delete cascade,
  drawdown_number         int not null,                           -- 1, 2, 3, ...

  -- Scheduled vs actual
  scheduled_date          date not null,
  requested_date          date,
  actual_date             date,
  scheduled_amount_eur    numeric not null check (scheduled_amount_eur >= 0),
  actual_amount_eur       numeric,

  -- Milestone gating
  milestone_label         text,                                   -- 'foundations_complete', 'mechanical_completion', etc.
  milestone_satisfied     boolean,
  independent_engineer_cert_doc_id text,                          -- ref to Supabase Storage
  conditions_precedent_met jsonb,                                  -- {cp1: true, cp2: false, ...}

  -- Status
  status                  text not null default 'scheduled'
    check (status in ('scheduled','requested','approved','funded',
                      'blocked','cancelled')),
  block_reason            text,

  -- Verification
  verification_state      public.verification_state not null default 'UNVERIFIED',

  created_at              timestamptz not null default now(),
  unique (tranche_id, drawdown_number)
);

create index idx_drawdown_tranche on public.drawdown_events (tranche_id, drawdown_number);


-- ----------------------------------------------------------------------------
-- 4. cod_test_results — the regime-transition record.
--    A deal can have many attempts; only one passed=true result transitions
--    deal_structures.actual_cod_date.
-- ----------------------------------------------------------------------------
create table public.cod_test_results (
  id                      uuid primary key default gen_random_uuid(),
  deal_structure_id       uuid not null references public.deal_structures(id) on delete cascade,
  test_attempt            int not null default 1,
  test_date               date not null,

  -- The hard conditions evaluated at the COD test.
  capacity_demonstration_pct numeric,                             -- typ. >=95%
  permits_in_force        boolean,
  offtake_unconditional   boolean,
  dsra_funded             boolean,
  insurance_in_force      boolean,
  o_and_m_agreement_signed boolean,

  -- Forward-looking projections (P90)
  lookforward_dscr_p90    numeric,
  lookforward_llcr_p90    numeric,
  lookforward_dscr_threshold numeric,                             -- snapshot of covenant threshold

  -- Overall verdict
  passed                  boolean not null,
  failure_reasons         jsonb,                                   -- when passed=false

  -- Verification + audit
  verification_state      public.verification_state not null default 'UNVERIFIED',
  evidence_doc_ids        text[],

  created_at              timestamptz not null default now(),
  unique (deal_structure_id, test_attempt)
);

create index idx_cod_test_deal on public.cod_test_results (deal_structure_id, test_date desc);


-- ----------------------------------------------------------------------------
-- 5. Trigger: when a COD test passes, set the parent deal's actual_cod_date.
--    This is the hard transition from pre-COD to operations governance.
-- ----------------------------------------------------------------------------
create or replace function public.tg_cod_test_pass()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.passed = true then
    update public.deal_structures
       set actual_cod_date = new.test_date,
           updated_at = now()
     where id = new.deal_structure_id
       and (actual_cod_date is null or actual_cod_date > new.test_date);
  end if;
  return new;
end $$;

drop trigger if exists trg_cod_test_pass on public.cod_test_results;
create trigger trg_cod_test_pass
  after insert or update on public.cod_test_results
  for each row execute function public.tg_cod_test_pass();


-- ----------------------------------------------------------------------------
-- 6. Helper function: which phase is a deal currently in?
--    Used by the engine to decide which compute path to run, and by the UI
--    to render the right view.
-- ----------------------------------------------------------------------------
create or replace function public.deal_current_phase(p_deal_id uuid)
returns text
language sql
stable
as $$
  select case
    when ds.actual_cod_date is null
      and current_date < ds.scheduled_cod_date     then 'construction'
    when ds.actual_cod_date is null
      and current_date >= ds.scheduled_cod_date    then 'cod_overdue'
    when ds.actual_cod_date is not null
      and current_date <  ds.actual_cod_date + (ds.operating_period_years * interval '1 year')
                                                   then 'operations'
    when ds.actual_cod_date is not null            then 'post_operations'
    else 'unknown'
  end as phase
  from public.deal_structures ds
  where ds.id = p_deal_id;
$$;

comment on function public.deal_current_phase is
  'Returns the current phase of a deal based on construction_start_date,
   scheduled_cod_date, actual_cod_date, and operating_period_years.
   Used by the engine and UI to gate behaviour. Returns ''cod_overdue'' when
   scheduled COD has passed but no successful cod_test_result exists yet —
   this should surface as a structural warning in the UI.';


-- ----------------------------------------------------------------------------
-- 7. RLS — all phased-finance tables scoped to the parent deal's owner.
-- ----------------------------------------------------------------------------
alter table public.covenants         enable row level security;
alter table public.precod_tests      enable row level security;
alter table public.drawdown_events   enable row level security;
alter table public.cod_test_results  enable row level security;

create policy "covenants_via_parent"
  on public.covenants for all to authenticated
  using (exists (select 1 from public.deal_structures ds
                 where ds.id = covenants.deal_structure_id
                   and ds.user_id = auth.uid()))
  with check (exists (select 1 from public.deal_structures ds
                      where ds.id = covenants.deal_structure_id
                        and ds.user_id = auth.uid()));

create policy "precod_tests_via_parent"
  on public.precod_tests for all to authenticated
  using (exists (select 1 from public.deal_structures ds
                 where ds.id = precod_tests.deal_structure_id
                   and ds.user_id = auth.uid()))
  with check (exists (select 1 from public.deal_structures ds
                      where ds.id = precod_tests.deal_structure_id
                        and ds.user_id = auth.uid()));

create policy "drawdown_events_via_tranche"
  on public.drawdown_events for all to authenticated
  using (exists (select 1 from public.debt_tranches dt
                 join public.deal_structures ds on ds.id = dt.deal_structure_id
                 where dt.id = drawdown_events.tranche_id
                   and ds.user_id = auth.uid()))
  with check (exists (select 1 from public.debt_tranches dt
                      join public.deal_structures ds on ds.id = dt.deal_structure_id
                      where dt.id = drawdown_events.tranche_id
                        and ds.user_id = auth.uid()));

create policy "cod_test_via_parent"
  on public.cod_test_results for all to authenticated
  using (exists (select 1 from public.deal_structures ds
                 where ds.id = cod_test_results.deal_structure_id
                   and ds.user_id = auth.uid()))
  with check (exists (select 1 from public.deal_structures ds
                      where ds.id = cod_test_results.deal_structure_id
                        and ds.user_id = auth.uid()));

commit;
