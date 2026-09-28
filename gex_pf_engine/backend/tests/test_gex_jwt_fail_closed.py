"""
The engine JWT verifier fails closed in production (fixed 2026-09-28).

`pf_engine.auth.gex_jwt` fell back to the platform's DEV secret whenever
GEX_JWT_SECRET was unset, in every environment. That secret is printed in the
source, and docker-compose.prod.yml gave the engine neither GEX_JWT_SECRET nor
GEX_JWKS_URL, so a production engine accepted any HS256 token signed with it:
measured 2026-09-28, 200 on GET /pf/curve/{id}/memory with a token minted from
the source alone.

Now, with ENVIRONMENT in the platform's production set (production, prod,
staging):
  - an unset, empty or dev-default GEX_JWT_SECRET is never a verification key,
    and HS256 tokens are refused with 401;
  - with GEX_JWKS_URL unset as well the engine has no key it may trust, and
    refuses to start, as the platform does on its own dev default.
Outside production nothing changes: local dev and this suite keep the dev
default (conftest.py signs every service token with it).

gex_jwt reads its configuration at import, so each case loads a FRESH copy of
it under the environment being tested; the copy `pf_engine.main` imported for
the rest of the suite is never touched. The subprocess cases boot the real app
in a fresh interpreter, the way the engine starts in a container.
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import jwt
import pytest
from fastapi import HTTPException

from pf_engine.auth import gex_jwt

BACKEND = Path(__file__).resolve().parents[1]
GEX_JWT_FILE = Path(gex_jwt.__file__)
AUTH_VARS = ("ENVIRONMENT", "GEX_JWT_SECRET", "GEX_JWKS_URL")

DEV_DEFAULT = "dev_secret_key_change_in_production"
PLATFORM_SECRET = "platform-secret-key-" + "x" * 44
# Port 9 (discard) is closed: an HS256 check that wrongly consulted the JWKS
# would fail loudly here instead of reaching anything.
UNREACHABLE_JWKS = "http://127.0.0.1:9/api/v1/auth/jwks"

# The three ways a production engine can be left without a real secret.
missing_secret = pytest.mark.parametrize(
    "secret", [None, "", DEV_DEFAULT], ids=["unset", "empty", "dev-default"]
)

_fresh = itertools.count()


def _env(secret: str | None = None, **env: str) -> dict[str, str]:
    return env if secret is None else {**env, "GEX_JWT_SECRET": secret}


def _load_gex_jwt(monkeypatch, **env: str):
    """Import a fresh gex_jwt with exactly `env` set among AUTH_VARS."""
    for var in AUTH_VARS:
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    name = f"_gex_jwt_fail_closed_{next(_fresh)}"
    spec = importlib.util.spec_from_file_location(name, GEX_JWT_FILE)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the module's string annotations through sys.modules.
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _token(engine, secret: str) -> str:
    """The claims of the platform's create_service_token(), signed with `secret`."""
    now = int(time.time())
    claims = {
        "iss": engine.GEX_JWT_ISSUER,
        "aud": engine.GEX_JWT_AUDIENCE,
        "sub": "service:fail-closed-tests",
        "session_tier": "service",
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


# ── Production: the dev default is never a verification key ─────────────────

@missing_secret
def test_production_without_a_trusted_key_refuses_to_start(monkeypatch, secret):
    with pytest.raises(RuntimeError, match="GEX_JWT_SECRET"):
        _load_gex_jwt(monkeypatch, **_env(secret, ENVIRONMENT="production"))


@pytest.mark.parametrize("environment", ["prod", "staging", "PRODUCTION", " Production "])
def test_every_platform_production_name_is_production(monkeypatch, environment):
    """The platform's config.py set, whatever the case or padding."""
    with pytest.raises(RuntimeError, match="GEX_JWT_SECRET"):
        _load_gex_jwt(monkeypatch, ENVIRONMENT=environment)


@missing_secret
def test_production_with_only_jwks_refuses_hs256(monkeypatch, caplog, secret):
    """An RS256-only platform: the engine starts, and a forged HS256 token is 401."""
    engine = _load_gex_jwt(
        monkeypatch,
        **_env(secret, ENVIRONMENT="production", GEX_JWKS_URL=UNREACHABLE_JWKS),
    )
    assert engine.GEX_JWT_SECRET is None
    assert "HS256 tokens are refused" in caplog.text
    with pytest.raises(HTTPException) as refused:
        engine.verify_gex_token(_token(engine, DEV_DEFAULT))
    assert refused.value.status_code == 401
    assert "HS256 is disabled" in refused.value.detail


def test_production_with_the_platform_secret_trusts_only_that_secret(monkeypatch):
    engine = _load_gex_jwt(
        monkeypatch, ENVIRONMENT="production", GEX_JWT_SECRET=PLATFORM_SECRET
    )
    assert engine.verify_gex_token(_token(engine, PLATFORM_SECRET)).is_service_role
    with pytest.raises(HTTPException) as refused:
        engine.verify_gex_token(_token(engine, DEV_DEFAULT))
    assert refused.value.status_code == 401


# ── Development: unchanged ──────────────────────────────────────────────────

@pytest.mark.parametrize("environment", [None, "development"], ids=["unset", "development"])
def test_development_keeps_the_dev_default(monkeypatch, environment):
    env = {} if environment is None else {"ENVIRONMENT": environment}
    engine = _load_gex_jwt(monkeypatch, **env)
    assert engine.GEX_JWT_SECRET == DEV_DEFAULT
    assert engine.verify_gex_token(_token(engine, DEV_DEFAULT)).is_service_role


# ── The real app, booted the way a container boots it ───────────────────────

# Prints the status of /health, then of a protected route called with a token
# signed by the dev default and with one signed by PLATFORM_SECRET.
_BOOT_AND_CALL = """
import json, sys, time
import jwt
from fastapi.testclient import TestClient
from pf_engine.auth import gex_jwt
from pf_engine.main import app

client = TestClient(app)

def curve_memory(secret):
    now = int(time.time())
    token = jwt.encode(
        {"iss": gex_jwt.GEX_JWT_ISSUER, "aud": gex_jwt.GEX_JWT_AUDIENCE,
         "sub": "service:fail-closed-tests", "session_tier": "service",
         "iat": now, "exp": now + 300},
        secret, algorithm="HS256")
    return client.get("/pf/curve/fail-closed/memory",
                      headers={"Authorization": f"Bearer {token}"}).status_code

print(json.dumps({
    "health": client.get("/health").status_code,
    "dev_default": curve_memory(sys.argv[1]),
    "platform_secret": curve_memory(sys.argv[2]),
}))
"""


def _boot_engine(tmp_path, **env: str) -> subprocess.CompletedProcess:
    """Run _BOOT_AND_CALL in a fresh interpreter with exactly `env` among AUTH_VARS."""
    inherited = {k: v for k, v in os.environ.items() if k not in AUTH_VARS}
    return subprocess.run(
        [sys.executable, "-c", _BOOT_AND_CALL, DEV_DEFAULT, PLATFORM_SECRET],
        cwd=BACKEND,
        env={
            **inherited,
            "PYTHONPATH": os.pathsep.join(filter(None, [str(BACKEND), os.environ.get("PYTHONPATH")])),
            "PF_ENGINE_DATA_DIR": str(tmp_path),  # never the shared calibration store
            **env,
        },
        capture_output=True,
        text=True,
        timeout=120,
    )


def _statuses(proc: subprocess.CompletedProcess) -> dict[str, int]:
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_engine_refuses_to_boot_on_the_old_prod_compose(tmp_path):
    """docker-compose.prod.yml before 2026-09-28: ENVIRONMENT=production, nothing else."""
    proc = _boot_engine(tmp_path, ENVIRONMENT="production")
    assert proc.returncode != 0, "the engine booted with no key it may trust"
    assert "GEX_JWT_SECRET is unset or the development default" in proc.stderr


def test_rs256_only_engine_answers_every_hs256_token_401(tmp_path):
    """The 2026-09-28 forged token, replayed against a production engine."""
    proc = _boot_engine(tmp_path, ENVIRONMENT="production", GEX_JWKS_URL=UNREACHABLE_JWKS)
    assert _statuses(proc) == {"health": 200, "dev_default": 401, "platform_secret": 401}


def test_engine_on_the_fixed_prod_compose_serves_platform_tokens_only(tmp_path):
    """docker-compose.prod.yml now passes SECRET_KEY through as GEX_JWT_SECRET."""
    proc = _boot_engine(
        tmp_path,
        ENVIRONMENT="production",
        GEX_JWT_SECRET=PLATFORM_SECRET,
        GEX_JWKS_URL=UNREACHABLE_JWKS,
    )
    assert _statuses(proc) == {"health": 200, "dev_default": 401, "platform_secret": 200}


# ── Every engine runs this file ─────────────────────────────────────────────

PLATFORM_REPO = BACKEND.parent.parent / "gex-platform-enhanced"
ENGINE_COPIES = [
    PLATFORM_REPO / engine / "auth" / "gex_jwt.py" for engine in ("tea_engine", "deal_engine")
]


def test_every_engine_copy_is_this_file():
    """
    gex_jwt.py is deployed verbatim to every engine, so the cases above cover
    tea_engine and deal_engine only while their copies ARE this file. The
    platform repo may be absent from a partial checkout or an image, which
    skips; a checked-out repo missing a copy fails, because a rename must
    update ENGINE_COPIES rather than silently drop out of the comparison.
    """
    if not PLATFORM_REPO.exists():
        pytest.skip(f"platform repo not checked out at {PLATFORM_REPO}")
    ours = GEX_JWT_FILE.read_bytes()
    for copy in ENGINE_COPIES:
        assert copy.exists(), f"{copy} is gone; if it was renamed, update ENGINE_COPIES"
        assert copy.read_bytes() == ours, f"{copy} has drifted from {GEX_JWT_FILE}"
