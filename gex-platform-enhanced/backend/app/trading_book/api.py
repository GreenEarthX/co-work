"""
gex_platform/trading_book/api.py

FastAPI router for B1 trading book endpoints.

Mounted by the main app as:
    app.include_router(trading_book.router, prefix="/api/v1/trading-book")

The cashflow endpoint is the actual B1 unblock for gex_pf_engine —
once it's live, the DSCR heatmap and CFO Report stop citing plug numbers.

Dependencies:
    `get_db` — replaced by `tenant_session_dependency` in main.py: PostgreSQL
    only, as gex_app, with the caller's tenant set on every transaction.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.trading_book.cashflows import (
    CashflowProjection,
    generate_cashflows_for_project,
)
from app.trading_book.models import (
    Asset,
    Contract,
    ContractStatus,
    Counterparty,
    FixedPriceContract,
    IndexDefinition,
    IndexHistory,
    IndexLinkedContract,
    ProjectFinanceLink,
)
from app.trading_book import schemas as sc


# ──────────────────────────────────────────────────────────────────────
# DB dependency
# ──────────────────────────────────────────────────────────────────────

def get_db() -> Iterator[Session]:
    """Never used as is: main.py installs tenant_session_dependency() over it.
    It refuses rather than inventing a database address (it used to default to
    postgresql+psycopg://localhost/gex, a database that does not exist)."""
    raise RuntimeError("trading_book.get_db is not configured; main.py installs "
                       "tenant_session_dependency over it")
    yield  # pragma: no cover — makes this a generator dependency


def tenant_session_dependency(session_factory):
    """The trading book's real DB dependency: PostgreSQL only (JML, 2026-10-23),
    running as gex_app under alembic 064's policies.

    The caller's tenant is set at the start of EVERY transaction, not once: a
    handler's commit ends the transaction and SET LOCAL with it, and the next
    statement must not run unscoped. main.py installs this over get_db; tests
    install it with a session factory bound to a throwaway database.
    """
    from sqlalchemy import event, text

    def dependency(request: Request):
        from app.core.db_backend import market_is_postgres, require_postgres
        from app.db.session import (_company_id_from_request, _sanitise_company_id,
                                    _sanitise_user_id, _user_id_from_request)

        require_postgres(market_is_postgres(), "The trading book", "MARKET_DB_BACKEND")
        company = _sanitise_company_id(_company_id_from_request(request) or "GUEST")
        user = _sanitise_user_id(_user_id_from_request(request))
        with session_factory() as session:
            @event.listens_for(session, "after_begin")
            def _scope(_s, _t, connection):
                connection.execute(text(
                    "SELECT set_config('app.current_company_id', :c, true), "
                    "set_config('app.current_user_id', :u, true)"), {"c": company, "u": user})
            yield session

    return dependency


# ──────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["trading-book"])


# ──────────────────────────────────────────────────────────────────────
# Who may do what (gap register G-05, 2026-10-23; alembic 064)
#
#   asset        the project's companies read it; only the project owner writes it
#   contract     the booking company (owner_company_id, from the caller, never the
#                body) writes it; it and any company seeing a linked asset read it
#   link         the asset's project owner, for a contract in its own book
#   counterparty any signed-in company reads and adds; GEX corrects
#   index        reference data: everyone reads, GEX staff write
#
# GEX operates the platform and books nothing. On PostgreSQL the same rules are
# RLS policies (064), so these checks are the clear refusal, not the only wall.
# ──────────────────────────────────────────────────────────────────────

CONTRACT_TRANSITIONS: dict[ContractStatus, tuple[ContractStatus, ...]] = {
    ContractStatus.DRAFT: (ContractStatus.PROPOSED, ContractStatus.TERMINATED),
    ContractStatus.PROPOSED: (ContractStatus.COMMITTED, ContractStatus.DRAFT, ContractStatus.TERMINATED),
    ContractStatus.COMMITTED: (ContractStatus.TERMINATED, ContractStatus.EXPIRED),
}


def _refuse(code: int, key: str, message: str):
    raise HTTPException(status_code=code, detail={"code": key, "message": message})


def _caller(request: Request) -> dict:
    payload = getattr(request.state, "user_payload", None) or {}
    if not (payload.get("user_id") or payload.get("sub")):
        _refuse(401, "AUTHENTICATION_REQUIRED", "Sign in to use the trading book.")
    return payload


def _is_gex(caller: dict) -> bool:
    return bool(caller.get("is_platform_admin"))


def _trader(caller: dict) -> str:
    if _is_gex(caller):
        _refuse(403, "GEX_DOES_NOT_TRADE", "GEX operates the platform and books nothing.")
    if not caller.get("company_id"):
        _refuse(403, "NO_COMPANY", "Your account belongs to no company.")
    return caller["company_id"]


def _gex_only(caller: dict) -> None:
    if not _is_gex(caller):
        _refuse(403, "GEX_REFERENCE_DATA", "Index definitions are reference data; GEX staff maintain them.")


def _profile(project_id: str):
    from app.core.project_registry import get_project_profile
    return get_project_profile(project_id)


def _sees_asset(caller: dict, asset: Asset) -> bool:
    if _is_gex(caller):
        return True
    profile = _profile(asset.project_id)
    return bool(profile) and caller.get("company_id") in profile.stakeholder_company_ids


def _owns_project(caller: dict, project_id: str) -> bool:
    profile = _profile(project_id)
    return bool(profile) and profile.owner_company_id == caller.get("company_id")


def _sees_contract(caller: dict, db: Session, contract: Contract) -> bool:
    if _is_gex(caller) or contract.owner_company_id == caller.get("company_id"):
        return True
    assets = db.execute(select(Asset).join(ProjectFinanceLink, ProjectFinanceLink.project_asset_id == Asset.id)
                        .where(ProjectFinanceLink.contract_id == contract.id)).scalars().all()
    return any(_sees_asset(caller, a) for a in assets)


def _asset(db: Session, caller: dict, asset_id: uuid.UUID) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None or not _sees_asset(caller, asset):
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return asset


def _contract(db: Session, caller: dict, contract_id: uuid.UUID) -> Contract:
    contract = db.get(Contract, contract_id)
    if contract is None or not _sees_contract(caller, db, contract):
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")
    return contract


def _contract_read(contract: Contract):
    if isinstance(contract, IndexLinkedContract):
        return sc.IndexLinkedContractRead.model_validate(contract)
    return sc.FixedPriceContractRead.model_validate(contract)


def _commit(db: Session, what: str) -> None:
    from sqlalchemy.exc import IntegrityError
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _refuse(409, "CONFLICT", f"{what} conflicts with an existing record: {exc.orig}")


@router.get("/health", summary="Trading book module health check")
def health() -> dict:
    return {"status": "ok", "module": "trading_book", "phase": "B1"}


@router.get(
    "/projects/{asset_id}/cashflows",
    response_model=CashflowProjection,
    summary="Project cashflow projection (B1 unblock for gex_pf_engine)",
)
def get_project_cashflows(
    asset_id: uuid.UUID,
    request: Request,
    from_date: Optional[date] = Query(
        default=None,
        description="Start of projection window. Defaults to today.",
    ),
    to_date: Optional[date] = Query(
        default=None,
        description="End of projection window. Defaults to from_date + 20 years.",
    ),
    granularity: str = Query(default="monthly", pattern="^monthly$"),
    db: Session = Depends(get_db),
) -> CashflowProjection:
    """Return the cashflow projection for one project asset.

    For each ProjectFinanceLink on the asset, expands the linked Contract
    into monthly cashflow rows over [from_date, to_date], applying:
      - sign convention from line_item_type
      - floor/cap collar on IndexLinkedContract
      - forward-extrapolation for periods beyond IndexHistory (flagged)
      - allocation_share at the link level

    `gex_pf_engine` consumes this for DSCR rollup and the heatmap stress.
    """
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        # 20-year default window — covers most green-fuels offtake tenors.
        to_date = date(from_date.year + 20, from_date.month, from_date.day)
    if to_date < from_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="to_date must be on or after from_date",
        )

    asset = _asset(db, _caller(request), asset_id)

    # Fetch links + their contracts. selectinload pulls contracts in one query.
    links = db.execute(
        select(ProjectFinanceLink)
        .where(ProjectFinanceLink.project_asset_id == asset_id)
        .options(selectinload(ProjectFinanceLink.contract))
    ).scalars().all()

    # For each link, fetch the contract polymorphically (so we get the right
    # subtype) plus relevant IndexHistory if it's an IndexLinkedContract.
    triples: list[tuple[ProjectFinanceLink, Contract, list[IndexHistory]]] = []
    for link in links:
        # Reload contract polymorphically — the selectinload above gives us
        # the parent row; we need the subtype for isinstance checks.
        contract = db.get(Contract, link.contract_id)
        if contract is None:
            continue

        history: list[IndexHistory] = []
        if isinstance(contract, IndexLinkedContract):
            history = db.execute(
                select(IndexHistory)
                .where(IndexHistory.index_definition_id == contract.index_definition_id)
                .order_by(IndexHistory.observation_date)
            ).scalars().all()

        triples.append((link, contract, history))

    return generate_cashflows_for_project(
        asset=asset,
        links_with_contracts=triples,
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,
    )


@router.get(
    "/projects/{asset_id}/contracts",
    summary="List contracts attached to a project (via ProjectFinanceLink)",
)
def list_project_contracts(
    asset_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Lightweight listing — full contract reads via /contracts/{id}."""
    _asset(db, _caller(request), asset_id)

    links = db.execute(
        select(ProjectFinanceLink).where(ProjectFinanceLink.project_asset_id == asset_id)
    ).scalars().all()

    out: list[dict] = []
    for link in links:
        contract = db.get(Contract, link.contract_id)
        if contract is None:
            continue
        out.append(
            {
                "link_id": str(link.id),
                "contract_id": str(contract.id),
                "contract_number": contract.contract_number,
                "contract_type": contract.contract_type,
                "fuel_type": contract.fuel_type,
                "line_item_type": link.line_item_type.value,
                "allocation_share": str(link.allocation_share),
                "effective_date": contract.effective_date.isoformat(),
                "termination_date": contract.termination_date.isoformat(),
                "notional_quantity": str(contract.notional_quantity),
                "quantity_unit": contract.quantity_unit,
                "currency": contract.currency,
                "status": contract.status.value,
            }
        )
    return out


# ──────────────────────────────────────────────────────────────────────
# Assets
# ──────────────────────────────────────────────────────────────────────

@router.post("/assets", response_model=sc.AssetRead, status_code=201, summary="Register a project's asset")
def create_asset(body: sc.AssetCreate, request: Request, db: Session = Depends(get_db)):
    caller = _caller(request)
    _trader(caller)
    if not _owns_project(caller, body.project_id):
        _refuse(403, "NOT_YOUR_PROJECT", "Only the company that owns the project registers its asset.")
    asset = Asset(**body.model_dump())
    db.add(asset)
    _commit(db, "Asset")
    db.refresh(asset)
    return asset


@router.get("/assets", response_model=list[sc.AssetRead], summary="Assets of the projects I can see")
def list_assets(request: Request, project_id: Optional[str] = None, db: Session = Depends(get_db)):
    caller = _caller(request)
    q = select(Asset).order_by(Asset.name)
    if project_id:
        q = q.where(Asset.project_id == project_id)
    return [a for a in db.execute(q).scalars().all() if _sees_asset(caller, a)]


@router.get("/assets/{asset_id}", response_model=sc.AssetRead)
def get_asset(asset_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    return _asset(db, _caller(request), asset_id)


@router.patch("/assets/{asset_id}", response_model=sc.AssetRead)
def update_asset(asset_id: uuid.UUID, body: sc.AssetUpdate, request: Request, db: Session = Depends(get_db)):
    caller = _caller(request)
    _trader(caller)
    asset = _asset(db, caller, asset_id)
    if not _owns_project(caller, asset.project_id):
        _refuse(403, "NOT_YOUR_PROJECT", "Only the project owner changes its asset.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(asset, k, v)
    _commit(db, "Asset")
    db.refresh(asset)
    return asset


# ──────────────────────────────────────────────────────────────────────
# Counterparties — a shared register of legal entities
# ──────────────────────────────────────────────────────────────────────

@router.post("/counterparties", response_model=sc.CounterpartyRead, status_code=201)
def create_counterparty(body: sc.CounterpartyCreate, request: Request, db: Session = Depends(get_db)):
    _caller(request)
    cp = Counterparty(**body.model_dump())
    db.add(cp)
    _commit(db, "Counterparty")
    db.refresh(cp)
    return cp


@router.get("/counterparties", response_model=list[sc.CounterpartyRead])
def list_counterparties(request: Request, db: Session = Depends(get_db)):
    _caller(request)
    return db.execute(select(Counterparty).order_by(Counterparty.legal_name)).scalars().all()


@router.patch("/counterparties/{counterparty_id}", response_model=sc.CounterpartyRead)
def update_counterparty(counterparty_id: uuid.UUID, body: sc.CounterpartyUpdate, request: Request,
                        db: Session = Depends(get_db)):
    caller = _caller(request)
    if not _is_gex(caller):
        _refuse(403, "SHARED_REGISTER", "A counterparty is shared by every book; GEX staff correct it.")
    cp = db.get(Counterparty, counterparty_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="Counterparty not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cp, k, v)
    _commit(db, "Counterparty")
    db.refresh(cp)
    return cp


# ──────────────────────────────────────────────────────────────────────
# Price indices — reference data
# ──────────────────────────────────────────────────────────────────────

@router.get("/indices", response_model=list[sc.IndexDefinitionRead])
def list_indices(request: Request, db: Session = Depends(get_db)):
    _caller(request)
    return db.execute(select(IndexDefinition).order_by(IndexDefinition.provider,
                                                       IndexDefinition.index_code)).scalars().all()


@router.post("/indices", response_model=sc.IndexDefinitionRead, status_code=201)
def create_index(body: sc.IndexDefinitionCreate, request: Request, db: Session = Depends(get_db)):
    _gex_only(_caller(request))
    idx = IndexDefinition(**body.model_dump())
    db.add(idx)
    _commit(db, "Index")
    db.refresh(idx)
    return idx


@router.patch("/indices/{index_id}", response_model=sc.IndexDefinitionRead)
def update_index(index_id: uuid.UUID, body: sc.IndexDefinitionUpdate, request: Request,
                 db: Session = Depends(get_db)):
    _gex_only(_caller(request))
    idx = db.get(IndexDefinition, index_id)
    if idx is None:
        raise HTTPException(status_code=404, detail="Index not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(idx, k, v)
    _commit(db, "Index")
    db.refresh(idx)
    return idx


@router.get("/indices/{index_id}/history", response_model=list[sc.IndexHistoryRead])
def list_index_history(index_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _caller(request)
    return db.execute(select(IndexHistory).where(IndexHistory.index_definition_id == index_id)
                      .order_by(IndexHistory.observation_date)).scalars().all()


@router.post("/indices/{index_id}/history", response_model=sc.IndexHistoryRead, status_code=201)
def add_index_observation(index_id: uuid.UUID, body: sc.IndexHistoryCreate, request: Request,
                          db: Session = Depends(get_db)):
    _gex_only(_caller(request))
    if body.index_definition_id != index_id:
        _refuse(422, "INDEX_MISMATCH", "The body names a different index than the path.")
    if db.get(IndexDefinition, index_id) is None:
        raise HTTPException(status_code=404, detail="Index not found")
    obs = IndexHistory(**body.model_dump())
    db.add(obs)
    _commit(db, "Observation")
    db.refresh(obs)
    return obs


# ──────────────────────────────────────────────────────────────────────
# Contracts — booked by the caller's company
# ──────────────────────────────────────────────────────────────────────

def _book(db: Session, request: Request, cls, body) -> Contract:
    company = _trader(_caller(request))
    for side in (body.buy_side_id, body.sell_side_id):
        if db.get(Counterparty, side) is None:
            _refuse(422, "UNKNOWN_COUNTERPARTY", f"Counterparty {side} is not registered.")
    data = body.model_dump()
    if cls is IndexLinkedContract and db.get(IndexDefinition, body.index_definition_id) is None:
        _refuse(422, "UNKNOWN_INDEX", f"Index {body.index_definition_id} is not registered.")
    contract = cls(**data, owner_company_id=company)
    db.add(contract)
    _commit(db, "Contract")
    db.refresh(contract)
    return contract


@router.post("/contracts/fixed-price", response_model=sc.FixedPriceContractRead, status_code=201)
def create_fixed_price_contract(body: sc.FixedPriceContractCreate, request: Request,
                                db: Session = Depends(get_db)):
    return _book(db, request, FixedPriceContract, body)


@router.post("/contracts/index-linked", response_model=sc.IndexLinkedContractRead, status_code=201)
def create_index_linked_contract(body: sc.IndexLinkedContractCreate, request: Request,
                                 db: Session = Depends(get_db)):
    return _book(db, request, IndexLinkedContract, body)


@router.get("/contracts", summary="My book, and contracts behind assets I can see")
def list_contracts(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    caller = _caller(request)
    rows = db.execute(select(Contract).order_by(Contract.trade_date.desc())).scalars().all()
    return [_contract_read(c).model_dump(mode="json") for c in rows if _sees_contract(caller, db, c)]


@router.get("/contracts/{contract_id}")
def get_contract(contract_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    return _contract_read(_contract(db, _caller(request), contract_id)).model_dump(mode="json")


@router.patch("/contracts/{contract_id}/status")
def update_contract_status(contract_id: uuid.UUID, body: sc.ContractStatusUpdate, request: Request,
                           db: Session = Depends(get_db)) -> dict:
    caller = _caller(request)
    company = _trader(caller)
    contract = _contract(db, caller, contract_id)
    if contract.owner_company_id != company:
        _refuse(403, "NOT_YOUR_BOOK", "Only the company whose book it is changes a contract.")
    if body.status not in CONTRACT_TRANSITIONS.get(contract.status, ()):
        _refuse(409, "INVALID_TRANSITION",
                f"{contract.status.value} -> {body.status.value} is not allowed; "
                f"allowed: {[s.value for s in CONTRACT_TRANSITIONS.get(contract.status, ())]}")
    contract.status = body.status
    _commit(db, "Contract")
    db.refresh(contract)
    return _contract_read(contract).model_dump(mode="json")


# ──────────────────────────────────────────────────────────────────────
# Project-finance links — allocate a contract's cashflows to an asset
# ──────────────────────────────────────────────────────────────────────

def _link_owner_check(caller: dict, db: Session, asset_id: uuid.UUID, contract_id: uuid.UUID) -> None:
    company = _trader(caller)
    asset = _asset(db, caller, asset_id)
    if not _owns_project(caller, asset.project_id):
        _refuse(403, "NOT_YOUR_PROJECT", "Only the project owner allocates cashflows to its asset.")
    contract = db.get(Contract, contract_id)
    if contract is None or contract.owner_company_id != company:
        _refuse(403, "NOT_YOUR_BOOK", "Only a contract in your own book can be allocated.")


@router.post("/links", response_model=sc.ProjectFinanceLinkRead, status_code=201)
def create_link(body: sc.ProjectFinanceLinkCreate, request: Request, db: Session = Depends(get_db)):
    _link_owner_check(_caller(request), db, body.project_asset_id, body.contract_id)
    link = ProjectFinanceLink(**body.model_dump())
    db.add(link)
    _commit(db, "Link")
    db.refresh(link)
    return link


@router.patch("/links/{link_id}", response_model=sc.ProjectFinanceLinkRead)
def update_link(link_id: uuid.UUID, body: sc.ProjectFinanceLinkUpdate, request: Request,
                db: Session = Depends(get_db)):
    caller = _caller(request)
    link = db.get(ProjectFinanceLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    _link_owner_check(caller, db, link.project_asset_id, link.contract_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(link, k, v)
    _commit(db, "Link")
    db.refresh(link)
    return link


@router.delete("/links/{link_id}", status_code=204)
def delete_link(link_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    caller = _caller(request)
    link = db.get(ProjectFinanceLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    _link_owner_check(caller, db, link.project_asset_id, link.contract_id)
    db.delete(link)
    _commit(db, "Link")
    return None


__all__ = ["router", "get_db", "tenant_session_dependency"]
