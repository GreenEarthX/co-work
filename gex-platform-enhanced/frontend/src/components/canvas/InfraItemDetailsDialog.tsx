/**
 * InfraItemDetailsDialog — Edit a single infrastructure equipment item.
 * Fields mirror the procurement record (NodeProcurement) so manual entry and
 * procurement-database fills populate the same shape.
 */
import { useEffect, useId, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/Button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/Select";
import { Database } from "lucide-react";
import type { InfraEquipmentItem } from "@/lib/siteInfrastructure";
import type { NodeProcurement } from "@/lib/procurementSync";
import EurNumberInput from "@/components/ui/EurNumberInput";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: InfraEquipmentItem | null;
  onSave: (patch: Partial<InfraEquipmentItem>) => void;
  onOpenProcurement: () => void;
}

const STRATEGIES = ["Best Price", "Best Efficiency", "Scale Optimised", "Custom"];

function emptyProcurement(): NodeProcurement {
  return {
    manufacturer: "", model: "", country: "", priceEur: 0, priceDisplay: "",
    efficiency: "", leadTimeMonths: 0, trl: 9, scaleThreshold: "",
    strategy: "Custom", plantScaleQty: 1, source: "manual",
    updatedAt: new Date().toISOString(),
  };
}

export default function InfraItemDetailsDialog({ open, onOpenChange, item, onSave, onOpenProcurement }: Props) {
  const [qty, setQty] = useState(1);
  const [unitCost, setUnitCost] = useState(0);
  const [notes, setNotes] = useState("");
  const [proc, setProc] = useState<NodeProcurement>(emptyProcurement());
  const idManu = useId();
  const idModel = useId();
  const idCountry = useId();
  const idStrategy = useId();
  const idEff = useId();
  const idLead = useId();
  const idTrl = useId();
  const idScale = useId();
  const idQty = useId();
  const idUnit = useId();
  const idNotes = useId();

  useEffect(() => {
    if (!item) return;
    setQty(item.quantity || 1);
    setUnitCost(item.unitCostEur || 0);
    setNotes(item.notes ?? "");
    setProc(item.procurement ?? emptyProcurement());
  }, [item]);

  if (!item) return null;

  const handleSave = () => {
    const hasProcData = proc.manufacturer || proc.model || proc.country;
    onSave({
      quantity: qty,
      unitCostEur: unitCost,
      notes,
      procurement: hasProcData
        ? { ...proc, priceEur: unitCost, priceDisplay: proc.priceDisplay || (unitCost ? `€ ${unitCost.toLocaleString()}` : ""), updatedAt: new Date().toISOString() }
        : undefined,
    });
    onOpenChange(false);
  };

  const inputCls = "bg-muted/40 border-border";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between gap-4">
            <span>{item.label}</span>
            <span className="text-xs font-mono text-muted-foreground">{item.equipmentId}</span>
          </DialogTitle>
          <DialogDescription>
            Configure procurement and cost details for this infrastructure item.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 pt-2">
          <Button variant="outline" size="sm" onClick={onOpenProcurement} className="gap-2">
            <Database className="h-3.5 w-3.5" /> Fill from Procurement Database
          </Button>

          {/* Commercial */}
          <section className="space-y-3">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Commercial</h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor={idManu} className="text-xs">Manufacturer</Label>
                <Input id={idManu} className={inputCls} value={proc.manufacturer} onChange={(e) => setProc({ ...proc, manufacturer: e.target.value })} />
              </div>
              <div>
                <Label htmlFor={idModel} className="text-xs">Model</Label>
                <Input id={idModel} className={inputCls} value={proc.model} onChange={(e) => setProc({ ...proc, model: e.target.value })} />
              </div>
              <div>
                <Label htmlFor={idCountry} className="text-xs">Country of origin</Label>
                <Input id={idCountry} className={inputCls} value={proc.country} onChange={(e) => setProc({ ...proc, country: e.target.value })} />
              </div>
              <div>
                <Label htmlFor={idStrategy} className="text-xs">Sourcing strategy</Label>
                <Select value={proc.strategy} onValueChange={(v) => setProc({ ...proc, strategy: v })}>
                  <SelectTrigger id={idStrategy} className={inputCls}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STRATEGIES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </section>

          {/* Performance */}
          <section className="space-y-3">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Performance</h3>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label htmlFor={idEff} className="text-xs">Efficiency</Label>
                <Input id={idEff} className={inputCls} value={proc.efficiency} onChange={(e) => setProc({ ...proc, efficiency: e.target.value })} placeholder="e.g. 70%" />
              </div>
              <div>
                <Label htmlFor={idLead} className="text-xs">Lead time (months)</Label>
                <Input id={idLead} className={inputCls} type="number" min={0} value={proc.leadTimeMonths} onChange={(e) => setProc({ ...proc, leadTimeMonths: Number(e.target.value) || 0 })} />
              </div>
              <div>
                <Label htmlFor={idTrl} className="text-xs">Technology Readiness Level</Label>
                <Input id={idTrl} className={inputCls} type="number" min={1} max={9} value={proc.trl} onChange={(e) => setProc({ ...proc, trl: Number(e.target.value) || 0 })} />
              </div>
              <div className="col-span-3">
                <Label htmlFor={idScale} className="text-xs">Scale threshold</Label>
                <Input id={idScale} className={inputCls} value={proc.scaleThreshold ?? ""} onChange={(e) => setProc({ ...proc, scaleThreshold: e.target.value })} placeholder="e.g. up to 5 MW" />
              </div>
            </div>
          </section>

          {/* Cost */}
          <section className="space-y-3">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Cost</h3>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label htmlFor={idQty} className="text-xs">Quantity</Label>
                <Input id={idQty} className={inputCls} type="number" min={0} value={qty} onChange={(e) => setQty(Number(e.target.value) || 0)} />
              </div>
              <div>
                <Label htmlFor={idUnit} className="text-xs">Unit cost (EUR)</Label>
                <EurNumberInput
                  id={idUnit}
                  value={unitCost}
                  min={0}
                  step={1000}
                  inputClassName={inputCls}
                  onChange={setUnitCost}
                />
              </div>
              <div>
                <Label className="text-xs">Line total</Label>
                <div className="h-10 px-3 flex items-center rounded-md bg-muted/60 border border-border text-sm font-semibold tabular-nums">
                  € {((qty || 0) * (unitCost || 0)).toLocaleString()}
                </div>
              </div>
            </div>
          </section>

          {/* Notes */}
          <section className="space-y-3">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Notes</h3>
            <Label htmlFor={idNotes} className="sr-only">Internal notes</Label>
            <Textarea id={idNotes} className={inputCls + " min-h-[70px]"} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Internal notes (optional)" />
          </section>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSave}>Save details</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}