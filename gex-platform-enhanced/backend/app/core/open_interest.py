"""
Open interest — the producer/offtaker discovery board.

Long-term offtake matching is the platform's tenet, so the first thing a client needs is
to see who is looking for what. An open interest is a PRE-CONTRACTUAL signal: "I expect
to have 50kt/yr of e-methanol from 2030 and I am looking for a 12-year offtake." It is
not an agreement and must never be confused with one — see
`vocabulary.COMMITMENT_OBJECT_ROLES`. When terms are agreed it is promoted to an
`OfftakeContract`, which is the canonical demand-side object.

THERE ARE TWO FILTERS AND ONLY ONE OF THEM IS SECURITY

  VisibilityPolicy  — the PUBLISHER's rule: who may see MY interest.
                      This is confidentiality. Getting it wrong leaks that a named
                      company is short 50kt, which is commercially material.

  ViewerFilter      — the VIEWER's preference: what I want to see.
                      This is convenience. It can only ever hide more, never reveal.

Visibility is the INTERSECTION: the publisher must permit the viewer, and the viewer's
own filter must not exclude the publisher. A system that implements only the viewer's
filter shows everything to everyone who did not think to exclude it. That is the failure
mode this module is shaped to prevent.

THREE RULES

1. Fail closed. Any rule that cannot be evaluated — unknown viewer, missing credit
   rating against a minimum — denies. Absence of information is never permission.
2. Never leak a hidden row's existence. `discover()` returns visible rows and nothing
   else. No total count, no "2 results hidden". A count is a disclosure.
3. Denial reasons are for the audit log, never for the viewer. Telling someone why they
   were excluded tells them there was something to be excluded from.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.core.contractual_rating_engine import CREDIT_ORDINAL
from app.core.db_backend import capital_connection

PRODUCER = "PRODUCER"
OFFTAKER = "OFFTAKER"
SIDES = (PRODUCER, OFFTAKER)

DRAFT = "DRAFT"
OPEN = "OPEN"
MATCHED = "MATCHED"
WITHDRAWN = "WITHDRAWN"
INTEREST_STATES = (DRAFT, OPEN, MATCHED, WITHDRAWN)


class InterestError(Exception):
    """Refused for a domain reason, not a bug."""


# ── the decision types ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ViewerProfile:
    """Who is looking. Derived server-side from the authenticated identity — never
    supplied by the client, or the whole model is decorative."""

    company_id: Optional[str]
    jurisdiction: Optional[str] = None
    credit_rating: Optional[str] = None  # S&P scale, as stored on auth_users
    is_platform_admin: bool = False


@dataclass(frozen=True)
class VisibilityPolicy:
    """The publisher's rule. Who may see MY interest."""

    denied_company_ids: frozenset = field(default_factory=frozenset)
    allowed_company_ids: Optional[frozenset] = None  # None = no allowlist in force
    denied_jurisdictions: frozenset = field(default_factory=frozenset)
    allowed_jurisdictions: Optional[frozenset] = None
    min_credit_rating: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "denied_company_ids": sorted(self.denied_company_ids),
                "allowed_company_ids": (
                    sorted(self.allowed_company_ids)
                    if self.allowed_company_ids is not None
                    else None
                ),
                "denied_jurisdictions": sorted(self.denied_jurisdictions),
                "allowed_jurisdictions": (
                    sorted(self.allowed_jurisdictions)
                    if self.allowed_jurisdictions is not None
                    else None
                ),
                "min_credit_rating": self.min_credit_rating,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def from_json(blob: str) -> "VisibilityPolicy":
        d = json.loads(blob) if blob else {}
        allowed_c = d.get("allowed_company_ids")
        allowed_j = d.get("allowed_jurisdictions")
        return VisibilityPolicy(
            denied_company_ids=frozenset(d.get("denied_company_ids", ())),
            allowed_company_ids=frozenset(allowed_c) if allowed_c is not None else None,
            denied_jurisdictions=frozenset(d.get("denied_jurisdictions", ())),
            allowed_jurisdictions=frozenset(allowed_j) if allowed_j is not None else None,
            min_credit_rating=d.get("min_credit_rating"),
        )


@dataclass(frozen=True)
class ViewerFilter:
    """The viewer's preference. Convenience only — can hide, can never reveal."""

    molecules: Optional[frozenset] = None
    jurisdictions: Optional[frozenset] = None
    sides: Optional[frozenset] = None
    min_counterparty_credit: Optional[str] = None
    max_years_to_cod: Optional[int] = None  # the "t minus x" filter


@dataclass(frozen=True)
class Decision:
    visible: bool
    reason: str  # AUDIT ONLY. Never render this to the viewer.


def _ordinal(rating: Optional[str]) -> Optional[int]:
    """Credit ordinal from the single canonical scale. There is no second scale."""
    if rating is None:
        return None
    value = CREDIT_ORDINAL.get(rating)
    if value is None or value == 0:  # 0 is "NR" — not a rating, an absence
        return None
    return value


# ── the predicate ─────────────────────────────────────────────────────────────


def publisher_permits(interest: dict, policy: VisibilityPolicy,
                      viewer: ViewerProfile) -> Decision:
    """Does the PUBLISHER allow this viewer to see this interest? Security-bearing."""
    if not viewer.company_id:
        return Decision(False, "no_viewer_identity")

    if viewer.company_id == interest["company_id"]:
        return Decision(True, "own_interest")

    # A platform admin does NOT bypass a publisher's confidentiality rule. The product
    # promise is that you control who sees your position; an admin backdoor would make
    # that promise false, and it is the first thing a counterparty will ask about.
    # Support access, if ever needed, must be a separate disclosed mechanism.
    if interest["state"] != OPEN:
        return Decision(False, "interest_not_open")

    if policy.allowed_company_ids is not None:
        if viewer.company_id not in policy.allowed_company_ids:
            return Decision(False, "not_on_publisher_allowlist")

    if viewer.company_id in policy.denied_company_ids:
        return Decision(False, "publisher_denied_company")

    if policy.allowed_jurisdictions is not None:
        if not viewer.jurisdiction:
            return Decision(False, "viewer_jurisdiction_unknown")  # fail closed
        if viewer.jurisdiction not in policy.allowed_jurisdictions:
            return Decision(False, "jurisdiction_not_allowed")

    if viewer.jurisdiction and viewer.jurisdiction in policy.denied_jurisdictions:
        return Decision(False, "publisher_denied_jurisdiction")

    if policy.min_credit_rating is not None:
        required = _ordinal(policy.min_credit_rating)
        actual = _ordinal(viewer.credit_rating)
        if actual is None:
            return Decision(False, "viewer_credit_unknown")  # fail closed
        if required is not None and actual < required:
            return Decision(False, "viewer_below_min_credit")

    return Decision(True, "permitted")


def viewer_wants(interest: dict, vfilter: ViewerFilter,
                 as_of_year: int) -> Decision:
    """Does the VIEWER want to see this? Preference only — hides, never reveals."""
    if vfilter.molecules is not None and interest.get("molecule") not in vfilter.molecules:
        return Decision(False, "molecule_filtered")
    if vfilter.sides is not None and interest["side"] not in vfilter.sides:
        return Decision(False, "side_filtered")
    if vfilter.jurisdictions is not None:
        if interest.get("jurisdiction") not in vfilter.jurisdictions:
            return Decision(False, "jurisdiction_filtered")

    if vfilter.min_counterparty_credit is not None:
        required = _ordinal(vfilter.min_counterparty_credit)
        actual = _ordinal(interest.get("counterparty_rating"))
        if actual is None:
            return Decision(False, "counterparty_credit_unknown")
        if required is not None and actual < required:
            return Decision(False, "counterparty_below_min_credit")

    if vfilter.max_years_to_cod is not None:
        target = interest.get("target_cod_year")
        if target is None:
            return Decision(False, "cod_unknown")
        if target - as_of_year > vfilter.max_years_to_cod:
            return Decision(False, "cod_too_far_out")

    return Decision(True, "wanted")


def is_visible(interest: dict, policy: VisibilityPolicy, viewer: ViewerProfile,
               vfilter: Optional[ViewerFilter], as_of_year: int) -> Decision:
    """Visibility is the intersection. Publisher first — it is the security half, and
    evaluating it first means a viewer's preferences can never widen what they see."""
    permitted = publisher_permits(interest, policy, viewer)
    if not permitted.visible:
        return permitted
    if vfilter is None:
        return permitted
    return viewer_wants(interest, vfilter, as_of_year)


# ── persistence ───────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


DDL = (
    """
    CREATE TABLE IF NOT EXISTS open_interests (
        interest_id          TEXT PRIMARY KEY,
        company_id           TEXT NOT NULL,
        side                 TEXT NOT NULL,
        molecule             TEXT,
        volume_tpa           REAL,
        target_cod_year      INTEGER,
        term_years_min       INTEGER,
        jurisdiction         TEXT,
        counterparty_rating  TEXT,
        indicative_price_eur_t REAL,
        state                TEXT NOT NULL DEFAULT 'DRAFT',
        visibility_json      TEXT NOT NULL DEFAULT '{}',
        note                 TEXT,
        created_by           TEXT NOT NULL,
        created_at           TEXT NOT NULL,
        updated_at           TEXT NOT NULL
    )
    """,
)


def init_open_interest_db() -> None:
    conn = capital_connection()
    try:
        for statement in DDL:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def publish_interest(company_id: str, side: str, created_by: str,
                     policy: Optional[VisibilityPolicy] = None,
                     state: str = OPEN, **fields) -> dict:
    if side not in SIDES:
        raise InterestError(f"side must be one of {SIDES}")
    if state not in INTEREST_STATES:
        raise InterestError(f"state must be one of {INTEREST_STATES}")

    now = _now()
    row = {
        "interest_id": f"oi_{uuid.uuid4().hex[:12]}",
        "company_id": company_id,
        "side": side,
        "molecule": fields.get("molecule"),
        "volume_tpa": fields.get("volume_tpa"),
        "target_cod_year": fields.get("target_cod_year"),
        "term_years_min": fields.get("term_years_min"),
        "jurisdiction": fields.get("jurisdiction"),
        "counterparty_rating": fields.get("counterparty_rating"),
        "indicative_price_eur_t": fields.get("indicative_price_eur_t"),
        "state": state,
        "visibility_json": (policy or VisibilityPolicy()).to_json(),
        "note": fields.get("note"),
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    conn = capital_connection()
    try:
        conn.execute(
            "INSERT INTO open_interests (interest_id, company_id, side, molecule,"
            " volume_tpa, target_cod_year, term_years_min, jurisdiction,"
            " counterparty_rating, indicative_price_eur_t, state, visibility_json, note,"
            " created_by, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(row.values()),
        )
        conn.commit()
    finally:
        conn.close()
    return row


def _all_interests() -> list[dict]:
    conn = capital_connection()
    try:
        cur = conn.execute("SELECT * FROM open_interests")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def discover(viewer: ViewerProfile, vfilter: Optional[ViewerFilter] = None,
             as_of_year: Optional[int] = None) -> list[dict]:
    """Interests this viewer may see.

    Returns visible rows and NOTHING ELSE — no total, no hidden count. A count of what
    you cannot see is a disclosure that it exists.
    """
    year = as_of_year if as_of_year is not None else datetime.now(timezone.utc).year
    out = []
    for interest in _all_interests():
        policy = VisibilityPolicy.from_json(interest.get("visibility_json") or "{}")
        if is_visible(interest, policy, viewer, vfilter, year).visible:
            # The publisher's own rules are not the viewer's business either.
            shown = {k: val for k, val in interest.items() if k != "visibility_json"}
            out.append(shown)
    return out
