# Connector fixtures (offline, synthetic, TEST only)

These fixtures prepare for extraction and matching of external evidence: AIB EECS certificates and
UDB transactions. They **prove nothing about any live registry**. No extraction or matching code
exists yet; `manifest.json` states, case by case, what that code must do under the rules of
`docs/GREENMESH_CONNECTOR_FIELD_MAPPING.md` v0.3 (§10 lists the acceptance cases). That draft awaits JML's approval, so the expected
outcomes may still change.

## What is synthetic

Everything. No real party, registry, account, device, certificate, PoS or scheme appears.
- **AIB certificate numbers** start with the prefix `9999999` (30 digits). Registries are
  `9999999000001` / `…002`, the issuing body is `99` and the country is `ZZ` (an ISO user-assigned
  code, not a country).
- **Account-holder check characters and GSRN check digits are not computed.** SD03's algorithm was
  not fully read, so a validator of check characters would reject these.
- **UDB identifiers** start with `TEST-`, `EOTEST`, `VSTEST` or `SPTEST`.
- **Compatibility rules** in the manifest (`TEST-RULE-00x`) use abstract intended uses
  (`TEST_USE_…`). **They are not legal or scheme positions.**

## Where the shapes come from

| Source | Files | How they are checked |
|---|---|---|
| UDB Exchange Model XSDs v3.5 (DRAFT), vendored in `udb/xsd_v3.5/`, unmodified; URL and sha256 in `manifest.json` | `udb/*.xml`, shaped on the public sample `EOGetTransactionResponse.xml` | Validated against the vendored XSDs (`test_connector_fixtures.py`) |
| AIB-EECS-SD03 HubCom 9.1: v81 tables (B4.3) and B3 examples | `aib/*.xml` | Against SD03's mandatory elements for the carrier, by the test. **Not against an XSD**: SD03 points to an AIB page for the XSD files, and it answered 404 on 15 Nov 2026 |

Notes found while building them:
- The UDB element names in the XSD differ in places from the field-specification sheets, for
  example `NON_RECOGNISED_VS` and `GHG_MEASURING_UNIT_ACR`. **The XSD is the authority for element
  names.**
- The public UDB sample `GetCertificateResponse.xml` does not validate against its own v3.5 schema
  (`IN_MATERIAL_TECH_PROD_PATH` is not expected there).

## Rules

- **Read by tests only.** Nothing under `app/` may read these files: the test checks this.
- **Every fixture file is used by at least one case**, and every case's file exists.
- **Never replace a synthetic value with a real one.** Real evidence never goes into the
  repository.
