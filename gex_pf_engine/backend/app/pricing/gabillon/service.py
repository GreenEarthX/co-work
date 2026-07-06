"""Service wrapper for Gabillon curve operations."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from app.pricing.gabillon.engine import GabillonCurveEngine, PARAM_ORDER
from app.pricing.memory import ProjectCalibrationMemory


class GabillonService:
    def __init__(self, memory: ProjectCalibrationMemory | None = None):
        self.memory = memory or ProjectCalibrationMemory()
        self._calibrated: dict[str, GabillonCurveEngine] = {}
        self._forecast_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def calibrate(self, config: dict[str, Any]) -> dict[str, Any]:
        engine = self._build(config)
        record = engine.calibrate(
            warm_start=bool(config.get("calibration", {}).get("warm_start_from_memory", True))
        )
        self._calibrated[engine.project_id] = engine
        self._forecast_cache.pop((engine.project_id, self._hash(config)), None)
        return record

    def pricing_curve(self, config: dict[str, Any], taus: list[float]) -> dict[str, Any]:
        engine = self._build_calibrated(config)
        return engine.pricing_curve(taus)

    def forecast_cone(self, config: dict[str, Any]) -> dict[str, Any]:
        project_id = config["project_id"]
        key = (project_id, self._hash(config))
        if key not in self._forecast_cache:
            self._forecast_cache[key] = self._build_calibrated(config).forecast_cone()
        return copy.deepcopy(self._forecast_cache[key])

    def history(self, project_id: str) -> list[dict[str, Any]]:
        return self.memory.history(project_id)

    def cached_engine(self, project_id: str, config: dict[str, Any] | None = None) -> GabillonCurveEngine:
        if project_id in self._calibrated:
            return self._calibrated[project_id]
        if config is None:
            config = self.memory.latest_config(project_id)
        if config is None:
            raise ValueError("No cached calibration for project_id")
        engine = self._build_calibrated(config)
        self._calibrated[project_id] = engine
        return engine

    def _build_calibrated(self, config: dict[str, Any]) -> GabillonCurveEngine:
        latest = self.memory.latest_params(config["project_id"])
        if latest is None:
            raise ValueError("No cached calibration for project_id")
        seeded = copy.deepcopy(config)
        for name in PARAM_ORDER:
            if name in latest:
                seeded["params"][name]["value"] = latest[name]
        return self._build(seeded)

    def _build(self, config: dict[str, Any]) -> GabillonCurveEngine:
        return GabillonCurveEngine(config, memory_store=self.memory, project_id=config["project_id"])

    def _hash(self, config: dict[str, Any]) -> str:
        blob = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()
