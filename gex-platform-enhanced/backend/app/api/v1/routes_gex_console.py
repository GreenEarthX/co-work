"""
GEX staff console (/api/v1/gex-console) — JML, 2026-11-03.
============================================================
The CISO workspace is a client company's view of itself. This is GEX's own:
who administers the platform, which companies are on it (test or real), what
GEX staff may and may not do, and where each client's onboarding stands.

READ ONLY. Every action this screen offers goes through an endpoint that
already enforces its rule: the vetting steps through /api/v1/account/…
(separation of duties is checked there, not here), reviewer appointments
through /api/v1/projects/{id}/reviewers. Nothing here writes.

GEX staff only (`is_platform_admin`), refused otherwise. Counting projects and
evidence across every tenant needs the PLATFORM_ADMIN tenant context; this is
GEX administration, the caller is checked first, and a read failure answers
503 rather than a count of zero.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.core.abac import PLATFORM_READ_RESOURCE_TYPES, REVIEWER_GATES

router = APIRouter()

PLATFORM_ADMIN = "PLATFORM_ADMIN"

# What GEX staff may do on a client's project, and what they may not. The
# readable set is the rule itself (abac R0P); the rest restates where the
# server refuses, so the screen cannot promise more than the code allows.
STAFF_MAY = [
    "Read gates and evidence on every project (ABAC rule R0P)",
    "Vet accounts: take on an application, record the verification call and the signed usage agreement",
    "Activate an account — only if someone else made the verification call",
    "Reject or suspend an account, with a reason",
    "Appoint or revoke an evidence reviewer, on a named party's written instruction",
    "Open a client's CISO workspace (read its accounts, sign-ins, barriers)",
]
STAFF_MAY_NOT = [
    "Verify evidence or confirm contract terms — independent reviewers and counterparties do",
    "Submit, edit, export or share a client's evidence",
    "Read financial models, contracts, data rooms or project activity",
    "Create a project for a client — the owner is always the company that creates it",
    "Activate an account it verified by telephone (separation of duties)",
    "Be appointed as a reviewer",
]


def _require_staff(request: Request) -> dict:
    payload = getattr(request.state, "user_payload", None) or {}
    if not (payload.get("user_id") or payload.get("sub")):
        raise HTTPException(status_code=401, detail="Authentication required")
    if not payload.get("is_platform_admin"):
        raise HTTPException(status_code=403, detail={
            "code": "GEX_STAFF_ONLY", "message": "The GEX staff console is for GEX platform administrators."})
    return payload


def _rows(sql: str, params: dict | None = None) -> list[dict]:
    from app.db.session import get_sync_engine
    try:
        with get_sync_engine().connect() as conn:
            conn.execute(text(f"SET LOCAL app.current_company_id = '{PLATFORM_ADMIN}'"))
            return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail={
            "code": "STORE_UNREADABLE", "message": f"The account store could not be read: {type(exc).__name__}"}) from exc


def _is_test(company_id: str) -> bool:
    return company_id.startswith("test_")


@router.get("/summary")
def summary(request: Request) -> dict[str, Any]:
    caller = _require_staff(request)

    admins = _rows(
        "SELECT u.user_id, u.email, u.user_name, u.account_state, u.activated_by, u.activated_at, "
        "u.created_at, (SELECT max(h.timestamp) FROM auth_login_history h "
        "  WHERE h.user_id = u.user_id AND h.success = 1) AS last_sign_in "
        "FROM auth_users u WHERE u.is_platform_admin = 1 ORDER BY u.email")

    tenants = _rows("SELECT company_id, company_name, company_type FROM tenants ORDER BY company_name")
    states = _rows("SELECT company_id, account_state, count(*) AS n FROM auth_users "
                   "WHERE is_platform_admin = 0 GROUP BY 1, 2")
    owned = _rows("SELECT owner_tenant_id AS company_id, count(*) AS n, "
                  "count(*) FILTER (WHERE project_id LIKE 'proj_TEST_%') AS test_n "
                  "FROM projects GROUP BY 1")
    by_state: dict[str, dict[str, int]] = {}
    for r in states:
        by_state.setdefault(r["company_id"], {})[r["account_state"] or "UNKNOWN"] = int(r["n"])
    projects = {r["company_id"]: r for r in owned}

    companies = [{
        "company_id": t["company_id"], "company_name": t["company_name"], "company_type": t["company_type"],
        "is_test": _is_test(t["company_id"]),
        "accounts": by_state.get(t["company_id"], {}),
        "projects_owned": int(projects.get(t["company_id"], {}).get("n", 0)),
        "test_projects_owned": int(projects.get(t["company_id"], {}).get("test_n", 0)),
    } for t in tenants]

    queue = _rows("SELECT count(*) AS n FROM auth_users WHERE account_state IN ('PENDING', 'IN_VETTING')")

    return {
        "caller_user_id": caller.get("user_id") or caller.get("sub"),
        "administrators": [{**a, "activated_at": _s(a["activated_at"]), "created_at": _s(a["created_at"]),
                            "last_sign_in": _s(a["last_sign_in"])} for a in admins],
        "companies": companies,
        "vetting_queue_count": int(queue[0]["n"]) if queue else 0,
        "staff_rights": {
            "readable_on_every_project": sorted(PLATFORM_READ_RESOURCE_TYPES),
            "may": STAFF_MAY, "may_not": STAFF_MAY_NOT,
            "reviewer_gates": {role.value: sorted(g, key=lambda x: int(x[1:]))
                               for role, g in REVIEWER_GATES.items()},
        },
    }


def _s(v: Any) -> Any:
    return None if v is None else str(v)


def _step(key: str, label: str, actor: str, status: str, detail: str) -> dict:
    return {"key": key, "label": label, "actor": actor, "status": status, "detail": detail}


@router.get("/onboarding/{company_id}")
def onboarding(company_id: str, request: Request) -> dict[str, Any]:
    """Where a client's onboarding stands, step by step, from the records alone."""
    _require_staff(request)

    tenant = _rows("SELECT company_id, company_name FROM tenants WHERE company_id = :c", {"c": company_id})
    if not tenant:
        raise HTTPException(status_code=404, detail={"code": "TENANT_NOT_REGISTERED",
                                                     "message": f"No company {company_id!r} is registered."})
    name = tenant[0]["company_name"]

    # A registered account carries a provisional company id until activation binds it.
    users = _rows(
        "SELECT user_id, email, user_name, telephone, account_state, phone_verified_by, phone_verified_at, "
        "agreement_ref, agreement_signed_at, activated_by, activated_at, company_id "
        "FROM auth_users WHERE is_platform_admin = 0 AND (company_id = :c "
        "OR (company_id LIKE 'pending_%' AND company_name = :n)) ORDER BY user_name",
        {"c": company_id, "n": name})
    projects = _rows("SELECT project_id, project_name FROM projects WHERE owner_tenant_id = :c "
                     "AND project_id NOT LIKE 'proj_TEST_%' ORDER BY project_name", {"c": company_id})
    open_ev = _rows(
        "SELECT count(*) AS n, count(e.assignee_user_id) AS assigned FROM bankability_evidence e "
        "JOIN projects p ON p.project_id = e.project_id WHERE p.owner_tenant_id = :c "
        "AND e.status <> 'VERIFIED'", {"c": company_id})[0]

    active = [u for u in users if u["account_state"] == "ACTIVE"]
    steps = [
        _step("tenant", "Company registered", "GEX", "done", f"{name} ({company_id})"),
        _step("register", "Accounts registered", "Client, or GEX on its instruction",
              "done" if users else "waiting",
              f"{len(users)} account(s)" if users else "No account registered for this company yet"),
    ]
    for u in users:
        who = u["user_name"] or u["email"]
        state = u["account_state"]
        claimed = state != "PENDING"
        steps += [
            _step(f"claim:{u['user_id']}", f"{who}: application taken on", "GEX staff",
                  "done" if claimed else "waiting",
                  f"{state} · {u['telephone'] or 'no telephone recorded'}"),
            _step(f"call:{u['user_id']}", f"{who}: verification call recorded", "GEX staff",
                  "done" if u["phone_verified_by"] else "waiting",
                  f"by {u['phone_verified_by']}" if u["phone_verified_by"] else "Not recorded"),
            _step(f"agreement:{u['user_id']}", f"{who}: signed usage agreement recorded", "GEX staff",
                  "done" if u["agreement_ref"] else "waiting",
                  u["agreement_ref"] or "Not recorded"),
            _step(f"activate:{u['user_id']}", f"{who}: activated", "A second GEX admin",
                  "done" if state == "ACTIVE" else ("blocked" if state in ("REJECTED", "SUSPENDED") else "waiting"),
                  f"by {u['activated_by']}" if state == "ACTIVE"
                  else ("Needs the call and the agreement first" if not (u["phone_verified_by"] and u["agreement_ref"])
                        else f"Anyone but {u['phone_verified_by']}")),
        ]
    steps += [
        _step("project", "Project created by the client's own account", "Client",
              "done" if projects else "waiting",
              ", ".join(p["project_name"] for p in projects) if projects
              else ("Waiting for an active account" if not active else "No project created yet")),
        _step("evidence", "Open evidence requests assigned to named accounts", "GEX",
              "done" if projects and open_ev["n"] and open_ev["assigned"] == open_ev["n"]
              else "waiting",
              f"{open_ev['assigned']} of {open_ev['n']} assigned" if open_ev["n"] else "No open requests yet"),
    ]

    return {
        "company_id": company_id, "company_name": name,
        "accounts": [{**u, "phone_verified_at": _s(u["phone_verified_at"]),
                      "agreement_signed_at": _s(u["agreement_signed_at"]),
                      "activated_at": _s(u["activated_at"])} for u in users],
        "steps": steps,
    }


@router.get("/ledger-anchor")
def ledger_anchor_health(request: Request) -> dict[str, Any]:
    """Phase 4 (Q11): the outbox by status, the rows that FAILED after their eight
    attempts, and whether the worker runs. Hashes and statuses only: no contract
    reference, no party, no terms."""
    from app.core import ledger_anchor

    _require_staff(request)
    counts = _rows("SELECT status, count(*) AS n, count(*) FILTER (WHERE pseudo_id IS NULL) AS no_pseudo_id, "
                   "min(created_at) AS oldest FROM ledger_anchor_outbox GROUP BY status")
    failed = _rows("SELECT event_hash, event_type, attempts, last_error, created_at, next_attempt_at "
                   "FROM ledger_anchor_outbox WHERE status = 'FAILED' ORDER BY id LIMIT 100")
    state = dict(ledger_anchor.STATE)
    return {
        "backend": state["backend"], "worker_running": state["running"], "worker_refused": state["refused"],
        "last_run_at": state["last_run_at"], "last_result": state["last_result"], "last_error": state["last_error"],
        "by_status": {r["status"]: {"count": int(r["n"]), "without_pseudo_id": int(r["no_pseudo_id"]),
                                    "oldest": _s(r["oldest"])} for r in counts},
        "failed": [{"event_hash": f["event_hash"].strip(), "event_type": f["event_type"],
                    "attempts": int(f["attempts"]), "last_error": f["last_error"], "created_at": _s(f["created_at"]),
                    "next_attempt_at": _s(f["next_attempt_at"])} for f in failed],
    }


# ── Model parameters, read only (JML, 20 Nov 2026) ────────────────────────────
# Two screens for GEX administrators: what the Gabillon model runs on, and what the TEA
# engine runs on. Nothing is edited here. A reference value is approved on the console's
# "Reference values awaiting approval" panel; a Gabillon calibration is the PF engine's.

_REF_COLS = ("ref_id, parameter_key, pathway, region, value_low, value_base, value_high, unit, currency, "
             "price_base_date, source_class, source_name, valid_from, state, proposed_by, proposed_at, "
             "approved_by, approved_at, note")
TEA_REFERENCE_KEYS = ("tea_fx_usd_to_eur", "tea_lcop_plausible_band", "tea_mc_default_rel_std",
                      "tea_mc_max_rel_std", "co2_feedstock_price", "h2_density_normal_0c_101325pa",
                      "electrolyser_installed_capex", "electrolyser_system_sec", "stack_life_hours",
                      "stack_replacement_pct_capex")


def _plain(v: Any) -> Any:
    """Numbers stay numbers; anything else that is not JSON becomes text."""
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def _reference(where: str, params: dict) -> list[dict]:
    return [{k: _plain(v) for k, v in r.items()} for r in _rows(
        f"SELECT {_REF_COLS} FROM reference_parameter WHERE {where} "
        "ORDER BY parameter_key, valid_from DESC NULLS LAST, proposed_at DESC", params)]


@router.get("/gabillon")
async def gabillon_parameters(request: Request) -> dict[str, Any]:
    """The Gabillon parameters per molecule (PF engine) and the Gabillon CEPCI forward rows."""
    _require_staff(request)
    from app.api.v1.routes_pricing_proxy import _call_pricing
    molecules: list[dict] = []
    engine_error = None
    try:
        cat = (await _call_pricing("/molecules")).get("catalog", [])
        for c in cat + [{"key": "H2", "label": "Hydrogen", "unit": "€/t (≡ €/kg × 1000)"}]:
            p = await _call_pricing(f"/params/{c['key']}")
            molecules.append({"key": c["key"], "label": c.get("label"), "unit": c.get("unit"),
                              "calibration_status": p.get("calibration_status"), "params": p.get("params")})
    except HTTPException as e:
        engine_error = str(e.detail)[:300]
    return {"molecules": molecules, "engine_error": engine_error,
            "cepci_forward": _reference("parameter_key LIKE 'cepci_forward_%'", {}),
            "notes": [
                "SEED = expert priors with no market observations (n_observations 0); MARKET = fitted to "
                "observations on the PF engine's calibration screen.",
                "The CEPCI forward rows are the Gabillon P-forward calibrated on the CEPCI history; a TEA run "
                "uses only an APPROVED row, and a published CEPCI value always wins.",
                "Electricity has no Gabillon curve: power is not storable.",
            ]}


@router.get("/tea-parameters")
async def tea_parameters(request: Request) -> dict[str, Any]:
    """What the TEA engine prices with: the pinned correlation set, GEX's equipment train under
    four eyes, and the TEA reference values."""
    _require_staff(request)
    import httpx
    from app.api.v1.routes_tea import TEA_ENGINE_URL
    engine, engine_error = None, None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{TEA_ENGINE_URL}/tea/correlations",
                                 headers={"Authorization": request.headers.get("Authorization", "")})
        if r.status_code == 200:
            engine = r.json()
        else:
            engine_error = f"TEA engine answered {r.status_code}"
    except httpx.HTTPError as e:
        engine_error = f"TEA engine unavailable: {type(e).__name__}"
    spec = [{k: _plain(v) for k, v in r.items()} for r in _rows(
        "SELECT spec_id, fuel_id, role, node, category, equipment_type, material, base_param, base_param_unit, "
        "scale_exp, reference_nameplate_t_per_year, state, proposed_by, proposed_at, approved_by, approved_at, note "
        "FROM tea_equipment_spec ORDER BY fuel_id, state, role")]
    pinned = [{k: _plain(v) for k, v in r.items()} for r in _rows(
        "SELECT set_hash, openpytea_version, correlations, cepci_year_min, cepci_year_max, "
        "gex_supplied_cepci_years, state, first_seen_at, first_seen_project, reviewed_by, reviewed_at, note "
        "FROM tea_correlation_set ORDER BY first_seen_at")]
    return {"engine": engine, "engine_error": engine_error, "equipment_spec": spec,
            "correlation_sets_seen": pinned,
            "reference": _reference("parameter_key = ANY(:k)", {"k": list(TEA_REFERENCE_KEYS)})}
