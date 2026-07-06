# GEX — Open Sign-off Register (prepared 2026-07-02)

Every governed decision currently awaiting a human signature, across the whole
programme — with everything pre-staged so each is a minutes-long act, not a
project. **Nothing below is self-signed: the builder does not verify its own
run.**

---

## A. External Adjacency Corpus (#5)

### A1 — Dataset ruling  `[ ] SIGNED: ________  date: ______`
Recommendation on record: **IEA Hydrogen Production & Infrastructure Projects
Database** as v1 spine. Evidence: license verified **CC BY 4.0** (2026-07-02,
IEA data-product page) — commercial use permitted with attribution; annual
updates; covers H₂ + ammonia/methanol/synfuel derivatives.
Supplements (each needs its own terms check before use): ICAO SAF facilities
tracker, EU IPCEI/Innovation Fund award lists, US DOE announcements.

### A2 — Legal sign-off of the attribution line  `[ ] SIGNED: ________`
**Drafted attribution line (CC BY 4.0 requires credit + license link +
change indication):**

> *"Contains data from the IEA Hydrogen Production and Infrastructure Projects
> Database © IEA, licensed under CC BY 4.0
> (https://creativecommons.org/licenses/by/4.0/). GEX derives cohort
> statistics and adjacency benchmarks from this data; values labeled
> EXTERNAL_PRIOR are derived, not IEA-published figures."*

Legal to confirm: (a) this wording; (b) that serving *derived statistics* to
platform users is within CC BY 4.0 (it is, prima facie — attribution given);
(c) supplements' terms.

### A3 — First import + taxonomy census  `[ ] EXECUTED: ________`
Blocked on A1+A2 **and one user action I cannot perform: an IEA account login
to download the dataset file.** Then: `POST /api/v1/corpus/import` (license +
attribution required or 422) → review `/corpus/summary` unmapped labels →
sign each via `/corpus/taxonomy/sign` → re-import lifts quarantines.

### A4 — Refresh schedule  `[ ] RULED: ________`
Recommendation: annual, on each IEA release (the version diff auto-yields the
transitions dataset).

---

## B. Canonical Ledger / Migration (rc2)

### B1 — Final review of Migration Spec v0.3-rc2  `[ ] SIGNED: ________`
Direction approved 2026-07-02; the three insisted edits + five rulings are
incorporated; spec changes 3.1–3.6 are landed and guard-tested (60/60).
Awaiting the final read of rc2 as amended.

### B2 — Postgres DSN  `[ ] PROVIDED: ________`
A Postgres answers on :5432 but rejects the compose credentials. Set
`CANONICAL_DATABASE_URL=postgresql://…` and the identical code path leaves
`sqlite-dev` for the ruled substrate. (Credential, not code.)

### B3 — The 3 development_packages  `[ ] RULED: ________`
Re-enter against the canonical ledger (recommended — they are demo rows) vs
migrate via the spec machinery.

---

## C. Domain verifications (external parties, not Jim)

### C1 — Process functions → `ascertained=True`
e-methanol / e-SAF / bio-SAF HEFA trains, sizing coefficients, stoichiometry:
**Independent Engineer** signature required. Until then every TEA result says
`ascertained: false`.

### C2 — Emission-factor set → `EF_VERIFIED_BY`
ISO 14067 verifier (or licensed ecoinvent/GREET dataset) signs the EF library;
until then every LCA result says `ascertained: false`.

---

## D. Documents

### D1 — GREENEARTHX v4.3 tracked changes  `[ ] ACCEPTED: ________`
76 tracked insertions (author "Claude") in
`docs/word-docs/GREENEARTHX_v4.3-tracked.docx` — accept/reject in Word.

---

*Register maintained alongside the running log; each signature should be
recorded here with name + date. Prepared by Claude (builder) — deliberately
unsigned by the builder.*
