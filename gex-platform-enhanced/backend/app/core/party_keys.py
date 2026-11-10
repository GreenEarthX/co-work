"""
A company's signing keys (Phase 5 of "One contract record"; alembic 096).
=======================================================================
A party signs its own confirmations and disputes with a key it registered here, so a
confirmation does not rest on a session token GEX signs itself. The rule:

  propose   an EXECUTIVE of the company, ACTIVE account, never a GEX account;
            an ed25519 public key (32 bytes, base64). The key reference is
            "ed25519:" + the first 16 hex of sha256(public key).
  activate  a SECOND executive of the same company (four eyes; the database
            refuses approver = proposer too).
  reject    the same, for a proposed key that should not stand.
  revoke    any executive of the company, with a reason; a revoked key signs no
            new event. Signatures it already made stay on the record, and the
            readout shows the key's state beside them.

Every step goes to the platform event ledger (`party_key.*`). GEX stores public keys
only; the private key never reaches the platform. No wallet integration and no
eIDAS seal validation in this phase: the scheme column is ready for them.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SCHEME = "ed25519"


class KeyRefused(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def key_ref_for(public_key_b64: str) -> str:
    return f"{SCHEME}:{hashlib.sha256(base64.b64decode(public_key_b64)).hexdigest()[:16]}"


def _conn(company_id: str):
    from app.core.db_backend import market_connection, market_is_postgres

    if not market_is_postgres():
        raise KeyRefused(503, "POSTGRES_REQUIRED", "Signing keys live in PostgreSQL only.")
    return market_connection(company_id=company_id)


def _executive(conn, payload: dict) -> dict:
    """The caller's account, required ACTIVE, EXECUTIVE and not GEX's."""
    if payload.get("is_platform_admin"):
        raise KeyRefused(403, "GEX_DOES_NOT_SIGN", "GEX confirms no party's terms, so it holds no party's key.")
    uid = payload.get("user_id") or payload.get("sub")
    row = conn.execute("SELECT user_id, company_id, account_state, business_function FROM auth_users "
                       "WHERE user_id = ?", (uid,)).fetchone()
    if row is None or row["account_state"] != "ACTIVE":
        raise KeyRefused(403, "ACCOUNT_NOT_ACTIVE", "Only an active account manages signing keys.")
    if (row["business_function"] or "").upper() != "EXECUTIVE":
        raise KeyRefused(403, "EXECUTIVE_ONLY", "Only an executive of the company manages its signing keys.")
    if not row["company_id"]:
        raise KeyRefused(403, "NO_COMPANY", "Your account belongs to no company.")
    return dict(row)


def _ledger(event_type: str, key: dict, actor: str, extra: Optional[dict] = None) -> None:
    """Written BEFORE the key change commits: a change the ledger cannot record is undone."""
    from app.core.event_store import append_event

    try:
        _append(append_event, event_type, key, actor, extra)
    except Exception as exc:  # noqa: BLE001
        logger.exception("party key %s: ledger event not written; change undone", key.get("key_ref"))
        raise KeyRefused(503, "AUDIT_UNAVAILABLE", "The change could not be recorded in the ledger, so it "
                                                   "was not made.") from exc


def _append(append_event, event_type, key, actor, extra):
    append_event(event_type=event_type, aggregate_type="party_signing_key", aggregate_id=key["key_ref"],
                 data={"key_ref": key["key_ref"], "scheme": key["scheme"], "company_id": key["company_id"],
                       **(extra or {})},
                 user_id=actor, company_id=key["company_id"])


def _view(r: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items() if k != "id"}


def list_keys(payload: dict) -> list[dict]:
    company = payload.get("company_id")
    if not company:
        return []
    conn = _conn(company)
    try:
        return [_view(r) for r in conn.execute("SELECT * FROM party_signing_key ORDER BY proposed_at").fetchall()]
    finally:
        conn.close()


def propose(payload: dict, public_key_b64: str, label: Optional[str] = None) -> dict:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        raw = base64.b64decode(public_key_b64, validate=True)
        Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError):
        raise KeyRefused(422, "NOT_AN_ED25519_KEY", "The public key must be 32 bytes of ed25519, base64.") from None
    conn = _conn(payload.get("company_id") or "")
    try:
        me = _executive(conn, payload)
        if me["company_id"] != payload.get("company_id"):
            raise KeyRefused(403, "OWN_COMPANY_ONLY", "A key is registered for your own company only.")
        ref = key_ref_for(public_key_b64)
        if conn.execute("SELECT 1 FROM app_party_signing_key(?)", (ref,)).fetchone():
            raise KeyRefused(409, "KEY_ALREADY_REGISTERED", "That public key is already registered.")
        conn.execute("INSERT INTO party_signing_key (company_id, key_ref, scheme, public_key, label, proposed_by) "
                     "VALUES (?, ?, ?, ?, ?, ?)", (me["company_id"], ref, SCHEME, public_key_b64, label, me["user_id"]))
        key = dict(conn.execute("SELECT * FROM party_signing_key WHERE key_ref = ?", (ref,)).fetchone())
        _ledger("party_key.proposed", key, me["user_id"])
        conn.commit()
    finally:
        conn.close()
    return _view(key)


def _decide(payload: dict, key_ref: str, to: str, reason: Optional[str] = None) -> dict:
    conn = _conn(payload.get("company_id") or "")
    try:
        me = _executive(conn, payload)
        row = conn.execute("SELECT * FROM party_signing_key WHERE key_ref = ? FOR UPDATE", (key_ref,)).fetchone()
        if row is None:
            raise KeyRefused(404, "KEY_NOT_FOUND", "No signing key of your company with that reference.")
        key = dict(row)
        now = datetime.now(timezone.utc)
        if to in ("ACTIVE", "REJECTED"):
            if key["status"] != "PROPOSED":
                raise KeyRefused(409, "KEY_NOT_PROPOSED", f"The key is {key['status']}.")
            if key["proposed_by"] == me["user_id"]:
                raise KeyRefused(403, "FOUR_EYES", "A second executive activates the key, not the one who proposed it.")
            conn.execute("UPDATE party_signing_key SET status = ?, approved_by = ?, approved_at = ? WHERE key_ref = ?",
                         (to, me["user_id"], now, key_ref))
        else:
            if key["status"] != "ACTIVE":
                raise KeyRefused(409, "KEY_NOT_ACTIVE", f"The key is {key['status']}.")
            if not (reason or "").strip():
                raise KeyRefused(422, "REASON_REQUIRED", "Say why the key is revoked.")
            conn.execute("UPDATE party_signing_key SET status = 'REVOKED', revoked_by = ?, revoked_at = ?, "
                         "revoke_reason = ? WHERE key_ref = ?", (me["user_id"], now, reason, key_ref))
        key = dict(conn.execute("SELECT * FROM party_signing_key WHERE key_ref = ?", (key_ref,)).fetchone())
        _ledger({"ACTIVE": "party_key.activated", "REJECTED": "party_key.rejected",
                 "REVOKED": "party_key.revoked"}[to], key, me["user_id"], {"reason": reason} if reason else None)
        conn.commit()
    finally:
        conn.close()
    return _view(key)


def activate(payload: dict, key_ref: str) -> dict:
    return _decide(payload, key_ref, "ACTIVE")


def reject(payload: dict, key_ref: str) -> dict:
    return _decide(payload, key_ref, "REJECTED")


def revoke(payload: dict, key_ref: str, reason: str) -> dict:
    return _decide(payload, key_ref, "REVOKED", reason)
