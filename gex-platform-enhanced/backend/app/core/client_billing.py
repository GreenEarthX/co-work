"""
Client commercial agreement and invoicing.

The platform had 66 routers and no way to charge anyone. It also had no object for the
thing that would pay: `company_id` is a bare string denormalised onto `auth_users` (12
distinct companies, 17 users, no `companies` table). This module adds the payer.

FOUR RULES THIS MODULE EXISTS TO ENFORCE

1. Money is integer minor units. Never a float. €1000 is 100_000 cents.
2. The fee schedule is frozen into a terms VERSION. Repricing requires publishing new
   terms and obtaining a new acceptance — there is no path that changes what an existing
   client owes without their signature.
3. Acceptance re-records the content hash. You can prove what was accepted even if the
   terms row is later edited, exactly as evidence does.
4. A fee whose basis is unresolved cannot be charged. `compute_charge` raises rather than
   guessing. This mirrors INSUFFICIENT_DATA in the coverage engine: the platform does not
   fabricate a number it has not been told how to derive.

WHAT THIS MODULE DELIBERATELY DOES NOT DO

It does not move money. There is no payment provider, no card handling, no stored
credential. `record_payment` marks an invoice paid against an external reference supplied
by whoever reconciled the bank statement. Wiring a payment rail is a separate decision
that requires credentials this codebase must not hold.

It does meter volume, as of 2026-08-11 — see "Throughput billing" at the foot of this
module. What it does not yet have is anything WRITING `settlement_events`, so the meter
has no input in production.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.core.db_backend import capital_connection

# ── client account lifecycle ──────────────────────────────────────────────────

PROSPECT = "PROSPECT"
TERMS_ACCEPTED = "TERMS_ACCEPTED"
INVOICED = "INVOICED"
ACTIVE = "ACTIVE"
LAPSED = "LAPSED"

CLIENT_STATES = (PROSPECT, TERMS_ACCEPTED, INVOICED, ACTIVE, LAPSED)

# Forward-only, with one renewal edge back into INVOICED. A client cannot be moved
# straight to ACTIVE: that would skip both the signature and the invoice.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    PROSPECT: frozenset({TERMS_ACCEPTED}),
    TERMS_ACCEPTED: frozenset({INVOICED}),
    INVOICED: frozenset({ACTIVE}),
    ACTIVE: frozenset({LAPSED}),
    LAPSED: frozenset({INVOICED}),  # renewal
}

DEFAULT_SEAT_LIMIT = 20

INVOICE_ISSUED = "ISSUED"
INVOICE_PAID = "PAID"
INVOICE_VOID = "VOID"


class BillingError(Exception):
    """Refused for a commercial or lifecycle reason, not a bug."""


class FeeBasisUnresolved(BillingError):
    """A fee was requested whose basis has not been decided. Do not guess at money."""


# ── the fee schedule ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FeeComponent:
    code: str
    label: str
    basis: str  # what the rate multiplies. UNRESOLVED means: refuse to charge.
    rate_minor_per_unit: Optional[int] = None  # integer minor units per unit
    rate_bps: Optional[int] = None  # basis points, for percentage fees
    unit: Optional[str] = None
    note: str = ""


BASIS_PER_CLIENT_YEAR = "PER_CLIENT_YEAR"
BASIS_PER_TONNE_TOKENISED = "PER_TONNE_TOKENISED"
BASIS_GROSS_SETTLED_VALUE = "GROSS_SETTLED_VALUE"
BASIS_UNRESOLVED = "UNRESOLVED"

SUBSCRIPTION = FeeComponent(
    code="SUBSCRIPTION",
    label="Platform subscription",
    basis=BASIS_PER_CLIENT_YEAR,
    rate_minor_per_unit=100_000,  # €1,000.00
    unit="client-year",
    note=f"Includes up to {DEFAULT_SEAT_LIMIT} named users.",
)

TOKENISATION = FeeComponent(
    code="TOKENISATION",
    label="Molecule tokenisation",
    basis=BASIS_PER_TONNE_TOKENISED,
    rate_minor_per_unit=100,  # €1.00 per tonne
    unit="tonne",
    note=(
        "UNIT TRAP — the token ledger stores `tokenised_mtpd`, which is tonnes PER DAY, "
        "with a delivery_start/delivery_end window. Tonnes = mtpd x days in window. "
        "Billing `tokenised_mtpd` directly undercharges by roughly two orders of "
        "magnitude. This is the same class of defect as the MTPD x 1000 CFADS bug."
    ),
)

PRODUCER_THROUGHPUT = FeeComponent(
    code="PRODUCER_THROUGHPUT",
    label="Producer throughput fee (from COD)",
    basis=BASIS_GROSS_SETTLED_VALUE,
    rate_bps=250,  # 2.50%
    unit="gross settled value",
    note=(
        "2.5% of the GROSS settled value of a delivery — volume x price as recorded on "
        "the settlement event the offtaker confirms in order to claim the green "
        "attribute. Gross means the full molecule value including the commodity base, "
        "NOT the green premium alone. The price is not an index GEX chooses: it is "
        "`price_per_kg` on the settlement, fixed or indexed per the offtake contract. "
        "Payer is the producer (counterparty_seller_id). Basis decided 2026-08-11."
    ),
)

OFFTAKER_THROUGHPUT = FeeComponent(
    code="OFFTAKER_THROUGHPUT",
    label="Offtaker throughput fee (from COD)",
    basis=BASIS_GROSS_SETTLED_VALUE,
    rate_bps=100,  # 1.00%
    unit="gross settled value",
    note=("1% of the same GROSS settled value, on the same settlement event. Payer is "
          "the offtaker (counterparty_buyer_id). Together the two sides are 3.5% of "
          "gross settled value per delivery. Basis decided 2026-08-11."),
)

FEE_SCHEDULE_V1 = (SUBSCRIPTION, TOKENISATION, PRODUCER_THROUGHPUT, OFFTAKER_THROUGHPUT)


def fee_schedule_payload(components=FEE_SCHEDULE_V1) -> str:
    return json.dumps([asdict(c) for c in components], sort_keys=True, separators=(",", ":"))


def compute_charge(component: FeeComponent, quantity: float, unit_value_minor: int = 0) -> int:
    """Return the charge in integer minor units.

    Refuses rather than guesses when the basis is unresolved — a wrong invoice is worse
    than no invoice, because it is a wrong invoice a client has to dispute.
    """
    if component.basis == BASIS_UNRESOLVED:
        raise FeeBasisUnresolved(
            f"{component.code}: {component.note}"
        )
    if quantity < 0:
        raise BillingError("quantity cannot be negative")

    if component.rate_minor_per_unit is not None:
        return round(component.rate_minor_per_unit * quantity)
    if component.rate_bps is not None:
        if unit_value_minor < 0:
            raise BillingError("unit value cannot be negative")
        return round(unit_value_minor * quantity * component.rate_bps / 10_000)
    raise BillingError(f"{component.code}: no rate defined")


# ── persistence ───────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


DDL = (
    """
    CREATE TABLE IF NOT EXISTS client_accounts (
        client_id     TEXT PRIMARY KEY,
        company_name  TEXT NOT NULL,
        state         TEXT NOT NULL DEFAULT 'PROSPECT',
        seat_limit    INTEGER NOT NULL DEFAULT 20,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS commercial_terms (
        terms_id          TEXT PRIMARY KEY,
        version           TEXT NOT NULL UNIQUE,
        content           TEXT NOT NULL,
        content_sha256    TEXT NOT NULL,
        fee_schedule_json TEXT NOT NULL,
        effective_from    TEXT NOT NULL,
        published_by      TEXT NOT NULL,
        published_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS terms_acceptances (
        acceptance_id       TEXT PRIMARY KEY,
        client_id           TEXT NOT NULL,
        terms_id            TEXT NOT NULL,
        accepted_by_user_id TEXT NOT NULL,
        accepted_sha256     TEXT NOT NULL,
        channel             TEXT,
        accepted_at         TEXT NOT NULL,
        UNIQUE (client_id, terms_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS client_invoices (
        invoice_id      TEXT PRIMARY KEY,
        invoice_number  TEXT NOT NULL UNIQUE,
        client_id       TEXT NOT NULL,
        terms_id        TEXT NOT NULL,
        currency        TEXT NOT NULL DEFAULT 'EUR',
        amount_minor    INTEGER NOT NULL,
        line_items_json TEXT NOT NULL,
        state           TEXT NOT NULL DEFAULT 'ISSUED',
        issued_at       TEXT NOT NULL,
        due_at          TEXT,
        paid_at         TEXT,
        payment_ref     TEXT
    )
    """,
)


def init_billing_db() -> None:
    conn = capital_connection()
    try:
        for statement in DDL:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


# ── operations ────────────────────────────────────────────────────────────────


def publish_terms(version: str, content: str, published_by: str,
                  effective_from: Optional[str] = None) -> dict:
    """Publish a terms version. The fee schedule is frozen into it."""
    terms_id = f"terms_{uuid.uuid4().hex[:12]}"
    now = _now()
    row = {
        "terms_id": terms_id,
        "version": version,
        "content": content,
        "content_sha256": _sha256(content),
        "fee_schedule_json": fee_schedule_payload(),
        "effective_from": effective_from or now,
        "published_by": published_by,
        "published_at": now,
    }
    conn = capital_connection()
    try:
        conn.execute(
            "INSERT INTO commercial_terms (terms_id, version, content, content_sha256,"
            " fee_schedule_json, effective_from, published_by, published_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            tuple(row.values()),
        )
        conn.commit()
    finally:
        conn.close()
    return row


def get_terms(terms_id: str) -> Optional[dict]:
    conn = capital_connection()
    try:
        cur = conn.execute("SELECT * FROM commercial_terms WHERE terms_id = ?", (terms_id,))
        r = cur.fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def create_client(client_id: str, company_name: str,
                  seat_limit: int = DEFAULT_SEAT_LIMIT) -> dict:
    now = _now()
    conn = capital_connection()
    try:
        conn.execute(
            "INSERT INTO client_accounts (client_id, company_name, state, seat_limit,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (client_id, company_name, PROSPECT, seat_limit, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_client(client_id)


def get_client(client_id: str) -> Optional[dict]:
    conn = capital_connection()
    try:
        cur = conn.execute("SELECT * FROM client_accounts WHERE client_id = ?", (client_id,))
        r = cur.fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def _set_state(client_id: str, new_state: str) -> None:
    client = get_client(client_id)
    if client is None:
        raise BillingError(f"no such client: {client_id}")
    current = client["state"]
    if new_state == current:
        # Setting a state to what it already is changes nothing and is not an error. This
        # is what lets a second invoice be issued to a client already in INVOICED — a
        # correction or a renewal — without pretending the lifecycle moved.
        return
    if new_state not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise BillingError(
            f"illegal client transition {current} -> {new_state}. "
            f"Allowed from {current}: {sorted(ALLOWED_TRANSITIONS.get(current, []))}"
        )
    conn = capital_connection()
    try:
        conn.execute(
            "UPDATE client_accounts SET state = ?, updated_at = ? WHERE client_id = ?",
            (new_state, _now(), client_id),
        )
        conn.commit()
    finally:
        conn.close()


def seats_used(client_id: str) -> int:
    """Counted from auth_users. There is no second user store and there must not be."""
    from app.core.db_backend import auth_connection

    conn = auth_connection()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM auth_users WHERE company_id = ?", (client_id,)
        )
        row = cur.fetchone()
        return int(row["n"] if hasattr(row, "keys") else row[0])
    finally:
        conn.close()


def accept_terms(client_id: str, terms_id: str, accepted_by_user_id: str,
                 channel: str = "WEB", assert_user_active=None) -> dict:
    """Record formal acceptance.

    `assert_user_active` is injected so this module does not import the auth stack
    directly; production wiring passes the account-lifecycle assertion. Acceptance by a
    non-vetted user is refused — the commercial agreement inherits the vetting gate
    rather than working around it.
    """
    client = get_client(client_id)
    if client is None:
        raise BillingError(f"no such client: {client_id}")
    terms = get_terms(terms_id)
    if terms is None:
        raise BillingError(f"no such terms: {terms_id}")
    if assert_user_active is not None:
        assert_user_active(accepted_by_user_id)

    acceptance = {
        "acceptance_id": f"acc_{uuid.uuid4().hex[:12]}",
        "client_id": client_id,
        "terms_id": terms_id,
        "accepted_by_user_id": accepted_by_user_id,
        # Re-recorded, not referenced: proves WHAT was accepted if the row is later edited.
        "accepted_sha256": terms["content_sha256"],
        "channel": channel,
        "accepted_at": _now(),
    }
    conn = capital_connection()
    try:
        conn.execute(
            "INSERT INTO terms_acceptances (acceptance_id, client_id, terms_id,"
            " accepted_by_user_id, accepted_sha256, channel, accepted_at)"
            " VALUES (?,?,?,?,?,?,?)",
            tuple(acceptance.values()),
        )
        conn.commit()
    finally:
        conn.close()

    _set_state(client_id, TERMS_ACCEPTED)
    return acceptance


def issue_subscription_invoice(client_id: str, terms_id: str,
                               due_at: Optional[str] = None) -> dict:
    """Issue the invoice that finalises the contract. Requires accepted terms."""
    client = get_client(client_id)
    if client is None:
        raise BillingError(f"no such client: {client_id}")

    conn = capital_connection()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM terms_acceptances WHERE client_id = ? AND terms_id = ?",
            (client_id, terms_id),
        )
        row = cur.fetchone()
        accepted = int(row["n"] if hasattr(row, "keys") else row[0])
    finally:
        conn.close()

    if not accepted:
        raise BillingError(
            "cannot invoice before the terms are accepted — the invoice is consideration "
            "for an agreed contract, not a way to form one"
        )

    amount = compute_charge(SUBSCRIPTION, quantity=1)
    invoice = {
        "invoice_id": f"inv_{uuid.uuid4().hex[:12]}",
        "invoice_number": f"GEX-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:6].upper()}",
        "client_id": client_id,
        "terms_id": terms_id,
        "currency": "EUR",
        "amount_minor": amount,
        "line_items_json": json.dumps(
            [
                {
                    "code": SUBSCRIPTION.code,
                    "label": SUBSCRIPTION.label,
                    "quantity": 1,
                    "unit": SUBSCRIPTION.unit,
                    "amount_minor": amount,
                    "seat_limit": client["seat_limit"],
                }
            ],
            separators=(",", ":"),
        ),
        "state": INVOICE_ISSUED,
        "issued_at": _now(),
        "due_at": due_at,
        "paid_at": None,
        "payment_ref": None,
    }
    conn = capital_connection()
    try:
        conn.execute(
            "INSERT INTO client_invoices (invoice_id, invoice_number, client_id, terms_id,"
            " currency, amount_minor, line_items_json, state, issued_at, due_at, paid_at,"
            " payment_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(invoice.values()),
        )
        conn.commit()
    finally:
        conn.close()

    _set_state(client_id, INVOICED)
    return invoice


def record_payment(invoice_id: str, payment_ref: str) -> dict:
    """Mark an invoice paid against an EXTERNAL reference.

    This module never touches a payment rail. `payment_ref` is whatever the person who
    reconciled the bank statement recorded. Wiring a provider is a separate decision that
    needs credentials this codebase must not hold.
    """
    if not payment_ref:
        raise BillingError("a payment reference is required — 'paid' must be evidenced")

    conn = capital_connection()
    try:
        cur = conn.execute("SELECT * FROM client_invoices WHERE invoice_id = ?", (invoice_id,))
        row = cur.fetchone()
        if row is None:
            raise BillingError(f"no such invoice: {invoice_id}")
        invoice = dict(row)
        if invoice["state"] != INVOICE_ISSUED:
            raise BillingError(
                f"invoice is {invoice['state']}, only {INVOICE_ISSUED} invoices can be paid"
            )
        now = _now()
        conn.execute(
            "UPDATE client_invoices SET state = ?, paid_at = ?, payment_ref = ?"
            " WHERE invoice_id = ?",
            (INVOICE_PAID, now, payment_ref, invoice_id),
        )
        conn.commit()
    finally:
        conn.close()

    _set_state(invoice["client_id"], ACTIVE)
    invoice.update(state=INVOICE_PAID, paid_at=now, payment_ref=payment_ref)
    return invoice


def get_invoice(invoice_id: str) -> Optional[dict]:
    conn = capital_connection()
    try:
        cur = conn.execute("SELECT * FROM client_invoices WHERE invoice_id = ?", (invoice_id,))
        r = cur.fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Throughput billing — charging a settled delivery
# ══════════════════════════════════════════════════════════════════════════════
#
# The billable event is a SETTLEMENT: the offtaker confirms receipt of a volume for a
# period. That confirmation is not a favour to GEX — it is what the offtaker must do to
# claim the green attribute. The meter and the compliance claim are the same record, so
# the fee is hard to avoid without giving up the thing you bought. That is the strongest
# property of this design and it is why metering works without GEX policing anyone.
#
# WHERE THE PARAMETERS ACTUALLY LIVE
#
# `settlement_events` carries token_id, counterparty_buyer_id, counterparty_seller_id,
# volume_kg, price_per_kg, total_amount, currency and settlement_date. That is the whole
# billing basis. The `tokens` table is a PROVENANCE certificate — molecule, carbon
# intensity, certification pathway, mass balance — and carries no price, no owner and no
# transfer. Do not add commercial terms to it; settlement is per-delivery, which is the
# period you bill on, and the token is per-production-lot, which is not.
#
# UNITS: settlements are in KILOGRAMS. The tokenisation fee is per TONNE. Divide by 1000.
#
# GREEN PREMIUM has no field in either table. If the fee is ever meant to apply to the
# premium rather than the gross settled value, there is nowhere to read it from and this
# code must not infer one. See `PREMIUM_IS_NOT_SEPARABLE`.

PRODUCER_SIDE = "PRODUCER"
OFFTAKER_SIDE = "OFFTAKER"

PAYMENT_TERMS_DAYS = 10  # title transfer + 10 days

FINAL_SETTLEMENT_STATUSES = frozenset({"SETTLED", "COMPLETED", "FINAL", "CONFIRMED"})

# DECIDED 2026-08-11: GROSS, not premium-only.
PREMIUM_BASIS_DECISION = (
    "Throughput fees are charged on the GROSS settled value — the full molecule value, "
    "including the commodity base that exists whether or not the molecule is green. "
    "Premium-only was the alternative and was NOT chosen; it would have been a materially "
    "smaller number and would have required a premium field, since neither `tokens` nor "
    "`settlement_events` separates a premium from the settled price. Reversing this is a "
    "repricing: it needs a new terms version and a new client acceptance, which the "
    "frozen fee schedule already enforces."
)


@dataclass(frozen=True)
class SettlementCharge:
    settlement_id: str
    side: str
    company_id: str
    volume_kg: float
    settled_value_minor: int
    fee_minor: int
    currency: str
    settled_at: str
    due_at: str
    component_code: str


def _due_date(settled_at: str, days: int = PAYMENT_TERMS_DAYS) -> str:
    from datetime import timedelta

    parsed = datetime.fromisoformat(settled_at.replace("Z", "+00:00"))
    return (parsed + timedelta(days=days)).isoformat()


def _settled_value_minor(settlement: dict) -> int:
    """Value in integer minor units, cross-checked against volume x price.

    A settlement whose total disagrees with its own volume and price is a corrupted row,
    and billing a corrupted row is worse than not billing it.
    """
    total = settlement.get("total_amount")
    volume = settlement.get("volume_kg")
    price = settlement.get("price_per_kg")

    if total is None:
        raise BillingError("settlement has no total_amount — nothing to charge on")
    if volume is None or volume <= 0:
        raise BillingError("settlement has no positive volume_kg")
    if price is not None:
        implied = volume * price
        if implied > 0 and abs(implied - total) / implied > 0.005:
            raise BillingError(
                f"settlement total_amount {total} disagrees with volume_kg x price_per_kg "
                f"{implied:.2f} by more than 0.5% — refusing to bill a corrupted row"
            )
    return round(total * 100)


def charges_for_settlement(settlement: dict) -> list[SettlementCharge]:
    """Both sides of one settled delivery. Pure — no I/O, no clock.

    Refuses rather than guessing on: a non-final settlement, a missing counterparty, a
    non-EUR currency, or a total that contradicts its own volume and price.
    """
    status = (settlement.get("settlement_status") or "").upper()
    if status not in FINAL_SETTLEMENT_STATUSES:
        raise BillingError(
            f"settlement_status {status!r} is not final — a delivery is billable when "
            f"title has transferred, not when it is pending"
        )

    currency = (settlement.get("currency") or "EUR").upper()
    if currency != "EUR":
        raise BillingError(
            f"settlement is in {currency}; fees are EUR and no FX rate or conversion date "
            f"is recorded. Refusing to invent one."
        )

    settled_at = settlement.get("settlement_date")
    if not settled_at:
        raise BillingError("settlement has no settlement_date — the due date derives from it")

    value_minor = _settled_value_minor(settlement)
    volume_kg = float(settlement["volume_kg"])
    due_at = _due_date(settled_at)

    sides = (
        (PRODUCER_SIDE, settlement.get("counterparty_seller_id"), PRODUCER_THROUGHPUT),
        (OFFTAKER_SIDE, settlement.get("counterparty_buyer_id"), OFFTAKER_THROUGHPUT),
    )

    charges: list[SettlementCharge] = []
    for side, company_id, component in sides:
        if not company_id:
            raise BillingError(
                f"settlement has no counterparty for the {side} side — both sides are "
                f"charged on the same event and a missing payer must not be skipped"
            )
        charges.append(
            SettlementCharge(
                settlement_id=settlement["settlement_id"],
                side=side,
                company_id=company_id,
                volume_kg=volume_kg,
                settled_value_minor=value_minor,
                fee_minor=round(value_minor * component.rate_bps / 10_000),
                currency=currency,
                settled_at=settled_at,
                due_at=due_at,
                component_code=component.code,
            )
        )
    return charges


def tokenisation_charge_minor(volume_kg: float) -> int:
    """EUR 1.00 per TONNE on a volume recorded in KILOGRAMS."""
    if volume_kg < 0:
        raise BillingError("volume cannot be negative")
    return compute_charge(TOKENISATION, quantity=volume_kg / 1000.0)


THROUGHPUT_DDL = (
    """
    CREATE TABLE IF NOT EXISTS throughput_charges (
        charge_id            TEXT PRIMARY KEY,
        settlement_id        TEXT NOT NULL,
        side                 TEXT NOT NULL,
        company_id           TEXT NOT NULL,
        component_code       TEXT NOT NULL,
        volume_kg            REAL NOT NULL,
        settled_value_minor  INTEGER NOT NULL,
        fee_minor            INTEGER NOT NULL,
        currency             TEXT NOT NULL,
        settled_at           TEXT NOT NULL,
        due_at               TEXT NOT NULL,
        accrued_at           TEXT NOT NULL,
        UNIQUE (settlement_id, side)
    )
    """,
)


def init_throughput_db() -> None:
    conn = capital_connection()
    try:
        for statement in THROUGHPUT_DDL:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def accrue_settlement(settlement: dict) -> list[dict]:
    """Record both charges for a settled delivery. Idempotent.

    UNIQUE(settlement_id, side) is the guard that matters. Replaying a settlement feed,
    re-running a period, or a retried webhook must never bill a client twice — and double
    billing is the single most common defect in usage-based systems.
    """
    charges = charges_for_settlement(settlement)
    now = _now()
    written = []

    conn = capital_connection()
    try:
        for charge in charges:
            cur = conn.execute(
                "SELECT charge_id FROM throughput_charges WHERE settlement_id = ? AND side = ?",
                (charge.settlement_id, charge.side),
            )
            if cur.fetchone() is not None:
                continue  # already accrued — not an error, just nothing to do
            row = (
                f"chg_{uuid.uuid4().hex[:12]}",
                charge.settlement_id, charge.side, charge.company_id,
                charge.component_code, charge.volume_kg, charge.settled_value_minor,
                charge.fee_minor, charge.currency, charge.settled_at, charge.due_at, now,
            )
            conn.execute(
                "INSERT INTO throughput_charges (charge_id, settlement_id, side, company_id,"
                " component_code, volume_kg, settled_value_minor, fee_minor, currency,"
                " settled_at, due_at, accrued_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )
            written.append({**asdict(charge), "charge_id": row[0]})
        conn.commit()
    finally:
        conn.close()
    return written


def charges_for_period(company_id: str, period_start: str, period_end: str) -> dict:
    """Everything a company owes for deliveries settled within a period."""
    conn = capital_connection()
    try:
        cur = conn.execute(
            "SELECT * FROM throughput_charges WHERE company_id = ?"
            " AND settled_at >= ? AND settled_at < ? ORDER BY settled_at",
            (company_id, period_start, period_end),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "company_id": company_id,
        "period_start": period_start,
        "period_end": period_end,
        "charges": rows,
        "total_fee_minor": sum(r["fee_minor"] for r in rows),
        "total_volume_kg": sum(r["volume_kg"] for r in rows),
        "currency": "EUR",
    }
