# R12 and D-H — proposals for decision (16 Nov 2026)

Status: **proposals, nothing built.** Each needs JML's answer row by row. Measured from the
development database and the code on 16 Nov 2026.

## R12 — who reads which project data

**Today.** `project_dataset` (21 kinds), `project_profile` (12 rows), `project_risk_flag` (15 rows)
and `tb_asset` (0 rows) are read by GEX and by **any company with access to the project**
(`app_company_can_see_capacity`, the generic "may see this project" helper). The one exception
is `demand_buyers` (113): GEX, the owner, and a mandated lender. Project access today means
one of: `OWNER` (8 rows), `MANDATED_LENDER` (2), `MANDATED_INSURER` (9), `STAKEHOLDER` (7:
offtakers, EPC contractors, others) and `REVIEWER` (appointed certifier or engineer; none live).

**The rule proposed.** Project access is not ownership (112). Commercial and financing data goes
to the owner and to the party mandated for it; descriptive data stays with everyone who may see
the project. A role is added to a kind only on JML's word, by naming its `access_role`, never by
falling back to "may see the project". Writes stay GEX-only (unchanged).

Contents below were read from each kind's payload keys, not from its name.

| Data | Holds | Owner | Lender | Insurer | Reviewer | Stakeholder |
|---|---|---|---|---|---|---|
| `deal_inputs` | DSCR P90, offtake binding %, EPC, insurance, grid status | ✔ | ✔ | — | — | **✖ (today ✔)** |
| `structuring_context` | DSCR P50/P90, LLCR, WACC, offtake coverage, gate scores | ✔ | ✔ | — | — | **✖ (today ✔)** |
| `bankers_snapshot` | financials, financing, offtake, kill switches, trust score | ✔ | ✔ | — | — | **✖ (today ✔)** |
| `capital_stack` | tranches, concessional, blended WACC | ✔ | ✔ | — | — | **✖ (today ✔)** |
| `term_sheet` | (no rows have keys yet) | ✔ | ✔ | — | — | **✖ (today ✔)** |
| `drawdown_layer`, `drawdown_milestones`, `drawdown_tranches`, `spend_wave` | financial close, drawdowns | ✔ | ✔ | — | — | **✖ (today ✔)** |
| `ic_pack_config`, `ic_pack_readiness` | investment-committee pack sections | ✔ | ✔ | — | — | **✖ (today ✔)** |
| `transfer_readiness` | DSCR post-transfer, consent matrix, warranty tail | ✔ | ✔ | — | — | **✖ (today ✔)** |
| `demand_buyers` | the project's buyer names | ✔ | ✔ | — | — | ✖ (since 113) |
| `offtake_quality` | offtake tests, red flags, remedies | ✔ | ✔ | — | — | **✖ (today ✔)** |
| `insurance_schedule` | lines, limits, premium, renewal, G7 evidence | ✔ | ✔ | ✔ | — | **✖ (today ✔)** |
| `cert_readiness`, `cert_45v` | temporal, geographic, additionality, LCA, verifier | ✔ | ✔ | — | ✔ | **✖ (today ✔)** |
| `plant_builder_preset` | equipment, labour, WACC, target price | ✔ | — | — | — | **✖ (today ✔)** |
| `task_router_inputs`, `adjacency_profile` | the owner's own work queue and ecosystem profile | ✔ | — | — | — | **✖ (today ✔)** |
| `project_timeline` | phases | ✔ | ✔ | ✔ | ✔ | ✔ (unchanged) |
| `project_profile` | descriptive fields of the project | ✔ | ✔ | ✔ | ✔ | ✔ (unchanged) |
| `project_risk_flag` | risk flags | ✔ | ✔ | ✔ | ✔ | **✖ (today ✔)** |
| `tb_asset` | (0 rows) | ✔ | ✔ | — | — | **✖ (today ✔)** |

**Questions for JML.** (1) Approve or change each row. (2) Should an offtaker that is a
STAKEHOLDER see `offtake_quality` for its own contract? Proposed no, until offtake data is per
buyer. (3) `project_risk_flag`: is a risk flag commercial (proposed) or descriptive?

**How it would be built.** One migration replacing the four read policies with a per-kind rule
(as 113 did), one SECURITY DEFINER helper per access role, and a policy test per kind in each
direction, negative-verified. Screens that a stakeholder opens today and would lose data on are
listed by the test run before the migration is applied.

## D-H — what a subscription unlocks

**Today.** No subscription concept exists (F28): `core/entitlements.py` covers finance review
only. Every vetted company can do everything its role allows.

**The rule proposed.** The server checks the plan alongside company, project and role, in one
table read by the routes and the screens (as `market_policy` is for roles). What is always free
must stay free so that the market can be seen and a counterparty can answer: a buyer is not
charged for answering a seller.

| Action | Proposed | Why |
|---|---|---|
| See Market Discovery (anonymous listings and RFQs) | **Free** | discovery is the reason to join |
| Answer an enquiry, share contact, decline | **Free** | the other side pays for asking; answering must not be blocked |
| Accept or decline a proposal made to you | **Free** | as above |
| Raise an RFQ | Subscription | creates demand others act on |
| List supply (wizard: capacity, token, listing) | Subscription | creates supply others act on |
| Send an enquiry | Subscription (or N free per month) | the first contact |
| Find supply / Compare against your RFQ | Subscription | the assessment is the product |
| Make a binding proposal | Subscription | |
| Trade confirmation, settlement, delivery | Covered by the trade fee, not the plan | billed per settled value (client billing) |
| Evidence pack export, registry export | Subscription | |

**Questions for JML.** (1) Which rows are paid. (2) Free quota for enquiries, if any. (3) One plan
or tiers. (4) What happens when a plan lapses mid-negotiation (proposed: open threads and
proposals continue; nothing new starts).

**How it would be built.** `plan_entitlement` (company, plan, valid_from, valid_until), the action
table beside `market_policy`, a refusal `PLAN_REQUIRED` naming the plan, `GET /market/policy`
returning what the plan allows so screens hide what would be refused, and a test per row.
