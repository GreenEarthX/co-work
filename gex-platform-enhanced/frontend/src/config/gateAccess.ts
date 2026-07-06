// Screen: Gate access config (no screen)
import type { ServiceType, UserRole } from "@/contexts/UserRoleContext";

export type GateActor =
  | "PRODUCER"
  | "OFFTAKER"
  | "COMMERCIAL_BANKER"
  | "DFI"
  | "INSURER"
  | "REGULATOR"
  | "GOV_AGENCY"
  | "CERTIFIER"
  | "EPC_CONTRACTOR"
  | "LOGISTICS_OPERATOR"
  | "TECHNOLOGY_PROVIDER"
  | "EXECUTIVE"
  | "GUEST";

const CANONICAL_GATE_BY_SHORT: Record<string, string> = {
  G0: "G0_SITE_RIGHTS",
  G1: "G1_GRID_WATER",
  G2: "G2_CERTIFICATION",
  G3: "G3_FEEDSTOCK_LOGISTICS",
  G4: "G4_OFFTAKE",
  G5: "G5_EPC",
  G6: "G6_IE_SIGNOFF",
  G7: "G7_INSURANCE",
  G8: "G8_MODEL_AUDIT",
  G9: "G9_PERMITS",
  G10: "G10_FINANCIAL_CLOSE",
  G11: "G11_COD",
};

const ACTOR_GATE_VISIBILITY: Record<GateActor, string[]> = {
  PRODUCER: [
    "G0_SITE_RIGHTS",
    "G1_GRID_WATER",
    "G3_FEEDSTOCK_LOGISTICS",
    "G5_EPC",
    "G9_PERMITS",
    "G11_COD",
  ],
  OFFTAKER: ["G4_OFFTAKE"],
  COMMERCIAL_BANKER: [
    "G4_OFFTAKE",
    "G6_IE_SIGNOFF",
    "G7_INSURANCE",
    "G8_MODEL_AUDIT",
    "G10_FINANCIAL_CLOSE",
  ],
  DFI: [
    "G4_OFFTAKE",
    "G6_IE_SIGNOFF",
    "G7_INSURANCE",
    "G8_MODEL_AUDIT",
    "G10_FINANCIAL_CLOSE",
  ],
  INSURER: ["G5_EPC", "G6_IE_SIGNOFF", "G7_INSURANCE"],
  REGULATOR: ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G9_PERMITS"],
  GOV_AGENCY: Object.values(CANONICAL_GATE_BY_SHORT),
  CERTIFIER: ["G2_CERTIFICATION", "G6_IE_SIGNOFF", "G9_PERMITS"],
  EPC_CONTRACTOR: ["G5_EPC", "G11_COD"],
  LOGISTICS_OPERATOR: ["G3_FEEDSTOCK_LOGISTICS"],
  TECHNOLOGY_PROVIDER: ["G5_EPC", "G11_COD"],
  EXECUTIVE: Object.values(CANONICAL_GATE_BY_SHORT),
  GUEST: [],
};

const SERVICE_ACTOR_MAP: Partial<
  Record<Exclude<ServiceType, null>, GateActor>
> = {
  BANK: "COMMERCIAL_BANKER",
  INSURER: "INSURER",
  CERTIFIER: "CERTIFIER",
  LOGISTICS: "LOGISTICS_OPERATOR",
  ENGINEER: "EPC_CONTRACTOR",
  EQUIPMENT: "TECHNOLOGY_PROVIDER",
};

export function getShortGateId(gateId: string): string {
  const match = gateId.match(/^G\d+/);
  return match ? match[0] : gateId;
}

export function normalizeGateId(gateId: string): string {
  const shortGateId = getShortGateId(gateId);
  return CANONICAL_GATE_BY_SHORT[shortGateId] ?? gateId;
}

export function getActorTypesForRole(role: UserRole): GateActor[] {
  if (role.business_function === "EXECUTIVE") {
    return ["EXECUTIVE"];
  }

  const actorTypes = new Set<GateActor>();
  const capabilities = new Set(role.capabilities ?? []);

  if (role.company_type === "PRODUCER" || capabilities.has("PRODUCE")) {
    actorTypes.add("PRODUCER");
  }

  if (role.company_type === "OFFTAKER" || capabilities.has("OFFTAKE")) {
    actorTypes.add("OFFTAKER");
  }

  if (role.company_type === "THIRD_PARTY" && role.service_type) {
    const serviceActor = SERVICE_ACTOR_MAP[role.service_type];
    if (serviceActor) {
      actorTypes.add(serviceActor);
    }
  }

  return actorTypes.size > 0 ? Array.from(actorTypes) : ["GUEST"];
}

export function getVisibleCanonicalGates(role: UserRole): Set<string> {
  const visible = new Set<string>();

  getActorTypesForRole(role).forEach((actorType) => {
    (ACTOR_GATE_VISIBILITY[actorType] ?? []).forEach((gateId) =>
      visible.add(gateId),
    );
  });

  return visible;
}

export function getVisibleGateShortIds(role: UserRole): Set<string> {
  return new Set(
    Array.from(getVisibleCanonicalGates(role)).map((gateId) =>
      getShortGateId(gateId),
    ),
  );
}

export function canAccessGate(role: UserRole, gateId: string): boolean {
  return getVisibleCanonicalGates(role).has(normalizeGateId(gateId));
}
