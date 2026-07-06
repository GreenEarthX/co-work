"""
app/trading_book

B1 (Bankability Phase 1) trading book module.

Trading in GEX = Buy/Sell physical tokenised green-fuel products plus
optional paper/derivatives. The security components (ABAC, JWT, SoD,
DRPL, WAE) remain core elements delivering clean, transparent, auditable
processes — they are NOT duplicated here.

Public surface:
    - Models: Asset, Counterparty, IndexDefinition, IndexHistory,
              Contract, FixedPriceContract, IndexLinkedContract,
              ProjectFinanceLink
    - Schemas: *Create, *Read, *Update for each entity
    - Cashflow generator: generate_cashflows_for_project()
    - FastAPI router: router

NOTE on PFLineItemType.DEBT_SERVICE / CAPEX:
    These are NOT trading cashflows. They exist so that non-trading
    cashflow sources (lender facilities, EPC milestone payments) can share
    the same period grid as offtake revenue for DSCR computation. The
    trading book proper only originates REVENUE and OPEX lines from
    actual Buy/Sell contracts.

NOTE on contract novation (B2/B3 scope):
    An offtake being novated to a third party (A→B novated to A→C)
    requires trade ledger recognition: TERMINATED on the original,
    new contract with the incoming counterparty, plus a novation-chain
    audit record. Not modelled in B1.
"""

from app.trading_book.models import (
    Asset,
    Base,
    Contract,
    ContractStatus,
    Counterparty,
    FixedPriceContract,
    IndexDefinition,
    IndexHistory,
    IndexLinkedContract,
    PFLineItemType,
    ProjectFinanceLink,
)
from app.trading_book.cashflows import (
    CashflowProjection,
    CashflowRow,
    PeriodSummary,
    generate_cashflows_for_project,
)
from app.trading_book.api import router

__all__ = [
    # ORM
    "Base",
    "ContractStatus",
    "PFLineItemType",
    "Asset",
    "Counterparty",
    "IndexDefinition",
    "IndexHistory",
    "Contract",
    "FixedPriceContract",
    "IndexLinkedContract",
    "ProjectFinanceLink",
    # Cashflows
    "CashflowRow",
    "PeriodSummary",
    "CashflowProjection",
    "generate_cashflows_for_project",
    # API
    "router",
]
