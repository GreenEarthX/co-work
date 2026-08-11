"""
Route-level identity guarantees for open interest and billing.

`app.core.open_interest` decides visibility correctly given a ViewerProfile. That is worth
nothing if the ViewerProfile can be supplied by the caller — you would simply claim to be
whoever is permitted to look. These tests guard the seam between the request and the
predicate, which is where the whole model can be quietly voided by adding one field to a
pydantic model.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.api.v1 import routes_client_billing as rcb
from app.api.v1 import routes_open_interest as roi
from app.core import open_interest as oi
from app.core.domain_authorization import DOMAIN_PREFIXES, check_domain_access, domain_for_path


class FakeState:
    def __init__(self, payload):
        self.user_payload = payload
        self.auth_user_payload = payload


class FakeRequest:
    def __init__(self, payload):
        self.state = FakeState(payload)


# ── identity is derived, never supplied ───────────────────────────────────────


# Fields that assert WHO THE CALLER IS. These must never be accepted from a request body.
# Note what is deliberately absent: `jurisdiction` and `counterparty_rating` on a published
# interest describe the INTEREST (where the project is, who the counterparty is), not the
# caller, and are legitimate body fields. A publisher overstating `counterparty_rating` to
# appear in more searches is a data-quality problem, not an authorization bypass — a
# different problem needing a different fix.
IDENTITY_FIELDS = {
    "company_id", "client_id", "counterparty_company_id", "is_platform_admin",
    "viewer", "viewer_company", "viewer_credit_rating", "viewer_jurisdiction",
    "accepted_by_user_id", "user_id", "created_by", "published_by",
}


def _model_fields(module, model_name: str) -> set[str]:
    tree = ast.parse(Path(inspect.getfile(module)).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == model_name:
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError(f"{model_name} not found in {module.__name__}")


def test_publishing_an_interest_takes_no_identity_from_the_body():
    """The company an interest belongs to is the caller's. If this model ever grows a
    `company_id`, anyone can publish as anyone."""
    fields = _model_fields(roi, "PublishInterestInput")
    leaked = fields & IDENTITY_FIELDS
    assert not leaked, f"identity fields accepted from the request body: {leaked}"


def test_the_visibility_policy_model_carries_no_viewer_identity():
    """A publisher declares who MAY see. It must not be able to declare who IS looking."""
    fields = _model_fields(roi, "VisibilityInput")
    assert "viewer" not in fields
    assert not (fields & {"credit_rating", "jurisdiction", "company_id"})


@pytest.mark.parametrize("model", ["AcceptTermsInput", "RecordPaymentInput", "IssueInvoiceInput"])
def test_billing_models_take_no_actor_identity_from_the_body(model):
    leaked = _model_fields(rcb, model) & IDENTITY_FIELDS
    assert not leaked, f"{model} accepts actor identity from the body: {leaked}"


def test_viewer_profile_is_built_only_from_the_verified_payload():
    source = inspect.getsource(roi.viewer_from_request)
    assert "payload_from_request" in source
    for smuggled in (".query_params", ".body", "body.", ".headers.get(\"x-company"):
        assert smuggled not in source, f"viewer identity read from {smuggled}"


def test_confidentiality_identity_is_not_the_tenancy_identity():
    """The bug this pins was live until 2026-08-11.

    `company_from_payload` returns the PLATFORM_ADMIN sentinel for staff, because it
    answers "which tenant's rows may this request read?". Confidentiality asks who is
    actually looking. Using the tenancy answer here replaced a real company with a
    sentinel that matches no publisher rule — so staff saw every interest, including
    those that had explicitly blocked them.
    """
    from app.core.request_tenant import PLATFORM_ADMIN, company_from_payload

    payload = {"company_id": "greenearthx", "is_platform_admin": True}
    assert company_from_payload(payload) == PLATFORM_ADMIN  # correct for tenancy

    viewer = roi.viewer_from_request(FakeRequest(payload))
    assert viewer.company_id == "greenearthx"  # and wrong for confidentiality
    assert viewer.company_id != PLATFORM_ADMIN


def test_an_unauthenticated_request_yields_a_viewer_that_sees_nothing():
    viewer = roi.viewer_from_request(FakeRequest(None))
    assert viewer.company_id is None

    interest = {
        "interest_id": "oi_x", "company_id": "someone", "side": oi.PRODUCER,
        "state": oi.OPEN, "molecule": "e-methanol",
    }
    assert not oi.publisher_permits(interest, oi.VisibilityPolicy(), viewer).visible


def test_a_payload_without_a_company_yields_a_viewer_that_sees_nothing():
    viewer = roi.viewer_from_request(FakeRequest({"sub": "u1"}))
    assert viewer.company_id is None


def test_the_admin_flag_is_carried_but_still_does_not_bypass_confidentiality():
    """Domain authorization lets an admin WRITE anywhere. Per-interest confidentiality is
    a different decision and the admin does not bypass it — confirmed 2026-08-11."""
    viewer = roi.viewer_from_request(
        FakeRequest({"company_id": "greenearthx", "is_platform_admin": True})
    )
    assert viewer.is_platform_admin is True

    interest = {
        "interest_id": "oi_y", "company_id": "producer_co", "side": oi.PRODUCER,
        "state": oi.OPEN,
    }
    policy = oi.VisibilityPolicy(denied_company_ids=frozenset({"greenearthx"}))
    assert not oi.publisher_permits(interest, policy, viewer).visible


# ── domain registration ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api/v1/open-interest", "marketplace"),
        ("/api/v1/billing/terms", "platform"),
        ("/api/v1/billing/clients/acme/invoice", "platform"),
    ],
)
def test_new_routes_are_mapped_to_a_business_domain(path, expected):
    """An unmapped path fails closed on write. Registration is mandatory, not tidiness."""
    assert domain_for_path(path) == expected


def test_an_unmapped_sibling_path_would_be_refused():
    """Negative control: proves the mapping above is doing the work, not a permissive
    default somewhere else."""
    allowed, _domain, reason = check_domain_access(
        {"business_function": "COMMERCIAL"}, "/api/v1/open-interest-unmapped", "POST"
    )
    assert allowed is False
    assert "not mapped to a business domain" in reason


def test_both_prefixes_are_declared_exactly_once():
    for prefix in ("/api/v1/billing", "/api/v1/open-interest"):
        assert list(DOMAIN_PREFIXES).count(prefix) == 1


# ── the app still builds with both routers attached ───────────────────────────


def test_the_application_imports_with_the_new_routers_registered():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/open-interest" in paths
    assert "/api/v1/billing/terms" in paths
    assert "/api/v1/billing/invoices/{invoice_id}/payment" in paths
