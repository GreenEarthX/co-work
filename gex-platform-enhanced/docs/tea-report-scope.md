# Techno-Economic Assessment (TEA) report — scope

**Date:** 2026-09-18 · **Status:** proposed, nothing built · **Measured against the tree on 2026-09-18.**

**One line:** the computation exists and is approved through a claim machine; what is
missing is a read model, a screen, and a document — in that order.

**Two decisions taken 2026-09-18, and they narrow this document:**

- **Internal view for now.** Nothing leaves the building, so increment 3b (a stored,
  hash-stamped artefact) is **out of scope** until that changes, and with it the dependency
  on the document-storage gaps in CLAUDE_HANDOFF §8.14.
- **The name stays TEA.** "EAT" is not adopted; the service already calls itself
  Techno-Economic Assessment, and a second name for one thing is what §8.13 is about.
  This file was renamed from `eat-report-scope.md` for the same reason.

---

## 1. What exists today (measured, not remembered)

| Piece | Where | State |
|---|---|---|
| TEA compute: CAPEX, OPEX, **LCOP**, plant summary | `tea_engine` :8002, `POST /compute` | Real, wraps OpenPyTEA 2.1.0 |
| Sensitivity (**tornado**) | `POST /sensitivity` → `base_lcop` + `tornado[]` | Real |
| LCA: `g_co2e_per_mj`, `ghg_saving`, allocation | `POST /lca/compute` | Real |
| Regulatory regime fork (cert gate · GHG method · subsidy) | `tea_engine/regimes.py` | Real, five pathway classes |
| Evidence → claim → approval | `backend/.../routes_tea.py`: `/compute/{project_id}`, `/base-case/{project_id}`, `/base-case/{claim_id}/approve` | Real; `model_base_case` with a state machine |
| Deterministic run fingerprint | `TEAResult.cost_basis_hash` | Real — the report's citation key |
| Client-side PDF precedent | `PlantExportDialog.tsx` (jsPDF) | Real, but exports the **plant canvas**, not economics |

**What is missing, and it is the last mile:**

- **No economics read model.** The permission strings `economics.snapshot.*`,
  `economics.cost_stack.*`, `economics.benchmark.*`, `economics.lca.*` are registered in
  the permission engine and in the ABAC route map, and **no route implements them**.
- **No screen.** The only frontend consumer of :8002 is `CertReadiness.tsx`, and it calls
  the certification gate, not the cost model. CAPEX, OPEX and LCOP appear nowhere in the UI.
- **No report.** `GET /reports/banker/{project_id}` returns hard-coded strings and a fixed
  `generated_at`. `GET /ic-pack/{id}/export/pdf` always raises 409 behind a
  `# Demo: pretend state is COMPUTED` comment. No server-side PDF library is installed.

---

## 2. Rules the build must not break

1. **The report reads an approved claim; it never recomputes.** A document whose numbers
   are produced at render time cannot be the numbers that passed approval. Source of truth:
   the live `model_base_case` for the project, plus the LCA and sensitivity runs it cites.
2. **A provisional run is never silently substituted.** `TEAResult.model_claim_state` is
   `"submitted"` by construction. If no approved base case exists, the API says so (409)
   and the screen says so; it does not fall back to the latest run.
3. **`ascertained=False` appears on the face of the document.** Inputs are public-reference
   first-pass values, not verifier-signed (CLAUDE_HANDOFF §5). A client-facing report that
   omits this misrepresents the platform's own position.
4. **The GREET path is a GREET-*consistent approximation*.** It may not be labelled a GREET
   result anywhere in the output.
5. **Every figure carries its fingerprint:** `cost_basis_hash`, `claim_id`, the approval
   decision and its approver, and the regime (`pathway_class`) the numbers were computed
   under. Two reports with the same hash must be the same numbers.
6. **Tenant scoping is not optional.** The economics of a project are commercially
   sensitive; the route sits behind ABAC like any project-scoped read.
7. **Nothing here feeds a gate.** The report is an output of the evidence plane, not an
   input to it.

---

## 3. Increment 1 — the economics read model (the only thing that unblocks the rest)

**`GET /api/v1/economics/snapshot/{project_id}`** — one approved economic picture.

| Field | Source |
|---|---|
| `claim_id`, `claim_state`, `approved_by`, `approved_at` | `model_base_case` |
| `cost_basis_hash`, `engine` | the run that became the claim |
| `capex`, `opex_per_year`, `lcop`, `unit` | `PlantSummaryExtract` on the claim |
| `cost_stack[]` (equipment/category → cost) | process-function meta of the run |
| `regime` (`pathway_class`, cert gate, GHG method, subsidy) | `tea_engine/regimes.py` fork recorded on the run |
| `lca` (`g_co2e_per_mj`, `ghg_saving`, allocation basis, method) | the LCA claim for the same pathway |
| `sensitivity.tornado[]` | the sensitivity run citing the same `cost_basis_hash` |
| `ascertained` (false), `provenance[]` | emission-factor and price provenance already on the run |

- **409** when a live base case exists but is not approved, naming the state.
- **404** when there is none. Never a partial object with nulls standing in for approval.
- Register the prefix in `domain_authorization.DOMAIN_PREFIXES` or
  `test_every_api_route_maps_to_a_domain` fails — the known trap for any new route.

**Tests:** approved claim renders; unapproved returns 409 with the state; missing returns
404; the hash on the response equals the hash on the claim; a tenant that does not own the
project gets nothing. Negative-verify each by breaking it.

**Effort:** small — days, not weeks. No new dependency.

---

## 4. Increment 2 — the screen

An economics view under the existing `economics.snapshot.economics_dashboard.view`
permission: headline LCOP with its unit and basis, CAPEX/OPEX, the cost stack, the tornado,
the LCA figures with method and allocation, the regime, and a standing
**"Provisional — not verifier-signed (`ascertained=false`)"** banner.

The claim state is displayed, not implied: *Approved by X on DATE* or *Awaiting IE/CFO
approval — figures not shown*.

**Effort:** small-to-medium, and it is where the value appears first: today these numbers
exist and nobody can see them.

---

## 5. Increment 3 — the document (deferred by the internal-view decision)

Only after 1 and 2, and only 3a while the audience is internal. A screen that prints
cleanly is enough for an internal reader; 3b exists here so the cost of changing the
decision is visible, not because it is planned.

| | 3a — print view (recommended first) | 3b — server-side artefact |
|---|---|---|
| How | Print-CSS page; the browser makes the PDF. jsPDF precedent exists | New dependency (WeasyPrint or ReportLab, both free) |
| Fingerprint | Renders `cost_basis_hash` and `claim_id` as text | Can hash the produced file and store it |
| Becomes evidence? | No | Yes — and then §8.14 applies: there is **no download route** for stored documents, and the document directory is not mounted in `docker-compose.yml` |
| Effort | Small | Medium, plus deployment work |

**Recommendation:** ship 3a. Move to 3b only when someone must be able to prove *which*
document was handed to a lender — at which point the storage gaps in §8.14 must be fixed
first, or the artefact will be unreadable through the API and lost on container replacement.

---

## 6. Out of scope

- Recomputing or curve-fitting anything at report time.
- Benchmarking against other projects (`economics.benchmark.*`) — a separate question about
  whose data may be compared with whose.
- Flipping `ascertained` to true. That needs a named ISO 14067 verifier, not code.
- Any path from the report back into a gate.

---

## 7. Decisions

1. ~~**Audience.**~~ **Decided 2026-09-18: internal view for now.** Increment 3b is out of
   scope. Revisit only when a document must leave the building, and expect the §8.14
   storage work to come with it.
2. ~~**Name.**~~ **Decided 2026-09-18: TEA stays.** "EAT" is not used anywhere in code,
   routes, permissions or documents.
3. **Open — which fields are client-confidential** if a project is ever published to the
   ecosystem map. Cost stack and LCOP are commercially sensitive and must not follow a
   project to a public surface. Not blocking increment 1, because the endpoint is
   project-scoped and behind ABAC; blocking any later reuse of it on the map.
4. **Open — who approves the base case in practice.** The report's authority *is* that
   approval. The platform models IE/CFO; the staffing question is the one D13 answered for
   the analyst review queue, and it deserves the same answer.
