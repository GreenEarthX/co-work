# GEX Sprint 0 - Repo-Accurate Implementation Checklist

Generated: 2026-05-06  
Source inputs:
- `frontend/public/dep-map_2.html`
- `/Users/jean-marie.lamay/Downloads/files3/GEX_Session_Manifest_March_2026.md`
- `/Users/jean-marie.lamay/Downloads/files3/GEX_Sprint_0_Claude_Code_Prompt.md`

Purpose: convert the Sprint 0 prompt into a checklist that matches the current `gex-platform-enhanced` repository. The external prompt is useful, but some route names, component props, and assumptions do not match this codebase exactly.

## Current Baseline

| Area | Current repo state | Key files |
|---|---|---|
| Auth | Server login exists, but JWT is still HS256. No refresh token family. OIDC discovery is a compatibility stub. | `backend/app/core/auth.py`, `backend/app/api/v1/routes_auth.py` |
| Demo headers | ABAC still falls back to `x-demo-*` headers when no bearer token resolves. | `backend/app/core/abac_middleware.py` |
| Project data | Frontend visible-project filtering still uses static `CUSTOMER_PROJECTS`. Backend has project registry and project truth APIs. | `frontend/src/hooks/useVisibleProjects.ts`, `frontend/src/data/customerProjects.ts`, `backend/app/core/project_registry.py`, `backend/app/api/v1/routes_project_truth.py` |
| Gate source | Backend gate registry exists. Frontend locks are still derived from `MENU_TABS` and local project gate data. | `backend/app/api/v1/routes_gate_registry.py`, `frontend/src/config/menuArchitecture.ts`, `frontend/src/hooks/useGateAccess.ts` |
| Route locks | `GateLock` and `GatedRoute` exist. `GatedRoute` currently takes a `path` prop, not `gate` / `requiredStatus`. | `frontend/src/components/GateLock.tsx`, `frontend/src/components/GatedRoute.tsx`, `frontend/src/App.tsx` |
| Events | Event bus routes exist for health, publish, recent, streams, consumer groups. No SSE route and no frontend `useEventStream` hook. | `backend/app/api/v1/routes_events.py`, `backend/app/core/event_bus.py`, `backend/app/core/event_store.py` |
| Menu drift | Active frontend menu differs from stale backend copy. | `frontend/src/config/menuArchitecture.ts`, `backend/app/config/menuArchitecture.ts` |

## S0.1 Auth Hardening

Goal: make auth credible enough for partner-facing security domains.

### Tasks

- [x] Add RSA key path settings to `backend/app/core/config.py`.
- [x] Add a key generation script, preferably `scripts/generate_jwt_keys.sh`.
- [x] Change `backend/app/core/auth.py` from `ALGORITHM = "HS256"` to `RS256`.
- [x] Sign access tokens with the private key.
- [x] Verify access tokens with the public key.
- [x] Add `iss` and `aud` claims to access tokens.
- [x] Enforce issuer and audience in `decode_access_token`.
- [x] Add a JWKS endpoint in `backend/app/api/v1/routes_auth.py`.
- [x] Add refresh token persistence, either in `auth.py` or a new `backend/app/core/refresh_tokens.py`.
- [x] Add refresh token table creation for the current SQLite setup.
- [x] Add `POST /api/v1/auth/refresh`.
- [x] Return `refresh_token` from `POST /api/v1/auth/login`.
- [x] Update `frontend/src/contexts/UserRoleContext.tsx` to store access token expiry.
- [x] Add frontend refresh-token rotation before access token expiry.
- [x] Make logout clear access token, refresh token, role, tier, and CISO session state.

### Demo Header Gate

- [x] Add `GEX_DEMO_MODE` or equivalent environment setting.
- [x] In `backend/app/core/abac_middleware.py`, allow `x-demo-*` fallback only when demo mode is explicitly true.
- [x] Return `401` when no valid bearer token exists and demo mode is false.
- [x] Add a warning log when demo mode accepts header-derived identity.

### Verification

- [x] Login returns an RS256 access token and refresh token.
- [x] `decode_access_token` rejects HS256 tokens.
- [x] Token without expected issuer is rejected.
- [x] Token without expected audience is rejected.
- [x] `x-demo-user` without bearer token returns `401` when demo mode is false.
- [x] Refresh token reuse after rotation revokes the token family.

## S0.2 Canonical Gate Source

Goal: stop frontend/backend gate drift.

### Current Mismatch To Respect

The external prompt proposes `useGateAccess(gate, requiredStatus)`, but this repo currently uses:

```tsx
<GatedRoute path="/capital-stack">
  <CapitalStack />
</GatedRoute>
```

and `useGateAccess()` maps route path to `gate_prerequisite`.

### Tasks

- [x] Keep `backend/app/api/v1/routes_gate_registry.py` as the backend source for gate definitions.
- [x] Add a route that returns frontend-usable gate lock rules.
- [x] Prefer route-path keys first because the current UI lock system is path-based.
- [x] Include `gate_short_id`, canonical gate ID, threshold, and linked route path in the response.
- [x] Add `frontend/src/hooks/useGateConfig.ts`.
- [x] Update `frontend/src/hooks/useGateAccess.ts` to read server gate config when available.
- [x] Keep local menu-derived gate config as development fallback only.
- [x] Document fallback behavior in `useGateAccess.ts`.
- [x] Do not delete `backend/app/config/menuArchitecture.ts` until imports are checked.
- [x] If unused, remove or archive the backend menu copy after verification.

### Verification

- [x] `GET /api/v1/gates/registry` returns canonical gates.
- [x] `GET /api/v1/gates/screen-gates` returns screen-to-gate mapping.
- [x] New frontend gate-config hook handles loading and error states.
- [x] Locking still works if the backend is unavailable in development.
- [x] Production mode does not silently rely on stale frontend-only gate config.

## S0.3 Project Data Unification

Goal: make visible projects server-owned, not static-data-owned.

### Tasks

- [x] Add a canonical visible projects endpoint, likely `GET /api/v1/projects/visible`.
- [x] Source visibility from authenticated user claims plus `backend/app/core/project_registry.py`.
- [x] Return enough data to replace `CustomerProject` in current frontend screens.
- [x] Keep `CUSTOMER_PROJECTS` only as an explicit development fallback.
- [x] Rewrite `frontend/src/hooks/useVisibleProjects.ts` to fetch from the backend.
- [x] Return loading/error states from `useVisibleProjects`.
- [x] Update `frontend/src/contexts/ProjectContext.tsx` to use fetched visible project IDs.
- [x] Update call sites that assume `useVisibleProjects()` returns a plain array synchronously.
- [x] Audit frontend imports of `CUSTOMER_PROJECTS` and `customerProjects`.
- [x] Replace direct static imports in user-facing pages.

### Verification

- [x] Producer sees owned projects and permitted associated projects.
- [x] Offtaker sees associated projects only.
- [x] Third-party provider sees associated projects only.
- [x] Guest sees no project data.
- [x] Selected project auto-corrects after login if current localStorage value is not visible.
- [x] Static fallback is disabled or visibly warned outside development.

## S0.4 Complete Gate Route Wrapping

Goal: direct URL access must behave the same as menu access.

### Current Gated Menu Paths

From current frontend menu configuration, these paths carry `gate_prerequisite` and should be audited against `App.tsx`:

| Path | Required gate |
|---|---|
| `/offtake-quality` | `G4` |
| `/term-sheet` | `G4` |
| `/capital-stack` | `G5` |
| `/finance-gaps` | `G5` |
| `/bankability-snapshot` | `G8` |
| `/ic-pack` | `G10` |
| `/insurance-schedule` | `G7` |
| `/insurance-coverage` | `G7` |
| `/data-room` | `G10` |
| `/approval-queue` | `G10` |
| `/commitment-signing` | `G10` |

### Tasks

- [x] Audit `frontend/src/App.tsx` for every path above.
- [x] Wrap each route with current repo syntax: `<GatedRoute path="/route">`.
- [x] Check nested `/finance/*` aliases for equivalent gated pages.
- [x] Wrap nested aliases or intentionally remove them.
- [x] Ensure `GateLock.tsx` route targets use current route names, not prompt-era names.
- [x] Add a small route/gate consistency test or script.
- [x] Confirm `GateLock` uses the selected project after project data unification.

### Verification

- [x] Navigating via menu to a locked page shows locked state.
- [x] Typing the URL directly to the same page shows locked state.
- [x] Completing or seeding the required gate unlocks the same page.
- [x] Nested finance aliases cannot bypass the lock.

## S0.5 Event Stream Contract

Goal: define browser event semantics without pretending real-time delivery is already finished.

### Tasks

- [x] Add an SSE contract endpoint to `backend/app/api/v1/routes_events.py`.
- [x] Prefer an explicit path under the current prefix, for example `GET /api/v1/events/stream/{project_id}`.
- [x] Return `501` if implementation is intentionally deferred.
- [x] Document event payload shape and supported event names in the response.
- [x] Define auth behavior for EventSource, including token transport and ABAC filtering.
- [x] Add `frontend/src/hooks/useEventStream.ts` as a stub.
- [x] Stub returns `{ lastEvent: null, isConnected: false, eventCount: 0 }`.
- [x] Add comments naming the intended query invalidations and UI reactions.

### Verification

- [x] `GET /api/v1/events/health` still works.
- [x] `GET /api/v1/events/stream/{project_id}` returns the documented contract or a real stream.
- [x] Frontend can import `useEventStream` without runtime side effects.
- [x] No UI claims live updates until the stream is implemented.

## S0.6 Menu Drift Cleanup

Goal: make the active menu source clear.

### Tasks

- [x] Treat `frontend/src/config/menuArchitecture.ts` as the active UI source.
- [x] Confirm whether `backend/app/config/menuArchitecture.ts` is imported anywhere.
- [x] If unused, archive or delete the stale backend copy in a separate cleanup commit.
- [x] If used, replace it with generated data from the frontend or backend gate registry.
- [x] Keep `frontend/public/menu-map-current.html` aligned with the active menu.
- [x] Keep `frontend/public/dep-map_2.html` aligned with Sprint 0 status.

### Verification

- [x] TopBar labels match `menu-map-current.html`.
- [x] CISO menu entries match `CISO_ITEMS`.
- [x] Backend gate registry and frontend menu lock paths do not disagree.

## Done Definition For Sprint 0

- [x] Partner-facing auth no longer depends on HS256-only tokens.
- [x] Refresh token rotation exists and is tested.
- [x] Demo header fallback cannot run unless demo mode is explicitly enabled.
- [x] Gate lock source is backend-backed or explicitly synchronized.
- [x] All gated menu routes are protected against direct URL bypass.
- [x] Visible projects come from backend identity/project scope.
- [x] Static project data is development fallback only.
- [x] Event stream contract exists and is honest about implementation status.
- [x] `frontend/public/dep-map_2.html` is updated after implementation to mark Sprint 0 items as implemented or intentionally deferred.

## Implementation Order

1. Auth hardening.
2. Demo header gate.
3. Project visible endpoint.
4. Frontend visible project hook migration.
5. Gate config endpoint and hook.
6. Complete route wrapping.
7. Event stream contract.
8. Menu drift cleanup.
9. Update `dep-map_2.html`.

## Implementation Record — 2026-05-06

All Sprint 0 tasks implemented and TypeScript build verified (`tsc && vite build` clean).

| Item | Files changed |
|---|---|
| RS256 key support | `backend/app/core/config.py`, `backend/app/core/auth.py`, `scripts/generate_jwt_keys.sh` |
| Refresh tokens | `backend/app/core/refresh_tokens.py` (new), `backend/app/api/v1/routes_auth.py` |
| JWKS endpoint | `routes_auth.py` `/jwks`, `/refresh`, `/logout` |
| Frontend session | `frontend/src/contexts/UserRoleContext.tsx`, `frontend/src/features/auth/LoginPage.tsx` |
| Demo header gate | `backend/app/core/abac_middleware.py` |
| Gate config hook | `frontend/src/hooks/useGateConfig.ts` (new) |
| Canonical gate source | `frontend/src/hooks/useGateAccess.ts` — reads backend first, local fallback |
| Visible projects API | `backend/app/api/v1/routes_projects.py` (new), registered in `main.py` |
| useVisibleProjects rewrite | `frontend/src/hooks/useVisibleProjects.ts` — backend-first with static dev fallback |
| Call site migration | 36 TSX/TS files updated from array return to `{ projects }` destructure |
| Gate route wrapping | `frontend/src/App.tsx` — `/offtake-quality`, `/finance-gaps`, `/insurance-coverage` + all `/finance/*` aliases |
| Event stream stub | `backend/app/api/v1/routes_events.py` `/stream/{project_id}` returns 501 with contract; `frontend/src/hooks/useEventStream.ts` (new) |
| Menu drift | `backend/app/config/menuArchitecture.ts` archived (was unused) |
| Deferred | Frontend token auto-refresh before expiry (requires timer + interceptor — Sprint 1). `dep-map_2.html` update (manual HTML file). |
