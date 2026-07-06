# ETFuels Projects Inventory

Updated from the current `gex-platform-enhanced` source tree on 2026-05-22.

This file consolidates the ETFuels-related project records, demo notes, and the current source-of-truth fields used across the frontend.

## Summary

ETFuels appears in the project registry in four active entries, plus one dedicated demo anchor:

1. `proj_etf_pecos1` - ETFuels Rattlesnake Gap / Pecos I
2. `etfuels_us_tx_rattlesnake_gap` - Rattlesnake Gap
3. `etfuels_fi_ranua_naataaapa` - Ranua Näätäaapa e-Methanol
4. `etfuels_uk_skyfuel_teesside` - Project SkyFuel Teesside
5. Demo reference - ETFuels Pecos I live demo notes in `CLAUDE.md`

## Project Registry

| ID | Name | Molecule | Location | Country | Status | Phase | COD | Capacity | CAPEX | Owner | Key Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `proj_etf_pecos1` | ETFuels Rattlesnake Gap | e-Methanol | West Texas | US | development | FEED Class 3 - Structurally Bankable | 2030-06-30 | 329 MTPD | EUR 562,000,000 | ETFuels SA | RFOcean binding 10-year fixed-price offtake; ETFuels SA related-party offtake remains unverified; 45V and RFNBO under review. |
| `etfuels_us_tx_rattlesnake_gap` | Rattlesnake Gap | e-Methanol | West Texas (Christoval / Schleicher County) | US | development | FEED underway - FID target end-2026 | 2030-03-31 | 342 MTPD | not publicly disclosed | ETFuels SA | Public-source seed; 125,000 t/yr e-methanol; RFOcean binding long-term fixed-price from 2030; not bankable evidence. |
| `etfuels_fi_ranua_naataaapa` | Ranua Näätäaapa e-Methanol | e-Methanol | Ranua, Lapland | FI | development | Pre-FEED - tax credit awarded | 2031-12-31 | 301 MTPD | EUR 800,000,000 | ETFuels SA | 300 MW wind to renewable H2; 110,000 t/yr; Business Finland tax credit awarded; CO2 counterparty not public. |
| `etfuels_uk_skyfuel_teesside` | Project SkyFuel Teesside | SAF | Redcar, Teesside | GB | development | AFF-supported development - FEED progressing | 2032-12-31 | 90 MTPD | not publicly disclosed | ETFuels SA | 33,000 t/yr SAF; Johnson Matthey + Protium; UK Advanced Fuels Fund support; feedstock linked to global e-methanol pipeline. |

## Project Notes

### `proj_etf_pecos1` - ETFuels Rattlesnake Gap / Pecos I

- Demo anchor used in the frontend project registry.
- Current model: 340 MW wind -> 150 MW PEM electrolysis -> 120,000 t/yr e-methanol.
- Current bankability snapshot:
  - overall completion: 58%
  - next milestone: resolve capacity discrepancy, then complete G4 credit support
  - unlocked capital: `GRANTS_TA`
  - key risks: capacity discrepancy, 45V temporal matching, related-party ETFuels SA offtake
- Main gate details currently encoded in the seed data:
  - G0 complete
  - G1 grid/utilities partial, ERCOT interconnect still open
  - G3 technology vendor locked but EPC contract open
  - G4 offtake bankable at 78% with RFOcean binding and ETFuels SA / Lufthansa Cargo elements
  - G7 insurance, G8 audit-grade model, and G10 financial close still open

### `etfuels_us_tx_rattlesnake_gap` - Rattlesnake Gap

- Public-source seed entry.
- 500 MW behind-the-meter wind + solar model.
- Current published capacity in the seed: 125,000 t/yr e-methanol.
- Main risks:
  - capacity conflict with older sources
  - electrolyser MW conflict
  - 45V guidance pending
  - offtake volume not public

### `etfuels_fi_ranua_naataaapa` - Ranua Näätäaapa

- Finnish project with tax credit support.
- 300 MW wind to renewable hydrogen to e-methanol.
- Reported output: 110,000 t/yr.
- Main risks:
  - capacity conflict with legacy sources
  - tax credit is not a cash grant
  - offtake not public
  - CO2 counterparty not public

### `etfuels_uk_skyfuel_teesside` - Project SkyFuel Teesside

- SAF project in Redcar, Teesside.
- 33,000 t/yr e-SAF via methanol-to-jet pathway.
- Technology partners: Johnson Matthey and Protium.
- Main risks:
  - AFF grant is development support only
  - UK Revenue Certainty Mechanism still evolving
  - feedstock depends on external e-methanol pipeline
  - SAF testing and certification chain still needed

## Demo References

The ETFuels live demo notes are documented in:

- `gex-platform-enhanced/CLAUDE.md`
- `gex-platform-enhanced/docs/demos/etfuels-2026/DEMO_BRIEF.md`
- `gex-platform-enhanced/docs/demos/etfuels-2026/storyboard.md`
- `gex-platform-enhanced/docs/demos/etfuels-2026/checklist.md`
- `gex-platform-enhanced/docs/demos/etfuels-2026/gaps.md`
- `gex-platform-enhanced/docs/demos/etfuels-2026/seed_etfuels_pecos.ts`

## Source Files

- `gex-platform-enhanced/frontend/src/data/customerProjects.ts`
- `gex-platform-enhanced/CLAUDE.md`
- `gex-platform-enhanced/frontend/src/features/finance/PlantBuilder.tsx`
- `gex-platform-enhanced/frontend/src/features/finance/CertReadiness.tsx`
- `gex-platform-enhanced/frontend/src/features/finance/LineagePanel.tsx`

