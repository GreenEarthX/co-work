-- ============================================================================
-- Sprint 2 / 2 of 4 — Equation engine runs as evidence
-- ============================================================================
-- Elevates Lovable's src/engine/ (the equipment/equation engine, ~3,400 lines)
-- from a design-time UI tool to a first-class evidence source for the
-- platform's bankability assertions.
--
-- The engine runs in the browser. After each run, the frontend persists the
-- outcome to this table via Supabase. Subsequent verification transitions on
-- the plant CONSULT this table: a plant cannot legitimately transition to
-- CONFIRMED unless its most recent engine run is clean.
--
-- This codifies the principle:
--   "Successful equation engine resolution is revealed engineering capability."
--
-- Depends on: 20260518120000 (Sprint 1) and the existing public.plants.
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 1. equation_engine_runs — one row per engine invocation.
--    inputs_hash makes runs replayable; engine_version makes them auditable.
-- ----------------------------------------------------------------------------
create table public.equation_engine_runs (
  id                      uuid primary key default gen_random_uuid(),
  plant_id                text not null,

  -- ---------- reproducibility ----------
  engine_version          text not null,                          -- semver or git SHA of src/engine/
  inputs_hash             text not null,                          -- hash of plants.data JSONB at run time
  ran_at                  timestamptz not null default now(),
  triggered_by_user       uuid,                                   -- auth.uid(); null if autorun

  -- ---------- the engine's verdict ----------
  status                  text not null
    check (status in ('clean','warnings','violations','engine_error')),
  formula_dag_resolved    boolean not null,
  mass_balance_closed     boolean not null,
  energy_balance_closed   boolean not null,
  unit_check_passed       boolean not null,
  rule_check_passed       boolean not null,

  -- ---------- structured findings ----------
  -- Each violation has:
  --   { rule_id, gate, equipment_id, severity, message, suggested_fix? }
  -- severity ∈ {info, warning, error, deal_killer}
  violations              jsonb not null default '[]'::jsonb,
  warnings                jsonb not null default '[]'::jsonb,
  metrics                 jsonb not null default '{}'::jsonb,     -- mass/energy closure errors, etc.

  -- ---------- deal-killer rollup ----------
  -- True if ANY violation has severity='deal_killer'. Drives the plant-level
  -- deal_killer_flag via the trigger below.
  has_deal_killer         boolean not null default false,

  -- ---------- verification state of the run itself ----------
  -- CONFIRMED = a reviewer has reviewed the engine output and the snapshot it
  -- ran on; AUDITED = a certifier has signed off (e.g. for compliance).
  verification_state      public.verification_state not null default 'UNVERIFIED'
);

create index idx_eer_plant_recent
  on public.equation_engine_runs (plant_id, ran_at desc);

create index idx_eer_plant_clean
  on public.equation_engine_runs (plant_id, ran_at desc)
  where status = 'clean';

create index idx_eer_plant_dealkillers
  on public.equation_engine_runs (plant_id)
  where has_deal_killer = true;

comment on table public.equation_engine_runs is
  'Persistent record of every src/engine/ run. Treated as the platform''s own
   technical due diligence on a plant configuration. A plant cannot be marked
   CONFIRMED unless its latest run is status=clean. Deal-killer violations
   cascade to plants.deal_killer_flag via on_engine_run trigger.';


-- ----------------------------------------------------------------------------
-- 2. RLS — ABAC-flavoured. Owner reads always; broader stakeholder reads are
--    granted by application-level ABAC rules calling this in service-role
--    context, not at RLS. Keeps RLS straightforward and correct.
-- ----------------------------------------------------------------------------
alter table public.equation_engine_runs enable row level security;

create policy "eer_owner_select"
  on public.equation_engine_runs for select to authenticated
  using (exists (select 1 from public.plants p
                 where p.id::text = equation_engine_runs.plant_id
                   and auth.uid()::text = p.user_id));

create policy "eer_owner_insert"
  on public.equation_engine_runs for insert to authenticated
  with check (exists (select 1 from public.plants p
                      where p.id::text = equation_engine_runs.plant_id
                        and auth.uid()::text = p.user_id));

-- No update/delete from authenticated. Engine runs are immutable history.
-- (Verification state changes flow through transition_verification_state,
-- which uses SECURITY DEFINER and updates the row in its own context.)


-- ----------------------------------------------------------------------------
-- 3. Extend transition function whitelist to include equation_engine_runs.
--    Reviewers may transition runs to CONFIRMED; certifiers to AUDITED.
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
  v_latest_engine_status text;
  v_target_plant_id text;
begin
  if p_to_state is null then
    raise exception 'p_to_state is required';
  end if;

  if p_target_table not in (
       'plants','equipment_equations','project_finance',
       'deal_structures','debt_tranches','offtake_contracts',
       'equation_engine_runs'
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

  -- ====================================================================
  -- ENGINE PRECONDITION (the key Sprint 2 rule)
  -- ====================================================================
  -- A plant cannot transition to CONFIRMED or AUDITED unless its most
  -- recent equation_engine_run is status='clean'. This is what makes
  -- src/engine/ first-class evidence rather than optional decoration.
  -- ====================================================================
  if p_target_table = 'plants' and p_to_state in ('CONFIRMED','AUDITED') then
    select status into v_latest_engine_status
    from public.equation_engine_runs
    where plant_id = p_target_id
    order by ran_at desc
    limit 1;

    if v_latest_engine_status is null then
      raise exception
        'cannot mark plant % as %: no equation engine run exists. '
        'Run the equipment/equation engine first.',
        p_target_id, p_to_state;
    end if;

    if v_latest_engine_status <> 'clean' then
      raise exception
        'cannot mark plant % as %: latest engine run status is "%". '
        'Resolve violations and re-run before requesting confirmation.',
        p_target_id, p_to_state, v_latest_engine_status;
    end if;
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


-- ----------------------------------------------------------------------------
-- 4. Trigger: cascade engine deal-killers to plants.deal_killer_flag.
--    Whenever an engine run is inserted with has_deal_killer=true, set the
--    plant's deal_killer_flag. When the LATEST run is clean and the plant
--    flag was previously set by the engine, clear it.
--
--    We use a marker in plants to distinguish flags set by the engine from
--    flags set manually by structurers — so a manual flag isn't accidentally
--    cleared by a subsequent clean run.
-- ----------------------------------------------------------------------------
alter table public.plants
  add column if not exists deal_killer_set_by text  -- 'engine' | 'user' | 'auditor' | null
    check (deal_killer_set_by in ('engine','user','auditor') or deal_killer_set_by is null);

create or replace function public.tg_cascade_engine_deal_killer()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_latest_has_killer boolean;
  v_latest_clean      boolean;
begin
  -- Most recent run for this plant after the insert
  select has_deal_killer, (status = 'clean')
  into v_latest_has_killer, v_latest_clean
  from public.equation_engine_runs
  where plant_id = new.plant_id
  order by ran_at desc
  limit 1;

  if v_latest_has_killer then
    update public.plants
      set deal_killer_flag = true,
          deal_killer_set_by = 'engine'
    where id::text = new.plant_id
      and (deal_killer_flag = false or deal_killer_set_by = 'engine');
  elsif v_latest_clean then
    -- Engine just cleared. Only auto-clear the flag if engine set it.
    update public.plants
      set deal_killer_flag = false,
          deal_killer_set_by = null
    where id::text = new.plant_id
      and deal_killer_set_by = 'engine';
  end if;

  return new;
end $$;

drop trigger if exists trg_cascade_engine_deal_killer on public.equation_engine_runs;
create trigger trg_cascade_engine_deal_killer
  after insert on public.equation_engine_runs
  for each row execute function public.tg_cascade_engine_deal_killer();


-- ----------------------------------------------------------------------------
-- 5. Convenience view: latest run per plant. Cheap read for the UI.
-- ----------------------------------------------------------------------------
create or replace view public.v_latest_engine_run as
select distinct on (plant_id)
  plant_id,
  id            as run_id,
  ran_at,
  status,
  formula_dag_resolved,
  mass_balance_closed,
  energy_balance_closed,
  unit_check_passed,
  rule_check_passed,
  has_deal_killer,
  jsonb_array_length(violations) as violation_count,
  jsonb_array_length(warnings)   as warning_count,
  verification_state
from public.equation_engine_runs
order by plant_id, ran_at desc;

comment on view public.v_latest_engine_run is
  'One row per plant: the most recent equation engine run. Drives the
   "Plant Plausibility" indicator in the UI and the engine precondition
   inside transition_verification_state.';

commit;

-- ============================================================================
-- Smoke test (run after applying)
-- ============================================================================
-- -- Insert a synthetic plant if needed
-- insert into plants (user_id, slug, data)
-- values (auth.uid()::text, 'test-engine-plant', '{}'::jsonb)
-- returning id;
--
-- -- 1) No engine run yet → cannot CONFIRM
-- select transition_verification_state(
--   'plants', '<plant-id>'::text, 'verification_state', 'CONFIRMED'
-- );
-- -- ERROR: no equation engine run exists.
--
-- -- 2) Insert a run with violations
-- insert into equation_engine_runs
--   (plant_id, engine_version, inputs_hash, status,
--    formula_dag_resolved, mass_balance_closed, energy_balance_closed,
--    unit_check_passed, rule_check_passed,
--    violations, has_deal_killer)
-- values ('<plant-id>', 'engine@1.0', 'abc123', 'violations',
--         true, false, true, true, false,
--         '[{"rule_id":"MB1","severity":"deal_killer","message":"H balance off"}]'::jsonb,
--         true);
--
-- -- Plant flag should now be set automatically
-- select deal_killer_flag, deal_killer_set_by from plants where id::text = '<plant-id>';
--
-- -- 3) Insert a clean run; flag clears
-- insert into equation_engine_runs
--   (plant_id, engine_version, inputs_hash, status,
--    formula_dag_resolved, mass_balance_closed, energy_balance_closed,
--    unit_check_passed, rule_check_passed)
-- values ('<plant-id>', 'engine@1.0', 'def456', 'clean',
--         true, true, true, true, true);
--
-- -- 4) Now CONFIRMED is allowed
-- select transition_verification_state(
--   'plants', '<plant-id>'::text, 'verification_state', 'SUBMITTED'
-- );
-- select transition_verification_state(
--   'plants', '<plant-id>'::text, 'verification_state', 'CONFIRMED'
-- );
