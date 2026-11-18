"""
The product behind a token: quality, carbon intensity and certificates (Phase 1; alembic 116).

Product requirement (discovery review §3.1): a token is a defined fuel quantity linked to its
molecule, origin, period, certification documents, environmental attributes and technical
qualities; certification ALWAYS has an explicit status; tokenisation, payment or membership
never establish verification.

  * The OWNING company declares (policy action `product.declare`: Commercial, Operations,
    Engineering or Compliance): quality parameters (declared, or measured with a lab document),
    carbon intensity (method, boundary, date, basis), certificates and inspection reports with
    their SCOPE (organisation, site, batch, sample) and the tokens a batch or sample covers.
  * ONLY an appointed independent reviewer decides a certificate (D-F, JML 2026-11-14): an
    account appointed CERTIFIER (or INDEPENDENT_ENGINEER, for an inspection report) on the
    project through GEX's reviewer appointments, of a company that is neither the owner nor the
    submitter, never GEX, and only with the document on file.
  * Expiry is derived at read time from valid_until; a verified certificate past its date reads
    "expired" everywhere, with no job to run.

Writes go through the market operator connection after the caller is authorised here.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional
import os
import re

from app.core import market_engine as me
from app.core.market_engine import Party, _refuse
from app.trading_book import record

SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 25 * 1024 * 1024
# Typed quality parameters: name -> (unit, what it is). A parameter outside this list is refused,
# so two sellers never describe the same property under two names.
PARAMETERS: dict[str, tuple[str, str]] = {
    "purity_pct_mass": ("% m/m", "Main component, mass fraction"),
    "purity_pct_mol": ("% mol/mol", "Main component, mole fraction"),
    "water_ppm_mass": ("ppm m/m", "Water"),
    "sulphur_ppm_mass": ("ppm m/m", "Total sulphur"),
    "chloride_ppm_mass": ("ppm m/m", "Chloride"),
    "oxygen_ppm_mol": ("ppm mol/mol", "Oxygen"),
    "co_ppm_mol": ("ppm mol/mol", "Carbon monoxide"),
    "co2_ppm_mol": ("ppm mol/mol", "Carbon dioxide"),
    "total_hydrocarbons_ppm_mol": ("ppm mol/mol", "Total hydrocarbons"),
    "ammonia_ppm_mol": ("ppm mol/mol", "Ammonia"),
    "ethanol_ppm_mass": ("ppm m/m", "Ethanol"),
    "density_kg_m3": ("kg/m3", "Density at reference conditions"),
    "delivery_pressure_bar": ("bar", "Delivery pressure"),
    "delivery_temperature_c": ("degC", "Delivery temperature"),
}
CI_BASES = ("estimate", "calculated", "measured")
SCOPES = ("organisation", "site", "batch", "sample")
DECIDERS = {"certificate": ("CERTIFIER",), "inspection": ("CERTIFIER", "INDEPENDENT_ENGINEER")}


def docs_dir() -> Path:
    return Path(os.getenv("GEX_PRODUCT_DOCS_DIR", "data/product_docs"))


def _iso(r: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, (datetime, date)) else v) for k, v in r.items() if k != "stored_path"}


def _project(conn, project_id: str) -> dict:
    p = record._row(conn, "SELECT project_id, owner_tenant_id FROM projects WHERE project_id = ?", (project_id,))
    if p is None:
        _refuse(404, "PROJECT_NOT_FOUND", "No project with that id.")
    return p


def _token(conn, token_id: str) -> dict:
    t = record._row(conn, "SELECT t.*, c.project_id FROM tokens t JOIN capacities c ON c.id = t.capacity_id "
                          "WHERE t.id = ?", (token_id,))
    if t is None:
        _refuse(404, "TOKEN_NOT_FOUND", "No token with that id.")
    return t


def _declarer(party: Party, owner: Optional[str]) -> None:
    me._trader(party)
    me._may(party, "product.declare")
    if owner != party.company_id:
        _refuse(404, "NOT_YOUR_PRODUCT", "Only the company that owns the project records its product facts.")


def _on_file(conn, project_id: str, sha: Optional[str], what: str) -> None:
    if not sha or not SHA256.match(str(sha)):
        _refuse(422, "DOCUMENT_REQUIRED", f"{what} needs its document on file: name it by sha256.")
    if record._row(conn, "SELECT 1 AS x FROM product_document WHERE project_id = ? AND sha256 = ?",
                   (project_id, sha)) is None:
        _refuse(422, "DOCUMENT_NOT_ON_FILE", "No document with that sha256 is on file for this project.")


# ── declarations (the owning company) ────────────────────────────────────────

def file_document(party: Party, project_id: str, filename: str, content: bytes) -> dict:
    if not content:
        _refuse(422, "DOCUMENT_EMPTY", "The document is empty.")
    if len(content) > MAX_BYTES:
        _refuse(413, "DOCUMENT_TOO_LARGE", "Documents are limited to 25 MB.")
    conn = me._conn()
    try:
        _declarer(party, _project(conn, project_id)["owner_tenant_id"])
        sha = hashlib.sha256(content).hexdigest()                 # GEX computes it, never the caller
        found = record._row(conn, "SELECT * FROM product_document WHERE project_id = ? AND sha256 = ?", (project_id, sha))
        if found:
            return _iso(found)
        dest = docs_dir() / project_id
        dest.mkdir(parents=True, exist_ok=True)
        name = Path(filename or "document").name
        path = dest / f"{sha}_{name}"
        path.write_bytes(content)
        conn.execute("INSERT INTO product_document (project_id, sha256, filename, size_bytes, stored_path, uploaded_by, "
                     "company_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (project_id, sha, name, len(content), str(path), party.user_id, party.company_id))
        conn.commit()
        return _iso(record._row(conn, "SELECT * FROM product_document WHERE project_id = ? AND sha256 = ?", (project_id, sha)))
    finally:
        conn.close()


def add_quality(party: Party, token_id: str, *, parameter: str, value: float, basis: str,
                document_sha256: Optional[str] = None) -> dict:
    if parameter not in PARAMETERS:
        _refuse(422, "QUALITY_PARAMETER", f"Unknown parameter {parameter!r}. Known: {', '.join(PARAMETERS)}.")
    if basis not in ("declared", "measured"):
        _refuse(422, "QUALITY_BASIS", "A quality value is declared, or measured with its lab report on file.")
    conn, trail = me._conn(), me._Trail(party)
    try:
        t = _token(conn, token_id)
        _declarer(party, _project(conn, t["project_id"])["owner_tenant_id"])
        if basis == "measured":
            _on_file(conn, t["project_id"], document_sha256, "A measured value")
        row = record._row(conn, "INSERT INTO token_quality (token_id, parameter, value, unit, basis, document_sha256, "
                                "recorded_by) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *",
                          (token_id, parameter, value, PARAMETERS[parameter][0], basis, document_sha256, party.user_id))
        trail.add("product.quality_recorded", "token", token_id, {"parameter": parameter, "basis": basis},
                  t["correlation_id"], t["project_id"])
        me._commit(conn, trail)
        return _iso(row)
    finally:
        conn.close()


def add_carbon_intensity(party: Party, token_id: str, *, value_gco2e_mj: float, method: str, system_boundary: str,
                         calculation_date: str, basis: str, document_sha256: Optional[str] = None) -> dict:
    if basis not in CI_BASES:
        _refuse(422, "CI_BASIS", f"The basis is one of: {', '.join(CI_BASES)}.")
    if not (method or "").strip() or not (system_boundary or "").strip():
        _refuse(422, "CI_METHOD", "Name the calculation method and the system boundary.")
    conn, trail = me._conn(), me._Trail(party)
    try:
        t = _token(conn, token_id)
        _declarer(party, _project(conn, t["project_id"])["owner_tenant_id"])
        if basis != "estimate":
            _on_file(conn, t["project_id"], document_sha256, "A calculated or measured carbon intensity")
        row = record._row(conn, "INSERT INTO token_carbon_intensity (token_id, value_gco2e_mj, method, system_boundary, "
                                "calculation_date, basis, document_sha256, recorded_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                                "RETURNING *", (token_id, value_gco2e_mj, method.strip(), system_boundary.strip(),
                                                calculation_date, basis, document_sha256, party.user_id))
        trail.add("product.carbon_intensity_recorded", "token", token_id, {"basis": basis}, t["correlation_id"],
                  t["project_id"])
        me._commit(conn, trail)
        return _iso(row)
    finally:
        conn.close()


def submit_certificate(party: Party, project_id: str, *, kind: str, scheme: str, body: str, reference: str,
                       scope: str, valid_from: str, valid_until: Optional[str] = None, facility_id: Optional[str] = None,
                       document_sha256: Optional[str] = None, covers: Optional[list[dict]] = None) -> dict:
    if kind not in DECIDERS:
        _refuse(422, "CERTIFICATE_KIND", "A record is a certificate or an inspection report.")
    if scope not in SCOPES:
        _refuse(422, "CERTIFICATE_SCOPE", f"The scope is one of: {', '.join(SCOPES)}.")
    if not (scheme or "").strip() or not (body or "").strip() or not (reference or "").strip():
        _refuse(422, "CERTIFICATE_IDENTITY", "Name the scheme, the issuing body and the reference.")
    if scope in ("batch", "sample") and not covers:
        _refuse(422, "CERTIFICATE_COVERAGE", "A batch or sample record names the tokens it covers.")
    if scope in ("organisation", "site") and covers:
        _refuse(422, "CERTIFICATE_COVERAGE", "An organisation or site certificate covers no particular quantity.")
    conn, trail = me._conn(), me._Trail(party)
    try:
        _declarer(party, _project(conn, project_id)["owner_tenant_id"])
        if document_sha256:
            _on_file(conn, project_id, document_sha256, "A certificate")
        for c in covers or []:
            if _token(conn, str(c.get("token_id")))["project_id"] != project_id:
                _refuse(422, "CERTIFICATE_COVERAGE", "A record covers tokens of its own project only.")
        state = "submitted" if document_sha256 else "asserted"   # never 'verified' from the submitter
        cert = record._row(conn, "INSERT INTO product_certificate (project_id, kind, scheme, body, reference, scope, "
                                 "facility_id, valid_from, valid_until, document_sha256, state, submitted_by, company_id) "
                                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *",
                           (project_id, kind, scheme.strip(), body.strip(), reference.strip(), scope, facility_id,
                            valid_from, valid_until, document_sha256, state, party.user_id, party.company_id))
        for c in covers or []:
            conn.execute("INSERT INTO token_certificate_coverage (certificate_id, token_id, quantity_t, period_start, "
                         "period_end, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                         (str(cert["id"]), str(c["token_id"]), c.get("quantity_t"), c.get("period_start"),
                          c.get("period_end"), party.user_id))
        trail.add("product.certificate_submitted", "product_certificate", str(cert["id"]),
                  {"kind": kind, "scope": scope, "state": state}, None, project_id)
        me._commit(conn, trail)
        return certificate_view(cert)
    finally:
        conn.close()


# ── decisions (an appointed independent reviewer only, D-F) ─────────────────

def decide_certificate(party: Party, certificate_id: str, decision: str, note: Optional[str] = None) -> dict:
    if decision not in ("verified", "rejected"):
        _refuse(422, "DECISION", "The decision is verified or rejected.")
    if party.is_admin:
        _refuse(403, "GEX_DOES_NOT_VERIFY", "GEX appoints reviewers; it verifies nothing itself.")
    conn, trail = me._conn(), me._Trail(party)
    try:
        c = record._row(conn, "SELECT * FROM product_certificate WHERE id::text = ? FOR UPDATE", (certificate_id,))
        if c is None:
            _refuse(404, "CERTIFICATE_NOT_FOUND", "No certificate with that id.")
        owner = _project(conn, c["project_id"])["owner_tenant_id"]
        if party.company_id in (owner, c["company_id"]):
            _refuse(403, "NOT_INDEPENDENT", "The owner and the submitter never decide their own certificate.")
        roles = {r["actor_type"] for r in record._rows(
            conn, "SELECT actor_type FROM auth_user_project_roles WHERE user_id = ? AND project_id = ?",
            (party.user_id, c["project_id"]))}
        account = record._row(conn, "SELECT assigned_audits_json FROM auth_users WHERE user_id = ?", (party.user_id,))
        audits = json.loads((account or {}).get("assigned_audits_json") or "[]")
        reviewer_company = record._row(conn, "SELECT 1 AS x FROM project_access WHERE project_id = ? AND company_id = ? "
                                             "AND access_role = 'REVIEWER'", (c["project_id"], party.company_id))
        if not (roles & set(DECIDERS[c["kind"]])) or c["project_id"] not in audits or reviewer_company is None:
            who = " or ".join(DECIDERS[c["kind"]]).lower().replace("_", " ")
            _refuse(403, "NOT_APPOINTED", f"Only a {who} appointed by GEX on this project decides this record.")
        if decision == "rejected" and c["state"] not in ("asserted", "submitted"):
            _refuse(409, "CERTIFICATE_STATE", f"A {c['state']} record is not decided again.")
        if decision == "verified":
            if c["state"] != "submitted":
                _refuse(409, "CERTIFICATE_STATE", "Only a submitted record, with its document on file, is verified.")
            if c["valid_until"] and c["valid_until"] < date.today():
                _refuse(409, "CERTIFICATE_EXPIRED", "The certificate has passed its validity date.")
        conn.execute("UPDATE product_certificate SET state = ?, decided_by = ?, decided_company_id = ?, decided_at = now(), "
                     "decision_note = ? WHERE id::text = ?",
                     (decision, party.user_id, party.company_id, (note or "").strip() or None, certificate_id))
        trail.add(f"product.certificate_{decision}", "product_certificate", certificate_id, {"by": party.user_id},
                  None, c["project_id"])
        me._commit(conn, trail)
        return certificate_view(record._row(conn, "SELECT * FROM product_certificate WHERE id::text = ?", (certificate_id,)))
    finally:
        conn.close()


# ── reading ──────────────────────────────────────────────────────────────────

def effective_state(c: dict, today: Optional[date] = None) -> str:
    """The state a reader sees: a verified certificate past valid_until is EXPIRED (never stored)."""
    today = today or date.today()
    vu = c.get("valid_until")
    vu = date.fromisoformat(str(vu)[:10]) if vu else None
    if c["state"] == "verified" and vu and vu < today:
        return "expired"
    return c["state"]


COVERS = {"organisation": "covers the organisation", "site": "covers the site",
          "batch": "covers this quantity", "sample": "covers a sample of this quantity"}


def certificate_view(c: dict) -> dict:
    out = _iso(dict(c))
    out["effective_state"] = effective_state(c)
    out["covers"] = COVERS[c["scope"]]
    return out


def _lineage(conn, token_id: str) -> list[str]:
    chain, t = [], token_id
    while t and t not in chain:
        chain.append(t)
        p = record._row(conn, "SELECT parent_token_id FROM tokens WHERE id = ?", (t,))
        t = p["parent_token_id"] if p else None
    return chain


def product_view(party: Party, token_id: str) -> dict:
    """Everything recorded about the product of a token (and of the tokens it was carved from),
    for its owner, its appointed reviewers and GEX."""
    conn = me._conn()
    try:
        t = _token(conn, token_id)
        owner = _project(conn, t["project_id"])["owner_tenant_id"]
        reviewer = record._row(conn, "SELECT 1 AS x FROM project_access WHERE project_id = ? AND company_id = ? "
                                     "AND access_role = 'REVIEWER'", (t["project_id"], party.company_id))
        if not (party.is_admin or party.company_id == owner or reviewer):
            _refuse(404, "TOKEN_NOT_FOUND", "No token of yours with that id.")
        chain = _lineage(conn, token_id)
        marks = ", ".join("?" for _ in chain)
        quality: dict[str, dict] = {}
        for q in record._rows(conn, f"SELECT * FROM token_quality WHERE token_id IN ({marks}) ORDER BY recorded_at DESC, id DESC",
                              tuple(chain)):
            quality.setdefault(q["parameter"], _iso(q))
        ci = record._row(conn, f"SELECT * FROM token_carbon_intensity WHERE token_id IN ({marks}) "
                               f"ORDER BY recorded_at DESC, id DESC LIMIT 1", tuple(chain))
        certs = record._rows(conn, f"SELECT DISTINCT c.* FROM product_certificate c LEFT JOIN token_certificate_coverage v "
                                   f"ON v.certificate_id = c.id WHERE c.project_id = ? AND (c.scope IN ('organisation', 'site') "
                                   f"OR v.token_id IN ({marks})) ORDER BY c.valid_from", (t["project_id"], *chain))
        return {"token_id": token_id, "project_id": t["project_id"], "molecule": t["molecule"],
                "production_pathway": t.get("production_pathway"), "physical_form": t.get("physical_form"),
                "specification_standard": t.get("specification_standard"),
                "quality": list(quality.values()), "carbon_intensity": _iso(ci) if ci else None,
                "certificates": [certificate_view(c) for c in certs], "carved_from": chain[1:]}
    finally:
        conn.close()


# ── what an anonymous listing may show (D-C, JML 2026-11-14) ────────────────

def listing_preview(party: Party, token_id: str) -> dict:
    """What an anonymous member will see of this token's product once listed (listing_summary,
    the market's own function), for the token's owner only: the listing wizard's preview."""
    conn = me._conn()
    try:
        t = _token(conn, token_id)
        if party.is_admin or party.company_id != _project(conn, t["project_id"])["owner_tenant_id"]:
            _refuse(404, "TOKEN_NOT_FOUND", "No token of yours with that id.")
        return {"token_id": token_id, "product": listing_summary(conn, token_id)}
    finally:
        conn.close()


def listing_summary(conn, token_id: Optional[str]) -> dict:
    """The product as an anonymous member sees it: identity, quality and carbon intensity with
    their basis, and each certificate's scheme, body, scope and EFFECTIVE status. Never a
    certificate reference, a document hash, a site or a facility: those identify the seller and
    are released with the contact, after an accepted enquiry (D-D)."""
    if not token_id:
        return {}
    t = record._row(conn, "SELECT * FROM tokens WHERE id = ?", (token_id,))
    if t is None:
        return {}
    p = record._row(conn, "SELECT c.project_id FROM capacities c WHERE c.id = ?", (t["capacity_id"],))
    chain = _lineage(conn, token_id)
    marks = ", ".join("?" for _ in chain)
    quality: dict[str, dict] = {}
    for q in record._rows(conn, f"SELECT parameter, value, unit, basis FROM token_quality WHERE token_id IN ({marks}) "
                                f"ORDER BY recorded_at DESC, id DESC", tuple(chain)):
        quality.setdefault(q["parameter"], {"parameter": q["parameter"], "value": float(q["value"]), "unit": q["unit"],
                                            "basis": q["basis"]})
    ci = record._row(conn, f"SELECT value_gco2e_mj, method, system_boundary, basis FROM token_carbon_intensity "
                           f"WHERE token_id IN ({marks}) ORDER BY recorded_at DESC, id DESC LIMIT 1", tuple(chain))
    certs = record._rows(conn, f"SELECT DISTINCT c.id, c.kind, c.scheme, c.body, c.scope, c.state, c.valid_from, c.valid_until "
                               f"FROM product_certificate c LEFT JOIN token_certificate_coverage v ON v.certificate_id = c.id "
                               f"WHERE c.project_id = ? AND (c.scope IN ('organisation', 'site') OR v.token_id IN ({marks}))",
                         ((p or {}).get("project_id"), *chain)) if p else []
    return {
        "production_pathway": t.get("production_pathway"), "physical_form": t.get("physical_form"),
        "specification_standard": t.get("specification_standard"),
        "carbon_intensity": ({"value_gco2e_mj": float(ci["value_gco2e_mj"]), "method": ci["method"],
                              "system_boundary": ci["system_boundary"], "basis": ci["basis"]} if ci else
                             ({"value_gco2e_mj": float(t["carbon_intensity_gco2e_mj"]), "basis": "declared_at_mint"}
                              if t.get("carbon_intensity_gco2e_mj") is not None else None)),
        "quality": list(quality.values()),
        # Validity dates are shown (not identifying): a buyer, and core/compatibility, judge the
        # certificate over the DELIVERY window, not only today.
        "certificates": sorted(({"kind": c["kind"], "scheme": c["scheme"], "body": c["body"], "scope": c["scope"],
                                 "covers": COVERS[c["scope"]], "status": effective_state(c),
                                 "valid_from": str(c["valid_from"])[:10] if c.get("valid_from") else None,
                                 "valid_until": str(c["valid_until"])[:10] if c.get("valid_until") else None}
                                for c in certs),
                               key=lambda c: (c["kind"], c["scheme"])),
    }
