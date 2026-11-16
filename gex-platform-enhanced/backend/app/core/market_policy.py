"""
Who may act in the market (decision D-B, JML 2026-11-14) — the ONE table.

Before this, the market engine checked only "a company, not GEX" (discovery review F04): a
producer CFO or an engineer could create RFQs and binding proposals through the API although
the menu hid those screens from them. Now:

  * Commercial acts: lists supply, raises RFQs, sends enquiries, makes, accepts and declines
    binding proposals, and raises its company's trade confirmation (the first pair of eyes).
  * The CEO (EXECUTIVE) and the CFO (FINANCE_TREASURY) read everything and give the SECOND
    approval of a trade confirmation (core/wae.py, TRADE_CONFIRM).
  * Engineering and Operations read. Operations may declare a capacity (a plant fact).

The market engine, the order book and the token and capacity routes call `require`; the screens
ask `GET /api/v1/market/policy` and hide what the caller may not do, so menu, URL and API follow
one rule. Changing who may act is JML's decision and is made HERE, nowhere else.
"""
from __future__ import annotations

from typing import Optional

COMMERCIAL, EXECUTIVE, FINANCE, OPERATIONS = "COMMERCIAL", "EXECUTIVE", "FINANCE_TREASURY", "OPERATIONS"
ENGINEERING, COMPLIANCE = "ENGINEERING", "COMPLIANCE_LEGAL"

# action -> (business functions allowed, what a person reads)
POLICY: dict[str, tuple[frozenset[str], str]] = {
    "capacity.create":       (frozenset({COMMERCIAL, OPERATIONS}), "Declaring a production capacity"),
    "token.mint":            (frozenset({COMMERCIAL}), "Tokenising capacity"),
    "listing.create":        (frozenset({COMMERCIAL}), "Listing supply"),
    "listing.open":          (frozenset({COMMERCIAL}), "Publishing a listing"),
    "listing.withdraw":      (frozenset({COMMERCIAL}), "Withdrawing a listing"),
    "rfq.create":            (frozenset({COMMERCIAL}), "Raising an RFQ"),
    "rfq.change":            (frozenset({COMMERCIAL}), "Publishing or withdrawing an RFQ"),
    "enquiry.send":          (frozenset({COMMERCIAL}), "Sending an enquiry"),
    "enquiry.reply":         (frozenset({COMMERCIAL}), "Answering an enquiry"),
    "proposal.create":       (frozenset({COMMERCIAL}), "Making a binding proposal"),
    "proposal.accept":       (frozenset({COMMERCIAL}), "Accepting a binding proposal"),
    "proposal.decline":      (frozenset({COMMERCIAL}), "Declining a proposal"),
    "order.create":          (frozenset({COMMERCIAL}), "Placing an order"),
    "order.change":          (frozenset({COMMERCIAL}), "Opening or cancelling an order"),
    "order.accept":          (frozenset({COMMERCIAL}), "Accepting an order"),
    "quote.create":          (frozenset({COMMERCIAL}), "Quoting on an RFQ"),
    "quote.accept":          (frozenset({COMMERCIAL}), "Accepting a quote"),
    "trade.confirm.request": (frozenset({COMMERCIAL}), "Raising your company's trade confirmation"),
    "trade.confirm.approve": (frozenset({EXECUTIVE, FINANCE}), "Approving a trade confirmation"),
    # Phase 1 (116): the owning company's product facts. Not a trade, so wider than Commercial.
    "product.declare":       (frozenset({COMMERCIAL, OPERATIONS, ENGINEERING, COMPLIANCE}),
                              "Recording product quality, carbon intensity or a certificate"),
}

_WHO = {COMMERCIAL: "Commercial", EXECUTIVE: "the CEO", FINANCE: "the CFO", OPERATIONS: "Operations",
        ENGINEERING: "Engineering", COMPLIANCE: "Compliance"}


def allows(business_function: Optional[str], action: str) -> bool:
    functions, _ = POLICY[action]
    return business_function in functions


def who(action: str) -> str:
    names = [_WHO.get(f, f) for f in sorted(POLICY[action][0])]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def refusal(business_function: Optional[str], action: str) -> Optional[tuple[int, str, str]]:
    """(status, code, message) when this function may not do this action, else None."""
    if allows(business_function, action):
        return None
    return (403, "ROLE_NOT_ALLOWED",
            f"{POLICY[action][1]} is done by {who(action)} in your company. Ask a colleague there.")


def allowed_actions(business_function: Optional[str]) -> list[str]:
    return sorted(a for a in POLICY if allows(business_function, a))


def require_payload(payload: dict, action: str) -> None:
    """For routes that hold the token payload, not a market Party."""
    from fastapi import HTTPException

    if (payload or {}).get("is_platform_admin"):     # GEX is refused as GEX, never as a role
        raise HTTPException(403, {"code": "GEX_DOES_NOT_TRADE",
                                  "message": "GEX operates the market and trades nothing."})
    r = refusal((payload or {}).get("business_function"), action)
    if r:
        raise HTTPException(r[0], {"code": r[1], "message": r[2]})
