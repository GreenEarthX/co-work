"""
scripts/preflight_reviewer_appointment.py must never be able to appoint anyone: it calls the real policy
(`reviewer_appointments.appoint`) so its verdicts are the real ones, and it must never commit. Pinned on the
source, because a preflight that quietly commits is an appointment made without the audit event.
"""
import ast
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "preflight_reviewer_appointment.py"


def test_the_preflight_never_commits_and_always_rolls_back():
    """Negative-verified 2026-10-31: adding conn.commit() to the script fails this."""
    tree = ast.parse(SCRIPT.read_text())
    calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "commit" not in calls
    assert "rollback" in calls


def test_the_preflight_uses_the_real_appointment_policy():
    src = SCRIPT.read_text()
    assert "ra.appoint(" in src and "from app.core import reviewer_appointments as ra" in src
