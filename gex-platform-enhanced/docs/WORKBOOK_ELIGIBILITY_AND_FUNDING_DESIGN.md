# Contract eligibility and funding need: design for review (19 Nov 2026)

For JML, before workbook steps 3 (capital stack as its own record) and 4 (offtake contract
status). Nothing below is built. Decisions needed are marked **D**.

## 1. Contract eligibility: four separate facts, not one "signed" status

"Signed" collapses facts that move independently. A record should hold each fact on its own,
with its own evidence, and the gate engine should read the combination it needs.

| Fact | Values | Evidence that sets it | Who may set it |
|---|---|---|---|
| **Instrument** | LOI / MoU, heads of terms, term sheet, commitment letter, definitive agreement (SPA, offtake agreement, facility agreement) | the document on file (sha256) | the producer declares; a reviewer confirms |
| **Binding** | non-binding, binding in part (exclusivity, confidentiality), binding | the document's own clause | as above |
| **Execution** | unsigned, executed by one party, executed by all parties (date, signatories) | the executed document on file | producer declares; **D1**: confirmed by whom |
| **Conditions** | none, open (list, longstop date), satisfied, waived (by whom) | CP satisfaction notices / waiver letters | producer declares; reviewer confirms |
| **Standing** | in force, suspended, disputed, terminated, novated | event (the existing adverse facts and novations) | as today |

Counterparty **confirmation** (what exists today) stays its own fact: the counterparty agrees the
record states the terms correctly. It does not make the contract executed or binding.

**What counts for a gate** (proposal; the rules engine stays the authority):

- Offtake towards G4: binding definitive agreement, executed by all parties, conditions satisfied or
  open within the longstop, standing in force, counterparty confirmed. Anything less is shown with its
  ladder position and counts for nothing.
- Funding: **committed** = executed facility agreement, or a credit-approved commitment letter (**D2**:
  is a commitment letter enough before financial close?). A term sheet, mandate or indicative offer is
  **pipeline**, never committed. Lender confirmation of terms does not make funding committed.

**Prospective buyers.** A buyer row may be a PROSPECT: a declared name, no GEX company, no
confirmation possible, never counted by the engine, allowed in a draft frame next to real buyers.
It becomes a buyer when GEX staff grant its company project access; the row keeps its stable id.

**Stable ids.** Each buyer row and each capital source keeps a GEX id across re-imports (as the
financing case and capital sources do since step 2). Never matched by name.

**D1.** Who confirms execution: the counterparty (each confirms its own executed copy), the lenders'
adviser (G4 is theirs in `REVIEWER_GATES`), or both?
**D2.** Does a credit-approved commitment letter count as committed funding before financial close?

## 2. Total project cost versus remaining funding need

Today the preview compares the capital stack with the TEA's fixed capital only. That is one use
among several. Proposal: a **sources and uses** view, each line from exactly one record.

**Uses (total project cost)**

| Use | From | Boundary rule |
|---|---|---|
| Development expenditure | pre-FID (DEVEX) packages: spent, committed, forecast to FID | counted once; not in fixed capital |
| Construction | the reviewed TEA's fixed capital (ISBL, OSBL, D&E, contingency) | contingency once, inside fixed capital |
| Owner's costs | stated, if not already in fixed capital | the workbook says which (no double count) |
| Financing costs | interest during construction, fees, hedging | **D3**: computed by the PF engine, or stated |
| Reserves funded at close | DSRA, maintenance reserve | from the financing case |
| Initial working capital | stated; the TEA's own working capital is listed beside it and not added twice | **D4** |

A line not stated is shown as **unknown**, and the total is then a floor, said as such.

**Sources, by standing:** funded to date (cash in: equity paid, grants received) · committed (per §1) ·
pipeline (applied, mandate, term sheet, indicative).

**Three figures, never one:**

- **Total project cost** = sum of uses (or "at least", when a use is unknown).
- **Remaining funding need** = total project cost − funded to date − committed.
- **Pipeline coverage** = pipeline ÷ remaining need: shown, never deducted.

**D3.** Financing costs: let the PF engine size IDC and fees from the financing case (it holds the
debt mechanics), or take them as stated figures with sources?
**D4.** Initial working capital: OpenPyTEA computes 15 % of fixed capital by default. Count that, or
require a stated figure and show OpenPyTEA's beside it?
