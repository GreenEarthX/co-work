/**
 * ProcurementSimulatorPage — Two-step wizard for generating and comparing
 * full-plant supplier configurations.
 *
 * Reachable at /procurement-simulator.
 * GEX adaptation: standalone mode (no canvas commit), uses GEX Layout shell.
 */
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ArrowLeft, Play, LayoutGrid, Table2, ListChecks } from "lucide-react";
import { useProcurementSimulator } from "./useProcurementSimulator";
import ConstraintPanel from "./components/ConstraintPanel";
import ConfigCards from "./components/results/ConfigCards";
import ComparisonMatrix from "./components/results/ComparisonMatrix";
import ShortlistBuilder from "./components/results/ShortlistBuilder";
import type { Configuration } from "@/lib/procurement/simulatorTypes";

type ViewMode = "cards" | "shortlist" | "matrix";

export function ProcurementSimulatorPage() {
  const plantId = "default";
  const sim = useProcurementSimulator(plantId);

  const [step, setStep] = useState<1 | 2>(1);
  const [view, setView] = useState<ViewMode>("cards");
  const [committingId, setCommittingId] = useState<string | null>(null);

  const configurations = sim.result?.configurations ?? [];
  const matchCounts = sim.liveMatchCounts;

  const handleCommit = async (config: Configuration) => {
    setCommittingId(config.id);
    try {
      const res = await sim.commitConfiguration(config);
      if (res.ok) {
        // Canvas commit succeeded (not yet wired)
      }
    } finally {
      setCommittingId(null);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div>
        <h1 className="font-display text-2xl font-bold text-[var(--text-primary)] mb-1">
          Procurement Simulator
        </h1>
        <p className="text-sm text-[var(--text-secondary)]">
          Greedy-diversified configuration engine — per-slot candidate filtering, 5 soft compatibility rules, 3 result views.
        </p>
      </div>

      {/* Step rail + action */}
      <div className="sticky top-0 z-20 -mx-1 px-1 py-3 bg-[var(--bg-primary)]/95 backdrop-blur border-b border-[var(--border-primary)]">
        <div className="flex items-center justify-between">
          <StepRail step={step} onSelect={(s) => setStep(s)} />
          <div className="flex items-center gap-2">
            {step === 1 ? (
              <Button
                size="sm"
                onClick={() => {
                  sim.run();
                  setStep(2);
                }}
                disabled={sim.equipment.length === 0}
              >
                <Play className="h-3.5 w-3.5 mr-1.5" /> Run simulation
              </Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={() => setStep(1)}>
                <ArrowLeft className="h-3.5 w-3.5 mr-1.5" /> Edit constraints
              </Button>
            )}
          </div>
        </div>
      </div>

      {step === 1 && (
        <div className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)]">
          <ConstraintPanel
            globals={sim.globals}
            setGlobals={sim.setGlobals}
            equipment={sim.equipment}
            matchCounts={matchCounts}
            onEquipmentChange={sim.setEquipmentConstraint}
            onCopyToAll={sim.copyToAllOfType}
            totalSlotMatches={sim.totalSlotMatches}
            totalSlotPool={sim.totalSlotPool}
          />
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-[var(--border-primary)]">
            <div className="flex">
              <ViewTab active={view === "cards"} onClick={() => setView("cards")} icon={<LayoutGrid className="h-3.5 w-3.5" />} label="Configurations" />
              <ViewTab active={view === "shortlist"} onClick={() => setView("shortlist")} icon={<ListChecks className="h-3.5 w-3.5" />} label="Shortlist" />
              <ViewTab active={view === "matrix"} onClick={() => setView("matrix")} icon={<Table2 className="h-3.5 w-3.5" />} label="Comparison Matrix" />
            </div>
            <div className="text-[11px] text-[var(--text-secondary)] tabular-nums pr-1">
              {configurations.length} configuration{configurations.length === 1 ? "" : "s"}
            </div>
          </div>

          {view === "cards" && (
            <ConfigCards configurations={configurations} onCommit={handleCommit} committingId={committingId} />
          )}
          {view === "shortlist" && (
            <ShortlistBuilder configurations={configurations} onCommit={handleCommit} />
          )}
          {view === "matrix" && (
            <ComparisonMatrix configurations={configurations} onCommit={handleCommit} />
          )}
        </div>
      )}
    </div>
  );
}

function StepRail({ step, onSelect }: { step: 1 | 2; onSelect: (n: 1 | 2) => void }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <StepNode n={1} label="Constraints" active={step === 1} done={step > 1} onClick={() => onSelect(1)} />
      <div className="h-px w-12 bg-[var(--border-primary)]" />
      <StepNode n={2} label="Results" active={step === 2} done={false} onClick={() => onSelect(2)} />
    </div>
  );
}

function StepNode({
  n,
  label,
  active,
  done,
  onClick,
}: { n: number; label: string; active: boolean; done: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="flex items-center gap-2 group">
      <span
        className={`h-5 w-5 rounded-full flex items-center justify-center text-[10px] font-semibold border transition ${
          active
            ? "bg-[#0ea5a0] text-white border-[#0ea5a0]"
            : done
              ? "bg-[#0ea5a0]/10 text-[#0ea5a0] border-[#0ea5a0]/30"
              : "bg-white text-gray-400 border-gray-300"
        }`}
      >
        {n}
      </span>
      <span
        className={`text-[11px] uppercase tracking-[0.12em] ${
          active ? "text-[var(--text-primary)] font-medium" : "text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]"
        }`}
      >
        {label}
      </span>
    </button>
  );
}

function ViewTab({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-4 py-2.5 text-xs transition border-b-2 ${
        active
          ? "border-[#0ea5a0] text-[var(--text-primary)] font-medium"
          : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

export default ProcurementSimulatorPage;
