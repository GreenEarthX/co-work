"""
Shared fixtures: a clean, releasable drawdown scenario built entirely by
appending ledger rows (the only write path). Tests mutate copies of this to
flip individual checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pytest

from efuel_truth_stack.enums import EntryType, FundingSourceType
from efuel_truth_stack.ledger import Ledger, new_entry, utc
from efuel_truth_stack.models import (
    Allocation, DebtCommitment, DrawdownRequest, EligibleCostLine,
)
from efuel_truth_stack.spec import NODES, cps_of_class

PROJECT = "PRJ1"
PERIOD = "2030-03"
VT = date(2030, 3, 1)          # valid-time anchor for the draw
VF = date(2030, 1, 1)          # claims valid from before the period
T0 = utc(2030, 3, 10, 12, 0)   # transaction-time of recording


@dataclass
class Scenario:
    ledger: Ledger
    drawdown: DrawdownRequest
    commitments: dict
    t0: object = T0
    vt: date = VT


def verify_claim(ledger: Ledger, node: str, claim_type: str, *,
                 producer: str = "projectco_cfo", verifier: str = "independent_engineer",
                 value=True) -> str:
    """Drive a claim to terminal-valid 'verified' the v0.3 way: a fact row
    (evidence → SUBMITTED) plus an explicit approval_decision from the verifier.
    Pre-v0.3 this was a single fact row with to_state='verified' — the exact
    state-smuggling pattern §5.4 now rejects at append time. Ordered entry ids
    keep the fold deterministic at a shared recorded_at."""
    claim_id = f"clm_{node}_{claim_type}"
    ledger.append(new_entry(
        project_id=PROJECT, entry_type=EntryType.CONTRACT, produced_by=producer,
        verified_by=verifier, valid_from=VF, recorded_at=T0,
        entry_id=f"le_{claim_id}_01",
        payload={"claim_id": claim_id, "claim_type": claim_type, "subject_node": node,
                 "value_type": "boolean", "value": value, "period": PERIOD},
    ))
    ledger.append(new_entry(
        project_id=PROJECT, entry_type=EntryType.APPROVAL_DECISION, produced_by=verifier,
        valid_from=VF, recorded_at=T0,
        entry_id=f"le_{claim_id}_02",
        payload={"claim_id": claim_id, "outcome": "approve", "period": PERIOD},
    ))
    return claim_id


def build_clean_scenario(include_release: bool = True) -> Scenario:
    ledger = Ledger()

    # 1+2: drive every initial + ongoing CP node's required claims to verified.
    for cp in cps_of_class("initial") + cps_of_class("ongoing"):
        for ct in NODES[cp["node"]]["required_claims"]:
            verify_claim(ledger, cp["node"], ct)

    # 4+5: one cost line, gross 1.0M, 10% retention; allocations balance to gross.
    cost_line = EligibleCostLine(
        cost_line_id="cl1", cost_category_id="epc_civils", total_amount=1_000_000.0,
        currency="EUR", retention_pct=0.10, vat_treatment="net",
        required_evidence_type=EntryType.COST_INVOICE,
        allocations=[Allocation(source=FundingSourceType.SENIOR_DEBT, amount=1_000_000.0,
                                eligible=True, eligibility_basis="EPC works")],
    )
    # verified cost invoice backing the cost line (epc writes, IE verifies)
    ledger.append(new_entry(
        project_id=PROJECT, entry_type=EntryType.COST_INVOICE, produced_by="epc_contractor",
        verified_by="independent_engineer", valid_from=VF, recorded_at=T0,
        payload={"cost_line_id": "cl1", "amount": 1_000_000.0, "period": PERIOD},
    ))

    # the draw: net of 10% retention => 900k from senior debt
    drawdown = DrawdownRequest(
        id="dd1", project_id=PROJECT, period=PERIOD, cost_lines=[cost_line],
        amount_by_source={FundingSourceType.SENIOR_DEBT: 900_000.0},
    )

    # 7 (reconciles): cash movement within the 5-day settlement window; GHG below limit
    ledger.append(new_entry(
        project_id=PROJECT, entry_type=EntryType.CASH_MOVEMENT, produced_by="account_bank",
        valid_from=date(2030, 3, 3), recorded_at=T0,
        payload={"period": PERIOD, "amount": 900_000.0},
    ))
    ledger.append(new_entry(
        project_id=PROJECT, entry_type=EntryType.MEASUREMENT, produced_by="metering_mrv_actor",
        verified_by="certification_body_auditor", valid_from=VF, recorded_at=T0,
        entry_id="le_clm_ghg_01",
        payload={"claim_id": "clm_ghg", "claim_type": "g_co2e_per_mj", "subject_node": "ghg_lca",
                 "value_type": "numeric", "value": 25.0, "unit": "gCO2e/MJ",
                 "period": PERIOD},
    ))
    # v0.3: verification is an explicit decision entry. v0.3.1: the CERTIFIER
    # approves GHG (authority-inversion fix — certification_body_auditor is now
    # an authorised approval_decision writer; the IE approving GHG was wrong).
    ledger.append(new_entry(
        project_id=PROJECT, entry_type=EntryType.APPROVAL_DECISION,
        produced_by="certification_body_auditor", valid_from=VF, recorded_at=T0,
        entry_id="le_clm_ghg_02",
        payload={"claim_id": "clm_ghg", "outcome": "approve", "period": PERIOD},
    ))

    # 9: account/security release decision present
    if include_release:
        ledger.append(new_entry(
            project_id=PROJECT, entry_type=EntryType.RELEASE_DECISION, produced_by="account_bank",
            valid_from=VT, recorded_at=T0,
            payload={"drawdown_id": "dd1", "period": PERIOD, "outcome": "approve"},
        ))

    commitments = {
        FundingSourceType.SENIOR_DEBT: DebtCommitment(
            id="comm_senior", source_type=FundingSourceType.SENIOR_DEBT, currency="EUR",
            committed_amount=5_000_000.0, drawable_amount=5_000_000.0,
        )
    }
    return Scenario(ledger=ledger, drawdown=drawdown, commitments=commitments)


@pytest.fixture
def clean() -> Scenario:
    return build_clean_scenario()


@pytest.fixture
def make_scenario():
    """Factory so a test can build variants, e.g. make_scenario(include_release=False)."""
    return build_clean_scenario
