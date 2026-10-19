# Baseline before the reference-data registry work — 2026-10-19

Taken on branch `reference-data-registry` at commit 9f59126 (the consolidation
commit), before any WP1 change. Later diffs against these files are deliberate.

## Tests

| Suite | Command | Result |
|---|---|---|
| Platform backend | `cd backend && ./venv/bin/python -m pytest tests/ -q -rs`, `DATABASE_URL` + `ALEMBIC_DATABASE_URL` exported | **899 pass, 18 skip, 0 fail** (skip reasons in `backend_tests.txt`) |
| PF engine | `cd gex_pf_engine/backend && ../micro_service/bin/python -m pytest tests/ -q` | **239 pass, 0 skip, 0 fail** |

The database was at Alembic head **060**, with 121 tables in `public`.

## Outputs

- `baseline_example_green_h2.json`: `GET /api/v1/model/examples/green-h2-project`
  on the PF engine (`pf_engine/api/routes_model.py:example_green_h2`). The route
  rejects calls without a JWT, so it was called in-process. It is pure computation,
  so the output is identical. Headline: min DSCR 4.456, total CFADS 865,050,000,
  `project_irr: "TBD"`, and subsidies `45V 3.0 + RED_III 0.5` stacked in a euro
  project at a 21% tax rate.
- `baseline_capital_bridge_h2_50mw.json`: `compute_capital_bridge` for a project
  bootstrapped with the code's own defaults: H2, 50 MW, FEL-1 2026, total capex
  EUR 100 M, the default 11-tranche stack. **No capital-bridge project exists in
  PostgreSQL** (`project_control` and `capital_stack_tranches` are empty), so it ran
  against a throwaway SQLite file. Reproduce with `capture_capital_bridge.py <outdir>`
  from `backend/`, with `PYTHONPATH=.`.
- `baseline_fuel_defaults.json`: `capital_bridge.FUEL_DEFAULTS` as it stands. These
  are the constants WP1 moves into the registry.
