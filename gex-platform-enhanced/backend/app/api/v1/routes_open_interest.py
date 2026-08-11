"""
Open interest discovery routes.

THE ONE RULE THIS FILE EXISTS TO ENFORCE

The viewer's identity — company, jurisdiction, credit rating — is derived SERVER-SIDE from
the authenticated session and from `auth_users`. It is never read from the request body or
the query string. If a caller could supply their own `company_id` or `credit_rating`, every
publisher's confidentiality rule in `app.core.open_interest` becomes decorative: you would
simply claim to be whoever is allowed to look.

The request models below deliberately have no identity fields. `tests/test_open_interest_routes.py`
asserts that over the AST, because a reviewer will not reliably notice a field being added.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core import open_interest as oi
from app.core.db_backend import auth_connection
from app.core.request_tenant import company_from_payload, payload_from_request

router = APIRouter(prefix="/open-interest", tags=["Open Interest"])

try:
    oi.init_open_interest_db()
except Exception:  # pragma: no cover - schema init is best-effort at import
    pass


# ── identity, derived server-side ─────────────────────────────────────────────


def _profile_columns(company_id: str) -> tuple[Optional[str], Optional[str]]:
    """Jurisdiction and credit rating for a company, read from the one user store."""
    conn = auth_connection()
    try:
        cur = conn.execute(
            "SELECT jurisdiction, credit_rating FROM auth_users WHERE company_id = ?"
            " AND jurisdiction IS NOT NULL LIMIT 1",
            (company_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None, None
        return (
            row["jurisdiction"] if hasattr(row, "keys") else row[0],
            row["credit_rating"] if hasattr(row, "keys") else row[1],
        )
    finally:
        conn.close()


def viewer_from_request(request: Request) -> oi.ViewerProfile:
    """The only place a ViewerProfile is constructed for a request.

    Reads the verified JWT payload. A missing or unverified payload yields a profile with
    no company_id, which `publisher_permits` denies outright — fail closed.
    """
    payload = payload_from_request(request) or {}

    # Deliberately NOT company_from_payload(). That function answers "which tenant's rows
    # may this request read?" and returns the PLATFORM_ADMIN sentinel for staff — correct
    # for tenancy, wrong here. Confidentiality asks a different question: who is actually
    # looking. A publisher's denylist names a real company, so a viewer whose identity has
    # been replaced by a sentinel matches no rule and sees everything.
    #
    # This was a live bypass of the confirmed "admin does not bypass" decision, caught by
    # test_the_admin_flag_is_carried_but_still_does_not_bypass_confidentiality. Do not
    # "simplify" this back to company_from_payload.
    company_id = payload.get("company_id") or None
    if not company_id:
        return oi.ViewerProfile(company_id=None)

    jurisdiction, credit_rating = _profile_columns(company_id)
    return oi.ViewerProfile(
        company_id=company_id,
        jurisdiction=jurisdiction,
        credit_rating=credit_rating,
        is_platform_admin=bool(payload.get("is_platform_admin")),
    )


# ── request models — note the absence of any identity field ───────────────────


class VisibilityInput(BaseModel):
    denied_company_ids: list[str] = Field(default_factory=list)
    allowed_company_ids: Optional[list[str]] = None
    denied_jurisdictions: list[str] = Field(default_factory=list)
    allowed_jurisdictions: Optional[list[str]] = None
    min_credit_rating: Optional[str] = None

    def to_policy(self) -> oi.VisibilityPolicy:
        return oi.VisibilityPolicy(
            denied_company_ids=frozenset(self.denied_company_ids),
            allowed_company_ids=(
                frozenset(self.allowed_company_ids)
                if self.allowed_company_ids is not None
                else None
            ),
            denied_jurisdictions=frozenset(self.denied_jurisdictions),
            allowed_jurisdictions=(
                frozenset(self.allowed_jurisdictions)
                if self.allowed_jurisdictions is not None
                else None
            ),
            min_credit_rating=self.min_credit_rating,
        )


class PublishInterestInput(BaseModel):
    side: str
    molecule: Optional[str] = None
    volume_tpa: Optional[float] = None
    target_cod_year: Optional[int] = None
    term_years_min: Optional[int] = None
    jurisdiction: Optional[str] = None
    counterparty_rating: Optional[str] = None
    indicative_price_eur_t: Optional[float] = None
    note: Optional[str] = None
    state: str = oi.OPEN
    visibility: VisibilityInput = Field(default_factory=VisibilityInput)


# ── routes ────────────────────────────────────────────────────────────────────


@router.post("")
async def publish(request: Request, body: PublishInterestInput):
    """Publish an interest for the CALLER's company. The company is not a parameter."""
    payload = payload_from_request(request) or {}
    company_id = company_from_payload(payload)
    if not company_id:
        raise HTTPException(status_code=401, detail="authenticated identity required")

    try:
        return oi.publish_interest(
            company_id=company_id,
            side=body.side,
            created_by=payload.get("sub") or payload.get("user_id") or "unknown",
            policy=body.visibility.to_policy(),
            state=body.state,
            molecule=body.molecule,
            volume_tpa=body.volume_tpa,
            target_cod_year=body.target_cod_year,
            term_years_min=body.term_years_min,
            jurisdiction=body.jurisdiction,
            counterparty_rating=body.counterparty_rating,
            indicative_price_eur_t=body.indicative_price_eur_t,
            note=body.note,
        )
    except oi.InterestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def discover(
    request: Request,
    molecule: Optional[list[str]] = Query(default=None),
    side: Optional[list[str]] = Query(default=None),
    jurisdiction: Optional[list[str]] = Query(default=None),
    min_counterparty_credit: Optional[str] = Query(default=None),
    max_years_to_cod: Optional[int] = Query(default=None),
    as_of_year: Optional[int] = Query(default=None),
):
    """Interests the CALLER may see.

    Returns a bare list. There is no total and no hidden count — a count of what you
    cannot see discloses that it exists.
    """
    viewer = viewer_from_request(request)
    vfilter = oi.ViewerFilter(
        molecules=frozenset(molecule) if molecule else None,
        sides=frozenset(side) if side else None,
        jurisdictions=frozenset(jurisdiction) if jurisdiction else None,
        min_counterparty_credit=min_counterparty_credit,
        max_years_to_cod=max_years_to_cod,
    )
    return oi.discover(viewer, vfilter, as_of_year)
