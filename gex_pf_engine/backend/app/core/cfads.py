"""
CFADS Calculator - Cash Flow Available for Debt Service
Specialized for green fuel projects with subsidy tracking
"""
from typing import Dict, List, Optional
from datetime import date
from decimal import Decimal


class CFADSCalculator:
    """
    Calculate CFADS for green fuel projects
    Accounts for:
    - Production revenue (offtake contracts)
    - Subsidies (45V, RED III, feed-in tariffs)
    - Operating costs
    - Maintenance capex
    - Working capital
    - Taxes
    """
    
    @staticmethod
    def calculate(
        production_volume_mtpd: float,
        offtake_price_eur_kg: float,
        subsidies: Dict[str, float] = None,
        opex_eur_kg: float = 0,
        maintenance_capex: float = 0,
        working_capital_change: float = 0,
        tax_rate: float = 0.21,
        period_days: int = 365
    ) -> Dict:
        """
        Calculate CFADS for a given period
        
        Args:
            production_volume_mtpd: Metric tonnes per day capacity
            offtake_price_eur_kg: Price per kg from offtake contracts
            subsidies: Dict of subsidy types and amounts (e.g., {'45V': 3.0, 'RED_III': 0.5})
            opex_eur_kg: Operating cost per kg
            maintenance_capex: Annual maintenance capital expenditure
            working_capital_change: Change in working capital (negative = cash out)
            tax_rate: Corporate tax rate
            period_days: Days in the period
        
        Returns:
            Dict with detailed CFADS breakdown
        """
        
        # 1. PRODUCTION REVENUE
        annual_production_kg = production_volume_mtpd * period_days
        base_revenue = annual_production_kg * offtake_price_eur_kg
        
        # 2. SUBSIDY REVENUE
        subsidy_revenue = 0
        subsidy_breakdown = {}
        if subsidies:
            for subsidy_type, value_eur_kg in subsidies.items():
                subsidy_amount = annual_production_kg * value_eur_kg
                subsidy_breakdown[subsidy_type] = subsidy_amount
                subsidy_revenue += subsidy_amount
        
        # 3. TOTAL REVENUE
        total_revenue = base_revenue + subsidy_revenue
        
        # 4. OPERATING COSTS
        total_opex = annual_production_kg * opex_eur_kg
        
        # 5. EBITDA
        ebitda = total_revenue - total_opex
        
        # 6. MAINTENANCE CAPEX
        # (Major capex is separate - this is just maintenance)
        
        # 7. WORKING CAPITAL
        # Negative = cash outflow (need to fund inventory, receivables)
        # Positive = cash inflow (collecting receivables, reducing inventory)
        
        # 8. TAXABLE INCOME
        taxable_income = ebitda - maintenance_capex
        
        # 9. TAXES
        taxes = max(taxable_income * tax_rate, 0) if taxable_income > 0 else 0
        
        # 10. CFADS
        cfads = (
            ebitda 
            - maintenance_capex 
            - working_capital_change 
            - taxes
        )
        
        return {
            "period_days": period_days,
            "production_kg": annual_production_kg,
            "production_mtpd": production_volume_mtpd,
            
            # Revenue breakdown
            "base_revenue": base_revenue,
            "subsidy_revenue": subsidy_revenue,
            "subsidy_breakdown": subsidy_breakdown,
            "total_revenue": total_revenue,
            
            # Cost breakdown
            "opex": total_opex,
            "opex_per_kg": opex_eur_kg,
            "maintenance_capex": maintenance_capex,
            "working_capital_change": working_capital_change,
            
            # Profitability
            "ebitda": ebitda,
            "ebitda_margin": (ebitda / total_revenue * 100) if total_revenue > 0 else 0,
            
            # Taxes
            "taxable_income": taxable_income,
            "taxes": taxes,
            "effective_tax_rate": (taxes / taxable_income * 100) if taxable_income > 0 else 0,
            
            # Final CFADS
            "cfads": cfads,
            "cfads_margin": (cfads / total_revenue * 100) if total_revenue > 0 else 0
        }
    
    
    @staticmethod
    def calculate_with_offtake_contracts(
        contracts: List[Dict],
        production_mtpd: float,
        subsidies: Dict[str, float] = None,
        opex_eur_kg: float = 0,
        period: str = "2027"
    ) -> Dict:
        """
        Calculate CFADS using actual offtake contracts
        Matches what we have in the trading platform!
        
        Args:
            contracts: List of contract dicts with volume_mtpd and price_eur_kg
            production_mtpd: Total production capacity
            subsidies: Subsidy amounts per kg
            opex_eur_kg: Operating cost per kg
            period: Year or period identifier
        
        Returns:
            CFADS breakdown with contract-level detail
        """
        
        # Sum up contracted volumes and revenues
        total_contracted_mtpd = sum(c.get('volume_mtpd', 0) for c in contracts)
        
        # Check if fully contracted
        utilization = min(total_contracted_mtpd / production_mtpd, 1.0) if production_mtpd > 0 else 0
        
        # Calculate revenue from each contract
        contract_revenues = []
        total_contract_revenue = 0
        
        for contract in contracts:
            volume = contract.get('volume_mtpd', 0)
            price = contract.get('price_eur_kg', 0)
            annual_kg = volume * 365
            revenue = annual_kg * price
            
            contract_revenues.append({
                "contract_id": contract.get('id', 'unknown'),
                "counterparty": contract.get('counterparty', 'unknown'),
                "volume_mtpd": volume,
                "price_eur_kg": price,
                "annual_revenue": revenue
            })
            
            total_contract_revenue += revenue
        
        # Calculate using contracted volume
        effective_production_mtpd = min(total_contracted_mtpd, production_mtpd)
        
        cfads_result = CFADSCalculator.calculate(
            production_volume_mtpd=effective_production_mtpd,
            offtake_price_eur_kg=0,  # Revenue calculated from contracts
            subsidies=subsidies,
            opex_eur_kg=opex_eur_kg
        )
        
        # Override revenue with contract revenue
        cfads_result['base_revenue'] = total_contract_revenue
        cfads_result['total_revenue'] = total_contract_revenue + cfads_result['subsidy_revenue']
        cfads_result['ebitda'] = cfads_result['total_revenue'] - cfads_result['opex']
        
        # Recalculate CFADS
        cfads_result['cfads'] = (
            cfads_result['ebitda']
            - cfads_result['maintenance_capex']
            - cfads_result['working_capital_change']
            - cfads_result['taxes']
        )
        
        # Add contract details
        cfads_result['contracts'] = contract_revenues
        cfads_result['utilization'] = utilization * 100
        cfads_result['uncontracted_capacity_mtpd'] = production_mtpd - total_contracted_mtpd
        
        return cfads_result
    
    
    @staticmethod
    def calculate_lifetime_cfads(
        production_mtpd: float,
        offtake_price_eur_kg: float,
        opex_eur_kg: float,
        subsidies: Dict[str, float],
        start_year: int,
        end_year: int,
        ramp_up_years: int = 1
    ) -> List[Dict]:
        """
        Calculate CFADS year-by-year over project lifetime
        Includes production ramp-up period
        
        Args:
            production_mtpd: Full capacity
            offtake_price_eur_kg: Contract price
            opex_eur_kg: Operating cost
            subsidies: Subsidy dict
            start_year: First year of operations
            end_year: Last year of operations
            ramp_up_years: Years to reach full production
        
        Returns:
            List of yearly CFADS calculations
        """
        yearly_cfads = []
        
        for year_offset in range(end_year - start_year + 1):
            year = start_year + year_offset
            
            # Production ramp-up
            if year_offset < ramp_up_years:
                production_factor = (year_offset + 1) / ramp_up_years
            else:
                production_factor = 1.0
            
            effective_production = production_mtpd * production_factor
            
            # Calculate for this year
            cfads_year = CFADSCalculator.calculate(
                production_volume_mtpd=effective_production,
                offtake_price_eur_kg=offtake_price_eur_kg,
                subsidies=subsidies,
                opex_eur_kg=opex_eur_kg
            )
            
            cfads_year['year'] = year
            cfads_year['production_factor'] = production_factor
            
            yearly_cfads.append(cfads_year)
        
        return yearly_cfads


if __name__ == "__main__":
    # Example: Green H2 project with subsidies
    result = CFADSCalculator.calculate(
        production_volume_mtpd=50.0,  # 50 tonnes/day
        offtake_price_eur_kg=6.0,     # €6/kg from offtake
        subsidies={
            '45V': 3.0,      # US Production Tax Credit: $3/kg
            'RED_III': 0.5   # EU support: €0.5/kg
        },
        opex_eur_kg=2.0,              # €2/kg operating cost
        maintenance_capex=1_000_000,  # €1M/year maintenance
        tax_rate=0.21
    )
    
    print(f"Annual CFADS: €{result['cfads']:,.0f}")
    print(f"EBITDA Margin: {result['ebitda_margin']:.1f}%")
    print(f"Subsidy Revenue: €{result['subsidy_revenue']:,.0f}")
