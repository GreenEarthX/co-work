from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.pricing.gabillon.engine import GabillonCurveEngine, gabillon_forward
from app.pricing.memory import ProjectCalibrationMemory

FIXTURES = Path(__file__).parent / "fixtures"


def load_config(project_id: str = "proj_test") -> dict:
    cfg = json.loads((FIXTURES / "gabillon_config.json").read_text())
    cfg["project_id"] = project_id
    cfg["simulation"]["n_paths"] = 2000
    return cfg


def test_mc_q_mean_reproduces_closed_form_forward(tmp_path):
    engine = GabillonCurveEngine(
        load_config(),
        memory_store=ProjectCalibrationMemory(str(tmp_path)),
        project_id="proj_test",
    )
    sim = engine.simulate_paths(
        measure="Q",
        n_paths=60000,
        horizon_years=5.0,
        seed=1,
        use_policy=False,
    )
    mc_q = float(sim["S"][-1].mean())
    cf = float(gabillon_forward(engine.market.spot, engine.market.long_term, 5.0, engine.params))
    assert abs(mc_q / cf - 1.0) < 0.01


def test_lcof_calibration_and_warm_start_memory(tmp_path):
    memory = ProjectCalibrationMemory(str(tmp_path))
    engine = GabillonCurveEngine(load_config(), memory_store=memory, project_id="proj_test")

    rec = engine.calibrate()
    assert abs(rec["params"]["kappa"] - 0.39) < 0.05
    assert rec["fit"]["r2_vs_fundamental"] > 0.97
    assert rec["warm_started"] is False

    rec2 = GabillonCurveEngine(load_config(), memory_store=memory, project_id="proj_test").calibrate()
    assert rec2["warm_started"] is True


def test_project_scoped_memory_does_not_collide(tmp_path):
    memory = ProjectCalibrationMemory(str(tmp_path))
    cfg_a = load_config("project_a")
    cfg_b = load_config("project_b")
    cfg_b = copy.deepcopy(cfg_b)
    cfg_b["params"]["kappa"]["value"] = 1.2

    GabillonCurveEngine(cfg_a, memory_store=memory, project_id="project_a").calibrate()
    GabillonCurveEngine(cfg_b, memory_store=memory, project_id="project_b").calibrate()

    assert memory.history("project_a")[0]["project_id"] == "project_a"
    assert memory.history("project_b")[0]["project_id"] == "project_b"


def test_curve_api_contracts_include_provenance_and_memory():
    client = TestClient(app)
    payload = load_config("api_curve_project")

    cal = client.post("/pf/curve/calibrate", json=payload)
    assert cal.status_code == 200
    assert cal.json()["fit"]["r2_vs_fundamental"] > 0.97

    pricing = client.post("/pf/curve/pricing", json={**payload, "taus": [1, 5]})
    assert pricing.status_code == 200
    body = pricing.json()
    assert body["measure"] == "Q"
    assert body["seed"] == payload["simulation"]["seed"]
    assert "provenance" in body

    memory = client.get("/pf/curve/api_curve_project/memory")
    assert memory.status_code == 200
    assert memory.json()["history"]
