"""
The permissioned upstream hydrogen proof (gap G-23; alembic 110).

A company that HOLDS a hydrogen token — delivered to it by title transfer (109) — may cite it
as the source of a downstream custody input. The proof that its hydrogen is RFNBO lives in the
SELLER's custody records, which the holder may not read. So the proof is computed here, on the
operator connection, only after checking that the asking company holds the token, and only
these fields leave:

    token -> its root token (through splits) -> the custody lot -> the lot's accounting period
    the period CLOSED, its statement RE-VERIFIED from its rows (custody_ledger.verify_period),
    the statement's hash, its RFNBO correlation status and the rules it used, the token's kg.

The holder cannot ask about a token it does not hold (None), cannot read the seller's lot or
period rows, and cannot enumerate other lots. Anything missing or unreadable is UNVERIFIED,
never assumed: no caller-supplied PASS is ever read.

The operator connection (PLATFORM_ADMIN) is a bootstrap here in the sense of CLAUDE.md:
the holder check is the access decision, and every use is logged by `_tenant_context`.
"""
from __future__ import annotations

from typing import Optional


def proof(token_id: str, company_id: Optional[str]) -> Optional[dict]:
    """The proof for `company_id`'s token, or None when that company does not hold it."""
    from app.core.custody_ledger import verify_period
    from app.core.db_backend import PLATFORM_ADMIN, domain_connection
    from app.core.delivery_title import root_of, token_kg

    if not company_id or company_id == PLATFORM_ADMIN:
        return None
    conn = domain_connection(company_id=PLATFORM_ADMIN)      # authorised below by the holder check
    try:
        t = conn.execute("SELECT id, holder_company_id, lifecycle_state, molecule FROM tokens WHERE id = ?",
                         (token_id,)).fetchone()
        if t is None or t["holder_company_id"] != company_id:
            return None
        root = root_of(conn, token_id)
        out = {"token_id": token_id, "root_token_id": root, "token_state": t["lifecycle_state"],
               "molecule": t["molecule"], "token_kg": float(token_kg(conn, token_id))}
        r = conn.execute("SELECT mass_balance_lot_id FROM tokens WHERE id = ?", (root,)).fetchone()
        lot = conn.execute("SELECT lot_id, molecule, period_id FROM mass_balance_lots WHERE lot_id = ?",
                           (r["mass_balance_lot_id"],)).fetchone() if r and r["mass_balance_lot_id"] else None
        if lot is None:
            return {**out, "status": "UNVERIFIED", "reason": "the token is backed by no custody lot"}
        out["lot_id"] = lot["lot_id"]
        if lot["molecule"] != "H2" or not lot["period_id"]:
            return {**out, "status": "UNVERIFIED",
                    "reason": "the token's lot is not a hydrogen lot of an accounting period"}
        p = conn.execute("SELECT period_id, status, statement, statement_hash FROM coc_period WHERE period_id = ?",
                         (lot["period_id"],)).fetchone()
        out.update(period_id=p["period_id"], period_status=p["status"])
        if p["status"] != "CLOSED":
            return {**out, "status": "UNVERIFIED", "reason": "the upstream hydrogen period is still open"}
        v = verify_period(conn, p["period_id"])
        out.update(statement_hash=p["statement_hash"], verified=bool(v["valid"]))
        if not v["valid"]:
            return {**out, "status": "UNVERIFIED", "reason": "the upstream period's statement does not re-verify"}
        c = (p["statement"] or {}).get("rfnbo_correlation") or {}
        status = c.get("status") if c.get("status") in ("PASS", "FAIL") else "UNVERIFIED"
        return {**out, "status": status, "rfnbo_status": c.get("status"), "rules_used": c.get("rules_used"),
                "reason": f"upstream hydrogen period correlation: {c.get('status', 'not computed')}"}
    finally:
        conn.close()
