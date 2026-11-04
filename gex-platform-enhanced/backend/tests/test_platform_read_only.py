"""
GEX staff read gates and evidence on every project, and do nothing else there.
==============================================================================
JML, 2026-11-03: "read-only". Before R0P, ABAC rule R0 made a platform admin
with no role on a project a GUEST, so every gate readout answered 403 for GEX
staff while `engine_view.persona_for` promised them the EXECUTIVE view.

Pinned here, both ways: an admin READ of GATE_EVALUATION / EVIDENCE is allowed;
every write, verification, export and share is not, and neither is any other
resource type (financial models, contracts, data rooms, activity). A non-admin
gains nothing.
"""
from __future__ import annotations

import pytest

from app.core.abac import (
    PLATFORM_READ_RESOURCE_TYPES,
    Action,
    ContextAttributes,
    Decision,
    ResourceAttributes,
    UserAttributes,
    evaluate_access,
)
from app.core.abac_middleware import ABACMiddleware

PID = "proj_TEST_platform_read_only"          # no registry profile: no role derivable
CTX = ContextAttributes(project_stakeholders={"owner_co"})


def _user(admin: bool) -> UserAttributes:
    return UserAttributes(user_id="u_gex", company_id="greenearthx",
                          actor_type_per_project={}, is_platform_admin=admin)


def _decide(admin: bool, action: Action, resource_type: str):
    resource = ResourceAttributes(project_id=PID, data_owner_company_id="owner_co",
                                  resource_type=resource_type)
    return evaluate_access(_user(admin), resource, action, CTX, phase=2)


def test_the_readable_set_is_gates_and_evidence_only():
    assert PLATFORM_READ_RESOURCE_TYPES == {"GATE_EVALUATION", "EVIDENCE"}


@pytest.mark.parametrize("resource_type", sorted(PLATFORM_READ_RESOURCE_TYPES))
def test_an_admin_reads_gates_and_evidence(resource_type):
    d = _decide(True, Action.READ, resource_type)
    assert d.decision == Decision.ALLOW
    assert d.rules_evaluated == ["R0P"]
    assert d.attributes_snapshot["is_platform_admin"] is True


@pytest.mark.parametrize("action", [Action.WRITE, Action.VERIFY, Action.DELETE,
                                    Action.EXPORT, Action.SHARE])
@pytest.mark.parametrize("resource_type", sorted(PLATFORM_READ_RESOURCE_TYPES))
def test_an_admin_still_cannot_write_verify_export_or_share(action, resource_type):
    d = _decide(True, action, resource_type)
    assert d.decision == Decision.DENY
    assert "R0P" not in d.rules_evaluated


@pytest.mark.parametrize("resource_type", ["FINANCIAL_MODEL", "CONTRACT", "DATA_ROOM",
                                           "AUDIT_ACTIVITY", "TIMELINE", "PERFORMANCE"])
def test_an_admin_does_not_read_the_parties_other_files(resource_type):
    d = _decide(True, Action.READ, resource_type)
    assert d.decision == Decision.DENY
    assert "R0P" not in d.rules_evaluated


def test_a_non_admin_gains_nothing():
    d = _decide(False, Action.READ, "GATE_EVALUATION")
    assert d.decision == Decision.DENY
    assert d.rules_evaluated == ["R0"]


@pytest.mark.parametrize("claim, expected", [(True, True), (1, True), (False, False),
                                             (0, False), (None, False)])
def test_the_flag_comes_from_the_token_and_defaults_closed(claim, expected):
    payload = {"user_id": "u", "company_id": "c", "is_platform_admin": claim}
    assert ABACMiddleware._user_from_payload(payload).is_platform_admin is expected
    assert ABACMiddleware._user_from_payload({"user_id": "u", "company_id": "c"}).is_platform_admin is False
