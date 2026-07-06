-- ============================================================================
-- Sprint 1 — RLS hardening
-- ============================================================================
-- Purpose:
--   Replace the current `USING (true)` policies on `plants` and
--   `equipment_equations` with ownership-aware policies. Remove the dangerous
--   anon write policies on `team_users` and `user_gate_status`.
--
-- WARNING — POTENTIALLY BREAKING
--   The existing policies allow anonymous and credentials/demo users to do
--   anything. Tightening them will lock out:
--     - demo / credentials users (AuthContext.provider in 'credentials','demo')
--       because they don't have an `auth.uid()`.
--     - any code that was relying on the permissive policies.
--
--   Recommended path:
--     (a) Apply 20260518120000 (verification state) first — it's additive.
--     (b) Test the engine + frontend integration end-to-end with the
--         additive migration only.
--     (c) Audit which app paths use demo / credentials providers. Decide
--         whether to (i) gate them behind a separate Postgres role, or
--         (ii) retire them in production.
--     (d) Apply THIS migration in a maintenance window. Have the rollback
--         block at the bottom ready.
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 1. plants — replace USING(true) with ownership check.
-- ----------------------------------------------------------------------------
-- The existing user_id column is TEXT (not UUID) because Lovable supports
-- both OAuth users (uuid string) and credentials/demo (synthetic string).
-- For real users, JWT `sub` (UUID) is cast to text for comparison.

drop policy if exists "Anyone can read plants" on public.plants;
drop policy if exists "Anyone can insert plants" on public.plants;
drop policy if exists "Anyone can update plants" on public.plants;
drop policy if exists "Anyone can delete plants" on public.plants;

create policy "Authenticated read own plants"
  on public.plants for select to authenticated
  using (auth.uid()::text = user_id);

create policy "Authenticated insert own plants"
  on public.plants for insert to authenticated
  with check (auth.uid()::text = user_id);

create policy "Authenticated update own plants"
  on public.plants for update to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

create policy "Authenticated delete own plants"
  on public.plants for delete to authenticated
  using (auth.uid()::text = user_id);

-- Service role bypasses RLS automatically — used by gex_pf_engine.

-- ----------------------------------------------------------------------------
-- 2. equipment_equations — same treatment.
-- ----------------------------------------------------------------------------
-- equipment_equations has no user_id today. The original `USING (true)` is
-- semantically "global library of equipment equations, anyone can edit".
-- For Sprint 1 we keep global READ but require authenticated WRITE — and
-- only allow service_role to delete (i.e. lock the catalog from end users).

drop policy if exists "Anyone can read equipment_equations" on public.equipment_equations;
drop policy if exists "Anyone can insert equipment_equations" on public.equipment_equations;
drop policy if exists "Anyone can update equipment_equations" on public.equipment_equations;
drop policy if exists "Anyone can delete equipment_equations" on public.equipment_equations;

create policy "Authenticated read equipment_equations"
  on public.equipment_equations for select to authenticated
  using (true);

create policy "Authenticated insert equipment_equations"
  on public.equipment_equations for insert to authenticated
  with check (true);

create policy "Authenticated update equipment_equations"
  on public.equipment_equations for update to authenticated
  using (true) with check (true);

-- No delete policy → only service_role can delete.

-- ----------------------------------------------------------------------------
-- 3. Remove the anonymous write policies on team-related tables.
--    Migration 20260330164528 introduced these for demo flows. They allow
--    any unauthenticated visitor to write to team_users / user_gate_status.
--    In any environment with real users these are unacceptable.
-- ----------------------------------------------------------------------------

drop policy if exists "Anon can insert team_users" on public.team_users;
drop policy if exists "Anon can update team_users" on public.team_users;
drop policy if exists "Anon can insert user_gate_status" on public.user_gate_status;
drop policy if exists "Anon can update user_gate_status" on public.user_gate_status;
drop policy if exists "Anon can delete user_gate_status" on public.user_gate_status;

-- The authenticated admin policies from 20260326072342 remain in place.

-- Optional: remove anon READ on the same tables. Keep this commented until
-- you've confirmed nothing in the marketing surface relies on it.
-- drop policy if exists "Anon can read teams" on public.teams;
-- drop policy if exists "Anon can read roles" on public.roles;
-- drop policy if exists "Anon can read team_users" on public.team_users;
-- drop policy if exists "Anon can read permission_gates" on public.permission_gates;
-- drop policy if exists "Anon can read user_gate_status" on public.user_gate_status;

commit;

-- ============================================================================
-- Rollback (run if Sprint 2 needs the old behaviour back temporarily):
-- ============================================================================
-- begin;
--
-- create policy "Anyone can read plants"
--   on public.plants for select using (true);
-- create policy "Anyone can insert plants"
--   on public.plants for insert with check (true);
-- create policy "Anyone can update plants"
--   on public.plants for update using (true) with check (true);
-- create policy "Anyone can delete plants"
--   on public.plants for delete using (true);
--
-- create policy "Anyone can read equipment_equations"
--   on public.equipment_equations for select using (true);
-- create policy "Anyone can insert equipment_equations"
--   on public.equipment_equations for insert with check (true);
-- create policy "Anyone can update equipment_equations"
--   on public.equipment_equations for update using (true) with check (true);
-- create policy "Anyone can delete equipment_equations"
--   on public.equipment_equations for delete using (true);
--
-- create policy "Anon can insert team_users"
--   on public.team_users for insert to anon with check (true);
-- create policy "Anon can update team_users"
--   on public.team_users for update to anon using (true) with check (true);
-- create policy "Anon can insert user_gate_status"
--   on public.user_gate_status for insert to anon with check (true);
-- create policy "Anon can update user_gate_status"
--   on public.user_gate_status for update to anon using (true) with check (true);
-- create policy "Anon can delete user_gate_status"
--   on public.user_gate_status for delete to anon using (true);
--
-- commit;
