"""
`app` — a guarded, deprecated alias for `pf_engine`.
====================================================
The package was renamed `app` -> `pf_engine` on 2026-09-09 because BOTH this
repo and `gex-platform-enhanced/backend` had a top-level package called `app`;
whichever imported first won and the other's submodules became unreachable.
That cost three failed attempts at one test helper, and once turned five tests
into silent SKIPs while the suite stayed green.

The rename was right. Deleting the old name was not: `uvicorn app.main:app` is
in shell history, and history is recalled with an arrow key, not read. It was
typed three times on 2026-09-09 — twice against a bare ModuleNotFoundError and
once against a tombstone that printed the correct command and still did not
start the engine. So the old name works again.

WHAT MAKES THIS SAFE, WHERE A PLAIN ALIAS WOULD NOT BE
------------------------------------------------------
The danger was never "two packages named app". It was one process holding both
trees on sys.path, silently resolving `app.main` to the wrong service — the
platform's `app.main` is a 56-router FastAPI app, this one is the PF engine.

So this alias REFUSES TO LOAD in exactly that configuration. If the platform's
backend is anywhere on sys.path, importing `app` raises instead of shadowing it.
The check is a direct statement of the invariant, not a heuristic: it looks for
`app/core/db_backend.py`, a file only the platform has.

Everything outside that case is a loud failure too. This package contains only
`main`, so a stray `import app.core...` or `app.api...` raises
ModuleNotFoundError rather than returning a wrong module.

`gex-platform-enhanced/backend/tests/test_sibling_app_alias.py` pins all of it.
Canonical name for new code is `pf_engine`; Dockerfile and CLAUDE.md both use it.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The platform backend, if it is reachable from this interpreter. `db_backend.py`
# is the marker because only the platform has it — matching on the directory name
# would break for anyone who checks the repo out under a different name.
_clashing = [
    p for p in sys.path
    if p and (Path(p) / "app" / "core" / "db_backend.py").is_file()
]
if _clashing:
    raise ImportError(
        "refusing to alias `app` -> `pf_engine`: gex-platform-enhanced's backend "
        f"is also on sys.path ({_clashing[0]}), and both trees define a top-level "
        "`app`. Whichever loaded first would win and silently supply the wrong "
        "service's modules — `app.main` is a 56-router platform app there and the "
        "PF engine here. Import `pf_engine` directly instead."
    )

print(
    "NOTE: `app` is a deprecated alias for `pf_engine` (renamed 2026-09-09). "
    "It works, but the canonical command is:\n"
    "      uvicorn pf_engine.main:app --reload --port 8001",
    file=sys.stderr,
)
