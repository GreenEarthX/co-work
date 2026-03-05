"""
Enhanced Project Orchestrator
Production-grade project finance tracking

Includes:
- Technical Readiness (TR1-9) levels
- Drawdown tranches (5 tranches tied to milestones)
- Critical covenants monitoring (DSCR, reserves, equity, etc.)
- Role-based access control
- Lender-grade reporting
"""
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from decimal import Decimal
import json


# ============================================================================
# TECHNICAL READINESS LEVELS
# ============================================================================

class TechnicalReadiness(Enum):
    """Technical Readiness levels for project maturity"""
    TR1 = "concept_study"           # Feasibility study
    TR2 = "pre_feed"                # Pre-FEED engineering
    TR3 = "feed_complete"           # FEED complete, ready for FID
    TR4 = "epc_contract"            # EPC contract signed
    TR5 = "site_preparation"        # Site work underway
    TR6 = "construction_50pct"      # 50% construction complete
    TR7 = "mechanical_complete"     # Construction complete
    TR8 = "commissioning"           # Commissioning phase
    TR9 = "commercial_operation"    # COD achieved


# ============================================================================
# DRAWDOWN TRANCHES
# ============================================================================

@dataclass
class DrawdownTranche:
    """Senior debt drawdown tranche"""
    tranche_number: int
    name: str
    percentage: float  # % of total senior debt
    tr_level: TechnicalReadiness
    milestone_description: str
    conditions: List[str]
    
    def to_dict(self) -> Dict:
        return {
            "tranche_number": self.tranche_number,
            "name": self.name,
            "percentage": self.percentage,
            "tr_level": self.tr_level.value,
            "milestone": self.milestone_description,
            "conditions": self.conditions
        }


class DrawdownSchedule:
    """Standard 5-tranche drawdown schedule"""
    
    @staticmethod
    def get_standard_tranches() -> List[DrawdownTranche]:
        """Get standard 5-tranche senior debt structure"""
        return [
            DrawdownTranche(
                tranche_number=1,
                name="Financial Close",
                percentage=15.0,
                tr_level=TechnicalReadiness.TR4,
                milestone_description="EPC contract signed, all permits obtained",
                conditions=[
                    "Equity contribution: 30% of total capex",
                    "All regulatory permits obtained",
                    "EPC contract executed",
                    "DSRA initially funded",
                    "Insurance policies active",
                    "Land rights secured"
                ]
            ),
            DrawdownTranche(
                tranche_number=2,
                name="Site Preparation Complete",
                percentage=20.0,
                tr_level=TechnicalReadiness.TR5,
                milestone_description="Site prepared, foundations started",
                conditions=[
                    "Equity contribution: 50% of total capex",
                    "Site preparation complete (independent engineer cert)",
                    "Foundation work commenced",
                    "No material EPC delays (>30 days)",
                    "Construction insurance verified",
                    "Environmental compliance verified"
                ]
            ),
            DrawdownTranche(
                tranche_number=3,
                name="Construction 50% Complete",
                percentage=30.0,
                tr_level=TechnicalReadiness.TR6,
                milestone_description="Half of capex deployed, major equipment installed",
                conditions=[
                    "Equity contribution: 75% of total capex",
                    "50% construction complete (independent engineer)",
                    "Major equipment delivered to site",
                    "Cost overruns <5% of budget",
                    "Schedule variance <10%",
                    "No force majeure events"
                ]
            ),
            DrawdownTranche(
                tranche_number=4,
                name="Mechanical Completion",
                percentage=25.0,
                tr_level=TechnicalReadiness.TR7,
                milestone_description="Construction complete, ready for commissioning",
                conditions=[
                    "Equity contribution: 100% of total capex",
                    "Mechanical completion certificate issued",
                    "All equipment installed and tested",
                    "Commissioning plan approved by lender's engineer",
                    "Operations team hired and trained",
                    "O&M contracts executed"
                ]
            ),
            DrawdownTranche(
                tranche_number=5,
                name="Commercial Operation Date",
                percentage=10.0,
                tr_level=TechnicalReadiness.TR9,
                milestone_description="COD achieved, operating at nameplate",
                conditions=[
                    "COD certificate issued",
                    "Performance tests passed (>95% nameplate)",
                    "DSCR ≥ 1.20x achieved for 6 consecutive months",
                    "Completion guarantee released",
                    "Lender's engineer final sign-off",
                    "All punch-list items complete"
                ]
            )
        ]


# ============================================================================
# CRITICAL COVENANTS
# ============================================================================

class CovenantType(Enum):
    """The 5 most critical financial covenants"""
    MINIMUM_DSCR = "minimum_dscr"                    # Most important
    COMPLETION_GUARANTEE = "completion_guarantee"     # Construction phase
    RESERVE_ACCOUNTS = "reserve_accounts"            # Liquidity protection
    MINIMUM_EQUITY = "minimum_equity"                # Skin in the game
    CHANGE_OF_CONTROL = "change_of_control"          # Sponsor stability


@dataclass
class CovenantRequirement:
    """Specific covenant requirement"""
    covenant_type: CovenantType
    threshold: Optional[Decimal] = None
    description: str = ""
    test_frequency: str = "quarterly"
    cure_period_days: int = 30
    breach_consequences: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "covenant_type": self.covenant_type.value,
            "threshold": float(self.threshold) if self.threshold else None,
            "description": self.description,
            "test_frequency": self.test_frequency,
            "cure_period_days": self.cure_period_days,
            "breach_consequences": self.breach_consequences
        }


class StandardCovenants:
    """Standard covenant package for project finance"""
    
    @staticmethod
    def get_standard_covenants() -> List[CovenantRequirement]:
        """Get lender-standard covenant package"""
        return [
            CovenantRequirement(
                covenant_type=CovenantType.MINIMUM_DSCR,
                threshold=Decimal("1.20"),
                description="Minimum Debt Service Coverage Ratio",
                test_frequency="quarterly",
                cure_period_days=30,
                breach_consequences=[
                    "Cash sweep into DSRA",
                    "Restricted distributions",
                    "Accelerated amortization",
                    "Potential event of default if not cured"
                ]
            ),
            CovenantRequirement(
                covenant_type=CovenantType.COMPLETION_GUARANTEE,
                description="Sponsor/EPC completion guarantee until COD + DSCR test",
                test_frequency="milestone",
                cure_period_days=0,
                breach_consequences=[
                    "Sponsor must contribute additional equity",
                    "EPC contractor performance bond called",
                    "Potential project acceleration by lenders"
                ]
            ),
            CovenantRequirement(
                covenant_type=CovenantType.RESERVE_ACCOUNTS,
                description="Maintain required reserve account balances",
                test_frequency="monthly",
                cure_period_days=15,
                breach_consequences=[
                    "DSRA: 6 months debt service",
                    "MMRA: Per maintenance schedule",
                    "Working capital: 3 months OPEX",
                    "Cash trap if deficient"
                ]
            ),
            CovenantRequirement(
                covenant_type=CovenantType.MINIMUM_EQUITY,
                threshold=Decimal("0.30"),
                description="Minimum 30% equity of total capex",
                test_frequency="drawdown",
                cure_period_days=0,
                breach_consequences=[
                    "Debt drawdown suspended",
                    "Additional equity contribution required",
                    "Potential project restructuring"
                ]
            ),
            CovenantRequirement(
                covenant_type=CovenantType.CHANGE_OF_CONTROL,
                description="No change in sponsor ownership >50% without lender consent",
                test_frequency="event_driven",
                cure_period_days=0,
                breach_consequences=[
                    "Event of default",
                    "Mandatory prepayment",
                    "Refinancing required"
                ]
            )
        ]


# ============================================================================
# STAKEHOLDER ROLES & ACCESS CONTROL
# ============================================================================

class StakeholderRole(Enum):
    """Different parties with different access levels"""
    PRODUCER = "producer"
    SENIOR_LENDER = "senior_lender"
    JUNIOR_LENDER = "junior_lender"
    EQUITY_INVESTOR = "equity_investor"
    GRANT_AGENCY = "grant_agency"
    REGULATOR = "regulator"
    AUDITOR = "auditor"
    INDEPENDENT_ENGINEER = "independent_engineer"


@dataclass
class AccessControl:
    """Define what each role can see and do"""
    role: StakeholderRole
    can_view_states: List[str]
    can_perform_actions: List[str]
    data_access_level: str  # 'full', 'financial', 'summary', 'public'
    can_approve_drawdowns: bool = False
    can_waive_covenants: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "role": self.role.value,
            "can_view_states": self.can_view_states,
            "can_perform_actions": self.can_perform_actions,
            "data_access_level": self.data_access_level,
            "can_approve_drawdowns": self.can_approve_drawdowns,
            "can_waive_covenants": self.can_waive_covenants
        }


class RolePermissions:
    """Standard permissions for each stakeholder role"""
    
    @staticmethod
    def get_role_permissions() -> Dict[StakeholderRole, AccessControl]:
        return {
            StakeholderRole.PRODUCER: AccessControl(
                role=StakeholderRole.PRODUCER,
                can_view_states=["all_own_projects"],
                can_perform_actions=["submit_project", "upload_documents", "view_certification", "request_drawdown"],
                data_access_level="full",
                can_approve_drawdowns=False,
                can_waive_covenants=False
            ),
            
            StakeholderRole.SENIOR_LENDER: AccessControl(
                role=StakeholderRole.SENIOR_LENDER,
                can_view_states=["listed", "in_review", "financial_close", "construction", "operating", "settled"],
                can_perform_actions=["review_financials", "approve_drawdown", "monitor_covenants", "request_cure", "declare_default"],
                data_access_level="full",
                can_approve_drawdowns=True,
                can_waive_covenants=True
            ),
            
            StakeholderRole.JUNIOR_LENDER: AccessControl(
                role=StakeholderRole.JUNIOR_LENDER,
                can_view_states=["listed", "in_review", "financial_close", "construction", "operating"],
                can_perform_actions=["review_financials", "monitor_performance"],
                data_access_level="financial",
                can_approve_drawdowns=False,
                can_waive_covenants=False
            ),
            
            StakeholderRole.EQUITY_INVESTOR: AccessControl(
                role=StakeholderRole.EQUITY_INVESTOR,
                can_view_states=["all"],
                can_perform_actions=["contribute_equity", "view_distributions", "vote_major_decisions"],
                data_access_level="full",
                can_approve_drawdowns=False,
                can_waive_covenants=False
            ),
            
            StakeholderRole.GRANT_AGENCY: AccessControl(
                role=StakeholderRole.GRANT_AGENCY,
                can_view_states=["certified", "operating", "settled"],
                can_perform_actions=["verify_compliance", "approve_subsidy", "audit_production"],
                data_access_level="summary",
                can_approve_drawdowns=False,
                can_waive_covenants=False
            ),
            
            StakeholderRole.REGULATOR: AccessControl(
                role=StakeholderRole.REGULATOR,
                can_view_states=["all"],
                can_perform_actions=["audit_compliance", "verify_certifications", "view_audit_trail"],
                data_access_level="full",
                can_approve_drawdowns=False,
                can_waive_covenants=False
            ),
            
            StakeholderRole.AUDITOR: AccessControl(
                role=StakeholderRole.AUDITOR,
                can_view_states=["modeled", "certified", "funded", "operating"],
                can_perform_actions=["view_financials", "verify_calculations", "access_audit_trail"],
                data_access_level="full",
                can_approve_drawdowns=False,
                can_waive_covenants=False
            ),
            
            StakeholderRole.INDEPENDENT_ENGINEER: AccessControl(
                role=StakeholderRole.INDEPENDENT_ENGINEER,
                can_view_states=["construction", "commissioning", "operating"],
                can_perform_actions=["certify_milestones", "verify_completion", "inspect_quality"],
                data_access_level="summary",
                can_approve_drawdowns=False,
                can_waive_covenants=False
            )
        }


# ============================================================================
# ENHANCED PROJECT STATES
# ============================================================================

class EnhancedProjectState(Enum):
    """Enhanced project states with TR levels"""
    # Pre-financing
    SUBMITTED = ("submitted", TechnicalReadiness.TR1)
    EVALUATING = ("evaluating", TechnicalReadiness.TR1)
    EVALUATED = ("evaluated", TechnicalReadiness.TR2)
    MODELING = ("modeling", TechnicalReadiness.TR2)
    MODELED = ("modeled", TechnicalReadiness.TR3)
    
    # Certification
    CERTIFICATION_PENDING = ("certification_pending", TechnicalReadiness.TR3)
    CERTIFIED = ("certified", TechnicalReadiness.TR3)
    
    # Lender review
    LISTED = ("listed", TechnicalReadiness.TR3)
    IN_REVIEW = ("in_review", TechnicalReadiness.TR3)
    
    # Financial close
    FINANCIAL_CLOSE = ("financial_close", TechnicalReadiness.TR4)
    
    # Construction (with tranches)
    CONSTRUCTION_SITE_PREP = ("construction_site_prep", TechnicalReadiness.TR5)
    CONSTRUCTION_50PCT = ("construction_50pct", TechnicalReadiness.TR6)
    MECHANICAL_COMPLETE = ("mechanical_complete", TechnicalReadiness.TR7)
    COMMISSIONING = ("commissioning", TechnicalReadiness.TR8)
    
    # Operations
    COD_ACHIEVED = ("cod_achieved", TechnicalReadiness.TR9)
    OPERATING = ("operating", TechnicalReadiness.TR9)
    
    # Settlement
    SETTLING = ("settling", TechnicalReadiness.TR9)
    SETTLED = ("settled", TechnicalReadiness.TR9)
    
    # Terminal
    REJECTED = ("rejected", None)
    CANCELLED = ("cancelled", None)
    FAILED = ("failed", None)
    
    def __init__(self, state_name: str, tr_level: Optional[TechnicalReadiness]):
        self.state_name = state_name
        self.tr_level = tr_level


# ============================================================================
# COVENANT MONITOR
# ============================================================================

class CovenantMonitor:
    """Monitor and enforce financial covenants"""
    
    def __init__(self):
        self.covenants = StandardCovenants.get_standard_covenants()
    
    async def check_dscr_covenant(
        self,
        project_id: str,
        cfads: Decimal,
        debt_service: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """Check if DSCR meets minimum threshold"""
        if debt_service == 0:
            return True, None
        
        dscr = cfads / debt_service
        min_dscr = Decimal("1.20")
        
        if dscr < min_dscr:
            return False, f"DSCR {dscr:.2f}x below minimum {min_dscr}x"
        
        return True, None
    
    async def check_reserve_accounts(
        self,
        project_id: str,
        dsra_balance: Decimal,
        required_dsra: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """Check reserve account funding"""
        if dsra_balance < required_dsra:
            shortfall = required_dsra - dsra_balance
            return False, f"DSRA shortfall: {shortfall:,.0f}"
        
        return True, None
    
    async def check_equity_contribution(
        self,
        equity_contributed: Decimal,
        total_capex: Decimal,
        required_percentage: Decimal = Decimal("0.30")
    ) -> Tuple[bool, Optional[str]]:
        """Check minimum equity contribution"""
        equity_pct = equity_contributed / total_capex
        
        if equity_pct < required_percentage:
            return False, f"Equity {equity_pct:.1%} below minimum {required_percentage:.1%}"
        
        return True, None


# ============================================================================
# DRAWDOWN MANAGER
# ============================================================================

class DrawdownManager:
    """Manage debt drawdown approvals"""
    
    def __init__(self):
        self.tranches = DrawdownSchedule.get_standard_tranches()
    
    async def can_drawdown_tranche(
        self,
        project_id: str,
        tranche_number: int,
        project_state: EnhancedProjectState
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Check if tranche can be drawn
        
        Returns: (can_draw, conditions_met, conditions_not_met)
        """
        if tranche_number < 1 or tranche_number > 5:
            return False, [], ["Invalid tranche number"]
        
        tranche = self.tranches[tranche_number - 1]
        
        # Check TR level
        if project_state.tr_level != tranche.tr_level:
            return False, [], [f"Project must be at {tranche.tr_level.value}"]
        
        # In production, check actual conditions from database
        # For now, return structure
        conditions_met = []
        conditions_not_met = []
        
        return True, conditions_met, conditions_not_met
    
    def get_tranche_info(self, tranche_number: int) -> Optional[DrawdownTranche]:
        """Get information about a specific tranche"""
        if 1 <= tranche_number <= 5:
            return self.tranches[tranche_number - 1]
        return None


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # Show drawdown schedule
    print("\n" + "="*60)
    print("STANDARD DRAWDOWN SCHEDULE")
    print("="*60)
    
    schedule = DrawdownSchedule.get_standard_tranches()
    for tranche in schedule:
        print(f"\nTranche {tranche.tranche_number}: {tranche.name}")
        print(f"  Amount: {tranche.percentage}% of senior debt")
        print(f"  TR Level: {tranche.tr_level.value}")
        print(f"  Milestone: {tranche.milestone_description}")
        print(f"  Conditions:")
        for cond in tranche.conditions:
            print(f"    - {cond}")
    
    # Show covenants
    print("\n" + "="*60)
    print("CRITICAL COVENANTS")
    print("="*60)
    
    covenants = StandardCovenants.get_standard_covenants()
    for cov in covenants:
        print(f"\n{cov.covenant_type.value.upper()}")
        print(f"  Description: {cov.description}")
        if cov.threshold:
            print(f"  Threshold: {cov.threshold}")
        print(f"  Test Frequency: {cov.test_frequency}")
        print(f"  Cure Period: {cov.cure_period_days} days")
        print(f"  Breach Consequences:")
        for cons in cov.breach_consequences:
            print(f"    - {cons}")
    
    # Show role permissions
    print("\n" + "="*60)
    print("STAKEHOLDER PERMISSIONS")
    print("="*60)
    
    permissions = RolePermissions.get_role_permissions()
    for role, access in permissions.items():
        print(f"\n{role.value.upper()}")
        print(f"  Data Access: {access.data_access_level}")
        print(f"  Can Approve Drawdowns: {access.can_approve_drawdowns}")
        print(f"  Can Waive Covenants: {access.can_waive_covenants}")
        print(f"  Actions: {', '.join(access.can_perform_actions[:3])}...")
