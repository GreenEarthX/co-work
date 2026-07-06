# CanonicalProjectLedger — Governed Migration Spec v0.3-rc2

**Status:** REVIEW EDITS APPLIED (Jim, 2026-07-02) — direction approved,
run NOT green-lit. The three insisted edits (§5.0 map-row wording, §5.4
`to_state` lockdown, §6b EvidenceLink DDL + §8 staging-ledger rollback) are
incorporated; five `[DECISION]` items are now RULED (§9). Final sign-off
pending review of rc2. Nothing here is self-executing.

## 1. Purpose & scope

Unify the platform's plural truth stores into one canonical, ledger-backed
project truth, per the review finding: *"a platform whose thesis is 'one truth'
runs on plural truths."*

**In scope (Phase 1):**
- `evidence_ledger` (backend SQLite, hash-chained rows)
- `model_base_case` (backend SQLite, cost-basis claims)
- `pathway_claims` (backend SQLite, GHG & pathway claims)

**Out of scope (Phase 2 candidates, listed in Annex B):** `drawdown_schedules`,
`settlement_events`, `dfi_criteria`, `development_packages`, approvals (WAE),
tokens/contracts. Same method applies; migrate after Phase 1 proves the harness.

**Non-goals:** no schema invention, no state re-interpretation, no data
"clean-up" during migration. Migration transports truth; it does not improve it.

## 2. Target model — one sentence

The target **is** the `efuel_truth_stack` specification (bumped v0.2 → v0.3):
`CanonicalLedgerEntry` (append-only, bitemporal, hash-anchored, kind-admitted,
write-authority-enforced) as the only store; **claims are projections**
(`fold_claims`), **nodes are rollups** (`rollup_nodes`), **evidence is a
relationship** (`EvidenceLink`), never rows that can drift from history.

Two structural principles (these are the whole design):

1. **Claims are not ledger contents.** `models.py`: *"Claim: Projection: the
   primary unit of truth, folded from the ledger."* Storing claim state as a
   column recreates the dual-truth disease inside the cure.
2. **Migrate history, not snapshots.** A legacy row with `state='verified'`
   becomes the *entries that produce* `verified` under `fold_claims` — never a
   copied state field. Acceptance is projection-equivalence (§7.C), not row copy.

## 3. Spec v0.3 — governed changes required before migration

| # | Change | Why |
|---|--------|-----|
| 3.1 | Add actor `migration_agent` to `actors` and to `WRITE_AUTHORITY` for every entry_type migrated | Every entry has `produced_by`; the ledger rejects unauthorized writers — including us |
| 3.2 | Formalise `BIOFUEL_NODES` (feedstock_sustainability, annex_ix, land_criteria, ghg_saving) from `spec.py` code-side into the JSON | Removes the code-side/spec split created 2026-07-01 |
| 3.3 | No new entry types | The existing 18 cover Phase 1 (verified in §5); resist vocabulary growth |
| 3.4 | Document AND constrain `payload.to_state` (see §5.4) | The migration relies on it (§5.2); unconstrained, it is a state-writing backdoor |
| 3.5 | Extend `_infer_target` to map `release_decision → SATISFIED` | Today `SATISFIED` is reachable only via `to_state` — which §5.4 forbids on non-decision entries; the projector must offer the legitimate path |
| 3.6 | Adopt the `evidence_links` relation (§6b) and teach `fold_claims` to consume it | Current fold attaches evidence only via `payload.claim_id` — one-entry-one-claim; a single certificate supporting N claims is inexpressible today |

`[DECISION]` 3.1 write-scope: `migration_agent` time-boxed (revoked after cutover)?

## 4. Content taxonomy (closes the review-round gaps)

All twelve proposed contents map onto existing vocabulary; **claims** and
**evidence artifacts** are corrected to projection/relationship; the missing
types are added to scope:

| Content | Entry type | Kind |
|---|---|---|
| measurements | `measurement` | fact |
| contracts | `contract` | fact |
| permits | `permit` | fact |
| certificates | `certificate` | fact |
| cost lines | `cost_invoice` | fact |
| cash movements | `cash_movement` | fact |
| **insurance docs** *(was missing)* | `insurance_doc` | fact |
| **offtake proofs** *(was missing — the credit anchor)* | `offtake_proof` | fact |
| approvals | `approval_decision` | decision |
| waivers | `waiver` | decision |
| **rejections / release decisions / drawstops / clawbacks** *(were missing — capital control)* | `rejection`, `release_decision`, `drawstop`, `clawback_notice` | decision |
| model outputs (TEA/LCA runs) | `projection_snapshot` | derived |
| reconciliation results | `reconciliation_result` | derived |
| **validation & audit results** *(were missing)* | `validation_result`, `audit_event` | derived |
| ~~claims~~ | **projection** via `fold_claims` — not stored | — |
| ~~evidence artifacts~~ | fact entry + `EvidenceLink` (hash-pinned relationship) | — |
| events (cost_overrun, delay, MAE, decert, breach, cure) | entries whose open/closed status is derivable; consumed by `evaluate_release_predicate` | per `EventType` |

## 5. Per-table mapping rules

### 5.0 Universal rules

- **Bitemporality:** `recorded_at` := legacy transaction time (`timestamp` /
  `created_at`). `valid_from` := legacy `valid_from` where present, else the
  transaction date **with `payload.valid_time_inferred = true`** — inferred
  valid-time must be visibly inferred, never silently asserted.
- **Ordering (load-bearing):** `fold_claims` orders by `(recorded_at, id)`.
  Where one legacy row expands to multiple entries sharing a timestamp, entry
  ids MUST be lexicographically ordered by intended sequence
  (`…-01`, `…-02`).
- **Hash bridge:** legacy hashes cannot be recomputed under the canonical
  scheme. Preserve them as testimony: `payload.legacy = {table, record_id,
  hash, prev_hash}`; the canonical `compute_entry_hash` is computed fresh.
  Both live in the migration map (§6).
- **Provenance:** every emitted entry carries `payload.legacy`. Map-row rule
  (audit-exact): every legacy row gets **at least one** migration-map record;
  a legacy row that emits N canonical entries gets **N** map records (same
  legacy ids, distinct `new_ledger_entry_id`); a quarantined legacy row gets
  **exactly one** map record with `new_ledger_entry_id = NULL` and a
  `quarantine_reason`.
- **Supersession:** the *superseding* claim's first entry carries
  `payload.supersedes_claim = <old_claim_id>` — the projector then derives
  `SUPERSEDED` + `superseded_by` on the old claim. Never write superseded state
  directly. Orphaned `superseded_by` references (target row missing) → quarantine.
- **No coercion:** any row failing kind-admission, write-authority,
  enum-membership, or referential checks → `migration_status = quarantined`,
  visible and unmigrated. Silence is the failure mode this spec exists to prevent.

### 5.1 `evidence_ledger` → fact entries

- One row → one **fact** entry; `claim_id` set where the row is referenced by a
  claim table (`run_evidence_id` / `evidence_id`), so `fold_claims` attaches the
  `EvidenceLink` and the fact advances the claim to `SUBMITTED`.
- **De-duplication rule:** rows that are *machine run records*
  (`submitted_by = 'tea_engine'`, entity_type `model_base_case`/`lca_run`) merge
  into the claim's single `projection_snapshot` (§5.2) — one event, one entry;
  both legacy ids preserved in `payload.legacy`.
- **category → entry_type map** (explicit; default = quarantine, not guess):

| legacy category + entity_type | entry_type |
|---|---|
| CERTIFICATION / * | `certificate` |
| COST / (invoice-like) | `cost_invoice` |
| COST / tea run record | merged into `projection_snapshot` (§5.2) |
| REVENUE / offtake-linked | `offtake_proof` |
| TECHNICAL / * | `measurement` |
| COUNTERPARTY / contract-like | `contract` |
| EXECUTION / permit-like | `permit` |
| `*_approval` entity types | `approval_decision` |
| anything else | **quarantine → human classification** |

`[DECISION]` confirm/extend this map against the real row population before run.

- Legacy `verification_state` (UNVERIFIED/SUBMITTED/CONFIRMED/AUDITED) maps to
  the claim layer, not the entry: CONFIRMED/AUDITED rows require a matching
  decision entry (from `reviewer_id`) — if none exists, **quarantine**
  (a "confirmed" row with no identifiable confirmer is exactly what must surface).
- The legacy per-project `prev_hash` chain must re-verify from
  `payload.legacy` fields after migration (§7.D).

### 5.2 `model_base_case` → entry sequences (the two-entry expansion)

Grounded in `projectors.py` semantics (verified 2026-07-02): derived-kind
entries do **not** advance state; `payload.to_state` and `approval_decision`
outcomes do; initial state is `ASSERTED`.

| Legacy state | Emitted entries (ordered) |
|---|---|
| `submitted` | **E1** `projection_snapshot` (derived; `produced_by=tea_engine`; payload: `claim_id`, `claim_type='model_base_case'`, `subject_node='financial_model'`, `value=cost_basis_hash`, capex/opex/lcop/nameplate, engine, `to_state='submitted'`, legacy) |
| `verified` | E1 as above **+ E2** `approval_decision` (decision; `produced_by = approved_by`; payload: `claim_id`, `outcome='approve'`, legacy `approval_decision_id`) → folds ASSERTED→…→VERIFIED |
| `rejected` | E1 + E2 with `outcome='reject'` |
| `superseded` | no state written; the successor row's E1 carries `supersedes_claim` |
| `superseded` with missing successor | quarantine |

- `reconciliation_group_id`, `valid_from`, `valid_to` carry over verbatim.
- `approved_by` empty on a `verified` row → **quarantine** (an unattributed
  verification is not migratable truth).

### 5.3 `pathway_claims` → entry sequences

Same expansion as §5.2 with: `claim_type`/`subject_node`/`value`/`unit`/
`value_type` from the row; `method` (annex_v/annex_vi/greet) preserved in
payload; E1's `produced_by = tea_engine` for GHG claims, else the recorded
producer; linked `evidence_id` handled per §5.1 de-duplication.

### 5.4 `payload.to_state` — bounded so it cannot smuggle terminal truth

Unconstrained, `to_state` recreates state-writing through the payload — the
exact disease this migration cures. The binding rule (enforced at append time
in v0.3, not merely documented):

- On **fact** and **derived** entries, `to_state` may express **non-terminal
  progression only** (`asserted`, `submitted`). Any terminal-valid value
  (`verified`, `satisfied`, `waived`) on a non-decision entry is **rejected at
  append** (and quarantined during migration).
- **Terminal-valid states require decision-kind entries from authorised
  actors**: `verified` via `approval_decision` (outcome approve), `waived` via
  `waiver`, `satisfied` via `release_decision` (per spec change 3.5;
  `to_state='satisfied'` is admissible **only on** a `release_decision` entry,
  where it is redundant-but-permitted).
- Consequently the §5.2 rule is absolute: a legacy `verified` row with empty
  `approved_by` can never be expressed as a compliant entry sequence — it
  quarantines. There is no payload route around a missing approver.

## 6. Migration provenance table (DDL)

```sql
CREATE TABLE ledger_migration_map (
    map_id               TEXT PRIMARY KEY,
    legacy_table         TEXT NOT NULL,
    legacy_record_id     TEXT NOT NULL,
    new_ledger_entry_id  TEXT,             -- NULL iff quarantined/failed
    migration_version    TEXT NOT NULL,    -- e.g. 'v0.3'
    migration_run_id     TEXT NOT NULL,    -- batch identity
    migration_timestamp  TEXT NOT NULL,
    migrated_by          TEXT NOT NULL,    -- actor (write authority applies)
    legacy_content_hash  TEXT NOT NULL,    -- as captured pre-migration
    new_content_hash     TEXT,             -- canonical compute_entry_hash
    migration_status     TEXT NOT NULL CHECK (migration_status IN
                         ('pending','migrated','quarantined','failed')),
    verification_status  TEXT NOT NULL DEFAULT 'pending' CHECK
                         (verification_status IN ('pending','passed','failed')),
    quarantine_reason    TEXT,
    UNIQUE (legacy_table, legacy_record_id, migration_version)  -- idempotency
);
```

Notes: one legacy row expanding to N entries → N map rows (same legacy ids,
distinct `new_ledger_entry_id`). `migrated ≠ verified`: §7 flips
`verification_status`, nothing else does.

## 6b. EvidenceLink relation (DDL) — evidence as an enforceable relationship

"Evidence is a relationship, not a type" must be a table, not a slogan. This
relation is **authoritative for the link** (which entry backs which claim, hash-
pinned at link time); it carries no state and can never contradict history —
the entry's content hash is frozen in `evidence_hash_at_link`, so tampering is
detectable by comparison. It also fixes a real gap (spec change 3.6): the
current fold expresses only one-entry-one-claim via `payload.claim_id`; this
relation expresses many-to-many (one IE certificate backing N claims).

```sql
CREATE TABLE evidence_links (
    link_id                TEXT PRIMARY KEY,
    claim_id               TEXT NOT NULL,
    ledger_entry_id        TEXT NOT NULL,
    link_type              TEXT NOT NULL,     -- supports | supersedes_basis | approval_basis
    linked_at              TEXT NOT NULL,
    linked_by              TEXT NOT NULL,     -- actor; write authority applies
    evidence_hash_at_link  TEXT NOT NULL,     -- entry content hash frozen at link time
    migration_run_id       TEXT,              -- NULL for organic (non-migrated) links
    UNIQUE (claim_id, ledger_entry_id, link_type)
);
```

Migration rule: every legacy `run_evidence_id` / `evidence_id` reference emits
one `evidence_links` row (`link_type='supports'`, `linked_by='migration_agent'`,
`migration_run_id` set); `fold_claims` (v0.3) merges these with
`payload.claim_id`-derived links, deduplicated by the UNIQUE key.

## 7. Acceptance tests (all must pass; no manual patching)

- **A — Count reconciliation.** Every legacy row has exactly one map row per
  emitted entry; `migrated + quarantined = total`; zero silent drops.
- **B — Hash bridge.** Per migrated row: stored `legacy_content_hash` matches
  recomputation from the frozen legacy snapshot; `new_content_hash` matches
  `compute_entry_hash` of the emitted entry.
- **C — Projection equivalence (the core test).** `fold_claims(migrated ledger)`
  reproduces, for every legacy claim: state, value, unit, valid_from/valid_to,
  supersession links, and evidence-link counts — equal to the legacy tables,
  row for row. A single mismatch fails the run.
- **D — Legacy-chain testimony.** The old per-project `prev_hash` chains
  re-verify end-to-end from `payload.legacy`.
- **E — Admission & authority.** Zero kind-admission or write-authority
  violations among migrated entries (violations exist only as quarantined rows).
- **F — Idempotency.** Immediate re-run of the same `migration_version`
  produces zero new entries and zero map changes.
- **G — Behavioral parity.** The certification-gate and release-gate endpoints
  return identical verdicts against legacy-read vs ledger-read for every
  project, before cutover.

## 8. Rollout & rollback (staging-ledger model — append-only is never violated)

Migration entries are born in a **staging ledger**, physically separate from
the canonical ledger. Only accepted batches are **promoted**; the canonical
ledger never contains an entry that can later be deleted.

1. **Provision the canonical + staging ledgers on Postgres** (Decision 4 —
   the canonical ledger is never built on SQLite).
2. **Freeze + snapshot** legacy SQLite tables (the hash-bridge baseline).
3. **Dual-write** new business events to legacy AND the canonical ledger
   — begins only after spec v0.3 sign-off.
4. **Backfill** legacy history into the **staging ledger** via
   `migration_agent`; quarantine queue reviewed by humans.
5. **Acceptance** (tests A–G, §7) runs against staging.
6. **Promotion**: accepted batches move staging → canonical, by
   `migration_run_id`, atomically per batch.
7. **Shadow-read**: gates/NBA/UI read canonical, compare to legacy (test G),
   serve legacy. Exit by criteria, not time (Decision 3).
8. **Cutover**: reads switch; legacy tables become **read-only views
   reconstructed from `fold_claims`**.
9. **Rollback semantics**: before promotion — drop staging entries by
   `migration_run_id` (staging is scaffolding, not truth). After promotion —
   **compensating entries only, never deletion**. Legacy untouched throughout.
10. Post-cutover: revoke `migration_agent` write authority (Decision 1).

## 9. Decisions — RULED (Jim, 2026-07-02)

1. **`migration_agent` — approved, tightly scoped.** Time-boxed,
   migration-version-scoped, phase-scoped; revoked immediately after cutover.
   No general application permissions, no UI persona, no normal login, no
   ability to write post-cutover business events.
2. **category→entry_type map — approved only after a real data census.**
   Before any run:
   `SELECT category, entity_type, COUNT(*) FROM evidence_ledger GROUP BY category, entity_type;`
   The **observed** mapping is signed, not the theoretical one in §5.1.
3. **Shadow-read exits by criteria, not time.** Minimum 7 calendar days AND
   100% pass on acceptance tests A–G AND zero unexplained behavioral-parity
   mismatches AND every quarantined row classified as *accepted quarantine*
   (never ignored failure) AND certification-gate + release-gate parity across
   every project and persona.
4. **Postgres — same programme, not the same cutover step.** The canonical
   ledger is **built on Postgres from step 1**; legacy SQLite stays frozen as
   source; dual-write bridges the phases (§8 sequence). The canonical ledger is
   never built on SQLite only to be migrated again. (Motivation on record: the
   async cross-thread SQLite bug found in live verification, 2026-07-02.)
5. **Phase-2 order — by capital-release importance:** ① `drawdown_schedules`
   + drawdown events (→ `release_decision`/`drawstop`), ② `dfi_criteria`,
   ③ WAE approvals store, ④ `settlement_events`, ⑤ `development_packages`,
   ⑥ tokens/contracts, ⑦ GreenMesh registry. Rationale: closest first to
   "can cash move today?"

**Spec changes 3.1–3.6: LANDED (2026-07-02).** `efuel_truth_stack_v0_3.json`
is live (spec.py default path); `migration_agent` admitted to all 8 gated
entry types; biofuel nodes in the JSON; `ToStateViolation` enforced at
`ledger.append`; `_infer_target` maps `release_decision → SATISFIED`;
`fold_claims(evidence_links=…)` merges hash-verified many-to-many links
(tamper ⇒ `ProjectionError`); `EvidenceLink.link_type` added. **17 new guard
tests; full suite 53/53.** Landing exposed and fixed a second latent flaw: the
reference fixtures themselves smuggled `to_state='verified'` on fact rows —
now modelled as fact + explicit `approval_decision`; and later evidence on a
verified claim (validity-narrowing corrections) crashed the fold — resolved by
the **inferred fact-floor rule** (a fact without explicit `to_state` infers
SUBMITTED as a floor, never a demotion; explicit `to_state` stays strict),
documented in the JSON and guard-tested.

**Remaining before implementation green-light:** final review of this rc2 +
the landed v0.3 changes; the evidence_ledger census (Decision 2).

## Annex A — Why not "just add a claims table with better constraints"

Because state stored beside history can contradict it, and nothing forces the
contradiction to surface. State derived from history cannot. The projector
already raises `ProjectionError` on illegal sequences — the migration inherits
a verifier for free, but only if state is never written down.

## Annex B — Phase-2 candidates (same method)

`drawdown_schedules` (+ its event table → `release_decision`/`drawstop`),
WAE approvals store, `settlement_events`, `dfi_criteria` status changes,
`development_packages` workflow states, GreenMesh registry rows.
