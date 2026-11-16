# GreenMesh Phase 2 — "Add the physical half and the connectors"

**Status: D0–D8 DECIDED by JML on 2026-11-12. Step 1 DONE the same day (head 102), Step 2 DONE (head 103).** A step that
depends on an open decision does not start until it is answered.

Sources:
- `../docs/product/GreenMesh_Description_and_Vision.md`: *Way forward* items 4–6 and the
  roadmap image `greenmesh_media/greenmesh_roadmap.png`.
- Gap register G-08, G-11 and G-19 to G-22.
- `docs/design/greenmesh_physical_layer_reference.py`, the design source. It is not wired.
- The tree and live database as read on 2026-11-12, head **099**. If the code disagrees, the
  code wins; fix this file.

**What Phase 2 adds:**
- Deliveries, routes and title transfer after quality verification (G-08).
- Connectors to the Union Database (UDB), certification schemes and GO registries.
- One live corridor pilot.

**The roadmap's gate that closes Phase 2:** the first real cargo is cleared, settled and audited
with zero findings. The code-side test of that gate is in Step 7. The real gate is an audit
outcome, and no test can stand in for it.

**Out of scope:**
- Netting, both bilateral swaps and multilateral.
- Book-and-claim voluntary mode.
- Min-cost flow routing optimisation.
- Zero-knowledge proofs.

The first two are Phase 3; the last two are not planned.

---

## Where things stand (measured 2026-11-12)

- **Phase 1's code gate is closed.** One synthetic RFNBO trade runs through the real market
  flow, and its evidence pack shows 7 compliance items VERIFIED and PASS, with none DECLARED or
  MISSING (`test_evidence_pack_pg.py`, commit `9240a63`). Suites: platform 1520 pass / 15 skip,
  frontend 265, PF engine 278.
- **The roadmap's Phase 1 gate is NOT passed.** The roadmap reads "one RFNBO trade runs end to
  end **and a certifier accepts its evidence**". No certifier has seen a pack. That is decision D0.
- **`deliveries` exists (044) and is empty.**
  - Columns are `volume_mt` double, integer flags (`quality_verified`, `title_transferred`,
    `payment_received`), and `title_transfer_date` as text.
  - Its policy is FOR ALL with no WITH CHECK, and `gex_app` holds full DML. Anyone with
    `project_access` (a reviewer, a lender) can create, change or delete a delivery: the same
    flaw as G-21.
  - `tb_flow.delivery_id` references it.
  - `trading_book/flows.py` already prices a `quantity_basis = delivered` flow from
    `deliveries.volume_mt`. Phase 2 must keep that reader working.
- **Take-or-pay is a contract TERM, not a schedule.**
  - `contract_tokens` reads `offtake.commitment_form` and `offtake.take_or_pay_pct` from confirmed
    cards, using the conservative aggregate across buyers.
  - Nothing computes a shortfall against delivered quantities (G-11).
- **The gate engine's G11 item `first_deliveries_accepted`** (`bankability_engine.py:358`, owner
  SALES) is verified by a reviewer like any other evidence. No delivery record feeds it.
- **The design source** (`greenmesh_physical_layer_reference.py`) has:
  - A delivery state machine: SCHEDULED → IN_TRANSIT → QUALITY_VERIFICATION →
    TITLE_TRANSFERRED → SETTLED, plus DISPUTED.
  - Quality verification before title transfer.
  - Availability and penalty tracking.

  Its figures, such as a material breach below 80% availability, are not reference data, and none
  of its logic has been reviewed.
- **Open gaps Phase 2 builds on:**
  - G-19: 72 test lots on `proj_etf_pecos1`.
  - G-20: chain-of-custody actors are taken from the request body.
  - G-21: lots are writable by project-access holders.
  - G-22: volumetric meter units are refused.
  - Hydrogen supplied as a custody input has no correlation check (handoff item 65). This blocks
    an ammonia corridor, because RFNBO ammonia depends on its hydrogen being RFNBO.

---

## Decisions needed from JML

| # | Decision | Why it blocks | Decision |
|---|---|---|---|
| **D0** | Start Phase 2 code before a certifier has accepted a Phase 1 pack, or wait? | The roadmap says the next phase starts only when the gate is passed. | **JML 2026-11-12: start Step 1 now.** Whether Step 2 waits for a certifier's feedback on a Phase 1 pack is still to be confirmed. |
| **D1** | Who verifies a delivery's quality? | Title transfer depends on it. No reviewer role covers cargo inspection: `REVIEWER_GATES` is scoped by gate, not by delivery. | **JML 2026-11-12:** an **independent inspector** (SGS or similar) does the inspection. Either party appoints it, and both parties agree to it. GEX staff do not appoint it. It is never the seller's or the buyer's company, and its certificate document must be on file (sha256). |
| **D2** | Where is the quality spec read from? | The check needs limits. | **JML 2026-11-12:** from the quality specification sheet in the contract's CONFIRMED terms only (purity, GHG intensity cap, other parameters). A delivery under a contract with no confirmed spec cannot reach title transfer. |
| **D3** | Can an off-spec delivery still pass title? | Common in practice (an accepted price adjustment), but it weakens the evidence. | **JML 2026-11-12:** yes, but only with a waiver confirmed by both parties, recorded with a document (the 077 premise-change pattern). The pack shows it as DECLARED with result FAIL, never as PASS. |
| **D4** | Where does title pass? | Title transfer and risk need a named place. | **JML 2026-11-12:** an Incoterms 2020 rule and a named place on the contract terms. GEX records the parties' stated transfer; it does not judge it legally. **Amended by JML 2026-11-12 (Step 3 ruling R1):** the Incoterm and named place govern RISK only; title passes by the contract's title clause (amendment B1). |
| **D5** | Which scheme and registry first? | Each connector is its own integration. | **JML 2026-11-12:** CertifHy or ISCC EU first, the UDB last *(15 Nov: "CertifHy" must name its scheme; the NGC is book-and-claim disclosure and does not fit the physical RFNBO chain, only the CertifHy EU RFNBO Voluntary Scheme or ISCC EU does; restating D5 is open for JML)*, **and the door left open for further actors**. Every connector sits behind one interface, so a new scheme, registry or GO hub is an added module, not a redesign. Reading GO cancellation statements inbound fits the same interface. Confirm each interface before any design; see Step 6. |
| **D6** | May GEX submit to a registry for a client? | Many registries accept submissions only from the economic operator or the certification body. | **JML 2026-11-12:** export only. GEX builds the submission file, and the party or its certifier submits it. Default `REGISTRY_CONNECTOR_BACKEND = none`. *(15 Nov, corrected: a written mandate does not authorise GEX to hold or reuse a party's login. A live submission would need the party's mandate AND access through the registry's own route, under its rules: its delegated access, an application identity of GEX's own, or service-provider permissions. G-REX's manual prohibits the password grant. See `docs/GREENMESH_CONNECTORS_RESEARCH.md`.)* |
| **D7** | The pilot corridor and partner. | A real cargo needs a real producer, buyer and certifier. | **JML 2026-11-12:** ammonia into North-West Europe. FortaVerde Pecém (tenant `mohring_energie`) is the candidate, only with the client's consent. Real data stays local and git-ignored, because `co-work` is public. |
| **D8** | Hydrogen density and reference conditions (G-22), and the G-19 test lots. | A pilot plant's meters may report Nm³. The test lots sit on a real project. | **JML 2026-11-12:** the density is a reference-registry row, proposed with its source and approved through the lifecycle, never written in code. G-19: archive the 72 lots, then delete them after a backup. JML has authorised this. |
| **T1** | The token-holder rule when legal title passes before acceptance (Step 3 amendment, B1). | The title clause may pass title at risk or on documents, before the cargo is accepted; GEX moves the token only once. | **Open.** Proposal: hold the token until ACCEPTED, labelled "legal title clause precedes acceptance; token held until ACCEPTED". Built as proposed, listed as open. |
| **T2** | The DISPUTED exit (Step 3 amendment, B3). | A dispute today has no exit. | **Open.** Proposal: a resolution confirmed by both parties, to ACCEPTED (labelled "resolved") or to REJECTED; four eyes where TRADE_CONFIRM asks for them; no GEX arbitration. |
| **T3** | The title and payment clauses for the first real structure (the corridor pilot, D7). | Without them no pilot delivery can pass title or produce a payment figure. | **Open.** From the term sheet, with the client's consent. |

---

## Step 0 — before any change

1. Branch `greenmesh-phase2` from `greenmesh-phase1`'s head in both trees. Never push.
   `pg_dump` before every migration (`files/backup_postgres.sh`).
2. Export both database URLs and run all three suites alone. Record the counts and the head
   (099 expected). Read the skips with `-rs`.
3. No deletions without JML. Retired files go to `../_claude_backups/<date>_greenmesh_phase2/_to_delete/`.

## Step 1 — close what Phase 2 stands on

**Done 2026-11-12, head 102** (handoff §8 item 68). Platform 1543 / 15 skip / 0 fail. The density
row is proposed, not approved. New gap G-23: a hydrogen input can name only a lot its company may
write.

These steps need no Phase 2 decision; the G-22 density row needs D8.

- **G-20:** every chain-of-custody actor field (`created_by`, `allocated_by`, `opened_by`,
  `recorded_by`, `closed_by`) is taken from the token's user. A body value is ignored or refused,
  as in evidence review.
- **G-21 and `deliveries`:**
  - Split the FOR ALL policies on `mass_balance_lots` and `deliveries` into SELECT (current read
    rule) and INSERT/UPDATE/DELETE (owner or GEX only).
  - Assert both in the migration, as 062 did.
  - A pg test reproduces the hole first: a reviewer company creates a delivery.
- **G-22:** accept Nm³ and m³ only once an approved density row exists. Store the row's id with
  the converted reading. Propose the row with its source and reference conditions. It is not in
  force until approved.
- **G-19 (D8):**
  1. `pg_dump` first.
  2. Copy the 72 `created_by = 'test'` lots on `proj_etf_pecos1` to an archive table or file.
  3. Delete them, as the superuser.
  4. Confirm that no allocation, token or period referenced them.
- **Hydrogen as an input:** a `coc_input` of type H2 must name the producing period, or a lot of
  an RFNBO hydrogen period. The period statement then carries that period's correlation result
  through, so a downstream ammonia period is only as RFNBO as its hydrogen. If no upstream period
  is named, the input stays UNVERIFIED and is never assumed.
- **Tests:** each hole reproduced before the fix and passing after; negative-verified.

## Step 2 — the delivery record (migration 100+)

**Done 2026-11-12, head 103** (handoff §8 item 69; JML: "Start Step 2 now"). One history (delivery
events on the contract chain), the state order and the acting party enforced by trigger, at most what
custody allocated to the tokens, nothing dated inside a closed custody period, the Incoterm read from
the confirmed terms. ACCEPTED, REJECTED, TITLE_TRANSFERRED and SETTLED are refused until Step 3.
**For Step 3 to decide:**
- whether the buyer's receipt or only acceptance prices a delivered-basis payment (today: the receipt,
  REJECTED excluded);
- how a DISPUTED delivery is resolved (today: no exit);
- the over-dispatch tolerance (today: none).

New gap G-24: market trades carry no Incoterm.

Rebuild `deliveries` as a real record on the one contract model. Do not create a second history.

- **Columns:**
  - Typed columns: boolean, timestamptz, numeric. No integer flags and no text dates.
  - Contract (`tb_contract`) and, for an offtake frame, the buyer's sub-leg.
  - Seller and buyer companies; the lot(s) and token(s) it draws on.
  - Scheduled window and actual times.
  - Nominated and delivered quantity: canonical kg, with `volume_mt` kept readable for
    `flows.py`.
  - Transport mode (pipeline, ship, truck, rail, ISO-container) and route: origin and
    destination as UN/LOCODE or a registered facility.
  - Incoterm and named place (D4).
- **States:**
  - Main path: SCHEDULED → IN_TRANSIT → ARRIVED → QUALITY_VERIFICATION → ACCEPTED →
    TITLE_TRANSFERRED → SETTLED.
  - Side branches: REJECTED and DISPUTED.
  - Transitions happen in one function, and each one is a contract event on
    `trading_book/record.py`, hash-chained and in the anchor outbox.
  - The row's state is derived from the events and fixed by trigger.
- **Rules:**
  - A delivered quantity never exceeds the quantity allocated to the contract's tokens.
  - A delivery on a closed custody period is refused.
  - Moving to IN_TRANSIT is the seller's act; ARRIVED is the buyer's.
  - Four eyes inside a company wherever TRADE_CONFIRM already asks for them.
- **RLS:** the parties and GEX read; the seller writes the dispatch and the buyer writes the
  receipt. A project-access holder reads only.
- **Tests (`pg_store`):** state order enforced, wrong-party acts refused, over-delivery refused,
  `flows.py`'s delivered-quantity flow priced from a new delivery (its existing tests stay green).

## Step 3 — quality before title (needs D1, D2, D3)

Superseded where the amendment below differs.

- The spec comes from the quality specification sheet in the confirmed card terms (D2).
- **Appointing the inspector (D1):** two contract events on the record.
  1. Either party proposes an inspector company, with the appointment document's sha256.
  2. The other party confirms it, with four eyes inside each party wherever TRADE_CONFIRM asks
     for them.

  Until both parties have agreed, there is no inspector. The appointment is refused when:
  - the inspector's company is the seller's or the buyer's;
  - it is a GEX account;
  - it is not an ACTIVE, registered company.

  Replacing an inspector takes the same two steps.
- The agreed inspector records a quality certificate: a document on file by sha256, plus the
  measured value of each spec parameter. Refused when:
  - the inspector is not the one agreed on the contract;
  - the certificate is missing.
- The check is computed per parameter as PASS or FAIL. A delivery reaches ACCEPTED only if every
  parameter passes, or under a waiver confirmed by both parties (D3), which is labelled.
- **Title transfer** needs ACCEPTED. It moves the delivered quantity of the tokens to the buyer
  through the existing token lifecycle (`tokens.holder_company_id`, MINTED → RETIRED in
  `tokens_sqlite.py`). There is no second ownership table.
- **Settlement:** for a contract with deliveries, a settlement must name a TITLE_TRANSFERRED
  delivery. SPOT token settlements, as in the Phase 1 gate, are unchanged.
- **Tests:**
  - an off-spec cargo refused;
  - a waiver labelled;
  - a non-independent inspector refused;
  - an inspector proposed but not agreed cannot certify;
  - title before acceptance refused;
  - settlement before title refused.

## Step 3 — amendment (12 Nov 2026)

From JML via Claude.ai, 12 Nov 2026 (`docs/GREENMESH_PHASE2_STEP3_PROMPT.md`). Where this section and
the original Step 3 differ, this section governs. Nothing in it is built: the build starts only on
JML's "go Step 3".

### B1. Three records, three triggers

Risk, title and payment are separate. None of them is derived from another.

| Record | Governed by | Event |
|---|---|---|
| **Risk** | The Incoterm and named place (D4), from the confirmed terms | `RISK_PASSED`: derived, with no party act. |
| **Title** | A title clause in the confirmed terms | Clause options: `ON_RISK`, `ON_ACCEPTANCE`, `ON_PAYMENT_IN_FULL` (retention of title), `ON_DOCUMENT_TRANSFER` (B/L or delivery order). |
| **Payment** | A payment clause in the confirmed terms | The trigger is one of `ON_BL`, `ON_INSPECTOR_CERTIFICATE`, `ON_ACCEPTANCE`, `ON_TITLE`. The quantity basis is one of `BL_QTY`, `OUTTURN_QTY` (the buyer's receipt), `ACCEPTED_QTY`. |

When risk passes, by Incoterm:
- **FCA, FAS, FOB, CFR, CIF, CPT, CIP:** on dispatch (IN_TRANSIT), at the shipment point.
- **EXW:** when the goods are placed at the buyer's disposal; recorded at dispatch at the latest.
- **DAP, DDP:** on ARRIVED.
- **DPU:** on ARRIVED, with unloading recorded.
- **C terms:** the named place is the destination, but risk passes at shipment. The confirmed terms
  must therefore also carry the shipment point; without it, `RISK_PASSED` is refused.

Rules:
- **Incoterms do not govern title.** Remove every place where title or TITLE_TRANSFERRED is gated on
  the presence of an Incoterm. The Incoterm gates risk only. List each place changed.
- **No default title clause.** A delivery whose contract has no title clause cannot reach
  TITLE_TRANSFERRED. The refusal names the missing clause.
- **Payment without a clause:**
  - a new contract confirmed after the migration produces no payment figure, and the refusal names
    the missing clause;
  - for an existing contract, `flows.py` keeps today's receipt basis, labelled "no payment clause —
    receipt basis assumed", and its existing tests stay green.
- **When GEX moves the token holder:** at the later of ACCEPTED and the title trigger. This keeps
  "quality before title". If the contract's legal title passes before acceptance (`ON_RISK` on F or C
  terms, or `ON_DOCUMENT_TRANSFER`), the record says so in a label: "legal title clause precedes
  acceptance; token held until ACCEPTED". **This is decision T1:** built as described, listed as open.

### B2. Partial delivery: split the token

A token has one holder, and the RLS policies depend on that. Do not add a shared-holdings table.

- **On TITLE_TRANSFERRED for less than the token's quantity:**
  - the parent token goes to a new terminal state `SPLIT`;
  - two child tokens are created, with `parent_token_id` set: one for the transferred quantity
    (holder = the buyer) and one for the remainder (holder = the seller).

  When the whole token is transferred, there is no split; only the holder changes.
- **Inheritance:** children inherit the parent's certificate reference and its custody lineage
  (097–101: period, inputs, characteristics, RFNBO correlation). The certificate quantity is
  apportioned in canonical kg, and nothing is rounded away.
- **One transaction, one event:** the split and the holder change are one transaction, written as one
  contract event on `trading_book/record.py`, hash-chained and in the anchor outbox.
- **Check first:** the current token lifecycle (`tokens_sqlite.py` and its PostgreSQL counterpart)
  and `delivery_draw`. If `SPLIT` or the parent link conflicts with what exists, report it before
  writing the migration.

### B3. The three questions Step 2 left open

- **What prices a delivered-basis payment:** the payment clause (B1). The receipt basis stays only as
  the labelled fallback for existing contracts.
- **DISPUTED:** it exits only through a resolution event confirmed by both parties, to ACCEPTED
  (labelled "resolved") or to REJECTED. Four eyes apply where TRADE_CONFIRM asks for them. GEX does
  not arbitrate. **Decision T2:** listed as open.
- **Over-dispatch tolerance:** only from a tolerance term in the confirmed terms. Without one there is
  no tolerance, as today.

### B4. Rejection

- REJECTED releases the delivery's draw back to the seller's token. The certificate is untouched, and
  no split happens.
- Step 3 accepts or rejects a delivery as a whole. Partial acceptance by quantity is out of scope and
  goes into the gap register as a new gap.

### B5. Invariants — each gets its own `pg_store` test

1. The children's quantities sum exactly to the parent's, in kg and in certificate quantity.
2. No quantity has two holders at the same time, and a `SPLIT` parent has no holder that can act.
3. A token holder never changes before ACCEPTED, nor before the title trigger.
4. Risk can pass before title. Title recorded before risk is caught and labelled, not silently allowed.
5. A rejected delivery returns its draw with the certificate intact.
6. A child token keeps its parent's RFNBO correlation result and custody lineage.
7. RLS: the buyer cannot read the seller's remainder child beyond what the parties already read today.
8. The tests already listed under Step 3 all pass:
   - off-spec refused;
   - waiver labelled;
   - non-independent inspector refused;
   - an inspector proposed but not agreed cannot certify;
   - title before acceptance refused;
   - settlement before title refused.
9. The Phase 1 gate and the Step 2 tests stay green.

### B6. Scope and stop points

- Migrations 104 onward. Market trades are unchanged (G-24 stays open).
- Build in this order:
  1. clauses on the confirmed terms;
  2. `RISK_PASSED`;
  3. inspector, certificate and ACCEPTED/REJECTED;
  4. the DISPUTED exit;
  5. title and the token split.
- **Stop before SETTLED**, and report.
- **Reporting after each sub-step:** measured test counts and head, a handoff §8 item, and gap register
  updates for G-11, G-23, G-24 and the new partial-acceptance gap.

Decisions T1–T3 are in the decision list above.

**Sub-step 1 done 2026-11-12, head 104** (handoff §8 item 70): typed delivery, title and payment
clauses, V15, `title` admitted by the database, three bases on every delivery. **Waiting on JML:**
- **P1:** whether "no payment clause, no payment figure" for contracts confirmed after the migration
  applies to market trades. None can carry the clause (G-24), so applying it removes the payment figure
  from every new market trade, against B6.
- **P2 (G-25):** how a contract gets both tokens and typed clauses, the precondition for sub-steps 2–5.
  **Answered 2026-11-13: an order-book sell order names a token** (105).

**Sub-step 2 done 2026-11-13, head 106** (handoff §8 item 71). Risk passes by the Incoterm as a derived
fact event; DPU's unloading record and `delivery_document` are built; facts do not move the state.
P1 still waits on JML.

**Sub-step 3 done 2026-11-13, head 107** (handoff §8 item 72): spec sheet + V16, inspector proposed and agreed
(four eyes, `DELIVERY_CONFIRM`), certificate, derived ACCEPTED, waiver (DECLARED/FAIL), buyer's REJECTED
releasing the draws.

**Sub-step 4 done 2026-11-13, head 108** (handoff §8 item 73): resolution proposed by one party and confirmed by
the other with four eyes; derived ACCEPTED (only with the certificate, R4) or REJECTED. **For T2:** a dispute
raised before inspection can end only REJECTED, because certification needs QUALITY_VERIFICATION.

**Sub-step 5 done 2026-11-13, head 109** (handoff §8 item 74): title at the later of ACCEPTED and the title clause's
trigger, the exact token split, frozen SPLIT tokens, R2. **Stopped before SETTLED**, as B6 says. Open:
- T1–T3, P1 and G-27 (title on payment in full);
- whether title passes on the drawn kg, as built, or on the received kg;
- the buyer's part made SETTLED at title.

**FlowFusion (JML, 2026-11-13): no economics code until E1–E9 are answered.** The FlowFusion integration plan
of 13 Nov was written against head 103. Its title, risk, waiver and split cases are built (104–109). Its
economics method, labelled proposal statuses and whole-claim check are kept as design input, and its
permissioned upstream proof is noted for G-23.

### Rulings on the code check (JML, 12 Nov 2026)

Before writing anything, Claude Code checked the amendment against the code and reported 12 places
where the two disagree. JML ruled on the four that were his to decide, as proposed:

- **R1 — D4 is risk only.** D4 is amended (decision list above): the Incoterm and named place govern
  risk; title passes by the title clause.
  - Corrected in Part C: the `title_basis` label and the docstring in `core/delivery_record.py`, G-24
    in the gap register, handoff item 69.
  - **Outside the repository, JML's to make:** in the description document, weakness 2 should read
    "Title has no clause of its own yet; the Incoterm governs risk only."
- **R2 — market settlement and the token holder.** Today `market_engine.confirm_settlement` moves the
  whole token to the buyer when the seller confirms payment, with no delivery or acceptance. From
  Step 3:
  - once a contract has a delivery, a market settlement no longer moves the holder; the holder
    changes only through the delivery record;
  - a contract with no delivery (the Phase 1 gate's SPOT settlement) is unchanged.

  This is the one change to market code in Step 3; B6's "market trades are unchanged" is read
  subject to it.
- **R3 — what is apportioned on a split.** No certificate quantity exists in the record.
  - **kg:** apportioned exactly, as decimal (numeric), from the token's custody allocation.
  - **Certificate id:** inherited unchanged.
  - **`energy_mj`:** apportioned by the same ratio and labelled DECLARED (it is a float and was never
    verified).
  - **Later:** if a certifier issues certificates carrying their own quantity, that quantity becomes a
    column of its own. B5 invariant 1 is read as kg exact, with `energy_mj` declared.
- **R4 — a resolved dispute still needs the inspection.** A DISPUTED delivery reaches ACCEPTED only
  with the agreed inspector's certificate:
  - the certificate passes: ACCEPTED, labelled "resolved";
  - it fails, and both parties confirm a waiver: ACCEPTED, labelled DECLARED and FAIL (D3);
  - otherwise: REJECTED.

  This refines T2, which stays open.

**Build notes.** The other eight points are design choices, proposed by Claude Code. JML raised no
objection; they are listed so the build follows them:
- **Test contracts:** Step 3's tests run on order-book trades that carry title and payment clauses.
  Market trades cannot carry them.
- **Splitting:** a `token_split` record (parent, children, kg as numeric), its sum checked by trigger.
  A child's kg comes from it, never from new custody allocations (they would double-count the lot).
  Lineage and the evidence pack follow `parent_token_id`.
- **Token write policies:**
  - a SPLIT parent is frozen by trigger;
  - `holder_company_id` changes only on the operator connection;
  - the holder keeps only the evidenced retirement act;
  - the capacity owner loses write access to tokens it no longer holds;
  - read rules are unchanged (B5 invariant 7).
- **Which tokens split:** only tokens on the delivery's contract, in RESERVED or MATCHED. Children
  start in the parent's state; SPLIT is terminal, in both the database check and `TOKEN_TRANSITIONS`.
- **Rejected draws:** 104's draw guard stops counting the draws of a REJECTED delivery. No row is
  deleted (103 keeps draws append-only).
- **Event names:**
  - state events keep `DELIVERY_<state>`;
  - facts get their own types (`DELIVERY_FACT_RISK_PASSED`, `DELIVERY_FACT_UNLOADED`, and so on), and
    the state is read from state events only;
  - DISPUTED gains exits to ACCEPTED and REJECTED.
- **New recorded facts**, each naming a document on file by sha256:
  - B/L or delivery order: the seller, with its quantity (`ON_BL`, `BL_QTY`);
  - document transfer: the buyer's acknowledgement (`ON_DOCUMENT_TRANSFER`);
  - unloading: the buyer (DPU).
- **Smaller points:**
  - `title` is added to the clause types, and the `delivery` clause gains `shipment_point` (C terms);
  - the over-dispatch tolerance is the flow's existing `tolerance_min_pct` / `tolerance_max_pct`;
  - "confirmed after the migration" is read against a one-row cut-over record written by 104;
  - dispute resolution's four eyes are a new action type with TRADE_CONFIRM's rules (a second person
    of the same company, one an executive), raised on the delivery.

## Step 4 — what delivery proves for the contract (G-11, partly)

**Done 2026-11-13, head 110, no migration** (handoff §8 item 76).
- **Decided by JML on 2026-11-13: keep the trade clause.** The shortfall reads the trade's own typed
  `commitment` clause, not the offtake cards. Deliveries exist only on trades, and frame sub-legs from trades
  carry no take-or-pay fields.
- **Not computed:** availability and penalties. No confirmed term defines them.
- **G11:** the seller files the acceptance record as evidence for the reviewer.

- **Take-or-pay shortfall:** per contract year, delivered and accepted quantity against
  `take_or_pay_pct` × contracted quantity, read only from confirmed terms. The output is a
  shortfall quantity, plus an amount if and only if the contract states a shortfall price. GEX
  computes; it does not invoice.
- **Availability and penalties:** compute availability only from metered production
  (`plant_data`), and penalties only if the contract carries the guarantee and the rate. The
  design source's 80% material-breach threshold is not used unless a contract states it.
- **G11 `first_deliveries_accepted`:** the delivery record attaches its acceptance events and
  certificate as a document the reviewer can verify. It does **not** verify the item itself
  (Attack A: GEX verifies nothing).
- **Tests:** shortfall arithmetic, a missing term gives no figure, a waiver counted as declared.

## Step 5 — the evidence pack, extended

**Done 2026-11-13, no migration, pack version 2** (handoff §8 item 77).
- **Open:** settlement items cannot name their delivery until settlement on a delivery exists (after
  Step 3). The pack states the missing link.
- **Fixed on the way:** a delivery contract's token, which the pack missed when it had no settlement.

- Add a `delivery` section per delivery:
  - `quality` is VERIFIED when an independent certificate is on file and the computed check
    passes; DECLARED under a waiver; MISSING with no certificate.
  - `title_transfer` is VERIFIED from the recomputed event chain.
  - `route` and `incoterm` are DECLARED.
- Settlement items name their delivery.
- `compliance_complete` additionally requires every delivery to be quality VERIFIED and PASS.
- The manifest stays deterministic, so the same records give the same hash.

## Step 6 — connectors (needs D5, D6)

**Status (corrected 15 Nov 2026): export foundation complete; external adapters and inbound
verification outstanding.** Head 111 (handoff §8 item 78, correction item 90; research in
`docs/GREENMESH_CONNECTORS_RESEARCH.md`, corrected 15 Nov).
- **Built:** the interface, `gex_export_v1` (GEX's internal format, not a registry's), the VERIFIED
  gate, the append-only outbox, `none` only. No registry has accepted a GEX file.
- **The 13 Nov research overstated what is unpublished.** These are public:
  - the AIB's message schemas (v80 and v81, defined in SD03 HubCom 9.1; AMQP XML or JSON);
  - the UDB's Exchange Model (XSDs v3.5, field specifications) and its connectivity documentation;
  - EEX's G-REX API manual v3.2 (REST, OpenAPI, demo environment, EEX France only).

  Its "GEX can only read" was wrong too: GEX's role depends on the registry's own access routes
  and permissions; a mandate alone gives none. Field mapping draft:
  `docs/GREENMESH_CONNECTOR_FIELD_MAPPING.md` (v0.3, for JML).
- **Outstanding, and none of it waits for a partner account:**
  - review those schemas;
  - inbound verification, as three tasks: extraction (needs the format), matching (GEX's records)
    and authoritative confirmation (needs registry access);
  - the scheme adapters.
- **D5 needs restating (open for JML).** CertifHy is two schemes: the NGC (book-and-claim,
  disclosure, not RFNBO compliance) and the EU RFNBO Voluntary Scheme (Commission-recognised). For
  the physical RFNBO chain the choice is the CertifHy EU RFNBO Voluntary Scheme or ISCC EU, by the
  pilot partner.

**Research first; write down the interface and its source before writing code.** UDB, CertifHy,
ISCC and the AIB hub each have their own data model and access rules. Do not invent field names.
For each connector, record:
- who may submit;
- the format;
- whether a test environment exists;
- the source and the date it was read.

- **Order (D5):** CertifHy or ISCC EU first, whichever the pilot partner uses, and the UDB last.
  The interface stays open to further actors: other schemes such as REDcert, GO hubs, and
  voluntary registries for Phase 3.
- **Shape:** `core/registry_connectors/<name>.py` behind one interface, used two ways:
  - Outbound: build the submission from the record, and refuse when any required item is not
    VERIFIED.
  - Inbound: read a GO cancellation statement or a scheme certificate, and verify it against the
    custody input that cites it.
- **Outbox:** every outbound submission is written to an outbox, as `ledger_anchor_outbox` is,
  with the payload hash. The default backend is `none`, which means export a file and send
  nothing. Live submission needs D6's mandate, access through the registry's own route
  (delegated access, an application identity or service-provider permissions, under its rules;
  never a party's login held or reused by GEX), and a test registry first. GEX's own secrets
  (for example an application's key) stay out of git, as every secret does. Production is not a
  configuration value.
- **Tests:** the payload is built only from VERIFIED items; a refusal names what is missing; the
  outbox is append-only; no network call happens under `none`.

## Step 7 — the corridor pilot (needs D7)

- **Code gate (`pg_store`, synthetic and labelled TEST):** one ammonia cargo runs end to end:
  1. metered hydrogen production;
  2. a hydrogen period, closed with a RFNBO correlation PASS;
  3. hydrogen supplied as an input to an ammonia period;
  4. an ammonia lot and its token;
  5. the contract through the real market flow;
  6. a delivery by ship, quality-certified by an appointed inspector, with title transferred;
  7. the settlement;
  8. the scheme export built.

  In the pack, the compliance and delivery sections have no item DECLARED or MISSING.
- **Real gate:** a real cargo from the D7 partner goes through the same flow on the live
  platform, and its pack is audited by the partner's certifier with zero findings. Record:
  - the cargo;
  - the certifier;
  - each finding and how it was closed.

  Until then, Phase 2 is built, not passed.

---

## Reporting

Report as in Phase 1. After each step:
- append a dated line under *Tests* in `.claude/CLAUDE.md` with the measured counts and head;
- add a handoff §8 item;
- update the gap register (G-08, G-11, G-19 to G-22, and any new gap).

State what is verified and what is declared, and do not overclaim. A step that waits on a
decision is reported as waiting, never worked around.
