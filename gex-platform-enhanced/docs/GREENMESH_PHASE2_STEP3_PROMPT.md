# Claude Code prompt — GreenMesh Phase 2, Step 3 amendment (risk, title, payment; token split)

From JML via Claude.ai, 12 Nov 2026. Work in `files/gex-platform-enhanced` (backend) unless a path says otherwise.

## Standing rules (unchanged)

- Back up every file before you edit it, to `files/_claude_backups/<date>_<topic>/`. Delete nothing without JML. Never push.
- Synthetic data only. Do not name FortaVerde or use its data in code, tests or fixtures. That needs the client's consent.
- Code wins. Where this prompt and the code disagree, report the disagreement before you change anything.
- Migrations: `alembic upgrade auth_slice@head` with `ALEMBIC_DATABASE_URL`. The app runs as `gex_app` under FORCED RLS. Tests use the `pg_store` fixture.
- Report as in the brief's *Reporting* section. Label what is verified and what is declared. A step that waits on a decision is reported as waiting, never worked around.

## Part A — register the reference (do now)

1. Read `../docs/product/GreenMesh_Description_and_Vision.md`. It is v2 and the master; the Word file is generated from it. Build nothing from it directly.
2. In `.claude/CLAUDE.md`, under the GreenMesh brief, add three lines:
   - v2 of the description is the reference;
   - its economics section (netback to IRR) is SCENARIO only until decisions E1–E9 are answered, so build no economics code;
   - Phase 2 Step 3 follows the amendment below, not the original Step 3 text.

## Part B — amend the brief (do now, then stop)

Back up `docs/GREENMESH_PHASE2_BRIEF.md`. Then add a section **"Step 3 — amendment (12 Nov 2026)"** directly after the current Step 3. Leave the original Step 3 text in place, and add one line under its heading: "Superseded where the amendment below differs." The amendment contains B1–B6.

### B1. Three records, three triggers

Risk, title and payment are separate. None of them is derived from another.

| Record | Governed by | Event |
|---|---|---|
| **Risk** | Incoterm and named place (D4), from the confirmed terms | `RISK_PASSED`, derived, with no party act. **FCA, FAS, FOB, CFR, CIF, CPT, CIP:** on dispatch (IN_TRANSIT) at the shipment point. **EXW:** when the goods are placed at the buyer's disposal; recorded at dispatch at the latest. **DAP, DDP:** on ARRIVED. **DPU:** on ARRIVED with unloading recorded. For C terms the named place is the destination, but risk passes at shipment, so the confirmed terms must also carry the shipment point; without it, `RISK_PASSED` is refused. |
| **Title** | A title clause in the confirmed terms | Clause options: `ON_RISK`, `ON_ACCEPTANCE`, `ON_PAYMENT_IN_FULL` (retention of title), `ON_DOCUMENT_TRANSFER` (B/L or delivery order). |
| **Payment** | A payment clause in the confirmed terms | The trigger is one of `ON_BL`, `ON_INSPECTOR_CERTIFICATE`, `ON_ACCEPTANCE`, `ON_TITLE`. The quantity basis is one of `BL_QTY`, `OUTTURN_QTY` (buyer's receipt), `ACCEPTED_QTY`. |

- **Incoterms do not govern title.** Remove every place where title or TITLE_TRANSFERRED is gated on the presence of an Incoterm. The Incoterm gates risk only. List each place you change.
- **No default title clause.** A delivery whose contract has no title clause cannot reach TITLE_TRANSFERRED. The refusal names the missing clause.
- **Payment without a clause.** For a new contract confirmed after the migration, no payment figure is produced; the refusal names the missing clause. For an existing contract, `flows.py` keeps today's receipt basis, and the figure is labelled "no payment clause — receipt basis assumed". Its existing tests stay green.
- **When GEX moves the token holder.** GEX moves `holder_company_id` at the later of ACCEPTED and the title trigger. This keeps "quality before title". If the contract's legal title passes before acceptance (`ON_RISK` on F or C terms, or `ON_DOCUMENT_TRANSFER`), the record says so in a label: "legal title clause precedes acceptance; token held until ACCEPTED". **This is decision T1. Build it as described, but list T1 as open.**

### B2. Partial delivery: split the token

A token has one holder, and the RLS policies depend on that. Do not add a shared-holdings table.

- On TITLE_TRANSFERRED for a quantity smaller than the token's quantity:
  - the parent token goes to a new terminal state `SPLIT`;
  - two child tokens are created, with `parent_token_id` set: one for the transferred quantity (holder = buyer) and one for the remainder (holder = seller);
  - when the whole token is transferred, there is no split; only the holder changes.
- Children inherit the parent's certificate reference and its custody lineage (097–101: period, inputs, characteristics, RFNBO correlation). The certificate quantity is apportioned in canonical kg, and nothing is rounded away.
- Split and holder change are one transaction, written as one contract event on `trading_book/record.py`, hash-chained, in the anchor outbox.
- Check the current token lifecycle (MINTED → RETIRED in `tokens_sqlite.py` and its Postgres counterpart) and `delivery_draw`. If `SPLIT` or the parent link conflicts with what exists, report it before you write the migration.

### B3. The three questions Step 2 left open

- **What prices a delivered-basis payment:** the payment clause (B1). The receipt basis stays only as the labelled fallback for existing contracts.
- **DISPUTED:** it exits only through a resolution event confirmed by both parties, to ACCEPTED (labelled "resolved") or to REJECTED. Four eyes apply where TRADE_CONFIRM asks for them. GEX does not arbitrate. **Decision T2: list it as open.**
- **Over-dispatch tolerance:** only from a tolerance term in the confirmed terms. Without one there is no tolerance, as today.

### B4. Rejection

- REJECTED releases the delivery's draw back to the seller's token. The certificate is untouched, and no split happens.
- Step 3 accepts or rejects a delivery as a whole. Partial acceptance by quantity is out of scope; add it to the gap register as a new gap.

### B5. Invariants — each one gets its own `pg_store` test

1. The children's quantities sum exactly to the parent's, in kg and in certificate quantity.
2. No quantity has two holders at the same time, and a `SPLIT` parent has no holder that can act.
3. A token holder never changes before ACCEPTED, nor before the title trigger.
4. Risk can pass before title. Title recorded before risk is caught and labelled, not silently allowed.
5. A rejected delivery returns its draw with the certificate intact.
6. A child token keeps its parent's RFNBO correlation result and custody lineage.
7. RLS: the buyer cannot read the seller's remainder child beyond what the parties already read today.
8. The tests already listed under Step 3 (off-spec refused, waiver labelled, non-independent inspector refused, inspector proposed but not agreed cannot certify, title before acceptance refused, settlement before title refused) all pass.
9. The Phase 1 gate and the Step 2 tests stay green.

### B6. Scope and stop points

- Migrations 104 onward. Market trades are unchanged (G-24 stays open).
- Build in this order:
  1. clauses on the confirmed terms;
  2. `RISK_PASSED`;
  3. inspector, certificate and ACCEPTED/REJECTED;
  4. DISPUTED exit;
  5. title and the token split.
- **Stop before SETTLED**, and report.

### Decisions for JML (put these in the brief's decision list)

- **T1:** the token-holder rule when legal title passes before acceptance (B1). Proposal: hold the token until ACCEPTED, labelled.
- **T2:** the DISPUTED exit (B3). Proposal: a resolution confirmed by both parties; no GEX arbitration.
- **T3:** the title and payment clauses for the first real structure (corridor pilot, D7). These come from the term sheet, with the client's consent.

**After Part B, stop.** Show JML the diff of the brief and a list of every disagreement you found between this prompt and the code. Start no migration until JML says "go Step 3".

## Part C — after "go Step 3"

Build B1–B6 in the B6 order, keeping the stop before SETTLED. After each sub-step, report as the brief's *Reporting* section asks:
- the measured test counts and head;
- a handoff §8 item;
- gap register updates: G-11, G-23, G-24, plus the new partial-acceptance gap.
