"""Pydantic contracts for offtake endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class OfftakeConfig(BaseModel):
    project_id: str
    curve_config: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    def engine_config(self) -> dict[str, Any]:
        data = self.model_dump()
        data.pop("curve_config", None)
        return data


class RollupRequest(BaseModel):
    project_id: str
    contracts: list[dict[str, Any]]
    curve_config: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    def template_config(self) -> dict[str, Any]:
        data = self.model_dump()
        data.pop("contracts", None)
        data.pop("curve_config", None)
        return data


class OfftakeValueResponse(BaseModel):
    contract_id: str | None
    project_id: str | None
    perspective: str
    seed: int
    total_value: float
    decomposition: dict[str, float]
    diagnostics: dict[str, Any]
    provenance: dict[str, Any]

    model_config = ConfigDict(extra="allow")


class GreenmeshRollupResponse(BaseModel):
    enabled: bool

    model_config = ConfigDict(extra="allow")
