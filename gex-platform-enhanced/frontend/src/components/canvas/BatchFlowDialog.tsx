/**
 * BatchFlowDialog — configure a batch (discrete) flow stream.
 * Same shell as ComponentDetailDialog so it feels native.
 */
import { useEffect, useMemo, useState } from "react";
import { Package, Clock, Truck, Info } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { Textarea } from "@/components/ui/textarea";
import {
  BATCH_PERIODS,
  BATCH_TRANSPORT_MODES,
  BATCH_UNITS,
  type BatchFlowConfig,
  computeEquivalentRate,
  defaultBatchConfig,
} from "./batchFlow";

interface BatchFlowDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialConfig?: BatchFlowConfig;
  carrierLabel?: string;
  carrierColor?: string;
  sourceLabel?: string;
  targetLabel?: string;
  flowUnit: string;
  onSave: (config: BatchFlowConfig) => void;
  onConvertToContinuous?: (equivalentRate: number) => void;
}

export default function BatchFlowDialog({
  open,
  onOpenChange,
  initialConfig,
  carrierLabel,
  carrierColor,
  sourceLabel,
  targetLabel,
  flowUnit,
  onSave,
  onConvertToContinuous,
}: BatchFlowDialogProps) {
  const [config, setConfig] = useState<BatchFlowConfig>(
    initialConfig ?? defaultBatchConfig(undefined, flowUnit),
  );

  useEffect(() => {
    if (open) setConfig(initialConfig ?? defaultBatchConfig(undefined, flowUnit));
  }, [open, initialConfig, flowUnit]);

  const equivalentRate = useMemo(
    () => computeEquivalentRate(config, flowUnit),
    [config, flowUnit],
  );

  const update = <K extends keyof BatchFlowConfig>(key: K, value: BatchFlowConfig[K]) =>
    setConfig((c) => ({ ...c, [key]: value }));

  const isValid = config.batchSize > 0 && config.frequency > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Package className="h-5 w-5 text-primary" />
            <DialogTitle>Batch flow configuration</DialogTitle>
          </div>
          <DialogDescription>
            Discrete batches instead of a continuous rate. Average equivalent rate is
            computed below and used by the balance and equation engines.
          </DialogDescription>
        </DialogHeader>

        {/* Carrier summary */}
        <div className="flex items-center gap-3 rounded-md border border-border bg-muted/30 px-3 py-2">
          {carrierColor && (
            <span
              className="h-3 w-3 rounded-full border border-border"
              style={{ backgroundColor: carrierColor }}
            />
          )}
          <div className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{sourceLabel ?? "Source"}</span>
            {" → "}
            <span className="font-medium text-foreground">{targetLabel ?? "Target"}</span>
            {carrierLabel && (
              <span className="ml-2 text-muted-foreground">· {carrierLabel}</span>
            )}
          </div>
        </div>

        <div className="space-y-5 pt-2">
          {/* Batch quantity */}
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Batch quantity
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Size per batch</Label>
                <Input
                  type="number"
                  step="any"
                  value={config.batchSize}
                  onChange={(e) => update("batchSize", parseFloat(e.target.value) || 0)}
                />
              </div>
              <div>
                <Label className="text-xs">Unit</Label>
                <Select value={config.batchUnit} onValueChange={(v) => update("batchUnit", v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {BATCH_UNITS.map((u) => (
                      <SelectItem key={u} value={u}>{u}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </section>

          {/* Frequency */}
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" /> Frequency
            </h3>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">Mode</Label>
                <Select
                  value={config.frequencyMode}
                  onValueChange={(v) => update("frequencyMode", v as BatchFlowConfig["frequencyMode"])}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="perPeriod">Batches per period</SelectItem>
                    <SelectItem value="interval">Interval between batches</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">
                  {config.frequencyMode === "perPeriod" ? "Batches" : "Interval"}
                </Label>
                <Input
                  type="number"
                  step="any"
                  value={config.frequency}
                  onChange={(e) => update("frequency", parseFloat(e.target.value) || 0)}
                />
              </div>
              <div>
                <Label className="text-xs">Period</Label>
                <Select value={config.period} onValueChange={(v) => update("period", v as BatchFlowConfig["period"])}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {BATCH_PERIODS.map((p) => (
                      <SelectItem key={p} value={p}>{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </section>

          {/* Timing */}
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Timing
            </h3>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">Charge duration (min)</Label>
                <Input
                  type="number"
                  step="any"
                  value={config.chargeDuration ?? ""}
                  onChange={(e) =>
                    update("chargeDuration", e.target.value ? parseFloat(e.target.value) : undefined)
                  }
                  placeholder="optional"
                />
              </div>
              <div>
                <Label className="text-xs">Arrival pattern</Label>
                <Select
                  value={config.arrivalPattern}
                  onValueChange={(v) => update("arrivalPattern", v as BatchFlowConfig["arrivalPattern"])}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="regular">Regular</SelectItem>
                    <SelectItem value="scheduled">Scheduled</SelectItem>
                    <SelectItem value="stochastic">Stochastic</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {config.arrivalPattern === "stochastic" && (
                <div>
                  <Label className="text-xs">Variability (± %)</Label>
                  <Input
                    type="number"
                    step="any"
                    value={config.variability ?? ""}
                    onChange={(e) =>
                      update("variability", e.target.value ? parseFloat(e.target.value) : undefined)
                    }
                  />
                </div>
              )}
            </div>
          </section>

          {/* Buffering */}
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Buffering downstream
            </h3>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">Idle behavior</Label>
                <Select
                  value={config.idleBehavior}
                  onValueChange={(v) => update("idleBehavior", v as BatchFlowConfig["idleBehavior"])}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No buffer</SelectItem>
                    <SelectItem value="buffered">Buffered (tank / silo)</SelectItem>
                    <SelectItem value="stop_downstream">Stops downstream</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {config.idleBehavior === "buffered" && (
                <>
                  <div>
                    <Label className="text-xs">Buffer capacity</Label>
                    <Input
                      type="number"
                      step="any"
                      value={config.bufferCapacity ?? ""}
                      onChange={(e) =>
                        update("bufferCapacity", e.target.value ? parseFloat(e.target.value) : undefined)
                      }
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Buffer unit</Label>
                    <Select
                      value={config.bufferUnit ?? config.batchUnit}
                      onValueChange={(v) => update("bufferUnit", v)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {BATCH_UNITS.map((u) => (
                          <SelectItem key={u} value={u}>{u}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </>
              )}
            </div>
          </section>

          {/* Transport */}
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <Truck className="h-3 w-3" /> Transport
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Mode</Label>
                <Select
                  value={config.transportMode ?? "truck"}
                  onValueChange={(v) => update("transportMode", v as BatchFlowConfig["transportMode"])}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {BATCH_TRANSPORT_MODES.map((m) => (
                      <SelectItem key={m} value={m}>{m.replace("_", " ")}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label className="text-xs">Notes</Label>
              <Textarea
                rows={2}
                value={config.notes ?? ""}
                onChange={(e) => update("notes", e.target.value)}
                placeholder="Optional operational notes…"
              />
            </div>
          </section>

          {/* Computed rate */}
          <section className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2.5">
            <div className="flex items-center gap-2 text-xs">
              <Info className="h-3.5 w-3.5 text-primary" />
              <span className="text-muted-foreground">Equivalent continuous rate:</span>
              <span className="font-semibold tabular-nums text-foreground">
                {equivalentRate.toFixed(equivalentRate < 10 ? 3 : 2)} {flowUnit}
              </span>
            </div>
          </section>
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          {onConvertToContinuous && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onConvertToContinuous(equivalentRate)}
            >
              Convert to continuous flow
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!isValid}
            onClick={() => {
              onSave(config);
              onOpenChange(false);
            }}
          >
            Save batch
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}