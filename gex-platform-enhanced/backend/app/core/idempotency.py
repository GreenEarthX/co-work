"""
Idempotent create requests (discovery review F12, alembic 114).

A client that retries a create — a timeout, a double click, a lost response — used to create
a second RFQ, listing, token or settlement. With an `Idempotency-Key` header the first request
reserves the key for the caller's company, runs, and stores its response; a repeat with the same
key and the same request returns that stored response (header `Idempotent-Replayed: true`) and
creates nothing. The same key with a DIFFERENT request is refused (422); a repeat that arrives
while the first is still running is refused (409) rather than run twice.

Without the header nothing changes (compatibility). A refused or failed request releases its
key, so the client may correct and retry. The key is scoped to the company (RLS on
`idempotency_record`), not global.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

logger = logging.getLogger("gex.idempotency")
HEADER = "Idempotency-Key"
KEY_FORMAT = re.compile(r"^[A-Za-z0-9_.:\-]{8,128}$")


def _conn(company_id: str):
    from app.core.db_backend import market_connection
    return market_connection(company_id=company_id)


def run(request: Request, body: Any, handler: Callable[[], Any], *, status_code: int = 200) -> Any:
    key = request.headers.get(HEADER)
    if not key:
        return handler()
    if not KEY_FORMAT.match(key):
        raise HTTPException(422, {"code": "IDEMPOTENCY_KEY_FORMAT",
                                  "message": f"{HEADER} must be 8-128 letters, digits or . _ : -"})
    payload = getattr(request.state, "user_payload", None) or {}
    company, user = payload.get("company_id"), payload.get("user_id") or payload.get("sub")
    if not company or not user:
        return handler()                                   # the handler refuses an anonymous caller
    path = f"{request.method} {request.url.path}"
    digest = hashlib.sha256(json.dumps({"path": path, "body": jsonable_encoder(body)},
                                       sort_keys=True, default=str).encode()).hexdigest()
    conn = _conn(company)
    try:
        row = conn.execute(
            "INSERT INTO idempotency_record (company_id, user_id, idem_key, method_path, request_sha256, status) "
            "VALUES (?, ?, ?, ?, ?, 'in_progress') ON CONFLICT (company_id, idem_key) DO NOTHING RETURNING id",
            (company, str(user), key, path, digest)).fetchone()
        conn.commit()
        if row is None:
            prior = conn.execute("SELECT method_path, request_sha256, status, status_code, response FROM "
                                 "idempotency_record WHERE company_id = ? AND idem_key = ?", (company, key)).fetchone()
            if prior is None or prior["method_path"] != path or prior["request_sha256"] != digest:
                raise HTTPException(422, {"code": "IDEMPOTENCY_KEY_REUSED",
                                          "message": "This Idempotency-Key was already used for a different request."})
            if prior["status"] == "done":
                return JSONResponse(prior["response"], status_code=prior["status_code"],
                                    headers={"Idempotent-Replayed": "true"})
            raise HTTPException(409, {"code": "IDEMPOTENCY_IN_PROGRESS",
                                      "message": "The same request is still being processed. Check before retrying."})
        record_id = row["id"]
    finally:
        conn.close()

    try:
        result = handler()
    except BaseException:
        _release(company, record_id)
        raise
    try:
        conn = _conn(company)
        try:
            conn.execute("UPDATE idempotency_record SET status = 'done', status_code = ?, response = ?::jsonb, "
                         "completed_at = now() WHERE id = ?",
                         (status_code, json.dumps(jsonable_encoder(result), default=str), record_id))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — the create succeeded; a retry will see IN_PROGRESS, never a duplicate
        logger.exception("idempotency: the response of record %s could not be stored", record_id)
    return result


def _release(company: str, record_id: int) -> None:
    try:
        conn = _conn(company)
        try:
            conn.execute("DELETE FROM idempotency_record WHERE id = ? AND status = 'in_progress'", (record_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.exception("idempotency: reservation %s could not be released", record_id)
