/**
 * CheckFindingsPanel — Unified panel showing all process flow validation results.
 * Auto-runs checks on open; results shown in tabbed categories.
 */
import { useState, useEffect, useRef } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/Badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

import {
  AlertTriangle,
  CheckCircle2,
  Info,
  XCircle,
  ChevronDown,
  ChevronRight,
  Scale,
  Cpu,
  Zap,
  Gauge,
  Loader2,
} from "lucide-react";
import { useEngineCheck } from "@/engine/hooks/useEquationEngine";
import type { RuleFinding, Severity } from "@/engine/types";
import type { BalanceReport, FlowImbalance } from "@/components/canvas/flowBalanceEngine";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  balanceReport: BalanceReport;
}

const SEVERITY_CONFIG: Record<Severity, { icon: typeof XCircle; color: string; bg: string; border: string; label: string }> = {
  ERROR: { icon: XCircle, color: "text-destructive", bg: "bg-destructive/10", border: "border-destructive/30", label: "Error" },
  WARNING: { icon: AlertTriangle, color: "text-amber-500", bg: "bg-amber-50 dark:bg-amber-950/20", border: "border-amber-300/40", label: "Warning" },
  CONSISTENCY: { icon: AlertTriangle, color: "text-amber-600", bg: "bg-amber-50/80 dark:bg-amber-950/15", border: "border-amber-200/40", label: "Consistency" },
  VALIDATION: { icon: Info, color: "text-blue-500", bg: "bg-blue-50 dark:bg-blue-950/20", border: "border-blue-300/40", label: "Validation" },
  CONTINUITY: { icon: AlertTriangle, color: "text-amber-500", bg: "bg-amber-50 dark:bg-amber-950/20", border: "border-amber-300/40", label: "Continuity" },
  INFO: { icon: Info, color: "text-muted-foreground", bg: "bg-muted/40", border: "border-border", label: "Info" },
};

type FlagCategory = "balance" | "capacity" | "consistency" | "validation";

const TAB_CONFIG: { key: FlagCategory; icon: typeof Scale; label: string; shortLabel: string; color: string }[] = [
  { key: "balance", icon: Scale, label: "Mass & Energy Balance", shortLabel: "Balance", color: "text-blue-500" },
  { key: "capacity", icon: Cpu, label: "Equipment Capacity", shortLabel: "Capacity", color: "text-destructive" },
  { key: "consistency", icon: Gauge, label: "Consistency", shortLabel: "Consistency", color: "text-amber-600" },
  { key: "validation", icon: Zap, label: "Parameter Validation", shortLabel: "Validation", color: "text-emerald-600" },
];

function categorizeFinding(f: RuleFinding): FlagCategory {
  if (f.severity === "CONSISTENCY" || f.severity === "CONTINUITY") return "consistency";
  if (f.severity === "VALIDATION" || f.severity === "INFO") return "validation";
  return "capacity";
}

function FindingCard({ finding }: { finding: RuleFinding }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = SEVERITY_CONFIG[finding.severity];
  const Icon = cfg.icon;

  return (
    <div className={`rounded-lg border ${cfg.border} ${cfg.bg} p-3 space-y-1.5 transition-all`}>
      <div className="flex items-start gap-2">
        <Icon className={`h-4 w-4 ${cfg.color} shrink-0 mt-0.5`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <Badge variant="outline" className={`h-4 text-[9px] px-1.5 ${cfg.color} border-current/30`}>
              {cfg.label}
            </Badge>
            <span className="text-[10px] font-mono text-muted-foreground truncate">
              {finding.issueCode}
            </span>
          </div>
          <p className="text-xs text-foreground/90 leading-relaxed">{finding.message}</p>

          {finding.keysAffected.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {finding.keysAffected.map((k) => (
                <span key={k} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-background border border-border text-muted-foreground">
                  {k}
                </span>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-muted-foreground hover:text-foreground p-0.5"
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </button>
      </div>

      {expanded && finding.evidenceJson && (
        <div className="ml-6 mt-1 p-2 rounded bg-background/60 border border-border">
          <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Evidence</p>
          <div className="text-[10px] font-mono text-muted-foreground space-y-0.5">
            {Object.entries(finding.evidenceJson).map(([k, v]) => (
              <div key={k}><span className="text-foreground/70">{k}:</span> {typeof v === 'number' ? Number(v.toPrecision(6)) : String(v)}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function BalanceImbalanceCard({ imb }: { imb: FlowImbalance }) {
  return (
    <div className="rounded-lg border border-blue-300/30 bg-blue-50/50 dark:bg-blue-950/20 p-3 space-y-1">
      <div className="flex items-start gap-2">
        <Scale className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <Badge variant="outline" className="h-4 text-[9px] px-1.5 text-blue-500 border-current/30">
              Balance
            </Badge>
            <span className="text-[10px] font-mono text-muted-foreground truncate">
              {imb.nodeLabel}
            </span>
          </div>
          <p className="text-xs text-foreground/90 leading-relaxed">
            Flow imbalance: In {imb.totalIn.toFixed(1)} → Out {imb.totalOut.toFixed(1)} {imb.unit}
          </p>
          <p className="text-[10px] font-mono text-destructive mt-0.5">
            {imb.loss > 0 ? "−" : "+"}{Math.abs(imb.loss).toFixed(1)} {imb.unit} ({Math.abs(imb.lossPercent).toFixed(1)}%)
          </p>
        </div>
      </div>
    </div>
  );
}

export function CheckFindingsPanel({ open, onOpenChange, balanceReport }: Props) {
  const { runFullCheck, findings } = useEngineCheck();
  const [hasRun, setHasRun] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const lastOpenRef = useRef(false);

  // Auto-run checks when panel opens
  useEffect(() => {
    if (open && !lastOpenRef.current) {
      setIsRunning(true);
      // Small delay for visual feedback
      const t = setTimeout(() => {
        runFullCheck();
        setHasRun(true);
        setIsRunning(false);
      }, 300);
      return () => clearTimeout(t);
    }
    lastOpenRef.current = open;
  }, [open, runFullCheck]);

  // Categorize rule findings
  const categorized = new Map<FlagCategory, RuleFinding[]>();
  for (const f of findings) {
    const cat = categorizeFinding(f);
    if (!categorized.has(cat)) categorized.set(cat, []);
    categorized.get(cat)!.push(f);
  }

  const balanceCount = balanceReport.imbalances.length;
  const capacityCount = categorized.get("capacity")?.length ?? 0;
  const consistencyCount = categorized.get("consistency")?.length ?? 0;
  const validationCount = categorized.get("validation")?.length ?? 0;
  const counts: Record<FlagCategory, number> = { balance: balanceCount, capacity: capacityCount, consistency: consistencyCount, validation: validationCount };
  const totalIssues = balanceCount + findings.length;
  const allClear = hasRun && !isRunning && totalIssues === 0 && balanceReport.balanced;

  // Pick the first tab that has issues, or default to "balance"
  const defaultTab = TAB_CONFIG.find(t => counts[t.key] > 0)?.key ?? "balance";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[420px] sm:w-[480px] p-0 flex flex-col">
        <SheetHeader className="p-5 pb-3 border-b border-border">
          <SheetTitle className="text-base flex items-center gap-2">
            <span className="h-8 w-8 rounded-md bg-primary/10 text-primary flex items-center justify-center">
              <CheckCircle2 className="h-4 w-4" />
            </span>
            Process Flow Check
          </SheetTitle>
          <SheetDescription className="text-xs text-muted-foreground">
            Validates mass/energy balance, equipment capacity, consistency, and parameter ranges.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 min-h-0 overflow-y-auto">
          {isRunning ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-3">
              <Loader2 className="h-8 w-8 text-primary animate-spin" />
              <p className="text-sm text-muted-foreground">Running checks…</p>
            </div>
          ) : !hasRun ? (
            <div className="text-center py-12 space-y-3 px-4">
              <div className="h-12 w-12 rounded-full bg-muted/60 mx-auto flex items-center justify-center">
                <CheckCircle2 className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">Preparing validation…</p>
            </div>
          ) : allClear ? (
            <div className="text-center py-16 space-y-3 px-4">
              <div className="h-14 w-14 rounded-full bg-success/10 mx-auto flex items-center justify-center">
                <CheckCircle2 className="h-7 w-7 text-success" />
              </div>
              <p className="text-sm font-medium text-success">All Checks Passed ✅</p>
              <p className="text-[10px] text-muted-foreground">
                Flow balance, equipment capacity, and parameter validation all clear.
              </p>
            </div>
          ) : (
            <div className="flex flex-col h-full">

              {/* Tabbed results */}
              <Tabs defaultValue={defaultTab} className="flex-1 flex flex-col px-4 pb-4">
                <TabsList className="w-full grid grid-cols-4 h-9 mb-3">
                  {TAB_CONFIG.map(t => {
                    const Icon = t.icon;
                    const c = counts[t.key];
                    return (
                      <TabsTrigger key={t.key} value={t.key} className="text-[10px] gap-1 px-1.5 data-[state=active]:shadow-sm">
                        <Icon className="h-3 w-3" />
                        <span className="hidden sm:inline">{t.shortLabel}</span>
                        {c > 0 && (
                          <Badge variant="secondary" className="h-4 min-w-[16px] text-[9px] px-1 ml-0.5">
                            {c}
                          </Badge>
                        )}
                      </TabsTrigger>
                    );
                  })}
                </TabsList>

                {/* Balance tab */}
                <TabsContent value="balance" className="flex-1 space-y-2 mt-0">
                  {balanceCount === 0 ? (
                    <EmptyCategory message="All flows balanced, no imbalances detected." />
                  ) : (
                    balanceReport.imbalances.map((imb, i) => (
                      <BalanceImbalanceCard key={i} imb={imb} />
                    ))
                  )}
                </TabsContent>

                {/* Capacity tab */}
                <TabsContent value="capacity" className="flex-1 space-y-2 mt-0">
                  {capacityCount === 0 ? (
                    <EmptyCategory message="No equipment capacity issues found." />
                  ) : (
                    categorized.get("capacity")!.map((f, i) => (
                      <FindingCard key={`${f.issueCode}-${i}`} finding={f} />
                    ))
                  )}
                </TabsContent>

                {/* Consistency tab */}
                <TabsContent value="consistency" className="flex-1 space-y-2 mt-0">
                  {consistencyCount === 0 ? (
                    <EmptyCategory message="No consistency issues found." />
                  ) : (
                    categorized.get("consistency")!.map((f, i) => (
                      <FindingCard key={`${f.issueCode}-${i}`} finding={f} />
                    ))
                  )}
                </TabsContent>

                {/* Validation tab */}
                <TabsContent value="validation" className="flex-1 space-y-2 mt-0">
                  {validationCount === 0 ? (
                    <EmptyCategory message="All parameters within valid ranges." />
                  ) : (
                    categorized.get("validation")!.map((f, i) => (
                      <FindingCard key={`${f.issueCode}-${i}`} finding={f} />
                    ))
                  )}
                </TabsContent>
              </Tabs>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function EmptyCategory({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/5 p-3">
      <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
      <p className="text-xs text-success">{message}</p>
    </div>
  );
}
