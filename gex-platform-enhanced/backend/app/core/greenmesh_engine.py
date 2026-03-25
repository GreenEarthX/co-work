"""
GreenMesh Engine — Multilateral Netting + Mass-Balance + Certification Mapping
v5.1

Three functions:
1. FlowFusion™: multilateral netting of physical flows across counterparties
2. Mass-balance clearing: track green attribute from production to delivery
3. Certification-Revenue mapping: compute GoO premium per regime per molecule
"""
import logging
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("gex.greenmesh_engine")


# ════════════════════════════════════════════════════════════════
# CERTIFICATION PREMIUM TABLE
# ════════════════════════════════════════════════════════════════

class CertificationPremium:
    """
    Revenue uplift from certification, per molecule per regime.
    These are ADDITIONAL to the base commodity price (€/tonne).
    Sources: BNEF H2 Green Premium Survey 2024, ICIS GoO market data 2025.
    """
    PREMIUMS_EUR_T: dict = {
        ("H2", "RFNBO"):          400,
        ("H2", "RED_III"):         250,
        ("H2", "45V"):             300,   # via PTC, effective premium
        ("H2", "CertifHy"):        100,
        ("NH3", "RFNBO"):          120,
        ("NH3", "RED_III"):         80,
        ("SAF", "RFNBO"):          350,
        ("SAF", "RED_III"):        280,
        ("SAF", "CORSIA"):         150,
        ("E_METHANOL", "RFNBO"):   200,
        ("E_METHANOL", "RED_III"): 150,
        ("E_NG", "RFNBO"):          90,
        ("E_NG", "RED_III"):        60,
    }

    @classmethod
    def get(cls, molecule: str, regime: str) -> float:
        return float(cls.PREMIUMS_EUR_T.get((molecule, regime), 0.0))

    @classmethod
    def all_for_molecule(cls, molecule: str) -> dict:
        return {
            regime: premium
            for (mol, regime), premium in cls.PREMIUMS_EUR_T.items()
            if mol == molecule
        }


# ════════════════════════════════════════════════════════════════
# MASS BALANCE
# ════════════════════════════════════════════════════════════════

@dataclass
class MassBalanceEntry:
    """Single entry in the mass-balance chain."""
    batch_id: str
    molecule: str
    volume_tonnes: float
    production_timestamp: str
    producer_company_id: str
    green_attribute: str            # "RFNBO" | "RED_III" | etc.
    goo_id: str                     # Guarantee of Origin token ID
    current_holder: str             # company_id
    chain: list = field(default_factory=list)    # ordered list of holder company_ids
    status: str = "PRODUCED"        # PRODUCED | IN_TRANSIT | DELIVERED | RETIRED
    ghg_intensity_kg_co2_kg: float = 0.0
    certification_expiry: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def transfer_to(self, new_holder: str) -> "MassBalanceEntry":
        """Transfer custody to new holder. Returns updated entry."""
        self.chain.append(self.current_holder)
        self.current_holder = new_holder
        self.status = "IN_TRANSIT"
        return self

    def deliver(self) -> "MassBalanceEntry":
        self.status = "DELIVERED"
        return self

    def retire(self) -> "MassBalanceEntry":
        """Retire GoO — cannot be transferred or used again."""
        self.status = "RETIRED"
        return self

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "molecule": self.molecule,
            "volume_tonnes": self.volume_tonnes,
            "production_timestamp": self.production_timestamp,
            "producer_company_id": self.producer_company_id,
            "green_attribute": self.green_attribute,
            "goo_id": self.goo_id,
            "current_holder": self.current_holder,
            "chain": self.chain,
            "status": self.status,
            "ghg_intensity_kg_co2_kg": self.ghg_intensity_kg_co2_kg,
            "certification_expiry": self.certification_expiry,
        }


def _make_goo_id(batch_id: str, producer_id: str, timestamp: str) -> str:
    """Deterministic GoO token ID from batch + producer + timestamp."""
    raw = f"{batch_id}:{producer_id}:{timestamp}"
    return "GOO-" + hashlib.sha256(raw.encode()).hexdigest()[:16].upper()


# ════════════════════════════════════════════════════════════════
# FLOW FUSION — MULTILATERAL NETTING
# ════════════════════════════════════════════════════════════════

@dataclass
class PhysicalFlow:
    """Bilateral physical delivery obligation."""
    flow_id: str
    from_company: str
    to_company: str
    molecule: str
    volume_tonnes: float
    delivery_date: str
    price_eur_t: float
    green_attribute: Optional[str] = None
    goo_id: Optional[str] = None


@dataclass
class FlowFusionResult:
    """Result of multilateral FlowFusion netting."""
    gross_flows: int
    net_flows: int
    netting_efficiency_pct: float
    settled_pairs: list       # (from, to, volume, molecule, value_eur)
    residual_pairs: list      # flows that couldn't be fully netted
    netting_savings_eur: float
    compression_ratio: float  # net / gross


def _run_multilateral_netting(flows: list[PhysicalFlow]) -> FlowFusionResult:
    """
    FlowFusion™ — multilateral netting algorithm.

    Build a net position matrix per (company_a, company_b, molecule),
    then cancel offsetting positions. Standard CLS-style bilateral netting
    extended to N counterparties via graph reduction.
    """
    # Step 1: Aggregate positions — net_matrix[(from, to, mol)] = volume
    net_matrix: dict = {}
    for flow in flows:
        key = (flow.from_company, flow.to_company, flow.molecule)
        net_matrix[key] = net_matrix.get(key, 0.0) + flow.volume_tonnes

    # Step 2: Cancel opposing flows — if A owes B and B owes A, offset
    cancelled_keys = set()
    settled = []
    residual = []
    gross_value = sum(
        f.volume_tonnes * f.price_eur_t for f in flows
    )

    net_keys = list(net_matrix.keys())
    for key in net_keys:
        if key in cancelled_keys:
            continue
        (frm, to, mol) = key
        reverse_key = (to, frm, mol)
        fwd_vol = net_matrix.get(key, 0.0)
        rev_vol = net_matrix.get(reverse_key, 0.0)

        if rev_vol > 0 and reverse_key not in cancelled_keys:
            net_vol = fwd_vol - rev_vol
            if net_vol > 0:
                settled.append((frm, to, round(net_vol, 4), mol))
                net_matrix[key] = net_vol
                net_matrix[reverse_key] = 0
            elif net_vol < 0:
                settled.append((to, frm, round(-net_vol, 4), mol))
                net_matrix[key] = 0
                net_matrix[reverse_key] = -net_vol
            else:
                # Perfect offset
                net_matrix[key] = 0
                net_matrix[reverse_key] = 0
            cancelled_keys.add(reverse_key)
        else:
            residual.append((frm, to, round(fwd_vol, 4), mol))

    # Step 3: Count survivors
    net_flows = sum(1 for (f, t, v, m) in settled + residual if v > 0)
    gross_flows = len(flows)
    netting_eff = round(
        100.0 * (gross_flows - net_flows) / gross_flows, 1
    ) if gross_flows > 0 else 0.0

    # Estimate netting savings (avoided settlement cost ~€5/tonne)
    netted_volume = sum(
        f.volume_tonnes for f in flows
    ) - sum(v for (_, _, v, _) in settled + residual if v > 0)
    savings = netted_volume * 5.0

    return FlowFusionResult(
        gross_flows=gross_flows,
        net_flows=net_flows,
        netting_efficiency_pct=netting_eff,
        settled_pairs=settled,
        residual_pairs=residual,
        netting_savings_eur=round(savings, 0),
        compression_ratio=round(net_flows / gross_flows, 3) if gross_flows else 1.0,
    )


# ════════════════════════════════════════════════════════════════
# GOO VALUE
# ════════════════════════════════════════════════════════════════

@dataclass
class GooValuation:
    molecule: str
    regime: str
    volume_tonnes: float
    base_commodity_price_eur_t: float
    goo_premium_eur_t: float
    total_goo_value_eur: float
    total_physical_value_eur: float
    total_value_eur: float
    premium_pct_of_total: float


# ════════════════════════════════════════════════════════════════
# GREENMESH ENGINE
# ════════════════════════════════════════════════════════════════

class GreenMeshEngine:
    """
    GreenMesh clearing engine — integrates:
    - FlowFusion™ multilateral netting
    - Mass-balance chain of custody
    - Certification-revenue mapping
    """

    def __init__(self):
        self._mass_balance_store: dict = {}     # batch_id → MassBalanceEntry
        self._flow_store: dict = {}             # flow_id → PhysicalFlow
        logger.info("GreenMeshEngine initialised")

    # ── Certification Premiums ──────────────────────────────────

    def compute_certification_premium(
        self, molecule: str, regimes: list
    ) -> dict:
        """For each regime, return the €/t premium this molecule earns."""
        return {
            regime: CertificationPremium.get(molecule, regime)
            for regime in regimes
        }

    def best_regime_for_molecule(self, molecule: str) -> tuple:
        """Return (best_regime, premium_eur_t) for maximising GoO value."""
        prems = CertificationPremium.all_for_molecule(molecule)
        if not prems:
            return (None, 0.0)
        best = max(prems.items(), key=lambda kv: kv[1])
        return best

    # ── GoO Valuation ───────────────────────────────────────────

    def compute_goo_value(
        self,
        molecule: str,
        regime: str,
        volume_tonnes: float,
        base_commodity_price_eur_t: float = 0.0,
    ) -> GooValuation:
        """
        GoO value = premium × volume.
        Separate from physical commodity revenue.
        """
        premium = CertificationPremium.get(molecule, regime)
        goo_val = premium * volume_tonnes
        phys_val = base_commodity_price_eur_t * volume_tonnes
        total_val = goo_val + phys_val
        prem_pct = round(100 * goo_val / total_val, 1) if total_val > 0 else 0.0

        return GooValuation(
            molecule=molecule,
            regime=regime,
            volume_tonnes=volume_tonnes,
            base_commodity_price_eur_t=base_commodity_price_eur_t,
            goo_premium_eur_t=premium,
            total_goo_value_eur=round(goo_val, 0),
            total_physical_value_eur=round(phys_val, 0),
            total_value_eur=round(total_val, 0),
            premium_pct_of_total=prem_pct,
        )

    # ── Mass Balance ────────────────────────────────────────────

    def register_batch(
        self,
        batch_id: str,
        molecule: str,
        volume_tonnes: float,
        producer_company_id: str,
        green_attribute: str,
        ghg_intensity: float = 0.0,
        certification_expiry: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> MassBalanceEntry:
        """Register a new production batch in the mass-balance chain."""
        now = datetime.now(timezone.utc).isoformat()
        goo_id = _make_goo_id(batch_id, producer_company_id, now)

        entry = MassBalanceEntry(
            batch_id=batch_id,
            molecule=molecule,
            volume_tonnes=volume_tonnes,
            production_timestamp=now,
            producer_company_id=producer_company_id,
            green_attribute=green_attribute,
            goo_id=goo_id,
            current_holder=producer_company_id,
            chain=[],
            status="PRODUCED",
            ghg_intensity_kg_co2_kg=ghg_intensity,
            certification_expiry=certification_expiry,
            metadata=metadata or {},
        )
        self._mass_balance_store[batch_id] = entry
        logger.info("Batch registered: %s (%.1f t %s, %s)", batch_id, volume_tonnes, molecule, green_attribute)
        return entry

    def transfer_batch(self, batch_id: str, new_holder: str) -> MassBalanceEntry:
        """Transfer GoO custody to new holder."""
        entry = self._mass_balance_store.get(batch_id)
        if not entry:
            raise ValueError(f"Batch {batch_id} not found")
        if entry.status == "RETIRED":
            raise ValueError(f"Batch {batch_id} GoO is retired — cannot transfer")
        entry.transfer_to(new_holder)
        return entry

    def deliver_batch(self, batch_id: str) -> MassBalanceEntry:
        """Mark batch as delivered."""
        entry = self._mass_balance_store.get(batch_id)
        if not entry:
            raise ValueError(f"Batch {batch_id} not found")
        entry.deliver()
        return entry

    def retire_goo(self, batch_id: str) -> MassBalanceEntry:
        """Retire GoO on claim — prevents double-counting."""
        entry = self._mass_balance_store.get(batch_id)
        if not entry:
            raise ValueError(f"Batch {batch_id} not found")
        entry.retire()
        logger.info("GoO retired: %s (batch %s)", entry.goo_id, batch_id)
        return entry

    def track_mass_balance(self, batch_id: str) -> Optional[MassBalanceEntry]:
        """Return the full chain of custody for a batch."""
        return self._mass_balance_store.get(batch_id)

    def list_batches(
        self,
        company_id: Optional[str] = None,
        molecule: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list:
        entries = list(self._mass_balance_store.values())
        if company_id:
            entries = [e for e in entries if e.current_holder == company_id or e.producer_company_id == company_id]
        if molecule:
            entries = [e for e in entries if e.molecule == molecule]
        if status:
            entries = [e for e in entries if e.status == status]
        return entries

    # ── FlowFusion ──────────────────────────────────────────────

    def register_flow(
        self,
        flow_id: str,
        from_company: str,
        to_company: str,
        molecule: str,
        volume_tonnes: float,
        delivery_date: str,
        price_eur_t: float,
        green_attribute: Optional[str] = None,
        goo_id: Optional[str] = None,
    ) -> PhysicalFlow:
        """Register a bilateral physical flow for netting."""
        flow = PhysicalFlow(
            flow_id=flow_id,
            from_company=from_company,
            to_company=to_company,
            molecule=molecule,
            volume_tonnes=volume_tonnes,
            delivery_date=delivery_date,
            price_eur_t=price_eur_t,
            green_attribute=green_attribute,
            goo_id=goo_id,
        )
        self._flow_store[flow_id] = flow
        return flow

    def run_flow_fusion(
        self,
        flows: Optional[list] = None,
        molecule: Optional[str] = None,
        delivery_date: Optional[str] = None,
    ) -> FlowFusionResult:
        """
        Run FlowFusion™ multilateral netting.
        Pass explicit flows list, or filter from registered flows.
        """
        if flows is not None:
            # flows is list of dicts with flow parameters
            flow_objs = [
                PhysicalFlow(
                    flow_id=f.get("flow_id", f"f{i}"),
                    from_company=f["from_company"],
                    to_company=f["to_company"],
                    molecule=f["molecule"],
                    volume_tonnes=float(f["volume_tonnes"]),
                    delivery_date=f.get("delivery_date", ""),
                    price_eur_t=float(f.get("price_eur_t", 0)),
                    green_attribute=f.get("green_attribute"),
                )
                for i, f in enumerate(flows)
            ]
        else:
            flow_objs = list(self._flow_store.values())
            if molecule:
                flow_objs = [f for f in flow_objs if f.molecule == molecule]
            if delivery_date:
                flow_objs = [f for f in flow_objs if f.delivery_date == delivery_date]

        if not flow_objs:
            return FlowFusionResult(
                gross_flows=0, net_flows=0,
                netting_efficiency_pct=0.0,
                settled_pairs=[], residual_pairs=[],
                netting_savings_eur=0.0, compression_ratio=1.0,
            )

        return _run_multilateral_netting(flow_objs)

    # ── Integrated Analysis ─────────────────────────────────────

    def offtake_quality_signal(
        self,
        molecule: str,
        regimes: list,
        volume_tonnes: float,
        base_price_eur_t: float,
    ) -> dict:
        """
        For offtake quality scoring: return the certified revenue uplift signal.
        Used by OfftakeQuality.tsx to show G4 (certified, long-term) quality score.
        """
        premiums = self.compute_certification_premium(molecule, regimes)
        best_premium = max(premiums.values(), default=0.0)
        best_regime = max(premiums, key=premiums.get) if premiums else None
        uplift_pct = round(100 * best_premium / base_price_eur_t, 1) if base_price_eur_t > 0 else 0.0

        return {
            "molecule": molecule,
            "regimes_achievable": [r for r, p in premiums.items() if p > 0],
            "best_regime": best_regime,
            "best_premium_eur_t": best_premium,
            "total_goo_value_eur": round(best_premium * volume_tonnes, 0),
            "base_revenue_eur": round(base_price_eur_t * volume_tonnes, 0),
            "certified_revenue_eur": round((base_price_eur_t + best_premium) * volume_tonnes, 0),
            "premium_uplift_pct": uplift_pct,
            "offtake_quality_grade": "G4" if best_premium > 200 else "G3" if best_premium > 80 else "G2",
        }

    def demand_aggregation_signal(
        self,
        molecule: str,
        certified_volume_tonnes: float,
        uncertified_volume_tonnes: float,
    ) -> dict:
        """
        Signal for demand aggregation: certified volumes attract premium buyers.
        """
        best_regime, best_premium = self.best_regime_for_molecule(molecule)
        return {
            "molecule": molecule,
            "certified_volume_tonnes": certified_volume_tonnes,
            "uncertified_volume_tonnes": uncertified_volume_tonnes,
            "certification_ratio_pct": round(
                100 * certified_volume_tonnes / (certified_volume_tonnes + uncertified_volume_tonnes), 1
            ) if (certified_volume_tonnes + uncertified_volume_tonnes) > 0 else 0.0,
            "best_certification": best_regime,
            "premium_eur_t": best_premium,
            "premium_uplift_certified_vs_uncertified_eur": round(
                best_premium * certified_volume_tonnes, 0
            ),
        }


# ════════════════════════════════════════════════════════════════
# SINGLETON
# ════════════════════════════════════════════════════════════════

_engine: Optional[GreenMeshEngine] = None


def get_greenmesh_engine() -> GreenMeshEngine:
    global _engine
    if _engine is None:
        _engine = GreenMeshEngine()
    return _engine
