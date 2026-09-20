"""
Password policy — the one place that decides whether a password is acceptable.

WHY THIS EXISTS
---------------
Measured 2026-09-20: there was **no policy at all**. Neither `auth.py` nor
`routes_auth.py` checked length, content or anything else, so the platform
accepted any string — including on `is_platform_admin` accounts, which carry
cross-tenant visibility over every customer's data.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
No composition rules. No "must contain an uppercase, a digit and a symbol".
NIST SP 800-63B dropped those because they produce predictable substitutions
(`Password1!`) that are weaker than the length they cost, and because they
push people towards reuse. Length plus a blocklist is what actually helps, so
that is what this enforces:

  1. **Length.** 12 characters, and 16 for a platform administrator. The
     higher bar for admins is not cosmetic: that flag maps to `PLATFORM_ADMIN`
     in `request_tenant.py`, which disables tenant isolation for the whole
     connection.
  2. **A blocklist**, checked case-insensitively, of common passwords and of
     terms specific to this deployment — an attacker guessing at GEX starts
     with "greenearthx", not with "correct horse".
  3. **Context.** A password must not contain the account's own address or
     name, which is the first thing anyone tries.
  4. **Triviality.** One repeated character, or a straight run off the
     keyboard, fails regardless of length.

An upper bound exists too. Nothing here truncates a passphrase — the limit is
only there so an enormous input cannot be used to burn CPU in the hash.

THE ONE EXEMPTION, STATED RATHER THAN HIDDEN
--------------------------------------------
Demo-user seeding (`auth._seed_user`) hashes `DEMO_PASSWORD` directly and does
not come through here, so the shared `demo1234` still works. That is
deliberate — the demo accounts exist to be logged into from a README — and it
is safe only because `GEX_SEED_DEMO_USERS=0` disables the whole seed set in
production. If that variable is ever not set in a real deployment, the policy
below is irrelevant: there are seventeen accounts with a known password.

USAGE

    from app.core.password_policy import validate_password, PasswordPolicyError
    validate_password(pw, email=email, is_platform_admin=False)

Raises `PasswordPolicyError` with a message meant to be shown to the person
choosing the password: it says what is wrong, never what would be right.
"""
from __future__ import annotations

import re
from typing import Optional

MIN_LENGTH = 12
MIN_LENGTH_PLATFORM_ADMIN = 16
MAX_LENGTH = 1024


class PasswordPolicyError(ValueError):
    """The password is not acceptable. The message is safe to show a user."""


# Deliberately short and deployment-specific rather than a 100k-entry list:
# the point is to catch the guesses a human actually makes here, not to
# reimplement haveibeenpwned. A real breach-corpus check belongs behind a
# service call and is a separate decision.
_COMMON = frozenset({
    "password", "passw0rd", "p@ssword", "letmein", "welcome", "monkey",
    "dragon", "qwerty", "azerty", "iloveyou", "admin", "administrator",
    "changeme", "default", "secret", "football", "baseball", "sunshine",
    "princess", "trustno1", "master", "shadow", "superman", "michael",
    "abc123", "123456", "12345678", "123456789", "1234567890",
    "qwerty123", "password1", "password123", "admin123", "root", "toor",
    # Deployment-specific: the first things anyone would try against GEX.
    "greenearthx", "greenearth", "gexplatform", "gex", "etfuels",
    "hydrogen", "methanol", "ammonia",
})

_KEYBOARD_RUNS = ("qwertyuiop", "asdfghjkl", "zxcvbnm", "azertyuiop",
                  "qwertzuiop", "0123456789", "abcdefghijklmnopqrstuvwxyz")

_WORD = re.compile(r"[a-z0-9]+")


def _strip_trailing_digits(value: str) -> str:
    """`greenearthx2026` is `greenearthx` with a year stuck on it."""
    return re.sub(r"\d+$", "", value)


def _contains_run(lowered: str, minimum: int = 6) -> bool:
    for run in _KEYBOARD_RUNS:
        for start in range(len(run) - minimum + 1):
            chunk = run[start:start + minimum]
            if chunk in lowered or chunk[::-1] in lowered:
                return True
    return False


def _context_terms(email: Optional[str], user_name: Optional[str]) -> set[str]:
    terms: set[str] = set()
    if email:
        local, _, domain = email.lower().partition("@")
        terms.update(t for t in _WORD.findall(local) if len(t) >= 4)
        # The domain label, not the TLD: "greenearthx" from
        # "someone@greenearthx.com".
        if domain:
            labels = domain.split(".")
            terms.update(t for t in labels[:-1] if len(t) >= 4)
    if user_name:
        terms.update(t for t in _WORD.findall(user_name.lower()) if len(t) >= 4)
    return terms


def validate_password(password: str, *, email: Optional[str] = None,
                      user_name: Optional[str] = None,
                      is_platform_admin: bool = False) -> None:
    """Raise `PasswordPolicyError` if `password` may not be used. Silent on OK."""
    if not isinstance(password, str) or not password:
        raise PasswordPolicyError("A password is required.")

    minimum = MIN_LENGTH_PLATFORM_ADMIN if is_platform_admin else MIN_LENGTH
    if len(password) < minimum:
        who = ("Administrator accounts can read every tenant's data, so they "
               "need a longer one. ") if is_platform_admin else ""
        raise PasswordPolicyError(
            f"Password must be at least {minimum} characters. {who}"
            "Length matters more than punctuation — a short phrase of "
            "unrelated words beats a mangled single word.")

    if len(password) > MAX_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_LENGTH} characters.")

    lowered = password.lower()

    if len(set(password)) < 5:
        raise PasswordPolicyError(
            "Password repeats too few distinct characters.")

    if _contains_run(lowered):
        raise PasswordPolicyError(
            "Password contains a straight run of keys or digits.")

    stripped = _strip_trailing_digits(lowered)
    if lowered in _COMMON or stripped in _COMMON:
        raise PasswordPolicyError(
            "That password is one of the most commonly used ones.")

    # A common word is also unacceptable when it IS the password with padding
    # around it — "greenearthx!!" adds nothing an attacker would not try.
    for common in _COMMON:
        if len(common) >= 6 and lowered.strip("!@#$%^&*()-_=+.,").rstrip("0123456789") == common:
            raise PasswordPolicyError(
                "That password is a common word with padding around it.")

    for term in _context_terms(email, user_name):
        if term in lowered:
            raise PasswordPolicyError(
                "Password must not contain your name or email address.")


def describe_policy(is_platform_admin: bool = False) -> dict[str, object]:
    """For a UI that wants to state the rule before the person types."""
    return {
        "min_length": MIN_LENGTH_PLATFORM_ADMIN if is_platform_admin else MIN_LENGTH,
        "max_length": MAX_LENGTH,
        "composition_rules": False,
        "note": ("Length is what matters. Several unrelated words are stronger "
                 "and easier to remember than a short mangled one."),
    }
