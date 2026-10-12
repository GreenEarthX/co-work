# Attack A — Advance a project despite missing land control or approvals

Run 30 Sep 2026 against the platform at head 059 with evidence rules 4.1.0. Source prompt:
*GEX Persona-Based Adversarial Testing Prompt Library*, §2 Producer, Attack A
(`Manus16_prompts/`). Harness: `docs/adversarial/harness/run_attack_a.py` (re-runnable).

## Verdict

**FAIL — Critical.** A producer can walk its own claims to VERIFIED. Nothing checks who
verifies, and the audit trail records whatever reviewer name the request supplies. In 22
unreviewed writes, with no document attached, the test project moved from Speculative to
**Technically plausible**, and GEX marked two capital decisions (Grants & TA, Seed / VC / Angel)
as eligible. Five more writes lifted the EPC ladder to **E4 (agreed form)** from an "engagement
letter". Every control the attack text asks for is present **except the one that matters**:
"require an accountable reviewer".

What held: maturity cannot be raised at verification; outsiders are refused; a producer cannot
write lender or buyer gates; the state is computed from evidence, never typed; and every change
is kept, append-only, with before and after values.

## How it was run (isolation)

- **Real code:** HTTP routing, the ABAC middleware (phase 2, rules R0/R1/R5), the evidence write
  validation, the evidence store and its append-only audit events. The state and ladders come
  from the **live gate engine** on :8001, a stateless computation.
- **Throwaway store:** a temporary SQLite file, with every `*_DB_BACKEND` switch pinned to sqlite
  (the `isolated_store` method). `DATABASE_URL` was pointed at an address that cannot connect,
  so no PostgreSQL write was possible. The dev database was checked before and after the run:
  0 TEST rows both times, 85 evidence rows both times.
- **Stubbed:** the project's owner profile and its context (grid-connected, project finance,
  FEED). The canonical `projects` table is PostgreSQL-only. Consequence: the EPC-card write in
  A5 returned 404 (`PROJECT_HAS_NO_OWNER`), a harness artifact.
- **Synthetic records only:** project `proj_TEST_attack_a`, owner "TEST Adversarial Dev", users
  `u_TEST_*`, every note labelled TEST/ADVERSARIAL.
- **Not covered:** the frontend was not driven. Code reading shows its Review and Verify buttons
  depend only on the item's status, not the user's role, and the "document attached" rule is
  enforced in the browser only (`StageGatesPage.tsx` around line 1487).

## The attack (the library's twelve fields)

| # | Field | Content |
|---|---|---|
| 1 | Attack objective | Present a project as further advanced than its evidence supports, as a developer under pressure before an investment committee |
| 2 | Preconditions | An authenticated producer executive of the owning company; a fresh project at Speculative |
| 3 | Synthetic inputs | 30 evidence writes (see steps); notes describing the true documents (land option, permit application, sponsor letter, EPC engagement letter) |
| 4 | Attempted manipulation | Declare an option as an executed lease and an application as a granted permit, then self-verify; self-verify every G0/G1 item; present an engagement letter as an agreed-form EPC; spoof the verifier's name |
| 5 | Expected control | Accept claims as claims; refuse self-verification; require a named, independent, accountable reviewer; distinguish application from approval; record the authenticated actor |
| 6 | Observed response | Claims accepted (correct), and **self-verification accepted** (wrong). The state advanced; eligibility was granted; the EPC reached E4; the audit trail named the spoofed certifier |
| 7 | Should the system | **Block** VERIFIED from the submitter or submitting company; **warn** on VERIFIED with no document |
| 8 | Evidence and audit requirements | Verifier identity from the token, not the request body; a document hash on every VERIFIED; ABAC decisions persisted |
| 9 | Consequence | A lender, grant body or investor reading the gate screen, the capital-eligibility panel or a banker snapshot sees an unsupported PASS and a false audit trail |
| 10 | Severity | **Critical** (library §19: the software can create an unsupported PASS affecting a material external commitment) |
| 11 | Remediation | Below |
| 12 | Regression tests | Below |

## Steps and observed results

| Step | Attempt | Expected control | Observed | Engine after | Result |
|---|---|---|---|---|---|
| A0 | Baseline, fresh TEST project | — | — | SPECULATIVE; O0, E0 | — |
| A1 | Submit a land **option** declared EXECUTED (lease) | Accept as a claim; not counted until verified | 200 accepted | SPECULATIVE | Pass |
| A2 | The same producer marks it **VERIFIED**, naming "Independent Certifier" as actor | Deny (separation of duties) | **200 accepted** | G0 item counted | **FAIL** |
| A2b | Verify a memo while raising its maturity INDICATIVE → EXECUTED | Deny | 422 `VERIFICATION_CANNOT_RAISE_MATURITY` | — | Pass |
| A3 | Self-verify every G0 and G1 item: 22 writes, no document | Deny each | **All 200** | **TECHNICALLY_PLAUSIBLE**; G0, G1 satisfied; **Grants & TA, Seed / VC / Angel eligible** | **FAIL** |
| A4 | Permit **application** and a **sponsor letter** recorded as granted permits (G9), self-verified | Tell application from approval; deny self-verification | **4 × 200** | Two G9 items counted | **FAIL** |
| A5 | EPC **engagement letter** recorded as agreed-form EPC, FEED, licence and security guarantees and damages schedule; self-verified | EPC must not reach E4 without independently verified documents | **5 × 200** | **E4 (agreed form)** — no contracting model needed | **FAIL** |
| A6a | A producer from an unrelated company writes this project's evidence | Deny (R1) | 403 | — | Pass |
| A6b | The producer writes a lender item (G10 conditions precedent) | Deny (R5) | 403 | — | Pass |
| A6c | The producer writes the buyer-side offtake item (G4) | Deny (R5) | 403 | — | Pass |
| A7 | Simulated: owner executive redeclares project finance → balance sheet | Allowed for the owner executive, audited | Not executed (PostgreSQL-only store); engine shows no change at this state | TECHNICALLY_PLAUSIBLE | Noted |
| A8 | Audit trail for the land item | Authenticated actor, before/after | Before/after kept, append-only; **actor = "TEST Independent Certifier (spoofed name)"**; `document_sha256` null | — | **FAIL** |

## Why it happens (code)

1. **VERIFY is never checked on this path.** `abac_middleware.py:113–121` maps POST to WRITE
   and switches to VERIFY only when the URL contains `/verify`. The evidence endpoint is
   `POST /api/v1/bankability/evidence`, with the status in the body. R5's rule "Only assigned
   certifiers can verify evidence" (`abac.py:518–525`) is therefore never reached.
2. **The handler tells reviewer from producer by the requested status, not by the caller.**
   `_validate_evidence_write` (`routes_bankability_proxy.py:54`) blocks raising maturity at
   review, but anyone allowed to write a gate may set VERIFIED.
3. **Gate owners verify their own gates.** R5 lets a producer write G0, G1, G3, G5, G9 and G11,
   an offtaker G4, and banks G4, G6, G7, G8 and G10 (`GATE_VISIBILITY`, `abac.py:237`). Each
   party can therefore verify the very evidence it is asserting.
4. **The audit actor is the request body.** `_upsert_evidence` records
   `actor = submitted_by or "system"` (`routes_bankability_proxy.py:307`); the token's user is
   not stored.
5. **Access decisions are not persisted.** `_log_access` is a placeholder
   (`abac_middleware.py:520`: "TODO: Write to ACCESS_LOG table").
6. **VERIFIED needs no document.** The server accepts it with no `document_sha256`; only the
   browser asks for a file.

Related, from the same review (screens, not API): the "Status & Blockers" page shows HamburgOne
as "Site Rights Secured — complete", "G0 complete" and rating **BB** while the engine shows 0 of
93 items verified. Its score simulator recommends "Advance to construction phase: +5 points"
(`BankabilityScorePage.tsx:288`), so the software itself proposes a status change as a way to
improve the rating. That is covered by the separate task "Make the gate screens tell one story".

## Remediation

1. **Separation of duties at the write path.** Classify a write by the requested status: a
   reviewer status (UNDER_REVIEW, VERIFIED, REJECTED, EXPIRED) is VERIFY. Then require:
   - the verifier is not the submitter, and not from the submitting company, unless a named
     reviewer role says otherwise;
   - the verifier holds a reviewer role for that gate. **Decided 2026-10-02:** certifier,
     independent engineer, lenders' adviser, insurer (table above).
2. **Audit the real actor.** Record the authenticated user id from the token on every evidence
   event. Keep `submitted_by` as display text only, or reject it when it differs from the token.
3. **VERIFIED requires a document** (hash on the server), and optionally a source type:
   authority, counterparty, sponsor, adviser. A sponsor letter can then never stand in for a
   permit.
4. **Persist ABAC decisions**, at least writes and denials, append-only.
5. **Screens:** no rating, completion claim or scoring lever that is not derived from the engine
   (already in the separate task).

## Regression tests to add with the fix

- `test_submitter_cannot_verify_own_evidence` — 403, not 200.
- `test_same_company_cannot_verify_its_own_claim`.
- `test_verification_requires_reviewer_role_for_the_gate`.
- `test_evidence_event_actor_is_the_authenticated_user` — a spoofed `submitted_by` is ignored or
  refused.
- `test_verified_requires_a_document_hash`.
- `test_verification_cannot_raise_maturity` — exists in spirit (A2b); keep it.
- Re-run this harness: A2–A5 must return 403 and the engine must stay at SPECULATIVE.

## Record (library §18)

| Field | Content |
|---|---|
| Test ID | ADV-PROD-A-2026-09-30 |
| Persona | Producer / project developer (owner executive) |
| Scenario | Pressure to show progress before an investment committee; land control and permits incomplete |
| Attack objective | Advance the project and obtain positive capital eligibility without completing mandatory gates |
| Synthetic records | `proj_TEST_attack_a`; `u_TEST_producer`, `u_TEST_outsider`; 30 evidence rows, 60 events (throwaway SQLite) |
| Materiality | Critical |
| Expected control | Block self-verification; require an accountable independent reviewer; record the true actor |
| Observed result | Self-verification allowed; state advanced to Technically plausible; two capital decisions eligible; EPC E4; spoofed audit actor |
| PASS integrity | **An unsupported PASS was possible** |
| Evidence trail | `docs/adversarial/results/2026-09-30_attack_A_results.json` (harness output; reproduced by a second run the same day); `evidence_events` rows with the spoofed actor and no document hash |
| Financial impact | Capital-eligibility signals (grants, seed and later gates) shown without evidence; lender-facing views inherit them |
| Regulatory impact | Permits recorded as granted from an application or a sponsor letter (G9) |
| Remediation | Separation of duties on verification; authenticated audit actor; document required; persisted access log |
| Regression test | As listed above, plus a re-run of this harness |
| Owner | To be named by JML |
| Due date | To be set by JML |

## Fix — 2026-10-01

**A2–A5 now return 403 and the engine stays at SPECULATIVE at every step.** Same harness,
unchanged: `results/2026-09-30_attack_A_results_after_fix.json` (the original run is kept).

| Step | Before | After |
|---|---|---|
| A1 claim submitted | 200 | 200 (a claim is still accepted as a claim) |
| A2 self-verify the land claim | 200 | **403** |
| A2b verify while raising maturity | 422 | 403 (R5 refuses before the maturity check; the 422 is tested with a legitimate reviewer) |
| A3 22 self-verifications | 22 × 200, Technically plausible, 2 capital decisions eligible | **22 × 403**, SPECULATIVE, nothing eligible |
| A4 permits self-verified | 4 × 200 | SUBMITTED 200, **VERIFIED 2 × 403** |
| A5 EPC self-verified | 5 × 200, **E4** | **5 × 403**, E0 (the terms card is still 404, the harness artifact above) |
| A8 audit actor | the spoofed certifier name | `u_TEST_producer`, the token's user |

| Defect | Fix | Code |
|---|---|---|
| 1. VERIFY never applied | A reviewer status (UNDER_REVIEW, VERIFIED, REJECTED, EXPIRED) on `POST /bankability/evidence` is a VERIFY, so R5 applies. A review that names no project is refused instead of skipping ABAC. | `abac_middleware._is_evidence_review`; `abac.verification_refusal` |
| 2. Self-verification | The reviewer must not be the submitter or from the submitter's company; nothing submitted, or a submitter naming no account, cannot be reviewed. The project owner's company never reviews its own project, whatever role its token carries (R5). | `routes_bankability_proxy._independence_refusal` |
| 3. Audit actor from the body | The token's user id is the actor of every evidence event, the submitter of a SUBMITTED and the verifier of a VERIFIED (`verified_by`, `verified_at` were never written before). The body's `submitted_by` is ignored, and logged when it names someone else. The document upload records the user id, not the e-mail. | `_upsert_evidence`, `upload_evidence_document` |
| 4. VERIFIED without a document | VERIFIED must name the sha256 of a document on file for that project and item. It is recorded on the event and as the item's `document_hash`. | `_document_on_file` |
| UI | Review, Verify and Reject appear only when the server says `can_review`, computed with the same two checks. Submitting uploads the file to the server first: it used to stay in the submitter's browser, where no reviewer could open it, and a `Document:` line in the notes counted as a document. The reviewer's own upload is gone; the review modal lists the documents on file. | `StageGatesPage.tsx`, `api.ts` |

**Who reviews which gate — owner decision, JML, 2026-10-02** (`abac.REVIEWER_GATES`): "each may
verify the relevant and linked gate: the certifier, the independent engineer, the lenders'
adviser, the insurer". Four roles, every one independent of GEX. Any listed role may verify any
item of the gate:

| Gate | May verify |
|---|---|
| G0 Site rights & social licence | Lenders' adviser · Independent engineer |
| G1 Power, utilities & technology | Independent engineer |
| G2 Certification pathway | Certifier |
| G3 Feedstock & logistics | Independent engineer |
| G4 Binding offtake | Lenders' adviser |
| G5 EPC risk priced | Independent engineer |
| G6 IE sign-off | Independent engineer |
| G7 Insurability | Insurer · Lenders' adviser |
| G8 Audit-grade model | Lenders' adviser |
| G9 Permits & appeal risk | Lenders' adviser |
| G10 Financial close | Lenders' adviser |
| G11 COD & stabilisation | Independent engineer · Certifier |

Never the submitter, the submitter's company or the project owner's company.
`INDEPENDENT_ENGINEER` and `LENDERS_ADVISER` are new actor types; `CERTIFIER` and `INSURER`
existed. Two consequences of the decision, both deliberate: G0, G1 and G3 need an appointed
independent engineer (G0 also takes a lenders' adviser), so a concept-stage project with
neither verifies nothing and stays at Speculative; and insurance **bound** at G10
(`insurance_certificates_delivered`) stays with the lenders' adviser, whose remit includes
insurance, because gate-level scope cannot give the insurer that one item without also giving
it the legal opinions and the security package. A per-item exception would be a separate
change. A reviewer is assigned the way a certifier always was: the role on the project, and
the project in `assigned_audits`. **Read access, decided the same day:** a reviewer may read
the gate screen (`GET /evaluate`) and the evidence and documents of its own gates, nothing
else. Other gates' items are withheld from its screen (R3; `_reviewer_only_scope`).

Measured 2026-09-30 on the live database: no account holds a reviewer role or an assigned
audit, so **nobody can verify anything until a reviewer is assigned.** That is the fail-closed
answer. Assigning one is a data operation, with no screen for it yet. On PostgreSQL the
reviewer's company also needs a `project_access` row, or RLS refuses its writes.

Tests: `backend/tests/test_evidence_review_separation.py`: the six listed above, plus the
decided table (4 roles × 12 gates), assignment, each role verifying its own gates, what a
reviewer may read, classification, owner independence, nothing submitted, legacy submitter,
missing project, rejection without a document, and `can_review` agreeing with the write.
Also `frontend/src/features/finance/__tests__/StageGatesReviewControls.test.tsx`. Each fix was
broken on purpose and the tests failed: 19 backend breaks and 6 UI breaks. The new write SQL
was also run on PostgreSQL itself, against TEMP copies of the tables.

**Not done here:**

- **ABAC decisions are still only logged** (Remediation 4). Persisting them needs an
  append-only table: a migration, RLS, and UPDATE/DELETE revoked from `gex_app`.
- **No source type on documents** (authority, counterparty, sponsor, adviser), so a sponsor
  letter can still be uploaded against a permit item. A reviewer now has to accept it.
- **The document upload skips ABAC.** Its body is multipart, so the middleware resolves no
  project and lets it through. On PostgreSQL, RLS still limits uploads to companies with
  access to the project, but gate ownership is not checked, and an upload resets the item to
  SUBMITTED with the uploader as its submitter. The download-by-hash route is likewise open
  to any signed-in user who has the hash.
