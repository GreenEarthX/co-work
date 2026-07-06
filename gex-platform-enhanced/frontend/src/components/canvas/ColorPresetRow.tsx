import { useEffect, useState, useSyncExternalStore } from "react";
import { Plus, X, RotateCcw } from "lucide-react";
import {
  getColorPresets,
  subscribeColorPresets,
  addColorPreset,
  removeColorPreset,
  resetColorPresets,
} from "@/lib/colorPresets";

interface ColorPresetRowProps {
  /** Currently displayed color (used as default when adding) */
  currentColor: string;
  /** Called when user clicks a preset swatch */
  onPick: (color: string) => void;
}

/**
 * A configurable horizontal row of color swatches users can pick from in one click.
 * Edit mode reveals an X on each swatch and a + tile to add the current color.
 */
export function ColorPresetRow({ currentColor, onPick }: ColorPresetRowProps) {
  const presets = useSyncExternalStore(subscribeColorPresets, getColorPresets, getColorPresets);
  const [editing, setEditing] = useState(false);

  // Exit edit mode when popover closes (component unmounts)
  useEffect(() => () => setEditing(false), []);

  return (
    <div className="space-y-1.5 pt-2 border-t border-border">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
          Brand Presets
        </span>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            className="text-[10px] text-muted-foreground hover:text-foreground px-1.5 py-0.5 rounded hover:bg-accent"
          >
            {editing ? "Done" : "Edit"}
          </button>
          {editing && (
            <button
              type="button"
              onClick={() => resetColorPresets()}
              title="Reset to defaults"
              className="text-muted-foreground hover:text-foreground p-1 rounded hover:bg-accent"
            >
              <RotateCcw className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 max-w-[220px]">
        {presets.map((c, i) => (
          <div key={`${c}-${i}`} className="relative group">
            <button
              type="button"
              onClick={() => !editing && onPick(c)}
              aria-label={`Use color ${c}`}
              title={c}
              className="h-5 w-5 rounded border border-border hover:scale-110 transition-transform shadow-sm"
              style={{ backgroundColor: c }}
            />
            {editing && (
              <button
                type="button"
                onClick={() => removeColorPreset(i)}
                aria-label={`Remove preset ${c}`}
                className="absolute -top-1 -right-1 h-3.5 w-3.5 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center shadow"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            )}
          </div>
        ))}
        {editing && (
          <button
            type="button"
            onClick={() => addColorPreset(currentColor)}
            title={`Add ${currentColor}`}
            className="h-5 w-5 rounded border border-dashed border-border text-muted-foreground hover:text-foreground hover:border-foreground flex items-center justify-center"
          >
            <Plus className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}
