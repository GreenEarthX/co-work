"""Pydantic contracts for Gabillon pricing endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GabillonConfig(BaseModel):
    project_id: str

    model_config = ConfigDict(extra="allow")

    def engine_config(self) -> dict[str, Any]:
        return self.model_dump()


class PricingCurveRequest(GabillonConfig):
    taus: list[float] = Field(default_factory=lambda: [0.25, 1, 2, 3, 5, 7, 10])

    def engine_config(self) -> dict[str, Any]:
        data = self.model_dump()
        data.pop("taus", None)
        return data


class CalibrationResponse(BaseModel):
    project_id: str
    params: dict[str, float]
    free_params: list[str]
    target_source: str
    warm_started: bool
    seed: int
    fit: dict[str, Any]
    provenance_note: str

    model_config = ConfigDict(extra="allow")


class PricingCurveResponse(BaseModel):
    measure: str
    tau: list[float]
    forward: list[float]
    seed: int
    provenance: dict[str, Any]

    model_config = ConfigDict(extra="allow")


class ForecastConeResponse(BaseModel):
    measure: str
    tau: list[float]
    seed: int
    mean: list[float]
    quantile_levels: list[float]
    cone: list[list[float]]
    provenance: dict[str, Any]

    model_config = ConfigDict(extra="allow")
