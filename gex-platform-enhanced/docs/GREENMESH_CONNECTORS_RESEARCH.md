# Registry and scheme connectors — interface research (Phase 2 Step 6)

**Restructured on 15 Nov 2026.** The sections below are the current findings. Each was checked
against its source. The superseded claims of 13 Nov and of the earlier 15 Nov reads are not kept in
the body: they are listed in the *Change log*, with what replaced them and why.

The brief's rule stands: write down the interface and its source before writing code, and do not
invent field names. The field-level mapping is in `docs/GREENMESH_CONNECTOR_FIELD_MAPPING.md`
(v0.3, 16 Nov, a draft for JML; §1 tracks identifier scope as research, §10 the acceptance cases).

## Current findings

| Source | Version, date | What it covers | Public without a login | Needs an account, onboarding or a contract |
|---|---|---|---|---|
| **AIB EECS SD03 HubCom** | Release **9.1**, 25 Mar 2026 (151 pages) | The hub's message rules and the element and field definitions for schemas **v80** (valid until the end of October 2027) and **v81** (from its implementation in the hub). Carriers: **Electricity, EnergyGas, Hydrogen**. Two message types only: a certificate transfer (`sendCertificate` / `setCertificate`) and an acknowledgement (`sendFeedback` / `setFeedback`). Transport is AMQP over mutually authenticated TLS, as **AMQP XML or AMQP JSON** (`"certificates": [ certificateBundle … ]`). Signatures use XML-DSig or JWS | **The PDF: yes.** **The XSD files: not obtained.** SD03 (p. 119) says they are downloaded separately from [the CMO-CMO schemes page](https://aib-net.org/eecs/cmo-cmo-schemes), which answered 404 on 15 Nov. It lists `exportenv80.xsd`, `transfers_v81.xsd` (named `exportenv81.xsd` in B3.2.3), `answers_v80/81.xsd`, `statistics_v80/81.xsd` and `accounts_v80/81.xsd` | Connecting to the hub: **registries (issuing bodies) only**, after audit and a Hub Participant Agreement |
| **AIB v81 fields relevant to RFNBO** (in SD03 9.1, read 15 Nov) | v81 | For **EnergyGas and Hydrogen** only (not applicable to Electricity): `BiddingZone` (attributes `zone90percentageRES`, `zoneLowEmission`), `RedispatchingCriteriaMet` ("RFNBO DA Art. 4.3"), `PowerPurchaseAgreement` (`startDate`, `endDate`, `buyerID`). `ProductionPeriod` gains a mandatory `length` (`month`, `day`, `hour`, `30min`, `15min`). Storage and conversion can cite a `cancellationStatement` / `preConversionCancellationStatement` id | Yes | — |
| **AIB cancellation statements** | — | **They do not travel over the hub.** v81 only cites a statement's id. The registry issues the statement to its account holder, in a format per registry | — | The registry and the account holder |
| **UDB Exchange Model** ([`Exchange_Model.pdf`](https://ec.europa.eu/assets/move-ener/udb/COM/Info/APIs/Exchange_Model.pdf)) | **v3.4**, model dated 15 Jun 2026, file created 17 Sep 2026, marked **DRAFT** | One-page class diagram (Enterprise Architect). It produces the XML exchanged "between UDB and service providers" and links the files below | **Yes** | — |
| **UDB XSDs, samples, field specifications** (`…/APIs/EXM_Files/`) | Package **v3.5** (last-modified 17 Sep to 12 Nov 2026) | Three XSDs (`commonTypes/BaseTypes_V1.0.0.xsd`; `udbModel/udbModel_v1.0.xsd`, 219 KB, 187 enumerations; `services/UDBService/udbService_v1.0.xsd`), 112 sample XML files, 34 field-specification xlsx files (one per transaction family), and `.eap`, `.xmi` and Word exports of the model | **Yes**, each answers 200 | — |
| **UDB Technical Connectivity** and **API Connectivity** (public PDFs) | One and two pages | Transport is **eDelivery AS4** (CEF eDelivery), a 4-corner model through Access Points, with only the products on the Commission's [AS4-conformant list](https://ec.europa.eu/digital-building-blocks/wikis/display/DIGITAL/eDelivery+AS4+conformant+solutions). **No REST interface is mentioned.** Responses are **asynchronous**: UDB reads a queue every second. Who may connect: "Member State, Voluntary Scheme, Certification Bodies, Economic Operators and Third-party service providers" | **Yes** | **AS4 onboarding**: an AS4 solution and endpoint, the form `Onboarding UDB Acc.docx`, the Commission's or the party's own PKI (`.pem`), connectivity tests |
| **UDB limits** (Technical Connectivity) | — | 100 messages per second across all APs/SPs; ≤ 1 MB per zip payload; **1000 requests per day per AP/SP**. The source says: "The above threshold is indicative only, we are currently monitoring the traffic for every AP/SP and revision will be made periodically." **Indicative and under review: confirm the current limit before sizing.** | Yes | — |
| **UDB documentation index** ([Additional UDB documentation](https://ec.europa.eu/assets/move-ener/udb/COM/Info/Additional_UDB_documentation.pdf)) and **Technical Specifications and Links** (modified 26 May 2026) | — | Links the public PDFs under `ec.europa.eu/assets/move-ener/udb/COM/Info/APIs/` (Exchange Model, API and Technical Connectivity, release notes, acronyms, eDelivery roadmap and onboarding) and the public user guides (UDB Dictionary, fuel codes, certificate scopes, gas value chain, Testing Sessions). An acceptance host (`www.acceptance.ec.europa.eu`) appears in the links | **Yes** | — |
| **UDB wiki pages** ([API Connectivity](https://wikis.ec.europa.eu/display/UDBBIS/API+Connectivity)) and the onboarding form | — | — | **No**: they redirect to EU Login | EU Login |
| **G-REX API Manual** ([current address](https://www.eex.com/fileadmin/EEX/Downloads/Registry_Services/Grexel_Merger/20251028_EEX-IB-API_manual-v3.0.pdf), 41 pages) | Title page: **Version 3.2, 05.08.2025** (file name says v3.0, 2025-10-28) | REST ("All features of G-REX can be performed directly through the APIs"). Six APIs: Certificate Creation, Management, Master Data, Private Reports, Public Reports, Transaction. Each exposes a `swagger.json` (OpenAPI) link; Postman environments and collections are appendices. Authentication: Microsoft Entra ID B2C, authorisation code with **PKCE**, a user sign-in with **multi-factor authentication**; the implicit flow (in production) and **Resource Owner Password Credentials are prohibited**. **Fair use: 500 requests per hour, 100 per minute**; no usage statistics are provided. Production `https://eexfranceapi.grexel.com/…` and demo `https://eexfrancedemoapi.grexel.com/…` (token tenant `gcrfrdemo.b2clogin.com`): **EEX France (power GO) only** | **Yes** (the manual) | API use: a registry account. Integration support "would require a direct contractual relationship with Grexel" |
| **G-REX OpenAPI** (`swagger.json`) | — | The field-level request and response schemas | **Not tried** | Not known |
| **EEX G-REX platform page** ([link](https://www.eex.com/de/markets/energy-certificates/g-rex-platform)) | — | Says G-REX supports "CertifHy – for hydrogen certification" and hydrogen as a carrier. It does not say which CertifHy scheme, and gives no CertifHy API hosts or demo | Yes | — |
| **ISCC EU** | Read 13 Nov | Commission-recognised voluntary scheme. Certification bodies certify; the supplying operator issues the PoS (the batch document). Public certificate database; sustainability-declaration and PoS templates | The certificate database: yes. The templates: reported, not checked | **An API: none found**, which is not proof that none exists |

**Not stated anywhere read:** RFNBO, hydrogen and ammonia in the UDB files. There are zero matches
for `rfnbo`, `hydrogen`, `h2`, `ammonia`, `electrolys`, `non-biological`, `temporal`, `bidding` or
`guarantee` in the three XSDs, the 112 samples and the 34 field specifications (their shared
strings). A fuel is a material code (a string), listed in the "fuel codes" user guide. **Read 16 Nov: that
guide does list RFNBO codes** (see *Sources read 16 Nov*, item 5). CertifHy, hydrogen and RFNBO are not mentioned in the G-REX manual.

## Which scheme — CertifHy is two schemes

| Scheme | What it is | Fits the physical RFNBO chain? |
|---|---|---|
| **CertifHy NGC** (Non-Governmental Certificate) | Book-and-claim GOs for disclosure. CertifHy applied in July 2023 for EECS recognition (outcome not confirmed here) | **No.** It discloses attributes and is not RFNBO compliance evidence |
| **CertifHy EU RFNBO Voluntary Scheme** | Recognised by the Commission (reported Dec 2024). Certification bodies recognised from 2025 (Vinçotte, TÜV SÜD, TÜV Rheinland, SGS, Bureau Veritas) | **Yes**, the candidate alongside ISCC EU |
| **ISCC EU** | Commission-recognised voluntary scheme; the PoS is the batch document | **Yes** |

**D5 flag (open for JML).** "CertifHy" alone is ambiguous. **D5 must name the scheme once the pilot
partner's scheme is known**: for the physical RFNBO chain the choice is the CertifHy EU RFNBO
Voluntary Scheme or ISCC EU.
- Whether either CertifHy scheme runs its registry on G-REX with API access is **NOT confirmed**.
- The likeliest reading is NGC (a GO-type certificate), but that is an inference.
- The SD03 tables read for the AIB fields are headed "EECS:GO (Disclosure)": an AIB hydrogen GO is
  a disclosure product in those tables.

## GEX's role and access — a mandate is not credentials

- **Never a hub participant.** Only registries connect to the AIB hub.
- **D6 (JML 2026-11-12): export only.** GEX builds the file and the party or its certifier submits
  it. `REGISTRY_CONNECTOR_BACKEND = none`.
- **A written mandate does not authorise GEX to hold or reuse a party's login.** Any live access
  would go through the registry's own route, under its rules:
  - the registry's delegated access for a party;
  - an application identity of GEX's own;
  - or service-provider permissions.
  
  Nothing in the D6 design stores a party's password, token or certificate.
- What the sources show about each route:
  - **UDB:** third-party service providers are named among those who connect. Each has its own AS4
    endpoint and its own PKI key (the Commission's or its own). Whether an SP needs a mandate from
    the economic operator, or any approval beyond onboarding, is **not stated**.
  - **G-REX:** the manual's tokens come from a user's own sign-in (PKCE, multi-factor), and it
    prohibits the password grant (ROPC), so a connector cannot sign in with a stored password.
    Delegated or application access is **not described** in the manual: ask Grexel and the issuing
    body.
  - **AIB:** not applicable to GEX (registries only).

## Inbound verification — three tasks

1. **Extraction:** reading a document's fields (a GO cancellation statement, a PoS, a certificate).
   It needs the document's format: the XSD for AIB messages, the UDB Exchange Model, the scheme's
   template for a PoS. A registry's cancellation statement has its own format, which none of the
   sources read gives.
2. **Matching:** comparing the extracted fields with the custody input that cites them (quantity,
   unit, period, holder, certificate or statement id). It is built on GEX's own records and needs
   only (1). It must also catch an excessive or incompatible allocation of the same evidence:
   see §5 *Double use of authentic evidence* in the field-mapping draft. Today nothing stops it.
3. **Authoritative confirmation:** that the cancellation or transaction really happened, asked of
   the registry itself. It needs registry access by one of the routes above, or a statement the
   registry signs. A hash of an uploaded PDF proves nothing about a cancellation.

**UDB inbound access is not an HTTP GET.** It is a named, asynchronous AS4 retrieval request, for
example:
- `EOGetTransaction` (by `TRANSACTION_ID`, or an economic operator with a trade-date or
  creation-date range);
- `EOGetPOSList` (by `POS_ID`, up to 999 per request);
- `GetCertificate`, `GetFPOM`, `GetPutOnMarket`, `GetBookOut`.

The response comes back later through the queue.

**OPEN:** whether the listed notifications can support reconciliation. They are
`TransactionSellerNotification`, `TransactionBuyerNotification`, `AuthorityAck`,
`MemberStateTransactionDataView` and `ErrorResponse`. The buyer notification carries
`TRANSACTION_ID`, `STATUS`, `POS_ID`, `QUANTITY` and `MEASURE_UNIT`, but the sources do not say who
receives which notification, or when.

**What a UDB record can show.** It has fields for:
- quantity, unit and energy content;
- GHG value and method;
- mass-balance start and duration;
- material code and voluntary-scheme number;
- plant start date.

These map onto custody inputs, lot characteristics and period windows (see the mapping draft).
**The inspected schema does not expose the underlying correlation and additionality evidence; a
UDB record alone does not independently demonstrate those checks.** GEX's temporal, geographic and
additionality results stay GEX-side evidence, computed from its own metered records.

**The UDB channel is real but heavy:**
- an AS4 Access Point, Commission onboarding and a PKI;
- an indicative 1000 requests a day, under review in the source (confirm the current limit before
  sizing);
- asynchronous responses.

## Status of Step 6

**Export foundation complete; external adapters and inbound verification outstanding.** Head 111:
- **Built:** one connector interface; `gex_export_v1`, GEX's internal format, VERIFIED items only;
  seller-only export with the VERIFIED gate; the append-only `registry_outbox`;
  `REGISTRY_CONNECTOR_BACKEND = none`.
- **Not demonstrated:** that any registry accepts a GEX file. `gex_export_v1` is not a registry's
  format.
- **Code disagrees with this document:** the docstring of
  `backend/app/core/registry_connectors/gex_export.py` still says no public field-level
  specification was found (13 Nov). The behaviour is unaffected. The comment is stale and is left
  for a code change JML approves.

**Next, none of which needs a partner account:**
- ~~the UDB "fuel codes" and "UDB Dictionary" user guides~~ (read 16 Nov: `RFNBO01` hydrogen and
  `RFNBO02` ammonia exist; whether `MATERIAL_CODE` carries them is open);
- a G-REX `swagger.json` from the demo host, if it is reachable without a token;
- the AIB Fact Sheets that SD03 cites for code lists (4, 22, 24, 25);
- JML's review of the field-mapping draft v0.3. Production extraction and matching code waits for
  that approval. Per JML (16 Nov), schema research and offline fixtures continue now, and D5
  selects the first production integration without stopping that work. The full reading list is
  in the mapping draft, §7.

## Sources read 16 Nov 2026 — the claims the external reviews cited

Each was labelled "REPORTED, NOT READ" in the mapping draft. Read on 16 Nov 2026 through the built-in
browser (EUR-Lex refuses plain downloads) and `curl`. The texts are summarised here in my own words;
only the clause references and one short quote per source are literal.

| # | Reported claim | Verdict | Source, clause, version |
|---|---|---|---|
| 1 | Mass-balance rules let intact sets of sustainability characteristics be assigned to withdrawals; physical-share rules only in particular cases | **Confirmed** | Reg. (EU) 2022/996, **Art. 19(2)(j)** and **(i)**, text as published OJ L 168, 27.6.2022 |
| 2 | The supplier's certificate validity is checked at the date of physical dispatch | **Confirmed, in a different document, and wider** | ISCC EU **203** v4.2 §3.1 (pp. 10 and 17). **201 v4.1 was not read** |
| 3 | EU ETS rules address an RFNBO quantity claimed by someone else through GO disclosure | **Partly confirmed: narrower** | Reg. (EU) 2018/2066, **Art. 39(5)**, consolidated 1 Jul 2024 |
| 4 | An AIB publication of 6 Nov 2026 proposes linking GO and PoS records with shared identifiers and coordinated cancellation | **Confirmed** | aib-net.org/node/3515 (news item); public summary PDF dated 5 Nov 2026 |
| 5 | (Open question) Does RFNBO hydrogen or ammonia have a UDB material code? | **Yes, a fuel code; link to `MATERIAL_CODE` not shown** | UDB *Fuel* guide, revision June 2025, p. 26 |

**1. Regulation (EU) 2022/996, Article 19 ("Implementation of the mass balance system").**
URL: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R0996 (the original text; later
amendments and consolidations were **not** read).
- 19(2)(j): the sustainability and GHG characteristics of a consignment are treated as one set. When
  consignments leave a mixture, any of the sets may be assigned to them, provided no set is split and the
  mass balance holds over the appropriate period. This is the claim, and it is confirmed. It supports
  "intact set per lot" and is incompatible with proportional splitting of attributes.
- 19(2)(i): where biofuels, bioliquids or biomass fuels are blended with fossil fuels, the characteristics
  assigned to the blend follow the **physical share** of the renewable part. The "particular case" is a fossil blend.
- Also in the same paragraph, not reported but relevant: separate mass balances where materials cannot form
  a mixture, with no transfer of information between them, (e); mixtures need a common container, facility or
  an **interconnected** grid, (a)–(d); and **(l) the balancing period is 3 months for most operators (12 for
  agricultural and forest biomass)**, aligned to the calendar year or its quarters, with the carried-forward data
  matching the physical stock at period end.
- Quote (Art. 19(2)(j)): "the sets of sustainability and GHG emissions saving characteristics are not split".
- **Limits of this reading:** the article is addressed to voluntary schemes and speaks of biofuels, bioliquids,
  biomass fuels, raw material and fuels. It does not by itself say that RFNBO supply chains follow it; that was
  not checked. A search summary cited this as "Article 20"; in the original text it is Article 19.
- **Dependent rule:** §5.4 (allocation method from the scheme, no proportional attributes) is **consistent**.
  The 3-month period in (l) bears on how GEX period length (097, certifier parameter) and carry-forward are
  set; §5.4 and §9 should say so. No contradiction.

**2. ISCC.** The URL given for ISCC EU 201 System Basics 4.1 (January 2024) answers **404** (browser and
`curl`, 16 Nov), so 201 v4.1 was **not read**. The same rule is in **ISCC EU 203 Traceability and Chain of
Custody, version 4.2, valid from 21 May 2025**
(https://www.iscc-system.org/wp-content/uploads/2025/04/ISCC_EU_203_Traceability_and_Chain-of-Custody_4.2.pdf):
- §3.1: recipients must ensure the supplier was certified at the date of **physical dispatch**.
- §3.1, p. 17: the supplier must hold a valid certificate at dispatch and, if the dates differ, also at the date
  the sustainability declaration is issued; a declaration cannot be issued outside a certificate's validity; the
  recipient must itself hold a valid certificate at receipt and at issue, and must verify the supplier's validity on
  both dates, and should not accept the declaration otherwise.
- The version the review named (4.1) is therefore not the current EU 203 version (4.2). What 201 says was not read.
- **Dependent rule:** §9.2 item 1 lists dispatch among several dates, which is consistent, but for ISCC the
  rule row needs **dispatch, issuance and receipt**, not dispatch alone. Revisit §9.2 when the rule rows are drafted.

**3. EU ETS.** Commission Implementing Regulation (EU) 2018/2066, consolidated text of 1 Jul 2024
(https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02018R2066-20240701; later consolidations not read).
- **Article 39(5)**: an operator may determine the RFNBO or RCF fraction of **natural gas injected into a gas
  grid** from purchase records of equivalent energy, if it shows (a) no double counting of the same quantity,
  in particular that it is "not claimed to be used by anyone else", including through a GO disclosure, and (b)
  that operator and producer are connected to the same grid. Cancellation of the quantity in the Union
  Database (Art. 31a RED) or a national database may be taken as demonstrating compliance; later non-compliance
  with the PoS leads the authority to correct the verified emissions. Article 39(4)(a) has the same test for biogas.
- **So the report is partly right, and narrower.** The provision exists and names GO disclosure, but it governs one
  accounting route for grid-injected gas under the ETS, not RFNBO claims in general. Hydrogen or ammonia outside a
  gas grid is not covered by this article as read.
- **Dependent rule:** §5.4's "refuse uses that an approved rule marks incompatible" does not rely on this article.
  Treat it as one source for a rule row for gas-grid injection, not as general authority.

**4. AIB, 6 Nov 2026.** https://www.aib-net.org/node/3515, "AIB publishes analysis on linking Guarantees of
Origin and the Union Database", dated 6 Nov 2026. The paper, "Linking Guarantees of Origin and the Union
Database – design follows responsibility", is dated 5 Nov 2026 (public summary, 632 kB).
- The news item (read in full) says AIB sets out, ahead of the revision of Regulation 2022/996, how national GO
  registries and the UDB can be connected. It proposes: keep GOs under national supervision; link GO and PoS
  records through shared identifiers and one coordinated cancellation process; accommodate the national-database
  route in Article 31a(5); phase it in. The aim is to prevent double claims in the renewable gas market.
- The public summary PDF was text-extracted and searched, **not read in full**. It mentions PoS identifiers and a
  "GO–PoS link identifier"; there are no matches for RFNBO, hydrogen or ammonia.
- It is a **proposal by AIB's Gas Scheme members**, not a rule, and not RFNBO-specific on this evidence.
- **Dependent rule:** none in the mapping depends on it; §5.4 already treats it as a proposal. Confirmed as reported.

**5. UDB fuel codes and dictionary.** Fuel guide: https://ec.europa.eu/assets/move-ener/udb/COM/UserGuide/Fuel_codes.pdf
(27 pages, "Revision June 2025"); Dictionary: .../UserGuide/UDB_Dictionary.pdf (2 pages).
- The guide, p. 26, lists `RFNBO01` Hydrogen, `RFNBO02` Ammonia, `RFNBO03` Methane, `RFNBO04` Methanol, `RFNBO05`
  FT Diesel, `RFNBO06` LNG, `RFNBO07` FT SAF, and `RCF0001`–`RCF0006`. Its column is headed "UDB Fuel Code (To be confirmed)",
  so the codes are provisional. Other hydrogen entries exist (`FBM0023` "Hydrogen from renewable sources", Annex III;
  `FBG0056` "Hydrogen"); their relation to the RFNBO codes was not examined.
- The guide says the fuel code is used in all communication with the UDB. It does **not** say that the XSD field
  `MATERIAL_CODE` (String10) carries it. `RFNBO01` fits 10 characters, but the link is **not established**.
- The Dictionary is a two-page glossary (terms and abbreviations); it says nothing about codes.
- **Effect:** the earlier statement that UDB files hold no RFNBO reference stands for the XSDs, samples and field
  specifications, and is superseded for the fuel-code guide. `coc_input.input_type` mapping stays NOT CONFIRMED.

**Not read:** ISCC EU 201 v4.1 (404); the full AIB paper; later amendments of 2022/996 and 2018/2066.
**Code check:** none made (docs only); no disagreement with code found or sought.

## Change log

| Date | Superseded claim | Replaced by | Why |
|---|---|---|---|
| 13 Nov → 15 Nov | None of the four interfaces publishes a field-level specification | The AIB XSDs (SD03 9.1), the UDB Exchange Model with its XSDs and field specifications, and the G-REX manual v3.2 are all public | The 13 Nov read stopped at landing pages; the documents were opened on 15 Nov |
| 13 Nov → 15 Nov | GEX can only ever read what AIB registries produce | GEX's role depends on the registry's own access routes and permissions, not on technology; under D6 it is export only | Overstated in the 13 Nov read |
| 13 Nov → 15 Nov | "CertifHy" as one scheme | Two schemes: NGC (disclosure) and the EU RFNBO Voluntary Scheme | Conflated in the 13 Nov read |
| 13 Nov → 15 Nov | AIB: no JSON | AMQP XML **or** AMQP JSON (SD03 9.1, Annex C) | Read in SD03 9.1 |
| 15 Nov (early) → 15 Nov | AIB XSD versions v71 and v80, v80 mandatory from 1 Jan 2024 (from the CMO-CMO schemes page) | v80 (to end Oct 2027) and v81, described in SD03 9.1; that page now answers 404 | SD03 9.1 is the current definition |
| 15 Nov (early) → 15 Nov | G-REX manual v3.1 (31 Jan 2025) at `API_manual_GREX.pdf` | v3.2 (05.08.2025) at a new address; the old link answers 404 | Found on EEX's French power GO page |
| 15 Nov (early) → 15 Nov | G-REX: "a fair-use policy applies (no metrics published)" | The manual publishes the limits (500 requests per hour, 100 per minute); only usage statistics are not provided | Re-read for this restructuring |
| 15 Nov (early) → 15 Nov | UDB: whether the documentation needs an EU Login | Only the wiki pages and the onboarding form do; every PDF, XSD, sample and field specification answered 200 without one | Checked by download |
| 15 Nov → 15 Nov (restructure) | "A UDB record cannot confirm" the RFNBO checks | "The inspected schema does not expose the underlying correlation and additionality evidence; a UDB record alone does not independently demonstrate those checks." | External review, accepted by JML |
| 15 Nov → 15 Nov (restructure) | Inbound UDB reads "through a GET message" | Named asynchronous AS4 retrieval requests; whether notifications support reconciliation is OPEN | External review, accepted by JML: AS4 has no HTTP GET |
| 15 Nov → 15 Nov (restructure) | "1000 requests a day" as a fixed limit | Indicative, under review in the source; confirm before sizing | External review, accepted by JML; the source's own wording |
| 15 Nov → 15 Nov (restructure) | Agency "with the party's written mandate, its credentials" (and D6's "credentials in `.env`") | A mandate does not authorise GEX to hold or reuse a party's login; the route is the registry's own delegated access, an application identity or service-provider permissions | External review, accepted by JML; G-REX also prohibits the password grant |
| 15 Nov → 15 Nov (restructure) | No RFNBO field in any interface | True of the UDB files read; **AIB v81** has `BiddingZone`, `RedispatchingCriteriaMet` and `PowerPurchaseAgreement` for EnergyGas and Hydrogen | Read in SD03 9.1 for the field mapping |
| 15 Nov → 16 Nov (fixtures) | The AIB XSDs are "defined in SD03 Annex B7" | SD03 defines the elements; the XSD files are separate downloads from an AIB page that answered 404, and they were **not obtained** | Found while building the offline fixtures |
| — → 16 Nov (fixtures) | — | UDB element names in the XSD differ in places from the field-specification sheets (e.g. `NON_RECOGNISED_VS`, `GHG_MEASURING_UNIT_ACR`); **the XSD is the authority for names.** The public sample `GetCertificateResponse.xml` fails its own v3.5 schema (`IN_MATERIAL_TECH_PROD_PATH` not expected) | Validated with lxml against the v3.5 XSDs |
| 16 Nov → 16 Nov (sources) | "Regulation 2022/996, EU ETS, ISCC EU 201 4.1 and the AIB publication of 6 Nov: REPORTED, NOT READ" | Read: 2022/996 Art. 19(2)(i),(j) confirmed; the ISCC dispatch rule confirmed in EU 203 v4.2 (201 v4.1 answers 404) and wider than reported; ETS Art. 39(5) narrower than reported (grid-injected gas); AIB item exists (node 3515); UDB fuel guide lists `RFNBO01`/`RFNBO02` | Read for the mapping draft's §5.4 and §7 (see *Sources read 16 Nov*) |
| 16 Nov (sources) | "A fuel is a material code, listed in the fuel-codes guide, not yet read" | The guide lists the RFNBO codes, marked "to be confirmed"; the link to `MATERIAL_CODE` is not shown | Read |

## Sources

**Read 13 Nov 2026:**
- **CertifHy:**
  - [EEX G-REX platform](https://www.eex.com/de/markets/energy-certificates/g-rex-platform)
  - [CertifHy D13](https://www.clean-hydrogen.europa.eu/system/files/2022-07/CertifHy-D13%20Guidelines%20for%20replication%20of%20GO%20Schemes.pdf)
- **ISCC:**
  - [DEKRA, ISCC EU](https://www.dekra.nl/en/iscc-eu-certification/)
  - [ISCC Proof of Compliance guidance](https://www.kem.gov.lv/sites/kem/files/media_file/ISCC-Guidance-Document-Proof-of-Compliance-V1.0.pdf)
- **UDB:** [UDB training for economic operators](https://ec.europa.eu/assets/move-ener/udb/Training%20Material/Union%20Database%20for%20Biofuels_EO.pdf)
- **AIB:** [How to join (2025)](https://www.aib-net.org/sites/default/files/assets/aib/how-to-join/AIB-2025-AIB%20How%20to%20Join%20presentation.pdf)

**Read 15 Nov 2026 (correction):**
- **AIB:**
  - [CMO-CMO schemes: XSD v71 / v80](https://aib-net.org/eecs/cmo-cmo-schemes) (answers 404 since; superseded by SD03 9.1)
  - [SD03 HubCom Release 9.1](https://www.aib-net.org/sites/default/files/assets/eecs/subsidiary-documents/AIB-EECS-SD03%20HubCom%20EECS%20Registration%20Databases%20-%20Release%209.1.pdf)
  - [AIB hub](https://www.aib-net.org/facts/eecs-registries/aib-hub)
- **G-REX:** [API manual, old address](https://www.eex.com/fileadmin/EEX/Downloads/Registry_Services/Grexel_Merger/API_manual_GREX.pdf) (answers 404)
- **UDB:**
  - [API Connectivity (Commission wiki)](https://wikis.ec.europa.eu/display/UDBBIS/API+Connectivity) (EU Login)
  - [Additional UDB documentation](https://ec.europa.eu/assets/move-ener/udb/COM/Info/Additional_UDB_documentation.pdf)
  - [EC Union Database page](https://energy.ec.europa.eu/topics/renewable-energy/bioenergy/biofuels/union-database-liquid-and-gaseous-renewable-and-recycled-carbon-fuels_en)
- **CertifHy schemes:**
  - [SGS recognised for the CertifHy EU RFNBO scheme](https://www.sgs.com/en/news/2025/05/sgs-recognized-as-approved-certification-body-for-certifhy-eu-rfnbo-voluntary-scheme)
  - [Bureau Veritas, CertifHy EU RFNBO](https://group.bureauveritas.com/newsroom/bureau-veritas-expands-hydrogen-certification-capabilities-certifhy-eu-rfnbo-voluntary)
  - [AIB, CertifHy](https://www.aib-net.org/news-events/aib-projects-and-other-news/certifhy)

**Read 15 Nov 2026 (later):** SD03 9.1 and the UDB documentation index opened and read; UDB
Technical Specifications and Links (modified 26 May 2026).

**Read 15 Nov 2026 (latest):**
- **UDB** (downloaded with `curl`, read locally; no account, no EU Login):
  - [Exchange Model](https://ec.europa.eu/assets/move-ener/udb/COM/Info/APIs/Exchange_Model.pdf)
  - [XSDs v3.5](https://ec.europa.eu/assets/move-ener/udb/COM/Info/APIs/EXM_Files/UDB-Exchange-Model%20-%20xml%20schemas%20v3.5.zip)
  - [samples](https://ec.europa.eu/assets/move-ener/udb/COM/Info/APIs/EXM_Files/Request_Responses_Samples.zip)
  - [field specifications](https://ec.europa.eu/assets/move-ener/udb/COM/Info/APIs/EXM_Files/Field_Specification.zip)
  - [Technical Connectivity](https://ec.europa.eu/assets/move-ener/udb/COM/Info/APIs/Technical_Connectivity.pdf)
  - [API Connectivity](https://ec.europa.eu/assets/move-ener/udb/COM/Info/APIs/API_Connectivity.pdf)
- **G-REX:**
  - [API manual v3.2, current address](https://www.eex.com/fileadmin/EEX/Downloads/Registry_Services/Grexel_Merger/20251028_EEX-IB-API_manual-v3.0.pdf)
  - [EEX French power GOs page (links it)](https://www.eex.com/en/markets/energy-certificates/french-power-gos)
  - [EEX G-REX platform page](https://www.eex.com/de/markets/energy-certificates/g-rex-platform)

**Re-read 15 Nov 2026 (restructure and field mapping):** the local copies of SD03 9.1, the UDB
field specifications (`POS_Get` v2.6, `Transactions` v2.6, `Transactions_Notification` v2.6, `Cert`
v3.0), `udbModel_v1.0.xsd`, Technical Connectivity and the G-REX manual v3.2. Nothing new was
downloaded.

Public contact named in the UDB API Connectivity PDF for the Commission PKI route:
`EC-EDELIVERY-SUPPORT@ec.europa.eu`.

**Read 16 Nov 2026 (sources named by the external reviews):**
- **EU law:**
  - [Regulation (EU) 2022/996, original text](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R0996) (Art. 19)
  - [Regulation (EU) 2018/2066, consolidated 1 Jul 2024](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02018R2066-20240701) (Art. 39)
- **ISCC:** [EU 203 Traceability and Chain of Custody v4.2](https://www.iscc-system.org/wp-content/uploads/2025/04/ISCC_EU_203_Traceability_and_Chain-of-Custody_4.2.pdf).
  [EU 201 v4.1](https://www.iscc-system.org/wp-content/uploads/2024/01/ISCC_EU_201_System_Basics_4.1_January2024.pdf) answers 404 and was not read.
- **AIB:**
  - [News item, 6 Nov 2026](https://www.aib-net.org/node/3515)
  - [Public summary of the paper, 5 Nov 2026](https://www.aib-net.org/sites/default/files/assets/news-events/Other%20news/AIB-2026-AIB-%20Linking%20GOs%20and%20the%20Union%20Database%20-%20public%20summary_20261105.pdf) (searched, not read in full)
- **UDB:**
  - [Fuel codes (rev. June 2025)](https://ec.europa.eu/assets/move-ener/udb/COM/UserGuide/Fuel_codes.pdf)
  - [UDB Dictionary](https://ec.europa.eu/assets/move-ener/udb/COM/UserGuide/UDB_Dictionary.pdf)
