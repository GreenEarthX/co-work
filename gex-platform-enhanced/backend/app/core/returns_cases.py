"""
Published returns cases (handoff v4, tasks 8 and 10; JML 2026-11-17).
=====================================================================
The OWNER publishes a returns case. A case version is fixed by: project,
scenario, valuation boundary, TEA case and input versions, model version, rules
version, evidence snapshot and publication date. It is hashed and immutable
(migration 123). Every screen, report and export that cites a version reads the
stored figures; nothing recomputes a case for an audience.

Rules held here, as pure functions where possible:

  identity()       what a version is, shown wherever it is cited
  needs_review()   DERIVED: what changed since publication (evidence fingerprint,
                   rules version, TEA claim). The case is never changed and no
                   new figure replaces it silently.
  disclose()       PERMISSIONS CONTROL DISCLOSURE ONLY. The owner sees the whole
                   version. A reader with the owner's RETURNS share sees the same
                   results — the same IRR — without any dated pre-FID figure; the
                   DEVEX total only with SUMMARY. Nothing is recomputed.

Sharing: capability "RETURNS_SHARE:<version_id>" (that version only) or
"RETURNS_SHARE:<case_id>@LATEST" (that case and its later versions), one user,
one project, read-only, expirable, revocable and audited in finance_entitlements.
RETURNS never opens FUNDING, PACKAGES, EVIDENCE or any pre-FID detail, and no
DEVEX section opens a returns case.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional

CAPABILITY_PREFIX = "RETURNS_SHARE:"
LATEST = "@LATEST"
BOUNDARIES = ("FULL_PROJECT", "FROM_FID")
VALIDITY = ("A published case states the forecast on its stated inputs. A verified base case means its "
            "assumptions and evidence were reviewed; it does not mean the forecast outcome is assured.")

_IDENTITY_FIELDS = ("version_id", "case_id", "project_id", "case_name", "version_number", "scenario",
                    "valuation_boundary", "tea_case", "input_versions", "model_version", "rules_version",
                    "evidence_fingerprint", "evidence_evaluated_at", "content_sha256",
                    "supersedes_version_id", "published_at", "published_by")


def case_id(project_id: str, case_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", case_name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("case_name is required")
    return f"{project_id}:{slug}"


def share_capability(*, version_id: Optional[str] = None, case: Optional[str] = None) -> str:
    if bool(version_id) == bool(case):
        raise ValueError("share one version, or one case and its later versions")
    return CAPABILITY_PREFIX + (version_id if version_id else case + LATEST)


def shared_targets(capabilities: Iterable[str]) -> tuple[set[str], set[str]]:
    """(version ids, case ids shared with later versions) from active capabilities."""
    versions, cases = set(), set()
    for cap in capabilities:
        if not cap.startswith(CAPABILITY_PREFIX):
            continue
        target = cap[len(CAPABILITY_PREFIX):]
        if target.endswith(LATEST):
            cases.add(target[:-len(LATEST)])
        elif target:
            versions.add(target)
    return versions, cases


def readable_by_share(version: dict, versions: set[str], cases: set[str]) -> bool:
    return version["version_id"] in versions or version["case_id"] in cases


def content_hash(record: dict) -> str:
    body = {k: record.get(k) for k in ("case_id", "project_id", "case_name", "version_number", "scenario",
                                       "valuation_boundary", "tea_case", "input_versions", "model_version",
                                       "rules_version", "evidence_fingerprint", "inputs", "results",
                                       "sensitivities", "provenance", "supersedes_version_id")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def new_version(*, project_id: str, owner_tenant_id: str, case_name: str, previous: Optional[dict],
                engine_result: dict, inputs: dict, readiness: dict, tea_case: Optional[dict],
                input_versions: Optional[dict], governance: Optional[dict], published_by: str) -> dict:
    """The row to insert. `engine_result` is the PF engine's returns result."""
    if engine_result.get("valuation_boundary") not in BOUNDARIES:
        raise ValueError("the engine result does not name its valuation boundary")
    record = {
        "version_id": str(uuid.uuid4()),
        "case_id": case_id(project_id, case_name),
        "project_id": project_id,
        "owner_tenant_id": owner_tenant_id,
        "case_name": case_name.strip(),
        "version_number": (previous["version_number"] + 1) if previous else 1,
        "scenario": engine_result["scenario"],
        "valuation_boundary": engine_result["valuation_boundary"],
        "tea_case": tea_case,
        "input_versions": input_versions,
        "model_version": engine_result["model_version"],
        "rules_version": readiness.get("rules_version"),
        "evidence_fingerprint": readiness.get("evidence_fingerprint"),
        "evidence_evaluated_at": readiness.get("evaluated_at"),
        "inputs": inputs,
        "results": {k: v for k, v in engine_result.items() if k not in ("downside", "provenance")},
        "sensitivities": engine_result.get("downside"),
        "provenance": engine_result.get("provenance"),
        "governance": governance,
        "supersedes_version_id": previous["version_id"] if previous else None,
        "published_by": published_by,
    }
    record["content_sha256"] = content_hash(record)
    return record


def identity(version: dict) -> dict:
    out = {k: version.get(k) for k in _IDENTITY_FIELDS}
    # Calculation chain (18 Nov): a version built from saved, reviewed records says so;
    # one built from inputs the owner typed says that too.
    out["chain_traced"] = bool((version.get("input_versions") or {}).get("chain"))
    out["valuation_boundary_label"] = (
        "Full project: pre-FID spend included" if version.get("valuation_boundary") == "FULL_PROJECT" else
        "From FID: pre-FID spend excluded as sunk — NOT a full-project return")
    return out


def needs_review(version: dict, *, current_fingerprint: Optional[str], current_rules_version: Optional[str],
                 current_tea_claim: Optional[str]) -> dict:
    """What changed behind a published case since it was published. Derived only."""
    changes = []
    if current_fingerprint is not None and version.get("evidence_fingerprint") != current_fingerprint:
        changes.append({"what": "EVIDENCE", "detail": "The project's evidence, premise or contract terms "
                        "changed since this case was published."})
    if current_rules_version is not None and version.get("rules_version") != current_rules_version:
        changes.append({"what": "RULES", "detail": f"Rules {version.get('rules_version')} -> {current_rules_version}."})
    published_claim = (version.get("tea_case") or {}).get("claim_id")
    if published_claim and current_tea_claim and published_claim != current_tea_claim:
        changes.append({"what": "TEA_INPUT", "detail": f"TEA base case {published_claim} -> {current_tea_claim}."})
    return {"needs_review": bool(changes), "changes": changes,
            "note": ("This case is unchanged; it reflects its inputs as published. The owner may publish a new "
                     "version; this one and the reports citing it stay as they are.") if changes else None}


def _undated(flows: dict) -> dict:
    """Project and equity flows with every pre-FID (dated) period removed."""
    first = flows.get("first_period", 0)
    keep = {}
    for key in ("unlevered", "levered"):
        series = flows.get(key) or []
        keep[key] = [cf for i, cf in enumerate(series) if first + i >= 0]
    return {"first_period": max(0, first), **keep,
            "withheld": "pre-FID periods" if first < 0 else None}


def disclose(version: dict, *, full: bool, devex_sections: Iterable[str] = ()) -> dict:
    """The version as this reader may see it. The FIGURES are the stored ones in
    both cases: a share changes what is shown, never what is computed."""
    base = {"identity": identity(version), "validity": VALIDITY}
    if full:
        return {**base, "disclosure": "OWNER", "inputs": version["inputs"], "results": version["results"],
                "sensitivities": version.get("sensitivities"), "provenance": version.get("provenance"),
                "governance": version.get("governance")}
    sections = set(devex_sections)
    results = dict(version["results"])
    results["flows"] = _undated(results.get("flows") or {})
    results["timeline"] = [row for row in results.get("timeline") or [] if row.get("period", 0) >= 0]
    withheld = ["dated pre-FID figures (FUNDING not shared)"]
    if "SUMMARY" not in sections:
        for key in ("devex_eur", "total_investment_eur", "equity_invested_eur"):
            results.pop(key, None)
        withheld.append("DEVEX totals (SUMMARY not shared)")
    provenance = dict(version.get("provenance") or {})
    if provenance.get("inputs"):
        provenance["inputs"] = {k: v for k, v in provenance["inputs"].items() if k != "pre_fid_spend_eur"}
    return {**base, "disclosure": "RETURNS_SHARE", "withheld": withheld, "results": results,
            "sensitivities": version.get("sensitivities"), "provenance": provenance}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
