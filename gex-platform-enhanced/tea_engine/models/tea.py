"""Pydantic contract for the GEX TEA engine (port 8002).

Inputs mirror a GEX pathway's `engineering` layer (process_units + financial
assumptions). Outputs are shaped to (a) populate gex_pf_engine.PlantSummary and
(b) be recorded as truth-stack EVIDENCE — never as a self-verified base case.
The result is always PROVISIONAL: claim_state='submitted'. Promotion to
'verified' happens elsewhere, via an IE/CFO APPROVAL_DECISION.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProcessUnitSpec(BaseModel):
    """One process unit → one OpenPyTEA Equipment costing."""
    model_config = ConfigDict(extra="ignore")

    id:           str
    category:     str                    # OpenPyTEA cost-correlation category (exact taxonomy)
    material:     str = "Carbon steel"   # OpenPyTEA material
    sizing:       float = Field(gt=0)    # the `param` cost is correlated against
    utilities:    list[str] = Field(default_factory=list)
    # passthrough for the real OpenPyTEA Equipment constructor
    equipment_type: Optional[str] = None   # OpenPyTEA `type` (e.g. "Compressor, centrifugal")
    process_type:   str = "Fluids"         # Fluids | Solids | Mixed


class FinancialAssumptions(BaseModel):
    """The assumption basis — recorded as its own evidence entry (assumption pack)."""
    model_config = ConfigDict(extra="ignore")

    discount_rate_pct:   float = 8.0
    electricity_eur_mwh: float = 60.0
    capacity_factor:     float = Field(default=0.6, gt=0, le=1)
    project_life_years:  int = 20
    contingency_pct:     float = 15.0
    co2_eur_t:           float = 50.0
    hydrogen_eur_t:      float = 3000.0     # green H2 ≈ 3 EUR/kg
    feedstock_oil_eur_t: float = 1200.0     # waste lipid (UCO/tallow) for HEFA biofuels


class TEAComputeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id:         str
    pathway_id:         str
    # Optional: if omitted, the molecule's canonical process function (derived from
    # fuel_id) supplies the equipment train. Supplying it overrides the registry.
    process_units:      list[ProcessUnitSpec] = Field(default_factory=list)
    assumptions:        FinancialAssumptions = Field(default_factory=FinancialAssumptions)
    nameplate_capacity: float = Field(gt=0)
    nameplate_unit:     str = "t_per_year"
    fuel_id:            str = "E_METHANOL"
    # passthrough for the real OpenPyTEA Plant constructor
    country:               str = "Netherlands"      # drives OpenPyTEA location factors
    plant_process_type:    str = "Fluids"
    variable_opex_inputs:  dict = Field(default_factory=dict)  # {stream:{consumption,price}}


class PlantSummaryExtract(BaseModel):
    """The exact subset gex_pf_engine.PlantSummary consumes (verification_state
    deliberately UNVERIFIED — a raw run is never trusted)."""
    capex_eur:          float
    opex_eur_per_year:  float
    nameplate_capacity: float
    nameplate_unit:     str
    verification_state: Literal["UNVERIFIED"] = "UNVERIFIED"


class EvidenceEntryProposal(BaseModel):
    """Shape of the CanonicalLedgerEntry the backend will append to the ledger.
    Returned as data (not appended here) so tea_engine takes no ledger write
    authority it shouldn't have."""
    kind:        Literal["derived"] = "derived"
    entry_type:  Literal["projection_snapshot"] = "projection_snapshot"
    produced_by: Literal["tea_engine"] = "tea_engine"
    payload:     dict


class TEAResult(BaseModel):
    engine:           str                 # "openpytea" | "stub"
    cost_basis_hash:  str                 # deterministic hash of the request config
    lcop:             float               # levelized cost of product (per nameplate unit)
    plant_summary:    PlantSummaryExtract
    run_evidence:     EvidenceEntryProposal
    process_function: Optional[dict] = None  # molecule process-function meta (None ⇒ caller-supplied train)
    regime:           Optional[dict] = None  # regulatory-regime fork (cert / GHG / subsidy) by pathway_class
    model_claim_state: Literal["submitted"] = "submitted"   # PROVISIONAL, never verified here
    note:             str = ("Provisional cost basis. Promote to model_base_case "
                             "only via IE/CFO approval_decision; no release-gated "
                             "compute until then.")


class SensitivityVar(BaseModel):
    parameter: str
    low_lcop:  float
    high_lcop: float


class TEASensitivityResult(BaseModel):
    engine:          str
    cost_basis_hash: str
    base_lcop:       float
    tornado:         list[SensitivityVar]
    run_evidence:    EvidenceEntryProposal
