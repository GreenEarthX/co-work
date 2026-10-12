# GEX gates — first-use comprehension test

A facilitator script for testing whether a capable professional who has never used GEX can
read the gates correctly and act on them. Written 30 Sep 2026 against evidence rules 4.1.0.

**This tests understanding, not integrity.** Whether a user can push an unsupported PASS
through the system is tested by the adversarial libraries (see
`docs/adversarial/2026-09-30_attack_A_producer_advance.md`). Here, the question is whether an
honest, intelligent newcomer reads the screens correctly, quickly, and with justified confidence.

## Who

- **3–5 participants per round.** Five sessions find most comprehension problems; three are
  enough for a first round.
- **Mix the roles:**
  - a finance professional (credit or project-finance analyst, investor), a Bloomberg user;
  - a plant or process engineer, a Simatic / process-control user;
  - an energy trader or portfolio manager, an EnergyHub or ETRM user;
  - optionally an offtaker's procurement lead.
- **Exclude** anyone who has seen GEX before, and GEX staff.

## Before the session

1. **The reference project is loaded** (JML's decision, 2026-10-02: a labelled TEST project in
   the development database, rather than a restored throwaway copy). It is
   `proj_TEST_gates_reference`, "TEST — Gates Comprehension Reference (synthetic)", owned by the
   HamburgOne demo tenant. Re-check or reload it with:

   ```bash
   cd backend && python scripts/load_comprehension_test_project.py --verify    # engine vs key
   python scripts/load_comprehension_test_project.py --execute                 # reload
   python scripts/load_comprehension_test_project.py --remove --execute        # delete it
   ```

   The live projects cannot be used instead: every one sits at Speculative with nothing
   verified, which makes the tasks trivial.
2. **The answer key** (Appendix B) was computed by the engine for exactly that state, and
   `--verify` checks the two still agree — it found a real fixture bug the first time it ran.
   If you change the state, recompute it; never write answers by hand.
3. **Accounts: every participant signs in as a HamburgOne account**, whatever their own
   profession — the producer executive (Lisa Friedrich) for the walkthrough. A runtime project
   grants nothing to other companies at the ABAC level, so the bank, insurer and offtaker demo
   accounts cannot open this project; a banker participant reads the same screens from the
   producer's side. Say so at the start, so nobody reads it as the software hiding a lender view.
4. **Kit:** screen and audio recording (with consent), a facilitator, a note-taker, and the
   scoring sheet (Appendix C).

## Rules for the facilitator

- Read each task **verbatim**. Never explain a term, a screen or a number.
- If asked what something means: *"What would you expect it to mean?"* Then note the answer.
- Ask them to think aloud. Do not confirm or deny answers during the session.
- Time each task from the end of the question to the final answer, stopping at the time limit.
- After every task ask: *"How confident are you, 1 to 5?"* and *"Where did you find that?"*
- Note every term the participant misreads, **verbatim**.

## Session plan (50 minutes)

| Min | Part | Script |
|---|---|---|
| 0–3 | Welcome and consent | "We are testing the software, not you. There are no wrong answers. Please think aloud." |
| 3–5 | Background | "What is your role? Which tools do you use every day? How do you track whether a project is ready for the next step today?" |
| 5–10 | First look | "Please log in and look around for five minutes. Tell me what you think this software is for, and who it is for." No tasks. Note the words they use. |
| 10–35 | Tasks T1–T8 | Below. |
| 35–40 | Own words | "In your own words, what is a *gate*? A *state*? What does *Commercially plausible* mean? *O2*? *Data missing*? *Eligible*?" |
| 40–45 | Trust | "Which number on these screens would you rely on? Which would you not show your committee? Why?" |
| 45–50 | Questionnaire, close | System Usability Scale (Appendix C), then: "What one change would help most?" |

## Tasks

Each task gives the question as read aloud, the time limit, the correct answer (from Appendix B),
what counts as partial, and what to watch for.

### T1 — Where does the project stand? (3 min)

> "Where does this project stand today? One sentence, and why."

- **Success:** Technically plausible (site and technology basis confirmed). Not yet commercially
  plausible, because offtake terms cover 55% of planned output and 60% is needed.
- **Partial:** the right state, a wrong or missing reason.
- **Fail:** quotes the project phase ("FEED") or a rating or score as the status.
- **Watch:** the project carries a *phase* (FEED), a *state* (Technically plausible) and, on
  other screens, a rating. Which one does the participant take as "where it stands"?

### T2 — What must happen next? (3 min)

> "What is the single most important thing the developer must do next, and how would they know
> it worked?"

- **Success:** get offtake terms (heads of terms or better) for at least 60% of planned output,
  i.e. at least 30,000 of 50,000 t/yr, which means one or more term sheets for at least a further
  2,500 t/yr. They would know because the state moves to Commercially plausible.
- **Partial:** "get a binding offtake". Not wrong, but it overshoots what this step needs.
- **Fail:** anything about construction, the rating, or items of later gates.

### T3 — Which capital? (3 min)

> "Which kinds of funding can this project approach now, and which not yet? And what does
> 'eligible' mean here?"

- **Success:** Grants & TA, Seed / VC / Angel and Strategic Equity are eligible, because gates
  G0, G1 and G3 are satisfied. Project equity is not yet eligible (G4), nor is any debt.
  "Eligible" means the capital provider may consider the project; GEX does not commit or release
  money.
- **Watch:** Strategic Equity is eligible although the project is not yet Commercially
  plausible, because eligibility follows each gate, not the state. Does that confuse? Does
  "unlocked" wording lead them to think money is available?

### T4 — What would you report? (3 min)

> "Your investment or credit committee asks for one status line on this project. What do you
> write, and which screen is it from? How confident are you, 1 to 5?"

- **Success:** the state and its blocker, taken from the gate screen. For example: "Technically
  plausible; commercial plausibility blocked by offtake coverage, 55% of the 60% needed; one
  supply inconsistency open."
- **Fail:** a rating, score or percentage given as the status (e.g. "BB", "63", "52%").
- **Why it matters:** this task measures whether the screens give one answer or several.
  A confidently wrong answer here is the most dangerous outcome of the whole test.

### T5 — How strong is the buyer's commitment? (3 min)

> "How strong is the buyer's commitment today, and what would make it strong enough for a bank?"

- **Success:** O2, heads of terms or term sheet: commercial fit, not binding, 55% of output.
  Next it needs a binding commitment with conditions and a longstop (O4, needed at G4). A lender
  under project finance needs, at Financeable, a firm, effective offtake with the lender
  protections (O7).
- **Partial:** "not binding yet" without the path.

### T6 — Is anything inconsistent? (3 min)

> "Is anything in this project's commitments inconsistent? Where does the software say so?"

- **Success:** check C6 fails, supply shorter than sales. Feedstock covers 60,000 of 70,000 t/yr
  and runs 8 years against a 10-year offtake. It blocks G4.
- **Watch:** eight checks show "data missing". Does the participant count those as failures?
  (T8 asks directly.)

### T7 — What if the buyer signs? (4 min)

> "Suppose the buyer signs a binding agreement for 70% of output: take-or-pay, investment-grade
> buyer, with conditions precedent and a longstop date. What changes on the screen, and what
> does not?"

- **Success:** the state moves to Commercially plausible, and the offtake rises to O6 (firm,
  creditworthy) but **not effective**: the conditions are outstanding. G4 stays blocked by the
  supply inconsistency (C6) and its other items. No new capital becomes eligible, because Project
  Equity needs G4.
- **Partial:** says the project becomes Buildable. This overshoots: G4 and G5 are still open.
- **Watch:** "firm" versus "effective". An O6 can still be conditional.

### T8 — Missing is not failed (2 min)

> "Several checks say 'data missing'. Does that count against the project?"

- **Success:** no. Missing data never blocks and never counts as a pass; it means the terms
  have not been recorded. Only a failed check blocks its gate.

### Persona probes (one per participant, optional, 2 min)

- **Finance (Bloomberg):** "Pick any figure on this screen. Where are its source and its as-of
  date?"
- **Engineer (Simatic):** "Which of these stop progress, like an interlock, and which are only
  warnings?" (Blocking gates and failed checks stop progress; "watch" items and missing data do
  not.)
- **Trader (EnergyHub):** "What share of this project's output is contracted, and what share is
  open?" (55% under terms; 45% open.)

## Measures and the pass bar

For every task: success / partial / fail, time, confidence 1–5, the screens visited, and misread
terms. Flag **confidently wrong** answers (confidence ≥ 4 and fail) separately.

**The gates count as understandable when:**
- at least 80% of the answers to T1–T4 across participants are successes;
- median time on T1–T3 is two minutes or less;
- no participant gives a rating, score or percentage as the status in T4;
- the System Usability Scale averages 68 or more (the published average).

Otherwise, fix what the notes point to and run another round with new participants.

## LLM pre-screen (optional, before real sessions)

A language model can run this script on screenshots to catch obvious problems cheaply. It
**under-reports confusion**, because it already knows the jargon, and it cannot report trust. Use
it to clean up before the sessions, never as the verdict. Prompt:

```text
You are a senior professional who has never used GEX: [a project-finance analyst who uses
Bloomberg daily | a process engineer who uses Simatic PCS 7 | an energy portfolio manager who
uses an ETRM]. You are intelligent, busy and sceptical, and you know nothing about GEX's
vocabulary. Using ONLY the attached screenshots, answer tasks T1–T8 below as that person would.
For each: your answer, which screenshot and which element you used, your confidence 1–5, every
term you had to guess, and anything on screen that contradicted anything else. Do not use
outside knowledge of GEX. If a screen does not tell you, say so.
[paste T1–T8 questions verbatim]
```

## Appendix A — The reference project (synthetic)

`proj_TEST_gates_reference`: e-methanol, grid-connected power, project finance, phase FEED,
planned output 50,000 t/yr. Every item below is VERIFIED; all other items are not started.
Loaded by `backend/scripts/load_comprehension_test_project.py`, which derives the item list
from the running engine so the fixture cannot drift from the rules. Every row carries
`submitted_by = TEST_FIXTURE_COMPREHENSION` — that marker is how you find them, and `--remove`
deletes them by project id. They are synthetic and carry no documents: no row here is a client
submission.

| Gate | Evidence (maturity where the item requires one) |
|---|---|
| G0 | All four items; the lease EXECUTED |
| G1 | Every item that applies to a grid-connected project; PPA term sheet and licensor term sheet INDICATIVE |
| G2 | All six items |
| G3 | All four items; feedstock supply terms INDICATIVE |
| G4 | The offtake document only, at INDICATIVE (heads of terms) |
| G5 | FEED complete; the EPC contract at INDICATIVE (a priced proposal) |

Commitment cards:

| Card | Fields |
|---|---|
| Offtake | counterparty "TEST Buyer"; planned output 50,000 t/yr; contracted 27,500 t/yr; take-or-pay, 70%; tenor 10 years; buyer investment-grade |
| EPC | contracting model lump-sum turnkey; guaranteed capacity 50,000 t/yr; expected availability 90% |
| Supply | feedstock required 70,000 t/yr; contracted 60,000 t/yr; feedstock tenor 8 years |

For T7, the counterfactual changes three things: the offtake document becomes EXECUTED, the
contracted volume becomes 35,000 t/yr, and a longstop date is recorded (conditions not yet
satisfied).

## Appendix B — Answer key (computed by the engine, rules 4.1.0)

Computed with `pf_engine.core.bankability_engine.evaluate()` for the state above, and confirmed
on 2026-10-02 through the live API (`GET /api/v1/bankability/evaluate`) against the loaded
project: same state, gates, capital, levels, coverage, failing check and 33.7% item completion.
`load_comprehension_test_project.py --verify` re-checks it whenever you need to.

| | Base | Counterfactual (T7) |
|---|---|---|
| State | TECHNICALLY_PLAUSIBLE: "Site and technology basis confirmed" | COMMERCIALLY_PLAUSIBLE: "Commercially defined — offtake term sheets cover most of the output" |
| Blocking the next state | Offtake coverage: "needs offtake terms for at least 60% of output; 55% is covered" | Nothing on the commitments; the next state (Buildable) needs G4 and G5 |
| Gates satisfied | G0, G1, G2, G3 | G0, G1, G2, G3 |
| Capital decisions eligible | Grants & TA; Seed / VC / Angel; Strategic Equity | Unchanged |
| Offtake | O2, coverage 55% of planned output, not effective | O6, coverage 70%, not effective. Not O7: lender protections not verified, tenor not shown against debt, change in law not allocated |
| EPC | E3: not agreed form (contract, licence guarantee, security package, damages schedule) | E3 |
| Coherence checks | C2 PASS; **C6 FAIL** (feedstock 60,000 of 70,000 t/yr; tenor 8 y against 10 y); C7 not applicable; the rest data missing | Same |
| G4 blocked by | Offtake O2 below the O4 G4 needs; C6 failed | C6 failed |
| Overall item completion | 33.7% | 34.8% |

## Appendix C — Scoring sheet and questionnaire

Per participant, per task: task · success / partial / fail · time (s) · confidence 1–5 ·
screens used · misread terms (verbatim) · notes.

**System Usability Scale** (Brooke, 1996; free to use). Ten statements, each scored 1 (strongly
disagree) to 5 (strongly agree):
1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

Score: for odd items subtract 1; for even items subtract the score from 5; sum and multiply by
2.5 (0–100).

**One trust question:** "Would you put a number from this software in front of your committee
without checking it elsewhere?" (yes / only some / no, and why)
