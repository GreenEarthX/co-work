"""
DEVEX brief — who may read it, and what they are given.
=======================================================
The DEVEX brief is all pre-FID spend of one project. It belongs to the
producer. This module holds the two decisions about it as pure functions, so
they can be read and tested without a database or a request:

  decide()        which sections a caller may read, and on what basis
  build_brief()   the brief itself, holding ONLY the sections it is given

Rules
  - The owner company (projects.owner_tenant_id) reads its own pre-FID data.
    Its finance and executive functions read the brief; that is the default
    and needs no grant.
  - Everyone else needs a share: a bank, a DFI, an adviser, and an associated
    company alike. A share names one user, one project and one section. It is
    a row in the existing project entitlement store (capability
    "DEVEX_SHARE:<SECTION>"), so it expires, is revoked and is audited like
    every other grant. No lender mandate is required: the owner's share is
    the authorisation.
  - A section opens only itself. SUMMARY and BREAKDOWN are aggregates in the
    brief; they do not open the package list (PACKAGES) or the spend wave
    (FUNDING). The package list does not open the documents and history
    beneath it (EVIDENCE). None opens another.
  - Nothing else opens pre-FID data. A finance role, a project relationship,
    a mandate or a FINANCE_REVIEW grant gives access to returns and other
    finance screens; none of them gives access to DEVEX.
  - Shares are read-only. Only the owner company's finance or executive
    function may create or revoke one.

The same decision is applied on every path to this data — the brief, the
package register, the spend wave, the project datasets and the one-shot project
view — by app/core/pre_fid_access.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

SECTIONS = ("SUMMARY", "BREAKDOWN", "FUNDING", "PACKAGES", "EVIDENCE")
BRIEF_SECTIONS = ("SUMMARY", "BREAKDOWN", "FUNDING", "PACKAGES")
SECTION_LABELS = {
    "SUMMARY": "Totals: pre-FID spend, drawn, evidenced, estimate maturity",
    "BREAKDOWN": "Spend by package type and phase",
    "FUNDING": "Funding by year and capital layer",
    "PACKAGES": "The package list: cost, state, risk removed, unlock conditions",
    "EVIDENCE": "Evidence documents and event history of each package (not part of the brief)",
}
CAPABILITY_PREFIX = "DEVEX_SHARE:"

PRODUCER_FUNCTIONS = frozenset({"FINANCE_TREASURY", "EXECUTIVE"})

PRE_FID_PHASES = ("FEL_1", "FEL_2", "FEED")
WORKFLOW_STATES = ("identified", "scoped", "costed", "evidenced", "eligible", "approved",
                   "committed", "drawable", "drawn", "verified", "closed", "propagated")
FID_GRADE_CLASSES = frozenset({"CLASS_3", "CLASS_2", "CLASS_1"})
NOT_BEFORE_FID = frozenset({"SENIOR_DEBT", "SENIOR", "ECA"})
_PACKAGE_FIELDS = ("package_id", "package_name", "package_type", "phase_required", "cost_amount",
                   "cost_p10", "cost_p90", "estimate_class", "workflow_state", "capital_eligible",
                   "risk_removed", "gex_gate", "unlock_condition")


def capability(section: str) -> str:
    return f"{CAPABILITY_PREFIX}{section}"


def section_of(capability_name: str) -> Optional[str]:
    """The section a capability shares, or None if it is not a DEVEX share."""
    if not capability_name.startswith(CAPABILITY_PREFIX):
        return None
    section = capability_name[len(CAPABILITY_PREFIX):]
    return section if section in SECTIONS else None


def _ordered(sections: Iterable[str]) -> tuple[str, ...]:
    wanted = set(sections)
    return tuple(s for s in SECTIONS if s in wanted)


def decide(*, is_owner: bool, is_platform_admin: bool,
           shared_sections: Iterable[str]) -> tuple[tuple[str, ...], str]:
    """(sections of pre-FID data the caller may read, basis). No sections means refused.

    is_owner         the caller's tenant is the project's owner_tenant_id
    shared_sections  sections with an ACTIVE share for this user and project
    """
    if is_platform_admin:
        return SECTIONS, "platform_admin"
    if is_owner:
        return SECTIONS, "owner"
    shared = _ordered(shared_sections)
    return (shared, "share") if shared else ((), "none")


def brief_sections(sections: Sequence[str], basis: str, business_function: Optional[str]) -> tuple[str, ...]:
    """The sections of the BRIEF a caller is sent. Inside the owner company the
    brief is a finance and executive document; other functions work in the
    package register and are not sent it."""
    if basis == "owner" and business_function not in PRODUCER_FUNCTIONS:
        return ()
    return tuple(s for s in sections if s in BRIEF_SECTIONS)


def may_manage_shares(*, owns_project: bool, business_function: Optional[str]) -> bool:
    """Only the owner company's finance or executive function shares the brief."""
    return owns_project and business_function in PRODUCER_FUNCTIONS


def validate_share(*, user_id: str, sections: Sequence[str], expires_at: Optional[str],
                   now: Optional[datetime] = None) -> tuple[str, ...]:
    """The sections to share, in canonical order. Raises ValueError with the reason."""
    if not (user_id or "").strip():
        raise ValueError("user_id of the person the sections are shared with is required")
    unknown = sorted(set(sections) - set(SECTIONS))
    if unknown:
        raise ValueError(f"unknown section(s) {unknown}; choose from {list(SECTIONS)}")
    chosen = _ordered(sections)
    if not chosen:
        raise ValueError("select at least one section to share")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
        except ValueError:
            raise ValueError("expires_at must be an ISO-8601 date or datetime") from None
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= (now or datetime.now(timezone.utc)):
            raise ValueError("expires_at is in the past")
    return chosen


def normalise_expiry(expires_at: Optional[str]) -> Optional[str]:
    """An expiry as a timezone-aware ISO string (UTC when none is stated), or None.

    The entitlement store compares expiries with an aware "now"; a bare date
    stored as given would make that comparison fail instead of expire.
    """
    if not expires_at:
        return None
    expiry = datetime.fromisoformat(expires_at)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry.isoformat()


def _cost(rows: Iterable[dict]) -> float:
    return sum(float(r.get("cost_amount") or 0.0) for r in rows)


def _at_or_beyond(row: dict, state: str) -> bool:
    current = row.get("workflow_state")
    return current in WORKFLOW_STATES and WORKFLOW_STATES.index(current) >= WORKFLOW_STATES.index(state)


def build_brief(packages: Sequence[dict], spend_wave: Optional[Sequence[dict]],
                sections: Iterable[str], spend_wave_verification: Optional[str] = None) -> dict:
    """The brief, holding only the given sections.

    packages    every development package of the project; pre-FID phases are
                selected here, so later-phase packages never reach the brief
    spend_wave  the recorded pre-FID spend wave, [{year, layers: {layer: EUR m}}]
    """
    allowed = set(sections)
    pre_fid = [p for p in packages if p.get("phase_required") in PRE_FID_PHASES]
    total = _cost(pre_fid)
    share = (lambda part: part / total) if total > 0 else (lambda part: None)
    brief: dict = {"sections": [s for s in _ordered(allowed) if s in BRIEF_SECTIONS],
                   "pre_fid_phases": list(PRE_FID_PHASES)}

    if "SUMMARY" in allowed:
        drawn = _cost(p for p in pre_fid if _at_or_beyond(p, "drawn"))
        brief["summary"] = {
            "pre_fid_spend_eur": total,
            "package_count": len(pre_fid),
            "drawn_eur": drawn,
            "to_draw_eur": total - drawn,
            "evidenced_share": share(_cost(p for p in pre_fid if _at_or_beyond(p, "evidenced"))),
            "fid_grade_share": share(_cost(p for p in pre_fid
                                           if p.get("estimate_class") in FID_GRADE_CLASSES)),
        }

    if "BREAKDOWN" in allowed:
        types = list(dict.fromkeys(p.get("package_type") for p in pre_fid))
        brief["breakdown"] = {
            "rows": [{"package_type": t,
                      "by_phase": {ph: _cost(p for p in pre_fid if p.get("package_type") == t
                                             and p.get("phase_required") == ph)
                                   for ph in PRE_FID_PHASES},
                      "total_eur": _cost(p for p in pre_fid if p.get("package_type") == t)}
                     for t in types],
            "phase_totals": {ph: _cost(p for p in pre_fid if p.get("phase_required") == ph)
                             for ph in PRE_FID_PHASES},
            "total_eur": total,
        }

    if "FUNDING" in allowed:
        if not spend_wave:
            brief["funding"] = None
        else:
            years = sorted(({"year": int(y["year"]),
                             "layers": {k: float(v or 0.0) * 1e6 for k, v in (y.get("layers") or {}).items()}}
                            for y in spend_wave), key=lambda y: y["year"])
            layers = list(dict.fromkeys(k for y in years for k in y["layers"]))
            layer_totals = {k: sum(y["layers"].get(k, 0.0) for y in years) for k in layers}
            wave_total = sum(layer_totals.values())
            funding = {
                "years": years, "layers": layers, "layer_totals_eur": layer_totals,
                "total_eur": wave_total, "verification_state": spend_wave_verification,
                "drawn_before_fid": [k for k in layers if k in NOT_BEFORE_FID and layer_totals[k] > 0],
            }
            # The gap to the register would give away the register total, so it
            # travels only with the summary.
            if "SUMMARY" in allowed:
                funding["register_gap_eur"] = wave_total - total
            brief["funding"] = funding

    if "PACKAGES" in allowed:
        brief["packages"] = [{k: p.get(k) for k in _PACKAGE_FIELDS} for p in pre_fid]

    return brief
