"""
Project Finance Engine - Core Calculation Engine
Orchestrates CFADS, waterfall, debt sculpting, and covenant monitoring
Event-driven with full audit trail
"""
from typing import Dict, List, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal
import json

# Event store integration (will connect to shared event store)
class EventEmitter:
    """Emit events for all financial calculations"""
    
    @staticmethod
    def emit(event_type: str, data: dict, correlation_id: str = None):
        """Emit financial event"""
        # TODO: Connect to shared event store
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data,
            "correlation_id": correlation_id
        }
        print(f"[EVENT] {event_type}: {correlation_id}")
        return event


class ProjectFinanceEngine:
    """
    Main calculation engine for project finance
    Coordinates CFADS, waterfall, debt service, and covenant monitoring
    """
    
    def __init__(self, project_id: str, correlation_id: str = None):
        self.project_id = project_id
        self.correlation_id = correlation_id or f"PROJ-{project_id[:8]}"
        
    
    def calculate_project_metrics(
        self,
        revenue: float,
        opex: float,
        capex: float,
        debt_service: float,
        period: str
    ) -> Dict:
        """
        Calculate key project metrics
        Returns CFADS, DSCR, and other covenant metrics
        """
        # Calculate CFADS (Cash Flow Available for Debt Service)
        cfads = self._calculate_cfads(revenue, opex, capex)
        
        # Calculate DSCR (Debt Service Coverage Ratio)
        dscr = self._calculate_dscr(cfads, debt_service)
        
        # Calculate other metrics
        metrics = {
            "period": period,
            "revenue": revenue,
            "opex": opex,
            "capex": capex,
            "ebitda": revenue - opex,
            "cfads": cfads,
            "debt_service": debt_service,
            "dscr": dscr,
            "cash_available_post_debt": cfads - debt_service,
            "covenant_compliance": {
                "dscr_compliant": dscr >= 1.3,  # Typical covenant
                "dscr_value": dscr,
                "dscr_threshold": 1.3
            }
        }
        
        # Emit event
        EventEmitter.emit(
            "finance.metrics_calculated",
            metrics,
            self.correlation_id
        )
        
        return metrics
    
    
    def _calculate_cfads(self, revenue: float, opex: float, capex: float) -> float:
        """
        Calculate Cash Flow Available for Debt Service
        CFADS = Revenue - OPEX - Maintenance CAPEX - Taxes
        Simplified: CFADS ≈ EBITDA - CapEx - Taxes
        """
        ebitda = revenue - opex
        tax_rate = 0.21  # Typical corporate tax
        taxes = ebitda * tax_rate if ebitda > 0 else 0
        
        cfads = ebitda - capex - taxes
        return max(cfads, 0)  # Can't be negative
    
    
    def _calculate_dscr(self, cfads: float, debt_service: float) -> float:
        """
        Calculate Debt Service Coverage Ratio
        DSCR = CFADS / Debt Service
        Minimum typically 1.3x (varies by lender)
        """
        if debt_service == 0:
            return float('inf')
        return cfads / debt_service
    
    
    def calculate_drawdown(
        self,
        milestone: str,
        total_capex: float,
        spent_to_date: float,
        milestone_percentage: float,
        senior_debt_total: float
    ) -> Dict:
        """
        Calculate debt drawdown for construction milestone
        Critical for construction-finance coupling!
        """
        # Calculate expected spend at this milestone
        expected_spend = total_capex * (milestone_percentage / 100)
        
        # Verify spend is on track
        variance = abs(spent_to_date - expected_spend) / total_capex
        on_track = variance < 0.05  # Within 5%
        
        # Calculate drawdown amount
        drawdown_percentage = milestone_percentage / 100
        drawdown_amount = senior_debt_total * drawdown_percentage
        
        # Cost to complete check (covenant!)
        remaining_capex = total_capex - spent_to_date
        remaining_debt = senior_debt_total * (1 - drawdown_percentage)
        cost_to_complete_ok = remaining_debt >= (remaining_capex * 0.6)  # Debt covers 60%
        
        result = {
            "milestone": milestone,
            "milestone_percentage": milestone_percentage,
            "total_capex": total_capex,
            "spent_to_date": spent_to_date,
            "expected_spend": expected_spend,
            "variance_percentage": variance * 100,
            "on_track": on_track,
            "drawdown_amount": drawdown_amount,
            "drawdown_eligible": on_track and cost_to_complete_ok,
            "covenant_checks": {
                "progress_vs_budget": on_track,
                "cost_to_complete": cost_to_complete_ok,
                "remaining_capex": remaining_capex,
                "remaining_debt": remaining_debt
            }
        }
        
        # Emit event
        EventEmitter.emit(
            "finance.drawdown_calculated",
            result,
            self.correlation_id
        )
        
        return result
    
    
    def calculate_waterfall(
        self,
        cfads: float,
        debt_tranches: List[Dict],
        reserve_requirements: Dict = None
    ) -> Dict:
        """
        Calculate cash flow waterfall
        Priority: Reserves → Senior Debt → Junior Debt → Mezzanine → Equity
        """
        remaining_cash = cfads
        distributions = []
        
        # 1. Reserve accounts (first priority)
        if reserve_requirements:
            for reserve_name, required_amount in reserve_requirements.items():
                allocation = min(remaining_cash, required_amount)
                distributions.append({
                    "priority": 1,
                    "recipient": f"reserve_{reserve_name}",
                    "type": "reserve",
                    "allocated": allocation,
                    "required": required_amount,
                    "fully_funded": allocation >= required_amount
                })
                remaining_cash -= allocation
        
        # 2. Debt tranches (by seniority)
        sorted_tranches = sorted(debt_tranches, key=lambda x: x.get('seniority', 1))
        
        for tranche in sorted_tranches:
            service_amount = tranche.get('service_amount', 0)
            allocation = min(remaining_cash, service_amount)
            
            distributions.append({
                "priority": tranche.get('seniority', 1) + 1,
                "recipient": tranche.get('name', 'unknown'),
                "type": "debt_service",
                "allocated": allocation,
                "required": service_amount,
                "fully_serviced": allocation >= service_amount,
                "seniority": tranche.get('seniority', 1)
            })
            remaining_cash -= allocation
        
        # 3. Equity (last priority)
        if remaining_cash > 0:
            distributions.append({
                "priority": 999,
                "recipient": "equity",
                "type": "equity_distribution",
                "allocated": remaining_cash,
                "required": 0,
                "fully_serviced": True
            })
        
        result = {
            "cfads": cfads,
            "distributions": distributions,
            "equity_distribution": remaining_cash,
            "all_debt_serviced": all(
                d.get('fully_serviced', True) 
                for d in distributions 
                if d['type'] == 'debt_service'
            )
        }
        
        # Emit event
        EventEmitter.emit(
            "finance.waterfall_calculated",
            result,
            self.correlation_id
        )
        
        return result
    
    
    def check_covenants(
        self,
        metrics: Dict,
        covenant_requirements: Dict
    ) -> Dict:
        """
        Check all financial covenants
        Critical for lender confidence!
        """
        checks = []
        all_compliant = True
        
        # DSCR covenant
        if 'dscr_minimum' in covenant_requirements:
            dscr_required = covenant_requirements['dscr_minimum']
            dscr_actual = metrics.get('dscr', 0)
            compliant = dscr_actual >= dscr_required
            
            checks.append({
                "covenant": "DSCR",
                "required": dscr_required,
                "actual": dscr_actual,
                "compliant": compliant,
                "severity": "critical" if not compliant else "ok"
            })
            
            if not compliant:
                all_compliant = False
        
        # Reserve account covenant
        if 'reserve_funded' in covenant_requirements:
            required = covenant_requirements['reserve_funded']
            checks.append({
                "covenant": "Reserve Account",
                "required": required,
                "actual": "check implementation",
                "compliant": True,  # Placeholder
                "severity": "critical"
            })
        
        # Completion guarantee (construction phase)
        if 'completion_guarantee' in covenant_requirements:
            checks.append({
                "covenant": "Completion Guarantee",
                "required": covenant_requirements['completion_guarantee'],
                "actual": "in place",  # Placeholder
                "compliant": True,
                "severity": "critical"
            })
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "all_compliant": all_compliant,
            "checks": checks,
            "breaches": [c for c in checks if not c['compliant']]
        }
        
        # Emit event
        EventEmitter.emit(
            "finance.covenant_checked",
            result,
            self.correlation_id
        )
        
        return result
    
    
    def model_project_lifetime(
        self,
        capacity_mtpd: float,
        price_eur_kg: float,
        opex_eur_kg: float,
        total_capex: float,
        senior_debt_amount: float,
        interest_rate: float,
        tenor_years: int,
        operations_start_year: int = 2027
    ) -> Dict:
        """
        Model full project lifetime cash flows
        Returns year-by-year CFADS, debt service, DSCR
        """
        # Simple annual model
        annual_production_kg = capacity_mtpd * 365  # MTPD to tonnes/year
        annual_revenue = annual_production_kg * price_eur_kg
        annual_opex = annual_production_kg * opex_eur_kg
        
        # Debt service (simplified - equal annual payments)
        annual_debt_service = self._calculate_annual_debt_service(
            senior_debt_amount,
            interest_rate,
            tenor_years
        )
        
        # Year by year
        years = []
        for year in range(operations_start_year, operations_start_year + tenor_years):
            cfads = self._calculate_cfads(annual_revenue, annual_opex, 0)  # No capex in operations
            dscr = self._calculate_dscr(cfads, annual_debt_service)
            
            years.append({
                "year": year,
                "revenue": annual_revenue,
                "opex": annual_opex,
                "cfads": cfads,
                "debt_service": annual_debt_service,
                "dscr": dscr,
                "covenant_compliant": dscr >= 1.3
            })
        
        # Summary metrics
        avg_dscr = sum(y['dscr'] for y in years) / len(years)
        min_dscr = min(y['dscr'] for y in years)
        total_cfads = sum(y['cfads'] for y in years)
        
        result = {
            "project_id": self.project_id,
            "operations_start": operations_start_year,
            "tenor_years": tenor_years,
            "annual_cashflows": years,
            "summary": {
                "avg_dscr": avg_dscr,
                "min_dscr": min_dscr,
                "total_cfads": total_cfads,
                "total_debt_service": annual_debt_service * tenor_years,
                "total_equity_distributions": total_cfads - (annual_debt_service * tenor_years),
                "project_irr": "TBD",  # Would need NPV calculation
                "bankable": min_dscr >= 1.2  # Conservative threshold
            }
        }
        
        # Emit event
        EventEmitter.emit(
            "finance.lifetime_modeled",
            result,
            self.correlation_id
        )
        
        return result
    
    
    def _calculate_annual_debt_service(
        self,
        principal: float,
        rate: float,
        years: int
    ) -> float:
        """
        Calculate annual debt service (principal + interest)
        Using standard annuity formula
        """
        if rate == 0:
            return principal / years
        
        # Annuity formula: PMT = P * [r(1+r)^n] / [(1+r)^n - 1]
        monthly_rate = rate / 12
        months = years * 12
        
        monthly_payment = principal * (
            monthly_rate * (1 + monthly_rate) ** months
        ) / (
            (1 + monthly_rate) ** months - 1
        )
        
        return monthly_payment * 12  # Annual


if __name__ == "__main__":
    # Example usage
    engine = ProjectFinanceEngine(
        project_id="test-project-1",
        correlation_id="CAP-TEST123"
    )
    
    # Calculate metrics
    metrics = engine.calculate_project_metrics(
        revenue=50_000_000,  # €50M/year
        opex=20_000_000,     # €20M/year
        capex=1_000_000,     # €1M maintenance
        debt_service=15_000_000,  # €15M/year
        period="2027-Q1"
    )
    
    print(f"CFADS: €{metrics['cfads']:,.0f}")
    print(f"DSCR: {metrics['dscr']:.2f}x")
    print(f"Compliant: {metrics['covenant_compliance']['dscr_compliant']}")
