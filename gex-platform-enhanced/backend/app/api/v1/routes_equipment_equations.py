"""
Equipment equations — the last Supabase caller in the frontend.

Increment 4 of `docs/supabase-cutover-endpoints.md`. Replaces
`useEquipmentEquations`, which read, upserted and deleted
`equipment_equations` straight from the browser under the bundled anon key.

THE DELETE IS THE POINT (CLAUDE_HANDOFF §8.16)

    supabase.from("equipment_equations").delete().eq("id", id)

Every other query in that hook filtered on `user_id`. The delete did not, so
with the anon key it removed any row by id, for anybody. Here the owner comes
from the bearer token and a row that is not the caller's matches nothing —
answered **404, not 403**, because a 403 would confirm the id exists.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core import equations_store
from app.core.equations_store import EquationNotFound

router = APIRouter()


class EquationBody(BaseModel):
    plant_slug: str
    equipment_node_id: str
    equation_id: str
    equation_expression: str
    output_param: str
    equipment_label: str = ""
    variable_bindings: dict[str, Any] = Field(default_factory=dict)


def _owner(request: Request) -> str:
    payload = getattr(request.state, "auth_user_payload", None)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required")
    owner = payload.get("user_id")
    if not owner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token carries no user identity")
    return owner


@router.get("")
def list_equations(request: Request,
                   plant_slug: str = Query(...),
                   node_id: str = Query(...)) -> list[dict[str, Any]]:
    """The caller's equations for one node of one plant."""
    return equations_store.list_equations(_owner(request), plant_slug, node_id)


@router.put("")
def upsert_equation(request: Request,
                    body: EquationBody = Body(...)) -> dict[str, Any]:
    """Create or update one equation, keyed on (plant, node, equation)."""
    return equations_store.upsert_equation(
        _owner(request),
        plant_slug=body.plant_slug,
        equipment_node_id=body.equipment_node_id,
        equipment_label=body.equipment_label,
        equation_id=body.equation_id,
        equation_expression=body.equation_expression,
        output_param=body.output_param,
        variable_bindings=body.variable_bindings,
    )


@router.delete("/{row_id}", status_code=204, response_model=None)
def delete_equation(row_id: str, request: Request) -> None:
    try:
        equations_store.delete_equation(_owner(request), row_id)
    except EquationNotFound:
        raise HTTPException(status_code=404, detail="No such equation")
