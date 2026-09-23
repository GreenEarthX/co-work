"""
The CISO workspace serves invented data. It has to say so.
===========================================================
`routes_ciso.py` returns fabricated user rosters (names, S&P credit ratings,
ISO 27001 certifications, KYC statuses), invented information barriers and a
generated access-event feed. None of it was observed.

Seeding a pre-production platform is deliberate and useful. The failure mode is
seeded data that cannot be told apart from observed data — 125 fabricated
`bankability_evidence` rows once carried status VERIFIED and fed a risk
classification indistinguishable from a real one. So every fabricated response
from this module carries `provenance: "SEED"`, and these tests keep it that way.

Note what is NOT stamped: `/policy-matrix` returns the gate-visibility model —
configuration describing how the platform works, not a claim about a client.
Labelling real data as seeded is also a lie, just a less dangerous one.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import routes_ciso

SEEDED_ENDPOINTS = [
    "/users",
    "/overview",
    "/access-log",
    "/compliance",
    "/barriers",
]


@pytest.fixture(scope="module")
def client():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(routes_ciso.router, prefix="/api/v1/ciso")
    return TestClient(app)


@pytest.mark.parametrize("path", SEEDED_ENDPOINTS)
def test_every_fabricated_endpoint_declares_itself_seeded(client, path):
    body = client.get(f"/api/v1/ciso{path}").json()
    assert body.get("provenance") == routes_ciso.SEED_PROVENANCE, (
        f"{path} returns invented data without saying so. A consumer cannot "
        "distinguish it from an observation."
    )
    assert "not been observed" in body.get("provenance_note", "")


def test_the_roster_does_not_claim_verified_kyc(client):
    """These people do not exist, so nobody ran a KYC check on them — and
    `requires_kyc:VERIFIED` is a real gate elsewhere in the platform."""
    users = client.get("/api/v1/ciso/users").json()["users"]
    assert users, "no seeded users returned — the fixture stopped exercising this"
    for user in users:
        assert user["kyc_status"] == routes_ciso.SEED_PROVENANCE, (
            f"{user['user_id']} claims kyc_status={user['kyc_status']!r}")
        assert user["provenance"] == routes_ciso.SEED_PROVENANCE
        # The demo still shows the shape it was written to show.
        assert "kyc_status_seeded_as" in user


def test_the_stamp_is_applied_where_the_data_is_served(client):
    """Not typed into each literal.

    A roster record added later must inherit the stamp. This asserts the
    mechanism — `_get_company_data` marks what it returns — rather than the
    current contents, so adding a user cannot quietly ship an unmarked one.
    """
    raw = routes_ciso._COMPANY_USERS["bp_global_energy"][0]
    assert "provenance" not in raw, (
        "the literal now carries its own provenance — if the stamp moved into "
        "the data, a new record can be added without it")
    _, served, _ = routes_ciso._get_company_data("bp_global_energy")
    assert served[0]["provenance"] == routes_ciso.SEED_PROVENANCE


def test_real_configuration_is_not_mislabelled_as_seeded(client):
    """`/policy-matrix` is the gate-visibility model, not invented observations."""
    body = client.get("/api/v1/ciso/policy-matrix").json()
    assert "provenance" not in body, (
        "the policy matrix is configuration, not seeded data — marking it SEED "
        "would teach readers to ignore the marker")
