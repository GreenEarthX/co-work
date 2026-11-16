# Connector field mapping — external evidence to GEX custody records

**Version 0.3, 16 Nov 2026: DRAFT for JML.** No extraction, matching or allocation code is built.
Only the offline fixtures are (§7).

- **JML decided on 16 Nov:**
  - a common contract, one adapter first, and shared behaviour extracted only when a second adapter
    shows the need;
  - provisional requests consume nothing, and any reservation needs explicit authorisation, expiry
    and release;
  - no confirmed allocation without an approved, applicable rule;
  - GEX's ledger prevents excess allocation within its own records and cannot guarantee against
    claims made elsewhere;
  - **Q2 is settled** (§5.8);
  - schema research and offline fixtures continue now; D5 selects the first production integration
    without stopping that work.
- **Waits for JML's approval of this version:**
  - the acceptance criteria (§9) and acceptance cases (§10);
  - the open questions (§8).

Companion to `docs/GREENMESH_CONNECTORS_RESEARCH.md`, which records each source, its version and its
access.

## Rules this draft follows

- **External field names are only those found in the sources read:**
  - AIB SD03 9.1;
  - the UDB Exchange Model v3.5 XSDs and field specifications;
  - the G-REX API manual v3.2.

  A needed field that is not in a source is marked **NOT CONFIRMED**.
- **A fact reported by a reviewer but not read here is labelled REPORTED, NOT READ.** It is
  written down so it is not lost. It is not relied on.
- **GEX fields were checked in the code at head 119.** A field GEX does not have is marked
  **NONE (gap)**. Checked:
  - migrations 044, 097, 099, 101, 110, 111 and 116;
  - `app/core/custody_ledger.py`, `rfnbo_correlation.py`, `evidence_pack.py`, `product_record.py`
    and `registry_connectors/gex_export.py`.
- **"Checked in code" means read, not run.** The tests named here exist. They were not run for this
  draft (docs only).
- **Direction: inbound.** These mappings are for extraction and matching. Under D6, GEX submits
  nothing.
- **Extracted is not verified.** A value extracted from an uploaded document is the party's
  declaration (DECLARED). Only confirmation by the authoritative registry could make it VERIFIED.
  This draft changes no label in the evidence pack.

### GEX records referred to

| Short name | What it is | Where defined |
|---|---|---|
| `coc_input.*` | A custody input consignment: hash-chained per period, append-only. `input_type` (ELECTRICITY, CO2, N2, WATER, H2), `quantity`, `unit`, `quantity_normalised`, `normalised_unit` (MWh or kg), `sustainability_status`, `received_on` (a date), `characteristics` (jsonb, any object), `evidence_kind` (PPA, GO, POS, SUPPLIER_INVOICE, METER, OTHER), `evidence_ref` (text, non-empty), `source_lot_id` (101), `source_token_id` (110) | 097, 101, 110; `custody_ledger.record_input` |
| `coc_period.*` | The accounting period: `facility_id`, `molecule`, `pathway`, `scheme`, `period_start`, `period_end` | 097 |
| `coc_scheme_rule.*` | `max_period_days`, `carry_forward_allowed`, `negative_interim_allowed`. Empty by design (the certifier's values). See the finding in §5.6 | 097 |
| `lot.characteristics.*` | A period lot's validated characteristics (`custody_ledger.Characteristics`; unknown keys refused): `ghg_intensity_gco2e_mj`, `pathway`, `scheme`, `certificate_id`, `country_of_origin`, `production_window_start`/`_end`, `rfnbo`, `additionality_basis` (DIRECT_CONNECTION, PPA, GRID_RENEWABLE_SHARE, GRID_LOW_EMISSION, IMBALANCE_REDUCTION, NOT_CLAIMED). **Lots only**: an input's `characteristics` is not validated beyond being an object | 097 |
| `mass_balance_lots.*` | `lot_id`, `molecule`, `production_date`, `total_volume_kg`, `allocated_volume_kg`, `certification_pathway`, `carbon_intensity_gco2e_mj` | 044, 097 |
| `coc_facility_profile.*` | `bidding_zone`, `electrolyser_commissioning_date`, `source` | 099 |
| `coc_ppa.*` | `ppa_ref` (unique per project), `generator_id`, `generator_bidding_zone`, `generator_commissioning_date`, `technology`, `evidence_ref` | 099 |
| `product_certificate.*` | `kind` (certificate, inspection), `scheme`, `body`, `reference`, `scope` (organisation, site, batch, sample), `facility_id`, `valid_from`, `valid_until`, `document_sha256`, `state` (asserted → submitted → verified or rejected; trigger-enforced), decider fields. **Unique on (project_id, scheme, reference) only. No quantity column** | 116; `product_record.py` |
| `token_certificate_coverage.*` | Which tokens a certificate covers: `quantity_t` (tonnes, nullable), `period_start`, `period_end`. Unique on (certificate_id, token_id). **Coverage is not summed or capped** | 116 |
| correlation | The `rfnbo_correlation` result: `temporal`, `geographic`, `additionality`, `upstream_hydrogen`, `rules_used`, `basis: COMPUTED`. Computed from metered `plant_data` and `coc_ppa`, **not from GO or PoS documents** | 099; `rfnbo_correlation.py` |

---

## 0. The common contract

**Six concepts, as a vocabulary every adapter answers to.** They are not a shared layer built in
advance.

| Concept | Question it answers | Who interprets it |
|---|---|---|
| **Evidence** | What was received, from where (provenance: upload, registry export, AS4 response), which version, which file (sha256) | Shared: recording and provenance |
| **Identity** | The scheme's authoritative identifier(s) for what the evidence is about, their scope, and any unresolved aliases | The adapter |
| **Claim** | What the evidence establishes: for whom, where, when, for which use. Some evidence carries no allocatable quantity at all (an organisation's or a site's certification status) | The adapter, against approved rules (§5.5) |
| **Quantity and allocation** | The eligible amount, its unit, any indivisibility, and what has been allocated against it | The adapter supplies the unit and granularity. The shared layer enforces the arithmetic and concurrency |
| **Lifecycle** | Transfer, split, conversion, cancellation, expiry, withdrawal, correction | The adapter maps external events. The shared layer records them |
| **Scheme rules** | How the operations above are interpreted and validated. Jurisdiction, intended use, effective dates, source and approval status | Approved data rows (§5.5, §6), never code defaults |

**What stays shared, so no adapter can get it wrong** (correction 4). It already exists in GEX and
must be reused, not re-implemented per adapter:
- **Permissions:** RLS, and the operator connection after an authorisation check.
- **Audit:** the event ledger and append-only triggers.
- **Idempotency:** `core/idempotency` (114).
- **Concurrency protection:** `FOR UPDATE` locking and the deferred constraint triggers.
- **Reversals as records:** a compensating record, never an edit.

**What an adapter does:**
- interprets identifiers, granularity, document types and scheme eligibility;
- maps them onto the concepts;
- supplies its own coverage check:
  - **AIB:** certificate-number intervals;
  - **UDB:** PoS and transaction lineage with quantities;
  - other schemes: their own (batch ids, serial numbers, balances, registry transactions).

**Build order:**
1. The adapter D5 names.
2. Offline fixtures for the others in the meantime (§7).
3. Extract the shared model once a second adapter shows what is common.

---

## 1. Identifier scope — engineering research, not a policy choice

**The task.** Establish from each specification how far each identifier is unique, and who
assigns it. This is a matter of fact. It is not JML's decision or Claude's.

| Identifier | Scope stated in the source? | What the source says | Still to read |
|---|---|---|---|
| AIB certificate number (`StartCertificateNumber`, `EndCertificateNumber`) | **Yes** | SD03 A2.1.1: the coding exists "to ensure uniqueness of all data identifiers". A2.3: GS1 GIAI, always 30 digits = the GS1 Company Prefix (6–13 digits) "of the registry assigning the Asset Reference" + a reference that registry assigns. SD03 note 2 (EECS Rules A3, immutability): issued certificate data is kept in imports and exports | Whether the receiving registry keeps the number on import (not stated explicitly in what was read). Whether GS1 prefixes can nest (GS1 rules, not read) |
| AIB registry | Yes | A2.2: each registry holds at least one GS1 prefix. One may be chosen as the registry ID; a registry may hold more than one | How the 2-digit `IssuingBody` code maps to a registry prefix (Fact Sheet 4, not read) |
| AIB account holder ID | Yes | A2.5: assigned by the host issuing body, starting with its 2-digit ID and ending with a check character | — |
| AIB production device | Yes | A2.4: GSRN with the registry's prefix and a check digit | — |
| AIB `cancellationStatement` | **No** | Token 1–150, "text field". For storage it comes with `cancellationIssuingBody` | The issuer's own statement format |
| AIB `preConversionCancellationStatement` | **No** | Same type. **No issuer attribute** in the v81 table | Where its issuer is stated |
| UDB `POS_ID` / `POSID`, `TRANSACTION_ID` | **No** | Generated by the UDB "when the trade or material was registered". Samples look like `POS-…` and `TRN-…` | UDB Dictionary |
| UDB `CERTIFICATE_NUMBER` | **No** | "Certificate number (Original)", String100, under a voluntary scheme and certification body | UDB Dictionary; scheme rules |
| UDB `REFERENCE_NUMBER` | Party-scoped | "seller / buyer reference" | Never an identity |
| G-REX identifiers | Unknown | Not in the manual | `swagger.json` |

**Interim identity rule, until scope is confirmed:**
1. **Every GEX evidence record gets a GEX internal ID.** Identity is attached to it, never used as
   its key.
2. **Authoritative identity is separate from provenance.**
   - Identity = scheme + registry or domain + identifier kind + identifier, with the scope where the
     specification requires one (e.g. the AIB issuing body for a cancellation statement).
   - Provenance = where GEX obtained the record: an upload, a party's export, an AS4 response. The
     same certificate may arrive through several channels, and each arrival is one more piece of
     evidence for the same identity.
3. **Equality is asserted only where the specification establishes scope.** Two equal identifiers
   whose scope is unknown are recorded as *possible aliases*, neither merged nor treated as
   distinct.
4. **Unresolved identity does not block ingestion.**
   - The evidence is recorded as `IDENTITY_UNRESOLVED`, with the reason. It can be linked to a
     declared input.
   - It cannot support a verified claim, or confirm an allocation, until identity, quantity and
     eligibility checks pass.
   - Conflict detection is incomplete while identity is unresolved, and the readout says so.

---

## 2. AIB adapter — certificate transfer fields, v80 / v81 (SD03 HubCom 9.1)

**Scope.** These are the fields of a certificate in a hub transfer message (`Body` / `Certificates`).
GEX never receives hub messages; only registries connect to the hub. A registry's cancellation
statement has its own format, which SD03 does not define. So these rows apply only where a
registry's export or statement carries the EECS fields. Whether it does is unresolved for every
registry.

M / O / N means mandatory, optional or not applicable, for the **Hydrogen** carrier (and EnergyGas
where it differs). "Elec." is the Electricity carrier.

| External field | GEX field | Conversion rule | Validation | Evidence source | Unresolved dependency |
|---|---|---|---|---|---|
| `StartCertificateNumber`, `EndCertificateNumber` (M; 30-digit fixed-length numbers, attribute `cS="eecs"`) | NONE (gap). Today only free text in `coc_input.evidence_ref` | Identity = the certificate numbers, keyed on the issuing registry's prefix (§1). Kept as an interval, never as one number | 30 digits each; start ≤ end; the interval is compared with already-allocated intervals of the same issuing registry (§5.3) | Registry statement or export | Whether the registry's statement lists the cancelled intervals |
| `NumberOfCertificates` (Body, M); `Certificates@faceValue` (length 1–8, default `MWh`) | `coc_input.quantity` + `coc_input.unit` | Quantity = certificates × the stated face value. **Read `faceValue`; do not hard-code 1 MWh.** SD03: "Currently only certificates with the default value (MWh) are supported by the AIB Hub", and the attribute exists. The review reports that AIB describes 1 Wh as optional (REPORTED, NOT READ; not among the 16 Nov sources) | Count equals End − Start + 1 within one interval (inference: confirm with the issuing body) | Registry statement | **Hydrogen MWh → kg: NONE (gap)**: needs an approved calorific value (102/D8 cover Nm³ only) |
| `IssuingBody` (M; 2 digits, Fact Sheet 4) | NONE (gap) | Part of the identity scope | 2-digit code | Registry | Fact Sheet 4 |
| `CountryOfIssue` (M; ISO 3166-1 alpha-2) | NONE (gap) for inputs. `lot.characteristics.country_of_origin` belongs to a lot | — | `^[A-Z]{2}$` | Registry | — |
| `DateOfIssue` (M; local date of the domain) | NONE (gap) | — | ≥ 2004-03-17 | Registry | — |
| `ProductionPeriod@start`, `@end` (M; local time with UTC offset, both inclusive); `@length` (v81, M: `month`, `day`, `hour`, `30min`, `15min`) | `coc_input.received_on` is a date only. NONE (gap) for an interval | To UTC with the stated offset | Inside `coc_period` (097 input guard). Whether `length` must match the `rfnbo_rule` granularity on that day is OPEN | Registry | **Temporal correlation reads metered `plant_data`, not inputs.** Whether GO periods should feed it is for JML and the certifier |
| `EnergyCarrier` (M: `Electricity`, `EnergyGas`, `Hydrogen`) | `coc_input.input_type` | `Electricity` → `ELECTRICITY`; `Hydrogen` → `H2`; `EnergyGas` → NONE (gap) | Allowed values only | Registry | — |
| `Product@name` (e.g. `EECS:GO`), `Product/Purpose` (e.g. `Disclosure`), `CompetentAuthority`, `ProductType@type` | `coc_input.evidence_kind` = `GO`. Purpose: NONE (gap) | — | The purpose must be compatible with the intended claim (§5.5) | Registry | The SD03 tables read are headed "EECS:GO (Disclosure)" |
| `Conversion@tag` (M); v81 `@preConversionCancellationStatement`, `PreConversionProductionPeriod`, `PreConversionProductionDevice` (O) | NONE (gap) | Lifecycle: a conversion event linking the hydrogen certificate to the electricity attributes it consumed | Identity unresolved where no issuer is given (§1) | Registry | Needed to see a consumed attribute claimed again elsewhere (§5.4) |
| v81 `Storage@cancellationStatement`, `@cancellationIssuingBody`, `@efficiencyFactor` | NONE (gap) | Lifecycle: a storage event | — | Registry | — |
| `ProductionDeviceID` (M), `ProductionDeviceName` (O) | Elec. GO: `coc_ppa.generator_id`. Hydrogen GO: `coc_period.facility_id` | NONE (gap): no mapping table between registry device IDs and GEX IDs | Equals the mapped ID | Registry | Who keeps that mapping |
| `DateOperational` (M) | Elec.: `coc_ppa.generator_commissioning_date`. Hydrogen: `coc_facility_profile.electrolyser_commissioning_date` | Local date | Equal, or flagged | Registry | The mismatch rule |
| `ProductionTechnology`, `EnergySource` (M; codes); `SourceShares` (O) | `coc_ppa.technology` (free text) | — | EECS Fact Sheet code lists (not read) | Registry | Code lists |
| `SupportFlag` (M), `ProductionSupportDescription`, `InvestmentSupportDescription` (O) | NONE (gap) | — | — | Registry | Whether additionality needs it (counsel or the certifier) |
| `ProductionDeviceLocation` / `Coordinates` or `Address` (at least one) | NONE (gap) | — | — | Registry | — |
| `Capacity/GasProductionCapacity` (M, Hydrogen); `ElectricalCapacity` (M, Elec.) | NONE (gap) | — | — | Registry | — |
| `Gas@type` (M); `CompositionPurity`, `GasCompositionCriteria`, `GasUsage` (O); v81 `@fossilAuxiliaryDeducted`, `GasCriterion`, `ETSESREligibility` (O) | NONE (gap) | — | Fact Sheet 22 (not read) | Registry | `ETSESREligibility` bears on ETS claims (§5.4) |
| `CalorificValue@type`, `@unit` (M for Hydrogen; value optional; `MJ/kg` default, `MJ/m3`, `MJ/l`) | NONE (gap) | Would allow MWh ↔ kg when a value is given | — | Registry | The MWh → kg gap |
| `GHGEmissions/GHGEmissionProduced` (O; `@unit` default `Kg CO2eq/MWh`; `@calculationMethod`, Fact Sheet 24) | `lot.characteristics.ghg_intensity_gco2e_mj` (lots only). Inputs: NONE (gap) | kg CO2eq/MWh × 1000 / 3600 = g CO2eq/MJ. Any other unit is refused | GEX requires ≥ 0; SD03 allows negative values | Registry | Whether a GO's figure may feed a lot |
| `GHGEmissions@GHGSavingsCriteriaMet` (O) | NONE (gap) | — | — | Registry | — |
| `Sustainability@sustainabilityCriteriaMet`, `@certificationBody`, `RequirementReference`, `Scheme`, `AuditReport` (O) | `Scheme` → `coc_period.scheme`. Others: NONE (gap) | Scheme name mapping NOT CONFIRMED | Equals the period's scheme | Registry | D5 |
| v81 `BiddingZone` (O, EnergyGas and Hydrogen; N for Elec.), with `@zone90percentageRES`, `@zoneLowEmission` | `coc_facility_profile.bidding_zone`, **if** the zone named is the electrolyser's. Closest additionality bases: `GRID_RENEWABLE_SHARE`, `GRID_LOW_EMISSION` | EIC code vs GEX free text: NONE (gap) | Equal to the facility's zone | Registry | SD03: the zone "to which the Output was injected". For a hydrogen GO, whether this is the electrolyser's zone is **NOT CONFIRMED**. GEX does not evaluate the grid alternatives (099) |
| v81 `RedispatchingCriteriaMet` (O; "RFNBO DA Art. 4.3") | NONE (gap). `IMBALANCE_REDUCTION` is not confirmed to be the same criterion | — | — | Registry | Counsel or the certifier |
| v81 `PowerPurchaseAgreement@startDate`, `@endDate`, `@buyerID` (O) | `coc_ppa`. Dates and buyer: NONE (gap) | — | `buyerID` is "usually the company registration number" | Registry | — |
| `SendingAccountID`, `ReceivingAccountID` (Body, M; A2.5) | NONE (gap) | Claim: the holder | Check character (A2.5) | Registry | — |
| `Label`, `AdditionalInfo`, `DisseminationLevel`, cogeneration and efficiency fields | Not mapped | — | — | — | Not needed for custody |

---

## 3. UDB adapter — Exchange Model XSDs v3.5 and field specifications

**Scope.** These are the UDB's own transactions. They reach GEX through one of two routes; neither
exists today:
- a named asynchronous AS4 retrieval (`EOGetTransaction`, `EOGetPOSList`, `GetCertificate`) by an
  onboarded Access Point or service provider;
- a party's export.

The model is marked **DRAFT**: pin v3.5. Field names are as in the field specifications. Where two
sheets spell a field differently, both are given.

**The XSD is the authority for element names (found 16 Nov).** It differs from the specification
sheets in places, for example `NON_RECOGNISED_VS` (sheets: `NON_RECOGNISES_VS`) and
`GHG_MEASURING_UNIT_ACR`. It also nests elements under `EO_TRANSACTION` and
`EO_TRANS_DETAIL_MATERIALS`. An extractor reads the XSD names; the offline fixtures validate
against the XSD.

| External field | GEX field | Conversion rule | Validation | Evidence source | Unresolved dependency |
|---|---|---|---|---|---|
| `POS_ID` (`EOGetTransactionResponse`, the `EOGetPOSList` request, `EOUpdatePOS`); `POSID` (`EOAddTransactionResponse`; `POSDetail` in the GetPOSList response sheet) | NONE (gap). Today only free text in `coc_input.evidence_ref` with `evidence_kind = POS` | Identity = (UDB, PoS, id); scope not stated (§1) | String50 | UDB | UDB Dictionary |
| `ORIGINAL_POS`, `PREVIOUS_POS` (per material and delivery split) | NONE (gap) | Lifecycle: lineage edges between PoS | Quantities along the lineage do not exceed their parents' (§5.3) | UDB | — |
| `TRANSACTION_ID` | NONE (gap) | Lifecycle: a transaction event | String50 | UDB | — |
| `QUANTITY` (Number(10,3) in `EOGetTransactionResponse`; String10 in `EOAddTransactionRequest`; Number(13,6) in notifications) and `MEASURE_UNIT` (`MeasuringUnitEnum`: `gal`, `kg`, `L`, `L20`, `LA`, `MT`, `MWh`, `SCM`, `SL`, `t`, `KWh`, `Nm3h`) | `coc_input.quantity`, `coc_input.unit` | `kg` → kg; `t` → kg × 1000; `MWh` → MWh; **`KWh` → GEX `kWh`** (spelled differently; map explicitly, × 0.001). **`MT` meaning NOT CONFIRMED: refuse.** Volumes (`gal`, `L`, `L20`, `LA`, `SCM`, `SL`, `Nm3h`): refuse (G-22, D8) | The unit fits `input_type` (`ck_coc_input_unit`); quantity > 0 | UDB | `MT`, `L20` |
| `MATERIAL_CODE` (String10), `MATERIAL_CATEGORY`, `MATERIAL_NAME` | `coc_input.input_type` (mapping NOT CONFIRMED) | — | — | UDB | **READ 16 Nov:** the fuel-code guide (rev. June 2025) lists `RFNBO01` hydrogen and `RFNBO02` ammonia, headed "to be confirmed". Whether `MATERIAL_CODE` carries a fuel code is NOT established (research doc, item 5) |
| `SELLER_ECONOMIC_OPERATOR_NUMBER`, `BUYER_ECONOMIC_OPERATOR_NUMBER`, `ECONOMIC_OPERATOR_NUMBER` (e.g. `EOXX00000001`) | NONE (gap): no mapping to GEX companies | Claim: the holder | The buyer is the company owning the consuming project | UDB | — |
| `SELLER_CERTIFICATE_NUMBER`, `BUYER_CERTIFICATE_NUMBER`; `CERTIFICATE_NUMBER`, `CERTIFICATE_BODY_NUMBER`, `CERT_DATE_FROM`, `CERT_DATE_TO`, `VALIDITY_STATUS` (`EOCertificate`) | `product_certificate.reference`, `body`, `valid_from`, `valid_until` (116). `lot.characteristics.certificate_id` (lots) | Claim: an operator's certification (no allocatable quantity) | `TRADE_DATE` within `CERT_DATE_FROM`..`CERT_DATE_TO` (the spec's own rule); `VALIDITY_STATUS` active | UDB | 116's uniqueness gap (§5.1) |
| `TRADE_DATE`, `LOADING_DATE`, `DELIVERY_DATE` | `coc_input.received_on` (proposed: `DELIVERY_DATE`) | Date | Inside the input's period (097) | UDB | Which date the certifier accepts |
| `COUNTRY_OF_ORIGIN`, `COUNTRY_OF_PRODUCTION` | `lot.characteristics.country_of_origin` (lots). Inputs: NONE (gap) | — | ISO 2 letters | UDB | — |
| `METHOD_TYPE`; `GHG_TOTAL_VALUE` / `GHG_TOTAL_VALUE_TRANSACTION`; `GHG_MEASURE_UNIT` / `GHG_MEASURE_UNIT_ACR` (`GHGUnitEnum`: `gCO2eq/MJ`, `kgCO2eq/DMT`); components `EEC`, `EL`, `EP`, `ETD`, `EU`, `ESCA`, `ECCS`, `ECCR` | `lot.characteristics.ghg_intensity_gco2e_mj` (lots). Inputs: NONE (gap) | `gCO2eq/MJ` unchanged; `kgCO2eq/DMT` refused | ≥ 0 | UDB | — |
| `SCHEME_OF_ORIGIN`, `CERTIFICATE_OF_ORIGIN`, `VOLUNTARY_SCHEME_NUMBER` (e.g. `VSXX0001`) | `coc_period.scheme`, `lot.characteristics.scheme`, `product_certificate.scheme` | VS number → scheme: NOT CONFIRMED | Equals the period's scheme | UDB | D5 |
| `PRODUCTION_PLANT_START_DATE`; `PROD_PLANT_DATE` | `coc_facility_profile.electrolyser_commissioning_date`, only if the plant is the electrolyser | Date | Equal, or flagged | UDB | — |
| `MASS_BALANCE_START_DATE`, `MASS_BALANCE_DURATION` (`MassbalanceDurationEnum`: 1, 12, 2, 3; the spec says "3 or 12") | `coc_period.period_start`; `coc_scheme_rule.max_period_days` | Unit NOT CONFIRMED (months, by inference) | The GEX period lies inside it | UDB | The XSD and the spec disagree |
| `MAX_CAPACITY_YEAR`, `REN_CAPACITY_YEAR`, `MAX_REN_CAPACITY_YEAR_UNITS` | NONE (gap) | — | — | UDB | — |
| `ENERGY_CONTENT`, `ENERGY_CONTENT_UNIT` (`MJ`, `MJ/kg`, `MJ/l`) | NONE (gap) | — | — | UDB | — |
| `STATUS`, `REJECT_REASON`; `POS_FLAG` | NONE (gap) | Proposal: only a complete PoS (`POS_FLAG` true) on a transaction not rejected may support a claim | — | UDB | Which statuses count |
| Notifications `TransactionBuyerNotification`, `TransactionSellerNotification` (`TRANSACTION_ID`, `STATUS`, `POS_ID`, `QUANTITY`, `MEASURE_UNIT`) | — | — | — | UDB | **OPEN:** whether they can support reconciliation |
| Temporal correlation, geographic correlation, additionality | correlation `temporal`, `geographic`, `additionality` (COMPUTED) | — | — | GEX metered records | **No UDB field.** The inspected schema does not expose the underlying correlation and additionality evidence; a UDB record alone does not independently demonstrate those checks |

---

## 4. G-REX (API manual v3.2, EEX France instance)

The manual names one request parameter, `accountNumber` (in its GET Account example), and the
filters `$top` and `$skip`. The field schemas are in each API's `swagger.json`, which has not been
read. **No G-REX certificate, transaction or cancellation field is confirmed.**

| External field | GEX field | Conversion rule | Validation | Evidence source | Unresolved dependency |
|---|---|---|---|---|---|
| `accountNumber` (request parameter) | NONE (gap) | Claim: the holder | — | G-REX | — |
| Certificate or cancellation ID: NOT CONFIRMED | NONE (gap) | — | — | G-REX | `swagger.json`; D5 |
| Quantity and unit: NOT CONFIRMED | `coc_input.quantity`, `unit` | — | — | G-REX | As above |
| Production period: NOT CONFIRMED | `coc_input.received_on` | — | — | G-REX | As above |
| Holder or beneficiary: NOT CONFIRMED | NONE (gap) | — | — | G-REX | As above |
| Cancellation purpose: NOT CONFIRMED | NONE (gap) | — | — | G-REX | As above |
| Postman variables (`Token`, `RefreshToken`, `ClientId`, base URIs) | Not mapped | — | — | — | Authentication plumbing. A connector holds no party's token |

---

## 5. Double use of authentic evidence

### 5.1 The gap (checked in code at head 119)

- **`coc_input.evidence_ref` is free text.** The column is `text NOT NULL CHECK (length(evidence_ref) > 0)`
  (097). There is no unique index, no quantity check and no link to a registered document;
  `custody_ledger.record_input` refuses only an empty value. The hash chain is per period: it proves
  an input was not edited, not that its document is unused elsewhere.
- **So one genuine 100 MWh cancellation statement can back inputs in two periods, or in two companies'
  projects.** A document hash does not stop this, because the second use cites the same authentic
  file. A company can even type another company's statement id, so free text is an *assertion*, not a
  link (§5.10).
- **`coc_ppa.evidence_ref`:** the same gap. Only `ppa_ref` is unique, and only within one project.
- **`product_certificate` (116), checked 16 Nov:**
  - unique only on `(project_id, scheme, reference)`;
  - no quantity column;
  - `token_certificate_coverage.quantity_t` is nullable, in tonnes, and never summed or capped.

  116 provides status, scope and validity, so it can carry the Claim concept for evidence with no
  allocatable quantity. **It is not an allocation control.**
- **116's expiry is evaluated against today, checked 16 Nov.** `product_record.effective_state`
  returns `expired` once `valid_until < date.today()`, whatever date the coverage concerns, and the
  per-token listing summary uses it. `decide()` refuses to verify a certificate that has expired
  today, even for a batch dispatched while it was valid. Both are the historical false failure that
  §9.2 rules out. Reported here, not changed (§8 Q10).

### 5.2 The precedent

The code below was read; its tests exist but were not run for this draft.
- **Token citations (110), enforced by the database.** `coc_input_source_token_guard` locks the
  token and refuses inputs whose total would exceed `app_token_kg` (`COC_SOURCE_TOKEN_EXHAUSTED`). It
  requires the citing company to hold the token, SETTLED. `tokens_consumed_guard` refuses to RETIRE
  a cited token. Test: `test_upstream_proof_pg.py`.
- **Lot citations (101), enforced by the application only.** `custody_ledger._source_lot` locks the
  lot and refuses more than total − allocated − cited (`COC_SOURCE_LOT_EXHAUSTED`). No trigger backs
  it. Test: `test_custody_periods_pg.py`.

These show the pattern working for GEX's own lots and tokens. They do not show that it works for
external evidence: that needs its own tests (§10).

### 5.3 Invariants, and three operations kept apart

**What GEX can guarantee.** Within the records GEX controls, no confirmed allocation, and no
authorised reservation that is still unexpired, exceeds the eligible quantity at the granularity
an approved rule establishes. No attribute is allocated to two claims that an approved rule marks
incompatible.

**What GEX cannot guarantee.** That nobody has claimed the evidence outside GEX. The readout says so
(§5.4).

| Operation | What it does | What it consumes |
|---|---|---|
| **Reference** | A GEX record cites evidence | No quantity. It implies no ownership, eligibility or right to claim. It is subject to access permissions, which only a registered evidence record can carry (§5.10) |
| **Allocate** | A quantity of the evidence's eligible amount is assigned to one GEX claim | That quantity, under the approved rule's granularity. A correction is a linked reversal entry (§9.3) |
| **External transfer or cancellation** | Happens in the registry | GEX records it as a lifecycle event from evidence and never performs it (D6) |

**Granularity comes from the rule and the document, never from an assumption.**
- AIB: read `faceValue`; each certificate number is one certificate.
- Allocation below the unit the rule establishes is refused.
- Where the rule establishes no divisibility, the document backs one allocation of its whole
  eligible quantity or none (§5.8).

**Coverage checks, per adapter:**
- **AIB:** intervals of certificate numbers, keyed on the issuing registry encoded in the number
  (A2.3.3). Comparing ranges still has to be validated against the GS1 and EECS rules (§1).
- **UDB:** quantities along the PoS lineage (`ORIGINAL_POS`, `PREVIOUS_POS`), in the same material
  and unit. A parent and its child may both be referenced; what is refused is allocating more,
  across the lineage, than the root's eligible quantity.

**Across a conversion, quantities are never compared directly** (MWh against kg H₂, kg H₂ against kg
NH₃). The eligible output comes from an approved process model (§9.1).

### 5.4 Conflicts cross stages, schemes and claim types

- **Allowed:** electricity attributes flowing to hydrogen and on to ammonia. Each stage carries
  forward the attributes allocated to it and creates no new entitlement to the original quantity.
- **A possible conflict:** the same consumed attribute claimed independently somewhere else. For
  example, electricity GOs cancelled for a conversion and also claimed for disclosure, or an RFNBO
  quantity also claimed by another party through GO disclosure. The review reports that EU ETS rules
  address the latter. **READ 16 Nov:** Regulation (EU) 2018/2066 (consolidated 1 Jul 2024), Article 39(5), requires
  evidence that an RFNBO or RCF quantity is "not claimed to be used by anyone else", including through a guarantee-of-origin
  disclosure. **It is narrower than the review reported:** it covers an operator determining the RFNBO
  fraction of natural gas injected into a grid from purchase records. It is not a general rule for hydrogen or
  ammonia outside that route. Details in `GREENMESH_CONNECTORS_RESEARCH.md`, *Sources read 16 Nov*, item 3. **Flag:** the
  "anywhere in the connected chain" rule above rests on approved rule rows (§5.5), not on this article alone.
- **The rule:** refuse uses of the same attributes or eligible quantity that an approved rule marks
  incompatible, anywhere in the connected chain. With no rule, compatibility is not established.
- **The allocation method comes from the applicable scheme and process rules; it is never hard-coded.**
  The review reports that EU mass-balance rules (Regulation (EU) 2022/996) permit assigning intact
  sets of sustainability characteristics to withdrawals, with physical-share requirements only in
  particular cases. **READ 16 Nov, CONFIRMED:** Regulation (EU) 2022/996 (as originally published), Article 19(2)(j) and (i);
  see the research doc, *Sources read 16 Nov*, item 1. **Flag:** Article 19(2)(l) also sets a mass-balance period of
  3 months for most operators; GEX's period length is an unconfirmed scheme parameter (097), so §5.4 and §9 need
  that value from the certifier. Whether 2022/996 governs RFNBO is not established by this reading. GEX lots already carry one intact characteristics set
  each (097). v0.2's "proportional attributes" is withdrawn.
- **GEX sees only the evidence recorded in GEX.** A claim made outside GEX is invisible unless its
  evidence arrives.
- **Reconciliation across systems:** the review reports an AIB publication of 6 Nov 2026 proposing to
  link GO and PoS records. **READ 16 Nov, CONFIRMED:** aib-net.org/node/3515, "AIB publishes analysis on linking
  Guarantees of Origin and the Union Database" (6 Nov 2026), proposing shared identifiers and one coordinated cancellation
  process. It is a proposal, it concerns renewable gas, and the Union Database (not a registry of PoS issuers) is the
  PoS side. Details in the research doc, item 4.

### 5.5 Compatibility and scheme rules are approved data

A rule row carries:
- jurisdiction;
- intended use;
- the evidence kinds and lifecycle states it concerns;
- the verdict;
- divisibility and granularity, where it permits several allocations;
- the validity test: which dates or periods are assessed (§9.2);
- `valid_from` / `valid_to`;
- the authoritative source (document and clause);
- the approval status, the approver (§6) and the date.

**An empty rule table means eligibility not established, never implicit permission.** That is the
pattern of `rfnbo_rule` (099) and the reference registry (061).

### 5.6 Finding: `coc_scheme_rule`'s empty table

If no rule exists, `custody_ledger.open_period` refuses carry-forward, but it leaves period length
unchecked: an implicit permission. Reported, not changed (§8 Q5).

### 5.7 Provisional requests and reservations (JML, 16 Nov)

| Step | Effect |
|---|---|
| **Provisional allocation request** | Keeps the declared quantity and the evidence reference. **Consumes nothing** |
| **Potential overlap detected** | Flagged privately for authorised review. A requester in another tenant sees only that a review is pending |
| **Reservation** | Only by an explicit, authorised operation, with its authoriser, an expiry, and release conditions recorded. An expired or released reservation counts for nothing |
| **Confirmation** | Availability is rechecked atomically (lock, then sum) at confirmation. Within the tenant the refusal gives the authorised detail; across tenants it is the neutral text of §5.11 |

Where identity is unresolved, overlap detection is incomplete, and the request says so.

### 5.8 Q2 — settled (JML, 16 Nov 2026)

> **Several inputs may draw on one quantity-bearing document where approved rules permit that use
> and the eligible quantity reconciles within GEX.** Otherwise GEX keeps the evidence and the
> proposed links and confirms no allocation.

What this means in practice:
- **"Approved rules permit that use"** covers eligibility for the intended claim and divisibility at
  a stated unit (§5.5).
- **"Reconciles within GEX"** means confirmed allocations plus authorised, unexpired reservations do
  not exceed the eligible quantity in its eligible unit, among GEX's records (§5.3).
- **Claim conditions** are assessed at the dates and over the periods the rule requires (§9.2), not
  only "now".

### 5.9 Verification decisions and assurance

**VERIFIED is recorded per decision, not per document.** One document can face several checks, each
with its own authority:

| Check | Possible assurance | Who or what decides |
|---|---|---|
| Authenticity | A registry response, a validated signature, or a certifier's attestation | As the approved evidence policy admits (§6) |
| Quantity reconciliation | GEX's calculation against recorded allocations | GEX (computed) |
| Claim eligibility | An assessment under an approved scheme rule | The rule's approver, applied by GEX or the certifier |
| Extraction | Fields read from the document | GEX (computed): this establishes what the document *says*, not that it is authentic |

**Each decision records:**
- the check;
- the method;
- the verifier (person or system, with company);
- the scope (which quantity, period and claim);
- the timestamp;
- the supporting evidence (sha256 on file, registry response id);
- the rule version used;
- the result.

**A lender sees exactly what VERIFIED covers.** "Fields match; source authenticity pending" is a
legitimate state. Authenticity confirmed alone does not establish RFNBO eligibility. Decisions are
append-only. A reassessment is a new decision linked to the old one, never an overwrite (§9.2).

Today `evidence_pack.item` carries `label` (VERIFIED / DECLARED / MISSING) and `result`. It has no
method, verifier or rule-version fields beyond what individual items add (e.g. `rules_used`). That
gap is for the build, after approval.

### 5.10 References are assertions until resolved

- **Free text is an assertion, not an authorised link.** A user typing another company's identifier
  gets neither access nor a claim.
- **A registered evidence record is the prerequisite for a resolved, permission-controlled
  relationship.** Until one exists, the text is kept as an `UNRESOLVED_ASSERTION`.
- **No existence leak.** Lookups and duplicate checks answer identically for "exists in another
  tenant" and "unknown". The cross-tenant detail goes only to authorised review (§5.7, §8 Q2).

### 5.11 Cross-company identity and disclosure (JML, 16 Nov 2026)

**JML's decision:**
- Do not disclose another company's registration or holdings.
- Keep document identity separate from permission to allocate: **the first uploader gains no
  exclusive rights.**
- Allow legitimate shared references, and detect incompatible allocations privately.
- A refusal says exactly: **"This allocation cannot be confirmed. Request an evidence review."**
- The neutral wording must come with controls that prevent cross-company lookups and the disclosure
  of database errors.

**What that requires:**
1. **One evidence record per company, never a shared registration record.** The same authoritative
   identity uploaded by two companies gives two records, each visible only to its own company.
   - An **operator-side identity index** links them for private conflict detection only. Like 110's
     guards, it is reached through SECURITY DEFINER functions that return a decision, never rows.
   - No company reads it.
   - Neither upload has priority: allocation is decided by §5.3, §5.7 and §5.8, not by who uploaded
     first.
2. **No cross-company unique constraint on any table a company writes to.** PostgreSQL's
   duplicate-key error names the key ("Key (…)=(…) already exists"), so the constraint itself would
   disclose. Uniqueness across companies lives only in the operator-side index.
   - Every database error on these paths maps to the neutral text. The raw message goes to the audit
     log, never to the response.
3. **When detail may be given, and when the neutral text is used:**
   - **Detail** is given only where it derives entirely from what the requester submitted or already
     holds. Example: "the document names another holder", which the requester can read in its own
     upload. Within one company, its own conflicting requests (AC-04) are its own data.
   - **The neutral text** is used for every cause the requester cannot see into: a cross-company
     conflict, pending authenticity, a pending eligibility review, a reviewer hold. One cause must not
     have a wording of its own.
4. **The limit, stated honestly: neutral wording reduces inference; it does not remove it.** A
   requester whose own records are complete may still guess that a refusal has an outside cause.
   Further controls:
   - **The same response timing for every neutral cause.** Conflict detection must not be visibly
     slower or faster than other checks.
   - **Probing is audited and rate-limited.** Repeated refusals on IDs a company does not hold are
     recorded and reach authorised review.
   - **Lookups by identifier never return another company's records.** Search, autocomplete,
     "already registered" hints and duplicate warnings are scoped to the requester's own records
     (§5.10).
5. **The evidence review** is the authorised channel for the detail, under the reviewer read rule
   still to be decided (§8 Q2). The reviewer's confidentiality duty is still to be defined. Migration
   070's `information_barrier` (the CISO workspace) is a precedent; whether it fits this use has not
   been checked.

---

## 6. Accountable rule approvers — to be nominated by JML

Roles are proposed below; each named approver is for JML to nominate. No rule row, process model or
evidence policy is in force until its approver is named.

| Rule category | Proposed approving role | Named approver |
|---|---|---|
| Identifier scope (§1): what the specification states | Engineering research, reviewed by a second reader against the source | TO BE NOMINATED BY JML |
| Scheme rules: period length, carry-forward, granularity and divisibility, eligible evidence, validity tests | The scheme's certification body or the project's certifier | TO BE NOMINATED BY JML |
| Compatibility across claims and jurisdictions (RED, RFNBO DA, ETS, disclosure) | Counsel | TO BE NOMINATED BY JML |
| Evidence policy: acceptable authenticity routes (§5.9) | Certifier with counsel | TO BE NOMINATED BY JML |
| Process models and conversion factors (§9.1) | Independent engineer | TO BE NOMINATED BY JML |
| Unit and physical constants (calorific value, density) | Independent engineer (as D8's density row) | TO BE NOMINATED BY JML |
| Platform policy: provisional handling, reservations, disclosure, reviewer diagnostics, correction authority (§9.3) | JML | JML |

---

## 7. Preparatory work that does not wait for D5 (JML, 16 Nov)

**Schema research, reading only:**
- the UDB Dictionary and fuel-code guide;
- AIB Fact Sheets 4, 22, 24 and 25;
- GS1 Company Prefix rules;
- a G-REX `swagger.json` from the demo host, if reachable without a token;
- the texts the reviews cite: EUR-Lex ETS, Regulation (EU) 2022/996, ISCC EU 201 System Basics 4.1,
  and the AIB publication of 6 Nov 2026. **Read 16 Nov** (ISCC 201 v4.1 answers 404; ISCC EU 203 v4.2 read
  instead). Results: `GREENMESH_CONNECTORS_RESEARCH.md`, *Sources read 16 Nov*. The UDB Dictionary and fuel-code guide are read too.
  ISCC (EU 203 v4.2, §3.1): the supplier must hold a valid certificate at dispatch **and** at the issue of the
  sustainability declaration, and the recipient at receipt and issue. **Flag:** §9.2 item 1 names dispatch among
  several dates; the ISCC rule row will need the declaration and receipt dates as well.

**Offline fixtures** (`backend/tests/fixtures/connectors/`; synthetic, TEST only; see its README).
- **Built 16 Nov:**
  - 3 AIB files, v81-shaped and checked against SD03's mandatory elements only (the AIB XSD files
    were not obtained);
  - 3 UDB files, validated against the vendored v3.5 XSDs (unmodified, sha256-pinned);
  - `manifest.json`;
  - `tests/test_connector_fixtures.py`, which needs `lxml`, declared 16 Nov.
- **v0.3 adds** the acceptance cases of §10 that offline fixtures can express. Counts are in the
  change log. Extraction and matching code is not built; it waits for approval.

---

## 8. Open questions for JML

1. **Approvers:** the nominations in §6.
2. **Reviewer diagnostics:** who may see cross-tenant overlap detail, through which read rule, and
   under which confidentiality duty (§5.11)? The disclosure rule itself was decided on 16 Nov (§5.11).
3. **Existing inputs:** record the live free-text `evidence_ref` values as `UNRESOLVED_ASSERTION`
   evidence (§5.10), or leave them outside the ledger with a label?
4. **Lot citations:** move the 101 cap into a trigger, to match 110?
5. **`coc_scheme_rule` (§5.6):** approve a fix for the unchecked period length?
6. **116 uniqueness:** flag the same scheme reference registered in two projects for review?
7. **MWh → kg for hydrogen:** an approved calorific-value row, or no MWh evidence against kg inputs?
8. **Partial overlap:** may the non-overlapping part of a partly overlapping document be allocated
   on its own (`aib_allocation_overlap_cross_tenant`)?
9. **Reservations (§5.7):** who may authorise one, the default expiry, and the release conditions.
10. **116's read-time expiry (§5.1):** approve a fix so status is assessed at the coverage's event
    dates (§9.2)?
11. **Material corrections (§9.3):** the materiality threshold that requires four eyes, and who the
    second approver may be.

---

## 9. Acceptance criteria

### 9.1 Conversion and yield

1. **Unit conversion and yield are separate steps.**
   - Unit conversion changes how a quantity of one thing is expressed (kWh → MWh; Nm³ H₂ → kg H₂
     with an approved density).
   - Yield turns inputs into outputs (MWh → kg H₂; kg H₂ + kg N₂ → kg NH₃).
   - One factor never does both.
2. **The eligible output comes from an approved process model.** That model covers the required
   inputs, the yields, the losses, and the inputs that bring no eligible attributes (for example N₂).
   - Example: ammonia output mass legitimately exceeds hydrogen input mass, and the control does not
     refuse it.
3. **Quantities in different dimensions are never compared directly.**
4. **Which inputs set the eligible output follows the model's rule.** GEX's custody credit (097) uses
   the minimum, across required inputs, of certified input divided by the factor in force. Whether
   that is the applicable rule for a given scheme is for the scheme-rule approver.
5. **A factor that is declared but not approved gives a DECLARED eligible output.** Today every 097
   conversion factor is the producer's declaration with a source string; none is approved by an
   independent engineer (§6).
6. **Downstream allocations carry forward the attributes allocated upstream.** Their total eligible
   output never exceeds what the process model gives for the upstream allocations.

### 9.2 Validity events: expiry, suspension, withdrawal

1. **Validity is assessed at the dates and over the periods the applicable rule requires.**
   - The relevant dates may be production, dispatch, receipt, declaration or cancellation.
   - Continuing conditions are assessed over their period.
   - The rule states which (§5.5); without one, validity is not established.
2. **Ordinary expiry stops new uses whose relevant date falls after it.** It does not invalidate a
   decision whose relevant dates were inside the validity period.
3. **Suspension and withdrawal are assessed against their reason, scope and effective date.**
   - Prospective: affects only uses with relevant dates on or after the effective date.
   - Retrospective: triggers reassessment of every affected allocation and downstream claim in its
     scope.
4. **Historical decisions are preserved.** A reassessment is a new, linked decision with its own
   date, rule version and result. The pack shows both.
5. **While a reassessment is pending**, the affected allocation's quantity is not restored for other
   use, and the downstream claims show `REASSESSMENT_PENDING`.
6. **Gate evidence is different.** A lapsed permit or insurance matters *now* (rules 4.6.0); custody
   evidence is assessed at its event dates. The two must not share one expiry rule.
7. **116 today evaluates expiry against today** (§5.1). Meeting criterion 2 needs a code change,
   which is not made.

### 9.3 Correction

1. **No restoring quantity while dependents are active.** An allocation's quantity becomes available
   again only by an authorised reversal entry, linked to the allocation, after every dependent has
   been handled. Dependents include an input in a closed period, a minted or cited token, a generated
   pack, and a registry file.
2. **Generated and submitted are different states.**
   - An export file that was only generated (a draft) is superseded by a replacement; no external
     acknowledgement is needed.
   - A file whose **submission is evidenced** puts the correction in `CORRECTION_PENDING_EXTERNALLY`
     until the external acknowledgement is recorded. The quantity stays restricted until then.
   - GEX never infers submission from a download.
3. **Replacing a pack** is a new pack that names the one it supersedes. A withdrawal notice is
   recorded where the old pack was relied on.
4. **Material corrections need four eyes:** a proposer and a different approver of the same company,
   with the authority JML defines (§8 Q11). This is a control still to specify. TRADE_CONFIRM's rules
   are a precedent, not the specification.
5. **Every correction keeps the full audit trail.** Entries are append-only and nothing is edited in
   place.

---

## 10. Acceptance cases

Given/when/then, against the rules above. **Fixture** names the offline case in
`backend/tests/fixtures/connectors/manifest.json`. "Doc only" means an offline fixture cannot stand
in; the reason is given.

| ID | Theme | Given | When | Then | Fixture |
|---|---|---|---|---|---|
| AC-01 | Partial allocation | 50-certificate electricity GO; an approved rule makes it eligible and divisible at whole certificates | Inputs request 30 and 20 in two periods; then a third requests 1 | 30 and 20 are both confirmable; the third is refused, with detail within the tenant | `ac01_partial_allocation_divisible` |
| AC-02 | Partial, divisibility not established | The same GO; the rule makes it eligible but states no divisibility | Request 30; separately, request the whole 50 | 30: not confirmable. 50 to one input: confirmable | `ac02_partial_without_divisibility` |
| AC-03 | Below the unit | Divisible at whole certificates | Request 30.5 MWh | Refused below the unit | `ac03_below_unit` |
| AC-04 | Conflicting requests, same tenant | Divisible GO of 50 | Two provisional requests of 30 | The second is flagged with detail; confirming the first succeeds; confirming the second is refused with detail | `ac04_conflict_same_tenant` |
| AC-05 | Conflicting requests, across tenants | Two GOs overlapping by 10 certificates; A's allocation confirmed | B requests its 40 | Flagged privately; B sees review pending; confirmation refused neutrally | `aib_allocation_overlap_cross_tenant` |
| AC-06 | Concurrent confirmation | Two provisional requests of 30 on 50 | Both confirmed at once | Exactly one confirms; the other is refused (atomic recheck) | `ac06_concurrent_confirmation` |
| AC-07 | Historical expiry | Seller certificate valid 1 Jan–30 Jun 2026; dispatch 15 Mar; allocation verified 20 Mar | Reassessed on 1 Sep (after expiry); a new request for a dispatch on 1 Aug | The March decision is preserved and still valid at its event; the August request is not valid at its event and not confirmable | `ac07_historical_expiry` |
| AC-08 | Continuing condition | The rule requires validity over the whole production period (March); certificate valid until 20 Mar | Request for March production | Not valid over the period; not confirmable. One favourable date is not enough | `ac08_continuing_condition` |
| AC-09 | Retrospective withdrawal, in scope | Confirmed allocation for a dispatch on 15 Mar; withdrawal effective 1 Feb, same scope | The withdrawal is recorded | Reassessment required; the historical decision preserved; downstream reassessment pending; quantity stays restricted | `ac09_retrospective_withdrawal` |
| AC-10 | Withdrawal not affecting | The same allocation; withdrawal effective 1 May, prospective | The withdrawal is recorded | Considered, no change; the decision is unaffected | `ac10_withdrawal_prospective` |
| AC-11 | Prospective suspension | Suspension from 1 Apr | Existing use (dispatch 15 Mar); new request (dispatch 10 Apr) | The existing use is unaffected; the new request is not valid at its event | `ac11_suspension_prospective` |
| AC-12 | Correction, no dependents | Confirmed allocation of 50; nothing downstream | A material reversal, proposed and approved by two people | Reversed; quantity restored; both entries kept | `ac12_correction_no_dependents` |
| AC-13 | Correction with dependents | The allocation feeds a closed period and a generated pack | A reversal is proposed | Refused while dependents are active; quantity restricted | `ac13_correction_with_dependents` |
| AC-14 | Externally pending, draft only | A registry file generated; no submission evidence | Correction | The draft is superseded; no external acknowledgement needed | `ac14_correction_draft_export` |
| AC-15 | Externally pending, submitted | Submission evidence recorded for the registry file | Correction | Correction pending externally; acknowledgement required; quantity restricted. A download alone never counts as submission | `ac15_correction_submitted_export` |
| AC-16 | Free-text assertion | Company A types an id that exists only in company B's registered evidence | Input recorded | Kept as an unresolved assertion; no access, no allocation; the answer is indistinguishable from an unknown id | `ac16_free_text_assertion` |
| AC-17 | Assurance per decision | Fields extracted and matched; registry confirms authenticity; no eligibility rule | The pack is built | Authenticity VERIFIED (method, verifier, scope, time, evidence, rule version); quantity VERIFIED (computed); eligibility not established; the claim is not VERIFIED | Doc only: needs a registry response, which an offline fixture must not fake |
| AC-18 | Conversion and yield | 50 MWh electricity allocated; an approved process model for H₂ and then NH₃ | Eligible outputs computed | H₂ from the model; NH₃ mass may exceed H₂ mass; no direct MWh-to-kg comparison; with only declared factors the output is DECLARED | Doc only: needs a process model, which none approved yet provides; GEX's own conversion check has tests in `test_custody_periods_pg.py` |
| AC-19 | Shared reference, no priority | Company A and company B each upload the same electricity GO (A is its holder) | Both reference it; B later requests an allocation | Two evidence records, one per company, neither visible to the other; neither upload has priority. B's refusal may say the document names another holder, since that comes from B's own upload | `ac19_shared_reference_no_priority` |
| AC-20 | No disclosure through errors or lookups | B's allocation conflicts with A's confirmed allocation; B also searches by the identifier | B confirms; B searches | B gets exactly "This allocation cannot be confirmed. Request an evidence review.", with no database message and the same timing as other neutral causes. The search returns only B's own records. The probe is audited | Doc only: needs the implementation, because errors, timing and search cannot be shown by fixtures |

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 15 Nov 2026 | First draft: AIB v80/v81, UDB v3.5, G-REX v3.2; the double-use gap; a proposed evidence allocation ledger |
| 0.2 | 16 Nov 2026 | After two reviews (JML accepted the direction):<br>• Identifier scope recast as engineering research (§1), with the SD03 Annex A facts.<br>• Interim identity rule: a GEX internal ID; authoritative identity separate from provenance; unresolved identity recorded, not refused.<br>• The common contract (§0): shared integrity controls versus adapter interpretation.<br>• Reference, allocate and external transfer/cancel kept apart.<br>• No hard-coded 1 MWh.<br>• Conflicts across stages, schemes and claim types; parent and child evidence allowed.<br>• Compatibility as approved data: empty means not established.<br>• Provisional requests recorded without reserving capacity; neutral refusals across tenants.<br>• Approver roles (§6); preparatory work (§7).<br>• 116 inspected in code (§5.1).<br>• Finding §5.6 (`coc_scheme_rule` period length).<br>• Withdrawn from v0.1: "one certificate, one input"; refusing a PoS with its descendant; naming the overlap in a refusal; "unknown issuer cannot register"; comparing ranges "within the same registry" (now: the issuing registry encoded in the number) |
| 0.2 (addendum) | 16 Nov 2026 | Offline fixtures built (§7). The UDB XSD is the authority for element names (§3). The AIB XSD files were not obtained. Q8 revised |
| 0.3 | 16 Nov 2026 | JML's corrections applied:<br>• Q2 settled (§5.8).<br>• GEX's guarantee limited to its own records (§5.3).<br>• Reservations need authorisation, expiry and release (§5.7).<br>• Verification decisions with their assurance, per decision (§5.9).<br>• Free text treated as an assertion (§5.10).<br>• Acceptance criteria for conversion and yield, validity events, and correction (§9).<br>• 18 acceptance cases (§10), 16 of them as offline fixtures (manifest now 26 cases; `test_connector_fixtures.py` 69 tests, +31, run alone, six new breaks each caught).<br>• Code checked: 116 evaluates expiry against today (§5.1, Q10).<br>• Withdrawn from v0.2: "proportional attributes" (allocation method now from scheme rules); "downstream never exceeds upstream" (dimensionally wrong; now the process model); "expiry cancels downstream" (now event-date validity and reassessment); "nothing contradicts" (now separate decisions per check); "an export blocks correction" (now generated versus submitted).<br>• New questions Q9–Q11 |
| 0.3 (addendum) | 16 Nov 2026 | §5.11 cross-company identity and disclosure (JML's decision on uniqueness across companies): one evidence record per company; an operator-side identity index; no cross-company unique constraint; the exact neutral refusal text; detail only from the requester's own data; the inference limit stated; same timing; probing audited. AC-19 (fixture), AC-20 (doc only). Q2 narrowed. Manifest 27 cases; `test_connector_fixtures.py` 73 tests (+4), run alone; four breaks each caught |
| 0.3 (sources) | 16 Nov 2026 | Four reviewer citations and the UDB fuel-code guide read; the REPORTED, NOT READ labels in §3, §5.4 and §7 replaced (research doc, *Sources read 16 Nov*). §5.4 and §9.2 text unchanged; flags added where a source is narrower or adds a parameter |
