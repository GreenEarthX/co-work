"""
Project premises — the financing model and the power model — change only on a
document and a second party (JML, 2026-10-28; alembic 077).

A premise decides which evidence applies. Balance-sheet funding drops the
lender-protection items and waives G6 and G8; a power model drops the PPA items
or the behind-the-meter ones. So a change that REMOVES items is a decision about
the bar itself, and the party that benefits must not take it alone:

  propose   the owner's executive (or GEX staff), WITH a supporting document.
            Nothing changes yet — the change is PENDING.
  confirm   a second party: an active account of another company party to the
            project (the funder, the counterparty …) or GEX staff. Only then is
            the premise applied and the project re-evaluated.
  contest   any project party, the producer or the offtaker included, may
            register a document against it. A CONTESTED change keeps the lender
            protections in place; only GEX staff may then confirm or reject it.
  withdraw  the proposer's company, while it is open.

Changes that remove nothing — back to project finance — apply at once, as before.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

FIELDS = ("financing_model", "power_model")


class PremiseRefusal(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def removes_items(field: str, old: Optional[str], new: str) -> bool:
    """Does this change take evidence out of the bar?"""
    if field == "financing_model":
        return new == "BALANCE_SHEET" and old != "BALANCE_SHEET"
    if field == "power_model":
        return new != old            # every power model drops some other model's items
    return False


@dataclass
class Party:
    user_id: str
    company_id: Optional[str]
    is_gex: bool
    is_owner_executive: bool
    is_project_party: bool


def party_for(payload: dict, owner_company_id: str, project_companies: set[str]) -> Party:
    company = payload.get("company_id")
    return Party(
        user_id=payload.get("user_id") or "",
        company_id=company,
        is_gex=bool(payload.get("is_platform_admin")),
        is_owner_executive=(company == owner_company_id and payload.get("business_function") == "EXECUTIVE"),
        is_project_party=company in project_companies,
    )


def check_propose(party: Party) -> None:
    if not (party.is_owner_executive or party.is_gex):
        raise PremiseRefusal(403, "OWNER_EXECUTIVE_OR_GEX", "Only the owner's executive or GEX staff propose a premise.")


def check_confirm(party: Party, change: dict) -> None:
    if change["status"] not in ("PENDING", "CONTESTED"):
        raise PremiseRefusal(409, "NOT_OPEN", f"This change is {change['status']}.")
    if change["status"] == "CONTESTED" and not party.is_gex:
        raise PremiseRefusal(403, "CONTESTED_GEX_DECIDES",
                             "A contested premise is decided by GEX staff; the lender protections stay until then.")
    if not party.is_gex:
        if not party.is_project_party:
            raise PremiseRefusal(403, "NOT_A_PROJECT_PARTY", "Only a party to the project, or GEX staff, confirm.")
        if party.company_id == change["proposed_company"] or party.user_id == change["proposed_by"]:
            raise PremiseRefusal(403, "SECOND_PARTY_REQUIRED",
                                 "A premise is confirmed by a second party — not the company that proposed it.")


def check_contest(party: Party, change: dict) -> None:
    if change["status"] not in ("PENDING", "CONTESTED", "CONFIRMED"):
        raise PremiseRefusal(409, "NOT_CONTESTABLE", f"This change is {change['status']}.")
    if not (party.is_project_party or party.is_gex):
        raise PremiseRefusal(403, "NOT_A_PROJECT_PARTY", "Only a party to the project contests a premise.")


def check_withdraw(party: Party, change: dict) -> None:
    if change["status"] not in ("PENDING", "CONTESTED"):
        raise PremiseRefusal(409, "NOT_OPEN", f"This change is {change['status']}.")
    if not (party.is_gex or party.company_id == change["proposed_company"]):
        raise PremiseRefusal(403, "PROPOSER_ONLY", "Only the proposing company withdraws its change.")


# ── Store (alembic 077), read and written in the caller's tenant ─────────────

PROTECTIVE = {"financing_model": "PROJECT_FINANCE", "power_model": None}


def _conn():
    from app.core.db_backend import domain_connection
    return domain_connection()


def _all(sql: str, params: tuple) -> list[dict]:
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def changes(project_id: str) -> list[dict]:
    rows = _all("SELECT * FROM project_premise_change WHERE project_id = ? ORDER BY id DESC", (project_id,))
    docs = _all("SELECT id, change_id, role, sha256, filename, size_bytes, uploaded_by, company_id, note, "
                "uploaded_at FROM project_premise_document WHERE project_id = ? ORDER BY id", (project_id,))
    for r in rows:
        for k in ("proposed_at", "decided_at"):
            r[k] = str(r[k]) if r.get(k) else None
        r["documents"] = [{**d, "uploaded_at": str(d["uploaded_at"])} for d in docs if d["change_id"] == r["id"]]
        r["undocumented"] = not any(d["role"] == "SUPPORT" for d in r["documents"])
    return rows


def get_change(project_id: str, change_id: int) -> dict:
    rows = _all("SELECT * FROM project_premise_change WHERE project_id = ? AND id = ?", (project_id, change_id))
    if not rows:
        raise PremiseRefusal(404, "NOT_FOUND", "No such premise change on this project.")
    return rows[0]


def protective_overrides(project_id: str) -> dict:
    """Premises the engine must NOT use: a field whose latest applied change is
    contested or rejected falls back to its protective value."""
    out = {}
    for field in FIELDS:
        rows = _all("SELECT status, applied FROM project_premise_change WHERE project_id = ? AND field = ? "
                    "AND applied ORDER BY id DESC LIMIT 1", (project_id, field))
        if rows and rows[0]["status"] in ("CONTESTED", "REJECTED"):
            out[field] = PROTECTIVE[field]
    return out


def open_change(project_id: str, field: str, from_value: Optional[str], to_value: str, party: "Party") -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO project_premise_change (project_id, field, from_value, to_value, status, proposed_by, "
            "proposed_company) VALUES (?, ?, ?, ?, 'PENDING', ?, ?) RETURNING id",
            (project_id, field, from_value, to_value, party.user_id, party.company_id))
        change_id = cur.fetchone()["id"]
        conn.commit()
        return change_id
    except Exception as exc:  # the one-open-change index
        conn.rollback()
        if "ux_premise_one_open" in str(exc):
            raise PremiseRefusal(409, "ALREADY_OPEN", f"A change of {field} is already open on this project.")
        raise
    finally:
        conn.close()


def add_document(project_id: str, change_id: int, role: str, content: bytes, filename: str,
                 party: "Party", note: Optional[str]) -> dict:
    import hashlib
    import os
    from pathlib import Path

    if not content:
        raise PremiseRefusal(422, "EMPTY_FILE", "The document is empty.")
    if len(content) > 25 * 1024 * 1024:
        raise PremiseRefusal(413, "TOO_LARGE", "Document exceeds 25 MB.")
    sha = hashlib.sha256(content).hexdigest()
    base = Path(os.getenv("GEX_EVIDENCE_DOCS_DIR", "data/evidence_docs")) / project_id / "_premises"
    base.mkdir(parents=True, exist_ok=True)
    name = os.path.basename(filename or "document.bin")
    dest = base / f"{sha[:12]}_{name}"
    dest.write_bytes(content)
    conn = _conn()
    try:
        conn.execute("INSERT INTO project_premise_document (change_id, project_id, role, sha256, filename, "
                     "stored_path, size_bytes, uploaded_by, company_id, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (change_id, project_id, role, sha, name, str(dest), len(content), party.user_id,
                      party.company_id, note))
        conn.commit()
    finally:
        conn.close()
    return {"sha256": sha, "filename": name, "size_bytes": len(content)}


def set_status(project_id: str, change_id: int, status: str, party: "Party", note: Optional[str] = None,
               applied: Optional[bool] = None) -> None:
    decided = status in ("CONFIRMED", "REJECTED", "WITHDRAWN")
    conn = _conn()
    try:
        conn.execute(
            "UPDATE project_premise_change SET status = ?, decision_note = COALESCE(?, decision_note), "
            "decided_by = CASE WHEN ? THEN ? ELSE decided_by END, "
            "decided_company = CASE WHEN ? THEN ? ELSE decided_company END, "
            "decided_at = CASE WHEN ? THEN now() ELSE decided_at END, "
            "applied = COALESCE(?, applied) WHERE project_id = ? AND id = ?",
            (status, note, decided, party.user_id, decided, party.company_id, decided, applied,
             project_id, change_id))
        conn.commit()
    finally:
        conn.close()
