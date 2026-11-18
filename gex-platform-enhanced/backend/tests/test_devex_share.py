"""
DEVEX brief access (app/core/devex_share.py): who reads what, and that a brief
never carries a section it was not given. Pure functions, no database.
"""
from datetime import datetime, timezone

import pytest

from app.core.devex_share import (
    BRIEF_SECTIONS, SECTIONS, brief_sections, build_brief, capability, decide, may_manage_shares, normalise_expiry,
    section_of,
    validate_share,
)

PACKAGES = [
    {"package_id": "a", "package_name": "Owner's engineer", "package_type": "DEVEX", "phase_required": "FEL_1",
     "cost_amount": 2e6, "estimate_class": "CLASS_4", "workflow_state": "drawn",
     "capital_eligible": ["EQUITY"], "risk_removed": ["TECHNICAL"], "notes": "internal"},
    {"package_id": "b", "package_name": "FEED", "package_type": "FEED", "phase_required": "FEED",
     "cost_amount": 6e6, "estimate_class": "CLASS_3", "workflow_state": "evidenced",
     "capital_eligible": ["EQUITY", "GRANT"], "risk_removed": ["COST"]},
    {"package_id": "c", "package_name": "Electrolysers", "package_type": "DIRECT_CAPEX",
     "phase_required": "CONSTRUCTION", "cost_amount": 100e6, "estimate_class": "CLASS_3",
     "workflow_state": "costed", "capital_eligible": ["SENIOR_DEBT"], "risk_removed": ["EXECUTION"]},
]
WAVE = [{"year": 2026, "layers": {"EQUITY_SPONSOR": 5.0, "GRANT": 1.0}},
        {"year": 2025, "layers": {"EQUITY_SEED": 2.5}}]


def test_the_owner_and_platform_staff_read_everything():
    assert decide(is_owner=True, is_platform_admin=False, shared_sections=()) == (SECTIONS, "owner")
    assert decide(is_owner=False, is_platform_admin=True, shared_sections=()) == (SECTIONS, "platform_admin")


def test_anyone_else_reads_exactly_what_is_shared_and_nothing_without_a_share():
    assert decide(is_owner=False, is_platform_admin=False, shared_sections=()) == ((), "none")
    assert decide(is_owner=False, is_platform_admin=False, shared_sections=["FUNDING", "SUMMARY"]) \
        == (("SUMMARY", "FUNDING"), "share")


def test_inside_the_owner_the_brief_is_for_finance_and_executives():
    assert brief_sections(SECTIONS, "owner", "FINANCE_TREASURY") == BRIEF_SECTIONS
    assert brief_sections(SECTIONS, "owner", "EXECUTIVE") == BRIEF_SECTIONS
    assert brief_sections(SECTIONS, "owner", "ENGINEERING") == ()
    assert brief_sections(("SUMMARY",), "share", None) == ("SUMMARY",)


def test_only_the_owner_companys_finance_or_executive_manages_shares():
    assert may_manage_shares(owns_project=True, business_function="EXECUTIVE")
    assert not may_manage_shares(owns_project=True, business_function="ENGINEERING")
    assert not may_manage_shares(owns_project=False, business_function="FINANCE_TREASURY")


def test_capability_names_round_trip_and_reject_strangers():
    assert section_of(capability("FUNDING")) == "FUNDING"
    assert section_of("FINANCE_REVIEW") is None
    assert section_of("DEVEX_SHARE:EVERYTHING") is None


def test_share_request_is_validated():
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    assert validate_share(user_id="u1", sections=["PACKAGES", "SUMMARY"], expires_at="2027-01-31", now=now) \
        == ("SUMMARY", "PACKAGES")
    for bad, message in [
        (dict(user_id=" ", sections=["SUMMARY"], expires_at=None), "user_id"),
        (dict(user_id="u1", sections=[], expires_at=None), "at least one"),
        (dict(user_id="u1", sections=["RETURNS"], expires_at=None), "unknown section"),
        (dict(user_id="u1", sections=["SUMMARY"], expires_at="2026-01-01"), "in the past"),
        (dict(user_id="u1", sections=["SUMMARY"], expires_at="next week"), "ISO-8601"),
    ]:
        with pytest.raises(ValueError, match=message):
            validate_share(**bad, now=now)


def test_brief_covers_pre_fid_packages_only():
    b = build_brief(PACKAGES, WAVE, SECTIONS, "UNVERIFIED")
    assert b["summary"]["pre_fid_spend_eur"] == 8e6            # the 100m construction package is out
    assert b["summary"]["package_count"] == 2
    assert b["summary"]["drawn_eur"] == 2e6
    assert b["summary"]["evidenced_share"] == pytest.approx(1.0)
    assert b["summary"]["fid_grade_share"] == pytest.approx(0.75)
    assert [p["package_id"] for p in b["packages"]] == ["a", "b"]
    assert "notes" not in b["packages"][0]
    assert b["breakdown"]["phase_totals"] == {"FEL_1": 2e6, "FEL_2": 0.0, "FEED": 6e6}
    assert [y["year"] for y in b["funding"]["years"]] == [2025, 2026]
    assert b["funding"]["total_eur"] == pytest.approx(8.5e6)
    assert b["funding"]["register_gap_eur"] == pytest.approx(0.5e6)
    assert b["funding"]["drawn_before_fid"] == []


def test_brief_holds_only_the_sections_it_is_given():
    b = build_brief(PACKAGES, WAVE, ["FUNDING"])
    assert b["sections"] == ["FUNDING"]
    assert not {"summary", "breakdown", "packages"} & set(b)
    assert "register_gap_eur" not in b["funding"]              # would give the register total away
    assert set(build_brief(PACKAGES, WAVE, ["SUMMARY"])) == {"sections", "pre_fid_phases", "summary"}


def test_senior_debt_drawn_before_fid_is_flagged_and_a_missing_wave_is_none():
    b = build_brief(PACKAGES, [{"year": 2026, "layers": {"SENIOR_DEBT": 3.0}}], ["FUNDING"])
    assert b["funding"]["drawn_before_fid"] == ["SENIOR_DEBT"]
    assert build_brief(PACKAGES, None, ["FUNDING"])["funding"] is None


def test_a_bare_date_expiry_is_stored_timezone_aware():
    assert normalise_expiry("2027-01-31") == "2027-01-31T00:00:00+00:00"
    assert normalise_expiry(None) is None
    assert datetime.fromisoformat(normalise_expiry("2027-01-31")) > datetime(2026, 11, 16, tzinfo=timezone.utc)


def test_evidence_is_its_own_section_and_never_part_of_the_brief():
    assert "EVIDENCE" in SECTIONS and "EVIDENCE" not in BRIEF_SECTIONS
    assert brief_sections(("EVIDENCE",), "share", None) == ()           # an evidence share opens no brief
    assert build_brief(PACKAGES, WAVE, SECTIONS)["sections"] == list(BRIEF_SECTIONS)
    assert validate_share(user_id="u1", sections=["EVIDENCE"], expires_at=None) == ("EVIDENCE",)
