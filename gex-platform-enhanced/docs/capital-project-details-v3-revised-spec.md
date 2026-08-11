# Capital Project Details — Revised Build Spec (v3)

**Supersedes:** "Capital Project Details 2" · **Date:** 2026-07-20
**Change in one line:** same scope, same UX, same success criteria — but pointed at the
APIs that already exist instead of `localStorage`, with the state-machine and vocabulary
mappings filled in.

> **Why this revision exists.** The v2 spec assumed a greenfield prototype. It is not
> greenfield: Projects, Capital Packages, package evidence upload, and a 12-state
> package workflow are already live, persisted, and reachable from a typed front-end
> client (`frontend/src/api.ts`). Building the v2 spec as written would create a second
> Project registry and a second package lifecycle in browser storage, competing with
> working server-side ones. **Wiring to the live API is less work than building the
> mock, not more** — the client functions already exist.
>
> Genuinely net-new in this spec: **Activities**, **Deliverables**, and a
> **developer-facing Package Workspace**. (Package screens do exist — under *Finance*,
> built for a financier persona and demanding AACE estimate classes and actor IDs. The
> developer's view of that same object is missing.) That is where the build effort belongs.
>
> **On vocabulary:** where this spec keeps the v2 wording (Proposed/Approved/Funded,
> Concept→Investment Secured, "Fuel Type"), that is deliberate. v2's language is closer to
> Blueprint Law 3 — *familiar language, novel intelligence* — than the internal enums are.
> Adopt it at the surface; map it to the canonical model underneath. One vocabulary at the
> edge, one canonical store beneath, one mapping file between them.

---

## 0. What already exists (verified in code, 2026-07-20)

| Capability | Status | Where |
|---|---|---|
| Project create + list | **Live** | `POST /api/v1/projects`, `GET /api/v1/projects/visible` · `projectsAPI` in `frontend/src/api.ts` · UI at `/projects/new` |
| Project commercial context | **Live** | `PATCH /api/v1/projects/{id}/context` → `project_context` table |
| Capital Packages (CRUD) | **Live** | `/api/v1/packages` — 13 routes, 35-column table, versioned, content-hashed |
| Package state machine | **Live** | 12 states, forward-only, server-enforced |
| Package evidence upload | **Live** | `POST /api/v1/packages/{id}/evidence` (multipart, SHA-256, appends to `evidence_refs`) |
| Package event log | **Live** | `GET /api/v1/packages/{id}/events` |
| Typed front-end client | **Live** | `packagesAPI`: listForProject, summary, create, update, transition, capitalTransition, events, listEvidence, uploadEvidence |
| Readiness metrics (CEC/FRI) | **Live** | `/api/v1/pre-cod-metrics` |
| Bankability gate scoring | **Live** | `/api/v1/bankability` (verification-weighted) |
| Package UI — **financier-facing** | **Live** | `features/finance/PackageRegister.tsx` (457 ln, wired to `packagesAPI`), `PackageDetailDrawer.tsx` (485 ln), `PackageBuilder.tsx` (structuring recommendations) |
| **Activities** | **Net-new** | no table, no route — build it |
| **Deliverables** | **Net-new** | no table, no route — build it |
| **Package UI — developer-facing** | **Net-new** | the package screens above live under *Finance* and demand AACE estimate class, `phase_required`, and a `discipline_owner` actor ID. A developer creating a first package cannot use them. This spec builds the **developer persona's** view of the same server-side object — a missing surface, not a duplicate. |

⚠️ **Naming collision to resolve first:** `routes_project_activity.py` already exists and
means *audit feed event*, not *work activity*. Name the new concept **`package_activity`**
in both API and UI to avoid a permanent ambiguity.

---

## 1. Project creation — use the existing flow, extend it

**Do not build a new Project object.** `/projects/new` already exists and POSTs a typed
payload to the live API. This spec **extends** that wizard from 1 step to 6.

### Step 1 — Project Identity → maps to the live `ProjectCreateInput`

| v2 spec field | Live field | Action |
|---|---|---|
| Project Name | `name` | exists |
| Fuel Type | `molecule` | exists — **reuse `molecule`**, label it "Fuel type" in the UI |
| Country | `country` | exists |
| City / Site Location | `location` | exists |
| Developer / Sponsor Org | `owner_company_name` | server-derived from the authenticated user's company — **do not collect**, display it |
| Short Description | — | net-new → store via `PATCH /projects/{id}/context` |
| Project Status (Draft/Active/On Hold/Archived) | — | net-new → see §5 |
| Technology Type | — | net-new → context (leave "TBD" as v2 had it) |

`molecule` accepts the v2 fuel list; keep the existing enum values as the wire format and
map display labels in the UI only.

### Step 2 — Project Scale → mostly live

| v2 spec field | Live field | Action |
|---|---|---|
| Estimated Total Capital Required | `capex_eur` | exists |
| Planned Production Capacity | `capacity_mtpd` | exists |
| Current Development Phase | `phase` (development / construction / commissioning / operating) | exists — **use these four values** |
| Currency, Capacity Unit, Target COD, Expected Project Life, Primary/Secondary Products | — | net-new → context |

Also already on the live wizard and worth keeping: `power_model`
(OFF_GRID_BTM / GRID_CONNECTED / HYBRID) and `financing_model`
(PROJECT_FINANCE / BALANCE_SHEET). These drive downstream finance behaviour — do not drop them.

### Step 3 — Commercial Context → one PATCH call

All Step-3 fields (target market, offtaker type, offtake status, revenue model, funding
status, funding secured, additional capital required, sponsor equity, debt requirement)
go to `PATCH /api/v1/projects/{id}/context` as a JSON payload. No new table needed.
Optional, as v2 specified.

### Step 4 — Initial Capital Readiness → **read, do not collect**

**This is the most important correction.** The v2 spec collects a manual Confidence score
and labels it a prototype mock. The platform already computes readiness:

- `GET /api/v1/pre-cod-metrics/{project_id}` → CEC (Capital Eligibility Coverage) and
  FRI (FID Readiness Index)
- `GET /api/v1/bankability/evaluate?project_id=…` → verification-weighted gate score and
  bankability state

**Display these as read-only.** A new project legitimately shows CEC 0% / FRI 0% /
SPECULATIVE — that is a *true* zero, not a mock, and it demonstrates the computation is
live. This honours Blueprint Law 7 ("Confidence is emergent, never manually assigned")
and removes a demo liability: no "Prototype initialization value" disclaimer in front of
an investor.

If a narrative stage label is wanted, derive it — never store it:

| Blueprint stage | Derived from live `BankabilityState` |
|---|---|
| Concept | SPECULATIVE |
| Early Development | TECHNICALLY_PLAUSIBLE |
| Development | COMMERCIALLY_PLAUSIBLE, BUILDABLE |
| Pre-Finance | STRUCTURALLY_BANKABLE |
| Finance Ready | CREDIT_APPROVED, FINANCEABLE |
| Investment Secured | OPERATIONAL, REFINANCING_ELIGIBLE |

Put this mapping in one front-end helper (`readinessStage.ts`) so it exists exactly once.

### Step 5 — Initial Capital Packages → `packagesAPI.create`

Same UX as v2 (create none / one / many / skip). Payload maps to the live contract:

| v2 field | Live field | Note |
|---|---|---|
| Package Name | `package_name` | min 3 chars |
| Purpose | `notes` + `package_type` | `package_type`: DEVEX, PRE_FEED, FEED, DIRECT_CAPEX, INDIRECT_CAPEX, OWNER_COST, CONTINGENCY, RESERVE, INSURANCE, LEGAL |
| Capital Amount | `cost_amount` | must be > 0 |
| Currency | `currency` | ISO 4217, default EUR |
| Planned Start/End | — | net-new → add to package or hold in Activities |
| Risks Addressed | `risk_removed[]` | **live enum** — TECHNICAL, PERMITTING, COST, SCHEDULE, REVENUE, CERTIFICATION, EXECUTION, SOVEREIGN, LEGAL, FINANCIAL, INSURABILITY, LOGISTICS |
| Expected Deliverables | → Deliverables (§9) | do not duplicate as free text |
| Expected Confidence Impact | — | **drop** — confidence is computed, not predicted by the author |
| — | `phase_required` | **required**: FEED / FID / CONSTRUCTION / COD |
| — | `discipline_owner` | **required**: actor ID |
| — | `estimate_class` | defaults CLASS_5 (AACE) |

### Step 6 — Review and Create

Unchanged from v2, except the review panel shows *computed* readiness (Step 4) rather
than an entered value. On success, navigate to the Capital Readiness Workspace.

---

## 2. Package Status — one lifecycle, not two

The v2 status list is a **different state machine** from the live one. Do not add a second.
The live machine is 12-state and forward-only, server-enforced via
`POST /packages/{id}/transition`.

| v2 status | Live `workflow_state` | Note |
|---|---|---|
| Proposed | `identified` | |
| Defined | `scoped` | |
| — | `costed` | cost estimate attached |
| Reviewed | `evidenced` | **requires ≥1 evidence document** — server enforces |
| — | `eligible` | funding pathway established |
| Approved | `approved` | |
| Funded | `committed` → `drawable` → `drawn` | live machine separates commitment from cash movement |
| Executing | `drawn` | |
| — | `verified` | use of funds evidenced |
| Closed | `closed` | |
| — | `propagated` | downstream effects applied |
| Archived | *(see §5 — archive flag, not a workflow state)* | |

**UI guidance:** display the live state label, and optionally group the 12 states into the
v2's coarser buckets for executive views. Transitions must go through the API so the
server can enforce preconditions (e.g. no `evidenced` without evidence) — a client-side
dropdown that writes state directly would defeat the guarantee that makes the data
bankable.

---

## 3. Activities — net-new (build as specified)

Each Activity belongs to exactly one Capital Package.

**Table `package_activities`** (note the name — avoids the `project_activity` collision):

```
activity_id       TEXT PRIMARY KEY
package_id        TEXT NOT NULL   -- FK → development_packages
activity_name     TEXT NOT NULL
description       TEXT
owner             TEXT
status            TEXT NOT NULL DEFAULT 'PLANNED'  -- PLANNED|IN_PROGRESS|COMPLETED|CANCELLED
planned_start     TEXT
planned_end       TEXT
actual_completion TEXT
notes             TEXT
created_by        TEXT NOT NULL
created_at        TEXT NOT NULL
updated_at        TEXT NOT NULL
```

Routes: `POST /api/v1/packages/{package_id}/activities`,
`GET /api/v1/packages/{package_id}/activities`,
`PATCH /api/v1/activities/{activity_id}`.

Follow house conventions: register the router in `main.py`, map the prefix to a business
domain in `app/core/domain_authorization.py` (**`projects`**), and use
`settings.SQLITE_DB_PATH` — never a module-owned path. CI guardrails enforce all three.

## 4. Deliverables — net-new (build as specified)

Each Deliverable belongs to exactly one Activity.

**Table `package_deliverables`**:

```
deliverable_id    TEXT PRIMARY KEY
activity_id       TEXT NOT NULL   -- FK → package_activities
deliverable_name  TEXT NOT NULL
description       TEXT
deliverable_type  TEXT
owner             TEXT
due_date          TEXT
status            TEXT NOT NULL DEFAULT 'EXPECTED'  -- EXPECTED|IN_PROGRESS|PRODUCED|SUBMITTED|ACCEPTED
evidence_ref      TEXT            -- SHA-256 hash once promoted to evidence (nullable)
notes             TEXT
created_by, created_at, updated_at
```

### "Create Evidence from Deliverable" — **enable it, don't stub it**

v2 marks this "Coming Soon." The endpoint already exists:
`POST /api/v1/packages/{package_id}/evidence` (multipart) — it stores the file, computes
its SHA-256, appends the hash to the package's `evidence_refs`, and logs the event.
`packagesAPI.uploadEvidence(packageId, file, title)` is already written.

Wiring it is roughly a day's work and converts the deliverable from a checkbox into the
first real link in the evidence chain: **Package → Activity → Deliverable → Evidence →
(risk reduction)**. Store the returned hash in `evidence_ref` and set status `SUBMITTED`.

This single change is what makes the prototype a slice of Capital Bridge Intelligence
rather than a CRUD demo. It is the highest-value item in this spec.

---

## 5. Project & Package status / archiving

v2's Draft/Active/On Hold/Archived is orthogonal to the workflow machine — keep it, but
as a **separate lifecycle field**, not mixed into `workflow_state`:

- Projects: add `lifecycle_status` (DRAFT|ACTIVE|ON_HOLD|ARCHIVED) to `projects`.
- Packages: add `archived_at` (nullable timestamp). Archived = non-null.

No hard deletes, per v2 — correct, and it matches platform doctrine. Archived items drop
out of default lists, remain behind an Archived filter, and retain all children.
(`DELETE /packages/{id}` exists; prefer archiving in the UI.)

## 6. Persistence — real API, no localStorage

Replace v2 §10 entirely.

- **Do not** use `localStorage` for Projects or Capital Packages. Both persist server-side
  today with versioning, content hashing, and an event log — properties a mock cannot
  provide and that the "all child objects remain connected to their correct parent"
  success criterion depends on.
- Activities and Deliverables persist through the new endpoints in §3–4.
- Portfolio → Project is `GET /projects/visible` (already ABAC-scoped per user).
- Acceptable transient client state: wizard step data before submit, and unsaved-form
  drafts. Nothing else.

**Auth note:** every route requires an authenticated identity (platform doctrine,
July 2026). The front-end must send the platform JWT; there is no anonymous fallback in
production. Front-end login wiring to `POST /api/v1/auth/login` is a live prerequisite —
if the current UI still relies on a demo user context, fix that first or the workspace
will 401.

## 7. Validation

Keep v2's rules and add the server's real constraints so client and server agree:

| Object | Required |
|---|---|
| Project | name, molecule (fuel), country, capacity, capex, power_model, financing_model, phase |
| Capital Package | package_name (≥3 chars), package_type, phase_required, discipline_owner, cost_amount (> 0) |
| Activity | activity_name |
| Deliverable | deliverable_name |

Surface server 4xx messages inline rather than replacing them with generic text — the API
returns specific reasons (e.g. an illegal state transition, or `evidenced` without evidence).

## 8. UX

v2 §12 is adopted unchanged — investor-grade, breadcrumbs, empty states, confirmation
before archiving, no generic-task-manager feel, and the fixed vocabulary (Project,
Capital Package, Capital Readiness, Financing Risk, Deliverable, Evidence).

Two additions:
- Show the package **event log** (`packagesAPI.events`) in the workspace. Provenance
  visible in the UI is a differentiator in investor demos.
- Label computed values as computed ("CEC 34% — computed from 12 evidenced packages"),
  never as scores someone typed.

## 9. Out of scope (revised)

Still out: Project Assessment engine, AI recommendations, Intelligence Center reasoning,
knowledge graph, external integrations.

**Moved into scope** (already built — no reason to defer):
- Reading computed Confidence/Readiness (§1 Step 4)
- Evidence upload from a Deliverable (§4)
- Server-side persistence and the package event log (§6)

Still deferred but now *reachable*: full Evidence Assessment, and the **Risk–Evidence
Pair** as a first-class object — the Blueprint's atomic unit, and the correct next
increment after this one.

## 10. Success criteria (v2's list, plus proof)

All ten v2 criteria stand. Add three that make the result demonstrable:

11. A created Project survives a **page reload and a different browser** (it is on the server).
12. A Package cannot be moved to `evidenced` **without evidence** — the server refuses, and the UI shows why.
13. A Deliverable can produce an Evidence record whose **SHA-256 hash appears in the package's `evidence_refs`** and in the event log.

Criterion 12 is the one to demo to an investor: it proves the platform enforces evidence
discipline rather than merely recording claims.
