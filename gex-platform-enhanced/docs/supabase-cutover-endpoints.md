# Supabase cutover — backend endpoints to replace the anonymous reads

**Status: COMPLETE.** All five increments cut over 2026-09-20. The frontend contains no
Supabase call, no client and not the dependency; a clean build has no anon key and no
`supabase` string in it. `scripts/audit-supabase.mjs` fails the build if any of it
returns, with an empty allowlist.

**One step remains and only Jim can take it: rotate the anon key in the Supabase
dashboard.** Deleting it from the source stops it shipping in future builds; it does not
invalidate the value, which is still live and still recoverable from git history, from
previously deployed bundles and from the public Docker Hub images. Enabling RLS on the
seven tables is worth doing as well — nothing in GEX reads them any more, so it costs
nothing.

**Correction carried from increment 3:** §0(b) below called the bucket public. It is not
— the public URL answers 404. The anon key reads and lists it, which is the real exposure,
and because the bucket is private the app's own `getPublicUrl` read path never worked at
all. See CLAUDE_HANDOFF §7.
**Date:** 2026-09-20.
**Why:** every table behind the frontend's `supabase.from()` calls is readable
by anyone on the internet with the baked-in anon key, and the write probe
returned `PGRST204` — authorization passed, only schema validation failed. The
durable fix is the one already recorded as §5.1 / §8.6: *deal and product data
belongs behind the backend*. This document is the endpoint list that makes that
possible.

---

## 0. Two findings that change the scope you asked for

You asked for the endpoints that replace **these reads**. Two things mean a
read-only replacement would not close the hole.

**(a) `plants` is not read-only — it is the canvas's write path.**
`PlantBuilder.tsx`, `iterations.ts` and `useCanvasData.ts` do `insert`,
`upsert`, `update` and `delete` against it. If the reads move but the writes
stay, the anon key stays in the bundle and RLS still cannot be turned on. The
writes are in scope or the exercise fails.

Two defects visible while reading those writes, both caused by anon access:

- `savePlantsToCloud` (PlantBuilder.tsx:197‑199) does `delete().eq("user_id")`
  then `insert(rows)` with **no transaction**. A failure between the two wipes
  the user's whole portfolio. PostgREST cannot make those atomic; one backend
  endpoint can.
- `useEquipmentEquations.remove` (`.delete().eq("id", id)`) carries **no user
  scoping at all**. With the anon key that deletes any row by id, for anyone.

**(b) Supabase Storage is in use — and the read path is broken.**
Not just tables. Five files touch `sb.storage.from("plant-data")` — 8 uploads,
12 lists, 6 removes, and **6 `getPublicUrl()` calls**.

I first wrote here that `getPublicUrl` implied a *public* bucket. **Tested
2026-09-20, that was wrong**, and the truth is more interesting:

- `/storage/v1/object/public/plant-data/…` answers **404 "Bucket not found"** —
  the bucket is private, verified both from the shell and in the running app.
- The **anon key reads and lists the whole bucket** (200, 18 kB of canvas
  JSON). That key ships in the public bundle, so the exposure is real; it just
  needs the key rather than only a URL.
- And because the bucket is private, **every `getPublicUrl` read has been
  failing**. Cloud saves worked, cloud loads always 404'd and fell back to
  localStorage silently. A user on a new device did not get their canvas back.

The bucket holds the actual canvas content — plant topology, equipment, site
infrastructure, custom libraries — and RLS does not cover it; bucket visibility
is a separate setting. Increment 3 is therefore a data-loss repair as well as a
security fix.

It also corrects §8.14: the platform *does* have file storage. It is in the
frontend, under an anon key, not in the backend.

---

## 1. What is being replaced

| Supabase surface | Rows | Callers | Verbs today |
|---|---|---|---|
| `teams` | 8 | `useTeamData` | select |
| `roles` | 31 | `useTeamData` | select |
| `team_users` | 19 | `useTeamData` | select |
| `permission_gates` | 7 | `useTeamData` | select |
| `user_gate_status` | 32 | `useTeamData` | select |
| `plants` | 53 | PlantBuilder, plantStore, iterations, useCanvasData | select, insert, upsert, update, delete |
| `equipment_equations` | 2 | useEquipmentEquations | select, upsert, delete |
| storage `plant-data` | — | PlantBuilder, useCanvasData, iterations, siteInfrastructure, customLibrary | upload, list, remove, getPublicUrl |
| `equation_engine_runs`, `v_latest_engine_run`, rpc | **absent (404)** | `dealClient.ts` | — |

`dealClient.ts` targets tables that do not exist in the project and **has no
callers** — the only file mentioning it is itself. It needs no endpoint. Delete
it (§6).

---

## 2. The identity question — MEASURED 2026-09-20, and it reverses my advice

`team_users` holds 19 people with `email`, `full_name`, `phone`,
`organisation`. **Measured in the 2026-09-20 export:** all 19 carry a name and
a working email (17 `@greenearthx.com`, 2 `@etfuels.com`); `phone` is empty in
every row and `organisation` is null in 14. Earlier notes in this session said
"email and phone" — that came from the column list, not the data, and is
corrected here. The columns still need the staff-only rule, because an empty
column is a fact about today, not a property of the table. `auth_users` holds 17 accounts with `email`, `user_name`,
`business_function`, `company_*`. These are two identity stores for
overlapping people — the dual-identity defect already on the register.

Moving the directory behind the backend forces the question, because I must put
the rows somewhere:

- **(A) Fold into `auth_users`** — add `teams`, `roles`, `permission_gates`,
  `user_gate_status` keyed on `auth_users.user_id`, and reconcile the 19 against
  the 17 by email. One identity, one vetting path, one place where somebody is
  deactivated. More work now; removes the defect.
- **(B) Import as a separate `staff_directory` read-model** — faithful copy of
  the five tables, no reconciliation. Fast; keeps two identity stores and the
  drift, which is exactly what the architecture doctrine forbids.

I originally recommended **(A)**, reasoning that two identity stores let a
person be removed in one and keep access through the other. The import ran the
comparison, and the data says otherwise.

### What the reconciliation actually found

| | |
|---|---|
| directory members with an `auth_users` account (by email) | **0 of 19** |
| accounts with a directory entry | **0 of 17** |
| same person, different address (name candidates) | **2** |

The two populations are **disjoint by design, not by drift**:

- `auth_users` is the **counterparty** table — banks, insurers, offtakers, an
  EPC (`nordlb`, `abnamro`, `allianz`, `zurich`, `siemens-energy`, `madrid2`,
  `hamburgone`, `brementhree`, `rotterdamofftake4`, `rheinwerk`), plus exactly
  one GEX address: `admin@greenearthx.com`.
- The directory is **GEX's own staff** — 17 `@greenearthx.com` people, none of
  whom hold a platform account, plus two ETFuels partners.

The only genuine overlap is those two: `felix@etfuels.com` /
`thierry@etfuels.com` in the directory are `felix.leworthy@etfuels.com` /
`thierry.groell@etfuels.com` in `auth_users` — the same two people under a
short and a full address. An email-only match misses them, which is why the
reconciliation now reports **name candidates** as well.

### Revised recommendation: (B), with the bridge

Folding is not deduplication here. It would mean creating 17 platform accounts
for staff who have none and, under `LOGIN_PERMITTED_STATES = {ACTIVE}` and the
vetting gate, should not silently acquire one. The defect I was guarding
against — one person, two records, drifting — applies to **2 rows, not 19**,
and `auth_user_id` already carries them once a human confirms the pairing.

So: keep two tables, and make the relationship explicit rather than implicit.
`auth_users` answers "who may sign in"; the directory answers "who works here
and on which team". They are different questions about different populations.

**Still yours to decide:** (i) confirm or reject those two pairings —
`reconcile_with_auth_users()` reports them and deliberately does not write
them, because two people can share a name and auto-linking would hand one
person another's account; and (ii) whether two ETFuels partners belong in
GEX's internal team directory holding permission gates at all. That second one
is a business question, not an engineering one.

Everything below is written so Group A's *HTTP contract* is identical either
way; only the storage layer behind it differs.

---

## 3. Group A — directory (replaces 5 tables, read-only) — **BUILT**

Prefix `/api/v1/directory` · domain `governance` · guard: authenticated, plus a
PII rule.

Built 2026-09-20 as specified below, in `app/api/v1/routes_directory.py`,
`app/core/directory_store.py`, `scripts/import_directory.py` and
`tests/test_directory_endpoints.py`. Two refinements made during the build:

- **GEX staff is `is_platform_admin`.** This section originally named two
  checks; `assert_activator_is_gex_staff` tests the same flag as
  `has_platform_admin_access`, so the code calls one. Two checks that mean the
  same thing are two checks that can drift.
- **`directory_members.auth_user_id`** (nullable) and
  `reconcile_with_auth_users()` were added so §2 can be *measured* before it is
  decided. `test_the_directory_grants_nothing` fails if any module outside the
  directory imports the store, so a read-model cannot quietly become the second
  identity authority while the decision is open.

`useTeamData` fires all five queries together on mount, so one composite
endpoint replaces five round trips. The two refetch paths it exposes
(`refetchUsers`, `refetchGateStatuses`) get their own endpoints.

```
GET  /api/v1/directory/overview
     → { teams[], roles[], members[], gates[], gate_statuses[] }
GET  /api/v1/directory/members            → members[]        (refetchUsers)
GET  /api/v1/directory/gate-status        → gate_statuses[]  (refetchGateStatuses)
```

Response shapes are the existing TS interfaces unchanged (`TeamRow`, `RoleRow`,
`TeamUserRow`, `PermissionGate`, `GateStatusRow`), so `useTeamData` changes its
transport and nothing else. Ordering moves server-side: teams by `name`, roles
by `role_code`, members by `full_name` — matching today's `.order()` calls.

**ACCESS RULE — corrected 2026-09-20, and it supersedes what this section
originally said.** GEX staff only. The first version admitted any
authenticated caller to the org chart and withheld just the addresses; a live
check found a counterparty account reading GEX's teams, roles and permission
gates. **No user of a paying customer may read GEX's internal directory in any
instance.** All three endpoints answer 403 to a non-staff caller. Scoping by
organisation was rejected on the data (null in 14 of 19 rows).

This is a specific case of a general rule that the remaining increments must
respect: GEX governs who may see, enter, modify and delete what, and who may
communicate with whom inside and outside their own organisation. Read access
is not "authenticated" — it is "entitled".

**PII rule, kept underneath the access rule as defence in depth.** `email` and
`phone` are returned only to a caller passing
`has_platform_admin_access(payload)` (the check `routes_fuels.py:56` uses) or
GEX staff (`assert_activator_is_gex_staff`, `routes_account_vetting.py:69`).
Every other authenticated caller gets `full_name`, `organisation`, `status`,
team and role ids, with `email` and `phone` **omitted from the JSON**, not
nulled — an absent key cannot be mistaken for "no phone on file".

Anonymous callers get 401 from the global `require_authenticated`.

---

## 4. Group B — plants (read **and** write) — **BUILT AND CUT OVER 2026-09-20**

Backend, migration and frontend all done; `plants` in Supabase has no caller.
RLS can be enabled on it. See CLAUDE_HANDOFF §7 for the measurements. The
`plant-data` storage bucket is untouched and remains public — increment 3.

Prefix `/api/v1/plants` · domain `projects` · guard: authenticated; owner-scoped.

```
GET    /api/v1/plants                → [{ slug, data, updated_at }]
GET    /api/v1/plants/{slug}         → { slug, data, updated_at }        404 if none
PUT    /api/v1/plants/{slug}         upsert one plant   (body: ProjectRecord)
DELETE /api/v1/plants/{slug}         remove one plant + its blobs
POST   /api/v1/plants/{slug}/touch   bump updated_at only   (useCanvasData.ts:356)
PUT    /api/v1/plants                bulk replace — see below
```

**The rule that makes this worth doing:** `user_id` is derived from the bearer
token and **never accepted from the client**. Today every call passes
`user_id` explicitly and the anon key honours it, so any visitor can read or
overwrite any user's portfolio by guessing a uuid. After the cutover that is
not expressible.

`PUT /api/v1/plants` replaces `savePlantsToCloud`'s delete-all-then-insert. It
runs inside one transaction, so the wipe described in §0(a) cannot happen. It
also refuses a body that would delete more than it writes unless
`?confirm_delete=<n>` matches the count being removed — a guard against an empty
array arriving from a half-initialised client and clearing the portfolio.

Storage: the existing project store, `data` as a JSON column, unique on
`(user_id, slug)` — the same constraint the `onConflict` clauses already assume.

---

## 5. Group C — canvas blobs — **BUILT AND CUT OVER 2026-09-20**

499 objects migrated, five frontend modules switched, no `storage.from()` call
left in the tree. See CLAUDE_HANDOFF §7 for the measurements and the two
corrections.

## 5. Group C — canvas blobs (replaces the `plant-data` bucket)

Prefix `/api/v1/plant-canvas` · domain `projects` · guard: authenticated;
owner-scoped.

The bucket holds three kinds of object under one namespace. Keeping them
distinct in the API stops the next person from inventing a fourth:

```
GET    /api/v1/plant-canvas/canvas/{slug}              → canvas JSON
PUT    /api/v1/plant-canvas/canvas/{slug}              → save (replaces upload upsert:true)
GET    /api/v1/plant-canvas/canvas/{slug}/versions     → [{ version_id, created_at, size }]
GET    /api/v1/plant-canvas/canvas/{slug}/versions/{version_id}
DELETE /api/v1/plant-canvas/canvas/{slug}              → object + its versions
GET/PUT /api/v1/plant-canvas/site/{slug}               (siteInfrastructure.ts)
GET/PUT /api/v1/plant-canvas/library                   (customLibrary.ts, per user)
```

**`getPublicUrl` has no replacement, by design.** The six call sites fetch a
public URL and then read it. They become a direct authenticated `GET` returning
the bytes. There is no signed-URL story here and there does not need to be —
these are small JSON documents, not media.

Storage mechanism: reuse the pattern already in the tree at
`development_packages.py:1101` — bytes on disk under a docs root, content
addressed by sha256, metadata row (path, sha, size, updated_at) in the store.
It works, it is auditable, and it is the only file-write path the backend has.
Version retention keeps the existing prune rule (newest 100 per plant).

This is the increment that also closes §8.14: after it, the backend has a real,
authenticated document path.

---

## 6. Group D — equipment equations — **BUILT AND CUT OVER 2026-09-20**

Both rows migrated, the unscoped delete closed (§8.16), `dealClient.ts`
deleted, and `audit-supabase.mjs` added to the build to keep it shut.

## 6. Group D — equipment equations, and the dead client

Prefix `/api/v1/equipment-equations` · domain `projects` · owner-scoped.

```
GET    /api/v1/equipment-equations?plant_slug=&node_id=   → StoredEquipmentEquation[]
PUT    /api/v1/equipment-equations                        upsert on
                                                          (user, plant, node, equation_id)
DELETE /api/v1/equipment-equations/{id}                   404 unless the row is the caller's
```

The `DELETE` ownership check is the fix for the unscoped delete in §0(a). A row
belonging to someone else returns **404, not 403** — a 403 would confirm the id
exists.

`dealClient.ts`: delete the file. Its tables are absent from the project and
nothing imports it.

---

## 7. Realtime — RESOLVED 2026-09-20 by deletion

Both hooks were removed, because measurement made the choice for me: neither
was doing anything. `useCanvasLiveSync` was called with arguments that stop it
opening a channel at all (disabled earlier over feedback loops), and
`useCanvasPresence` filtered every peer out as "self" because the stubbed
AuthContext gives every user the same id. Since increment 2 a canvas is a
per-user document, so there is no shared object to be present on either.

If real collaboration arrives — shared canvases with distinct identities —
option 2 below is the way back, and it needs a real `AuthContext` first
(§8.17). The original options are kept for that day.

### The options as originally written

These two use `supabase.channel()` / `.subscribe()`, which no REST endpoint
replaces, and §9 records the decision **not** to build WebSockets.

Three honest options:

1. **Drop realtime.** Single-editor canvas, last-write-wins, plus the existing
   `touch` endpoint so other tabs see a fresh `updated_at` on focus. Cheapest;
   loses live cursors. *Recommended for the cutover* — it is what unblocks
   turning the anon key off.
2. **Poll for presence.** `POST /api/v1/plants/{slug}/presence` heartbeat +
   `GET` returning heartbeats from the last 60s, polled every 15s. Restores the
   "who else is here" dot without a socket or reopening §9. ~40 lines.
3. **Keep Supabase realtime only,** with RLS on and an authenticated JWT. Keeps
   the anon key and the second identity store alive. Not recommended — it is
   the one option that leaves the original problem in place.

Option 1 now, option 2 if the presence dot turns out to matter, is my
recommendation. It does not need deciding before Group A starts.

---

## 8. Build order

Each increment is shippable and reduces exposure on its own.

| # | Increment | Closes |
|---|---|---|
| 1 ✅ | Group A — directory | 19 names + emails incl. 2 at a partner firm; the GDPR question |
| 2 ✅ | Group B — plants | 53 plants incl. `data` and `user_id`; the wipe bug |
| 3 ✅ | Group C — canvas blobs | the public bucket |
| 4 | Group D + delete `dealClient.ts` | the unscoped delete — **done** |
| 5 | Realtime decision, then revoke the anon key | the key itself — **only this is left** |

Per increment, the house rules already in force: a router registered in
`main.py`, a `DOMAIN_PREFIXES` entry (or `test_every_api_route_maps_to_a_domain`
fails CI), tests using `isolated_store`, and one negative test per guard —
break the guard, watch the test fail, restore it.

**Data migration.** Rows must move before the key is revoked: export via the
anon key (we already have read access — 53 + 19 + 31 + 32 + 8 + 7 + 2 rows and
the bucket's objects), import into the backend store, diff the counts. Do the
export *first*, whatever else is decided.

**Sequencing against RLS.** Enabling RLS now breaks the plant canvas, plant
list, iterations, equipment equations, team screens and realtime sync —
nothing else, since the backend, auth and engines never touch Supabase. Either:

- **Close first:** enable RLS today, accept those internal screens break for the
  duration of the build. Exposure stops now.
- **Build first:** leave it open until increment 5. The screens keep working;
  the data stays public for as long as the build takes.

Given the personal data in `team_users`, closing first is the defensible choice,
and increment 1 is the shortest path back to a working team screen.

**Keeping it shut.** A frontend build gate — `audit-supabase.mjs`, in the style
of `audit-menu.mjs` — failing the build on any new `supabase.from(` or
`.storage.from(` outside a shrinking allowlist. Without it this grows back one
convenient call at a time.
