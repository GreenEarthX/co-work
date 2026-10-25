"""Project datasets: the kinds the frontend held in code.

Revision ID: 071
Revises: 070

JML 2026-10-25 (project data out of code, part 3): fourteen screens carried
per-project dictionaries — banker snapshots, capital stacks, certification and
45V readiness, offtake quality, insurance schedules, transfer readiness, IC-pack
configuration, demand buyers, spend waves, drawdown tranches, term sheets and
timelines. They move to project_dataset (069) verbatim and UNVERIFIED, by
scripts/move_frontend_datasets_20261025.py. This only widens the kind check;
the defaults those screens used for every other project are not moved.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "071"
down_revision: Union[str, None] = "070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKEND = ("deal_inputs", "task_router_inputs", "structuring_context", "drawdown_layer", "adjacency_profile")
FRONTEND = ("bankers_snapshot", "capital_stack", "cert_readiness", "cert_45v", "offtake_quality",
            "insurance_schedule", "transfer_readiness", "ic_pack_config", "ic_pack_readiness", "demand_buyers",
            "spend_wave", "drawdown_tranches", "drawdown_milestones", "term_sheet", "project_timeline", "plant_builder_preset")


def _check(kinds) -> None:
    op.get_bind().execute(sa.text("ALTER TABLE project_dataset DROP CONSTRAINT project_dataset_kind_check"))
    listed = ", ".join(f"'{k}'" for k in kinds)
    op.get_bind().execute(sa.text(
        f"ALTER TABLE project_dataset ADD CONSTRAINT project_dataset_kind_check CHECK (kind IN ({listed}))"))


def upgrade() -> None:
    _check(BACKEND + FRONTEND)


def downgrade() -> None:
    kinds = ", ".join(f"'{k}'" for k in FRONTEND)
    op.get_bind().execute(sa.text(f"DELETE FROM project_dataset WHERE kind IN ({kinds})"))
    _check(BACKEND)
