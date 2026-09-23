# Frontend Data Persistence Audit

**Review date:** 2026-09-22  
**Objective:** expose frontend values that are mocked, seeded, derived as fallbacks, or stored only in the browser, and define their PostgreSQL replacement.

## Immediate finding

The frontend is not yet a pure view of server-held data. Financial and marketplace screens contain explicit mock/fallback datasets, while several workflows use `localStorage` as durable storage. These values must not be presented as authoritative project facts.

## Mock and fallback business data

| Surface | Current source | Required PostgreSQL/API replacement | Priority |
|---|---|---|---|
| Marketplace | `features/marketplace/useMarketplace.ts` mock rows | Existing marketplace tables and API (`capacities`, `tokens`, `offers`, `matches`) | P0 |
| Drawdown timeline | `features/finance/DrawdownTimeline.tsx` mock tranches/milestones | Capital bridge tables and project-scoped drawdown endpoint | P0 |
| Spend wave | `features/finance/SpendWaveView.tsx` mock annual spend | `spend_wave`/`spend_waves` plus project endpoint | P0 |
| Finance lineage | `features/finance/LineagePanel.tsx` mock nodes/details | Append-only lineage/events endpoint backed by PostgreSQL | P0 |
| DFI dashboard | `features/finance/DFIDashboard.tsx` mock institutions | `dfi_criteria`, `dfi_criteria_status`, `dfi_impact_kpis` endpoint | P0 |
| Data room hashes | `features/finance/DataRoom.tsx` deterministic `fakeHash()` | Store real document digest, version, uploader, and timestamp in evidence tables | P0 |
| Bankability rating | `features/finance/BankabilityScorePage.tsx` client fallback rating | Backend bankability result only; unavailable API produces an explicit unavailable state | P0 |
| Finance bankability | `features/finance/FinanceBankabilityView.tsx` derived fallback/proxy | Persist model input/output/version and return canonical backend computation | P0 |
| Certification/offtake | `CertReadiness.tsx`, `OfftakeQuality.tsx` demo fallback | Project-scoped certification and offtake endpoints; no silent demo substitution | P0 |
| Pricing curves/admin | `MoleculePriceCurve.tsx`, `GabillonAdminPage.tsx`, `MoleculeLineage.tsx` seed fallbacks | PF engine response plus persisted calibration/run lineage | P1 |
| Ownership team | `components/canvas/OwnershipRolesPanel.tsx` `SEED_TEAM` | Directory members and project-role assignment API | P1 |

Policy: production builds should fail when identifiers matching `MOCK_*`, `fakeHash`, or known demo-fallback markers occur outside tests, stories, and an explicitly isolated sandbox package.

## Browser-only business data

| Data | Current files/keys | PostgreSQL destination | Treatment |
|---|---|---|---|
| Plant setup and profile | `NewPlantDialog.tsx`, `PlantSettingsDialog.tsx`; `gex_plant_*` | `projects`, `project_context`, plant profile tables | Server authoritative; local cache may remain versioned |
| Plants list | `lib/plantStore.ts`; `ptool_plant_list` | Existing plants backend store, then PostgreSQL migration | Remove local authority |
| Canvas payload/iterations | `PlantBuilder.tsx`, `useLocalPersistence.ts`, `iterations.ts` | `canvas_blobs`/versioned canvas API, migrated to PostgreSQL | Cache only; server revision wins |
| Custom equipment library | `lib/customLibrary.ts` | Tenant-scoped component-library tables | Sync via API |
| Ownership assignments | `OwnershipRolesPanel.tsx` | Project role/assignment tables with audit events | Server only |
| Team alignment/messages | `TeamAlignmentPanel.tsx` | Matrix/event-backed collaboration endpoint | Server only |
| Procurement model/export | `procurementExport.ts`, `useProcurementSimulator.ts` | Project procurement scenario and revision tables | Server authoritative |
| Export validation | `ExportValidationDialog.tsx` | Validation result/event table | Persist with model/data version |
| Bankability saved state | `BankabilityScorePage.tsx` | Bankability snapshot/evidence tables | Server only |
| KYC/KYB workflow | `features/kyc/kycState.ts` | Auth/vetting/KYB tables with RLS and audit | P0: remove browser authority |
| Guest ABAC policy | `ABACManagementPage.tsx` | Governance policy tables | P0: server only |
| Pricing calibration/cache | pricing components | Model-run/calibration tables | Server authoritative |

## Acceptable browser-local state

These can remain local because they are disposable user-interface preferences: selected project pointer, collapsed dashboard sections, canvas toolbar preferences, label normalization preferences, colors, and the last-edited equation pointer. They must never grant access or replace server data.

Authentication/session material should use secure, HTTP-only, same-site cookies where practical. `CISOGate.tsx` currently reads a password from `localStorage` and supplies a hard-coded fallback; this is a P0 security defect, not a persistence preference.

## Fastest PostgreSQL delivery plan

1. **Cut over the eight migrated slices.** Run `backend/scripts/cutover_postgres.py --execute`, then deploy the eight `*_DB_BACKEND=postgres` settings already present in Compose.
2. **Freeze new browser persistence.** Add a CI guard that rejects new direct `localStorage` calls except an allowlist of preferences/cache modules.
3. **Remove false authority first.** Replace P0 mocks and silent fallbacks with backend calls and explicit unavailable/empty states.
4. **Add missing PostgreSQL schemas.** Prioritize KYC/KYB, canvas/versioning, plant profiles, project ownership, procurement scenarios, and model-run lineage.
5. **Backfill browser/Supabase exports.** Import under stable tenant/project IDs, preserve source and timestamps, and compare counts/checksums.
6. **Retire transitional stores.** Make SQLite read-only, observe the rollback window, then make production startup reject SQLite and remove the database file.

## Definition of done

- All eight backend selectors report `postgres` in the deployed environment.
- Copy scripts report column and row parity with no mismatch.
- RLS tests pass using the restricted runtime role.
- No production screen silently substitutes mock/demo data after an API failure.
- Durable business changes survive a new browser/device and are visible only to entitled tenants.
- Every computed or imported value records source, timestamp, actor, verification status, and model version where applicable.
