"""
Cash Flow Waterfall - Payment Priority Logic
Manages distribution of CFADS across reserves, debt tranches, and equity.
Supports concessional (DFI) tranches with grace periods via debt.tranche.
"""
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from .debt.tranche import Tranche, TrancheType, FinancingStructure


class Priority(Enum):
    """Payment priority levels"""
    RESERVE = 1
    SENIOR_DEBT = 2
    JUNIOR_DEBT = 3
    MEZZANINE = 4
    EQUITY = 5


@dataclass
class WaterfallItem:
    """Single item in the waterfall"""
    priority: int
    name: str
    category: str  # 'reserve', 'debt', 'equity'
    required_amount: float
    allocated_amount: float = 0.0
    
    @property
    def shortfall(self) -> float:
        return max(self.required_amount - self.allocated_amount, 0)
    
    @property
    def fully_funded(self) -> bool:
        return self.allocated_amount >= self.required_amount
    
    @property
    def funding_percentage(self) -> float:
        if self.required_amount == 0:
            return 100.0
        return (self.allocated_amount / self.required_amount) * 100


class CashFlowWaterfall:
    """
    Execute cash flow waterfall distribution
    Priority order (typical):
    1. Reserve accounts (DSRA, maintenance, etc.)
    2. Senior debt service (principal + interest)
    3. Junior debt service
    4. Mezzanine debt service
    5. Equity distributions
    """
    
    def __init__(self):
        self.items: List[WaterfallItem] = []
    
    
    def add_reserve(self, name: str, required_amount: float, priority: int = 1):
        """Add reserve account requirement"""
        self.items.append(WaterfallItem(
            priority=priority,
            name=name,
            category='reserve',
            required_amount=required_amount
        ))
    
    
    def add_debt(
        self,
        name: str,
        principal: float,
        interest: float,
        seniority: int = 2  # 2=senior, 3=junior, 4=mezzanine
    ):
        """Add debt service requirement"""
        self.items.append(WaterfallItem(
            priority=seniority,
            name=name,
            category='debt',
            required_amount=principal + interest
        ))
    
    
    def execute(self, available_cash: float) -> Dict:
        """
        Execute waterfall distribution
        
        Args:
            available_cash: CFADS available for distribution
        
        Returns:
            Dict with distribution details and remaining cash
        """
        remaining_cash = available_cash
        distributions = []
        
        # Sort by priority
        sorted_items = sorted(self.items, key=lambda x: (x.priority, x.name))
        
        # Distribute to each item in priority order
        for item in sorted_items:
            allocation = min(remaining_cash, item.required_amount)
            item.allocated_amount = allocation
            remaining_cash -= allocation
            
            distributions.append({
                "priority": item.priority,
                "name": item.name,
                "category": item.category,
                "required": item.required_amount,
                "allocated": item.allocated_amount,
                "shortfall": item.shortfall,
                "fully_funded": item.fully_funded,
                "funding_percentage": item.funding_percentage
            })
        
        # Check if all required payments made
        all_reserves_funded = all(
            d['fully_funded'] 
            for d in distributions 
            if d['category'] == 'reserve'
        )
        
        all_debt_serviced = all(
            d['fully_funded']
            for d in distributions
            if d['category'] == 'debt'
        )
        
        total_shortfall = sum(d['shortfall'] for d in distributions)
        
        return {
            "available_cash": available_cash,
            "distributions": distributions,
            "remaining_for_equity": remaining_cash,
            "total_distributed": available_cash - remaining_cash,
            "total_shortfall": total_shortfall,
            "all_reserves_funded": all_reserves_funded,
            "all_debt_serviced": all_debt_serviced,
            "covenant_compliant": all_reserves_funded and all_debt_serviced
        }
    
    
    @staticmethod
    def create_typical_structure(
        cfads: float,
        senior_debt_service: float,
        junior_debt_service: float = 0,
        mezzanine_service: float = 0,
        dsra_required: float = 0,
        maintenance_reserve: float = 0
    ) -> Dict:
        """
        Create and execute typical waterfall structure
        
        Args:
            cfads: Cash flow available
            senior_debt_service: Annual senior debt payment
            junior_debt_service: Annual junior debt payment
            mezzanine_service: Annual mezzanine payment
            dsra_required: Debt Service Reserve Account requirement
            maintenance_reserve: Maintenance reserve requirement
        
        Returns:
            Waterfall execution results
        """
        waterfall = CashFlowWaterfall()
        
        # 1. Reserves (highest priority)
        if dsra_required > 0:
            waterfall.add_reserve("DSRA", dsra_required, priority=1)
        
        if maintenance_reserve > 0:
            waterfall.add_reserve("Maintenance Reserve", maintenance_reserve, priority=1)
        
        # 2. Senior Debt
        if senior_debt_service > 0:
            waterfall.add_debt(
                "Senior Debt",
                principal=senior_debt_service * 0.6,  # Rough split
                interest=senior_debt_service * 0.4,
                seniority=2
            )
        
        # 3. Junior Debt
        if junior_debt_service > 0:
            waterfall.add_debt(
                "Junior Debt",
                principal=junior_debt_service * 0.5,
                interest=junior_debt_service * 0.5,
                seniority=3
            )
        
        # 4. Mezzanine
        if mezzanine_service > 0:
            waterfall.add_debt(
                "Mezzanine",
                principal=mezzanine_service * 0.3,
                interest=mezzanine_service * 0.7,
                seniority=4
            )
        
        # Execute
        return waterfall.execute(cfads)
    
    
    @staticmethod
    def create_green_project_waterfall(
        cfads: float,
        financing_structure: Dict
    ) -> Dict:
        """
        Create waterfall for green project financing structure
        Based on the typical structure you showed me!
        
        Args:
            cfads: Annual CFADS
            financing_structure: Dict with:
                - senior_debt: {amount, rate, tenor}
                - junior_debt: {amount, rate, tenor}
                - mezzanine: {amount, rate, tenor}
                - green_bond: {amount, rate, tenor}
                - dfi_funding: {amount, rate, tenor}
        
        Returns:
            Waterfall execution with green finance specifics
        """
        waterfall = CashFlowWaterfall()
        
        # Reserve requirements (6 months of debt service is typical)
        total_annual_debt = 0
        
        # Senior Debt (45-60% of capital stack)
        if 'senior_debt' in financing_structure:
            senior = financing_structure['senior_debt']
            annual_service = CashFlowWaterfall._calculate_debt_service(
                senior['amount'],
                senior['rate'],
                senior['tenor']
            )
            total_annual_debt += annual_service
            waterfall.add_debt("Senior Debt", 0, annual_service, seniority=2)
        
        # Junior/Subordinated Debt (12-15%)
        if 'junior_debt' in financing_structure:
            junior = financing_structure['junior_debt']
            annual_service = CashFlowWaterfall._calculate_debt_service(
                junior['amount'],
                junior['rate'],
                junior['tenor']
            )
            total_annual_debt += annual_service
            waterfall.add_debt("Junior Debt", 0, annual_service, seniority=3)
        
        # Mezzanine (2-3%)
        if 'mezzanine' in financing_structure:
            mezz = financing_structure['mezzanine']
            annual_service = CashFlowWaterfall._calculate_debt_service(
                mezz['amount'],
                mezz['rate'],
                mezz['tenor']
            )
            total_annual_debt += annual_service
            waterfall.add_debt("Mezzanine", 0, annual_service, seniority=4)
        
        # Green Bonds (4-8%)
        if 'green_bond' in financing_structure:
            bond = financing_structure['green_bond']
            annual_service = CashFlowWaterfall._calculate_debt_service(
                bond['amount'],
                bond['rate'],
                bond['tenor']
            )
            total_annual_debt += annual_service
            waterfall.add_debt("Green Bond", 0, annual_service, seniority=2)  # Often senior
        
        # DFI/IFC Funding (10-12%)
        if 'dfi_funding' in financing_structure:
            dfi = financing_structure['dfi_funding']
            annual_service = CashFlowWaterfall._calculate_debt_service(
                dfi['amount'],
                dfi['rate'],
                dfi['tenor']
            )
            total_annual_debt += annual_service
            waterfall.add_debt("DFI Funding", 0, annual_service, seniority=2)  # Senior-like
        
        # DSRA = 6 months of total debt service
        dsra_required = total_annual_debt / 2
        waterfall.add_reserve("DSRA", dsra_required, priority=1)
        
        # Execute
        result = waterfall.execute(cfads)
        
        # Add financing structure summary
        result['financing_structure'] = financing_structure
        result['total_annual_debt_service'] = total_annual_debt
        result['dsra_required'] = dsra_required
        
        return result
    
    
    @staticmethod
    def _calculate_debt_service(principal: float, rate: float, tenor: int) -> float:
        """Calculate annual debt service using annuity formula"""
        if rate == 0:
            return principal / tenor
        
        annual_payment = principal * (rate * (1 + rate) ** tenor) / ((1 + rate) ** tenor - 1)
        return annual_payment


    @staticmethod
    def create_from_financing_structure(
        cfads: float,
        structure: FinancingStructure,
        year: int = 1,
    ) -> Dict:
        """
        Create waterfall from a FinancingStructure (supports concessional/DFI).
        Uses Tranche.annual_debt_service(year) which respects grace periods.

        Args:
            cfads: Annual CFADS for this year
            structure: FinancingStructure with typed tranches
            year: Project year (1-indexed) — affects grace period logic

        Returns:
            Waterfall execution with concessional metrics
        """
        waterfall = CashFlowWaterfall()
        total_annual_debt = 0.0
        tranche_details = []

        for t in structure.tranches:
            annual_service = t.annual_debt_service(year)
            total_annual_debt += annual_service
            in_grace = year <= t.grace_period_years

            waterfall.add_debt(
                t.name,
                principal=0,
                interest=annual_service,
                seniority=t.seniority_rank,
            )
            tranche_details.append({
                "name": t.name,
                "type": t.tranche_type.value,
                "amount": t.amount,
                "rate": t.rate,
                "annual_service": annual_service,
                "in_grace_period": in_grace,
                "is_concessional": t.is_concessional,
                "dfi_provider": t.dfi_provider.value if t.dfi_provider else None,
            })

        # DSRA = 6 months of total debt service
        dsra_required = total_annual_debt / 2
        if dsra_required > 0:
            waterfall.add_reserve("DSRA", dsra_required, priority=1)

        result = waterfall.execute(cfads)

        # DSCR
        dscr = cfads / total_annual_debt if total_annual_debt > 0 else float('inf')

        result["year"] = year
        result["tranche_details"] = tranche_details
        result["total_annual_debt_service"] = total_annual_debt
        result["dsra_required"] = dsra_required
        result["dscr"] = round(dscr, 3)
        result["blended_wacc"] = round(structure.blended_wacc(), 5)
        result["blended_debt_cost"] = round(structure.blended_debt_cost(), 5)
        result["concessional_share"] = round(structure.concessional_share, 4)
        result["catalytic_ratio"] = round(structure.catalytic_ratio, 2) if structure.catalytic_ratio != float('inf') else None
        result["financing_summary"] = structure.to_dict()

        return result


    @staticmethod
    def create_multi_currency_waterfall(
        cfads_by_currency: Dict[str, float],
        structure: FinancingStructure,
        year: int = 1,
    ) -> Dict:
        """
        Multi-currency waterfall. Converts all CFADS to base currency
        using the FinancingStructure's base_currency, then runs waterfall.

        Args:
            cfads_by_currency: e.g. {"EUR": 20_000_000, "USD": 5_000_000}
            structure: FinancingStructure with FX rates on tranches
            year: Project year

        Returns:
            Waterfall execution with FX breakdown
        """
        # Sum CFADS in base currency (assumes cfads_by_currency keys match tranche currencies)
        # For now, treat all amounts as already in base currency
        total_cfads_base = sum(cfads_by_currency.values())

        result = CashFlowWaterfall.create_from_financing_structure(
            cfads=total_cfads_base,
            structure=structure,
            year=year,
        )
        result["cfads_by_currency"] = cfads_by_currency
        result["base_currency"] = structure.base_currency
        return result


class CashSweep:
    """
    Post-waterfall excess cash sweep mechanism.
    Applies lock-up tests (DSCR floor, LLCR floor) before
    allowing equity distributions.
    """

    def __init__(
        self,
        dscr_lock_up: float = 1.10,
        dscr_default: float = 1.05,
        llcr_lock_up: float = 1.15,
        sweep_pct: float = 0.50,
    ):
        self.dscr_lock_up = dscr_lock_up
        self.dscr_default = dscr_default
        self.llcr_lock_up = llcr_lock_up
        self.sweep_pct = sweep_pct

    def apply(self, waterfall_result: Dict, llcr: float = 999.0) -> Dict:
        """
        Apply sweep/lock-up logic to waterfall output.

        Returns updated result with:
          - sweep_applied: bool
          - equity_distribution: float (may be reduced)
          - sweep_to_debt: float (excess redirected to prepayment)
          - lock_up_triggered: bool
          - default_triggered: bool
        """
        dscr = waterfall_result.get("dscr", float("inf"))
        excess = waterfall_result.get("remaining_for_equity", 0)

        default_triggered = dscr < self.dscr_default
        lock_up_triggered = dscr < self.dscr_lock_up or llcr < self.llcr_lock_up

        if default_triggered:
            # All cash trapped — no equity distribution
            equity_dist = 0.0
            sweep_to_debt = excess
        elif lock_up_triggered:
            # Partial sweep — excess cash prepays debt
            sweep_to_debt = excess * self.sweep_pct
            equity_dist = excess - sweep_to_debt
        else:
            # No constraint — full equity distribution
            equity_dist = excess
            sweep_to_debt = 0.0

        waterfall_result["cash_sweep"] = {
            "dscr_lock_up_threshold": self.dscr_lock_up,
            "dscr_default_threshold": self.dscr_default,
            "llcr_lock_up_threshold": self.llcr_lock_up,
            "actual_dscr": round(dscr, 3) if dscr != float("inf") else None,
            "actual_llcr": round(llcr, 3) if llcr != 999.0 else None,
            "lock_up_triggered": lock_up_triggered,
            "default_triggered": default_triggered,
            "sweep_pct": self.sweep_pct,
            "sweep_to_debt_prepayment": round(sweep_to_debt, 2),
            "equity_distribution": round(equity_dist, 2),
        }
        waterfall_result["remaining_for_equity"] = round(equity_dist, 2)

        return waterfall_result


if __name__ == "__main__":
    # Example: Green H2 project waterfall
    result = CashFlowWaterfall.create_typical_structure(
        cfads=25_000_000,              # €25M CFADS
        senior_debt_service=15_000_000,  # €15M/year
        junior_debt_service=3_000_000,   # €3M/year
        dsra_required=9_000_000,         # 6 months coverage
        maintenance_reserve=1_000_000    # €1M
    )
    
    print(f"Equity Distribution: €{result['remaining_for_equity']:,.0f}")
    print(f"All Debt Serviced: {result['all_debt_serviced']}")
    print(f"Covenant Compliant: {result['covenant_compliant']}")
