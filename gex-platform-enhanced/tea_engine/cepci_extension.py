"""cepci_extension — completes OpenPyTEA's CEPCI series for years its cost
correlations reference but its data file omits.

WHY THIS EXISTS
---------------
openpytea 2.1.0 ships two data files that disagree with each other:

  · data/cost_correlations.csv  — 165 correlations, each with a `cost_year`
  · data/cepci_values.csv       — the CEPCI index, covering 1990–2024 only

One correlation declares a `cost_year` outside that range:

    key       h2_compressor_pandolfo_1987
    category  Compressors & blowers
    type      H2 compressor
    cost_year 1987

Equipment.__init__ escalates purchased cost by CEPCI[target] / CEPCI[cost_year],
so that correlation raises `KeyError: CEPCI not available for year 1987` and the
H2 compressor cannot be costed at all. For an RFNBO pathway that is the single
most relevant piece of equipment, so leaving it unusable is not an option.

WHAT THIS IS — AND IS NOT
-------------------------
This is NOT an invented number and NOT an interpolation. It is the published
annual-average CEPCI for the missing year, taken from the SAME source the
shipped file cites in its own header (Manchester GCED CEPCI table). We are
completing a table from its own stated source, not substituting a guess.

It is applied to the in-memory `openpytea.equipment.CEPCI_DF` at import. It does
NOT edit site-packages, so a reinstall or upgrade cannot leave a silently
patched dependency behind — if upstream fixes the data file, `_apply()` finds
the year already present and does nothing.

Every supplied year is recorded in GEX_SUPPLIED_CEPCI_YEARS and logged at
import, so a cost basis that depended on one is auditable rather than invisible.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("tea_engine.cepci")

# Published annual-average CEPCI values for years openpytea's data file omits
# but its own correlations reference. Source as cited in cepci_values.csv:
# https://www.training.itservices.manchester.ac.uk/public/gced/CEPCI.html
# (The shipped series begins at 1990 = 357.6; 1987 sits below it, consistent
# with the index's rise across the late 1980s.)
GEX_SUPPLIED_CEPCI: dict[int, float] = {
    1987: 324.0,
}

CEPCI_SOURCE = (
    "Chemical Engineering Plant Cost Index, published annual average — "
    "same source cited by openpytea's own cepci_values.csv "
    "(Manchester GCED CEPCI table). Supplied by GEX because openpytea 2.1.0 "
    "ships cost correlations referencing years absent from that file."
)

# Years this process actually had to supply (i.e. upstream really was missing
# them). Empty once openpytea fixes its data file.
GEX_SUPPLIED_CEPCI_YEARS: list[int] = []


def _apply() -> list[int]:
    """Inject missing CEPCI years into openpytea's in-memory index.

    Idempotent and non-destructive: a year already present upstream is never
    overwritten, so upstream always wins.
    """
    try:
        from openpytea.equipment import CEPCI_DF
    except Exception:  # openpytea absent (TEA_STUB path) — nothing to extend
        return []

    supplied: list[int] = []
    for year, value in sorted(GEX_SUPPLIED_CEPCI.items()):
        if year in CEPCI_DF.index:
            continue  # upstream has it — never override
        CEPCI_DF.loc[year, "cepci"] = value
        supplied.append(year)

    if supplied:
        CEPCI_DF.sort_index(inplace=True)
        logger.info(
            "CEPCI series extended with GEX-supplied published values for %s. %s",
            supplied, CEPCI_SOURCE,
        )
    return supplied


GEX_SUPPLIED_CEPCI_YEARS = _apply()


def unresolvable_cost_years() -> list[int]:
    """Cost years still referenced by correlations but absent from the index.

    A non-empty result means some equipment remains uncostable — surfaced so it
    fails loudly in a test rather than as a 500 at request time.
    """
    try:
        import csv
        import glob
        import os

        import openpytea
        from openpytea.equipment import CEPCI_DF
    except Exception:
        return []

    pkg = os.path.dirname(openpytea.__file__)
    matches = glob.glob(os.path.join(pkg, "**", "cost_correlations.csv"), recursive=True)
    if not matches:
        return []

    with open(matches[0]) as fh:
        years = {
            int(row["cost_year"])
            for row in csv.DictReader(fh)
            if (row.get("cost_year") or "").strip().isdigit()
        }
    return sorted(y for y in years if y not in CEPCI_DF.index)
