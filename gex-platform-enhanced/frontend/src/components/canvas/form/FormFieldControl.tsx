import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Lock, Unlock } from "lucide-react";
import type { FieldDef } from "@/components/canvas/fieldDictionary";

interface EngineFieldInfo {
  displayValue?: string;
  source?: string;
  isDerived?: boolean;
  isOverridden?: boolean;
  isEditable?: boolean;
  allowedUnits?: string[];
  selectedUnit?: string;
  onUnitChange?: (unit: string) => void;
  onToggleOverride?: () => void;
}

export interface FormFieldControlProps {
  field: FieldDef;
  value: string;
  onChange: (value: string) => void;
  engineInfo?: EngineFieldInfo;
  disabled?: boolean;
}

const baseFieldClass = "h-10 text-xs transition-colors";

const SOURCE_BADGE: Record<string, { label: string; className: string }> = {
  DERIVED: { label: "Derived", className: "border-muted-foreground/40 text-muted-foreground bg-muted/60" },
  DEFAULT_LIBRARY: { label: "Default", className: "border-blue-400/40 text-blue-600 bg-blue-50 dark:bg-blue-950/30 dark:text-blue-400" },
  OVERRIDE: { label: "Overridden", className: "border-orange-400/40 text-orange-600 bg-orange-50 dark:bg-orange-950/30 dark:text-orange-400" },
  USER: { label: "", className: "" },
};

const FormFieldControl = ({ field, value, onChange, engineInfo, disabled }: FormFieldControlProps) => {
  const isFilled = !!value.trim();
  const isRequiredEmpty = !!field.required && !isFilled;
  const isDerived = engineInfo?.isDerived && !engineInfo?.isOverridden;
  const source = engineInfo?.source ?? "";

  // Shell color based on engine source or fill state
  const shellClass = isDerived
    ? "border-muted-foreground/30 bg-muted/40"
    : source === "DEFAULT_LIBRARY"
      ? "border-blue-300/40 bg-blue-50/40 dark:bg-blue-950/20"
      : source === "OVERRIDE"
        ? "border-orange-300/40 bg-orange-50/40 dark:bg-orange-950/20"
        : isRequiredEmpty
          ? "border-warning/40 bg-warning-soft/40"
          : isFilled
            ? "border-success/40 bg-success-soft/40"
            : "border-border bg-background";

  const helperText = [
    field.description,
    field.min !== undefined && field.max !== undefined
      ? `Range: ${field.min}–${field.max}${field.unit ? ` ${field.unit}` : ""}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const sourceBadge = SOURCE_BADGE[source];
  const showUnitSelector = engineInfo?.allowedUnits && engineInfo.allowedUnits.length > 1 && field.type === "number";

  return (
    <div className={`rounded-lg border p-2.5 space-y-1.5 ${shellClass}`}>
      <div className="flex items-center justify-between gap-2">
        <Label className={`text-xs font-medium leading-tight ${isDerived ? "text-muted-foreground italic" : "text-foreground/90"}`}>
          {field.name}
        </Label>
        <div className="flex items-center gap-1">
          {sourceBadge?.label && (
            <Badge variant="outline" className={`h-4 text-[9px] px-1.5 ${sourceBadge.className}`}>
              {sourceBadge.label}
            </Badge>
          )}
          {field.required && !sourceBadge?.label && (
            <Badge variant="outline" className="h-4 text-[9px] px-1.5 border-warning text-warning">
              Required
            </Badge>
          )}
          {isDerived && engineInfo?.onToggleOverride && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0 text-muted-foreground hover:text-foreground"
              onClick={engineInfo.onToggleOverride}
              title="Override derived value"
            >
              <Unlock className="h-3 w-3" />
            </Button>
          )}
          {engineInfo?.isOverridden && engineInfo?.onToggleOverride && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0 text-orange-500 hover:text-orange-700"
              onClick={engineInfo.onToggleOverride}
              title="Revert to derived value"
            >
              <Lock className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>

      {field.type === "select" && field.values ? (
        <Select value={value} onValueChange={onChange}>
          <SelectTrigger className={`${baseFieldClass} bg-background`}>
            <SelectValue placeholder="Select one option" />
          </SelectTrigger>
          <SelectContent>
            {field.values.map((option) => (
              <SelectItem key={option} value={option} className="text-xs">
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : field.type === "number" ? (
        <div className="relative flex gap-1.5">
          <Input
            type="number"
            value={isDerived ? (engineInfo?.displayValue ?? value) : value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.min !== undefined && field.max !== undefined ? `${field.min} – ${field.max}` : "Enter numeric value"}
            min={field.min}
            max={field.max}
            step="any"
            disabled={isDerived || disabled}
            className={`${baseFieldClass} bg-background flex-1 ${(isDerived || disabled) ? "italic text-muted-foreground cursor-not-allowed" : ""} ${showUnitSelector ? "pr-2" : "pr-16"}`}
          />
          {showUnitSelector ? (
            <Select value={engineInfo?.selectedUnit ?? field.unit ?? ""} onValueChange={(u) => engineInfo?.onUnitChange?.(u)}>
              <SelectTrigger className="h-10 w-[90px] text-[10px] font-mono bg-muted/60 border-muted-foreground/20 shrink-0">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {engineInfo!.allowedUnits!.map((u) => (
                  <SelectItem key={u} value={u} className="text-[10px] font-mono">{u}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : field.unit ? (
            <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-mono text-muted-foreground rounded bg-muted px-1.5 py-0.5">
              {field.unit}
            </span>
          ) : null}
        </div>
      ) : field.type === "date" ? (
        <Input
          type="date"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`${baseFieldClass} bg-background`}
        />
      ) : field.type === "multiselect" ? (
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter multiple values, comma-separated"
          className="min-h-[70px] text-xs bg-background"
        />
      ) : (
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter value"
          className={`${baseFieldClass} bg-background`}
        />
      )}

      {helperText && <p className="text-[10px] text-muted-foreground leading-tight">{helperText}</p>}
    </div>
  );
};

export default FormFieldControl;