# GEX Menu Architecture Views

Generated from local `frontend/src/config/menuArchitecture.ts`. This supersedes the earlier persona-only SVG because it enumerates actual tabs, sections, links, role filters, gate locks, and route registration.

## Interaction Model

- `TopBar` renders five universal tabs from `MENU_TABS`: Projects, Commercial, Finance, Compliance, Operations.
- Hover or click opens `TopBarDropdown`.
- `isVisible(item, role)` filters items by company type, business function, service type, and capability-derived company types.
- Dropdown items are grouped by `section`; blank sections render first without a header.
- `gate_prerequisite` marks a screen as potentially locked. `useGateAccess` uses backend screen-gates first, then menu-derived fallback. Lock threshold is 60%.
- Selecting an unlocked item calls `navigate(item.path)` and closes the dropdown.
- CISO is separate from `MENU_TABS`; it is password-gated and uses `CISO_ITEMS`.

## Route Registration Gaps

All menu paths are registered in `App.tsx`.

## Reused Paths / Aliases

| Path | Menu entries |
|---|---|
| `/bankability-scores` | Projects:Status &amp; Blockers<br>Finance:Bankability Status |
| `/finance-plant-builder` | Projects:Cost Basis (CAPEX / LCOF)<br>Finance:Cost Basis (CAPEX / LCOF) |
| `/plant-data` | Projects:Plant Telemetry<br>Operations:Plant Telemetry |
| `/producer-bankability` | Projects:Production Roadmap<br>Operations:Construction Progress |
| `/reports` | Projects:Evidence Upload<br>Compliance:Decision Twin (RFNBO/RED III)<br>Compliance:Audit Trail<br>Compliance:Environmental &amp; ESG<br>Operations:Performance Matrix |
| `/capacity` | Commercial:GreenMesh<br>Operations:Logistics &amp; Shipping |
| `/cert-readiness` | Compliance:Certification Readiness<br>Compliance:Certification Distance |
| `/finance-timeline` | Operations:Project Timeline<br>Operations:Milestones &amp; Drawdown |

## All Menus And Links

### Projects

| Section | Label | Path | Visible To | Gate | New | Route |
|---|---|---|---|---|---|---|
| Default | Dashboard Projects | `/dashboard` | ALL |  |  | registered |
| Default | My Projects | `/projects` | ALL |  |  | registered |
| Default | Task Flow | `/finance-dashboard` | ALL |  |  | registered |
| Default | Status & Blockers | `/bankability-scores` | ALL |  |  | registered |
| Default | Challenge Review | `/adversarial-review` | ALL |  | yes | registered |
| ENGINEERING | Cost Basis (CAPEX / LCOF) | `/finance-plant-builder` | PRODUCER / ENGINEERING; THIRD_PARTY / ENGINEER; THIRD_PARTY / EQUIPMENT |  |  | registered |
| ENGINEERING | Plant Telemetry | `/plant-data` | PRODUCER / ENGINEERING; PRODUCER / OPERATIONS; THIRD_PARTY / ENGINEER |  |  | registered |
| ENGINEERING | Production Roadmap | `/producer-bankability` | PRODUCER / ENGINEERING; PRODUCER / OPERATIONS; THIRD_PARTY / ENGINEER |  |  | registered |
| ENGINEERING | Evidence Upload | `/reports` | PRODUCER; THIRD_PARTY / CERTIFIER |  |  | registered |

### Commercial

| Section | Label | Path | Visible To | Gate | New | Route |
|---|---|---|---|---|---|---|
| Default | Commercial Overview | `/marketplace` | PRODUCER / COMMERCIAL; OFFTAKER / COMMERCIAL; OFFTAKER / EXECUTIVE |  |  | registered |
| Default | Purchase | `/offtaker-supply` | OFFTAKER |  |  | registered |
| Default | Sales | `/finance-demand` | PRODUCER / COMMERCIAL; PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK |  | yes | registered |
| Default | Offtake Quality | `/offtake-quality` | PRODUCER / COMMERCIAL; PRODUCER / FINANCE_TREASURY; OFFTAKER / COMMERCIAL; THIRD_PARTY / BANK | G4 |  | registered |
| NEGOTIATION | Matching Engine | `/matching` | PRODUCER / COMMERCIAL; OFFTAKER / COMMERCIAL |  |  | registered |
| NEGOTIATION | RFQ Management | `/trader-dashboard` | PRODUCER / COMMERCIAL; OFFTAKER / COMMERCIAL; OFFTAKER / FINANCE_TREASURY |  |  | registered |
| NEGOTIATION | Contracts | `/contracts` | PRODUCER / COMMERCIAL; PRODUCER / FINANCE_TREASURY; OFFTAKER; THIRD_PARTY / BANK; THIRD_PARTY / LEGAL |  |  | registered |
| NEGOTIATION | Term Sheet Tracker | `/term-sheet` | PRODUCER / FINANCE_TREASURY; PRODUCER / COMMERCIAL; OFFTAKER / EXECUTIVE; OFFTAKER / FINANCE_TREASURY; THIRD_PARTY / BANK; THIRD_PARTY / LEGAL | G4 |  | registered |
| MARKET DATA | Counterparties | `/settlement` | PRODUCER / COMMERCIAL; OFFTAKER / COMMERCIAL |  |  | registered |
| MARKET DATA | GreenMesh | `/capacity` | PRODUCER / COMMERCIAL; PRODUCER / OPERATIONS; THIRD_PARTY / LOGISTICS |  |  | registered |

### Finance

| Section | Label | Path | Visible To | Gate | New | Route |
|---|---|---|---|---|---|---|
| Default | Bankability Status | `/bankability-scores` | ALL |  |  | registered |
| STRUCTURING | Sensitivity Analysis | `/dscr-sensitivity` | ALL |  |  | registered |
| STRUCTURING | Price Lineage | `/pricing-lineage` | ALL |  |  | registered |
| Default | Capital Stack | `/capital-stack` | PRODUCER / FINANCE_TREASURY; PRODUCER / EXECUTIVE; THIRD_PARTY / BANK | G5 |  | registered |
| Default | Covenants | `/covenants` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK |  |  | registered |
| STRUCTURING | Cost Basis (CAPEX / LCOF) | `/finance-plant-builder` | PRODUCER / FINANCE_TREASURY; PRODUCER / EXECUTIVE; THIRD_PARTY / BANK |  |  | registered |
| STRUCTURING | Gap Analysis | `/finance-gaps` | PRODUCER / FINANCE_TREASURY; PRODUCER / EXECUTIVE; THIRD_PARTY / BANK | G5 | yes | registered |
| STRUCTURING | Instrument Catalog | `/finance-instruments` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK |  | yes | registered |
| STRUCTURING | Instrument Compatibility | `/instrument-compatibility` | PRODUCER / FINANCE_TREASURY; PRODUCER / COMMERCIAL; OFFTAKER / FINANCE_TREASURY; THIRD_PARTY / BANK; THIRD_PARTY / INSURER |  | yes | registered |
| STRUCTURING | Package Builder | `/finance-package` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK |  | yes | registered |
| STRUCTURING | Risk Allocation | `/finance-risk-matrix` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK; THIRD_PARTY / INSURER |  | yes | registered |
| STRUCTURING | Structuring Timeline | `/finance-structuring-timeline` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK |  | yes | registered |
| STRUCTURING | Spend Wave (Pre-FID) | `/finance/spend-wave` | PRODUCER / FINANCE_TREASURY; PRODUCER / EXECUTIVE; THIRD_PARTY / BANK |  | yes | nested /finance route |
| STRUCTURING | Drawdown Timeline | `/finance/drawdown-timeline` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK | G10 | yes | nested /finance route |
| STRUCTURING | DFI Dashboard | `/finance/dfi-dashboard` | PRODUCER / FINANCE_TREASURY; PRODUCER / EXECUTIVE; THIRD_PARTY / BANK |  | yes | nested /finance route |
| STRUCTURING | Information Lineage | `/finance/lineage` | PRODUCER / FINANCE_TREASURY; PRODUCER / EXECUTIVE; THIRD_PARTY / BANK |  | yes | nested /finance route |
| EXPORT | Banker's Snapshot | `/bankability-snapshot` | PRODUCER / FINANCE_TREASURY; PRODUCER / EXECUTIVE; THIRD_PARTY / BANK | G8 |  | registered |
| EXPORT | IC Pack Builder | `/ic-pack` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK | G10 |  | registered |
| GATING | Insurance Schedule | `/insurance-schedule` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK; THIRD_PARTY / INSURER | G7 |  | registered |
| GATING | Coverage Lines (CAR/EAR/DSU/BI) | `/insurance-coverage` | THIRD_PARTY / INSURER; PRODUCER / FINANCE_TREASURY | G7 |  | registered |
| GATING | Asset & Exposure Register | `/insurance-assets` | THIRD_PARTY / INSURER; PRODUCER / FINANCE_TREASURY |  |  | registered |
| EXPORT | Transfer Readiness | `/transfer-readiness` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK |  |  | registered |
| EXPORT | Data Room | `/data-room` | PRODUCER / FINANCE_TREASURY; PRODUCER / COMPLIANCE_LEGAL; OFFTAKER / COMMERCIAL; THIRD_PARTY / BANK; THIRD_PARTY / INSURER; THIRD_PARTY / LEGAL; THIRD_PARTY / CERTIFIER | G10 |  | registered |
| DEAL ROOM | Approval Queue | `/approval-queue` | PRODUCER / FINANCE_TREASURY; PRODUCER / EXECUTIVE; OFFTAKER / EXECUTIVE; THIRD_PARTY / BANK | G10 |  | registered |
| DEAL ROOM | Commitment Signing | `/commitment-signing` | PRODUCER / FINANCE_TREASURY; PRODUCER / COMMERCIAL; OFFTAKER / COMMERCIAL; OFFTAKER / FINANCE_TREASURY; OFFTAKER / EXECUTIVE; THIRD_PARTY / BANK | G10 |  | registered |
| DEAL ROOM | Commitment Verifier | `/commitment-verifier` | ALL |  |  | registered |

### Compliance

| Section | Label | Path | Visible To | Gate | New | Route |
|---|---|---|---|---|---|---|
| Default | Certification Readiness | `/cert-readiness` | PRODUCER / COMPLIANCE_LEGAL; PRODUCER / ENGINEERING; THIRD_PARTY / CERTIFIER; OFFTAKER / COMPLIANCE_LEGAL |  |  | registered |
| Default | Certification Distance | `/cert-readiness` | PRODUCER / COMPLIANCE_LEGAL; OFFTAKER / COMPLIANCE_LEGAL; OFFTAKER / COMMERCIAL |  |  | registered |
| Default | Evidence Hierarchy | `/evidence-hierarchy` | ALL |  |  | registered |
| Default | Verification Status | `/stage-gates` | THIRD_PARTY / CERTIFIER; THIRD_PARTY / BANK; PRODUCER / COMPLIANCE_LEGAL |  |  | registered |
| REGULATORY | Regulatory Registry | `/regulator-dashboard` | PRODUCER / COMPLIANCE_LEGAL; THIRD_PARTY / LEGAL |  |  | registered |
| REGULATORY | Decision Twin (RFNBO/RED III) | `/reports` | PRODUCER / COMPLIANCE_LEGAL; PRODUCER / ENGINEERING; THIRD_PARTY / CERTIFIER |  |  | registered |
| REGULATORY | Audit Trail | `/reports` | ALL |  |  | registered |
| REGULATORY | Environmental & ESG | `/reports` | PRODUCER / COMPLIANCE_LEGAL; THIRD_PARTY / LEGAL |  |  | registered |

### Operations

| Section | Label | Path | Visible To | Gate | New | Route |
|---|---|---|---|---|---|---|
| Default | Project Timeline | `/finance-timeline` | ALL |  |  | registered |
| Default | Construction Progress | `/producer-bankability` | PRODUCER / ENGINEERING; PRODUCER / OPERATIONS; THIRD_PARTY / ENGINEER |  |  | registered |
| Default | Milestones & Drawdown | `/finance-timeline` | PRODUCER / FINANCE_TREASURY; THIRD_PARTY / BANK |  |  | registered |
| PORTFOLIO | CEO Report | `/cfo-report` | PRODUCER / FINANCE_TREASURY; PRODUCER / EXECUTIVE; PRODUCER / OPERATIONS |  |  | registered |
| PLANT | Plant Telemetry | `/plant-data` | PRODUCER / OPERATIONS; PRODUCER / ENGINEERING; THIRD_PARTY / ENGINEER |  |  | registered |
| PLANT | Logistics & Shipping | `/capacity` | THIRD_PARTY / LOGISTICS; OFFTAKER / OPERATIONS; PRODUCER / OPERATIONS |  |  | registered |
| PLANT | Performance Matrix | `/reports` | PRODUCER / OPERATIONS; PRODUCER / ENGINEERING; THIRD_PARTY / ENGINEER; THIRD_PARTY / BANK |  |  | registered |
| PLANT | OT Gateway Status | `/ciso-gateways` | PRODUCER / OPERATIONS |  |  | registered |

### CISO Admin Password-Gated Menu

| Section | Label | Path | Route |
|---|---|---|---|
| SECURITY | Security Overview | `/ciso-dashboard` | registered |
| SECURITY | Access Monitor | `/ciso-access-monitor` | registered |
| SECURITY | Identity & Access (ABAC) | `/ciso-identity` | registered |
| SECURITY | Information Barriers | `/ciso-barriers` | registered |
| SECURITY | Data Residency | `/ciso-residency` | registered |
| SECURITY | OT Gateways | `/ciso-gateways` | registered |
| SECURITY | Communications Monitor | `/ciso-communications` | registered |
| SECURITY | Gantt Visibility | `/ciso-gantt-config` | registered |
| SECURITY | Policy Matrix | `/ciso-policy` | registered |
| SECURITY | Compliance (ISO 27001) | `/ciso-compliance` | registered |
| SECURITY | Event Bus Monitor | `/ciso-dashboard` | registered |
| WEBMASTER | Pricing Curves (Gabillon) | `/ciso-pricing` | registered |
| WEBMASTER | Forward Curves (Project view) | `/pricing-curves` | registered |

## Representative Role Visibility Matrix

| Role | Projects | Commercial | Finance | Compliance | Operations | Total |
|---|---:|---:|---:|---:|---:|---:|
| Producer Engineering | 9 | 0 | 4 | 4 | 4 | 21 |
| Producer Finance | 6 | 4 | 26 | 2 | 3 | 41 |
| Producer Commercial | 6 | 9 | 6 | 2 | 1 | 24 |
| Producer Executive | 6 | 0 | 12 | 2 | 2 | 22 |
| Offtaker Commercial | 5 | 7 | 6 | 3 | 1 | 22 |
| Offtaker Finance | 5 | 4 | 6 | 2 | 1 | 18 |
| Bank | 5 | 4 | 24 | 3 | 3 | 39 |
| Insurer | 5 | 0 | 10 | 2 | 1 | 18 |
| Certifier | 6 | 0 | 5 | 5 | 1 | 17 |
| Legal | 5 | 2 | 5 | 4 | 1 | 17 |
| Engineer | 8 | 0 | 4 | 2 | 4 | 18 |
| Logistics | 5 | 1 | 4 | 2 | 2 | 14 |

## Role-Specific Visible Links

### Producer Engineering

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]
- ENGINEERING / Cost Basis (CAPEX / LCOF) -> `/finance-plant-builder`
- ENGINEERING / Plant Telemetry -> `/plant-data`
- ENGINEERING / Production Roadmap -> `/producer-bankability`
- ENGINEERING / Evidence Upload -> `/reports`

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Certification Readiness -> `/cert-readiness`
- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Decision Twin (RFNBO/RED III) -> `/reports`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`
- Construction Progress -> `/producer-bankability`
- PLANT / Plant Telemetry -> `/plant-data`
- PLANT / Performance Matrix -> `/reports`

### Producer Finance

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]
- ENGINEERING / Evidence Upload -> `/reports`

**Commercial**

- Sales -> `/finance-demand` [new]
- Offtake Quality -> `/offtake-quality` [gate G4]
- NEGOTIATION / Contracts -> `/contracts`
- NEGOTIATION / Term Sheet Tracker -> `/term-sheet` [gate G4]

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- Capital Stack -> `/capital-stack` [gate G5]
- Covenants -> `/covenants`
- STRUCTURING / Cost Basis (CAPEX / LCOF) -> `/finance-plant-builder`
- STRUCTURING / Gap Analysis -> `/finance-gaps` [gate G5] [new]
- STRUCTURING / Instrument Catalog -> `/finance-instruments` [new]
- STRUCTURING / Instrument Compatibility -> `/instrument-compatibility` [new]
- STRUCTURING / Package Builder -> `/finance-package` [new]
- STRUCTURING / Risk Allocation -> `/finance-risk-matrix` [new]
- STRUCTURING / Structuring Timeline -> `/finance-structuring-timeline` [new]
- STRUCTURING / Spend Wave (Pre-FID) -> `/finance/spend-wave` [new]
- STRUCTURING / Drawdown Timeline -> `/finance/drawdown-timeline` [gate G10] [new]
- STRUCTURING / DFI Dashboard -> `/finance/dfi-dashboard` [new]
- STRUCTURING / Information Lineage -> `/finance/lineage` [new]
- EXPORT / Banker's Snapshot -> `/bankability-snapshot` [gate G8]
- EXPORT / IC Pack Builder -> `/ic-pack` [gate G10]
- GATING / Insurance Schedule -> `/insurance-schedule` [gate G7]
- GATING / Coverage Lines (CAR/EAR/DSU/BI) -> `/insurance-coverage` [gate G7]
- GATING / Asset & Exposure Register -> `/insurance-assets`
- EXPORT / Transfer Readiness -> `/transfer-readiness`
- EXPORT / Data Room -> `/data-room` [gate G10]
- DEAL ROOM / Approval Queue -> `/approval-queue` [gate G10]
- DEAL ROOM / Commitment Signing -> `/commitment-signing` [gate G10]
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`
- Milestones & Drawdown -> `/finance-timeline`
- PORTFOLIO / CEO Report -> `/cfo-report`

### Producer Commercial

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]
- ENGINEERING / Evidence Upload -> `/reports`

**Commercial**

- Commercial Overview -> `/marketplace`
- Sales -> `/finance-demand` [new]
- Offtake Quality -> `/offtake-quality` [gate G4]
- NEGOTIATION / Matching Engine -> `/matching`
- NEGOTIATION / RFQ Management -> `/trader-dashboard`
- NEGOTIATION / Contracts -> `/contracts`
- NEGOTIATION / Term Sheet Tracker -> `/term-sheet` [gate G4]
- MARKET DATA / Counterparties -> `/settlement`
- MARKET DATA / GreenMesh -> `/capacity`

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- STRUCTURING / Instrument Compatibility -> `/instrument-compatibility` [new]
- DEAL ROOM / Commitment Signing -> `/commitment-signing` [gate G10]
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`

### Producer Executive

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]
- ENGINEERING / Evidence Upload -> `/reports`

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- Capital Stack -> `/capital-stack` [gate G5]
- STRUCTURING / Cost Basis (CAPEX / LCOF) -> `/finance-plant-builder`
- STRUCTURING / Gap Analysis -> `/finance-gaps` [gate G5] [new]
- STRUCTURING / Spend Wave (Pre-FID) -> `/finance/spend-wave` [new]
- STRUCTURING / DFI Dashboard -> `/finance/dfi-dashboard` [new]
- STRUCTURING / Information Lineage -> `/finance/lineage` [new]
- EXPORT / Banker's Snapshot -> `/bankability-snapshot` [gate G8]
- DEAL ROOM / Approval Queue -> `/approval-queue` [gate G10]
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`
- PORTFOLIO / CEO Report -> `/cfo-report`

### Offtaker Commercial

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]

**Commercial**

- Commercial Overview -> `/marketplace`
- Purchase -> `/offtaker-supply`
- Offtake Quality -> `/offtake-quality` [gate G4]
- NEGOTIATION / Matching Engine -> `/matching`
- NEGOTIATION / RFQ Management -> `/trader-dashboard`
- NEGOTIATION / Contracts -> `/contracts`
- MARKET DATA / Counterparties -> `/settlement`

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- EXPORT / Data Room -> `/data-room` [gate G10]
- DEAL ROOM / Commitment Signing -> `/commitment-signing` [gate G10]
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Certification Distance -> `/cert-readiness`
- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`

### Offtaker Finance

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]

**Commercial**

- Purchase -> `/offtaker-supply`
- NEGOTIATION / RFQ Management -> `/trader-dashboard`
- NEGOTIATION / Contracts -> `/contracts`
- NEGOTIATION / Term Sheet Tracker -> `/term-sheet` [gate G4]

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- STRUCTURING / Instrument Compatibility -> `/instrument-compatibility` [new]
- DEAL ROOM / Commitment Signing -> `/commitment-signing` [gate G10]
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`

### Bank

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]

**Commercial**

- Sales -> `/finance-demand` [new]
- Offtake Quality -> `/offtake-quality` [gate G4]
- NEGOTIATION / Contracts -> `/contracts`
- NEGOTIATION / Term Sheet Tracker -> `/term-sheet` [gate G4]

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- Capital Stack -> `/capital-stack` [gate G5]
- Covenants -> `/covenants`
- STRUCTURING / Cost Basis (CAPEX / LCOF) -> `/finance-plant-builder`
- STRUCTURING / Gap Analysis -> `/finance-gaps` [gate G5] [new]
- STRUCTURING / Instrument Catalog -> `/finance-instruments` [new]
- STRUCTURING / Instrument Compatibility -> `/instrument-compatibility` [new]
- STRUCTURING / Package Builder -> `/finance-package` [new]
- STRUCTURING / Risk Allocation -> `/finance-risk-matrix` [new]
- STRUCTURING / Structuring Timeline -> `/finance-structuring-timeline` [new]
- STRUCTURING / Spend Wave (Pre-FID) -> `/finance/spend-wave` [new]
- STRUCTURING / Drawdown Timeline -> `/finance/drawdown-timeline` [gate G10] [new]
- STRUCTURING / DFI Dashboard -> `/finance/dfi-dashboard` [new]
- STRUCTURING / Information Lineage -> `/finance/lineage` [new]
- EXPORT / Banker's Snapshot -> `/bankability-snapshot` [gate G8]
- EXPORT / IC Pack Builder -> `/ic-pack` [gate G10]
- GATING / Insurance Schedule -> `/insurance-schedule` [gate G7]
- EXPORT / Transfer Readiness -> `/transfer-readiness`
- EXPORT / Data Room -> `/data-room` [gate G10]
- DEAL ROOM / Approval Queue -> `/approval-queue` [gate G10]
- DEAL ROOM / Commitment Signing -> `/commitment-signing` [gate G10]
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Evidence Hierarchy -> `/evidence-hierarchy`
- Verification Status -> `/stage-gates`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`
- Milestones & Drawdown -> `/finance-timeline`
- PLANT / Performance Matrix -> `/reports`

### Insurer

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- STRUCTURING / Instrument Compatibility -> `/instrument-compatibility` [new]
- STRUCTURING / Risk Allocation -> `/finance-risk-matrix` [new]
- GATING / Insurance Schedule -> `/insurance-schedule` [gate G7]
- GATING / Coverage Lines (CAR/EAR/DSU/BI) -> `/insurance-coverage` [gate G7]
- GATING / Asset & Exposure Register -> `/insurance-assets`
- EXPORT / Data Room -> `/data-room` [gate G10]
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`

### Certifier

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]
- ENGINEERING / Evidence Upload -> `/reports`

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- EXPORT / Data Room -> `/data-room` [gate G10]
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Certification Readiness -> `/cert-readiness`
- Evidence Hierarchy -> `/evidence-hierarchy`
- Verification Status -> `/stage-gates`
- REGULATORY / Decision Twin (RFNBO/RED III) -> `/reports`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`

### Legal

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]

**Commercial**

- NEGOTIATION / Contracts -> `/contracts`
- NEGOTIATION / Term Sheet Tracker -> `/term-sheet` [gate G4]

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- EXPORT / Data Room -> `/data-room` [gate G10]
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Regulatory Registry -> `/regulator-dashboard`
- REGULATORY / Audit Trail -> `/reports`
- REGULATORY / Environmental & ESG -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`

### Engineer

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]
- ENGINEERING / Cost Basis (CAPEX / LCOF) -> `/finance-plant-builder`
- ENGINEERING / Plant Telemetry -> `/plant-data`
- ENGINEERING / Production Roadmap -> `/producer-bankability`

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`
- Construction Progress -> `/producer-bankability`
- PLANT / Plant Telemetry -> `/plant-data`
- PLANT / Performance Matrix -> `/reports`

### Logistics

**Projects**

- Dashboard Projects -> `/dashboard`
- My Projects -> `/projects`
- Task Flow -> `/finance-dashboard`
- Status & Blockers -> `/bankability-scores`
- Challenge Review -> `/adversarial-review` [new]

**Commercial**

- MARKET DATA / GreenMesh -> `/capacity`

**Finance**

- Bankability Status -> `/bankability-scores`
- STRUCTURING / Sensitivity Analysis -> `/dscr-sensitivity`
- STRUCTURING / Price Lineage -> `/pricing-lineage`
- DEAL ROOM / Commitment Verifier -> `/commitment-verifier`

**Compliance**

- Evidence Hierarchy -> `/evidence-hierarchy`
- REGULATORY / Audit Trail -> `/reports`

**Operations**

- Project Timeline -> `/finance-timeline`
- PLANT / Logistics & Shipping -> `/capacity`

