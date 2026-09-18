"""
Tranche & Financing Structure - DFI/Concessional Finance Layer
Models individual debt tranches including concessional instruments (IFC, EIB, KfW, etc.)
and computes blended WACC across the full capital stack.
"""
from typing import Dict, List, Optional
from enum import Enum
from dataclasses import dataclass, field


class TrancheType(Enum):
    """Debt instrument classification"""
    SENIOR = "senior"
    JUNIOR = "junior"
    MEZZANINE = "mezzanine"
    GREEN_BOND = "green_bond"
    ESG_LINKED = "esg_linked"                    # ESG-linked with KPI margin ratchet
    CONCESSIONAL = "concessional"
    CONCESSIONAL_FIRST_LOSS = "concessional_first_loss"


class DFIProvider(Enum):
    """Development Finance Institution identifiers"""
    IFC = "IFC"         # International Finance Corporation
    EIB = "EIB"         # European Investment Bank
    EBRD = "EBRD"       # European Bank for Reconstruction and Development
    KFW = "KfW"         # Kreditanstalt fur Wiederaufbau
    DEG = "DEG"         # Deutsche Investitions- und Entwicklungsgesellschaft
    FMO = "FMO"         # Nederlandse Financierings-Maatschappij
    PROPARCO = "PROPARCO"
    AfDB = "AfDB"       # African Development Bank
    ADB = "ADB"         # Asian Development Bank
    GCF = "GCF"         # Green Climate Fund
    CIF = "CIF"         # Climate Investment Funds
    BPI = "BPI"         # Bpifrance (French Public Investment Bank)
    DFC = "DFC"         # US International Development Finance Corporation
    OTHER = "OTHER"


@dataclass
class Tranche:
    """
    Single financing tranche in the capital stack.
    Handles both commercial and concessional instruments.
    """
    name: str
    tranche_type: TrancheType
    amount: float                           # In denomination currency
    rate: float                             # Annual rate (e.g. 0.045 = 4.5%)
    tenor: int                              # Years
    grace_period_years: int = 0             # Interest-only period (DFI standard: 2-5y)
    dfi_provider: Optional[DFIProvider] = None
    is_first_loss: bool = False             # First-loss position absorbs losses first
    additionality_pct: float = 0.0          # % of capital this tranche mobilises
    green_bond_framework: Optional[str] = None  # e.g. "ICMA GBP 2021"
    use_of_proceeds: Optional[str] = None       # e.g. "Electrolyser procurement"
    esg_kpi_description: Optional[str] = None   # e.g. "GHG intensity <2 kgCO2e/kgH2 by 2028"
    margin_ratchet_bps: int = 0                 # Step-up/down on KPI miss/hit
    currency: str = "EUR"                       # ISO 4217 code
    fx_rate_to_base: float = 1.0                # Conversion rate to project base currency
    fx_hedge_id: Optional[str] = None           # Link to FX hedge instrument

    @property
    def is_concessional(self) -> bool:
        """Concessional = below-market rate or DFI-backed"""
        return self.tranche_type in (
            TrancheType.CONCESSIONAL,
            TrancheType.CONCESSIONAL_FIRST_LOSS,
        ) or self.dfi_provider is not None

    @property
    def seniority_rank(self) -> int:
        """
        Payment priority in waterfall.
        1 = most senior (reserves), 2 = senior debt, etc.
        Concessional first-loss sits BELOW mezzanine.
        """
        rank_map = {
            TrancheType.SENIOR: 2,
            TrancheType.GREEN_BOND: 2,          # Green bonds are typically senior
            TrancheType.ESG_LINKED: 2,          # ESG-linked typically senior ranking
            TrancheType.CONCESSIONAL: 2,        # Concessional often pari-passu with senior
            TrancheType.JUNIOR: 3,
            TrancheType.MEZZANINE: 4,
            TrancheType.CONCESSIONAL_FIRST_LOSS: 5,  # Absorbs first losses
        }
        return rank_map.get(self.tranche_type, 3)

    def annual_debt_service(self, year: int) -> float:
        """
        Compute annual debt service for a given project year (1-indexed).
        Returns amount in base currency (FX-converted).
        During grace period: interest-only.
        After grace: standard annuity on remaining principal.
        Beyond tenor: 0.
        """
        if year < 1 or year > self.tenor:
            return 0.0

        amt = self.amount_in_base  # Use FX-converted amount

        if year <= self.grace_period_years:
            # Grace period: interest-only on full principal
            return amt * self.rate

        # Post-grace amortising period
        remaining_tenor = self.tenor - self.grace_period_years
        if remaining_tenor <= 0:
            return 0.0

        if self.rate == 0:
            return amt / remaining_tenor

        # Standard annuity formula on full principal over remaining tenor
        r = self.rate
        n = remaining_tenor
        annuity = amt * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
        return annuity

    @property
    def amount_in_base(self) -> float:
        """Amount converted to project base currency"""
        return self.amount * self.fx_rate_to_base

    def weighted_cost(self) -> float:
        """Amount (in base currency) * rate — used for blended cost computation"""
        return self.amount_in_base * self.rate

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "tranche_type": self.tranche_type.value,
            "amount": self.amount,
            "amount_in_base": self.amount_in_base,
            "currency": self.currency,
            "fx_rate_to_base": self.fx_rate_to_base,
            "fx_hedge_id": self.fx_hedge_id,
            "rate": self.rate,
            "tenor": self.tenor,
            "grace_period_years": self.grace_period_years,
            "dfi_provider": self.dfi_provider.value if self.dfi_provider else None,
            "is_first_loss": self.is_first_loss,
            "is_concessional": self.is_concessional,
            "additionality_pct": self.additionality_pct,
            "seniority_rank": self.seniority_rank,
            "green_bond_framework": self.green_bond_framework,
            "use_of_proceeds": self.use_of_proceeds,
            "esg_kpi_description": self.esg_kpi_description,
            "margin_ratchet_bps": self.margin_ratchet_bps,
        }


@dataclass
class FinancingStructure:
    """
    Full capital stack for a green project.
    Aggregates tranches + equity + grants to produce blended WACC.
    """
    tranches: List[Tranche] = field(default_factory=list)
    equity_amount: float = 0.0
    equity_cost: float = 0.12       # Typical cost of equity for green infra
    grants_amount: float = 0.0      # Non-repayable (dilutes WACC toward 0)
    base_currency: str = "EUR"      # Project base currency for FX conversion

    # --- Aggregate properties ---

    @property
    def total_debt(self) -> float:
        """Total debt in base currency (FX-converted)"""
        return sum(t.amount_in_base for t in self.tranches)

    @property
    def total_concessional(self) -> float:
        return sum(t.amount_in_base for t in self.tranches if t.is_concessional)

    @property
    def total_commercial(self) -> float:
        return sum(t.amount_in_base for t in self.tranches if not t.is_concessional)

    @property
    def total_capital(self) -> float:
        return self.total_debt + self.equity_amount + self.grants_amount

    @property
    def leverage_ratio(self) -> float:
        """Debt / total capital"""
        if self.total_capital == 0:
            return 0.0
        return self.total_debt / self.total_capital

    @property
    def concessional_share(self) -> float:
        """Share of concessional in total debt"""
        if self.total_debt == 0:
            return 0.0
        return self.total_concessional / self.total_debt

    @property
    def catalytic_ratio(self) -> float:
        """
        Commercial capital mobilised per unit of concessional.
        IFC target: >= 5:1
        """
        if self.total_concessional == 0:
            return float('inf') if self.total_commercial > 0 else 0.0
        return self.total_commercial / self.total_concessional

    # --- Core calculations ---

    def blended_wacc(self) -> float:
        """
        Weighted Average Cost of Capital across ALL sources.
        WACC = sum(amount_i * cost_i) / sum(amount_i)
        Grants have cost=0, diluting WACC — that's the whole point.
        """
        if self.total_capital == 0:
            return 0.0

        weighted_sum = 0.0

        # Debt tranches
        for t in self.tranches:
            weighted_sum += t.amount * t.rate

        # Equity
        weighted_sum += self.equity_amount * self.equity_cost

        # Grants: cost = 0, so they only expand denominator
        # weighted_sum += self.grants_amount * 0.0

        return weighted_sum / self.total_capital

    def blended_debt_cost(self) -> float:
        """Weighted average cost of debt only (excludes equity and grants)"""
        if self.total_debt == 0:
            return 0.0
        return sum(t.weighted_cost() for t in self.tranches) / self.total_debt

    def total_annual_debt_service(self, year: int) -> float:
        """Sum of all tranche debt service for a given project year"""
        return sum(t.annual_debt_service(year) for t in self.tranches)

    def max_grace_period(self) -> int:
        """Longest grace period across all tranches"""
        if not self.tranches:
            return 0
        return max(t.grace_period_years for t in self.tranches)

    def debt_service_profile(self) -> List[Dict]:
        """Year-by-year total debt service across all tranches"""
        if not self.tranches:
            return []
        max_tenor = max(t.tenor for t in self.tranches)
        profile = []
        for year in range(1, max_tenor + 1):
            year_ds = self.total_annual_debt_service(year)
            tranche_detail = {}
            for t in self.tranches:
                ds = t.annual_debt_service(year)
                if ds > 0:
                    tranche_detail[t.name] = ds
            profile.append({
                "year": year,
                "total_debt_service": year_ds,
                "tranches": tranche_detail,
            })
        return profile

    def to_dict(self) -> Dict:
        return {
            "tranches": [t.to_dict() for t in self.tranches],
            "equity_amount": self.equity_amount,
            "equity_cost": self.equity_cost,
            "grants_amount": self.grants_amount,
            "base_currency": self.base_currency,
            "total_debt": self.total_debt,
            "total_concessional": self.total_concessional,
            "total_commercial": self.total_commercial,
            "total_capital": self.total_capital,
            "leverage_ratio": self.leverage_ratio,
            "concessional_share": self.concessional_share,
            "catalytic_ratio": self.catalytic_ratio,
            "blended_wacc": self.blended_wacc(),
            "blended_debt_cost": self.blended_debt_cost(),
            "debt_service_profile": self.debt_service_profile(),
        }


# --- Factory helpers for common structures ---

def create_typical_green_h2_structure(
    total_capex: float,
    equity_pct: float = 0.30,
    concessional_pct: float = 0.12,
    grant_pct: float = 0.05,
    dfi_provider: DFIProvider = DFIProvider.IFC,
    dfi_rate: float = 0.025,
    dfi_grace_years: int = 3,
    senior_rate: float = 0.055,
    senior_tenor: int = 15,
) -> FinancingStructure:
    """
    Build a typical green hydrogen financing structure.
    Defaults based on IFC / EIB precedent for 100-500MW projects.
    """
    equity = total_capex * equity_pct
    grant = total_capex * grant_pct
    concessional = total_capex * concessional_pct
    senior = total_capex - equity - grant - concessional

    structure = FinancingStructure(
        equity_amount=equity,
        equity_cost=0.12,
        grants_amount=grant,
        tranches=[
            Tranche(
                name="Senior Debt",
                tranche_type=TrancheType.SENIOR,
                amount=senior,
                rate=senior_rate,
                tenor=senior_tenor,
            ),
            Tranche(
                name=f"{dfi_provider.value} Concessional",
                tranche_type=TrancheType.CONCESSIONAL,
                amount=concessional,
                rate=dfi_rate,
                tenor=senior_tenor + 3,     # DFI typically longer tenor
                grace_period_years=dfi_grace_years,
                dfi_provider=dfi_provider,
            ),
        ],
    )
    return structure
