# Ecosystem Navigator — Data Structure Review

**Date:** 2026-09-16
**Status:** review — companion to `docs/news-to-project-truth-pipeline.md`
**Source reviewed:** `Data_structure_local.docx`, six layers, five field dictionaries
**One line:** the document asks one explicit question — can we tell that the
ingested project and the user's project are the same, and override the newer one —
and the answer is that you can tell, you already partly do, and you must not
override.

**Everything below marked *measured* was checked against the working tree on
2026-09-16.** The tree contains more of this feature than the document assumes,
and it contains one live matching rule that will merge unrelated projects the day
real data lands.

---

## 1. What is already built — measured, not remembered

| # | Finding | Location |
|---|---|---|
| 1 | **The map has no data.** Both source arrays are stubbed to `[]` | `frontend/src/lib/ecosystem/mockData.ts`, `observatoryData.ts` |
| 2 | **Publish-to-map is already built** and wired into the plant builder UI | `PlantBuilder.tsx:61-65, 635-742` |
| 3 | **It persists to `localStorage` only** — keys `gex_ecosystem_user_projects`, `gex_ecosystem_enrichments`. No backend call | `userProjects.ts:16-17, 48-53` |
| 4 | **A matcher already exists** — a four-rule deterministic cascade, first match wins, no confidence score | `userProjects.ts:165-227` |
| 5 | **It already chose attach-over-overwrite** — "we ATTACH user-supplied enrichments instead of duplicating the marker" | `userProjects.ts:6-8` |
| 6 | **Field-level publication consent already exists** — `visibleFields` lets the user pick what is exposed | `userProjects.ts` (`ProjectEnrichment`) |
| 7 | **35 ecosystem rights registered; 27 at `PUBLIC` access tier**, 7 privileged, 1 stakeholder | `backend/app/core/permission_engine.py:121+` |
| 8 | **`EcoProject` declares itself "the API contract for all project data ingestion"** and is referenced by nothing outside its own directory — not the backend, not even the plant builder | `frontend/src/lib/ecosystem/types.ts:3, 27` |
| 9 | **The plant builder does not produce Layer-1 data.** It is an equipment/costing engine — `EquipmentItem`, `PlantConfiguration`, capacity factor, cert readiness | `backend/app/core/plant_builder.py:52-337` |

Findings 3, 8 and 9 together mean the Layer 0 step-2 path in the document does
not yet do what the document says it does. "Shared to ecosystem map" currently
means *visible in the browser that created it*. Nothing reaches another user,
another device, or the backend.

Finding 9 is the larger gap. The document treats the plant builder as the entry
form for the Layer 1 field set — project name, location, maturity stage, press
releases, contacts. The plant builder as built takes an equipment configuration
and returns capex and certification readiness. It holds almost none of the Layer 1
fields. Either a new project-details form is needed, or Layer 1 needs to be
explicit that most of it comes from ingestion and only a slice from users.

---

## 2. The document's own question, answered

> *"A project can already exist from step 1, then a user modifies/improves the same
> project with 2 — can we identify that the project from 1 and 2 are the same and
> override the most updated version?"*

Three separate questions are folded together here. They have different answers.

**Can we identify that they are the same?** Partly, and better than the current
code does. The four-rule matcher in §3 is too loose in two rules and too strict in
one. §3 replaces it with the scored approach from the pipeline spec.

**Should the user's version override the ingested one?** **No** — and the code
already agrees with this, which is the most useful thing in the tree. Override
destroys the third-party reading. Keeping both is what makes the disagreement
visible, and the disagreement is the product. If a developer publishes 100 kt/yr
and the IEA database says 60 kt/yr, a platform that shows one number has thrown
away its only interesting signal.

**Should "most updated" decide?** **No.** Recency is not authority. Last-write-wins
across merged sources means a stale press release overwrites a fresh regulatory
filing whenever the release is scraped second. The document's provenance model —
a single `Source` free-text field of 60 characters plus one `Last Updated`
timestamp — can express nothing else, because it has nowhere to record who said
it or how strong they are.

**What to do instead.** Attach, and resolve on read. Each layer keeps every
assertion with its asserting party, authority tier and timestamp. The map displays
the winner under a stated precedence rule, and a click shows the alternatives. The
tenant's own published assertion wins for their own project on descriptive fields
— they know their own plant name and address — and does **not** automatically win
on promotional fields, which are capacity, COD and anything about offtake or
finance, because a promoter is an interested party on exactly those.

That split is the whole answer, and it needs one column the document does not
have: **who is asserting, and are they interested.**

---

## 3. The live matcher will merge unrelated projects

*Measured at `userProjects.ts:165-227`.* Four rules, evaluated in order, first
match wins, no score, no review band.

| Rule | Condition | Assessment |
|---|---|---|
| 1 | Exact normalised name | **No location check.** Two projects named "Green Hydrogen Project" on different continents merge. Generic names are the norm in this sector. |
| 2 | Name substring either direction AND same molecule | **Substring either way is dangerous.** A short pool name substring-matches almost everything, and it has no notion of which words carry identity. |
| 3 | Name overlap AND ≤ 25 km | **Merges on a molecule contradiction.** It only runs when rule 2 did not, and rule 2 fires whenever molecules agree — so rule 3's live cases are "molecule unknown" and "molecules differ". 25 km is also the loosest radius of the three despite having the least evidence behind it. |
| 4 | **Same molecule AND ≤ 5 km, no name test at all** | **The false-merge bug.** |

Rule 4 attaches a user's plant to a stranger's project because both make hydrogen
and both sit within 5 km. That is a description of every industrial cluster in
Europe — Rotterdam, Antwerp, Duisburg, Humber. The document's own Layer 1 has
`Site Environment: Industrial Cluster` as a look-up value, so the schema
anticipates exactly the conditions under which this rule misfires.

**This bug is latent, not active.** The candidate pool is
`verifiedProjects + observatoryProjects`, both measured empty, so the matcher
returns `null` today and every publish creates a fresh marker. It activates on the
day the first CSV lands, which is the day nobody will be looking at this function.

**Fixed in `frontend/src/lib/ecosystem/userProjects.ts`** over three passes —
rules 1 and 4 on 2026-09-16, then rule 2, then rule 3 on 2026-09-17. All four
rules of the cascade have now been tightened. Rule 4 now
requires the **same owner** in addition to molecule and proximity, which keeps its
legitimate purpose — catching one project filed under two names — while removing
the cluster false-merge. Rule 1 now requires location to **positively support** the
match: distance within 50 km where both sides have coordinates, otherwise
agreeing countries, otherwise no match.

A third change was needed to make the first two hold. An exact name is also a
substring, and rule 2 has no distance test, so a candidate rejected by rule 1 on
location fell straight through to rule 2 and merged anyway. Candidates whose
location **positively contradicts** the input are now filtered out ahead of the
whole cascade. "Unknown" is not a contradiction — only evidence that actually
places a project elsewhere excludes it.

Owner comparison is normalized equality, never substring: substring matching on
company names is how unrelated companies merge. Normalization strips legal-form
suffixes and transliterates the letters NFD does not decompose, so `Ørsted A/S`
and `Orsted AS` agree. Without that, `Ørsted` normalized to `rsted`.

Ten regression tests in `src/lib/ecosystem/__tests__/userProjects.match.test.ts`,
all three guards negative-verified by reverting each and confirming the relevant
tests fail. The candidate pool is mocked, because it ships empty.

**Rule 2 fixed 2026-09-16**, in a second pass. The two-way substring test is
replaced by distinctive-token overlap. Names are split into tokens; generic
sector vocabulary is discarded — `project`, `plant`, `green`, `hydrogen`,
`power`, `phase` and so on, roughly sixty words — and what remains must
intersect and cover at least half of the shorter name's distinctive tokens. A
name with no distinctive tokens matches nothing, which is right: it identifies
nothing. Molecule words are in the discard list deliberately, because rule 2
already compares molecule and would otherwise count the same evidence twice.

Three things this fixed that substring could not express:

- a project literally named `H2` no longer captures every input containing `h2`
- `hydro` no longer matches `hydrogen`
- two differently-worded but equally generic names no longer match each other

**A second cascade-wide guard came out of it.** Phase 1 and Phase 2 of one
development share an owner, a molecule and a location to within a few hundred
metres, so rule 4 merged them even after rules 2 and 3 declined. Conflicting
ordinals — digits or roman numerals, and only when **both** names state one —
now exclude a candidate ahead of every rule, exactly as a contradicting location
does. One side being silent is not a conflict: "NEOM Helios" may well be that
project's phase 1.

Two parsing traps were found while testing and are pinned by tests. `Power-to-X`
and `PtX` are ubiquitous here, so reading that `X` as roman ten made every
Power-to-X project look like a different phase from every numbered one; `x` is
excluded from the numeral set. And `to` was counting as a distinctive word.

**Rule 3 fixed 2026-09-17**, in a third pass, and the diagnosis is the same shape
as the other two: a rule that fires only in the cases an earlier rule rejected
inherits a meaning nobody chose for it. Rule 3 runs only when rule 2 did not, and
rule 2 fires whenever the molecules agree — so rule 3's live cases were exactly
"molecule unknown on one side" and "molecules known and different". It merged
both. The second is a false merge: a methanol plant and an ammonia plant sharing
a site and a site name are two projects, and that is the normal shape of a
developer's cluster.

Rule 3 now requires the molecule to be **unknown** on at least one side, and its
radius drops from 25 km to 10 km. It carried the least evidence of the three
proximity rules — no molecule agreement, no owner agreement — while having the
widest radius. 25 km spans a whole port complex.

Here a rule-local guard is sufficient, unlike the location and ordinal cases. The
only rule after it is rule 4, which requires the molecules to be **equal**, so
nothing downstream can re-merge what rule 3 declines. A test pins that, because
the reasoning rather than the code is what guarantees it.

**Candidate selection was also arbitrary.** Rule 2 took the first hit and rule 3
took the nearest, so the result depended on the order the two pool arrays happen
to be concatenated in. Both now rank by name-overlap strength, then distance.

**Still open.** Replacing the whole cascade with the scored matcher and the three
confidence bands from the pipeline spec remains the real fix — the rules are
tightened but still binary, with no medium band and no human review. Two
behaviours must carry over when that happens: attach rather than overwrite, and
keep the human-readable `reason` string the current code already produces, now
naming which words matched.

One property worth knowing before that work: name overlap is scored by
containment, dividing by the *shorter* name's token count, so a one-word
distinctive name scores 1.0 against any longer name containing it. That is honest
for containment and is bounded by the location and molecule guards, but it means
the score cannot discriminate between candidates when the input name is a single
distinctive word.

---

## 4. Four vocabularies for the same concepts

The doctrine already names vocabulary entropy as a standing problem. This feature
adds a fourth and fifth instance before it ships.

**Production pathway**

| Source | Values |
|---|---|
| `Data_structure_local.docx`, Layer 1 §4 | Synthetic, Biogenic, Fossil, Mixed, Other |
| `frontend/src/lib/ecosystem/types.ts` | Synthetic Pathway, Biogenic Pathway, Thermochemical Pathway, Hybrid Pathway, Physical Recovery Pathway |

Neither is a superset. The document has Fossil, Mixed and Other; the code has
Thermochemical, Hybrid and Physical Recovery. Nothing maps.

**Lifecycle status**

| Source | Values |
|---|---|
| Document, Layer 1 §3 Maturity Stage | Concept, Pre Feasibility, Feasibility, FEL 1, FEL 2, FEL 3, Permitting, Pre FID, FID, Construction, Commissioning, Operating — **12, and no cancelled** |
| `types.ts` `ProjectStatus` | operational, construction, planned, concept, cancelled — **5, including cancelled** |
| Document, Layer 4 Pipeline | Operating, Under Construction, Planned, Dormant, Decommissioned |
| `routes_project_truth.py` | G0–G11 gate ladder |

Four ladders. The document's Layer 1 ladder has no terminal failure state at all,
so a cancelled project cannot be recorded as cancelled — it simply stops updating.
The pipeline spec's §8.4 requires cancellation to be expressible; Layer 1 as
specified cannot express it.

**Product**

The document's Main Product look-up is two lists in one field:

> Hydrogen, Ammonia, Methane, Methanol, Diesel, Kerosene, Ethanol, Gasoline
> (H₂, NH₃, e-NH₃, e-MeOH, e-CH₄, SAF, HVO, e-Naphtha, e-Gasoline, e-LG)

The parenthetical is not a gloss on the first list. It adds SAF, HVO, e-Naphtha
and e-LG, which the names list lacks, and drops Diesel and Ethanol, which it has.
`types.ts` `MoleculeType` is a *third* list with propane, butane, lpg and naphtha.
Separately, the `e-` prefix encodes pathway inside the product name, which the
Production Pathway field already encodes — so a synthetic methanol project has two
places to say the same thing and they can disagree.

**Ruling needed.** One canonical product vocabulary, molecule only, with pathway
kept in the pathway field. `e-MeOH` is `methanol` + `Synthetic`. `SAF` is not a
molecule at all — it is an end use, and the document already has an End Use field.

**Data source / provenance**

| Source | Values |
|---|---|
| Document, every layer §"Data Source" | free text, 60 chars |
| `types.ts` `DataSource` | verified, observatory, generated |
| Pipeline spec §7.1 | T1–T5 authority register |
| `evidence_ledger.py` | `verification_state` and `claim_state`, two separate axes |

The document's note — *"Source can be user verification if added through the plant
builder or verified from the GeoMap"* — puts **who said it** and **whether it was
checked** in the same 60-character field. Those are two axes, and the evidence
ledger already separates them deliberately. Collapsing them means you cannot
express "the developer said it and nobody has checked", which is the state most
map data will actually be in.

---

## 5. One-to-many declared in prose, one-to-one in schema

Four places where the document's notes contradict its own field definitions.

| Field | Note | Schema as written |
|---|---|---|
| Main Product | *"User can add as many Main Product and By-product as he has and declare every time the capacity for each"* | one `Main Product` + one `Capacity` + one `Unit` |
| End Use | *"User can have more than one End Use per Product"* | one `End Use`, 60 chars |
| Press Release | *"User can add as many links as he wants"* | one link field, 1000 chars |
| Partners | *"User can add more than one partner"* | one field, 200 chars |

All four need child tables. Products especially: a project making hydrogen *and*
ammonia with different capacities cannot be represented, and that configuration is
common — ammonia plants that also sell merchant hydrogen, methanol plants selling
by-product oxygen.

A 200-character comma-joined partner list is also the entity-resolution problem
recreated at the field level. The pipeline spec compares partners; it cannot
compare a delimited string.

---

## 6. Identity — the gap under everything else

**No dictionary defines a key.** Not Layer 1, not any of the four infrastructure
dictionaries. Every layer starts with `Project Name; mandatory: yes` and stops. So:

- identity is the name, therefore a rename is a new project
- `Organization Name; alphanumeric; length: 60` is free text in all five layers,
  so "Ørsted", "Orsted A/S" and "Ørsted A/S" are three different developers
- the pipeline spec's §5.2 weights developer identity at 0.30 and requires
  *"resolved entity identity, not string match"* — unbuildable against this schema

**And no layer links to any other.** Layer 2 is defined as *"Infrastructure
elements contributing to the success of production plants defined in layer 1"* —
but no infrastructure dictionary has a field pointing at a Layer 1 project. The
relationship the definition asserts is not representable. The flowchart's C3 box,
"create / link asset", has nothing to write into.

Three tables close this:

```sql
CREATE TABLE organizations (
    org_id        TEXT PRIMARY KEY,
    legal_name    TEXT NOT NULL,
    country       TEXT,
    registry_id   TEXT,          -- LEI / company number where known
    verified      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE organization_aliases (
    org_id   TEXT NOT NULL,
    alias    TEXT NOT NULL,      -- every spelling ever seen, incl. news variants
    source   TEXT,
    PRIMARY KEY (org_id, alias)
);
CREATE TABLE project_assets (             -- the missing Layer 1 ↔ Layer 2-5 edge
    project_id   TEXT NOT NULL,
    asset_id     TEXT NOT NULL,
    asset_layer  TEXT NOT NULL,           -- POWER | CCUS | PIPELINE | PORT
    relation     TEXT NOT NULL,           -- SUPPLIES_POWER | OFFTAKES_CO2 |
                                          -- EXPORTS_VIA | CONNECTED_TO
    asserted_by  TEXT NOT NULL,
    confidence   REAL,
    PRIMARY KEY (project_id, asset_id, relation)
);
```

`organization_aliases` is what makes developer matching work, and it is also where
the news pipeline puts every spelling it encounters — the same census-then-sign
pattern `corpus_taxonomy_map` already uses.

---

## 7. Field-level defects

### 7.1 COD is mandatory and cannot be known

Layer 1 §3: `Commercial Operation Date (COD); mandatory: yes`, while §3's own
Maturity Stage look-up begins at **Concept**. A concept-stage project has no
commercial operation date. Mandatory means every concept project gets an invented
one, and an invented date is indistinguishable from a real one once stored.

The CCUS dictionary marks COD `mandatory: no`. The two dictionaries disagree about
the same field.

**Fix.** COD is optional, and carries a qualifier: `target`, `announced`,
`contracted`, `achieved`. A COD is a different kind of fact before and after it
happens, and the pipeline spec's decay clock needs the distinction.

### 7.2 Units

Three separate problems.

- **`Unit; alphanumeric; length: 30; data_type: real`** — a unit *label* is a
  string. `data_type: real` is a copy-paste from the Capacity line above it, and
  it repeats on the by-product Unit field.
- **`unit_family: MASS_PER_TIME` cannot express the By-Product list**, which
  includes **Electricity** and **Heat**. Those are energy per time. Any by-product
  row for electricity has no valid unit under the declared family.
- **Capacity is optional while Unit is optional independently**, so a bare number
  with no unit is a legal row. The pipeline spec forbids a numeric claim with a
  null unit from ever being corroborated, and this platform has already been bitten
  by kilogram-versus-tonne and by MTPD ambiguity in the billing path.

`EcoProject.capacity?: string` in the frontend is the same problem in its worst
form — `"100 MW"` and `"50 kt/yr"` in one free-text field, with no way to validate
or compare. Note the frontend's own `ProjectEnrichment` already does this correctly
with `capacityValue` and `capacityUnit` alongside the label. Two representations of
capacity coexist in one module; keep the split one.

### 7.3 Investment has no currency and no date

`Investment; numeric; length: 15; unit_family: COST`. €500M announced in 2021 is
not €500M in 2026, and the field cannot say which currency it is. Needs amount,
currency, and a reference date. Same trap as capacity, higher stakes.

### 7.4 CCUS storage types are hydrogen storage types

Layer 3 §3: *Underground Storage, Above-Ground Gaseous Storage, Solid-State
Storage, Chemical Storage*. Those are the storage classes for **hydrogen**. CO₂
storage classes are saline aquifer, depleted oil or gas field, enhanced oil
recovery, and mineralisation. The look-up appears to have been copied from a
hydrogen dictionary — consistent with the dictionary citing
`Hydrogen Infrastructure Database - September 2025.xlsx` as its source.

Compounding it: `Capacity; unit: MtCO2/yr` is an **injection rate**, not a storage
capacity. Total storage capacity in Mt is a different quantity, and a CCUS project
needs both — the rate governs how much a plant can send per year, the total governs
how long the site lasts.

### 7.5 Look-up tables are live Google Sheets

Country, Technology and End Use all point at `docs.google.com` spreadsheet URLs.
For production controlled vocabulary this means: no version, no signature, no
offline copy, no audit of who changed a value, editable by anyone holding the link,
and a hard dependency on an external service being reachable at ingest time.

The adjacency corpus already establishes the alternative and enforces it —
unmapped labels quarantine rather than guess, and a human signs each mapping. Pull
these three sheets into versioned reference tables, keep the sheet as the editing
surface if that is convenient for whoever maintains them, and import on a signed
snapshot with a retrieval date.

### 7.6 Personal data on a public surface

Layer 1 §8 and §9 collect `Organization Email`, `Organization Telephone`,
`Contact Name`, `Contact Email`, `Contact Telephone`. The ecosystem map is a public
surface by design — measured, 35 registered rights of which 27 sit at `PUBLIC`
access tier in `permission_engine.py`, including map view, layer switching and
marker filtering.

A named individual's direct email and telephone on a public map is a personal-data
disclosure and needs a lawful basis. Two rules follow, and neither is optional:

1. **Contact details never flow from the news pipeline.** A person named in a press
   release has not consented to appear in a contact directory. Class C provenance
   must be barred from writing these fields.
2. **Contact details default to private** and surface only through the existing
   `visibleFields` consent mechanism, set by the publishing tenant. That mechanism
   is already built and is the right place for this.

Also: `Contact Email; length: 40` versus `Organization Email; length: 100`. Forty
characters rejects many legitimate addresses. And telephone numbers are declared
`numeric` in three places, which destroys leading zeros and `+` country codes.
Telephone is a string.

### 7.7 Smaller items

| Item | Issue |
|---|---|
| Certification Phase | ends `"Surveillance Other"` — one value or two with a missing comma? |
| `Project Lifetime; numeric; length: 3` | no unit stated; presumably years |
| Power plant `Efficiency; unit: %` | no basis — LHV or HHV, and on a CHP, electrical or total? |
| Pipeline §2 "Project Location" | heading present, **no fields** — and a pipeline is a route with two endpoints, not a point |
| Port mandatory fields | City, Longitude and Latitude mandatory for Port only; no stated reason for the inconsistency |
| Power Plant, CCUS | no status or maturity field at all — a cancelled power plant cannot be recorded as cancelled |
| Layer numbering | contents page nests CCUS/Pipeline/Port under Layer 2; body makes them Layers 3, 4, 5 |
| Source file names | Pipeline and Port dictionaries both cite `ccus.csv`; "Infrastracture" typo in two places |
| `"an SEO agent"` | search-engine optimisation is not research. The thing described is the pipeline in the companion spec; the name will mislead whoever picks up the ticket |

---

## 8. What the corrected structure looks like

Only the parts that change. Field lists from the document carry over unless named
above.

```sql
-- Identity, shared by every layer -------------------------------------------
-- organizations / organization_aliases / project_assets as in §6

CREATE TABLE eco_projects (                  -- Layer 1
    project_id      TEXT PRIMARY KEY,        -- stable; NOT the name
    canonical_name  TEXT NOT NULL,
    org_id          TEXT NOT NULL REFERENCES organizations(org_id),
    provenance      TEXT NOT NULL,           -- CLASS_B_PUBLISHED | CLASS_C_EXTERNAL
    tenant_id       TEXT,                    -- set only for CLASS_B
    country         TEXT NOT NULL,
    lat             REAL,  lng  REAL,
    maturity_stage  TEXT,                    -- one canonical ladder, incl. CANCELLED
    stage_since     TEXT,
    lifecycle_state TEXT NOT NULL DEFAULT 'ACTIVE'   -- ACTIVE | CANCELLED | DORMANT
);

CREATE TABLE eco_project_names (             -- rename does not break identity
    project_id TEXT NOT NULL, name TEXT NOT NULL,
    is_canonical INTEGER NOT NULL DEFAULT 0, source TEXT,
    PRIMARY KEY (project_id, name)
);

CREATE TABLE eco_project_products (          -- §5: one-to-many, per product
    project_id    TEXT NOT NULL,
    role          TEXT NOT NULL,             -- MAIN | BY_PRODUCT
    molecule      TEXT NOT NULL,             -- canonical molecule only, no e- prefix
    pathway       TEXT,                      -- the e- lives HERE
    capacity_value REAL,
    capacity_unit  TEXT,                     -- mandatory whenever value is present
    unit_family    TEXT NOT NULL,            -- MASS_PER_TIME | ENERGY_PER_TIME | VOLUME_PER_TIME
    basis          TEXT,                     -- nameplate | annual_output | MTPD
    PRIMARY KEY (project_id, role, molecule)
);

CREATE TABLE eco_project_end_uses (          -- §5
    project_id TEXT NOT NULL, molecule TEXT NOT NULL, end_use TEXT NOT NULL,
    PRIMARY KEY (project_id, molecule, end_use)
);

CREATE TABLE eco_project_partners (          -- §5, resolved not delimited
    project_id TEXT NOT NULL,
    org_id     TEXT NOT NULL REFERENCES organizations(org_id),
    role       TEXT,                         -- EPC | TECHNOLOGY | OFFTAKER | FINANCIER
    PRIMARY KEY (project_id, org_id, role)
);

CREATE TABLE eco_project_links (             -- §5, press releases and sources
    link_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
    url TEXT NOT NULL, link_type TEXT NOT NULL,   -- PRESS_RELEASE | WEBSITE | FILING
    published_at TEXT, retrieved_at TEXT
);

CREATE TABLE eco_project_cod (               -- §7.1, a COD is a qualified fact
    project_id TEXT NOT NULL, cod_date TEXT NOT NULL,
    qualifier TEXT NOT NULL,                 -- target | announced | contracted | achieved
    asserted_by TEXT NOT NULL, asserted_at TEXT NOT NULL,
    PRIMARY KEY (project_id, cod_date, qualifier, asserted_by)
);

CREATE TABLE eco_project_contacts (          -- §7.6, private by default
    project_id TEXT PRIMARY KEY,
    contact_name TEXT, contact_email TEXT, contact_phone TEXT,   -- phone is TEXT
    visible_fields TEXT NOT NULL DEFAULT '[]',   -- tenant consent, existing mechanism
    source_class TEXT NOT NULL                   -- CLASS_B only; CLASS_C barred
);

CREATE TABLE eco_investment (                -- §7.3
    project_id TEXT NOT NULL, amount REAL NOT NULL,
    currency TEXT NOT NULL, as_of_date TEXT NOT NULL,
    asserted_by TEXT NOT NULL,
    PRIMARY KEY (project_id, asserted_by, as_of_date)
);
```

Every table carrying an assertion takes `asserted_by`, and every asserting party
resolves to the authority register in the pipeline spec. That single column is
what makes §2's answer implementable.

---

## 9. Build order

Ordered by what unblocks what, not by size.

1. ~~**Tighten the matcher cascade.**~~ **Done.** All four rules. Twenty-two tests
   in `src/lib/ecosystem/__tests__/userProjects.match.test.ts`; every guard
   negative-verified by reverting it and confirming the relevant tests fail.
   See §3.
2. **Move publication off `localStorage` to the backend.** Until then the feature
   does not do what it claims, and no amount of schema work matters. This is now
   the most urgent item.
3. **Settle the four vocabularies** — pathway, lifecycle, product, provenance. One
   canonical list each, with the `e-` prefix removed from products. Everything
   downstream encodes these, so changing them later is expensive.
4. **Organizations and aliases.** Unblocks developer matching, which is the
   heaviest weight in the pipeline spec's scorer.
5. **Child tables for the four one-to-many fields.**
6. **`project_assets`** — the missing Layer 1 ↔ infrastructure edge.
7. **`asserted_by` and the authority register**, which is where this document and
   the pipeline spec converge.
8. **Then ingestion**, per the pipeline spec.

Step 1 is done. Step 2 is the remaining urgent one: it is what makes the feature
real, and every later step assumes a server-side store exists.

---

## 10. Decisions this review cannot make

1. **Does a tenant's published assertion outrank an ingested one on descriptive
   fields?** §2 proposes yes for descriptive, no for promotional. The split point
   between those two sets is a product judgement.
2. **Who maintains the three Google Sheets**, and will they accept a signed
   snapshot process? §7.5 assumes they will.
3. **Is there a lawful basis for publishing contact details?** §7.6 states the
   constraint, not the answer. This one probably needs counsel rather than
   engineering.
4. **Does Layer 1 get its own project-details form**, or does the plant builder
   grow one? Finding 9 in §1 says one of the two must happen.
