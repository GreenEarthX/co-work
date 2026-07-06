/**
 * Plant-level settings panel — configures shared parameters like HOURS_YEAR
 * that propagate to all equipment instances via the equation engine.
 */
import { useState } from "react";
import { Settings2, Route, X, Plus } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { engineInstance } from "@/engine/EquationEngine";
import type { Node } from "@xyflow/react";

interface PlantSettingsPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  criticalPathMode?: boolean;
  onToggleCriticalPathMode?: () => void;
  criticalPathNodeIds: Set<string>;
  onCriticalPathChange: (ids: Set<string>) => void;
  equipmentNodes: Node[];
  hoursYear: number;
  onHoursYearChange: (val: number) => void;
  plantAvailability: number;
  onPlantAvailabilityChange: (val: number) => void;
}

export function PlantSettingsPanel({
  open, onOpenChange,
  criticalPathMode, onToggleCriticalPathMode,
  criticalPathNodeIds, onCriticalPathChange, equipmentNodes,
  hoursYear, onHoursYearChange,
  plantAvailability, onPlantAvailabilityChange,
}: PlantSettingsPanelProps) {
  const [addOpen, setAddOpen] = useState(false);

  const handleHoursChange = (val: string) => {
    const num = parseFloat(val);
    if (!isNaN(num) && num >= 0 && num <= 8760) {
      onHoursYearChange(num);
      engineInstance.setPlantParameter("HOURS_YEAR", num, "h/yr");
    }
  };

  const handleAvailabilityChange = (val: string) => {
    const num = parseFloat(val);
    if (!isNaN(num) && num >= 0 && num <= 100) {
      onPlantAvailabilityChange(num);
    }
  };

  const effectiveHours = Math.round(hoursYear * (plantAvailability / 100));

  const criticalNodes = equipmentNodes.filter((n) => criticalPathNodeIds.has(n.id));
  const availableToAdd = equipmentNodes.filter((n) => !criticalPathNodeIds.has(n.id));

  const removeFromCriticalPath = (nodeId: string) => {
    const next = new Set(criticalPathNodeIds);
    next.delete(nodeId);
    onCriticalPathChange(next);
  };

  const addToCriticalPath = (nodeId: string) => {
    const next = new Set(criticalPathNodeIds);
    next.add(nodeId);
    onCriticalPathChange(next);
    setAddOpen(false);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-96 sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2 text-base">
            <Settings2 className="h-4 w-4 text-primary" />
            Plant Settings
          </SheetTitle>
          <SheetDescription className="text-xs">
            Plant-level parameters shared across all equipment. Changes trigger
            re-resolution of every instance on the canvas.
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="mt-6 h-[calc(100vh-140px)]">
          <div className="space-y-5 pr-3">
            {/* Annual Hours per Year */}
            <div className="space-y-2">
              <div className="flex items-center gap-1.5">
                <Label htmlFor="hours-year" className="text-xs font-semibold">
                  Total Calendar Hours per Year
                </Label>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="inline-flex items-center justify-center h-4 w-4 rounded-full border border-muted-foreground/30 text-[9px] font-semibold text-muted-foreground cursor-help">
                      i
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-60 text-xs">
                    365 × 24 = 8,760 hours, or 366 × 24 = 8,784 hours for a leap year.
                  </TooltipContent>
                </Tooltip>
              </div>
              <div className="flex items-center gap-2">
                <Input
                  id="hours-year"
                  type="number"
                  min={0}
                  max={8760}
                  step={100}
                  value={hoursYear}
                  onChange={(e) => handleHoursChange(e.target.value)}
                  className="h-9 font-mono text-sm"
                />
                <span className="text-xs text-muted-foreground whitespace-nowrap">h / yr</span>
              </div>
            </div>

            {/* Plant Availability */}
            <div className="space-y-2">
              <Label htmlFor="plant-availability" className="text-xs font-semibold">
                Plant Availability
              </Label>
              <div className="flex items-center gap-2">
                <Input
                  id="plant-availability"
                  type="number"
                  min={0}
                  max={100}
                  step={0.1}
                  value={plantAvailability}
                  onChange={(e) => handleAvailabilityChange(e.target.value)}
                  className="h-9 font-mono text-sm"
                />
                <span className="text-xs text-muted-foreground whitespace-nowrap">%</span>
              </div>
            </div>

            {/* Effective Operating Hours (auto-calculated) */}
            <div className="space-y-2">
              <Label className="text-xs font-semibold">
                Effective Operating Hours
              </Label>
              <div className="flex items-center gap-2">
                <div className="h-9 flex-1 rounded-md border border-border bg-muted/50 px-3 flex items-center font-mono text-sm text-foreground">
                  {effectiveHours.toLocaleString()}
                </div>
                <span className="text-xs text-muted-foreground whitespace-nowrap">h / yr</span>
              </div>
              <p className="text-[10px] text-muted-foreground">
                Annual Hours × Plant Availability. This is the effective time the plant is expected to operate per year.
              </p>
            </div>

            {/* Critical Path Section */}
            <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-3">
              <div className="flex items-center gap-2">
                <Route className="h-4 w-4 text-primary" />
                <Label className="text-xs font-semibold">Critical Path</Label>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="inline-flex items-center justify-center h-4 w-4 rounded-full border border-muted-foreground/30 text-[9px] font-semibold text-muted-foreground cursor-help">
                      i
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-52 text-xs">
                    Equipment on the critical path will inherit the plant availability factor for throughput calculations.
                  </TooltipContent>
                </Tooltip>
              </div>
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                Select the equipment that defines the critical production path. These units will automatically inherit {effectiveHours.toLocaleString()} h/yr as their operating hours.
              </p>

              {/* Select on canvas button */}
              <Button
                variant={criticalPathMode ? "default" : "outline"}
                size="sm"
                className={`h-9 w-full text-xs gap-2 transition-all duration-150 ${criticalPathMode ? "ring-2 ring-primary/40" : ""}`}
                onClick={() => {
                  onToggleCriticalPathMode?.();
                  if (!criticalPathMode) onOpenChange(false);
                }}
              >
                <Route className="h-3.5 w-3.5" />
                {criticalPathMode ? `Done (${criticalPathNodeIds.size} selected)` : "Select on Canvas"}
              </Button>

              {/* Critical path equipment list */}
              {criticalNodes.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                    Selected Equipment ({criticalNodes.length})
                  </p>
                  <div className="space-y-1">
                    {criticalNodes.map((node) => (
                      <div
                        key={node.id}
                        className="flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 group/item"
                      >
                        <div className="h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0" />
                        <span className="text-[10px] font-medium text-foreground flex-1 truncate">
                          {node.data.label as string}
                        </span>
                        <span className="text-[9px] font-mono text-muted-foreground whitespace-nowrap shrink-0">
                          {effectiveHours.toLocaleString()} h
                        </span>
                        <button
                          onClick={() => removeFromCriticalPath(node.id)}
                          className="h-4 w-4 rounded flex items-center justify-center text-muted-foreground opacity-0 group-hover/item:opacity-100 hover:text-destructive hover:bg-destructive/10 transition-all"
                          title="Remove from critical path"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Add equipment from list */}
              {availableToAdd.length > 0 && (
                <Popover open={addOpen} onOpenChange={setAddOpen}>
                  <PopoverTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-7 w-full text-[10px] gap-1.5 text-muted-foreground hover:text-foreground">
                      <Plus className="h-3 w-3" />
                      Add Equipment
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-64 p-1.5" side="bottom" align="start">
                    <ScrollArea className="max-h-48">
                      <div className="space-y-0.5">
                        {availableToAdd.map((node) => (
                          <button
                            key={node.id}
                            onClick={() => addToCriticalPath(node.id)}
                            className="w-full text-left rounded-md px-2.5 py-1.5 text-[10px] font-medium text-foreground hover:bg-accent transition-colors"
                          >
                            {node.data.label as string}
                          </button>
                        ))}
                      </div>
                    </ScrollArea>
                  </PopoverContent>
                </Popover>
              )}

              {criticalNodes.length === 0 && (
                <p className="text-[10px] text-muted-foreground/60 italic text-center py-1">
                  No equipment selected yet
                </p>
              )}
            </div>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
