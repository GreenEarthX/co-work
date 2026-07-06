from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.pricing.gabillon.engine import GabillonCurveEngine
from app.pricing.gabillon.service import GabillonService
from app.pricing.memory import ProjectCalibrationMemory
from app.pricing.offtake.engine import OfftakeEngine
from app.pricing.offtake.service import OfftakeService

FIXTURES = Path(__file__).parent / "fixtures"


def curve_config(project_id: str = "proj_offtake") -> dict:
    cfg = json.loads((FIXTURES / "gabillon_config.json").read_text())
    cfg["project_id"] = project_id
    cfg["simulation"]["n_paths"] = 2000
    return cfg


def offtake_config(project_id: str = "proj_offtake") -> dict:
    cfg = json.loads((FIXTURES / "offtake_config.json").read_text())
    cfg["project_id"] = project_id
    cfg["simulation"]["n_paths"] = 2000
    return cfg


def calibrated_curve(tmp_path, project_id: str = "proj_offtake") -> GabillonCurveEngine:
    memory = ProjectCalibrationMemory(str(tmp_path))
    curve = GabillonCurveEngine(curve_config(project_id), memory_store=memory, project_id=project_id)
    curve.calibrate()
    return curve


def test_zero_flex_band_has_near_zero_swing(tmp_path):
    curve = calibrated_curve(tmp_path)
    cfg = offtake_config()
    cfg["volume"]["min_per_year"] = cfg["volume"]["max_per_year"] = cfg["volume"]["baseline_per_year"]

    swing = OfftakeEngine(cfg, curve).volume_flex_value()
    assert swing["swing_to_buyer"] < 1e-6


def test_wider_band_increases_swing_value(tmp_path):
    curve = calibrated_curve(tmp_path)
    narrow = OfftakeEngine(offtake_config(), curve).volume_flex_value()

    cfg = offtake_config()
    cfg["volume"]["min_per_year"] = 60.0
    cfg["volume"]["max_per_year"] = 130.0
    cfg["volume"]["total_max"] = 1300.0
    wide = OfftakeEngine(cfg, curve).volume_flex_value()

    assert wide["swing_to_buyer"] >= narrow["swing_to_buyer"] - 1.0


def test_total_equals_additive_decomposition(tmp_path):
    curve = calibrated_curve(tmp_path)
    result = OfftakeEngine(offtake_config(), curve).value_contract()
    decomp = result["decomposition"]

    total = (
        decomp["linear_indexed_leg"]
        + decomp["collar"]
        + decomp["volume_flex"]
    )
    assert abs(result["total_value"] - total) < 1e-6
    assert "provenance" in result


def test_offtake_api_reuses_cached_calibration():
    client = TestClient(app)
    project_id = "api_offtake_project"
    curve_payload = curve_config(project_id)
    value_payload = offtake_config(project_id)

    missing = client.post("/pf/offtake/value", json=value_payload)
    assert missing.status_code == 409

    assert client.post("/pf/curve/calibrate", json=curve_payload).status_code == 200
    value = client.post("/pf/offtake/value", json=value_payload)
    assert value.status_code == 200
    assert value.json()["seed"] == value_payload["simulation"]["seed"]


def test_offtake_service_reuses_persisted_calibration_without_curve_config(tmp_path):
    memory = ProjectCalibrationMemory(str(tmp_path))
    project_id = "persisted_offtake_project"

    GabillonService(memory).calibrate(curve_config(project_id))
    fresh_curves = GabillonService(memory)
    result = OfftakeService(fresh_curves).value_contract(offtake_config(project_id))

    assert result["project_id"] == project_id
    assert "provenance" in result
