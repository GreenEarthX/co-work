"""
GEX Adversarial Reviews
=======================
Stores structured challenge reviews raised by adversarial agents or humans
acting in adversarial-agent mode.

This module is platform-local by design. It does not call gex_pf_engine.
It persists review state in the platform SQLite DB and emits immutable
audit events into the existing event store.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.core.event_store import append_event, init_event_store
from app.core.config import settings

logger = logging.getLogger("gex.adversarial_reviews")

_DB_PATH = settings.SQLITE_DB_PATH


class ReviewStatus(str, Enum):
    OPEN = "OPEN"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    WAIVED = "WAIVED"
    CLOSED = "CLOSED"


class FinalStance(str, Enum):
    PROCEED = "PROCEED"
    PROCEED_WITH_CAUTION = "PROCEED_WITH_CAUTION"
    ESCALATE_INTERNALLY = "ESCALATE_INTERNALLY"
    STOP = "STOP"


class FindingKind(str, Enum):
    FALSE_PREMISE = "FALSE_PREMISE"
    KNOWLEDGE_GAP = "KNOWLEDGE_GAP"
    MISUNDERSTOOD_TASK = "MISUNDERSTOOD_TASK"
    UX_WEAKNESS = "UX_WEAKNESS"
    SEQUENCING_ERROR = "SEQUENCING_ERROR"
    LOGIC_FLAW = "LOGIC_FLAW"
    TRUST_PROBLEM = "TRUST_PROBLEM"
    COOPERATION_BREAKDOWN = "COOPERATION_BREAKDOWN"
    HANDOFF_FAILURE = "HANDOFF_FAILURE"


class FindingClassification(str, Enum):
    UNCLEAR = "UNCLEAR"
    MISSING = "MISSING"
    MISLEADING = "MISLEADING"
    STRUCTURALLY_WRONG = "STRUCTURALLY_WRONG"


class FindingSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class HandoffStatus(str, Enum):
    OPEN = "OPEN"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CLOSED = "CLOSED"


class AdversarialEventType(str, Enum):
    REVIEW_CREATED = "adversarial.review_created"
    FINDING_ADDED = "adversarial.finding_added"
    HANDOFF_CREATED = "adversarial.handoff_created"
    STATUS_CHANGED = "adversarial.review_status_changed"


PROMPT_PRESETS: list[dict] = [
    {
        "id": "preset_oft_ham_emeoh_l1",
        "prompt_card_id": "OFT-HAM-EMEOH-L1",
        "agent_id": "OFT-HAM-EMEOH-L1",
        "employee_name": "Lars Becker",
        "actor_type": "OFFTAKER",
        "category": "Offtaker",
        "subtype": "e-Methanol",
        "sophistication": 1,
        "tone": "practical, skeptical",
        "trust_trigger": "Visible distinction between available, certifiable, claimable, and financeable",
        "cooperation_priority": "Unify procurement, logistics, compliance, treasury, and operations before commitment",
        "description": "Hamburg procurement operator testing whether supply is operationally firm.",
    },
    {
        "id": "preset_oft_ham_emeoh_l2",
        "prompt_card_id": "OFT-HAM-EMEOH-L2",
        "agent_id": "OFT-HAM-EMEOH-L2",
        "employee_name": "Katrin Seidel",
        "actor_type": "OFFTAKER",
        "category": "Offtaker",
        "subtype": "e-Methanol",
        "sophistication": 2,
        "tone": "practical, skeptical",
        "trust_trigger": "Commercial structure made visible instead of hidden behind sustainability language",
        "cooperation_priority": "Unify procurement, logistics, compliance, treasury, and operations before commitment",
        "description": "Cross-functional maritime sourcing lead looking for milestone-driven practicality.",
    },
    {
        "id": "preset_oft_ham_emeoh_l3",
        "prompt_card_id": "OFT-HAM-EMEOH-L3",
        "agent_id": "OFT-HAM-EMEOH-L3",
        "employee_name": "Henrik Vogt",
        "actor_type": "OFFTAKER",
        "category": "Offtaker",
        "subtype": "e-Methanol",
        "sophistication": 3,
        "tone": "evidence-led, skeptical",
        "trust_trigger": "Audit-defensible separation of delivery, claimability, and counterparty evidence",
        "cooperation_priority": "Unify procurement, logistics, compliance, treasury, and operations before commitment",
        "description": "Structured supply specialist probing evidence quality and downstream claim risk.",
    },
    {
        "id": "preset_bank_layered_l2",
        "prompt_card_id": "BNK-LAYERED-CAPEX-L2",
        "agent_id": "BNK-LAYERED-CAPEX-L2",
        "employee_name": "Sophie Martin",
        "actor_type": "COMMERCIAL_BANKER",
        "category": "Bank",
        "subtype": "Project Finance",
        "sophistication": 2,
        "tone": "direct, credit-minded",
        "trust_trigger": "Explicit separation of evidence quality, deal blockers, and financing assumptions",
        "cooperation_priority": "Keep origination, credit, insurance, IE, and treasury aligned on unresolved risks",
        "description": "Relationship manager testing bankability logic, sequencing, and export readiness.",
    },
    {
        "id": "preset_prod_delivery_l2",
        "prompt_card_id": "PROD-DELIVERY-HANDOFF-L2",
        "agent_id": "PROD-DELIVERY-HANDOFF-L2",
        "employee_name": "Jonas Richter",
        "actor_type": "PRODUCER",
        "category": "Producer",
        "subtype": "Green Fuels",
        "sophistication": 2,
        "tone": "operator-first",
        "trust_trigger": "Clear ownership of missing evidence and clean handoffs into finance and compliance",
        "cooperation_priority": "Prevent engineering, operations, and finance from keeping different versions of project truth",
        "description": "Producer operator testing evidence sequencing and cross-functional handoff quality.",
    },
]

_PRESET_BY_ID = {preset["id"]: preset for preset in PROMPT_PRESETS}
_ACTIVE_REVIEW_STATUSES = {ReviewStatus.OPEN.value, ReviewStatus.ESCALATED.value}
_RESOLVED_REVIEW_STATUSES = {
    ReviewStatus.RESOLVED.value,
    ReviewStatus.WAIVED.value,
    ReviewStatus.CLOSED.value,
}
_SEVERITY_ORDER = {
    FindingSeverity.CRITICAL.value: 0,
    FindingSeverity.HIGH.value: 1,
    FindingSeverity.MEDIUM.value: 2,
    FindingSeverity.LOW.value: 3,
}


def _connect(db_path: str = _DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _from_json(value: Optional[str], fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_adversarial_reviews_db(db_path: str = _DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS adversarial_reviews (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            actor_type TEXT NOT NULL,
            target_type TEXT,
            target_id TEXT,
            target_route TEXT,
            screen_title TEXT,
            prompt_preset_id TEXT,
            prompt_card_id TEXT,
            agent_id TEXT,
            employee_name TEXT,
            category TEXT,
            subtype TEXT,
            sophistication INTEGER,
            summary TEXT,
            what_it_seems_to_do TEXT,
            what_it_gets_wrong TEXT,
            what_is_missing TEXT,
            what_feels_dangerous TEXT,
            cooperation_risk TEXT,
            trust_increase_needed TEXT,
            clean_handoff_note TEXT,
            final_stance TEXT NOT NULL,
            trust_delta INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'OPEN',
            created_by TEXT NOT NULL,
            resolution_note TEXT,
            resolved_by TEXT,
            correlation_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_adv_reviews_project_status
            ON adversarial_reviews(project_id, status);
        CREATE INDEX IF NOT EXISTS ix_adv_reviews_actor
            ON adversarial_reviews(actor_type);
        CREATE INDEX IF NOT EXISTS ix_adv_reviews_target
            ON adversarial_reviews(target_type, target_id);

        CREATE TABLE IF NOT EXISTS adversarial_findings (
            id TEXT PRIMARY KEY,
            review_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            classification TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            owner_role TEXT,
            blocking INTEGER NOT NULL DEFAULT 1,
            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(review_id) REFERENCES adversarial_reviews(id)
        );
        CREATE INDEX IF NOT EXISTS ix_adv_findings_review
            ON adversarial_findings(review_id);
        CREATE INDEX IF NOT EXISTS ix_adv_findings_severity
            ON adversarial_findings(severity);

        CREATE TABLE IF NOT EXISTS adversarial_handoffs (
            id TEXT PRIMARY KEY,
            review_id TEXT NOT NULL,
            from_role TEXT,
            to_role TEXT NOT NULL,
            plain_language TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            due_at TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(review_id) REFERENCES adversarial_reviews(id)
        );
        CREATE INDEX IF NOT EXISTS ix_adv_handoffs_review
            ON adversarial_handoffs(review_id);
        """
    )
    con.commit()
    con.close()

    try:
        init_event_store()
    except Exception as exc:
        logger.debug("Event store init skipped for adversarial reviews: %s", exc)


def list_prompt_presets(actor_type: Optional[str] = None) -> list[dict]:
    presets = PROMPT_PRESETS
    if actor_type:
        presets = [preset for preset in presets if preset["actor_type"] == actor_type]
    return presets


def _append_event(
    event_type: AdversarialEventType,
    review_id: str,
    project_id: str,
    created_by: Optional[str],
    correlation_id: str,
    data: dict,
) -> None:
    try:
        append_event(
            event_type=event_type.value,
            aggregate_type="adversarial_review",
            aggregate_id=review_id,
            data={"project_id": project_id, **data},
            user_id=created_by,
            correlation_id=correlation_id,
            metadata={"subsystem": "adversarial_reviews"},
        )
    except Exception as exc:
        logger.debug("Adversarial review event append skipped: %s", exc)


def _review_exists(review_id: str, db_path: str = _DB_PATH) -> bool:
    con = _connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT 1 FROM adversarial_reviews WHERE id = ? LIMIT 1", (review_id,))
    row = cur.fetchone()
    con.close()
    return row is not None


def _serialize_finding(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "review_id": row["review_id"],
        "kind": row["kind"],
        "classification": row["classification"],
        "severity": row["severity"],
        "title": row["title"],
        "detail": row["detail"],
        "owner_role": row["owner_role"],
        "blocking": bool(row["blocking"]),
        "evidence_refs": _from_json(row["evidence_refs_json"], []),
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


def _serialize_handoff(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "review_id": row["review_id"],
        "from_role": row["from_role"],
        "to_role": row["to_role"],
        "plain_language": row["plain_language"],
        "status": row["status"],
        "due_at": row["due_at"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


def _base_review_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "actor_type": row["actor_type"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "target_route": row["target_route"],
        "screen_title": row["screen_title"],
        "prompt_preset_id": row["prompt_preset_id"],
        "prompt_card_id": row["prompt_card_id"],
        "agent_id": row["agent_id"],
        "employee_name": row["employee_name"],
        "category": row["category"],
        "subtype": row["subtype"],
        "sophistication": row["sophistication"],
        "summary": row["summary"],
        "what_it_seems_to_do": row["what_it_seems_to_do"],
        "what_it_gets_wrong": row["what_it_gets_wrong"],
        "what_is_missing": row["what_is_missing"],
        "what_feels_dangerous": row["what_feels_dangerous"],
        "cooperation_risk": row["cooperation_risk"],
        "trust_increase_needed": row["trust_increase_needed"],
        "clean_handoff_note": row["clean_handoff_note"],
        "final_stance": row["final_stance"],
        "trust_delta": row["trust_delta"],
        "status": row["status"],
        "created_by": row["created_by"],
        "resolution_note": row["resolution_note"],
        "resolved_by": row["resolved_by"],
        "correlation_id": row["correlation_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "resolved_at": row["resolved_at"],
    }


def get_review(review_id: str, db_path: str = _DB_PATH) -> Optional[dict]:
    con = _connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT * FROM adversarial_reviews WHERE id = ?", (review_id,))
    row = cur.fetchone()
    if row is None:
        con.close()
        return None

    cur.execute(
        "SELECT * FROM adversarial_findings WHERE review_id = ? ORDER BY created_at ASC",
        (review_id,),
    )
    findings = [_serialize_finding(finding) for finding in cur.fetchall()]

    cur.execute(
        "SELECT * FROM adversarial_handoffs WHERE review_id = ? ORDER BY created_at ASC",
        (review_id,),
    )
    handoffs = [_serialize_handoff(handoff) for handoff in cur.fetchall()]
    con.close()

    review = _base_review_dict(row)
    review["findings"] = findings
    review["handoffs"] = handoffs
    review["blocking_findings"] = sum(1 for finding in findings if finding["blocking"])
    review["critical_findings"] = sum(1 for finding in findings if finding["severity"] == FindingSeverity.CRITICAL.value)
    return review


def list_reviews(
    project_id: Optional[str] = None,
    actor_type: Optional[str] = None,
    status: Optional[str] = None,
    db_path: str = _DB_PATH,
) -> list[dict]:
    con = _connect(db_path)
    cur = con.cursor()

    query = "SELECT * FROM adversarial_reviews WHERE 1=1"
    params: list[object] = []

    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    if actor_type:
        query += " AND actor_type = ?"
        params.append(actor_type)
    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC"
    cur.execute(query, params)
    rows = cur.fetchall()
    con.close()
    return [get_review(row["id"], db_path) for row in rows if row is not None]


def create_review(
    *,
    project_id: str,
    actor_type: str,
    target_type: Optional[str],
    target_id: Optional[str],
    target_route: Optional[str],
    screen_title: Optional[str],
    prompt_preset_id: Optional[str],
    prompt_card_id: Optional[str],
    agent_id: Optional[str],
    employee_name: Optional[str],
    category: Optional[str],
    subtype: Optional[str],
    sophistication: Optional[int],
    summary: Optional[str],
    what_it_seems_to_do: Optional[str],
    what_it_gets_wrong: Optional[str],
    what_is_missing: Optional[str],
    what_feels_dangerous: Optional[str],
    cooperation_risk: Optional[str],
    trust_increase_needed: Optional[str],
    clean_handoff_note: Optional[str],
    final_stance: str,
    trust_delta: int,
    created_by: str,
    initial_findings: Optional[list[dict]] = None,
    initial_handoffs: Optional[list[dict]] = None,
    db_path: str = _DB_PATH,
) -> dict:
    preset = _PRESET_BY_ID.get(prompt_preset_id or "")
    review_id = str(uuid.uuid4())
    correlation_id = f"adv-{review_id}"
    now = _now()

    merged_prompt_card_id = prompt_card_id or (preset["prompt_card_id"] if preset else None)
    merged_agent_id = agent_id or (preset["agent_id"] if preset else None)
    merged_employee_name = employee_name or (preset["employee_name"] if preset else None)
    merged_category = category or (preset["category"] if preset else None)
    merged_subtype = subtype or (preset["subtype"] if preset else None)
    merged_sophistication = sophistication if sophistication is not None else (preset["sophistication"] if preset else None)

    con = _connect(db_path)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO adversarial_reviews (
            id, project_id, actor_type, target_type, target_id, target_route, screen_title,
            prompt_preset_id, prompt_card_id, agent_id, employee_name, category, subtype, sophistication,
            summary, what_it_seems_to_do, what_it_gets_wrong, what_is_missing, what_feels_dangerous,
            cooperation_risk, trust_increase_needed, clean_handoff_note, final_stance, trust_delta,
            status, created_by, correlation_id, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            review_id,
            project_id,
            actor_type,
            target_type,
            target_id,
            target_route,
            screen_title,
            prompt_preset_id,
            merged_prompt_card_id,
            merged_agent_id,
            merged_employee_name,
            merged_category,
            merged_subtype,
            merged_sophistication,
            summary,
            what_it_seems_to_do,
            what_it_gets_wrong,
            what_is_missing,
            what_feels_dangerous,
            cooperation_risk,
            trust_increase_needed,
            clean_handoff_note,
            final_stance,
            trust_delta,
            ReviewStatus.OPEN.value,
            created_by,
            correlation_id,
            now,
            now,
        ),
    )
    con.commit()
    con.close()

    _append_event(
        event_type=AdversarialEventType.REVIEW_CREATED,
        review_id=review_id,
        project_id=project_id,
        created_by=created_by,
        correlation_id=correlation_id,
        data={
            "actor_type": actor_type,
            "target_route": target_route,
            "screen_title": screen_title,
            "final_stance": final_stance,
            "trust_delta": trust_delta,
        },
    )

    for finding in initial_findings or []:
        add_finding(review_id=review_id, db_path=db_path, **finding)

    for handoff in initial_handoffs or []:
        add_handoff(review_id=review_id, db_path=db_path, **handoff)

    return get_review(review_id, db_path)  # type: ignore[return-value]


def add_finding(
    *,
    review_id: str,
    kind: str,
    classification: str,
    severity: str,
    title: str,
    detail: str,
    owner_role: Optional[str],
    blocking: bool,
    evidence_refs: Optional[list[str]],
    created_by: str,
    db_path: str = _DB_PATH,
) -> dict:
    review = get_review(review_id, db_path)
    if review is None:
        raise ValueError("Review not found")

    finding_id = str(uuid.uuid4())
    con = _connect(db_path)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO adversarial_findings (
            id, review_id, kind, classification, severity, title, detail,
            owner_role, blocking, evidence_refs_json, created_by, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            finding_id,
            review_id,
            kind,
            classification,
            severity,
            title,
            detail,
            owner_role,
            1 if blocking else 0,
            _json(evidence_refs or []),
            created_by,
            _now(),
        ),
    )
    cur.execute(
        "UPDATE adversarial_reviews SET updated_at = ? WHERE id = ?",
        (_now(), review_id),
    )
    con.commit()
    con.close()

    _append_event(
        event_type=AdversarialEventType.FINDING_ADDED,
        review_id=review_id,
        project_id=review["project_id"],
        created_by=created_by,
        correlation_id=review["correlation_id"],
        data={
            "finding_id": finding_id,
            "kind": kind,
            "classification": classification,
            "severity": severity,
            "blocking": blocking,
        },
    )

    updated = get_review(review_id, db_path)
    assert updated is not None
    finding = next((item for item in updated["findings"] if item["id"] == finding_id), None)
    if finding is None:
        raise ValueError("Finding was not persisted")
    return finding


def add_handoff(
    *,
    review_id: str,
    from_role: Optional[str],
    to_role: str,
    plain_language: str,
    status: str,
    due_at: Optional[str],
    created_by: str,
    db_path: str = _DB_PATH,
) -> dict:
    review = get_review(review_id, db_path)
    if review is None:
        raise ValueError("Review not found")

    handoff_id = str(uuid.uuid4())
    con = _connect(db_path)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO adversarial_handoffs (
            id, review_id, from_role, to_role, plain_language, status, due_at, created_by, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            handoff_id,
            review_id,
            from_role,
            to_role,
            plain_language,
            status,
            due_at,
            created_by,
            _now(),
        ),
    )
    cur.execute(
        "UPDATE adversarial_reviews SET updated_at = ? WHERE id = ?",
        (_now(), review_id),
    )
    con.commit()
    con.close()

    _append_event(
        event_type=AdversarialEventType.HANDOFF_CREATED,
        review_id=review_id,
        project_id=review["project_id"],
        created_by=created_by,
        correlation_id=review["correlation_id"],
        data={
            "handoff_id": handoff_id,
            "from_role": from_role,
            "to_role": to_role,
            "status": status,
        },
    )

    updated = get_review(review_id, db_path)
    assert updated is not None
    handoff = next((item for item in updated["handoffs"] if item["id"] == handoff_id), None)
    if handoff is None:
        raise ValueError("Handoff was not persisted")
    return handoff


def update_review_status(
    *,
    review_id: str,
    status: str,
    resolution_note: Optional[str],
    resolved_by: Optional[str],
    db_path: str = _DB_PATH,
) -> dict:
    review = get_review(review_id, db_path)
    if review is None:
        raise ValueError("Review not found")

    now = _now()
    resolved_at = now if status in {
        ReviewStatus.RESOLVED.value,
        ReviewStatus.WAIVED.value,
        ReviewStatus.CLOSED.value,
    } else None

    con = _connect(db_path)
    cur = con.cursor()
    cur.execute(
        """
        UPDATE adversarial_reviews
        SET status = ?, resolution_note = ?, resolved_by = ?, resolved_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, resolution_note, resolved_by, resolved_at, now, review_id),
    )
    con.commit()
    con.close()

    _append_event(
        event_type=AdversarialEventType.STATUS_CHANGED,
        review_id=review_id,
        project_id=review["project_id"],
        created_by=resolved_by,
        correlation_id=review["correlation_id"],
        data={
            "previous_status": review["status"],
            "new_status": status,
            "resolution_note": resolution_note,
        },
    )

    updated = get_review(review_id, db_path)
    assert updated is not None
    return updated


def get_project_summary(
    project_id: str,
    actor_type: Optional[str] = None,
    db_path: str = _DB_PATH,
) -> dict:
    reviews = list_reviews(project_id=project_id, actor_type=actor_type, db_path=db_path)

    total_reviews = len(reviews)
    open_reviews = sum(1 for review in reviews if review["status"] == ReviewStatus.OPEN.value)
    escalated_reviews = sum(1 for review in reviews if review["status"] == ReviewStatus.ESCALATED.value)
    resolved_reviews = sum(1 for review in reviews if review["status"] in _RESOLVED_REVIEW_STATUSES)

    blocking_findings = 0
    critical_findings = 0
    net_trust_delta = 0
    owner_roles: set[str] = set()
    stance_counts = {stance.value: 0 for stance in FinalStance}

    for review in reviews:
        if review["status"] not in _RESOLVED_REVIEW_STATUSES:
            blocking_findings += review["blocking_findings"]
            critical_findings += review["critical_findings"]
        net_trust_delta += int(review["trust_delta"] or 0)
        stance_counts[review["final_stance"]] = stance_counts.get(review["final_stance"], 0) + 1
        for finding in review["findings"]:
            if finding["owner_role"]:
                owner_roles.add(finding["owner_role"])

    recent_reviews = [
        {
            "id": review["id"],
            "actor_type": review["actor_type"],
            "agent_id": review["agent_id"],
            "screen_title": review["screen_title"],
            "target_route": review["target_route"],
            "status": review["status"],
            "final_stance": review["final_stance"],
            "blocking_findings": review["blocking_findings"],
            "critical_findings": review["critical_findings"],
            "created_at": review["created_at"],
        }
        for review in reviews[:5]
    ]

    return {
        "project_id": project_id,
        "actor_type": actor_type,
        "total_reviews": total_reviews,
        "open_reviews": open_reviews,
        "escalated_reviews": escalated_reviews,
        "resolved_reviews": resolved_reviews,
        "blocking_findings": blocking_findings,
        "critical_findings": critical_findings,
        "net_trust_delta": net_trust_delta,
        "owner_roles": sorted(owner_roles),
        "stance_counts": stance_counts,
        "recent_reviews": recent_reviews,
        "recommended_presets": list_prompt_presets(actor_type),
    }


def get_project_promotion_gate(
    project_id: str,
    db_path: str = _DB_PATH,
) -> dict:
    """
    Summarize whether workflow promotion should be blocked for a project.

    Any OPEN or ESCALATED review carrying a blocking finding blocks promotion
    until the review is resolved, waived, or closed.
    """
    reviews = list_reviews(project_id=project_id, db_path=db_path)

    blockers: list[dict] = []
    review_ids: set[str] = set()
    blocking_titles: list[str] = []

    for review in reviews:
        if review["status"] not in _ACTIVE_REVIEW_STATUSES:
            continue
        for finding in review["findings"]:
            if not finding["blocking"]:
                continue
            blockers.append(
                {
                    "review_id": review["id"],
                    "finding_id": finding["id"],
                    "severity": finding["severity"],
                    "title": finding["title"],
                    "owner_role": finding["owner_role"],
                    "actor_type": review["actor_type"],
                    "screen_title": review["screen_title"],
                    "target_route": review["target_route"],
                    "review_status": review["status"],
                    "created_at": finding["created_at"],
                }
            )
            review_ids.add(review["id"])
            if finding["title"] not in blocking_titles:
                blocking_titles.append(finding["title"])

    blockers.sort(
        key=lambda blocker: (
            _SEVERITY_ORDER.get(blocker["severity"], 99),
            blocker["created_at"],
        )
    )

    blocking_findings = len(blockers)
    blocking_reviews = len(review_ids)
    critical_findings = sum(
        1 for blocker in blockers if blocker["severity"] == FindingSeverity.CRITICAL.value
    )
    blocked = blocking_findings > 0

    if blocked:
        finding_label = "finding" if blocking_findings == 1 else "findings"
        review_label = "review" if blocking_reviews == 1 else "reviews"
        summary = (
            f"Promotion blocked by {blocking_findings} open blocking {finding_label} "
            f"across {blocking_reviews} adversarial {review_label} for project {project_id}."
        )
    else:
        summary = None

    return {
        "project_id": project_id,
        "blocked": blocked,
        "blocking_findings": blocking_findings,
        "blocking_reviews": blocking_reviews,
        "critical_findings": critical_findings,
        "summary": summary,
        "blocking_titles": blocking_titles[:5],
        "blockers": blockers[:10],
    }
