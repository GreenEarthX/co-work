"""
The two FortaVerde demo sign-ins (JML, 2026-11-03): they live in the TEST
fixture tenant, carry "(demo)" and a .test address, are removed with the
fixture, and the script refuses to overwrite any account it did not write.
Pure checks: no database.
"""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "create_fortaverde_demo_accounts.py"
MARKER = "TEST_FIXTURE_FORTAVERDE"
TENANT = "test_fortaverde"


def _mod():
    spec = importlib.util.spec_from_file_location("gex_fv_demo_accounts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_accounts_cannot_be_mistaken_for_the_real_people():
    m = _mod()
    ids = [a[0] for a in m.DEMO_ACCOUNTS]
    emails = [a[1] for a in m.DEMO_ACCOUNTS]
    assert len(m.DEMO_ACCOUNTS) == 2 and len(set(ids)) == 2 and len(set(emails)) == 2
    for user_id, email, name, function, contact_id, _title in m.DEMO_ACCOUNTS:
        assert user_id.startswith("usr_demo_fv_")
        assert email.endswith("@fortaverde.test"), email          # reserved TLD, never a real inbox
        assert "moehring-energie" not in email                   # the real accounts' domain
        assert name.endswith(" (demo)"), name
        assert function == "EXECUTIVE" and contact_id in {"P1", "P2"}


def test_the_row_says_what_was_bypassed_and_goes_with_the_fixture():
    note = _mod().vetting_note(MARKER, "P1", "CEO")
    assert note.startswith(MARKER)                               # the fixture's --remove matches on this
    assert "VETTING BYPASSED" in note and "mohring_energie" in note


def test_refuses_any_account_it_did_not_write():
    m = _mod()
    ours = m.DEMO_ACCOUNTS[0][0]
    good = (ours, TENANT, f"{MARKER}: DEMO sign-in ...")
    assert m.conflicts([good], TENANT, MARKER) == []
    assert m.conflicts([("jan_block_real", TENANT, f"{MARKER}: x")], TENANT, MARKER)   # not one of our ids
    assert m.conflicts([(ours, "mohring_energie", f"{MARKER}: x")], TENANT, MARKER)    # another tenant
    assert m.conflicts([(ours, TENANT, "registered by the owner")], TENANT, MARKER)    # not marked
    assert m.conflicts([(ours, TENANT, None)], TENANT, MARKER)


def test_platform_app_is_imported_before_the_knowledge_record():
    """Loading the record runs its validator, which puts gex_pf_engine/backend first on
    sys.path. `app` must already be the platform's by then, or the PF engine's alias
    guard stops the script (seen 2026-11-03, before anything was written)."""
    import inspect

    src = inspect.getsource(_mod().main)
    assert src.index("from app.core.auth import pwd_context") < src.index("import load_fortaverde_test_project")
