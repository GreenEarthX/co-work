from __future__ import annotations

from math import ceil

CAPACITY_DAYS_PER_YEAR = 365
ANNUAL_CAPACITY_ROUNDING_STEP = 10


def _finite_volume(value: float | int) -> float:
    try:
        volume = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, volume)


def round_annual_capacity_mt_year(value: float | int) -> int:
    volume = _finite_volume(value)
    return int(ceil(volume / ANNUAL_CAPACITY_ROUNDING_STEP) * ANNUAL_CAPACITY_ROUNDING_STEP)


def capacity_mtpd_to_mt_year(capacity_mtpd: float | int) -> int:
    return round_annual_capacity_mt_year(_finite_volume(capacity_mtpd) * CAPACITY_DAYS_PER_YEAR)


def capacity_mt_year_to_mtpd(capacity_mt_year: float | int) -> int:
    return int(ceil(_finite_volume(capacity_mt_year) / CAPACITY_DAYS_PER_YEAR))
