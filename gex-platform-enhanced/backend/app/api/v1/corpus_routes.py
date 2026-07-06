"""
External Adjacency Corpus routes — thin surface over app.core.external_corpus.

Everything served here is an EXTERNAL_PRIOR (benchmark/nudge context). By ruled
policy it never enters gate evaluation or bankability scoring — the leak-guard
test enforces the import boundary.

Mount in main.py:
    from app.api.v1.corpus_routes import router as corpus_router, init_db as corpus_init_db
    corpus_init_db()
    app.include_router(corpus_router, prefix="/api/v1/corpus", tags=["External Corpus"])
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app.core import external_corpus as xc

router = APIRouter()
init_db = xc.init_db


class SnapshotImport(BaseModel):
    source: str                      # e.g. "IEA_H2_DB"
    source_version: str              # e.g. "2025-10"
    license: str                     # e.g. "CC BY 4.0"
    attribution: str                 # the signed attribution line
    retrieved_at: str
    imported_by: str
    rows: list[dict] = Field(default_factory=list)


class MappingSignoff(BaseModel):
    source: str
    field: str                       # fuel_id | technology_class | status | pathway_class
    raw_label: str
    gex_value: str
    mapped_by: str


@router.get("/summary")
def summary() -> dict[str, Any]:
    return xc.corpus_summary()


@router.post("/import", status_code=201)
def import_snapshot(body: SnapshotImport) -> dict[str, Any]:
    """Import one hash-anchored snapshot. License + attribution are REQUIRED
    fields — an unlicensed import cannot be expressed."""
    if not body.license.strip() or not body.attribution.strip():
        raise HTTPException(422, "license and attribution are required — "
                                 "no unlicensed corpus data")
    return xc.import_snapshot(**body.model_dump())


@router.post("/taxonomy/sign")
def sign_mapping(body: MappingSignoff) -> dict[str, Any]:
    """Census-then-sign: a human maps one OBSERVED external label to GEX vocabulary."""
    xc.sign_mapping(body.source, body.field, body.raw_label, body.gex_value, body.mapped_by)
    return {"signed": body.model_dump(), "note": "re-import the snapshot to lift quarantines"}


@router.get("/density")
def density(fuel_id: str, technology_class: Optional[str] = None,
            jurisdiction: Optional[str] = None,
            pathway_class: Optional[str] = None) -> dict[str, Any]:
    return xc.density({"fuel_id": fuel_id, "technology_class": technology_class,
                       "jurisdiction": jurisdiction, "pathway_class": pathway_class})


@router.get("/base-rates")
def base_rates(fuel_id: Optional[str] = None,
               jurisdiction: Optional[str] = None) -> dict[str, Any]:
    return xc.base_rates(fuel_id, jurisdiction)
