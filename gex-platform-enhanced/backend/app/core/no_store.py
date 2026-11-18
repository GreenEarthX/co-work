"""
Responses that must never be cached (handoff v4, task 9).
=========================================================
Every response carrying pre-FID data, a figure derived from it, or a returns
case is sent `Cache-Control: no-store, private`, so a revoked share or a
refused read cannot be served afterwards from a browser or proxy cache. The
access rule itself re-reads the shares on every request (pre_fid_access).

One list, applied by one middleware in main.py. A new route carrying such data
belongs under one of these prefixes, or is added here.
"""
from __future__ import annotations

NO_STORE = "no-store, private"

PREFIXES = (
    "/api/v1/packages",            # development packages: pre-FID spend
    "/api/v1/spend-wave",          # the spend wave
    "/api/v1/capital-bridge",      # spend wave, one-shot project view
    "/api/v1/devex-brief",         # the DEVEX brief and its shares
    "/api/v1/pre-cod-metrics",     # CEC, FRI, capital gap: derived from packages
    "/api/v1/lineage",             # project lineage
    "/api/v1/returns-cases",       # published returns cases and their shares
    "/api/v1/calculation-chain",   # cost basis, TEA, financing and returns of one project
    "/api/v1/cost-basis",          # saved cost basis versions
    "/api/v1/tea-review",          # reviews of TEA base cases
    "/api/v1/finance-model",       # returns computed on the owner's inputs
    "/api/v1/projects/",           # datasets (spend_wave) and the one-shot project view
    "/api/v1/structuring",         # gaps and packages on the owner's records
    "/api/v1/ic-pack",             # IC pack exports (PDF, JSON)
    "/api/v1/evidence-pack",       # export
)


def applies(path: str) -> bool:
    return any(path.startswith(p) for p in PREFIXES)
