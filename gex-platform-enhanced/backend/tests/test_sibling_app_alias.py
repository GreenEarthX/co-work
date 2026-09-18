"""
The sibling's `app` -> `pf_engine` alias, and the guard that makes it safe.
==========================================================================
`gex_pf_engine/backend/app/` is a deprecated alias for `pf_engine`. It exists
because `uvicorn app.main:app` lives in shell history and was typed three times
on 2026-09-09 after the rename — twice against a bare ModuleNotFoundError, once
against a tombstone that printed the right command and still did not start the
engine.

The rename itself was correct and stands: both this repo and the sibling had a
top-level `app`, whichever imported first won, and the loser's submodules
vanished. That is why the alias carries a guard, and why these tests exist.

WHAT IS BEING PINNED
  1. the alias resolves, and to the SAME FastAPI object — not a second instance
  2. it REFUSES to load when the platform backend is also on sys.path
  3. it holds nothing but __init__.py and main.py, so a stray `app.core...`
     fails loudly instead of resolving into the wrong service
  4. the canonical name still works and is what the docs tell people to use

(2) is the whole safety argument. If it ever stops raising, the alias becomes
the silent wrong-module bug the rename removed — so it is negative-verified
here rather than asserted in a comment.

Import behaviour cannot be tested in this process: `app` is already bound to the
PLATFORM's package, which is precisely the ambiguity under test. Every case
below therefore runs in a subprocess under the sibling's own interpreter. A
missing sibling checkout SKIPS; a present sibling that answers wrongly FAILS.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SIBLING = Path(__file__).resolve().parents[2].parent / "gex_pf_engine" / "backend"
PYTHON = SIBLING.parent / "micro_service" / "bin" / "python"
ALIAS = SIBLING / "app"
PLATFORM_BACKEND = Path(__file__).resolve().parents[1]


def _run(code: str) -> subprocess.CompletedProcess:
    """Run `code` under the sibling's interpreter, cwd = sibling backend."""
    if not SIBLING.exists() or not PYTHON.exists():
        pytest.skip(f"sibling gex_pf_engine / micro_service not present at {SIBLING}")
    return subprocess.run(
        [str(PYTHON), "-c", code], cwd=str(SIBLING),
        capture_output=True, text=True, timeout=120,
    )


def test_the_alias_files_are_present():
    """Without these, `uvicorn app.main:app` dies on a bare ModuleNotFoundError."""
    if not SIBLING.exists():
        pytest.skip("sibling not checked out")
    assert (ALIAS / "__init__.py").is_file(), f"{ALIAS}/__init__.py missing"
    assert (ALIAS / "main.py").is_file(), (
        f"{ALIAS}/main.py missing — `uvicorn app.main:app` is in shell history "
        "and will fail without it"
    )


def test_app_main_resolves_to_the_very_same_object_as_pf_engine_main():
    """
    Identity, not equality. A second `FastAPI()` under the old name would drift:
    a route or exception handler registered on one would be missing from the
    other, and which one uvicorn served would depend on the command typed.
    """
    r = _run(
        "import app.main, pf_engine.main;"
        "print('SAME' if app.main.app is pf_engine.main.app else 'DIFFERENT')"
    )
    assert r.returncode == 0, f"alias failed to import:\n{r.stderr}"
    assert "SAME" in r.stdout, (
        f"`app.main:app` is not the same object as `pf_engine.main:app`:\n{r.stdout}\n{r.stderr}"
    )


def test_the_alias_announces_that_it_is_deprecated():
    """A working alias that says nothing never gets migrated away from."""
    r = _run("import app.main")
    assert r.returncode == 0, r.stderr
    assert "deprecated alias" in r.stderr, (
        f"the alias loaded silently; stderr was:\n{r.stderr}"
    )
    assert "pf_engine.main:app" in r.stderr, "the notice must name the canonical command"


def test_the_alias_REFUSES_to_load_beside_the_platform_backend():
    """
    THE SAFETY PROPERTY — negative-verified, not asserted.

    The dangerous configuration is the SIBLING first on sys.path with the
    platform backend also reachable: `import app` then finds this alias, and
    without the guard `app.main` would silently be the PF engine instead of the
    56-router platform app. So the platform is APPENDED — the sibling is the cwd,
    sys.path[0] — and the import must raise.

    CORRECTED 2026-09-14. The first version INSERTED the platform at
    sys.path[0]. In that order `import app` resolves to the platform's own
    package, the alias is never imported, the guard never runs — and the test
    failed with "NO_GUARD", reading as though the guard were broken. The guard
    was fine; the test never reached it. It went unnoticed for five days because
    the run that would have caught it was interrupted on 2026-09-09.
    """
    r = _run(
        f"import sys; sys.path.append({str(PLATFORM_BACKEND)!r});\n"
        "try:\n"
        "    import app\n"
        "    print('NO_GUARD')\n"
        "except ImportError as e:\n"
        "    print('RAISED'); print(e)\n"
    )
    assert r.returncode == 0, r.stderr
    assert "RAISED" in r.stdout, (
        "the alias loaded with gex-platform-enhanced's backend on sys.path. "
        "That is the silent wrong-module bug the 2026-09-09 rename removed.\n"
        f"stdout: {r.stdout}\nstderr: {r.stderr}"
    )
    assert "both trees define a top-level" in r.stdout, "the guard must explain itself"


def test_with_the_platform_first_the_platform_app_wins():
    """
    The other order, and why it is not the hazard: with the platform ahead on
    sys.path, `app` IS the platform's package and the alias is never imported.
    Pinned so that both orders are on record — confusing them is exactly how the
    test above came to test nothing.
    """
    r = _run(
        f"import sys; sys.path.insert(0, {str(PLATFORM_BACKEND)!r});\n"
        "import importlib.util\n"
        "print(importlib.util.find_spec('app').origin)\n"
    )
    assert r.returncode == 0, r.stderr
    origin = r.stdout.strip()
    assert origin.startswith(str(PLATFORM_BACKEND)), (
        f"with the platform first, `app` must resolve to the platform package; got {origin}"
    )


def test_the_alias_exposes_nothing_but_main():
    """
    A stray `app.core...` or `app.api...` must fail loudly rather than resolve
    into a 39-file engine that has neither.
    """
    if not SIBLING.exists():
        pytest.skip("sibling not checked out")
    contents = sorted(
        p.name for p in ALIAS.iterdir() if p.name != "__pycache__"
    )
    assert contents == ["__init__.py", "main.py"], (
        f"the alias package must hold only __init__.py and main.py; found {contents}"
    )
    r = _run(
        "try:\n"
        "    import app.core.db_backend\n"
        "    print('RESOLVED')\n"
        "except ModuleNotFoundError:\n"
        "    print('NOT_FOUND')\n"
    )
    assert "NOT_FOUND" in r.stdout, (
        f"`app.core.db_backend` resolved through the alias: {r.stdout}{r.stderr}"
    )


def test_the_canonical_name_is_what_the_docs_tell_people_to_run():
    """The alias is a concession, not the documented path."""
    r = _run("import pf_engine.main; print(type(pf_engine.main.app).__name__)")
    assert r.returncode == 0, f"canonical import broke:\n{r.stderr}"
    assert "FastAPI" in r.stdout, r.stdout

    claude_md = Path(__file__).resolve().parents[2] / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        text = claude_md.read_text()
        assert "pf_engine.main:app" in text, (
            "CLAUDE.md must document the canonical command, not the alias"
        )
