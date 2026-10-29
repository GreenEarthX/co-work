"""escalation — which index escalates an equipment cost to the target year.

OpenPyTEA escalates every purchased cost by ``CEPCI[target_year] / CEPCI[cost_year]``
(``equipment.inflation_adjustment``), and raises if either year is missing from
``CEPCI_DF``. The shipped series covers 1990-2024 while the correlations carry cost
years 1987-2016, which is why ``cepci_extension`` injects 1987.

Two problems this module exists to solve:

1. **The target year was decorative.** ``integrity.OPENPYTEA_TARGET_CEPCI_YEAR`` labelled
   the cost basis but was never passed to ``Equipment``, which quietly used OpenPyTEA's
   own default of 2024. The two agreed by coincidence, so changing the GEX constant
   would have made the LABEL move while the arithmetic stood still. ``target_year()``
   is now the single answer and the runner passes it explicitly.

2. **Escalation stops at 2024.** The free CEPCI series ends there and is now behind a
   subscription, so a 2025+ cost base is impossible today — ``inflation_adjustment``
   raises. A provider may supply the missing years.

The seam, deliberately narrow: a provider supplies ``{year: index_value}`` on the SAME
scale as CEPCI, and those years are written into the in-memory series OpenPyTEA reads —
the mechanism ``cepci_extension`` already uses for 1987. That makes a new index a swap,
not surgery, and it means a provider EXTENDS the series rather than replacing it. It has
to: the GreenEarthX index is defined from 2001 (its factor series start there) while the
correlations reach back to 1987, so no index on offer can price the whole table alone.

The pin from migration 074 covers this for free: ``correlation_set.fingerprint()`` hashes
the EFFECTIVE series, so any provider-supplied year changes ``cost_basis_hash``. A
different escalation basis therefore cannot price a basis silently.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Protocol

logger = logging.getLogger("gex.tea.escalation")

#: The cost base GEX escalates to. Matches OpenPyTEA's own default today; the runner
#: now passes it explicitly so the label and the arithmetic cannot drift apart.
DEFAULT_TARGET_YEAR = 2024


class EscalationProvider(Protocol):
    name: str

    def series(self) -> dict[int, float]:
        """Years this provider supplies, on the CEPCI scale (1957-59 = 100)."""

    def describe(self) -> dict:
        """Provenance for the cost basis artefact."""


class CepciProvider:
    """The default: OpenPyTEA's own CEPCI series, plus the years GEX already supplies.

    Supplies no extra years itself — `cepci_extension` has already injected what the
    correlations need. Named explicitly so the artefact says which index priced it
    rather than leaving it implied.
    """

    name = "cepci"

    def series(self) -> dict[int, float]:
        return {}

    def describe(self) -> dict:
        from tea_engine import cepci_extension as ce
        return {
            "provider": self.name,
            "index": "Chemical Engineering Plant Cost Index (CEPCI)",
            "source": "openpytea data/cepci_values.csv (1990-2024) + GEX-supplied years",
            "gex_supplied_years": list(ce.GEX_SUPPLIED_CEPCI_YEARS),
            "covers_beyond_2024": False,
            "note": ("The free CEPCI series ends at 2024 and is now behind a "
                     "subscription, so no cost base after 2024 is available on this "
                     "provider."),
        }


class GexIndexProvider:
    """The GreenEarthX escalation index (paper 2026-10-07), once its inputs exist.

    G(t) = InputCost(t) * CycleFactor(t); F(a->b) = G(b)/G(a), baseline-neutral.
    Needs annual factor series (engineering PCU541330541330, buildings WPUSI012011,
    steel, construction materials) and Brent DCOILBRENTEU for the cycle term.

    DELIBERATELY INERT until a governed snapshot of those series exists. It reports
    unavailable rather than guessing: an escalation index that silently invents a year
    would move every capex with nothing to audit. A spot feed is also refused by
    design — `cost_basis_hash` must stay deterministic, so the snapshot has to be an
    annual average governed like any other reference row.
    """

    name = "gex_index"

    def __init__(self, snapshot: Optional[dict[int, float]] = None,
                 provenance: Optional[dict] = None) -> None:
        self._snapshot = dict(snapshot or {})
        self._provenance = provenance or {}

    @property
    def available(self) -> bool:
        return bool(self._snapshot)

    def series(self) -> dict[int, float]:
        return dict(self._snapshot)

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "index": "GreenEarthX plant-cost escalation index",
            "available": self.available,
            "years": sorted(self._snapshot) if self._snapshot else [],
            "covers_beyond_2024": any(y > 2024 for y in self._snapshot),
            **self._provenance,
            "note": ("Inert until a governed annual-average snapshot of the factor "
                     "series is loaded. Not fed from spot data: cost_basis_hash must "
                     "stay deterministic."),
        }


_PROVIDERS: dict[str, EscalationProvider] = {
    CepciProvider.name: CepciProvider(),
    GexIndexProvider.name: GexIndexProvider(),
}


def register(provider: EscalationProvider) -> None:
    """Install a provider — how a populated GEX index arrives without touching callers."""
    _PROVIDERS[provider.name] = provider


def active_provider() -> EscalationProvider:
    """The provider in force. CEPCI unless GEX_ESCALATION_PROVIDER names another.

    Falls back to CEPCI, loudly, if the named provider is unknown or has nothing to
    offer — an unusable provider must not take TEA offline, and must not silently
    look like it worked.
    """
    want = (os.getenv("GEX_ESCALATION_PROVIDER") or CepciProvider.name).strip()
    p = _PROVIDERS.get(want)
    if p is None:
        logger.warning("unknown escalation provider %r; using cepci", want)
        return _PROVIDERS[CepciProvider.name]
    if want != CepciProvider.name and not p.series():
        logger.warning("escalation provider %r supplies no years; using cepci", want)
        return _PROVIDERS[CepciProvider.name]
    return p


def apply(provider: Optional[EscalationProvider] = None) -> list[int]:
    """Write the provider's years into the series OpenPyTEA reads. Returns years added.

    Extends, never overwrites: a year already present keeps its published value, so a
    provider cannot quietly restate history.
    """
    p = provider or active_provider()
    extra = p.series()
    if not extra:
        return []
    try:
        from openpytea.equipment import CEPCI_DF
    except Exception as exc:                            # pragma: no cover
        logger.warning("cannot reach CEPCI_DF (%s); escalation unchanged", exc)
        return []
    added: list[int] = []
    for year, value in sorted(extra.items()):
        if year in CEPCI_DF.index:
            continue
        CEPCI_DF.loc[year, "cepci"] = float(value)
        added.append(int(year))
    if added:
        logger.info("escalation provider %s supplied years %s", p.name, added)
    return added


def available_years() -> list[int]:
    """Every year a cost base could use: already loaded, PLUS what the active provider
    can supply.

    Deliberately order-independent. `cost_basis_hash` runs before `_build_plant` calls
    `apply()`, so a check against only the loaded series refused a year the provider was
    about to inject — the validation would have depended on which line ran first.
    """
    loaded: set[int] = set()
    try:
        from tea_engine import cepci_extension  # noqa: F401  (applies at import)
        from openpytea.equipment import CEPCI_DF
        loaded = {int(y) for y in CEPCI_DF.index}
    except Exception:                                   # pragma: no cover
        pass
    try:
        loaded |= {int(y) for y in active_provider().series()}
    except Exception:                                   # pragma: no cover
        pass
    return sorted(loaded)


def target_year() -> int:
    """The cost base to escalate to — the single answer, label and arithmetic alike.

    GEX_TEA_TARGET_YEAR may move it, but only to a year the series actually covers:
    OpenPyTEA raises deep inside `inflation_adjustment` otherwise, and the resulting
    error names neither the year nor the reason.
    """
    raw = os.getenv("GEX_TEA_TARGET_YEAR")
    if not raw:
        return DEFAULT_TARGET_YEAR
    try:
        want = int(raw)
    except ValueError:
        logger.warning("GEX_TEA_TARGET_YEAR=%r is not a year; using %s",
                       raw, DEFAULT_TARGET_YEAR)
        return DEFAULT_TARGET_YEAR
    years = available_years()
    if years and want not in years:
        raise ValueError(
            f"cost base {want} is not available: the escalation series covers "
            f"{years[0]}-{years[-1]}. The free CEPCI series ends at 2024; a later cost "
            f"base needs an escalation provider that supplies that year "
            f"(GEX_ESCALATION_PROVIDER).")
    return want


def describe() -> dict:
    """The escalation basis, for the cost-basis artefact."""
    p = active_provider()
    years = available_years()
    return {
        **p.describe(),
        "target_year": target_year(),
        "series_covers": ([years[0], years[-1]] if years else None),
    }
