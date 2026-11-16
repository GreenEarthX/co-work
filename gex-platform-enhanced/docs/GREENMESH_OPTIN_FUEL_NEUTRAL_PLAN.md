# GreenMesh: opt-in, fuel-neutral, parametrised — plan for decision

**Version 0.2, 15 Nov 2026: decisions taken by JML (§6).** Nothing here is built. Every finding below was read from
the code or the live database on 15 Nov 2026; if the code disagrees, the code wins.

**JML's requirement (15 Nov):**
- GreenMesh and FlowFusion serve all e-fuels.
- They are an option that producers, buyers and prosumers may choose, never a compulsory feature.
- When a client chooses them, their parameters are cleanly presented and can be set by the users
  who hold the rights.

**What "GreenMesh" covers here:**
- chain of custody (periods, inputs, conversion factors; 097);
- meter reconciliation (098);
- RFNBO correlation (099);
- deliveries, risk, quality and title (103–109);
- the upstream proof (110);
- take-or-pay;
- the evidence pack;
- the registry export (111).

FlowFusion (netting) is not built: it is Phase 3, behind E8.

---

## 1. Where the code stands (measured 15 Nov)

| Requirement | Status | Evidence |
|---|---|---|
| Optional | **Yes, by absence.** A listing, RFQ, match and settlement need no custody period, meter reading or delivery. A lot without a period works (`NO_PERIOD`). | `core/market_engine.py` has no custody check; `custody_grade: NO_PERIOD` (097) |
| Chosen | **No.** No company, project or contract can say "we use GreenMesh". | no setting in `config.py`, no table |
| Unused parts shown fairly | **No.** A contract with no custody shows `custody_period: MISSING` ("no settled or delivered token names this contract"), and `compliance_complete` is false. That reads as a failure for a client who never chose it. | `core/evidence_pack.py:231`, `:267` |
| All e-fuels | **Mostly.** The fuel is a free-text name. The quality sheet takes any parameters. Delivery, risk, title, take-or-pay and export are fuel-blind. The RFNBO checks apply to any electricity-based fuel. | `trading_book/quality.py`, `core/rfnbo_correlation.py` |
| Hydrogen-only parts | **Three.** (a) An upstream citation must be H2 (101, 110). (b) A volume reading converts for H2 only; any other fuel's m³ is refused (102). (c) Input types are fixed at `ELECTRICITY, CO2, N2, WATER, H2`. | `core/custody_ledger.py:223`, `:252`; `102:32`; `097:62` |
| One fuel vocabulary | **No. There are two, plus free text.** (Details below the table.) | live database |
| Parameters on a screen | **No.** The frontend calls none of the custody, meter, PPA, delivery, take-or-pay or evidence-pack routes. | grep of `frontend/src`, 15 Nov |
| Parameters set by the right role | **No.** Any user of the project owner's company may write conversion factors, meter tolerances, facility profiles and PPAs. No role check. The producer sets the very tolerance its own declarations are checked against; `source` is free text. | `api/v1/mass_balance.py:771`; `098:44` (`WRITE` = admin or owner) |

**The two fuel vocabularies:**
- `fuel_catalog`: 10 fuels, with aliases, units and specific energy; GEX writes it.
- `tb_commodity`: 5 commodities; capacities and terms reference it.
- Custody, tokens and lots match a free-text `molecule` exactly. The live capacities hold `H2`,
  `e-Methanol`, `SAF`, `NH3` and `e-NG`.

**Inconsistencies found in the vocabularies:**
- `tb_commodity.registry_pathway = 'E_NG'` while `fuel_catalog` names that fuel `E_METHANE`. `E_NG`
  appears only as an alias there.
- `H2` is `legacy_operational, offered = 0` in `fuel_catalog`, yet it is the fuel the custody code
  is built around.
- `SAF` does not say whether it is bio or e-fuel.
- `HVO` is a biofuel, not an e-fuel.
- `fuel_catalog.specific_energy_value` (e.g. H2 33.3 kWh/kg) comes from a seed file
  (`seed:gex_fuel_catalog.json`), with no source or approval on record.

---

## 2. Principles proposed

1. **Optional.** No trade, listing, settlement or gate ever needs a GreenMesh record. Nothing outside
   GreenMesh reads its tables to decide anything. A guardrail test pins this.
2. **Chosen, on the record.** A client chooses GreenMesh explicitly: who chose it, when, and which
   modules. Choosing and leaving are ledger events. Nothing is inferred from data being present.
3. **Fuel-neutral.** No fuel name in code. What differs by fuel is data from the one fuel catalogue:
   inputs, intermediates, density, scheme and whether RFNBO rules apply.
4. **Every parameter is data with an owner.** Each parameter has a proposer role, a confirming
   party, a source document, a `valid_from` and a screen. An unconfirmed parameter is DECLARED,
   never VERIFIED.
5. **One vocabulary, no third.** The existing catalogue is made the master; no new fuel list is
   created.
6. **FlowFusion inherits all of this** when it is built: opt-in per party, fuel-neutral, every
   parameter data with an owner. Nothing is built for it now (E8).

---

## 3. Work, in four parts

### A. Opt-in

- **A1. Enrolment record.** New table (`greenmesh_enrolment`, append-only), per project:
  - the modules chosen: `custody`, `metering`, `rfnbo`, `export`;
  - `valid_from`; proposed by, confirmed by.
  - Leaving is a new row, never an edit. Its history is kept, and closed periods stay closed.
  - Writes are refused for a project that has not enrolled the module.
  - No live client data is affected. Measured 15 Nov, the dev database holds **zero** rows in
    `coc_period`, `coc_input`, `mass_balance_lots`, `coc_conversion_factor`,
    `coc_meter_tolerance`, `coc_ppa`, `deliveries` and `tokens`. Re-check before the migration.
- **A2. Deliveries are chosen per contract, not per project.** They already are: a delivery needs
  confirmed delivery terms (an Incoterm and a named place). The plan only makes that explicit on
  screen.
- **A3. The evidence pack respects the choice.**
  - A module the project has not chosen is listed under `not_chosen` and produces no items.
  - `compliance_complete` becomes `null` ("not applicable"), not `false`, when nothing was chosen.
  - The three labels VERIFIED / DECLARED / MISSING keep their meaning. "Not chosen" is not a fourth
    label: it is the absence of a section.
  - MISSING then means "chosen and not supported", which is what it should mean.
- **A4. Guardrail.** One test runs a full market trade and settlement with zero GreenMesh rows and
  no enrolment. A second, AST-based guard checks that no market module imports a GreenMesh module.
  Both are negative-verified.

### B. Fuel-neutral

- **B1. One fuel master.** Proposal: `fuel_catalog` is the master, since it has aliases and units.
  - `tb_commodity` references it; its `registry_pathway` already points there.
  - Custody, tokens and lots store the catalogue id, resolved from aliases on entry. Unknown names
    are refused.
  - The existing free-text values are mapped by a one-off script that is listed and reversible.
  - Fix the `E_NG` / `E_METHANE` mismatch. Split SAF into bio and e-fuel pathways, or say it is a
    product with several pathways. Decide whether HVO belongs in a GreenMesh scope at all.
- **B2. Input types from data, not a CHECK list.** A catalogue of input types replaces `097:62`'s
  fixed list. Candidates:
  - CO, and CO₂ split by origin (biogenic, DAC, industrial point source; RED III treats them
    differently);
  - methanol as an intermediate;
  - biomass feedstock, if bio pathways are in scope.
  - The list is for the certifier to confirm; none is invented here.
- **B3. Upstream citations for any intermediate.** Generalise 101 and 110 from "must be H2" to any
  catalogue fuel marked as an intermediate (H2 → NH3, H2 → e-methanol, e-methanol → e-SAF or
  e-gasoline). The upstream RFNBO result is carried through by the same logic (`core/upstream_proof.py`).
- **B4. Volume conversion for any fuel.** Generalise 102: an approved density row per fuel and per
  reference conditions, through the reference registry. Liquids are often metered in m³ too. No
  density is used until approved, exactly as for H2 today (D8).
- **B5. RFNBO checks only where they apply.** Each pathway in the catalogue says whether the
  2023/1184 rules apply. For a pathway where they don't (a biofuel), the correlation check answers
  `NOT_APPLICABLE` with the reason, never FAIL and never PASS.
- **B6. Quality sheet templates.** Reference rows naming a standard per fuel (for H2, methanol and
  jet fuel). They are PROPOSED until approved, with values taken from the standard itself. The
  parties still confirm the sheet on their terms (D2). No value is written here.
- **The specific-energy values** in `fuel_catalog` are not used for any MWh → kg conversion until
  each one has a source and an approval. This links to ledger question 6 in
  `GREENMESH_CONNECTOR_FIELD_MAPPING.md`.

### C. Roles and confirmation

Who may set each parameter. "Today" is measured; "Proposed" is for decision.

| Parameter | Today | Proposed: proposes | Proposed: confirms | Until confirmed |
|---|---|---|---|---|
| Enrolment (A1) | — | owner's Operations or Commercial | a second person of the owner, one an EXECUTIVE (four eyes) | not enrolled |
| Conversion factor | any owner user | owner's Operations | independent engineer or certifier appointed on the project | DECLARED, counts as today |
| Meter tolerance | any owner user; free-text source | owner's Operations | certifier or independent engineer, with a document | **zero, as today** |
| Facility profile (bidding zone, electrolyser commissioning) | any owner user | owner's Operations | independent engineer | DECLARED |
| PPA | any owner user | owner's Commercial, with the PPA document on file | — (the document; the allocation ledger stops double use) | DECLARED |
| Scheme rule (`coc_scheme_rule`) | GEX admin | the certifier's document | GEX records it, four eyes; GEX decides nothing | no rule → as today |
| RFNBO rule (`rfnbo_rule`) | GEX admin | GEX, from the legal text | counsel, recorded | as today |
| Density, other reference rows | GEX, registry lifecycle | unchanged | unchanged | PROPOSED, not in force |
| Quality sheet, Incoterm, title, payment, commitment | contract terms, both parties | unchanged | unchanged | — |
| Inspector | one party proposes, the other agrees, four eyes | unchanged | unchanged | — |
| Registry connector backend | server setting (`none` only) | unchanged | unchanged | — |

- **Where the rules live:** extend `core/market_policy.py`, the one place that says who may act, so
  that there is no second policy module.
- **Existing parameter rows:** none in the dev database (15 Nov). Any that appear before C lands
  have no confirmer; they become DECLARED, are listed, and are never silently promoted.

### D. Screens

- **Capacity & Logistics (`/capacity`)** gets a per-project GreenMesh section:
  - enrolment and modules;
  - fuel and pathway;
  - facility profile, conversion factors, meter tolerances and PPAs;
  - scheme and RFNBO rules, read-only.
  - Each value shows its source, who proposed and who confirmed it, `valid_from` and status.
  - Controls appear only when the server answers `can_propose` / `can_confirm` (the
    `ReviewersPanel` pattern).
- **The contract screen** shows the delivery terms, quality sheet and inspector.
- **The evidence pack** is shown as a read view: per item, its label, result and reason, plus the
  `not_chosen` list.
- Frontend tests for each control's visibility rule.

---

## 4. Order proposed

1. **A (opt-in):** small; it stops unused modules reading as failures. 1 migration.
2. **C (roles):** closes the self-set tolerance, the integrity issue. 1 migration plus policy.
3. **B (fuel-neutral):** the largest. Two or three migrations plus the vocabulary mapping script.
4. **D (screens):** once A–C fix what the screens show.
5. **The evidence allocation ledger** (field mapping v0.1) comes after C. It touches the same tables
   (`coc_input`, `coc_ppa`) and needs C's roles.

Each step follows `.claude/CLAUDE.md`:
- back up first, and round-trip each migration;
- run the full suite with both URLs exported, alone;
- negative-verify each guard;
- record a Tests line and a handoff item.

---

## 5. Decisions for JML

**Opt-in**
- **O1.** Is enrolment per project (proposed), per facility, or per company?
- **O2.** Who enrols: the owner's Operations or Commercial plus an executive (proposed), or an
  executive alone?
- **O3.** May a buyer or prosumer require GreenMesh as a term of its RFQ (e.g. "custody-graded
  supply only")? If so, it becomes a compatibility requirement (`core/compatibility.py`). It stays a
  choice: the seller may decline.
- **O4.** On leaving: closed periods stay closed. Should open periods be closed in deficit-free
  state first, or frozen?

**Fuels**
- **F1.** Is `fuel_catalog` the master (proposed), or `tb_commodity`?
- **F2.** Which input types and CO₂ origins? This is for the certifier.
- **F3.** Are bio pathways (HVO, bio-SAF) in GreenMesh's scope, or e-fuels only?
- **F4.** Which fuels are intermediates that may be cited upstream?

**Roles**
- **R-a.** Does the confirmer table in §3C stand as proposed?
- **R-b.** Should existing unconfirmed parameter rows be relabelled DECLARED (proposed) or archived?

**Screens**
- **S1.** Is the GreenMesh section placed in Capacity & Logistics (proposed), or does it get its own
  menu entry?

---

## 6. Decisions taken (JML, 15 Nov 2026)

All eleven were taken as recommended, except F4, which is broader. (v0.1 said "twelve"; there are
eleven.)

| # | Decision |
|---|---|
| O1 | Enrolment is **per project**. |
| O2 | The owner's Operations or Commercial **proposes**; a second person of the owner, one an EXECUTIVE, **confirms** (four eyes). |
| O3 | A buyer or prosumer **may require GreenMesh** in its RFQ, as a compatibility requirement. The seller still chooses: it may decline or enrol. |
| O4 | Leaving is **refused until every open period is closed** (never in deficit). |
| F1 | **`fuel_catalog` is the master**; `tb_commodity` references it. |
| F2 | The extended input-type list is **drafted from the scheme documents with sources** and stays proposed until the **certifier confirms** it through JML. |
| F3 | **All pathways are in scope, bio included**, with rules per pathway. The RFNBO electricity checks answer `NOT_APPLICABLE` for a pathway they do not cover. |
| F4 | **Any catalogue fuel** may be cited upstream: the catalogue marks intermediates as data. No fuel name is in code. |
| R-a | The roles table in §3C **stands as proposed**. It is implemented in `core/market_policy.py`. |
| R-b | A value with no confirmer is **DECLARED**, listed, and never silently promoted. Confirmation makes it VERIFIED from that date. |
| S1 | The settings live in a **per-project GreenMesh section of Capacity & Logistics** (`/capacity`). No new menu entry. |

**Implementation notes:**
- **O3.** `core/compatibility.py` rules that a missing claim is *Needs evidence*, never
  *Incompatible*. Enrolment is different: it is a fact the platform itself records, not a seller's
  claim. A seller whose project has not enrolled the required module is therefore *Incompatible*
  for that requirement, and the reason says so. Confirm this reading before building it.
- **F4.** Carrying the upstream RFNBO result through applies only where the upstream pathway is
  RFNBO (F3). An intermediate from a bio pathway carries its own scheme result, or none, labelled
  as such.

**Order unchanged:** A, then C, then B, then D, then the evidence allocation ledger, which still
needs answers to its own ten questions (field mapping v0.1).

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 15 Nov 2026 | First draft, after JML's requirement that GreenMesh and FlowFusion be optional, fuel-neutral and parametrised |
| 0.2 | 15 Nov 2026 | JML's eleven decisions recorded (§6) |
