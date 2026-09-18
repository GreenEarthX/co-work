"""Service wrapper for offtake valuation."""
from __future__ import annotations

from typing import Any

from pf_engine.pricing.gabillon.service import GabillonService
from pf_engine.pricing.offtake.engine import OfftakeEngine


class OfftakeService:
    def __init__(self, curves: GabillonService):
        self.curves = curves

    def value_contract(self, config: dict[str, Any], curve_config: dict[str, Any] | None = None) -> dict[str, Any]:
        curve = self.curves.cached_engine(config["project_id"], curve_config)
        return OfftakeEngine(config, curve).value_contract()

    def greenmesh_rollup(
        self,
        template_config: dict[str, Any],
        contracts: list[dict[str, Any]],
        curve_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        curve = self.curves.cached_engine(template_config["project_id"], curve_config)
        return OfftakeEngine(template_config, curve).greenmesh_rollup(contracts)
