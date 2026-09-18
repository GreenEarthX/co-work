"""
Price Lineage Engine — Molecule Cost DNA
Decomposes a forward price into its constituent cost drivers:
  spot basis, convenience yield, seasonality, CAPEX floor,
  regulatory premium, subsidy reduction, financing spread,
  insurance premium.

Each decomposition carries correlation_ids for full audit trail.
This is the "Bloomberg view" — WHY a molecule costs what it costs.
"""
import math
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from datetime import datetime, timezone

from .gabillon import GabillonParams, GabillonModel, get_gabillon_model, SEED_PARAMS
from .debt.tranche import FinancingStructure

logger = logging.getLogger("gex.price_lineage")


# ════════════════════════════════════════════════════════════════
# PRICE COMPONENT — single driver in the decomposition
# ════════════════════════════════════════════════════════════════

@dataclass
class PriceComponent:
    """One additive component of the forward price."""
    name: str                           # Human label
    slug: str                           # Machine key
    value_eur_t: float                  # EUR/t contribution (can be negative)
    pct_of_total: float = 0.0           # % of final forward price
    source: str = ""                    # What data source / model produced this
    explanation: str = ""               # One-line human-readable "because"
    correlation_id: Optional[str] = None  # Links to event store


@dataclass
class PriceDecomposition:
    """
    Full decomposition of a forward price into its cost DNA.
    This is the core data model that makes GEX the Bloomberg Terminal
    for the Green Transition.
    """
    molecule: str
    tenor_months: int
    timestamp: str = ""

    # Final prices
    forward_price_eur_t: float = 0.0
    spot_price_eur_t: float = 0.0

    # Components (ordered by contribution)
    components: List[PriceComponent] = field(default_factory=list)

    # Financing context
    blended_wacc: Optional[float] = None
    concessional_share: Optional[float] = None
    catalytic_ratio: Optional[float] = None
    dfi_providers: List[str] = field(default_factory=list)

    # Certification context
    active_subsidies: Dict[str, float] = field(default_factory=dict)
    certifications: List[str] = field(default_factory=list)

    # Insurance context
    insurance_premium_eur_t: float = 0.0
    insurance_provider: str = ""

    # Lineage metadata
    correlation_id: str = ""
    gabillon_params_hash: str = ""
    calibration_date: str = ""
    n_observations: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def total_premium_eur_t(self) -> float:
        """Total premium above spot."""
        return self.forward_price_eur_t - self.spot_price_eur_t

    @property
    def subsidy_reduction_eur_t(self) -> float:
        """Total subsidy impact (negative = reduces cost to offtaker)."""
        return sum(
            c.value_eur_t for c in self.components
            if c.slug.startswith("subsidy_")
        )

    @property
    def financing_impact_eur_t(self) -> float:
        """Financing cost component."""
        return sum(
            c.value_eur_t for c in self.components
            if c.slug in ("financing_spread", "concessional_absorption", "grace_period_benefit")
        )

    def narrative(self) -> str:
        """
        Generate the Information Lineage narrative.
        'This molecule costs €X/t because...'
        """
        lines = [
            f"This {self.molecule} forward ({self.tenor_months}M) is priced at "
            f"€{self.forward_price_eur_t:,.0f}/t because:"
        ]
        for i, c in enumerate(self.components, 1):
            sign = "+" if c.value_eur_t >= 0 else ""
            lines.append(
                f"  {i}. {sign}€{c.value_eur_t:,.0f}/t — {c.explanation}"
            )
        if self.blended_wacc is not None:
            lines.append(
                f"  Financing: {self.blended_wacc*100:.1f}% blended WACC "
                f"({self.concessional_share*100:.0f}% concessional)"
            )
        if self.active_subsidies:
            subs = ", ".join(f"{k}: €{v:,.0f}/t" for k, v in self.active_subsidies.items())
            lines.append(f"  Subsidies: {subs}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "molecule": self.molecule,
            "tenor_months": self.tenor_months,
            "timestamp": self.timestamp,
            "forward_price_eur_t": round(self.forward_price_eur_t, 2),
            "spot_price_eur_t": round(self.spot_price_eur_t, 2),
            "total_premium_eur_t": round(self.total_premium_eur_t, 2),
            "components": [
                {
                    "name": c.name,
                    "slug": c.slug,
                    "value_eur_t": round(c.value_eur_t, 2),
                    "pct_of_total": round(c.pct_of_total, 1),
                    "source": c.source,
                    "explanation": c.explanation,
                    "correlation_id": c.correlation_id,
                }
                for c in self.components
            ],
            "financing": {
                "blended_wacc": round(self.blended_wacc, 5) if self.blended_wacc is not None else None,
                "concessional_share": round(self.concessional_share, 4) if self.concessional_share is not None else None,
                "catalytic_ratio": round(self.catalytic_ratio, 2) if self.catalytic_ratio is not None else None,
                "dfi_providers": self.dfi_providers,
            },
            "subsidies": self.active_subsidies,
            "certifications": self.certifications,
            "insurance": {
                "premium_eur_t": round(self.insurance_premium_eur_t, 2),
                "provider": self.insurance_provider,
            },
            "lineage": {
                "correlation_id": self.correlation_id,
                "gabillon_params_hash": self.gabillon_params_hash,
                "calibration_date": self.calibration_date,
                "n_observations": self.n_observations,
            },
            "narrative": self.narrative(),
        }


# ════════════════════════════════════════════════════════════════
# LINEAGE ENGINE — the bridge between all engines
# ════════════════════════════════════════════════════════════════

class PriceLineageEngine:
    """
    Connects Gabillon pricing + FinancingStructure + subsidies + insurance
    into a single price decomposition with full audit trail.
    """

    def __init__(self, model: Optional[GabillonModel] = None):
        self.model = model or get_gabillon_model()

    def decompose(
        self,
        molecule: str,
        tenor_months: int = 12,
        spot_override: Optional[float] = None,
        financing: Optional[FinancingStructure] = None,
        subsidies: Optional[Dict[str, float]] = None,
        insurance_annual_eur: float = 0.0,
        insurance_provider: str = "",
        annual_production_tonnes: float = 1.0,
        certifications: Optional[List[str]] = None,
        correlation_id: str = "",
    ) -> PriceDecomposition:
        """
        Decompose a forward price into its constituent cost drivers.

        This is THE method that produces the Information Lineage.
        Each component is independently attributable and auditable.
        """
        params = SEED_PARAMS.get(molecule)
        if not params:
            raise ValueError(f"Unsupported molecule: {molecule}")

        spot = spot_override or math.exp(params.mu_base)
        delta = params.theta_0  # Use base convenience yield
        tau = tenor_months / 12.0

        # ─── 1. Compute forward price components individually ───

        components: List[PriceComponent] = []

        # Component 1: Spot basis
        components.append(PriceComponent(
            name="Spot Basis",
            slug="spot_basis",
            value_eur_t=spot,
            source=f"Gabillon calibration ({params.last_calibrated})",
            explanation=f"Current market spot price for {molecule}",
        ))

        # Component 2: Convenience yield (backwardation/contango)
        # Matches GabillonModel.forward_price: -((1-e^(-κτ))/κ)(δ-θ).
        e_alpha_tau = math.exp(-params.alpha * tau)
        e_kappa_tau = math.exp(-params.kappa * tau)
        convenience_value = spot * (
            math.exp(-((1 - e_kappa_tau) / params.kappa) * (delta - params.theta_0)) - 1
        ) if params.kappa > 0 else 0
        components.append(PriceComponent(
            name="Convenience Yield",
            slug="convenience_yield",
            value_eur_t=round(convenience_value, 2),
            source="Gabillon two-factor model",
            explanation=(
                "Scarcity premium from physical supply tightness"
                if convenience_value > 0
                else "Contango from excess supply / storage carry"
            ),
        ))

        # Component 3: Mean reversion toward long-run equilibrium.
        # Matches GabillonModel.forward_price: (1-e^(-ατ))(μ - ln S) blends the
        # log-spot toward the equilibrium log-level μ. Zero when spot is AT
        # equilibrium; positive when spot below, negative when above.
        equilibrium = math.exp(params.mu_base)
        drift_value = spot * (
            math.exp((1 - e_alpha_tau) * (params.mu_base - math.log(spot))) - 1
        ) if tau > 0 else 0
        components.append(PriceComponent(
            name="Mean Reversion Drift",
            slug="mean_reversion",
            value_eur_t=round(drift_value, 2),
            source="Gabillon α parameter",
            explanation=(
                f"Price converging toward €{equilibrium:,.0f}/t equilibrium "
                f"(half-life: {self.model.mean_reversion_half_life(params):.0f}M)"
            ),
        ))

        # Component 4: Seasonality
        T_abs = tau
        season_raw = (
            params.season_a1 * math.sin(2 * math.pi * T_abs)
            + params.season_a2 * math.cos(2 * math.pi * T_abs)
        )
        season_value = spot * season_raw
        quarter_map = {0: "Q1", 1: "Q1", 2: "Q1", 3: "Q2", 4: "Q2", 5: "Q2",
                       6: "Q3", 7: "Q3", 8: "Q3", 9: "Q4", 10: "Q4", 11: "Q4"}
        delivery_q = quarter_map.get(tenor_months % 12, "")
        components.append(PriceComponent(
            name="Seasonality",
            slug="seasonality",
            value_eur_t=round(season_value, 2),
            source="Quarterly Fourier decomposition",
            explanation=f"{delivery_q} seasonal adjustment ({season_raw*100:+.1f}%)",
        ))

        # Component 5: CAPEX floor pull (learning curve anchor)
        floor_pull_value = 0.0
        if params.capex_floor_eur_t > 0 and spot < params.capex_floor_eur_t:
            floor_pull_value = spot * 0.10 * tau * (
                math.log(params.capex_floor_eur_t) - math.log(spot)
            )
        components.append(PriceComponent(
            name="CAPEX Floor",
            slug="capex_floor",
            value_eur_t=round(floor_pull_value, 2),
            source=f"Plant Builder LCOH: €{params.capex_floor_eur_t:,.0f}/t",
            explanation=(
                f"Price anchored upward — below production cost floor of €{params.capex_floor_eur_t:,.0f}/t"
                if floor_pull_value > 0
                else "Price above LCOH — no floor support needed"
            ),
        ))

        # Component 6: Regulatory premium (ETS + RFNBO mandate)
        reg_premium = params.regulatory_premium_base
        components.append(PriceComponent(
            name="Regulatory Premium",
            slug="regulatory_premium",
            value_eur_t=round(reg_premium, 2),
            source="EU ETS carbon price + RFNBO/RED III mandate progression",
            explanation=f"Green premium from carbon pricing (€{reg_premium:,.0f}/t embedded)",
        ))

        # ─── 2. Financing structure impact ───

        financing_spread = 0.0
        concessional_absorption = 0.0
        grace_benefit = 0.0

        if financing:
            wacc = financing.blended_wacc()
            risk_free = 0.03  # ECB policy rate proxy
            spread_pct = max(wacc - risk_free, 0)

            # Financing spread: portion of LCOH attributable to cost of capital
            # LCOH ≈ (CAPEX × CRF(wacc, tenor) + OPEX) / production
            # The spread component = CAPEX × (CRF(wacc) - CRF(risk_free)) / production
            if params.capex_floor_eur_t > 0:
                capex_proxy = params.capex_floor_eur_t * 0.65  # ~65% of LCOH is capex
                avg_tenor = 15
                if wacc > 0 and avg_tenor > 0:
                    crf_wacc = wacc * (1 + wacc)**avg_tenor / ((1 + wacc)**avg_tenor - 1)
                    crf_rf = risk_free * (1 + risk_free)**avg_tenor / ((1 + risk_free)**avg_tenor - 1)
                    financing_spread = capex_proxy * (crf_wacc - crf_rf)

            # Concessional absorption: how much DFI capital reduced the WACC
            if financing.total_concessional > 0:
                commercial_wacc = financing.blended_debt_cost()
                concessional_avg_rate = (
                    sum(t.rate * t.amount for t in financing.tranches if t.is_concessional)
                    / financing.total_concessional
                ) if financing.total_concessional > 0 else 0

                # Savings from concessional below commercial rate
                rate_saving = max(commercial_wacc - concessional_avg_rate, 0)
                share = financing.concessional_share
                if params.capex_floor_eur_t > 0:
                    concessional_absorption = -(params.capex_floor_eur_t * 0.65 * rate_saving * share * 0.08)

            # Grace period benefit: deferred principal = lower early-year cost
            max_grace = financing.max_grace_period()
            if max_grace > 0:
                grace_benefit = -(params.capex_floor_eur_t * 0.02 * max_grace)

            components.append(PriceComponent(
                name="Financing Spread",
                slug="financing_spread",
                value_eur_t=round(financing_spread, 2),
                source=f"Blended WACC {wacc*100:.1f}% vs risk-free {risk_free*100:.1f}%",
                explanation=f"Cost of capital above risk-free rate ({spread_pct*100:.1f}% spread)",
            ))

            if concessional_absorption != 0:
                dfi_names = [
                    t.dfi_provider.value for t in financing.tranches
                    if t.dfi_provider is not None
                ]
                components.append(PriceComponent(
                    name="Concessional Absorption",
                    slug="concessional_absorption",
                    value_eur_t=round(concessional_absorption, 2),
                    source=f"DFI: {', '.join(dfi_names) or 'concessional tranches'}",
                    explanation=(
                        f"{financing.concessional_share*100:.0f}% of CAPEX absorbed by "
                        f"concessional capital at below-market rates"
                    ),
                ))

            if grace_benefit != 0:
                components.append(PriceComponent(
                    name="Grace Period Benefit",
                    slug="grace_period_benefit",
                    value_eur_t=round(grace_benefit, 2),
                    source=f"DFI grace period: {max_grace}y interest-only",
                    explanation=f"{max_grace}y deferred principal reduces early-year cost of production",
                ))

        # ─── 3. Subsidy reduction ───

        if subsidies:
            for sub_name, sub_value_eur_kg in subsidies.items():
                # Convert EUR/kg to EUR/t (× 1000)
                sub_eur_t = -(sub_value_eur_kg * 1000)
                components.append(PriceComponent(
                    name=f"Subsidy: {sub_name}",
                    slug=f"subsidy_{sub_name.lower()}",
                    value_eur_t=round(sub_eur_t, 2),
                    source=f"{sub_name} certification",
                    explanation=f"{sub_name} subsidy reduces effective offtaker cost by €{abs(sub_eur_t):,.0f}/t",
                ))

        # ─── 4. Insurance premium ───

        insurance_eur_t = 0.0
        if insurance_annual_eur > 0 and annual_production_tonnes > 0:
            insurance_eur_t = insurance_annual_eur / annual_production_tonnes
            components.append(PriceComponent(
                name="Insurance Premium",
                slug="insurance_premium",
                value_eur_t=round(insurance_eur_t, 2),
                source=insurance_provider or "Insurance broker",
                explanation=f"Annual insurance premium allocated across {annual_production_tonnes:,.0f}t production",
            ))

        # ─── 5. Compute market forward and reconcile ───
        #
        # The Gabillon model prices the MARKET forward (spot dynamics only:
        # spot basis, convenience yield, mean reversion, seasonality, floor).
        # The residual reconciles ONLY those market terms — it must never
        # absorb the cost stack or subsidies, or it becomes unauditable.

        market_forward = self.model.forward_price(params, spot, delta, tau)
        MARKET_SLUGS = {"spot_basis", "convenience_yield", "mean_reversion",
                        "seasonality", "capex_floor"}
        market_sum = sum(c.value_eur_t for c in components if c.slug in MARKET_SLUGS)

        residual = market_forward - market_sum
        if abs(residual) > 1.0:
            components.append(PriceComponent(
                name="Model Residual",
                slug="residual",
                value_eur_t=round(residual, 2),
                source="Gabillon cross-terms + Jensen correction",
                explanation="Non-linear interaction between market model factors",
            ))

        # All-in delivered forward = market forward + cost-stack pass-throughs
        # (regulatory premium, financing spread, DFI absorption/grace, insurance).
        # Subsidies are excluded: they do not change the contract forward —
        # they bridge from the forward to the EFFECTIVE OFFTAKER COST.
        cost_stack = sum(
            c.value_eur_t for c in components
            if c.slug not in MARKET_SLUGS
            and c.slug != "residual"
            and not c.slug.startswith("subsidy_")
        )
        actual_forward = round(market_forward + cost_stack, 2)

        # ─── 6. Compute percentages ───

        final_price = actual_forward
        for c in components:
            c.pct_of_total = (c.value_eur_t / final_price * 100) if final_price != 0 else 0

        # ─── 7. Assemble decomposition ───

        dfi_list = []
        if financing:
            dfi_list = [
                t.dfi_provider.value for t in financing.tranches
                if t.dfi_provider is not None
            ]

        return PriceDecomposition(
            molecule=molecule,
            tenor_months=tenor_months,
            forward_price_eur_t=actual_forward,
            spot_price_eur_t=spot,
            components=components,
            blended_wacc=financing.blended_wacc() if financing else None,
            concessional_share=financing.concessional_share if financing else None,
            catalytic_ratio=(
                financing.catalytic_ratio if financing and financing.catalytic_ratio != float('inf') else None
            ),
            dfi_providers=dfi_list,
            active_subsidies={k: round(v * 1000, 2) for k, v in (subsidies or {}).items()},
            certifications=certifications or [],
            insurance_premium_eur_t=insurance_eur_t,
            insurance_provider=insurance_provider,
            correlation_id=correlation_id,
            gabillon_params_hash="",
            calibration_date=params.last_calibrated,
            n_observations=params.n_observations,
        )

    def decompose_multi_tenor(
        self,
        molecule: str,
        tenors: Optional[List[int]] = None,
        **kwargs,
    ) -> List[Dict]:
        """Decompose at multiple tenors — for term structure lineage view."""
        if tenors is None:
            tenors = [1, 3, 6, 12, 24, 36, 60]
        return [
            self.decompose(molecule, tenor_months=t, **kwargs).to_dict()
            for t in tenors
        ]
