"""
Propose the Gabillon CEPCI forward for the years after the last published one (JML, 20 Nov 2026).
===================================================================================================
The TEA engine prices in a fixed cost year (2024) and the published CEPCI ends there, so a quote
dated 2025 or later could not be converted. JML: calibrate a forward curve on the past CEPCI with
the Gabillon model. This script:

  1. reads the CEPCI series the TEA engine escalates with   (GET :8002/tea/cepci)
  2. calibrates the Gabillon model on it in the PF engine    (POST :8001/pf/index/forward)
  3. PROPOSES one reference row per forward year, cepci_forward_<year>:
       value_base = E_P[CEPCI], value_low / value_high = the 90% band, unit "-",
       source_name = the model, the calibration window and its parameters.

It proposes only. Nothing uses a forward until a person approves its row on the GEX staff
console; a published CEPCI value always wins over a forward. Re-run after a new published year:
a new proposal supersedes the old one when approved.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/propose_cepci_forward_20261120.py [--execute]
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import reference_registry as reg  # noqa: E402
from app.services.engine_auth import engine_auth_headers  # noqa: E402

TEA = os.getenv("TEA_ENGINE_URL", "http://localhost:8002")
PF = os.getenv("PF_ENGINE_URL", os.getenv("GEX_ENGINE_URL", "http://localhost:8001"))
PROPOSER = "CEPCI_FORWARD_GABILLON_20261120 (Claude, on JML's instruction of 20 Nov)"
LAST_KEY_YEAR = 2030


def main(execute: bool) -> int:
    h = engine_auth_headers()
    cepci = httpx.get(f"{TEA}/tea/cepci", headers=h, timeout=30)
    cepci.raise_for_status()
    c = cepci.json()
    horizon = LAST_KEY_YEAR - c["last_year"]
    fwd = httpx.post(f"{PF}/pf/index/forward", headers=h, timeout=120,
                     json={"index_name": "CEPCI", "source": c["source"], "series": c["series"],
                           "horizon_years": horizon})
    fwd.raise_for_status()
    f = fwd.json()
    cal = f["calibration"]
    pr = cal["params"]
    basis = (f"Gabillon two-factor P-forward (PF engine, pricing/gabillon/history.py), Kalman ML on CEPCI "
             f"{cal['first_year']}-{cal['last_year']} ({cal['observations']} points, {c['source']}): "
             f"kappa {pr['kappa']:.3f}, sigma_S {pr['sigma_S']:.3f}, sigma_L {pr['sigma_L']:.3f}, "
             f"mu_L {pr['mu_L']:.4f}/yr; on a bound: {', '.join(cal['parameters_on_a_bound']) or 'none'}")
    print(basis)
    from app.core.db_backend import fuelref_connection
    conn = fuelref_connection(company_id="PLATFORM_ADMIN")   # curating GEX-held reference data
    try:
        for row in f["forward"]:
            key = f"cepci_forward_{row['year']}"
            proposal = {"parameter_key": key, "pathway": "ANY", "region": "ANY", "value_low": round(row["p05"], 1),
                        "value_base": round(row["expected"], 1), "value_high": round(row["p95"], 1), "unit": "-",
                        "source_class": "gex_assumption", "source_name": basis[:480],
                        "retrieved_at": date.today().isoformat(), "valid_from": date.today().isoformat(),
                        "note": ("A MODEL forward, not a published index: E_P[CEPCI] with a 90% band. Replaced by "
                                 "the published value for its year as soon as one exists. lambda_S fixed 0 (a cost "
                                 "index has no market price of risk).")}
            reg.validate_proposal(proposal)
            print(f"  {key}: {proposal['value_low']} / {proposal['value_base']} / {proposal['value_high']}")
            if execute:
                exists = conn.execute("SELECT ref_id FROM reference_parameter WHERE parameter_key = ? AND state = "
                                      "'proposed' AND proposed_by = ?", (key, PROPOSER)).fetchone()
                if exists:
                    print(f"    already proposed: {exists['ref_id']}")
                    continue
                print(f"    proposed {reg.propose(conn, proposal, actor=PROPOSER)['ref_id']}")
        if execute:
            conn.commit()
        else:
            print("DRY RUN — nothing written. Add --execute.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main("--execute" in sys.argv))
