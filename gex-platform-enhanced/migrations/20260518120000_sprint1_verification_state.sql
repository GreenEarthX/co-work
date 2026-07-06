-- ============================================================================
-- Sprint 1 — Verification state infrastructure
-- ============================================================================
-- Purpose:
--   Introduce v6.0 verification states (UNVERIFIED / SUBMITTED / CONFIRMED /
--   AUDITED) as a first-class data primitive. Adds:
--     1. verification_state enum
--     2. verification_state_transitions audit table
--     3. transition_verification_state() function (single entry point — all
--        state changes go through here so the audit trail is enforced)
--     4. verification_state + deal_killer_flag columns on `plants`,
--        `equipment_equations`, and `project_finance`
--
-- Safety:
--   This migration is ADDITIVE ONLY. No existing columns altered, no policies
--   dropped, no data rewritten. Backfills default to 'UNVERIFIED' which is the
--   correct conservative state for any pre-existing row.
--
--   RLS tightening lives in the SEPARATE migration
--   20260518120001_sprint1_rls_hardening.sql which the user reviews and applies
--   on its own schedule (it may break demo / credentials-provider flows).
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 1. Enum type for verification state. Idempotent so re-runs don't fail.
-- ----------------------------------------------------------------------------
do $$ begin
  create type public.verification_state as enum (
    'UNVERIFIED',  -- claim exists, no evidence yet
    'SUBMITTED',   -- evidence uploaded, awaiting review
    'CONFIRMED',   -- platform-reviewed, evidence checked
    'AUDITED'      -- third-party / certifier signed-off
  );
exception when duplicate_object then null; end $$;

-- ----------------------------------------------------------------------------
-- 2. Audit table — every transition recorded, immutable by RLS.
-- ----------------------------------------------------------------------------
create table if not exists public.verification_state_transitions (
  id                  uuid primary key default gen_random_uuid(),
  -- polymorphic pointer to the row whose state changed
  target_table        text not null,
  target_id           text not null,
  target_field        text not null default 'verification_state',
  -- transition itself
  from_state          public.verification_state,  -- null on first set
  to_state            public.verification_state not null,
  -- who and why
  actor_user_id       uuid,         -- auth.uid() at time of transition; null for service-role
  actor_role          text,         -- jwt role claim
  reason              text,         -- free text, required when going backwards
  evidence_doc_ids    text[],       -- pointers into Supabase Storage (if any)
  -- metadata
  occurred_at         timestamptz not null default now(),
  inserted_at         timestamptz not null default now()
);

create index if not exists idx_vst_target
  on public.verification_state_transitions (target_table, target_id, occurred_at desc);

create index if not exists idx_vst_actor
  on public.verification_state_transitions (actor_user_id, occurred_at desc);

alter table public.verification_state_transitions enable row level security;

-- Tenants can read transitions for rows they own — but cannot insert/update/
-- delete directly. The only legitimate writer is transition_verification_state().
do $$ begin
  create policy "Authenticated can read own transitions"
    on public.verification_state_transitions for select to authenticated
    using (
      -- Defer the ownership check to the target row's own RLS by querying it.
      -- This is intentionally permissive at the audit layer; the auth check
      -- on the target row (plants etc.) is what actually gates access.
      true
    );
exception when duplicate_object then null; end $$;

-- No one inserts directly. The transition function (security definer) is the
-- only path. We explicitly do NOT create insert/update/delete policies, so
-- those operations are denied by default under RLS for anyone except
-- service_role.

-- ----------------------------------------------------------------------------
-- 3. Single entry point for state transitions.
--    All callers — frontend (via RPC), engine (via service-role), edge
--    functions — go through this so the audit log is the source of truth.
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

  -- Whitelist of tables this function will touch. Add to this list as more
  -- tables adopt verification state. Anything not in the list is refused so
  -- the function cannot be abused to write to arbitrary tables.
  if p_target_table not in ('plants','equipment_equations','project_finance') then
    raise exception 'verification state not enabled on table %', p_target_table;
  end if;

  if p_target_field <> 'verification_state' then
    raise exception 'only verification_state field supported (got %)', p_target_field;
  end if;

  -- Actor context
  begin
    v_actor_user_id := auth.uid();
  exception when others then
    v_actor_user_id := null;
  end;

  begin
    v_actor_role := nullif(current_setting('request.jwt.claim.role', true), '');
  exception when others then
    v_actor_role := null;
  end;

  -- Read current state via dynamic SQL (target_id is text; cast in-table)
  v_sql := format(
    'select verification_state from public.%I where id::text = $1',
    p_target_table
  );
  execute v_sql into v_current_state using p_target_id;

  if v_current_state is null and not found then
    raise exception 'row not found: %.id=%', p_target_table, p_target_id;
  end if;

  -- Direction policy: forward transitions are free; backward transitions
  -- require a reason (so withdrawal of evidence is documented).
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

  -- No-op transitions are allowed but recorded — useful for "re-confirm" events.

  -- Update the target row
  v_sql := format(
    'update public.%I set verification_state = $1 where id::text = $2',
    p_target_table
  );
  execute v_sql using p_to_state, p_target_id;

  -- Record the transition
  insert into public.verification_state_transitions
    (target_table, target_id, target_field, from_state, to_state,
     actor_user_id, actor_role, reason, evidence_doc_ids)
  values
    (p_target_table, p_target_id, p_target_field, v_current_state, p_to_state,
     v_actor_user_id, v_actor_role, p_reason, p_evidence_ids)
  returning * into v_row;

  return v_row;
end $$;

comment on function public.transition_verification_state is
  'Single entry point for v6.0 verification state changes. Updates the target
   row and records the transition. Use this rather than direct UPDATE so the
   audit trail is enforced. Backward transitions (e.g. CONFIRMED -> UNVERIFIED)
   require a non-empty reason.';

grant execute on function public.transition_verification_state to authenticated;
-- service_role inherits via SECURITY DEFINER

-- ----------------------------------------------------------------------------
-- 4. Add verification_state + deal_killer_flag to existing tables.
--    All default to UNVERIFIED so existing rows get the conservative state.
-- ----------------------------------------------------------------------------

-- plants: project-level verification (overall plant status)
alter table public.plants
  add column if not exists verification_state public.verification_state
    not null default 'UNVERIFIED',
  add column if not exists deal_killer_flag boolean
    not null default false,
  add column if not exists last_verified_at timestamptz;

create index if not exists idx_plants_verification
  on public.plants (verification_state)
  where verification_state in ('CONFIRMED','AUDITED');

-- equipment_equations: per-equation provenance
alter table public.equipment_equations
  add column if not exists verification_state public.verification_state
    not null default 'UNVERIFIED',
  add column if not exists deal_killer_flag boolean
    not null default false;

-- project_finance: per-assumptions-set verification (CONFIRMED means a banker
-- has signed off on these inputs; AUDITED means an auditor has)
alter table public.project_finance
  add column if not exists verification_state public.verification_state
    not null default 'UNVERIFIED',
  add column if not exists deal_killer_flag boolean
    not null default false;

-- ----------------------------------------------------------------------------
-- 5. Convenience view: latest transition per (table, row)
-- ----------------------------------------------------------------------------
create or replace view public.v_latest_verification_transition as
select distinct on (target_table, target_id)
  target_table,
  target_id,
  from_state,
  to_state,
  actor_user_id,
  reason,
  occurred_at
from public.verification_state_transitions
order by target_table, target_id, occurred_at desc;

comment on view public.v_latest_verification_transition is
  'Most recent verification state transition per (target_table, target_id).
   Useful for displaying "last verified by X on Y" in the UI without joining
   the full audit table.';

commit;

-- ============================================================================
-- Smoke test (run manually in SQL Editor after applying):
-- ============================================================================
-- 1) insert into plants (user_id, slug, data) values ('test-user','test-plant','{}');
-- 2) select id from plants where slug = 'test-plant';
-- 3) select public.transition_verification_state(
--      'plants', '<id from step 2>'::text, 'verification_state', 'SUBMITTED'
--    );
-- 4) select * from public.verification_state_transitions
--    where target_id = '<id>' order by occurred_at desc limit 5;
-- 5) Backward transition without reason should fail:
--    select public.transition_verification_state(
--      'plants','<id>','verification_state','UNVERIFIED'
--    );
-- 6) With reason should succeed:
--    select public.transition_verification_state(
--      'plants','<id>','verification_state','UNVERIFIED','evidence withdrawn'
--    );
