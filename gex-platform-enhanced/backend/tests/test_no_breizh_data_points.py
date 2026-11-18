"""
No Breizh data point in application code.
=========================================
Breizh SAF is the structuring reference case (tests/fixtures/reference_cases/
breizh_saf.json). It may be read by tests and documentation. It may not reach a
project: not as a default, a fallback, a seed, or a figure inside a module.

This scans the application sources of the platform and of the PF engine:
  - string literals carrying an identifying string (name, id, location);
    comments and docstrings are allowed, because they record what was removed
  - a dict literal equal to Breizh's twelve gate scores
  - the Breizh project size as a number
  - a class or dict literal holding four or more of Breizh's structuring inputs
Test directories and fixtures are not scanned.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PLATFORM = BACKEND.parent
REFERENCE = json.loads((BACKEND / "tests/fixtures/reference_cases/breizh_saf.json").read_text())
STRINGS = [s.lower() for s in REFERENCE["identifying_strings"]]
GATE_PROFILE = REFERENCE["gate_scores"]
SIZE = REFERENCE["identity"]["capex_eur"]
INPUTS = {k: v for k, v in REFERENCE["structuring_inputs"].items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
INPUT_VALUES = set(INPUTS.values())

ROOTS_PY = [BACKEND / "app", PLATFORM.parent / "gex_pf_engine" / "backend" / "pf_engine",
            PLATFORM / "tea_engine", PLATFORM / "deal_engine"]
ROOTS_TS = [PLATFORM / "frontend" / "src"]
SKIP = re.compile(r"(^|/)(tests?|__tests__|fixtures|node_modules|venv|__pycache__)(/|$)")


def _files(roots, suffixes):
    for root in roots:
        if root.exists():
            for path in root.rglob("*"):
                if path.suffix in suffixes and not SKIP.search(path.relative_to(root.parent).as_posix()):
                    yield path


def _docstrings(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
                ids.add(id(first.value))
    return ids


def _number(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    return None


def python_findings(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    docs, out = _docstrings(tree), []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            low = node.value.lower()
            out += [f"{path}:{line}: string carries '{s}'" for s in STRINGS if s in low]
        if _number(node) == SIZE:
            out.append(f"{path}:{line}: Breizh project size {SIZE:,}")
        if isinstance(node, ast.Dict):
            try:
                literal = {ast.literal_eval(k): ast.literal_eval(v) for k, v in zip(node.keys, node.values) if k is not None}
            except Exception:  # noqa: BLE001 — not a literal dict
                literal = None
            if literal == GATE_PROFILE:
                out.append(f"{path}:{line}: Breizh twelve-gate score profile")
        if isinstance(node, (ast.ClassDef, ast.Dict)):
            found = {n for sub in ast.walk(node) if (n := _number(sub)) is not None} & INPUT_VALUES
            if len(found) >= 4:
                out.append(f"{path}:{line}: {len(found)} Breizh structuring inputs in one block {sorted(found)}")
    return out


_TS_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_TS_GATE = re.compile(r"\bG(1[01]|[0-9])['\"]?\s*:\s*(\d+)")


def typescript_findings(path: Path) -> list[str]:
    code = _TS_COMMENTS.sub("", path.read_text(encoding="utf-8", errors="ignore"))
    out = [f"{path}: code carries '{s}'" for s in STRINGS if s in code.lower()]
    pairs = {f"G{g}": int(v) for g, v in _TS_GATE.findall(code)}
    if pairs and all(pairs.get(k) == v for k, v in GATE_PROFILE.items()):
        out.append(f"{path}: Breizh twelve-gate score profile")
    if re.search(r"\b285[_,]?000[_,]?000\b", code):
        out.append(f"{path}: Breizh project size {SIZE:,}")
    return out


def test_the_reference_case_is_marked_as_reference_only():
    assert REFERENCE["status"].startswith("REFERENCE ONLY")
    assert len(GATE_PROFILE) == 12 and STRINGS


def test_the_scan_would_catch_each_kind_of_data_point(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text(
        '"""A docstring may say Breizh."""\n'
        "# a comment may say Breizh\n"
        "DEFAULT = 'proj_breizh_saf'\n"
        f"SIZE = {SIZE}\n"
        f"SCORES = {GATE_PROFILE!r}\n"
        "class Ctx:\n    a = 1.34\n    b = 1.18\n    c = 1.41\n    d = 0.089\n")
    found = python_findings(planted)
    assert any("string carries 'breizh'" in f for f in found)
    assert any("project size" in f for f in found)
    assert any("gate score profile" in f for f in found)
    assert any("structuring inputs" in f for f in found)
    assert not any(":1:" in f or ":2:" in f for f in found)          # docstring and comment allowed
    ts = tmp_path / "planted.tsx"
    ts.write_text("// Breizh in a comment is fine\nconst id = 'GEX-BRZ-SAF-001'\nconst g = {G0: 95, G1: 88, G2: 72, G3: 90, "
                  "G4: 78, G5: 45, G6: 0, G7: 55, G8: 68, G9: 92, G10: 0, G11: 0}\n")
    ts_found = typescript_findings(ts)
    assert any("carries 'gex-brz'" in f for f in ts_found) and any("gate score profile" in f for f in ts_found)
    assert not any("'breizh'" in f for f in ts_found)                # the comment is not code


def test_no_application_python_carries_a_breizh_data_point():
    findings = [f for path in _files(ROOTS_PY, {".py"}) for f in python_findings(path)]
    assert findings == [], "\n".join(findings)


def test_no_application_typescript_carries_a_breizh_data_point():
    findings = [f for path in _files(ROOTS_TS, {".ts", ".tsx"}) for f in typescript_findings(path)]
    assert findings == [], "\n".join(findings)


# ── Provenance, not similarity (handoff v4 task 7; Part C test 14) ───────────
import importlib.util
import hashlib
import warnings

SCRIPTS = BACKEND / "scripts"
LOAD_FILE = SCRIPTS / "data" / "project_datasets_20261025.json"
QUARANTINE = SCRIPTS / "data" / "quarantine" / "proj_bremen_h2_structuring_context_20261117.json"
RECORDED = ("dscr_p50", "dscr_p90", "wacc", "offtake_coverage_pct")


def _loader():
    spec = importlib.util.spec_from_file_location("move_project_datasets", SCRIPTS / "move_project_datasets_20261025.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dataset(**kw):
    return {"project_id": "proj_x", "kind": "structuring_context", "from": "a recorded source", "payload": {}, **kw}


def test_the_loader_refuses_reference_provenance_a_missing_source_and_a_missing_approver():
    """Rule: contamination is defined by provenance; a loader needs a source and an approver."""
    refusals = _loader().refusals
    assert refusals({"approved_by": "JML", "datasets": [_dataset()]}) == []
    assert any("no approver" in r for r in refusals({"datasets": [_dataset()]}))
    assert any("no source" in r for r in refusals({"approved_by": "JML", "datasets": [_dataset(**{"from": ""})]}))
    for source in ("tests/fixtures/reference_cases/breizh_saf.json", "Breizh SAF workbook", "reference case"):
        assert any("reference case" in r for r in
                   refusals({"approved_by": "JML", "datasets": [_dataset(**{"from": source})]}))


def test_similarity_alone_never_refuses_a_record():
    """Rule: numerical similarity is a review flag, never the finding."""
    copy = {k: REFERENCE["structuring_inputs"][k] for k in RECORDED}
    assert _loader().refusals({"approved_by": "JML", "datasets": [_dataset(payload=copy)]}) == []


def test_the_load_file_is_loadable_and_no_longer_carries_bremens_record():
    data = json.loads(LOAD_FILE.read_text())
    assert _loader().refusals(data) == []
    assert not [d for d in data["datasets"] if d["project_id"] == "proj_bremen_h2" and d["kind"] == "structuring_context"]
    derived = {"gate_scores", "stage", "jurisdiction", "molecule", "project_size_eur"}
    assert all(not derived & set(d["payload"]) for d in data["datasets"] if d["kind"] == "structuring_context")


def test_bremens_record_is_quarantined_with_its_hash_and_provenance():
    q = json.loads(QUARANTINE.read_text())
    canon = json.dumps(q["row"]["payload"], sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canon.encode()).hexdigest() == q["payload_sha256"]
    assert q["reason"].startswith("PROVENANCE") and "review flag only" in q["similarity_note"]
    assert q["row"]["project_id"] == "proj_bremen_h2" and q["row"]["kind"] == "structuring_context"


def test_no_script_reads_the_reference_fixture():
    """A loader or data script never opens tests/fixtures (docstrings may mention it)."""
    found = []
    for path in SCRIPTS.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                if ("tests/fixtures" in node.value or "reference_cases" in node.value) and \
                        path.name != "move_project_datasets_20261025.py":
                    found.append(f"{path.name}:{node.lineno}")
    assert found == []


def test_similarity_review_flag_on_the_load_file():
    """Review flag only: a record resembling the reference case is reported for a
    person to check its provenance. It never fails and never deletes."""
    data = json.loads(LOAD_FILE.read_text())
    ref = REFERENCE["structuring_inputs"]
    flags = []
    for d in data["datasets"]:
        if d["kind"] == "structuring_context":
            same = [k for k in RECORDED if d["payload"].get(k) == ref.get(k)]
            if len(same) >= 2:
                flags.append(f"{d['project_id']}: {len(same)}/{len(RECORDED)} inputs equal the reference case")
    if flags:
        warnings.warn("REVIEW (provenance check, not a finding): " + "; ".join(flags))
