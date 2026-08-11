# Capital Project Details — Orchestration-Hardened Build Spec (v4)

**Supersedes:** `capital-project-details-v3-revised-spec.md`  
**Date:** 2026-08-10  
**Basis:** `Capital Project Details 3.docx`, `capital-project-details-v3-revised-spec.md`, and the 2026-08-10 `CLAUDE_HANDOFF.md` engineering state.

**Change in one line:** preserve v3's superior implementation discipline — live APIs, one canonical package workflow, computed readiness, server persistence, evidence hashing, event history, and backend authorization — while strengthening the domain model so GEX orchestrates **changing project facts, capital interventions, evidence consequences, and decision readiness over time**, rather than merely storing the latest form values.

---

## Status language used in this spec

- **LIVE** — verified as already implemented in the referenced v3 / engineering handoff.
- **NET-NEW** — required by this spec and not claimed to exist already.
- **DESIGN INVARIANT** — an architectural rule. Implementation may be incremental, but new work must not contradict it.
- **DEFERRED** — deliberately not part of this build.

---

# 0. GEX orchestration model — the non-negotiable layer

The application is not a task manager and not a collection of independent forms. The execution domain must preserve this causal chain:

```text
Vetted Organisation / Actor
        ↓
      Project
        ↓
Project Baselines / Assumptions over time
        ↓
   Capital Package
        ↓
      Activity
        ↓
    Deliverable
        ↓
      Evidence
        ↓
Risk / Gate consequence
        ↓
Computed Readiness / Financeability
        ↓
Capital or Project Decision
```

The current iteration does **not** need to make Risk–Evidence Pair, Gate Consequence, or Decision a new first-class object. It must, however, avoid data structures that make that future chain impossible.

### 0.1 Orchestration laws

1. **One canonical object per concept.** Do not create a second Project registry, second package workflow, browser-only package store, or parallel readiness score.
2. **One governed parent chain.** Project → Capital Package → Activity → Deliverable is server-enforced. A child created inside a parent workspace inherits that parent; the user does not re-select it.
3. **Parentage is not ordinary editable metadata.** Normal UI must not move a Package to another Project, an Activity to another Package, or a Deliverable to another Activity. Correction requires a governed action/event, not silent reassignment.
4. **Lifecycle, execution status, development phase, and readiness are different axes.** Never collapse them into one status field.
5. **Important project facts evolve.** CAPEX, capacity, COD and other material assumptions may change as engineering and commercial evidence improve. Preserve the revision trail; do not silently overwrite history.
6. **Unknown is a legitimate state.** Do not force a greenfield user to fabricate production volume, dates, prices, or other precision merely to pass a wizard.
7. **Readiness is emergent.** Confidence, Capital Readiness, CEC/FRI and Bankability outputs are computed/read-only. A user may state the intended risk outcome of a package; the user may not type the readiness improvement it supposedly creates.
8. **A Deliverable is not Evidence.** A produced report is a work product. Evidence is the governed artifact/fact created from it, with provenance and hash. Deliverable acceptance and evidence verification remain separate concepts.
9. **A Capital Package is an intervention, not a budget row.** It spends or commits capital to remove risk, create deliverables/evidence, satisfy a condition, or move the project toward a financeable state.
10. **No hard delete for governed project objects.** Archive or annul where appropriate; retain lineage.
11. **State-changing actions must be attributable.** Actor, time, object, previous state/value, new state/value, and reason/basis should be recoverable from the event/audit lineage for material changes.
12. **Authorization is product policy; RLS is defence in depth.** Project access, vetted status, organisation role and allowed action are decided in the GEX backend. Database RLS reinforces this; the frontend must not become the policy engine.

These laws are the main domain upgrade carried forward from the Word design while preserving the Markdown's stronger technical implementation.

---

# 1. What already exists — keep it, do not duplicate it

The following capabilities were verified in the v3 spec and remain authoritative unless the repository has changed since that inspection.

| Capability | Status | Existing path / rule |
|---|---|---|
| Project create + list | **LIVE** | `POST /api/v1/projects`, `GET /api/v1/projects/visible`; typed `projectsAPI`; UI at `/projects/new` |
| Project commercial context | **LIVE** | `PATCH /api/v1/projects/{id}/context` → `project_context` |
| Capital Packages | **LIVE** | `/api/v1/packages`; versioned/content-hashed server object |
| Package workflow | **LIVE** | 12-state, forward-only, server-enforced |
| Package evidence upload | **LIVE** | `POST /api/v1/packages/{id}/evidence`; multipart, SHA-256, event/evidence reference |
| Package event log | **LIVE** | `GET /api/v1/packages/{id}/events` |
| Typed package client | **LIVE** | `packagesAPI` create/update/transition/events/evidence methods |
| CEC / FRI | **LIVE** | `/api/v1/pre-cod-metrics` |
| Bankability evaluation | **LIVE** | `/api/v1/bankability` |
| Financier-facing package UI | **LIVE** | Finance package register/detail/builder |
| Package Activities | **NET-NEW** | Build as `package_activity`, not `project_activity` |
| Deliverables | **NET-NEW** | Build under Activities |
| Developer-facing Package Workspace | **NET-NEW** | New surface over the same canonical Package object |
| Material project baseline history | **NET-NEW** | Add minimal revision structure; do not replace canonical Project |

### 1.1 Engineering constraints updated to 2026-08-10

The v3 instruction to use `settings.SQLITE_DB_PATH` for new Activity/Deliverable persistence is now **superseded**.

The engineering handoff states that:

- PostgreSQL schema/data migration is complete, but runtime cutover is not complete.
- All eight backend switches, including `CAPITAL_DB_BACKEND`, are still on SQLite by design.
- `app/core/db_backend.py` is the backend-aware SQLite/PostgreSQL shim.
- RLS is proven but not yet the current runtime enforcement path because the application still connects using a bypassing role.
- Backend tenant context has been hardened to fail closed when no tenant is bound.

**Rule for this build:** new Capital Project Details persistence must use the existing backend-aware database architecture. Do not add new raw `sqlite3.connect` sites and do not create a new module-owned SQLite path.

Until the final PostgreSQL cutover is complete, any new persisted object required at runtime must have a deliberate compatibility path for the active SQLite store **and** the PostgreSQL target, with equivalent schema/constraint tests. Do not create another migration island.

### 1.2 Identity and authority boundary

The current account lifecycle is authoritative: registration alone does not make a user trusted. Activation follows GEX vetting, including telephone verification and signed usage agreement, after which normal authenticated/project-scoped access applies.

Therefore:

- `owner_company_name` / Developer-Sponsor identity is derived from governed identity and project relationships.
- Do **not** make organisation ownership an ordinary free-text field that a project user can rewrite.
- A future Sponsor transfer, if required, is a governed relationship change with audit history — not a Project Edit form field.
- All Project/Package/Activity/Deliverable/Evidence writes go through the GEX backend. Do not add direct frontend Supabase `.from()` persistence for this domain.

---

# 2. Project creation — extend the existing flow, but allow project truth to mature

**Do not build a new Project object.** Extend the existing `/projects/new` flow to six steps.

The main v4 change is that Project creation should distinguish **identity**, **declared assumptions**, **derived outputs**, and **known unknowns**.

## Step 1 — Project Identity

| UI field | Canonical / live mapping | Rule |
|---|---|---|
| Project Name | `name` | required |
| Fuel Type | `molecule` | existing wire field; UI label remains familiar |
| Country | `country` | required |
| Region / State / Province | context | optional |
| City / Site Location | `location` | optional |
| Developer / Sponsor Organisation | authenticated/project organisation | display, do not free-type as authority |
| Short Description | context | optional |
| Lifecycle Status | `lifecycle_status` | separate from phase/readiness; see §8 |
| Technology Type | context | optional; `TBD` is allowed |

**DESIGN INVARIANT:** Project identity can exist before a complete financing package, complete engineering basis, or complete production forecast exists.

## Step 2 — Project Scale and Baseline Assumptions

Keep the useful live fields:

- `capex_eur`
- `capacity_mtpd`
- `phase`
- `power_model` (`OFF_GRID_BTM | GRID_CONNECTED | HYBRID`)
- `financing_model` (`PROJECT_FINANCE | BALANCE_SHEET`)

But stop treating material values as timeless facts.

### 2.1 CAPEX — current value plus governed revisions

The Word design correctly recognises that initial capital required can be stated early but must be revisited as the project advances.

**v4 rule:** `capex_eur` may remain the current compatibility/snapshot field, but every material CAPEX revision must be recoverable as a dated baseline revision.

### 2.2 Production capacity — do not force false precision

The Word design correctly distinguishes a pure greenfield project from one already carrying an engineering/production basis.

**v4 rule:** a Project may be created when capacity is not yet known. Do not use `0`, an arbitrary placeholder, or a fabricated point estimate to satisfy validation.

If the current server contract requires `capacity_mtpd`, extend that contract rather than teaching the UI to lie. A Draft Project must be able to persist with capacity unknown.

### 2.3 Minimal Project Baseline Revision model — NET-NEW

Add a small, generic revision object for **material project assumptions only**. Do not turn every editable Project field into event sourcing.

Suggested table: `project_baseline_revisions`

```text
revision_id             TEXT PRIMARY KEY
project_id              TEXT NOT NULL
metric                   TEXT NOT NULL
                         -- TOTAL_CAPEX | DESIGN_CAPACITY | TARGET_COD | PROJECT_LIFE
value_numeric            NUMERIC NULL
value_text               TEXT NULL
lower_bound              NUMERIC NULL
upper_bound              NUMERIC NULL
unit                     TEXT NULL
currency                 TEXT NULL
basis                    TEXT NOT NULL
                         -- USER_DECLARED | DOCUMENT_DERIVED | ENGINE_OUTPUT
basis_note               TEXT NULL
evidence_ref             TEXT NULL
supersedes_revision_id   TEXT NULL
effective_at             TEXT NOT NULL
created_by               TEXT NOT NULL
created_at               TEXT NOT NULL
```

Rules:

- `project_id` is immutable.
- A revision does not delete the revision it supersedes.
- Point estimate, range, and unknown are all representable.
- Do **not** add a second home-grown "verification status" here. Evidence verification belongs to the evidence domain.
- The current Project snapshot may project the latest effective revision for compatibility/performance, but the revision history is the provenance record. During transition, any write that changes both the revision record and legacy snapshot field must be coordinated server-side as one logical operation; the browser must not dual-write them.
- After the first value, changing CAPEX/capacity/COD should ask for a short **basis/reason for change**.

This is intentionally narrow. It solves the Word document's strongest orchestration insight without attempting a full knowledge graph.

## Step 3 — Commercial Context

Continue to use `PATCH /api/v1/projects/{id}/context` for the current fields:

- target market
- intended offtaker type
- offtake status
- revenue model
- funding status
- funding secured
- additional capital required
- sponsor equity
- debt requirement

These remain optional during early creation.

**Orchestration rule:** material context changes must be visible in Project history/event lineage. The UI should not imply that the current value was always true.

Where a commercial item later becomes a governed contract, financing instrument, covenant, or evidence object, the specialised canonical object becomes authoritative; `project_context` remains summary/context, not a competing contract register.

## Step 4 — Initial Capital Readiness → read, do not collect

Preserve v3's superior rule.

Read:

- `GET /api/v1/pre-cod-metrics/{project_id}` → CEC / FRI
- `GET /api/v1/bankability/evaluate?project_id=…` → gate score / BankabilityState

Do not allow a user to enter Confidence or Capital Readiness.

If a narrative label is needed, derive it once from `BankabilityState`:

| Surface stage | Derived BankabilityState |
|---|---|
| Concept | `SPECULATIVE` |
| Early Development | `TECHNICALLY_PLAUSIBLE` |
| Development | `COMMERCIALLY_PLAUSIBLE`, `BUILDABLE` |
| Pre-Finance | `STRUCTURALLY_BANKABLE` |
| Finance Ready | `CREDIT_APPROVED`, `FINANCEABLE` |
| Investment Secured | `OPERATIONAL`, `REFINANCING_ELIGIBLE` |

Put this mapping in one helper such as `readinessStage.ts`.

**No false zero:** if the engine returns a valid calculated zero, show zero. If a calculation cannot be performed because prerequisite facts are absent, show **Insufficient data / N/A**, not a fabricated score.

## Step 5 — Initial Capital Packages

Preserve the Word design's excellent sequencing:

- Create Project with no packages.
- Create one or more initial packages.
- Skip and create packages later.
- Do not create detailed Activities or Evidence inside the Project wizard.

Map to the live Package contract:

| Surface field | Canonical/live field | v4 rule |
|---|---|---|
| Package Name | `package_name` | required |
| Purpose | `notes` + `package_type` | keep familiar wording at surface |
| Capital Amount | `cost_amount` | required by current package contract |
| Currency | `currency` | ISO 4217 |
| Planned Start / End | package dates or Activities | add once canonical location decided; do not duplicate |
| Risks Addressed | `risk_removed[]` | expresses intended risk outcome |
| Expected Deliverables | Deliverable objects | do not maintain a competing free-text deliverable list once objects exist |
| Expected Confidence Impact | **REMOVE** | user must not author a readiness gain |
| Phase Required | `phase_required` | existing canonical field |
| Discipline Owner | `discipline_owner` | existing canonical actor reference |
| Estimate Class | `estimate_class` | existing finance discipline |
| Target Gate / Condition | **NET-NEW optional link** | records intended consequence; does not itself satisfy the gate |

### Replace “Expected Confidence Impact” with two different concepts

1. **Intended outcome** — authored: risk to remove / gate or condition the Package intends to support.
2. **Observed readiness change** — derived retrospectively by the platform after evidence/state changes.

Do not merge them. Intent is a claim; the observed change is a computed result. **Do not attribute that change causally to one Package unless the engine explicitly supports causal attribution** — several project facts may have changed in the same period.

## Step 6 — Review and Create

Show five categories separately:

1. **Identity** — who/what the Project is.
2. **Declared baseline** — current CAPEX/capacity/COD assumptions and their basis.
3. **Known unknowns** — fields intentionally not yet known.
4. **Computed readiness** — read-only results.
5. **Initial interventions** — Capital Packages, if any.

Actions remain:

- Back
- Save as Draft
- Create Project

After creation, navigate to the Project's Capital Readiness Workspace.

---

# 3. Project editing — current snapshot plus history, not silent replacement

Add **Edit Project** near the Project title, but split editable content into two classes.

## 3.1 Ordinary context edits

Examples: description, region, technology label, commercial notes.

These can use normal form editing, subject to authorization and audit logging.

## 3.2 Material baseline revisions

Examples:

- total CAPEX
- design/production capacity
- target COD
- project life

Changing these values should create a new `project_baseline_revision` rather than destroy the prior basis.

UI pattern:

```text
Current CAPEX        EUR 520m
Basis                FEED estimate / document-derived
Effective            2026-08-10
Previous baseline    EUR 450m  → view history
Reason for change    [required when revising]
```

The Project page may show the latest value prominently, but a lender/investor/auditor must be able to answer: **what did we believe before, when did it change, and why?**

## 3.3 Never directly editable

- Derived Confidence
- CEC / FRI
- Derived Capital Readiness
- BankabilityState / gate outputs
- Project Assessment outputs
- Evidence hash / evidence verification result
- Governed organisation ownership via ordinary Project Edit

---

# 4. Keep all state dimensions separate

GEX currently has several legitimate state concepts. v4 makes the separation explicit.

| Dimension | Object | Nature | Examples |
|---|---|---|---|
| Lifecycle | Project | authored/governed | DRAFT, ACTIVE, ON_HOLD, ARCHIVED |
| Development phase | Project | project fact | development, construction, commissioning, operating |
| Readiness | Project | **derived** | SPECULATIVE → FINANCEABLE etc. |
| Workflow state | Capital Package | server state machine | identified → … → propagated |
| Archive state | Capital Package | administrative lifecycle | `archived_at` null/non-null |
| Execution status | Activity | operational | PLANNED, IN_PROGRESS, COMPLETED, CANCELLED |
| Work-product status | Deliverable | operational/governed | EXPECTED, IN_PROGRESS, PRODUCED, SUBMITTED, ACCEPTED |
| Evidence status | Evidence domain | governed fact/evidence lifecycle | use existing evidence vocabulary; do not duplicate here |

**DESIGN INVARIANT:** one dimension may influence another, but it may not masquerade as another.

Examples:

- Project `ACTIVE` does not mean Finance Ready.
- Package `drawn` does not mean its Deliverables are accepted.
- Deliverable `ACCEPTED` does not automatically mean its Evidence is verified.
- Archiving a Package does not rewind its historical workflow state.

---

# 5. Capital Package — treat it as the orchestration unit for capital-to-evidence

Keep the existing 12-state server workflow. Do not add the Word document's simpler package state machine as a second machine.

| Familiar surface grouping | Canonical `workflow_state` | Meaning |
|---|---|---|
| Proposed | `identified` | intervention recognised |
| Defined | `scoped` | scope established |
| Costed | `costed` | cost estimate attached |
| Reviewed / evidenced | `evidenced` | ≥1 evidence item; server precondition applies |
| Eligible | `eligible` | funding pathway established |
| Approved | `approved` | approved under canonical workflow |
| Funded | `committed` → `drawable` → `drawn` | commitment and cash movement remain distinct |
| Verified | `verified` | use/outcome evidence established |
| Closed | `closed` | package execution closed |
| Propagated | `propagated` | downstream effect applied |
| Archived | separate `archived_at` | not a workflow state |

### 5.1 Package causal contract

A Package should answer:

```text
Why are we spending/committing this capital?
    ↓
Which risk / condition is it intended to address?
    ↓
Which Activities will use the package?
    ↓
Which Deliverables must result?
    ↓
Which Evidence is produced/submitted?
    ↓
What did the platform actually observe in readiness/gate status afterwards?
```

This causal contract is more important than adding more package fields.

### 5.2 Parentage

- Package belongs to exactly one Project.
- When created inside a Project Workspace, `project_id` is server-derived from route/context.
- The UI must never offer “Move to Project” as an ordinary edit.
- Any administrative correction must preserve the old relationship in audit/event history.

---

# 6. Package Activities — NET-NEW, but project-scoped by construction

There is already a `routes_project_activity.py` concept meaning audit-feed event. Do not reuse that name.

Use **`package_activity`** in API/UI and **`package_activities`** for the table.

### 6.1 Important change from v3: include `project_id`

The August engineering handoff's RLS doctrine makes project scope security-significant. A new tenant-owned table without an honest project scope risks becoming admin-only or requiring awkward policy exceptions.

Therefore Activity carries both the immediate parent and the security anchor:

```text
activity_id        TEXT PRIMARY KEY
project_id         TEXT NOT NULL   -- server-derived from package; immutable
package_id         TEXT NOT NULL   -- FK → development_packages; immutable
activity_name      TEXT NOT NULL
description        TEXT
owner_actor_id     TEXT NULL       -- canonical actor/user reference where available
status             TEXT NOT NULL DEFAULT 'PLANNED'
                   -- PLANNED | IN_PROGRESS | COMPLETED | CANCELLED
planned_start      TEXT
planned_end        TEXT
actual_completion  TEXT
notes              TEXT
version            INTEGER NOT NULL DEFAULT 1
created_by         TEXT NOT NULL
created_at         TEXT NOT NULL
updated_at         TEXT NOT NULL
```

Rules:

- Client does not choose `project_id`; backend derives it from the Package.
- Backend rejects any `project_id/package_id` mismatch.
- `package_id` is not normally editable.
- Activity completion is not equivalent to risk removal or readiness improvement.
- If `owner_actor_id` cannot yet resolve to the platform actor model, keep it nullable rather than inventing authoritative free-text identity.

### 6.2 Routes

```text
POST  /api/v1/packages/{package_id}/activities
GET   /api/v1/packages/{package_id}/activities
PATCH /api/v1/activities/{activity_id}
```

Register the router in `main.py`, map it to the appropriate domain authorization, and persist through the backend-aware DB layer.

---

# 7. Deliverables — NET-NEW, and explicitly distinct from Evidence

Each Deliverable belongs to exactly one Activity and inherits Project + Package lineage.

Suggested structure:

```text
deliverable_id     TEXT PRIMARY KEY
project_id         TEXT NOT NULL   -- server-derived; immutable
package_id         TEXT NOT NULL   -- server-derived; immutable
activity_id        TEXT NOT NULL   -- FK → package_activities; immutable
deliverable_name   TEXT NOT NULL
description        TEXT
deliverable_type   TEXT
owner_actor_id     TEXT NULL
due_date           TEXT
status             TEXT NOT NULL DEFAULT 'EXPECTED'
                   -- EXPECTED | IN_PROGRESS | PRODUCED | SUBMITTED | ACCEPTED
notes              TEXT
version            INTEGER NOT NULL DEFAULT 1
created_by         TEXT NOT NULL
created_at         TEXT NOT NULL
updated_at         TEXT NOT NULL
```

Do **not** use a single `evidence_ref` column as the permanent relationship model. One Deliverable may produce multiple evidence items, and a later Risk–Evidence model may need to reuse an evidence item across more than one consequence.

### 7.1 Evidence linkage — minimal future-proof link

Add:

```text
deliverable_evidence_links
--------------------------
project_id          TEXT NOT NULL   -- server-derived security anchor; immutable
package_id          TEXT NOT NULL   -- server-derived lineage; immutable
deliverable_id      TEXT NOT NULL
evidence_ref        TEXT NOT NULL   -- SHA-256 / canonical evidence reference
relation_type       TEXT NOT NULL DEFAULT 'PRODUCED_FROM'
created_by          TEXT NOT NULL
created_at          TEXT NOT NULL
PRIMARY KEY (deliverable_id, evidence_ref)
```

This keeps evidence canonical while making provenance explicit.

### 7.2 “Create Evidence from Deliverable” — enable it

Preserve v3's superior decision to wire the real evidence path rather than leaving a disabled “Coming Soon” button.

Existing package evidence upload:

`POST /api/v1/packages/{package_id}/evidence`

Existing client:

`packagesAPI.uploadEvidence(packageId, file, title)`

### 7.3 Upgrade the orchestration boundary

Do **not** make the browser coordinate three independent writes:

1. upload package evidence,
2. create Deliverable→Evidence link,
3. change Deliverable status to `SUBMITTED`.

That creates a partial-state failure mode.

Prefer one **NET-NEW backend orchestration endpoint**, for example:

```text
POST /api/v1/deliverables/{deliverable_id}/evidence
```

Server responsibilities:

1. Resolve Deliverable → Activity → Package → Project.
2. Authorize against that Project.
3. Reuse the existing Package evidence upload/service logic.
4. Obtain/store the SHA-256 evidence reference.
5. Create `deliverable_evidence_links`.
6. Move Deliverable to `SUBMITTED` if appropriate.
7. Append the event/audit lineage.
8. Return the evidence/link/status result as one orchestration result.

The existing Package evidence endpoint remains canonical evidence machinery; the Deliverable endpoint is an orchestration wrapper, not a second evidence store.

### 7.4 Critical semantic separation

- `PRODUCED` = the work product exists.
- `SUBMITTED` = it has been promoted/submitted into governed evidence flow.
- `ACCEPTED` = the Deliverable has been accepted under its work-product process.
- Evidence verification/assessment remains in the evidence domain and may occur independently.

---

# 8. Project and Package lifecycle / archiving

## 8.1 Project lifecycle

Add/keep:

```text
DRAFT | ACTIVE | ON_HOLD | ARCHIVED
```

Actions:

- Activate Project
- Put On Hold
- Archive Project
- Restore Project

No hard delete in this domain UI.

Archived Projects:

- disappear from default active lists,
- remain available through Archived filter,
- retain Packages, Activities, Deliverables, Evidence links and history.

## 8.2 Package archive

Use `archived_at` as separate administrative lifecycle; do not add `ARCHIVED` to the 12-state workflow.

On archive/restore, record actor/time and preferably a reason.

---

# 9. Persistence, authorization and tenant isolation

This section replaces v3's remaining SQLite-specific implementation wording.

### 9.1 Server persistence only

Persist Projects, baseline revisions, Packages, Activities, Deliverables and Deliverable→Evidence links server-side.

Permitted browser-local state:

- unsaved wizard inputs,
- temporary form state,
- UI preferences.

Not permitted as canonical state:

- Project records,
- package workflow,
- Activities,
- Deliverables,
- evidence relationships,
- readiness results.

### 9.2 Backend-aware database access

Use the platform's backend-aware persistence path associated with the capital/projects domain. Do not introduce:

- module-owned database files,
- new raw `sqlite3.connect` call sites,
- direct frontend database writes,
- a second persistence abstraction for this feature.

During the current dual-store transition, schema/behaviour must remain compatible with both the active SQLite path and PostgreSQL target until the cutover is complete.

### 9.3 Project scope must be derivable on every governed child object

For new tables in this spec:

- `project_baseline_revisions.project_id`
- `package_activities.project_id`
- `package_deliverables.project_id`
- `deliverable_evidence_links.project_id` (server-derived; never client-selected)

The backend derives lineage; the user does not type it.

This supports project authorization now and honest RLS policy after runtime cutover.

### 9.4 Fail closed

No request may gain visibility merely because tenant/project context is absent. Do not use a platform-admin default as an implicit tenant context.

### 9.5 Event/audit lineage

Reuse the platform event/audit conventions rather than creating an unaudited local history.

At minimum, preserve attributable history for:

- Project lifecycle changes,
- material baseline revisions,
- Package workflow transitions,
- Package archive/restore,
- Activity status changes,
- Deliverable status changes,
- Deliverable→Evidence promotion/link creation.

Where existing platform code requires event append before projection write, preserve that convention.

---

# 10. Validation — validate truth, not form completion

The previous spec's validation was too close to “all important fields must have a value.” v4 distinguishes **object identity requirements** from **calculation prerequisites**.

| Object / action | Required |
|---|---|
| Create Draft Project | name, molecule/fuel, country; governed owner derived from identity |
| Add current CAPEX baseline | value or range, currency, basis |
| Add capacity baseline | value or range, unit, basis; **not required if genuinely unknown** |
| Invoke a calculation | whatever the target engine explicitly requires; otherwise return insufficient-data state |
| Capital Package | canonical server requirements: package name, type, phase required, discipline owner, positive cost amount, etc. |
| Activity | activity name + server-derived Package/Project lineage |
| Deliverable | deliverable name + server-derived Activity/Package/Project lineage |
| Promote Deliverable to Evidence | existing package evidence requirements + valid Deliverable lineage |

### 10.1 Never use placeholder values to satisfy a required numeric field

Prohibited examples:

- `capacity_mtpd = 0` when capacity is unknown,
- arbitrary CAPEX inserted only to unlock the next screen,
- fake COD date,
- manually typed readiness score.

If the current API prevents a truthful Draft, fix the API contract.

### 10.2 Surface server validation

Display specific 4xx reasons inline, including:

- illegal package transition,
- evidence prerequisite not met,
- cross-parent lineage mismatch,
- missing engine prerequisite,
- unauthorized project access.

Do not replace these with generic “Something went wrong.”

---

# 11. Developer-facing Capital Readiness Workspace

The new workspace is not a duplicate of the financier Package UI. It is a different view over the **same canonical objects**.

### 11.1 Project header

Show:

- Project identity
- lifecycle status
- development phase
- current baseline CAPEX/capacity/COD
- basis/source of each material baseline
- computed CEC / FRI / BankabilityState
- last meaningful baseline/readiness change

Actions:

- Edit Project
- View Baseline History
- Add Capital Package
- Archive / Hold according to permission

### 11.2 Package view

Each Package should show more than “status and amount.” Show the intervention logic:

```text
Package: FEED Close-Out
Capital: EUR 8.5m
Purpose: close design / cost / permitting gaps before FID
Targets: COST, TECHNICAL, PERMITTING
Workflow: evidenced
Activities: 7 / 9 complete
Deliverables: 5 produced, 4 submitted
Evidence: 8 linked
Readiness: current computed state shown separately
```

Do not invent a “+12 confidence points” claim.

### 11.3 Project history

Provide a compact chronological view of material changes:

- CAPEX baseline revised
- capacity basis revised
- Package moved from costed → evidenced
- evidence submitted from Deliverable
- readiness/gate result changed

This is where GEX begins to feel like structured orchestration rather than CRUD.

---

# 12. UX rules

Retain v3/v2 investor-grade requirements:

- clear page titles,
- breadcrumbs,
- Save / Cancel,
- success messages,
- unsaved-change warning,
- confirmation before archive,
- useful empty states,
- no generic task-management vocabulary.

Use the vocabulary:

- Project
- Project Baseline
- Capital Package
- Capital Readiness
- Financing Risk
- Activity
- Deliverable
- Evidence

### 12.1 Make epistemic state visible without becoming academic

Use simple surface language:

- **Current estimate**
- **Range**
- **Not yet known**
- **Basis: Sponsor estimate / FEED document / Engine output**
- **Computed**
- **Evidence submitted**

Do not expose internal evidence-state enums or technical audit terminology unless the user asks for detail.

### 12.2 Show consequence, not just completion

A task-manager UI celebrates “9/9 tasks complete.” GEX should answer the more important question:

**What changed because the work was completed and evidenced?**

Where available, surface:

- risk still open / risk addressed,
- gate still blocked / gate satisfied,
- current package state,
- computed readiness movement,
- remaining evidence gap.

Do not infer these consequences client-side; display server/engine outputs.

---

# 13. Scope for this iteration

## In scope

- Extend existing Project creation rather than duplicate it.
- Preserve real API/server persistence.
- Preserve canonical 12-state Package workflow.
- Preserve computed readiness and bankability outputs as read-only.
- Add minimal `project_baseline_revisions` for material changing assumptions.
- Allow truthful Draft Projects with unknown capacity rather than placeholder values.
- Build Package Activities.
- Build Deliverables.
- Include `project_id` lineage/security anchor on new governed child tables.
- Enable Deliverable → Evidence promotion using existing package evidence machinery.
- Prefer one backend orchestration endpoint for Deliverable evidence promotion.
- Add Deliverable→Evidence link table rather than one permanent scalar `evidence_ref`.
- Add developer-facing Package/Capital Readiness Workspace.
- Show package/project event history.
- Archive rather than hard-delete through the UI.

## Still deferred

- Full Evidence Assessment redesign.
- Risk–Evidence Pair as a first-class object.
- Full Project Assessment redesign.
- AI recommendations / Intelligence Center reasoning.
- Knowledge graph.
- External integrations not already present.
- New sponsor-transfer workflow.
- Full dependency graph between Capital Packages.
- A generic bitemporal truth engine for every Project field.

The point is to strengthen the domain spine now without turning this build into a platform rewrite.

---

# 14. API / schema worklist

## Reuse unchanged

- `POST /api/v1/projects`
- `GET /api/v1/projects/visible`
- `PATCH /api/v1/projects/{id}/context`
- `/api/v1/packages` canonical CRUD/transition routes
- `POST /api/v1/packages/{id}/evidence`
- `GET /api/v1/packages/{id}/events`
- `/api/v1/pre-cod-metrics`
- `/api/v1/bankability`

## Extend / add

### Project baseline revisions

```text
POST /api/v1/projects/{project_id}/baselines
GET  /api/v1/projects/{project_id}/baselines
```

Server derives actor/project authorization and preserves supersession history.

### Activities

```text
POST  /api/v1/packages/{package_id}/activities
GET   /api/v1/packages/{package_id}/activities
PATCH /api/v1/activities/{activity_id}
```

### Deliverables

```text
POST  /api/v1/activities/{activity_id}/deliverables
GET   /api/v1/activities/{activity_id}/deliverables
PATCH /api/v1/deliverables/{deliverable_id}
```

### Deliverable evidence orchestration

Preferred:

```text
POST /api/v1/deliverables/{deliverable_id}/evidence
```

This route reuses the existing Package evidence service and creates the Deliverable link/status/event as one orchestration operation.

### Project creation contract

Amend Draft creation so unknown capacity can remain null/absent rather than requiring a fake `capacity_mtpd`.

---

# 15. Tests and guardrails

Add tests that prove the orchestration model rather than only testing CRUD success.

1. A Draft Project can be created without fabricated capacity.
2. Updating CAPEX creates a new baseline revision and preserves the prior one.
3. A baseline revision cannot change `project_id`.
4. An Activity created under Package A inherits Package A's `project_id` server-side.
5. A client cannot smuggle an Activity into a different Project by sending a conflicting `project_id`.
6. A Deliverable inherits Project + Package from its Activity.
7. A Deliverable cannot be re-parented by ordinary PATCH.
8. A Package cannot move to `evidenced` without evidence — existing server rule remains green.
9. Deliverable evidence promotion produces a canonical SHA-256 evidence reference and a Deliverable link.
10. A failed evidence promotion cannot leave a successful Deliverable status with no link, or a link with no evidence object.
11. Deliverable `ACCEPTED` does not automatically mark Evidence verified.
12. No API permits a user to write CEC/FRI/Bankability/derived Confidence.
13. Package archive does not erase workflow/event history.
14. Project archive preserves all descendants.
15. New tables are project-scoped and tenant-isolation tests fail closed when tenant context is absent.
16. New DB access does not increase the raw SQLite connection guardrail count.
17. PostgreSQL schema/migrations and the current runtime store agree for new object structure until cutover.
18. Parent-chain/event tests use negative verification: deliberately try the forbidden cross-parent or direct-derived-value write and prove it fails.

---

# 16. Success criteria

A successful v4 build must demonstrate all of the following:

1. A user can create a Project using the existing canonical Project path.
2. The Project may be a truthful early greenfield record with unknown capacity rather than a fabricated number.
3. A Project survives reload and a different browser because canonical state is server-side.
4. Developer/Sponsor authority comes from governed identity/project relationships, not a free-text ownership field.
5. A material CAPEX/capacity/COD change preserves the prior baseline and its basis.
6. Computed readiness is visible and cannot be directly edited.
7. A Project can exist with zero Capital Packages and receive them later.
8. A Capital Package remains the canonical existing server object and uses the existing 12-state workflow.
9. A Package created inside a Project cannot accidentally attach to another Project.
10. Activities exist inside exactly one Package and carry server-derived Project scope.
11. Deliverables exist inside exactly one Activity and retain complete Project/Package lineage.
12. A Deliverable can be promoted to canonical Evidence using the existing SHA-256 evidence machinery.
13. The Deliverable→Evidence relationship is explicit and visible.
14. The Package cannot become `evidenced` without evidence.
15. Work completion, Deliverable acceptance, Evidence verification, Package workflow, and Project readiness remain separate states.
16. Archive operations preserve descendants and history.
17. Package and Project history show material state/value transitions with attribution.
18. The developer workspace reads as **capital-to-evidence orchestration**, not generic project management.
19. No new browser-local canonical store, direct Supabase persistence path, or second state machine has been introduced.
20. New persistence respects the current backend database transition and future project-scoped RLS model.

---

# 17. Recommended implementation sequence

This order keeps risk low and prevents UI work from defining the data model by accident.

### Slice A — orchestration invariants + contracts

- Relax Draft Project capacity requirement.
- Add `project_baseline_revisions` schema/API.
- Define immutable parentage and status-axis rules in types/tests.

### Slice B — Activities

- Add project-scoped `package_activities` to current runtime store and PostgreSQL migration path.
- Add backend routes/authorization.
- Add negative parent-scope tests.

### Slice C — Deliverables

- Add project/package/activity-scoped `package_deliverables`.
- Add routes and immutable lineage tests.

### Slice D — Evidence orchestration

- Add `deliverable_evidence_links`.
- Add Deliverable evidence orchestration endpoint that reuses existing package evidence machinery.
- Prove partial-state failure cannot produce an inconsistent visible result.

### Slice E — developer workspace

- Build Project header with current baseline + history.
- Build Package intervention view.
- Add Activities / Deliverables.
- Add evidence promotion.
- Show event/history chronology.

### Slice F — UX and investor demo proof

Demo this sequence:

```text
Early greenfield Project
→ capacity explicitly unknown
→ CAPEX baseline v1 entered
→ FEED Package created
→ Activity completed
→ Deliverable produced
→ Deliverable promoted to hashed Evidence
→ Package becomes eligible for evidenced transition
→ CAPEX baseline revised with prior value preserved
→ readiness/gate output shown as computed, not authored
```

That demonstration communicates the actual GEX proposition: **the platform preserves how project claims mature into governed evidence and how governed evidence changes capital readiness.**
