"""correlation_set — a fingerprint of the cost data that priced a basis.

OpenPyTEA's 417 published cost correlations (1,291 fitted coefficients, Turton /
Towler & Sinnott / Seider) and its CEPCI index series live in CSV files inside
site-packages. They are literature constants, so unlike GEX's own assumptions they must
NOT be editable — editing them destroys the traceability that makes a number defensible
to a lender. But a cost basis must still record WHICH set priced it, because:

  · a `pip install` can replace them without anything in this repo changing;
  · `cepci_extension` mutates the in-memory CEPCI series at import, so the EFFECTIVE
    series is not the shipped file;
  · the engine version alone is not enough — two installs of the same version could
    carry different data (a vendored tree, a patched wheel, a local build).

So this module fingerprints the EFFECTIVE data and `cost_basis_hash` includes it. The
fingerprint is a pin, not a parameter: nothing here is proposable or approvable. What
IS governed is whether GEX has reviewed a given set — recorded in `tea_correlation_set`
by the backend bridge, which flags a set it has never seen.

Deterministic by construction: raw file bytes plus the effective CEPCI series as sorted
(year, value) pairs. No dict ordering, no float formatting, no pandas round-trip.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Optional

_CORRELATIONS = "cost_correlations.csv"
_CEPCI = "cepci_values.csv"


def _data_dir() -> Optional[str]:
    try:
        import openpytea
    except Exception:                                  # pragma: no cover
        return None
    d = os.path.join(os.path.dirname(openpytea.__file__), "data")
    return d if os.path.isdir(d) else None


def _effective_cepci() -> list[tuple[int, float]]:
    """The CEPCI series actually in force, AFTER cepci_extension's in-memory additions.

    Hashing the shipped file alone would miss every year GEX supplies, so two installs
    differing only in the extension would fingerprint identically.
    """
    try:
        from tea_engine import cepci_extension  # noqa: F401  (applies at import)
        from openpytea.equipment import CEPCI_DF
    except Exception:                                  # pragma: no cover
        return []
    out: list[tuple[int, float]] = []
    for year in sorted(CEPCI_DF.index):
        try:
            out.append((int(year), round(float(CEPCI_DF.loc[year, "cepci"]), 6)))
        except Exception:                              # pragma: no cover
            continue
    return out


def fingerprint() -> dict[str, Any]:
    """The pin for the cost data in force.

    NOT cached. It was @lru_cache(maxsize=1) on the assumption that the data cannot
    change in-process — which is false: `escalation.apply()` injects years into the
    in-memory CEPCI series, and a cached fingerprint then reported the OLD series after
    the cost base had already moved. Measured 2026-10-26: a 2025 cost base changed capex
    175,255,929 -> 180,864,119 while the pin still said [1987, 2024] and
    cost_basis_hash did not move — the precise defect this pin exists to prevent.
    Re-reading two files per compute is cheaper than a wrong pin.
    """
    d = _data_dir()
    parts: list[bytes] = []
    components: dict[str, Any] = {}

    for name in (_CORRELATIONS, _CEPCI):
        path = os.path.join(d, name) if d else None
        if path and os.path.isfile(path):
            raw = open(path, "rb").read()
            parts.append(name.encode() + b"\0" + raw)
            components[name] = {
                "sha256": hashlib.sha256(raw).hexdigest()[:16],
                "bytes": len(raw),
            }
        else:
            parts.append(name.encode() + b"\0<absent>")
            components[name] = None

    cepci = _effective_cepci()
    parts.append(b"cepci_effective\0" + repr(cepci).encode())

    version = None
    try:
        from importlib.metadata import version as _v
        version = _v("openpytea")
    except Exception:                                  # pragma: no cover
        pass
    parts.append(b"openpytea\0" + str(version).encode())

    digest = hashlib.sha256(b"\x1f".join(parts)).hexdigest()
    return {
        "hash": "sha256:" + digest[:24],
        "openpytea_version": version,
        "correlations": _count_correlations(d),
        "cepci_year_range": ([cepci[0][0], cepci[-1][0]] if cepci else None),
        "cepci_years": len(cepci),
        "gex_supplied_cepci_years": _gex_supplied(),
        "components": components,
        "note": ("Published cost correlations and the effective CEPCI series. A pin, not "
                 "a parameter: these are literature constants and are deliberately not "
                 "editable. The hash changes if the installed data changes."),
    }


def _count_correlations(d: Optional[str]) -> Optional[int]:
    if not d:
        return None
    path = os.path.join(d, _CORRELATIONS)
    if not os.path.isfile(path):
        return None
    # Not a line count: the notes column contains embedded newlines, so counting lines
    # overstates the row count (420 against the real 417). Parse it.
    try:
        import pandas as pd
        return int(len(pd.read_csv(path)))
    except Exception:                                  # pragma: no cover
        return None


def _gex_supplied() -> list[int]:
    try:
        from tea_engine import cepci_extension as ce
        return list(ce.GEX_SUPPLIED_CEPCI_YEARS)
    except Exception:                                  # pragma: no cover
        return []


def set_hash() -> str:
    return str(fingerprint()["hash"])
