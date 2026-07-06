/**
 * EquationsTab — per-equipment equation configurator.
 *
 * The user picks a formula from the equation library, then for each input
 * variable in that formula configures a cascading source binding:
 *   1. Source dictionary  (Equipment / Carrier / Gate / Flow / Plant Form / Default Library)
 *   2. ID                  (only for Equipment, Carrier, Gate, Flow)
 *   3. Field               (the field whose value will be captured)
 *
 * The tab evaluates the equation live and shows the computed result.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { Node, Edge } from "@xyflow/react";
import { Plus, Trash2, Calculator, AlertCircle, Sigma, Save, ArrowDown, Loader2, PackageOpen } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import {
  loadEquationLibrary,
  flattenEquations,
  parseInputParams,
  type EquationDef,
} from "@/lib/equations/equationLibrary";
import { getComponentIdForLabel } from "@/lib/equations/labelToComponentId";
import {
  SOURCE_OPTIONS,
  listIdsForSource,
  listFieldsForSource,
  resolveBinding,
  evaluateExpression,
  type SourceKind,
  type VariableBinding,
  type ResolverContext,
} from "@/lib/equations/sourceResolver";
import { useEquipmentEquations } from "@/hooks/useEquipmentEquations";
import EquationMiniMap from "./EquationMiniMap";
import { toast } from "@/hooks/use-toast";
import type { FieldDef } from "./fieldDictionary";

interface Props {
  plantSlug: string;
  nodeId: string;
  equipmentLabel: string;
  nodes: Node[];
  edges: Edge[];
  plantForm?: Record<string, unknown>;
  plantFieldDefs?: FieldDef[];
}

const EquationsTab = ({
  plantSlug,
  nodeId,
  equipmentLabel,
  nodes,
  edges,
  plantForm = {},
  plantFieldDefs = [],
}: Props) => {
  const [library, setLibrary] = useState<Awaited<ReturnType<typeof loadEquationLibrary>>>([]);
  // Tracks the lifecycle of the equation library fetch so the picker can
  // distinguish between "still loading" and "loaded but empty for this
  // equipment". Starts in `loading` so the very first render doesn't flash a
  // misleading empty state.
  const [libraryStatus, setLibraryStatus] = useState<"loading" | "ready" | "error">("loading");
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const { items, upsert, remove } = useEquipmentEquations(plantSlug, nodeId, equipmentLabel);

  // Editor state for the currently-being-edited equation
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draftEquationId, setDraftEquationId] = useState<string>("");
  const [draftBindings, setDraftBindings] = useState<Record<string, VariableBinding>>({});
  const editorRef = useRef<HTMLDivElement | null>(null);
  // Refs for the two key entry points we want to highlight when the editor
  // opens, so the user immediately knows where to act.
  const formulaPickerRef = useRef<HTMLButtonElement | null>(null);
  const formulaHeaderRef = useRef<HTMLDivElement | null>(null);
  const [pulseTarget, setPulseTarget] = useState<"picker" | "header" | null>(null);
  // Tracks whether the editor is currently visible in the scroll viewport.
  // When false (and the editor is open), we show the sticky "Jump to editor"
  // header so the user can return with one click.
  const [editorVisible, setEditorVisible] = useState(true);

  // Captured scroll position of the dialog's scroll container at the moment
  // the editor was opened. Restored when the user closes via Escape/Cancel
  // so they land back where they were instead of at the top of the tab.
  const savedScrollRef = useRef<{ el: Element; top: number } | null>(null);

  // Persist & recall the last-edited equation per equipment node so that
  // reopening the dialog drops the user back at the formula they were last
  // working on. Stored in localStorage to survive across sessions without
  // touching the equations table schema.
  const lastEditedKey = `gex_last_edited_eq:${nodeId}`;
  const [highlightEquationId, setHighlightEquationId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const didAutoScrollRef = useRef(false);

  const rememberLastEdited = (equationId: string) => {
    try {
      localStorage.setItem(lastEditedKey, equationId);
    } catch {
      /* ignore quota */
    }
  };

  // After items have loaded for this node, scroll to the last-edited card.
  useEffect(() => {
    if (didAutoScrollRef.current) return;
    if (items.length === 0) return;
    let lastId: string | null = null;
    try {
      lastId = localStorage.getItem(lastEditedKey);
    } catch {
      lastId = null;
    }
    if (!lastId) return;
    const exists = items.some((it) => it.equation_id === lastId);
    if (!exists) return;
    didAutoScrollRef.current = true;
    // Wait one frame so the DOM nodes for the cards exist.
    requestAnimationFrame(() => {
      const el = containerRef.current?.querySelector<HTMLElement>(
        `[data-equation-id="${CSS.escape(lastId!)}"]`,
      );
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        setHighlightEquationId(lastId);
        window.setTimeout(() => setHighlightEquationId(null), 2400);
      }
    });
  }, [items, lastEditedKey]);

  useEffect(() => {
    if (!pickerOpen || !editorRef.current) {
      setEditorVisible(true);
      return;
    }
    const el = editorRef.current;
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry) setEditorVisible(entry.isIntersecting);
      },
      { threshold: 0.05 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [pickerOpen]);

  const jumpToEditor = () => {
    editorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  /** Walk up the DOM to find the nearest vertically-scrollable ancestor. */
  const findScrollParent = (el: HTMLElement | null): Element | null => {
    let cur: HTMLElement | null = el?.parentElement ?? null;
    while (cur && cur !== document.body) {
      const style = getComputedStyle(cur);
      const oy = style.overflowY;
      if ((oy === "auto" || oy === "scroll") && cur.scrollHeight > cur.clientHeight) {
        return cur;
      }
      cur = cur.parentElement;
    }
    return document.scrollingElement || document.documentElement;
  };

  /** Capture scroll position the moment the editor opens. */
  useEffect(() => {
    if (!pickerOpen) return;
    const scrollEl = findScrollParent(containerRef.current);
    if (scrollEl) {
      savedScrollRef.current = { el: scrollEl, top: scrollEl.scrollTop };
    }
  }, [pickerOpen]);

  /** Close the editor and restore the scroll position saved on open. */
  const closeEditor = () => {
    setPickerOpen(false);
    setDraftEquationId("");
    setDraftBindings({});
    const saved = savedScrollRef.current;
    if (saved) {
      // Wait for the editor unmount/layout to settle before restoring.
      requestAnimationFrame(() => {
        try {
          (saved.el as HTMLElement).scrollTo({ top: saved.top, behavior: "smooth" });
        } catch {
          (saved.el as HTMLElement).scrollTop = saved.top;
        }
        savedScrollRef.current = null;
      });
    }
  };

  /** Escape closes the editor and returns to the previous scroll position. */
  useEffect(() => {
    if (!pickerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Don't fight Radix popovers / select dropdowns — let them close first.
      const openOverlay = document.querySelector(
        '[data-state="open"][role="listbox"], [data-state="open"][role="dialog"][data-radix-popper-content-wrapper]',
      );
      if (openOverlay) return;
      e.preventDefault();
      e.stopPropagation();
      closeEditor();
    };
    // Use capture so we run before the parent Dialog's own Escape handler.
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
    // closeEditor is stable enough — uses refs + setters
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickerOpen]);

  // Scroll the editor into view whenever it opens, so users aren't left
  // staring at the bottom of the module wondering where the form went.
  useEffect(() => {
    if (!pickerOpen) return;
    const t = window.setTimeout(() => {
      editorRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 60);
    return () => window.clearTimeout(t);
  }, [pickerOpen, draftEquationId]);

  useEffect(() => {
    let cancelled = false;
    setLibraryStatus("loading");
    setLibraryError(null);
    loadEquationLibrary()
      .then((lib) => {
        if (cancelled) return;
        setLibrary(lib);
        setLibraryStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setLibrary([]);
        setLibraryError(err instanceof Error ? err.message : "Unable to load equation library");
        setLibraryStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const allEquations = useMemo(() => flattenEquations(library), [library]);

  // Filter to ONLY this equipment's equations, based on its label → component_id mapping.
  const componentId = useMemo(() => getComponentIdForLabel(equipmentLabel), [equipmentLabel]);
  const equipmentEquations = useMemo(
    () => (componentId ? allEquations.filter((e) => e.component_id === componentId) : []),
    [allEquations, componentId],
  );

  // Per-instance filtering: an equation already saved for THIS specific
  // equipment node (nodeId) is hidden from the "add new" picker so the user
  // doesn't accidentally bind the same formula twice on the same instance.
  // Two equipment with the same label still get independent sets because
  // `items` is scoped by nodeId via useEquipmentEquations.
  const usedEquationIds = useMemo(
    () => new Set(items.map((it) => it.equation_id)),
    [items],
  );
  const availableEquations = useMemo(
    () =>
      equipmentEquations.filter((eq) => {
        // Always keep the one currently being edited so the picker can show
        // its own selection.
        if (eq.id === draftEquationId) return true;
        return !usedEquationIds.has(eq.id);
      }),
    [equipmentEquations, usedEquationIds, draftEquationId],
  );

  const ctx: ResolverContext = useMemo(
    () => ({ nodes, edges, plantForm, plantFieldDefs }),
    [nodes, edges, plantForm, plantFieldDefs],
  );

  const draftEquation = equipmentEquations.find((e) => e.id === draftEquationId) ?? null;

  const startNew = () => {
    setDraftEquationId("");
    setDraftBindings({});
    setPickerOpen(true);
  };

  const onPickEquation = (equationId: string) => {
    setDraftEquationId(equationId);
    const eq = equipmentEquations.find((e) => e.id === equationId);
    if (!eq) return;
    const params = parseInputParams(eq.input_params);
    const initial: Record<string, VariableBinding> = {};
    for (const p of params) initial[p] = { source: "" };
    setDraftBindings(initial);
  };

  /** Pulse-highlight whichever entry field is now relevant. */
  useEffect(() => {
    if (!pickerOpen) {
      setPulseTarget(null);
      return;
    }
    // No equation chosen yet → draw attention to the formula picker so the
    // user knows where to start.
    if (!draftEquationId) {
      setPulseTarget("picker");
      // Delay focus until the editor has scrolled into view.
      const tFocus = window.setTimeout(() => {
        formulaPickerRef.current?.focus({ preventScroll: true });
      }, 320);
      const tStop = window.setTimeout(() => setPulseTarget(null), 1800);
      return () => {
        window.clearTimeout(tFocus);
        window.clearTimeout(tStop);
      };
    }
    // Equation loaded → highlight the formula header so the user can verify
    // they're editing the right thing.
    setPulseTarget("header");
    const t = window.setTimeout(() => setPulseTarget(null), 1800);
    return () => window.clearTimeout(t);
  }, [pickerOpen, draftEquationId]);

  const updateBinding = (paramKey: string, patch: Partial<VariableBinding>) => {
    setDraftBindings((prev) => ({
      ...prev,
      [paramKey]: { ...prev[paramKey], ...patch },
    }));
  };

  const handleSaveDraft = async () => {
    if (!draftEquation) return;
    const { error } = await upsert({
      equation_id: draftEquation.id,
      equation_expression: draftEquation.expression,
      output_param: draftEquation.output_param,
      variable_bindings: draftBindings,
    });
    if (error) {
      toast({ title: "Save failed", description: error.message, variant: "destructive" });
      return;
    }
    toast({ title: "Equation saved", description: draftEquation.id });
    rememberLastEdited(draftEquation.id);
    closeEditor();
  };

  return (
    <div ref={containerRef} className="space-y-5 relative">
      {/* Sticky "jump to editor" header, only shown when the editor is open
          but currently scrolled out of view. Sits at the top of this tab so it
          stays visible while users browse saved equations above. */}
      {pickerOpen && !editorVisible && (
        <div className="sticky top-0 z-30 -mx-4 px-4 py-2 bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80 border-b border-primary/30 shadow-sm flex items-center justify-between gap-2 animate-in fade-in slide-in-from-top-1">
          <div className="flex items-center gap-2 min-w-0">
            <span className="h-6 w-6 rounded-md bg-primary/15 text-primary flex items-center justify-center shrink-0">
              <Sigma className="h-3 w-3" />
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-foreground truncate">
                Equation editor open
              </p>
              <p className="text-[10px] text-muted-foreground truncate">
                {draftEquation
                  ? `Editing ${draftEquation.id}`
                  : "Pick a formula to start configuring"}
              </p>
            </div>
          </div>
          <Button
            size="sm"
            className="h-7 text-[11px] gap-1.5 shrink-0"
            onClick={jumpToEditor}
          >
            <ArrowDown className="h-3 w-3" />
            Jump to editor
          </Button>
        </div>
      )}

      {/* Header, contextual subline + primary CTA */}
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-muted-foreground">
          {libraryStatus === "loading" ? (
            <span className="inline-flex items-center gap-1.5">
              <Loader2 className="h-3 w-3 animate-spin" />
              Loading equation library…
            </span>
          ) : libraryStatus === "error" ? (
            <span className="inline-flex items-center gap-1.5 text-destructive">
              <AlertCircle className="h-3 w-3" />
              Failed to load library, {libraryError}
            </span>
          ) : componentId
            ? `${equipmentEquations.length} equation${equipmentEquations.length === 1 ? "" : "s"} available for ${equipmentLabel}`
            : `No equation set is mapped to ${equipmentLabel || "this equipment"} yet.`}
        </p>
        <Button
          size="sm"
          className="h-7 text-[11px] gap-1.5"
          onClick={startNew}
          disabled={libraryStatus === "loading"}
          title={
            libraryStatus === "loading"
              ? "Library still loading…"
              : equipmentEquations.length === 0
                ? "Open the editor to see why no equations are available"
                : "Add a new equation"
          }
        >
          {libraryStatus === "loading" ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Plus className="h-3 w-3" />
          )}
          Add equation
        </Button>
      </div>

      {/* Saved equations */}
      {items.length === 0 && !pickerOpen && (
        <div className="rounded-lg border border-dashed border-border bg-muted/30 p-4 text-center">
          <Calculator className="h-6 w-6 text-muted-foreground/60 mx-auto mb-1.5" />
          <p className="text-[11px] text-muted-foreground">
            No equations configured for this equipment yet.
          </p>
        </div>
      )}

      {items.map((it) => {
        const def = allEquations.find((e) => e.id === it.equation_id);
        return (
          <SavedEquationCard
            key={it.id}
            ctx={ctx}
            stored={it}
            def={def}
            isHighlighted={highlightEquationId === it.equation_id}
            onDelete={() => void remove(it.id)}
            onEdit={() => {
              setDraftEquationId(it.equation_id);
              setDraftBindings(it.variable_bindings);
              setPickerOpen(true);
              rememberLastEdited(it.equation_id);
            }}
          />
        );
      })}

      {/* Editor */}
      {pickerOpen && (
        <div
          ref={editorRef}
          className="rounded-lg border border-primary/30 bg-card p-4 space-y-4 scroll-mt-4"
        >
          <div className="flex items-center justify-between">
            <Label className="text-xs font-semibold">Formula</Label>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[10px]"
              onClick={closeEditor}
              title="Close editor (Esc)"
            >
              Cancel
            </Button>
          </div>

          <Select value={draftEquationId} onValueChange={onPickEquation}>
            <SelectTrigger
              ref={formulaPickerRef}
              className={`h-9 text-xs transition-shadow ${
                pulseTarget === "picker"
                  ? "ring-2 ring-primary/60 ring-offset-1 ring-offset-background animate-pulse"
                  : ""
              }`}
              disabled={libraryStatus !== "ready" || equipmentEquations.length === 0}
            >
              <SelectValue
                placeholder={
                  libraryStatus === "loading"
                    ? "Loading equation library…"
                    : libraryStatus === "error"
                      ? "Library failed to load, see message below"
                      : equipmentEquations.length === 0
                        ? "No formulas available for this equipment"
                        : "Select a formula from the library…"
                }
              />
            </SelectTrigger>
            <SelectContent className="max-h-80">
              {libraryStatus === "loading" && (
                <div className="px-3 py-6 flex flex-col items-center gap-2 text-[11px] text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  <span>Loading equation library…</span>
                </div>
              )}
              {libraryStatus === "error" && (
                <div className="px-3 py-4 flex flex-col items-center gap-1.5 text-[11px] text-destructive text-center">
                  <AlertCircle className="h-4 w-4" />
                  <span className="font-medium">Library failed to load</span>
                  <span className="text-muted-foreground">{libraryError}</span>
                </div>
              )}
              {libraryStatus === "ready" && equipmentEquations.length === 0 && (
                <div className="px-3 py-4 flex flex-col items-center gap-1.5 text-[11px] text-muted-foreground text-center">
                  <PackageOpen className="h-4 w-4 opacity-60" />
                  <span className="font-medium text-foreground">No equations available</span>
                  <span>
                    The library has no formulas mapped to{" "}
                    <span className="font-mono">{equipmentLabel || "this equipment"}</span>.
                  </span>
                </div>
              )}
              {libraryStatus === "ready" &&
                equipmentEquations.length > 0 &&
                availableEquations.length === 0 && (
                  <div className="px-3 py-4 flex flex-col items-center gap-1.5 text-[11px] text-muted-foreground text-center">
                    <PackageOpen className="h-4 w-4 opacity-60" />
                    <span className="font-medium text-foreground">All equations already added</span>
                    <span>
                      Every formula mapped to this instance ({usedEquationIds.size}) is
                      already bound. Remove one below to add a different equation.
                    </span>
                  </div>
                )}
              {libraryStatus === "ready" && availableEquations.map((eq) => (
                <SelectItem key={eq.id} value={eq.id} className="text-xs">
                  <span className="font-mono mr-2 text-muted-foreground">{eq.id}</span>
                  <span className="whitespace-normal break-words">{eq.expression}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Inline explanation shown directly below the picker when the
              library is still loading, errored, or returned no formulas for
              this equipment, so the user understands the picker state
              without having to open the dropdown. */}
          {libraryStatus === "loading" && (
            <div className="rounded-md border border-border bg-muted/30 px-3 py-2 flex items-center gap-2 text-[11px] text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />
              Fetching equation library…
            </div>
          )}
          {libraryStatus === "error" && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 flex items-start gap-2 text-[11px]">
              <AlertCircle className="h-3.5 w-3.5 text-destructive shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <p className="font-medium text-destructive">Library failed to load</p>
                <p className="text-muted-foreground">{libraryError}</p>
              </div>
            </div>
          )}
          {libraryStatus === "ready" && equipmentEquations.length === 0 && (
            <div className="rounded-md border border-warning/40 bg-warning-soft/40 px-3 py-2 flex items-start gap-2 text-[11px]">
              <PackageOpen className="h-3.5 w-3.5 text-warning shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <p className="font-medium text-foreground">No formulas mapped to this equipment</p>
                <p className="text-muted-foreground">
                  The library loaded successfully but has no equations for{" "}
                  <span className="font-mono">{equipmentLabel || "this equipment"}</span>.
                  Try editing this on a different component, or extend the library.
                </p>
              </div>
            </div>
          )}

          {draftEquation && (
            <>
              {/* Prominent formula header, sticky-style banner */}
              <div
                ref={formulaHeaderRef}
                className={`rounded-lg border bg-primary/5 px-4 py-3 space-y-1.5 transition-all duration-300 ${
                  pulseTarget === "header"
                    ? "border-primary ring-2 ring-primary/40 shadow-md"
                    : "border-primary/30"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Sigma className="h-3.5 w-3.5 text-primary" />
                  <span className="text-[10px] uppercase tracking-wider text-primary font-semibold">
                    Formula · {draftEquation.id}
                  </span>
                </div>
                <p className="text-sm font-mono font-semibold text-foreground break-words">
                  {draftEquation.expression}
                </p>
                <p className="text-[11px] text-muted-foreground italic">{draftEquation.description}</p>
              </div>

              <div className="space-y-3">
                <Label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Variable bindings
                </Label>
                {parseInputParams(draftEquation.input_params).map((param) => (
                  <BindingRow
                    key={param}
                    paramName={param}
                    binding={draftBindings[param] ?? { source: "" }}
                    ctx={ctx}
                    onChange={(patch) => updateBinding(param, patch)}
                    pinScope={`${nodeId}:${draftEquation.id}:${param}`}
                  />
                ))}
              </div>

              <LivePreview equation={draftEquation} bindings={draftBindings} ctx={ctx} />

              <div className="flex justify-end gap-2 pt-1">
                <Button size="sm" className="h-8 text-[11px] gap-1.5" onClick={() => void handleSaveDraft()}>
                  <Save className="h-3 w-3" /> Save equation
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

/* ─────────────── Binding row (3 cascading selects) ─────────────── */

function BindingRow({
  paramName,
  binding,
  ctx,
  onChange,
  pinScope: _pinScope,
}: {
  paramName: string;
  binding: VariableBinding;
  ctx: ResolverContext;
  onChange: (patch: Partial<VariableBinding>) => void;
  /** Stable identifier used to persist the pinned ID across tab switches /
   *  page refreshes. Format suggestion: `${nodeId}:${equationId}:${param}`. */
  pinScope: string;
}) {
  const ids = binding.source ? listIdsForSource(ctx, binding.source as SourceKind) : [];
  const fields = binding.source
    ? listFieldsForSource(ctx, binding.source as SourceKind, binding.refId)
    : [];
  const sourceCfg = SOURCE_OPTIONS.find((s) => s.value === binding.source);
  const needsId = sourceCfg?.needsId ?? false;
  const isFlow = binding.source === "flow";
  const isNodeKind =
    binding.source === "equipment" ||
    binding.source === "carrier" ||
    binding.source === "gate";

  const resolved = resolveBinding(ctx, binding);
  const fieldMeta = fields.find((f) => f.key === binding.field);
  const fieldUnit = fieldMeta?.unit;

  return (
    <div className="rounded-md border border-border bg-background p-2.5 space-y-2">
      {/* Variable header, name + live resolved value */}
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-sm font-semibold text-primary">{paramName}</span>
        <div className="flex items-center gap-1.5 text-[11px] font-mono">
          <span className="text-muted-foreground">=</span>
          {resolved.status === "ok" && resolved.value !== null && (
            <span className="px-2 py-0.5 rounded-md bg-success-soft text-success font-semibold">
              {Number(resolved.value.toPrecision(6))}
              {fieldUnit && <span className="text-muted-foreground ml-1 font-normal">{fieldUnit}</span>}
            </span>
          )}
          {resolved.status === "missing" && (
            <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground italic">
              {binding.source ? "no value" : "unbound"}
            </span>
          )}
          {resolved.status === "non_numeric" && (
            <span className="px-2 py-0.5 rounded-md bg-destructive/10 text-destructive">
              non-numeric
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {/* Source dictionary */}
        <div>
          <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">Source</Label>
          <Select
            value={binding.source}
            onValueChange={(v) =>
              onChange({ source: v as SourceKind, refId: undefined, field: undefined })
            }
          >
            <SelectTrigger className="h-8 text-[11px] mt-0.5">
              <SelectValue placeholder="Source…" />
            </SelectTrigger>
            <SelectContent>
              {SOURCE_OPTIONS.map((s) => (
                <SelectItem key={s.value} value={s.value} className="text-[11px]">
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* ID (cascading, only for sources that require it) */}
        <div>
          <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">
            {needsId ? "ID" : "–"}
          </Label>
          <Select
            value={binding.refId ?? ""}
            onValueChange={(v) => onChange({ refId: v, field: undefined })}
            disabled={!needsId}
          >
            <SelectTrigger className="h-8 text-[11px] mt-0.5">
              <SelectValue placeholder={needsId ? "Select ID…" : "Not required"} />
            </SelectTrigger>
            <SelectContent className="max-h-96 w-[320px]">
              {needsId && (
                <div className="sticky top-0 z-10 bg-popover border-b border-border p-2">
                  <p className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1">
                    Canvas preview
                  </p>
                  <EquationMiniMap
                    nodes={ctx.nodes}
                    edges={ctx.edges}
                    highlightNodeId={isNodeKind ? binding.refId ?? undefined : undefined}
                    highlightEdgeId={isFlow ? binding.refId ?? undefined : undefined}
                    width="100%"
                  />
                </div>
              )}
              {ids.length === 0 && (
                <div className="px-2 py-1.5 text-[10px] text-muted-foreground">No items</div>
              )}
              {ids.map((it) => {
                // Detect duplicate labels among siblings so we can highlight the
                // disambiguating identifier (e.g. two "Deoxidation Unit" nodes).
                const isDuplicate =
                  ids.filter((o) => o.label === it.label).length > 1;
                return (
                <SelectItem
                  key={it.id}
                  value={it.id}
                  className="text-[11px]"
                >
                  <span
                    className={
                      "font-mono mr-1.5 " +
                      (isDuplicate
                        ? "text-primary font-semibold"
                        : "text-muted-foreground")
                    }
                    title={it.id}
                  >
                    {it.id}
                  </span>
                  {it.label}
                </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>

        {/* Field */}
        <div>
          <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">Field</Label>
          <Select
            value={binding.field ?? ""}
            onValueChange={(v) => onChange({ field: v })}
            disabled={!binding.source || (needsId && !binding.refId)}
          >
            <SelectTrigger className="h-8 text-[11px] mt-0.5">
              <SelectValue placeholder="Field…" />
            </SelectTrigger>
            <SelectContent className="max-h-72">
              {fields.length === 0 && (
                <div className="px-2 py-1.5 text-[10px] text-muted-foreground">No fields</div>
              )}
              {fields.map((f) => (
                <SelectItem key={f.key} value={f.key} className="text-[11px]">
                  {f.label}
                  {f.unit ? <span className="text-muted-foreground ml-1.5">({f.unit})</span> : null}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}

/* ─────────────── Live preview ─────────────── */

function LivePreview({
  equation,
  bindings,
  ctx,
}: {
  equation: EquationDef;
  bindings: Record<string, VariableBinding>;
  ctx: ResolverContext;
}) {
  const values: Record<string, number | null> = {};
  for (const [k, b] of Object.entries(bindings)) {
    values[k] = resolveBinding(ctx, b).value;
  }
  const result = evaluateExpression(equation.expression, values);

  return (
    <div className="rounded-md border border-border bg-muted/30 p-2.5 space-y-1">
      <p className="text-[9px] uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
        <Calculator className="h-2.5 w-2.5" />
        Live computation
      </p>
      <p className="text-xs font-mono">
        <span className="text-primary">{equation.output_param}</span>
        <span className="text-muted-foreground"> = </span>
        {result.value !== null ? (
          <span className="font-semibold">{Number(result.value.toPrecision(6))}</span>
        ) : (
          <span className="text-warning inline-flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            {result.error ?? "unresolved"}
          </span>
        )}
      </p>
    </div>
  );
}

/* ─────────────── Saved equation summary card ─────────────── */

function SavedEquationCard({
  ctx,
  stored,
  def,
  onEdit,
  onDelete,
  isHighlighted = false,
}: {
  ctx: ResolverContext;
  stored: { id: string; equation_id: string; equation_expression: string; output_param: string; variable_bindings: Record<string, VariableBinding> };
  def: (EquationDef & { component_id: string }) | undefined;
  onEdit: () => void;
  onDelete: () => void;
  isHighlighted?: boolean;
}) {
  const values: Record<string, number | null> = {};
  for (const [k, b] of Object.entries(stored.variable_bindings)) {
    values[k] = resolveBinding(ctx, b).value;
  }
  const result = evaluateExpression(stored.equation_expression, values);

  return (
    <div
      data-equation-id={stored.equation_id}
      className={`rounded-lg border bg-card p-3 space-y-2 transition-all duration-500 ${
        isHighlighted
          ? "border-primary ring-2 ring-primary/40 shadow-md scroll-mt-4"
          : "border-border"
      }`}
    >
      {isHighlighted && (
        <div className="flex items-center gap-1.5 text-[10px] text-primary font-medium">
          <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
          Last edited, jumped here
        </div>
      )}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="h-4 text-[9px] px-1.5 font-mono">
              {stored.equation_id}
            </Badge>
            {def && <span className="text-[10px] text-muted-foreground">{def.component_id}</span>}
          </div>
          <p className="text-xs font-mono mt-1">{stored.equation_expression}</p>
          {def && <p className="text-[10px] text-muted-foreground mt-0.5 italic">{def.description}</p>}
        </div>
        <div className="flex gap-1 shrink-0">
          <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={onEdit}>Edit</Button>
          <Button variant="ghost" size="sm" className="h-6 text-[10px] text-destructive" onClick={onDelete}>
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </div>

      <div className="rounded bg-muted/40 px-2 py-1.5 flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">Computed</span>
        <span className="text-xs font-mono font-semibold">
          {result.value !== null
            ? `${stored.output_param} = ${Number(result.value.toPrecision(6))}`
            : <span className="text-warning">{result.error ?? "unresolved"}</span>}
        </span>
      </div>
    </div>
  );
}

export default EquationsTab;