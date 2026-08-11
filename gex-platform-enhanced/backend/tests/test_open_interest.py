"""
Open interest discovery — item 3.

This is the only surface in the platform where getting authorization wrong is a breach
rather than a bug: it discloses that a named company is short 50kt. So the tests lean
hard on the negative — what must NOT be visible, and what must happen when a rule cannot
be evaluated.
"""
from __future__ import annotations

import uuid

import pytest

from app.core import open_interest as oi
from app.core.open_interest import (
    ViewerFilter,
    ViewerProfile,
    VisibilityPolicy,
)


@pytest.fixture(scope="module", autouse=True)
def _schema(isolated_store):
    oi.init_open_interest_db()


def an_interest(company_id="producer_co", **over) -> dict:
    base = dict(
        interest_id=f"oi_{uuid.uuid4().hex[:8]}",
        company_id=company_id,
        side=oi.PRODUCER,
        molecule="e-methanol",
        volume_tpa=50_000.0,
        target_cod_year=2030,
        term_years_min=12,
        jurisdiction="DE",
        counterparty_rating="A",
        state=oi.OPEN,
    )
    base.update(over)
    return base


VIEWER = ViewerProfile(company_id="offtaker_co", jurisdiction="NL", credit_rating="A")


# ── the publisher's rule is the security half ─────────────────────────────────


def test_an_unrestricted_open_interest_is_visible():
    assert oi.publisher_permits(an_interest(), VisibilityPolicy(), VIEWER).visible


def test_a_named_denied_counterparty_cannot_see_it():
    policy = VisibilityPolicy(denied_company_ids=frozenset({"offtaker_co"}))
    decision = oi.publisher_permits(an_interest(), policy, VIEWER)
    assert not decision.visible
    assert decision.reason == "publisher_denied_company"


def test_an_allowlist_excludes_everyone_not_on_it():
    policy = VisibilityPolicy(allowed_company_ids=frozenset({"someone_else"}))
    assert not oi.publisher_permits(an_interest(), policy, VIEWER).visible

    policy = VisibilityPolicy(allowed_company_ids=frozenset({"offtaker_co"}))
    assert oi.publisher_permits(an_interest(), policy, VIEWER).visible


def test_an_empty_allowlist_hides_from_everyone_rather_than_no_one():
    """`allowed=frozenset()` means 'nobody'. The dangerous reading is 'no restriction'."""
    policy = VisibilityPolicy(allowed_company_ids=frozenset())
    assert not oi.publisher_permits(an_interest(), policy, VIEWER).visible


def test_jurisdiction_restrictions_apply_in_both_directions():
    denied = VisibilityPolicy(denied_jurisdictions=frozenset({"NL"}))
    assert not oi.publisher_permits(an_interest(), denied, VIEWER).visible

    allowed = VisibilityPolicy(allowed_jurisdictions=frozenset({"FR"}))
    assert not oi.publisher_permits(an_interest(), allowed, VIEWER).visible


def test_a_viewer_below_the_publishers_credit_floor_is_excluded():
    policy = VisibilityPolicy(min_credit_rating="AA")
    weak = ViewerProfile(company_id="weak_co", jurisdiction="NL", credit_rating="BB")
    assert not oi.publisher_permits(an_interest(), policy, weak).visible

    strong = ViewerProfile(company_id="strong_co", jurisdiction="NL", credit_rating="AAA")
    assert oi.publisher_permits(an_interest(), policy, strong).visible


def test_the_publisher_always_sees_their_own_interest_even_when_not_open():
    own = ViewerProfile(company_id="producer_co")
    for state in (oi.DRAFT, oi.OPEN, oi.MATCHED, oi.WITHDRAWN):
        assert oi.publisher_permits(an_interest(state=state), VisibilityPolicy(), own).visible


def test_a_withdrawn_or_draft_interest_is_invisible_to_everyone_else():
    for state in (oi.DRAFT, oi.WITHDRAWN, oi.MATCHED):
        decision = oi.publisher_permits(an_interest(state=state), VisibilityPolicy(), VIEWER)
        assert not decision.visible
        assert decision.reason == "interest_not_open"


# ── fail closed ───────────────────────────────────────────────────────────────


def test_no_viewer_identity_sees_nothing():
    anonymous = ViewerProfile(company_id=None)
    assert not oi.publisher_permits(an_interest(), VisibilityPolicy(), anonymous).visible


def test_an_unknown_credit_rating_fails_closed_against_a_minimum():
    """Absence of information is never permission."""
    policy = VisibilityPolicy(min_credit_rating="BBB")
    for rating in (None, "NR"):
        unknown = ViewerProfile(company_id="mystery_co", jurisdiction="NL",
                                credit_rating=rating)
        decision = oi.publisher_permits(an_interest(), policy, unknown)
        assert not decision.visible
        assert decision.reason == "viewer_credit_unknown"


def test_an_unknown_jurisdiction_fails_closed_against_an_allowlist():
    policy = VisibilityPolicy(allowed_jurisdictions=frozenset({"DE", "NL"}))
    unknown = ViewerProfile(company_id="mystery_co", jurisdiction=None, credit_rating="A")
    decision = oi.publisher_permits(an_interest(), policy, unknown)
    assert not decision.visible
    assert decision.reason == "viewer_jurisdiction_unknown"


def test_a_platform_admin_does_not_bypass_the_publishers_rule():
    """The product promise is that you control who sees your position. An admin backdoor
    makes that promise false, and it is the first thing a counterparty asks about."""
    admin = ViewerProfile(company_id="greenearthx", jurisdiction="DE",
                          credit_rating="AAA", is_platform_admin=True)
    policy = VisibilityPolicy(denied_company_ids=frozenset({"greenearthx"}))
    assert not oi.publisher_permits(an_interest(), policy, admin).visible


# ── the viewer's filter can only ever hide ────────────────────────────────────


def test_the_viewer_filter_narrows_and_never_widens():
    denied = VisibilityPolicy(denied_company_ids=frozenset({"offtaker_co"}))
    permissive = ViewerFilter()  # wants everything

    assert not oi.is_visible(an_interest(), denied, VIEWER, permissive, 2026).visible
    assert not oi.is_visible(an_interest(), denied, VIEWER, None, 2026).visible


def test_the_t_minus_x_filter_hides_projects_too_far_from_cod():
    near = an_interest(target_cod_year=2029)
    far = an_interest(target_cod_year=2040)
    within_five = ViewerFilter(max_years_to_cod=5)

    assert oi.is_visible(near, VisibilityPolicy(), VIEWER, within_five, 2026).visible
    assert not oi.is_visible(far, VisibilityPolicy(), VIEWER, within_five, 2026).visible


def test_an_unknown_cod_is_hidden_by_a_cod_filter_rather_than_assumed_near():
    unknown = an_interest(target_cod_year=None)
    decision = oi.viewer_wants(unknown, ViewerFilter(max_years_to_cod=5), 2026)
    assert not decision.visible
    assert decision.reason == "cod_unknown"


def test_molecule_side_and_jurisdiction_filters_apply():
    interest = an_interest()
    assert not oi.viewer_wants(interest, ViewerFilter(molecules=frozenset({"ammonia"})), 2026).visible
    assert not oi.viewer_wants(interest, ViewerFilter(sides=frozenset({oi.OFFTAKER})), 2026).visible
    assert not oi.viewer_wants(interest, ViewerFilter(jurisdictions=frozenset({"ES"})), 2026).visible
    assert oi.viewer_wants(interest, ViewerFilter(molecules=frozenset({"e-methanol"})), 2026).visible


def test_counterparty_credit_filter_uses_the_one_canonical_scale():
    """There is exactly one credit scale in this platform and it is CREDIT_ORDINAL."""
    import inspect

    source = inspect.getsource(oi)
    assert "CREDIT_ORDINAL" in source
    assert "contractual_rating_engine" in source

    weak = an_interest(counterparty_rating="B")
    assert not oi.viewer_wants(weak, ViewerFilter(min_counterparty_credit="A"), 2026).visible


# ── discovery must not disclose what it hides ─────────────────────────────────


def test_discover_returns_only_visible_rows_and_no_hidden_count():
    company = f"pub_{uuid.uuid4().hex[:6]}"
    seeker = ViewerProfile(company_id=f"seek_{uuid.uuid4().hex[:6]}", jurisdiction="NL",
                           credit_rating="A")

    oi.publish_interest(company, oi.PRODUCER, "u1", molecule="e-methanol",
                        target_cod_year=2030, jurisdiction="DE")
    oi.publish_interest(company, oi.PRODUCER, "u1", molecule="e-methanol",
                        target_cod_year=2030, jurisdiction="DE",
                        policy=VisibilityPolicy(denied_company_ids=frozenset({seeker.company_id})))

    results = oi.discover(seeker, ViewerFilter(molecules=frozenset({"e-methanol"})), 2026)
    mine = [r for r in results if r["company_id"] == company]
    assert len(mine) == 1

    # The result is a plain list. There is no envelope carrying a total, because a total
    # tells you how much you are not being shown.
    assert isinstance(results, list)


def test_discover_never_returns_the_publishers_visibility_rules():
    """Who a publisher has blocked is itself confidential."""
    company = f"pub_{uuid.uuid4().hex[:6]}"
    oi.publish_interest(company, oi.OFFTAKER, "u1", molecule="ammonia",
                        policy=VisibilityPolicy(denied_company_ids=frozenset({"rival_co"})))

    viewer = ViewerProfile(company_id=f"v_{uuid.uuid4().hex[:6]}", jurisdiction="NL",
                           credit_rating="A")
    for row in oi.discover(viewer, None, 2026):
        assert "visibility_json" not in row


def test_denial_reasons_are_never_part_of_a_discover_result():
    """Telling someone why they were excluded tells them there was something to be
    excluded from. Reasons are audit-only."""
    viewer = ViewerProfile(company_id=f"v_{uuid.uuid4().hex[:6]}", jurisdiction="NL",
                           credit_rating="A")
    for row in oi.discover(viewer, None, 2026):
        assert "reason" not in row
        assert "visible" not in row


# ── round trip ────────────────────────────────────────────────────────────────


def test_a_visibility_policy_survives_persistence_unchanged():
    policy = VisibilityPolicy(
        denied_company_ids=frozenset({"a", "b"}),
        allowed_jurisdictions=frozenset({"DE"}),
        min_credit_rating="BBB",
    )
    assert VisibilityPolicy.from_json(policy.to_json()) == policy


def test_an_empty_allowlist_survives_persistence_as_empty_not_absent():
    """frozenset() and None mean opposite things — nobody, versus no restriction."""
    nobody = VisibilityPolicy(allowed_company_ids=frozenset())
    assert VisibilityPolicy.from_json(nobody.to_json()).allowed_company_ids == frozenset()

    unrestricted = VisibilityPolicy()
    assert VisibilityPolicy.from_json(unrestricted.to_json()).allowed_company_ids is None


def test_an_interest_must_declare_a_valid_side():
    with pytest.raises(oi.InterestError):
        oi.publish_interest("co", "BOTH", "u1")
