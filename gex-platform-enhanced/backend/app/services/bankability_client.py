"""
GEX Bankability Client
=======================
Location: gex-platform-enhanced/backend/app/services/bankability_client.py

HTTP bridge between gex-platform-enhanced and gex_pf_engine's bankability engine.
Integrates with the existing:
  - event_storene.py (audit trail)
  - state_machine.py (phase transitions)
  - WebSocket layer (push to frontend)

Call flow:
  1. Evidence status changes in platform DB
  2. This client calls POST /api/v1/bankability/evaluate on port 8001
  3. Engine returns snapshot
  4. Client stores snapshot, emits event, pushes to WebSocket
  5. Frontend workspace receives persona-scoped update
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger("gex.bankability_client")

# Engine URL — in production, use environment variable
BANKABILITY_ENGINE_URL = "http://localhost:8001/api/v1/bankability"
REQUEST_TIMEOUT = 30.0


class BankabilityClient:
    """
    Async HTTP client for the bankability engine.
    Instantiate once in app startup, inject into routes/services.
    """

    def __init__(self, base_url: str = BANKABILITY_ENGINE_URL):
        self.base_url = base_url

    # ─── CORE: EVALUATE ON EVIDENCE CHANGE ──────────────────────────────────

    async def evaluate(
        self,
        project_id: str,
        evidence_rows: list[dict],
        previous_state: Optional[str] = None,
    ) -> dict:
        """
        Call this on every evidence status change.

        Args:
            project_id: GEX project ID
            evidence_rows: List of evidence dicts from platform DB
                Each dict: {key, status, submitted_by, verified_by, ...}
            previous_state: Last known bankability state string

        Returns:
            Full ProjectBankabilitySnapshot dict

        Integration in existing code:

            # In api/endpoints/evidence.py or wherever evidence is updated
            @router.put("/projects/{project_id}/evidence/{evidence_key}")
            async def update_evidence(project_id, evidence_key, payload):
                # 1. Update DB
                db.update_evidence(project_id, evidence_key, payload)

                # 2. Fetch all evidence for this project
                all_evidence = db.get_all_evidence(project_id)
                project = db.get_project(project_id)

                # 3. Evaluate bankability
                snapshot = await bankability_client.evaluate(
                    project_id=project_id,
                    evidence_rows=[e.to_dict() for e in all_evidence],
                    previous_state=project.bankability_state,
                )

                # 4. Update project state if changed
                if snapshot["current_state"] != project.bankability_state:
                    db.update_project_state(project_id, snapshot["current_state"])

                    # 5. Emit event for audit trail
                    event_store.append(
                        event_type="BANKABILITY_STATE_CHANGED",
                        project_id=project_id,
                        payload={
                            "from_state": project.bankability_state,
                            "to_state": snapshot["current_state"],
                            "regression": snapshot.get("regression"),
                            "snapshot_hash": snapshot["snapshot_hash"],
                        }
                    )

                # 6. Push to frontend via WebSocket
                await ws_manager.broadcast_to_project(project_id, {
                    "type": "BANKABILITY_UPDATE",
                    "snapshot": snapshot,
                })

                return snapshot
        """
        payload = {
            "project_id": project_id,
            "evidence": evidence_rows,
            "previous_state": previous_state,
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            try:
                resp = await client.post(f"{self.base_url}/evaluate", json=payload)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Bankability engine HTTP error: {e.response.status_code}")
                raise
            except httpx.ConnectError:
                logger.error("Cannot connect to bankability engine. Is gex_pf_engine running on port 8001?")
                raise

    # ─── PERSONA-SCOPED VIEW (called by workspace pages) ───────────────────

    async def evaluate_for_persona(
        self,
        project_id: str,
        evidence_rows: list[dict],
        persona: str,
        previous_state: Optional[str] = None,
    ) -> dict:
        """
        Get persona-scoped bankability view.

        Called when a workspace page loads:
            PRODUCER  → Producer workspace loads production management
            FINANCE   → Finance workspace loads StageGatesPage
            REGULATOR → Regulator workspace loads verification page
            EXECUTIVE → Executive workspace loads KPI dashboard

        Integration in existing routes:

            # In api/endpoints/workspace.py or similar
            @router.get("/projects/{project_id}/bankability/{persona}")
            async def get_bankability_view(project_id, persona):
                all_evidence = db.get_all_evidence(project_id)
                project = db.get_project(project_id)
                return await bankability_client.evaluate_for_persona(
                    project_id=project_id,
                    evidence_rows=[e.to_dict() for e in all_evidence],
                    persona=persona,
                    previous_state=project.bankability_state,
                )
        """
        payload = {
            "project_id": project_id,
            "evidence": evidence_rows,
            "persona": persona,
            "previous_state": previous_state,
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(f"{self.base_url}/evaluate/persona", json=payload)
            resp.raise_for_status()
            return resp.json()

    # ─── EXECUTIVE MULTI-PERSONA VIEW ───────────────────────────────────────

    async def evaluate_multi_persona(
        self,
        project_id: str,
        evidence_rows: list[dict],
        personas: list[str],
        previous_state: Optional[str] = None,
    ) -> dict:
        """
        Executive dashboard: see all persona views + full snapshot.
        Used by CEO/CFO/Head of Legal to understand cross-functional status.
        """
        payload = {
            "project_id": project_id,
            "evidence": evidence_rows,
            "personas": personas,
            "previous_state": previous_state,
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(f"{self.base_url}/evaluate/multi-persona", json=payload)
            resp.raise_for_status()
            return resp.json()

    # ─── GATE DEFINITIONS (cache on startup) ────────────────────────────────

    async def get_gate_definitions(self) -> list[dict]:
        """Fetch gate definitions. Call once on app init, cache in memory."""
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(f"{self.base_url}/gates")
            resp.raise_for_status()
            return resp.json()

    # ─── RULES (for Executive transparency view) ───────────────────────────

    async def get_rules(self) -> dict:
        """Fetch state transition and regression rules."""
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(f"{self.base_url}/rules")
            resp.raise_for_status()
            return resp.json()

    # ─── REGRESSION CHECK (scheduled/periodic) ─────────────────────────────

    async def check_regression(
        self,
        project_id: str,
        evidence_rows: list[dict],
        previous_state: str,
    ) -> dict:
        """
        Explicit regression check. Run this:
          - On a cron schedule (e.g., daily)
          - When evidence items expire
          - When external events invalidate evidence

        If regression detected, the platform should:
          1. Update project state
          2. Notify stakeholders
          3. Log to event store
          4. Trigger re-evaluation workflow
        """
        payload = {
            "project_id": project_id,
            "evidence": evidence_rows,
            "previous_state": previous_state,
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(f"{self.base_url}/regression/check", json=payload)
            resp.raise_for_status()
            return resp.json()

    # ─── HEALTH CHECK ──────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Check if bankability engine is reachable."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                return resp.json()
            except Exception:
                return {"status": "unreachable"}


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

bankability_client = BankabilityClient()
