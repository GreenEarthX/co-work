"""
Debt Sculpting - DSCR-Based Repayment Profiling with DFI Grace Periods
Sculpts debt repayment to match CFADS profile, ensuring minimum DSCR
while respecting concessional grace periods and first-loss positions.
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from .tranche import Tranche, TrancheType, FinancingStructure


@dataclass
class SculptingConstraints:
    """Parameters governing debt sculpting"""
    target_dscr: float = 1.35           # Target DSCR (commercial lender minimum)
    min_dscr: float = 1.20              # Hard floor — triggers lock-up
    max_dscr: float = 2.00              # Cap to avoid over-sculpting
    lock_up_dscr: float = 1.10          # Cash sweep / distribution lock-up trigger
    default_dscr: float = 1.00          # Below this = technical default
    tail_years: int = 2                 # Years of cash flow beyond last debt payment


@dataclass
class SculptedYear:
    """Single year in the sculpted repayment profile"""
    year: int
    cfads: float
    total_debt_service: float
    dscr: float
    is_grace_period: bool               # Any tranche in grace
    surplus_cash: float
    is_lock_up: bool                    # DSCR below lock-up threshold
    is_compliant: bool                  # DSCR above min threshold
    tranche_payments: Dict[str, float]  # Per-tranche breakdown


class DebtSculptor:
    """
    Sculpts debt repayment across tranches to match CFADS profile.

    Key behaviours:
    - Concessional tranches with grace periods: interest-only during grace
    - First-loss tranches: absorb shortfalls before commercial debt
    - Target DSCR sculpting: adjusts commercial repayment to hit target
    - Grace period handling: DFI grace = interest-only, no principal reduction
    """

    def __init__(
        self,
        financing: FinancingStructure,
        constraints: Optional[SculptingConstraints] = None,
    ):
        self.financing = financing
        self.constraints = constraints or SculptingConstraints()

    def sculpt(self, cfads_profile: List[float]) -> Dict:
        """
        Sculpt debt repayment across the full project lifetime.

        Args:
            cfads_profile: Year-by-year CFADS values (index 0 = year 1)

        Returns:
            Dict with sculpted profile, DSCR series, and compliance flags
        """
        years = len(cfads_profile)
        sculpted_years: List[SculptedYear] = []
        cumulative_shortfall = 0.0

        for i, cfads in enumerate(cfads_profile):
            year = i + 1

            # 1. Compute natural debt service for this year
            #    (respects grace periods automatically via Tranche.annual_debt_service)
            tranche_payments: Dict[str, float] = {}
            total_ds = 0.0
            any_grace = False

            for t in self.financing.tranches:
                ds = t.annual_debt_service(year)
                tranche_payments[t.name] = ds
                total_ds += ds
                if year <= t.grace_period_years:
                    any_grace = True

            # 2. Compute natural DSCR
            natural_dscr = cfads / total_ds if total_ds > 0 else float('inf')

            # 3. If DSCR too high, we could sculpt DOWN (increase repayment)
            #    If DSCR too low, sculpt UP (reduce commercial repayment)
            adjusted_ds = total_ds
            adjusted_payments = dict(tranche_payments)

            if natural_dscr < self.constraints.min_dscr and total_ds > 0:
                # Need to reduce debt service — cut commercial tranches first
                target_ds = cfads / self.constraints.target_dscr
                reduction_needed = total_ds - target_ds
                adjusted_ds, adjusted_payments = self._reduce_commercial_first(
                    tranche_payments, reduction_needed, year
                )
                shortfall = max(total_ds - adjusted_ds, 0)
                cumulative_shortfall += shortfall

            elif natural_dscr > self.constraints.max_dscr and not any_grace:
                # Over-covered — could accelerate repayment
                target_ds = cfads / self.constraints.target_dscr
                if target_ds > total_ds:
                    # Distribute excess to senior tranches first
                    extra = target_ds - total_ds
                    adjusted_ds, adjusted_payments = self._accelerate_senior(
                        tranche_payments, extra, year
                    )

            # 4. Final DSCR
            dscr = cfads / adjusted_ds if adjusted_ds > 0 else float('inf')
            surplus = cfads - adjusted_ds

            sculpted_year = SculptedYear(
                year=year,
                cfads=cfads,
                total_debt_service=adjusted_ds,
                dscr=dscr,
                is_grace_period=any_grace,
                surplus_cash=surplus,
                is_lock_up=dscr < self.constraints.lock_up_dscr,
                is_compliant=dscr >= self.constraints.min_dscr,
                tranche_payments=adjusted_payments,
            )
            sculpted_years.append(sculpted_year)

        # Aggregate results
        dscr_series = [sy.dscr for sy in sculpted_years]
        min_dscr = min(dscr_series) if dscr_series else 0
        avg_dscr = sum(dscr_series) / len(dscr_series) if dscr_series else 0
        all_compliant = all(sy.is_compliant for sy in sculpted_years)
        lock_up_years = [sy.year for sy in sculpted_years if sy.is_lock_up]

        return {
            "sculpted_profile": [self._year_to_dict(sy) for sy in sculpted_years],
            "summary": {
                "min_dscr": round(min_dscr, 3),
                "avg_dscr": round(avg_dscr, 3),
                "max_dscr": round(max(dscr_series) if dscr_series else 0, 3),
                "all_compliant": all_compliant,
                "lock_up_years": lock_up_years,
                "cumulative_shortfall": round(cumulative_shortfall, 2),
                "total_debt_service": round(
                    sum(sy.total_debt_service for sy in sculpted_years), 2
                ),
                "total_cfads": round(sum(sy.cfads for sy in sculpted_years), 2),
                "grace_period_years": self.financing.max_grace_period(),
                "blended_wacc": round(self.financing.blended_wacc(), 5),
            },
            "constraints_used": {
                "target_dscr": self.constraints.target_dscr,
                "min_dscr": self.constraints.min_dscr,
                "lock_up_dscr": self.constraints.lock_up_dscr,
            },
        }

    def compute_dscr_for_year(self, year: int, cfads: float) -> Dict:
        """
        Compute DSCR for a single year — useful for real-time dashboards.
        """
        total_ds = self.financing.total_annual_debt_service(year)
        dscr = cfads / total_ds if total_ds > 0 else float('inf')
        any_grace = any(
            year <= t.grace_period_years for t in self.financing.tranches
        )
        return {
            "year": year,
            "cfads": cfads,
            "debt_service": total_ds,
            "dscr": round(dscr, 3),
            "is_grace_period": any_grace,
            "is_compliant": dscr >= self.constraints.min_dscr,
            "blended_wacc": round(self.financing.blended_wacc(), 5),
        }

    # --- Internal helpers ---

    def _reduce_commercial_first(
        self,
        payments: Dict[str, float],
        reduction: float,
        year: int,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Reduce commercial tranche payments first, preserve concessional.
        First-loss absorbs before junior, junior before senior.
        """
        adjusted = dict(payments)
        remaining_reduction = reduction

        # Order: first-loss, then mezzanine, then junior, then senior
        for t in sorted(
            self.financing.tranches,
            key=lambda x: -x.seniority_rank,  # Lowest priority first
        ):
            if remaining_reduction <= 0:
                break
            if t.is_concessional:
                continue  # Don't cut concessional — DFI terms are contractual

            current = adjusted.get(t.name, 0)
            # Can reduce up to interest-only floor
            interest_floor = t.amount * t.rate
            max_reduction = max(current - interest_floor, 0)
            actual_reduction = min(remaining_reduction, max_reduction)

            adjusted[t.name] = current - actual_reduction
            remaining_reduction -= actual_reduction

        total_adjusted = sum(adjusted.values())
        return total_adjusted, adjusted

    def _accelerate_senior(
        self,
        payments: Dict[str, float],
        extra: float,
        year: int,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Distribute surplus cash to senior tranches for accelerated repayment.
        """
        adjusted = dict(payments)
        remaining_extra = extra

        # Order: senior first, then junior
        for t in sorted(
            self.financing.tranches,
            key=lambda x: x.seniority_rank,  # Highest priority first
        ):
            if remaining_extra <= 0:
                break
            if year <= t.grace_period_years:
                continue  # Can't accelerate during grace

            # Cap acceleration at 150% of scheduled payment
            current = adjusted.get(t.name, 0)
            max_acceleration = current * 0.5
            actual_extra = min(remaining_extra, max_acceleration)

            adjusted[t.name] = current + actual_extra
            remaining_extra -= actual_extra

        total_adjusted = sum(adjusted.values())
        return total_adjusted, adjusted

    @staticmethod
    def _year_to_dict(sy: SculptedYear) -> Dict:
        return {
            "year": sy.year,
            "cfads": round(sy.cfads, 2),
            "total_debt_service": round(sy.total_debt_service, 2),
            "dscr": round(sy.dscr, 3),
            "is_grace_period": sy.is_grace_period,
            "surplus_cash": round(sy.surplus_cash, 2),
            "is_lock_up": sy.is_lock_up,
            "is_compliant": sy.is_compliant,
            "tranche_payments": {
                k: round(v, 2) for k, v in sy.tranche_payments.items()
            },
        }
