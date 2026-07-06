/**
 * ConstructionForm — Refinery-style construction CAPEX breakdown for the
 * Site Infrastructure workspace. Four grouped sections (Civil & Structural,
 * Mechanical, Electrical & Instrumentation, Indirect Services) with strict
 * numeric inputs in EUR, plus contingency and notes.
 */
import { useId } from "react";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Building, Wrench, Zap, Briefcase } from "lucide-react";
import {
  formatEur,
  CONSTRUCTION_LINE_KEYS,
  type InfraConstruction,
} from "@/lib/siteInfrastructure";
import EurNumberInput from "@/components/ui/EurNumberInput";

type FieldKey = (typeof CONSTRUCTION_LINE_KEYS)[number];

interface FieldDef { key: FieldKey; label: string; help?: string }
interface GroupDef { title: string; icon: typeof Building; fields: FieldDef[] }

const GROUPS: GroupDef[] = [
  {
    title: "Civil & Structural",
    icon: Building,
    fields: [
      { key: "foundationsEur",        label: "Foundations & piling",        help: "Concrete pads, deep piles, equipment foundations" },
      { key: "structuralSteelEur",    label: "Structural steel",            help: "Pipe racks, equipment supports, platforms" },
      { key: "concreteMaterialsEur",  label: "Concrete materials on site",  help: "Ready-mix, rebar, formwork delivered" },
      { key: "buildingsEur",          label: "Buildings & enclosures",      help: "Control room, MCC, warehouse, lab" },
      { key: "pavingRoadsEur",        label: "Paving & internal roads",     help: "Asphalt, hardstanding, drainage" },
    ],
  },
  {
    title: "Mechanical (utility scope)",
    icon: Wrench,
    fields: [
      { key: "utilityPipingEur",             label: "Utility & off-site piping",      help: "Cooling water, instrument air, demin water, drainage — process piping lives on the Canvas" },
      { key: "siteEquipmentInstallationEur", label: "Site-equipment installation",    help: "Setting and aligning items from the Site Equipment tab. Process-equipment installation is on the Canvas" },
      { key: "insulationPaintingEur",        label: "Insulation, fireproofing & painting", help: "Site-wide bulk insulation and surface protection" },
    ],
  },
  {
    title: "Electrical & Instrumentation",
    icon: Zap,
    fields: [
      { key: "cablingTraysEur",       label: "Cabling & cable trays",          help: "Low- and medium-voltage cable bulk, trays and supports inside the fence" },
      { key: "substationEur",         label: "In-plant substation & transformers", help: "Step-down from grid tie-in to plant distribution. Grid hookup itself is on the Site & Land tab" },
      { key: "controlRoomDcsEur",     label: "Control room, DCS & SCADA",      help: "Distributed Control System, operator workstations, network hardware" },
      { key: "instrumentationEur",    label: "Field instrumentation",          help: "Transmitters, control valves, analysers, junction boxes" },
    ],
  },
  {
    title: "Indirect services",
    icon: Briefcase,
    fields: [
      { key: "feedEngineeringEur",       label: "Front-End Engineering Design",   help: "Conceptual and basic engineering performed pre-FID" },
      { key: "detailedEngineeringEur",   label: "Detailed engineering",           help: "Post-FID design documents, isometrics, datasheets" },
      { key: "projectManagementEur",     label: "Project management",             help: "Owner and EPC project teams during construction" },
      { key: "epcFeeEur",                label: "EPC contractor fee",             help: "Fixed margin / overhead on the lump-sum contract" },
      { key: "commissioningStartupEur",  label: "Commissioning & start-up",       help: "Pre-startup safety review, performance testing, vendor support" },
      { key: "hsseSecurityEur",          label: "Health, safety, security and environment during construction", help: "Site safety officer, temporary fencing, medical, induction" },
    ],
  },
];

interface Props {
  construction: InfraConstruction;
  onChange: (patch: Partial<InfraConstruction>) => void;
  totalEur: number;
}

export default function ConstructionForm({ construction, onChange, totalEur }: Props) {
  const notesId = useId();
  const contId = useId();
  const directSubtotal = CONSTRUCTION_LINE_KEYS.reduce(
    (sum, k) => sum + (Number(construction[k]) || 0),
    0,
  );
  const contingencyEur = directSubtotal * ((construction.contingencyPct || 0) / 100);

  return (
    <div className="space-y-5 max-w-5xl">
      {GROUPS.map((group) => {
        const Icon = group.icon;
        const subtotal = group.fields.reduce(
          (sum, f) => sum + (Number(construction[f.key]) || 0),
          0,
        );
        return (
          <section key={group.title} className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
            <header className="flex items-center justify-between gap-2 px-5 py-3 border-b border-border bg-muted/40">
              <div className="flex items-center gap-2">
                <span className="h-7 w-7 rounded-md bg-card border border-border flex items-center justify-center">
                  <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                </span>
                <h3 className="text-sm font-semibold text-foreground">{group.title}</h3>
              </div>
              <span className="text-xs text-muted-foreground tabular-nums">
                Subtotal <span className="font-semibold text-foreground ml-1">{formatEur(subtotal)}</span>
              </span>
            </header>
            <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-x-5 gap-y-4">
              {group.fields.map((f) => (
                <ConstructionField
                  key={f.key}
                  fieldKey={f.key}
                  label={f.label}
                  help={f.help}
                  value={Number(construction[f.key]) || 0}
                  onChange={(n) => onChange({ [f.key]: n } as Partial<InfraConstruction>)}
                />
              ))}
            </div>
          </section>
        );
      })}

      <section className="rounded-xl border border-border bg-card shadow-sm p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div>
            <Label htmlFor={contId} className="text-xs">Contingency (%)</Label>
            <EurNumberInput
              id={contId}
              noSymbol
              value={construction.contingencyPct || 0}
              min={0}
              max={100}
              inputClassName="bg-muted/40 border-border h-9 mt-1"
              onChange={(n) => onChange({ contingencyPct: n })}
            />
          </div>
          <div className="text-sm">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Direct subtotal</div>
            <div className="font-semibold tabular-nums">{formatEur(directSubtotal)}</div>
          </div>
          <div className="text-sm">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Contingency amount</div>
            <div className="font-semibold tabular-nums">{formatEur(contingencyEur)}</div>
          </div>
        </div>
        <div>
          <Label htmlFor={notesId} className="text-xs">Notes</Label>
          <Textarea
            id={notesId}
            value={construction.notes ?? ""}
            onChange={(e) => onChange({ notes: e.target.value })}
            className="min-h-[70px] bg-muted/40 border-border mt-1"
            placeholder="Assumptions, exclusions, sourcing notes…"
          />
        </div>
        <div className="pt-3 border-t border-border flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Construction total (incl. contingency)</span>
          <span className="text-xl font-bold text-primary tabular-nums">{formatEur(totalEur)}</span>
        </div>
      </section>
    </div>
  );
}

/* Individual field with linked help text + grouped EUR input */
function ConstructionField({
  fieldKey, label, help, value, onChange,
}: {
  fieldKey: string;
  label: string;
  help?: string;
  value: number;
  onChange: (n: number) => void;
}) {
  const inputId = `cf-${fieldKey}`;
  const helpId = `cf-${fieldKey}-help`;
  return (
    <div>
      <Label htmlFor={inputId} className="text-xs">
        {label} <span className="text-muted-foreground font-normal">(EUR)</span>
      </Label>
      <EurNumberInput
        id={inputId}
        value={value}
        min={0}
        step={1000}
        inputClassName="bg-muted/40 border-border h-9 mt-1"
        ariaDescribedBy={help ? helpId : undefined}
        onChange={onChange}
      />
      {help && (
        <p id={helpId} className="text-[10px] text-muted-foreground mt-1 leading-snug">
          {help}
        </p>
      )}
    </div>
  );
}