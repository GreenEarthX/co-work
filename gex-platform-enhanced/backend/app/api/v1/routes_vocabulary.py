"""
Canonical vocabulary API (ADR 2026-07-29).

Serves app/core/vocabulary.py so every surface — front-end, reports, exports —
renders the same words for the same state. Clients must NOT keep their own
label maps; that is how the platform ended up with four evidence vocabularies.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.vocabulary import CONCEPTS, export, to_canonical

router = APIRouter(prefix="/api/v1/vocabulary", tags=["vocabulary"])


@router.get("")
def get_vocabulary() -> dict:
    """The whole registry — canonical values, labels, descriptions, buckets."""
    return export()


@router.get("/{concept}")
def get_concept(concept: str) -> dict:
    if concept not in CONCEPTS:
        raise HTTPException(
            404,
            f"Unknown concept {concept!r}. Known: {sorted(CONCEPTS)}",
        )
    return export()["concepts"][concept]


@router.get("/{concept}/translate")
def translate(concept: str, vocabulary: str, value: str) -> dict:
    """
    Map a legacy/parallel vocabulary value onto the canonical one.
    Used when migrating a module off its private enum.
    """
    if concept not in CONCEPTS:
        raise HTTPException(404, f"Unknown concept {concept!r}")
    try:
        canonical = to_canonical(concept, vocabulary, value)
    except KeyError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"concept": concept, "vocabulary": vocabulary,
            "value": value, "canonical": canonical}
