"""
The platform had no password policy at all until 2026-09-20.

Measured that day: neither `auth.py` nor `routes_auth.py` checked length or
content, so any string was accepted — including on `is_platform_admin`
accounts, which `request_tenant.py` maps to `PLATFORM_ADMIN`, disabling tenant
isolation for the whole connection.

The tests that matter here are the refusals, and one structural one: the
policy must be enforced in `update_password` itself, because that is what an
operator calls from a shell when provisioning an account — the path with no
human reading a form's validation message.

Deliberately no composition rules are tested, because none exist: NIST
SP 800-63B dropped them, and a test asserting "must contain a symbol" would
pin the wrong behaviour in place.
"""
from __future__ import annotations

import pytest

from app.core.password_policy import (
    MIN_LENGTH,
    MIN_LENGTH_PLATFORM_ADMIN,
    PasswordPolicyError,
    describe_policy,
    validate_password,
)

GOOD = "tangerine harbour lantern"          # long, unrelated words, no padding
GOOD_ADMIN = "tangerine harbour lantern drift"


def test_a_long_passphrase_is_accepted():
    validate_password(GOOD, email="someone@example.com")


def test_too_short_is_refused():
    with pytest.raises(PasswordPolicyError, match=f"at least {MIN_LENGTH}"):
        validate_password("short1234", email="someone@example.com")


def test_an_admin_needs_more_length_than_the_general_minimum():
    """The flag grants cross-tenant visibility; the bar is higher on purpose."""
    borderline = "a" * (MIN_LENGTH_PLATFORM_ADMIN - 1)
    borderline = "quiet lantern"            # 13 chars: fine generally, not for admin
    assert MIN_LENGTH <= len(borderline) < MIN_LENGTH_PLATFORM_ADMIN

    validate_password(borderline, email="someone@example.com")
    with pytest.raises(PasswordPolicyError, match="every tenant"):
        validate_password(borderline, email="someone@example.com",
                          is_platform_admin=True)
    validate_password(GOOD_ADMIN, email="someone@example.com",
                      is_platform_admin=True)


@pytest.mark.parametrize("weak", [
    "password1234", "Password1234", "administrator", "changeme1234",
    "greenearthx", "greenearthx2026", "greenearthx!!",
])
def test_common_and_deployment_specific_words_are_refused(weak):
    """An attacker guessing at GEX starts with 'greenearthx', not with a
    dictionary. Trailing years and punctuation padding do not rescue it."""
    with pytest.raises(PasswordPolicyError):
        validate_password(weak, email="someone@example.com")


@pytest.mark.parametrize("trivial", [
    "aaaaaaaaaaaaaa", "ababababababab", "qwertyuiop12", "0123456789ab",
    "abcdefghijkl",
])
def test_trivial_strings_are_refused_however_long(trivial):
    assert len(trivial) >= MIN_LENGTH
    with pytest.raises(PasswordPolicyError):
        validate_password(trivial, email="someone@example.com")


def test_a_password_may_not_contain_the_account_it_belongs_to():
    with pytest.raises(PasswordPolicyError, match="name or email"):
        validate_password("marwen is my name here",
                          email="t-marwenc@greenearthx.com",
                          user_name="Marwen Chaabouni")
    with pytest.raises(PasswordPolicyError, match="name or email"):
        validate_password("chaabouni forever ok",
                          email="t-marwenc@greenearthx.com",
                          user_name="Marwen Chaabouni")


def test_an_enormous_password_is_refused_rather_than_hashed():
    with pytest.raises(PasswordPolicyError, match="at most"):
        validate_password("x" * 5000, email="someone@example.com")


def test_an_empty_password_is_refused():
    with pytest.raises(PasswordPolicyError):
        validate_password("", email="someone@example.com")


def test_the_policy_can_describe_itself_without_leaking_a_rule_set():
    described = describe_policy(is_platform_admin=True)
    assert described["min_length"] == MIN_LENGTH_PLATFORM_ADMIN
    assert described["composition_rules"] is False


# ── enforcement, not just the predicate ──────────────────────────────────────

def test_update_password_enforces_the_policy(isolated_store):
    """
    The structural test. `update_password` is what an operator calls from a
    shell; a policy enforced only in the HTTP route would not cover it.
    """
    from app.core import auth

    auth.init_auth_db()
    conn = auth._get_conn()
    try:
        conn.execute(
            # account_state ACTIVE on purpose: credentials alone are not trust
            # here, and a PENDING account is refused at login however good the
            # password is. That is the vetting gate, not the policy.
            "INSERT INTO auth_users (user_id, email, password_hash, company_id, "
            "company_name, company_type, business_function, user_name, "
            "is_platform_admin, account_state) "
            "VALUES (?,?,?,?,?,?,?,?,1,'ACTIVE')",
            ("u_admin", "boss@example.com", "x", "c1", "Co", "PRODUCER",
             "EXECUTIVE", "The Boss"))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(PasswordPolicyError):
        auth.update_password("boss@example.com", "short")

    # The admin minimum is applied because the row says is_platform_admin=1 —
    # the caller does not have to remember to say so.
    with pytest.raises(PasswordPolicyError, match="every tenant"):
        auth.update_password("boss@example.com", "quiet lantern")

    auth.update_password("boss@example.com", GOOD_ADMIN)
    assert auth.authenticate_user("boss@example.com", GOOD_ADMIN) is not None
