# Evidence-Ledger Census — Migration Decision 2 (executed 2026-07-02)

**Instrument:** the ruled Decision-2 query (and extensions) against the live
backend store `backend/gex_platform.db` (1.05 MB).
**Rule being satisfied:** *"the observed mapping is signed, not the theoretical
one."*

## Result — the observed population

| Table (Phase 1) | Rows |
|---|---|
| `evidence_ledger` | **0** |
| `model_base_case` | **0** |
| `pathway_claims` | **0** |

| Table (Phase 2 candidates) | Rows |
|---|---|
| `drawdown_schedules` / `_events` | 0 / 0 |
| `settlement_events`, `dfi_criteria`, `approval_requests`, `tokens` | 0 |
| `development_packages` / `_events` / `package_evidence` | **3 / 18 / 2** |
| `pre_cod_snapshots` | 2 |

Everything else with rows is auth/config (users, roles, login history,
entitlement audit, approval policies, fuel defaults).

Derived answers to the census questions:
- **category × entity_type mapping:** vacuous — no rows to map.
- **Quarantine candidates** (CONFIRMED/AUDITED without reviewer; verified
  claims without approver): **zero** — vacuously.
- **Hash-chain verification:** vacuously intact.
- Rows created during this programme's testing lived in per-test temp DBs;
  the live browser verification session performed reads only. The production
  ledger has never been written.

## Consequence — the migration calculus inverts

**There is no legacy truth to migrate in Phase 1.** The backfill machinery
(two-entry expansion, quarantine queue, hash bridge, projection equivalence)
has an empty domain. Running it would be ceremony.

**Recommendation: canonical-first cutover** (subject to sign-off):

1. Stand up the **canonical ledger on Postgres now** (Decision 4 already rules
   this), with `evidence_links` and the migration-map table created alongside —
   empty but governed.
2. **Point the write paths at the canonical ledger from day one**
   (`routes_tea` compute/LCA/approve emit `CanonicalLedgerEntry` +
   `evidence_links` directly, per the signed §4 taxonomy). The signed mapping
   becomes a **write-time contract**, not a translation run — legacy tables
   never accumulate content that would later need migrating.
3. Legacy tables become fold-backed read-only views **immediately** (nothing to
   reconcile, no dual-write period needed for Phase 1).
4. The migration spec (v0.3-rc2) remains in force as the governance instrument
   for: (a) the Phase-2 tables the moment any accumulates data — today that is
   only `development_packages` (3/18/2 rows: trivially migratable or
   re-enterable, owner's call); (b) **any other environment/instance whose
   census differs** — this census is per-environment evidence, valid for this
   database only, and must be re-run wherever a cutover is proposed.

## Sign-off — RULED (Jim, 2026-07-02) & EXECUTED

- [x] Census accepted as Decision-2 evidence **for this environment**.
- [x] **Canonical-first cutover approved and EXECUTED** (write-time contract):
  - `backend/app/core/canonical_ledger.py` — the persistent canonical store:
    `canonical_ledger_entries` + `evidence_links` (§6b) + `ledger_migration_map`
    (§6). All v0.3 write rules enforced at the store (`ToStateViolation`,
    `WriteAuthorityError`, kind-admission, append-only, supersedes-existence).
  - **Substrate rule enforced in code (Decision 4):** Postgres via
    `CANONICAL_DATABASE_URL`; unconfigured → `SubstrateError` (refuses to run);
    SQLite only under an explicit `GEX_CANONICAL_DEV=1` waiver, and then every
    read/write surface reports `substrate='sqlite-dev'` — a dev ledger cannot
    masquerade as canonical. *(A Postgres answers on :5432 but rejected the
    compose credentials — DSN needed from the owner to flip the substrate;
    the code path is identical.)*
  - `routes_tea` write paths emit canonical entries as system of record
    (compute → `projection_snapshot`; approvals → `approval_decision` by
    ROLE with the human user in the payload; LCA → two snapshots **+ a
    hash-pinned evidence_link** — one computation backing two claims, §6b live).
    Legacy tables are hereby re-classified: **read-models fed by the same code
    path, no longer competing truth.**
  - `GET /api/v1/tea/canonical/{project_id}` — the canonical read: fold +
    **live projection-equivalence check** (acceptance C/G as a running API).
  - **Verified end-to-end:** compute → IE approval → LCA → certifier approval
    (v0.3.1 authority fix in action) → fold: 5 entries → 3 claims
    (`verified`/`verified`/`submitted`, link-borne evidence on ghg_saving) →
    **projection_equivalence: EQUIVALENT**. Substrate guard, smuggling
    rejection, and write-authority rejection all verified at the store.
- [ ] **Deferred:** the 3 `development_packages` (+18 events, 2 evidence rows)
      — recommendation stands to re-enter against the canonical ledger when
      Phase-2 reaches packages (they are demo rows); the spec's machinery
      remains available if provenance of those rows matters.
