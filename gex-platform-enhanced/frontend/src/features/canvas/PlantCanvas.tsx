/**
 * PlantCanvas — Node-based plant design editor (React Flow).
 * @route /project/:projectId/canvas
 */
import { useState, useCallback, useRef, useMemo, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  ConnectionLineType,
  ConnectionMode,
  MarkerType,
  addEdge,
  reconnectEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type NodePositionChange,
  ReactFlowProvider,
  ViewportPortal,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Play, CheckCircle2, Cpu, Zap, ArrowRightFromLine, ChevronRight, AlertTriangle, Settings2, Download, X, Undo2, DollarSign, Gauge, Settings, Merge, Split, Loader2, Cloud, BarChart3, GitBranch, Plus, Check, Pencil, Trash2 } from "lucide-react";
import { useCanvasHistory } from "@/hooks/useCanvasHistory";
import { useCanvasData } from "@/hooks/useCanvasData";
import { useCanvasToolbarPrefs } from "@/hooks/useCanvasToolbarPrefs";
import { useLabelNormalizationPrefs } from "@/hooks/useLabelNormalizationPrefs";
import { useCanvasPresence, colorForUser } from "@/hooks/useCanvasPresence";
import { useCanvasLiveSync } from "@/hooks/useCanvasLiveSync";
import { PresenceCursors } from "@/components/canvas/PresenceCursors";
import { PresenceAvatars } from "@/components/canvas/PresenceAvatars";
import { useAuth } from "@/contexts/AuthContext";
import VersionHistoryDialog from "@/components/canvas/VersionHistoryDialog";
import { NodeIdVisibilityProvider, NodeIdDebugProvider, LabelNormalizationProvider, CompactNodeProvider, StraightEdgesProvider } from "@/components/canvas/nodeIdVisibility";
import { computeSnap, nodeDimsByType, type AlignmentGuide, type NodeRect } from "@/components/canvas/alignmentGuides";
import ZoomLegibilityBridge from "@/components/canvas/ZoomLegibilityBridge";
import SaveConfirmDialog from "@/components/canvas/SaveConfirmDialog";
import AppNav from "@/components/AppNav";
import { toast } from "sonner";
import UserContextBar from "@/components/UserContextBar";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";
import { getProjectOrDefault } from "@/lib/projectRegistry";
import { useSyncedPlants } from "@/lib/plantStore";
import { createIteration, renamePlantVariation, deletePlantVariation } from "@/lib/iterations";
import { nextIterationLabel, getCollectionDisplayName } from "@/lib/projectRegistry";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useProjectAccess } from "@/lib/projectAccess";
import AccessRestricted from "@/components/auth/AccessRestricted";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import ComponentLibrary from "@/components/canvas/ComponentLibrary";
import CarrierNode from "@/components/canvas/CarrierNode";
import GateNode from "@/components/canvas/GateNode";
import EquipmentNode from "@/components/canvas/EquipmentNode";
import BoundaryNode from "@/components/canvas/BoundaryNode";
import ComponentDetailDialog from "@/components/canvas/ComponentDetailDialog";
import { logComponentEvent } from "@/components/canvas/OwnershipRolesPanel";
import ProcurementWarningDialog from "@/components/canvas/ProcurementWarningDialog";
import { matchProcurement, getProcurementEntry, type ProcurementStrategy } from "@/components/canvas/procurementDatabase";
import { persistProcurementToPlant } from "@/components/canvas/procurementExport";
import PlantExportDialog from "@/components/canvas/PlantExportDialog";
import FlowEdge from "@/components/canvas/FlowEdge";
import { EdgeContextMenu } from "@/components/canvas/EdgeContextMenu";
import { NodeContextMenu } from "@/components/canvas/NodeContextMenu";
import BatchFlowDialog from "@/components/canvas/BatchFlowDialog";
import {
  defaultBatchConfig,
  computeEquivalentRate,
  type BatchFlowConfig,
} from "@/components/canvas/batchFlow";
import { runFlowBalance, type BalanceReport } from "@/components/canvas/flowBalanceEngine";
import { getColorFromResource, normalizeConnection } from "@/components/canvas/portSystem";
import { subscribeCarrierOverrides } from "@/lib/carrierColorOverrides";
// import { transposeEdgeHandles } from "@/components/canvas/autoLayout";
import { CheckFindingsPanel } from "@/components/canvas/CheckFindingsPanel";
import { PlantSettingsDialog } from "@/components/canvas/PlantSettingsDialog";
import { Badge } from "@/components/ui/Badge";
import SupplierPickerDialog from "@/components/canvas/SupplierPickerDialog";
import { applyProcurementToNode } from "@/lib/procurementSync";
import { useEngineCheck } from "@/engine/hooks/useEquationEngine";

const nodeTypes = {
  carrier: CarrierNode,
  gate: GateNode,
  equipment: EquipmentNode,
  boundary: BoundaryNode,
};

const edgeTypes = {
  flowEdge: FlowEdge,
};

type CarrierLegendItem = { label: string; color: string };

type ExportSnapshot = {
  nodes: Node[];
  legendItems: CarrierLegendItem[];
  signature: string;
};

const NORTHSEA_V1_LEGEND_LABELS = [
  "Air",
  "CO₂",
  "Electricity",
  "Heat",
  "Hydrogen",
  "Methanol",
  "Oxygen",
  "Seawater",
  "Wastewater",
  "Water",
];

// plantData now comes from projectRegistry

const PlantCanvasInner = () => {
  const navigate = useNavigate();
  const { plantId } = useParams();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { fitView } = useReactFlow();
  

  const plant = getProjectOrDefault(plantId);
  // ── Live presence (Phase 1: avatars + cursors) ──
  const { user: authUser } = useAuth();
  const { data: canvasData, loadedPlantId, loading: canvasLoading, error: canvasError, saveCanvasData, saving, listVersions, restoreVersion } = useCanvasData(plantId, authUser?.id);
  const presenceMe = useMemo(
    () =>
      authUser
        ? {
            userId: authUser.id,
            name: authUser.name || authUser.email,
            email: authUser.email,
            color: colorForUser(authUser.id),
          }
        : null,
    [authUser],
  );
  const { peers: presencePeers, publishCursor } = useCanvasPresence(plantId, presenceMe);
  // ── Iterations (collection siblings) ──
  const allPlants = useSyncedPlants(authUser?.id);
  const collectionGroupId = plant.projectGroupId || plant.id;
  const iterationMembers = useMemo(
    () =>
      allPlants
        .filter((p) => (p.projectGroupId || p.id) === collectionGroupId && !p.archived)
        .sort((a, b) => a.id.localeCompare(b.id)),
    [allPlants, collectionGroupId],
  );
  const [creatingIteration, setCreatingIteration] = useState(false);
  // ── Iteration UX state: name-on-create, rename, delete ──
  const [newIterDialogOpen, setNewIterDialogOpen] = useState(false);
  const [newIterName, setNewIterName] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; label: string } | null>(null);
  const [deletingIteration, setDeletingIteration] = useState(false);
  // Live snapshot sync disabled — was causing feedback loops where applying a
  // peer snapshot dirtied local state and triggered an immediate rebroadcast,
  // spamming "X updated the plant" toasts. Presence (cursors/avatars) still
  // works. Cloud autosave keeps peers in sync on a slower cadence.
  const { lastRemote: _remoteSnapshot, broadcastSnapshot: _broadcastSnapshot } = useCanvasLiveSync(
    undefined,
    null,
  );
  const remoteSnapshot = null as typeof _remoteSnapshot;
  const broadcastSnapshot = useCallback(
    (..._args: Parameters<typeof _broadcastSnapshot>) => {},
    [],
  );

  const initialNodes = canvasData?.nodes || [];
  const initialEdges = canvasData?.edges || [];

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState(initialEdges);

  // ── Dynamic system boundary refs: declared before settings snapshots use them ──
  const lastBoundaryRef = useRef({ x: 0, y: 0, w: 0, h: 0 });
  const manualPadding = useRef({ left: 0, right: 0, top: 0, bottom: 0 });
  const isResizingBoundary = useRef(false);
  const isDraggingNodeRef = useRef(false);
  // Live ref to current nodes so the change handler can stay referentially stable
  // across renders. Re-creating onNodesChangeTracked every render forces React
  // Flow to re-bind listeners mid-drag, which is the main source of jitter.
  const nodesRef = useRef(nodes);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);
  const edgesRef = useRef(edges);
  useEffect(() => { edgesRef.current = edges; }, [edges]);
  // Cheap flag: do we have any gate node? Skips the per-change clamp loop entirely
  // when there are none.
  const hasGateNodeRef = useRef(false);
  useEffect(() => {
    hasGateNodeRef.current = nodes.some((n) => n.type === "gate");
  }, [nodes]);

  // ── rAF coalescing for in-flight drag position updates ──
  // React Flow can emit many `position` changes per frame (especially with
  // multi-select drags). We buffer them and flush at most once per animation
  // frame, keeping only the latest position per node id. Non-position changes
  // and drag-end (`dragging === false`) bypass the buffer so selection,
  // deletion, and snapshotting stay synchronous.
  const dragRafRef = useRef<number | null>(null);
  const dragBufferRef = useRef<Map<string, NodePositionChange>>(new Map());

  // When canvasData arrives (async), populate nodes/edges and plant settings
  const didInitialFit = useRef(false);
  const hydratedPlantIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!canvasData) return;
    if (canvasLoading) return;
    if (loadedPlantId !== (plantId ?? null)) return;
    // Only hydrate from cloud once per plantId. Subsequent canvasData updates
    // (e.g. echoed by autosave) must NOT stomp the live local state — that
    // causes ReactFlow to re-mount nodes/edges, which wipes selection and
    // makes streams appear to flash.
    if (hydratedPlantIdRef.current === plantId) return;
    hydratedPlantIdRef.current = plantId ?? null;
    didInitialFit.current = false;

      setNodes(canvasData.nodes);
      setEdges(canvasData.edges);
      // One-time fitView after initial data load
      if (canvasData.nodes.length > 0 && !didInitialFit.current) {
        didInitialFit.current = true;
        setTimeout(() => fitView({ padding: 0.15 }), 80);
      }
    if (canvasData.plantSettings) {
      setPlantHoursYear(canvasData.plantSettings.hoursYear);
      setPlantAvailability(canvasData.plantSettings.plantAvailability);
      setCriticalPathNodeIds(new Set(canvasData.plantSettings.criticalPathNodeIds));
      const bp = canvasData.plantSettings.boundaryPadding;
      if (bp) manualPadding.current = { ...bp };
    }
  }, [canvasData, loadedPlantId, canvasLoading, plantId, setNodes, setEdges, fitView]);

  /** Track whether a delete key was pressed — only then allow edge removal */
  const userDeleteIntent = useRef(false);

  // Track if canvas has been modified
  const [isDirty, setIsDirty] = useState(false);
  const [dirtyVersion, setDirtyVersion] = useState(0);
  const dirtyVersionRef = useRef(0);
  const markCanvasDirty = useCallback(() => {
    const nextVersion = dirtyVersionRef.current + 1;
    dirtyVersionRef.current = nextVersion;
    setDirtyVersion(nextVersion);
    setIsDirty(true);
  }, []);
  // Plant settings state (must be before persistCanvas)
  const [criticalPathMode, setCriticalPathMode] = useState(false);
  const [criticalPathNodeIds, setCriticalPathNodeIds] = useState<Set<string>>(new Set());
  const [plantHoursYear, setPlantHoursYear] = useState(8760);
  const [plantAvailability, setPlantAvailability] = useState(91.3);
  const effectiveOperatingHours = Math.round(plantHoursYear * (plantAvailability / 100));

  const [showSavePrompt, setShowSavePrompt] = useState(false);
  const pendingNavigation = useRef<string | null>(null);

  // Guard all navigation (menu clicks, sign out, browser back, tab close)
  const { proceed: guardProceed, reset: guardReset } = useUnsavedChangesGuard({
    isDirty,
    onBlock: useCallback((pendingUrl: string) => {
      pendingNavigation.current = pendingUrl;
      setShowSavePrompt(true);
    }, []),
  });

  // Track which gate nodes are currently snapped to boundary
  const [snappedGates, setSnappedGates] = useState<Set<string>>(new Set());
  const snappedTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Active alignment guides shown while dragging.
  const [alignGuides, setAlignGuides] = useState<AlignmentGuide[]>([]);

  const markGateSnapped = useCallback((gateId: string) => {
    setSnappedGates((prev) => {
      const next = new Set(prev);
      next.add(gateId);
      return next;
    });
    if (snappedTimers.current[gateId]) clearTimeout(snappedTimers.current[gateId]);
    snappedTimers.current[gateId] = setTimeout(() => {
      setSnappedGates((prev) => {
        const next = new Set(prev);
        next.delete(gateId);
        return next;
      });
    }, 600);
  }, []);

  // Mark dirty on any node/edge change
  const applyChangesWithGateClamp = useCallback((changes: NodeChange[]): { applied: NodeChange[]; didClampGate: boolean } => {
    const boundary = lastBoundaryRef.current;
    let didClampGate = false;
    const needsGateClamp = hasGateNodeRef.current && boundary.w > 0;
    // Build snapshot of other nodes for alignment snapping (only when at least
    // one position change is in flight to avoid the cost on selection changes).
    const hasDrag = changes.some((c) => c.type === "position" && c.position);
    const otherRects: NodeRect[] = hasDrag
      ? nodesRef.current
          .filter((n) => n.type !== "boundary")
          .map((n) => {
            const dims = nodeDimsByType(n.type);
            return { id: n.id, x: n.position.x, y: n.position.y, w: dims.w, h: dims.h };
          })
      : [];
    const draggedIds = new Set(
      changes.filter((c) => c.type === "position" && c.position).map((c) => (c as NodePositionChange).id),
    );
    const guidesAccum: AlignmentGuide[] = [];
    const stillDragging = changes.some((c) => c.type === "position" && c.dragging === true);

    let clamped = changes.map((c) => {
      if (c.type === "position" && c.position && c.dragging !== false) {
        const node = nodesRef.current.find((n) => n.id === c.id);
        if (node && node.type !== "boundary") {
          const dims = nodeDimsByType(node.type);
          const filtered = otherRects.filter((r) => !draggedIds.has(r.id));
          const { position, guides } = computeSnap(c.id, c.position, dims, filtered);
          if (guides.length > 0) guidesAccum.push(...guides);
          return { ...c, position };
        }
      }
      return c;
    });

    // Update guide overlay (only while a drag is active).
    if (hasDrag) {
      if (stillDragging) {
        setAlignGuides((prev) => {
          if (prev.length === guidesAccum.length && prev.every((p, i) => {
            const q = guidesAccum[i];
            return q && p.orientation === q.orientation && p.position === q.position && p.start === q.start && p.end === q.end;
          })) return prev;
          return guidesAccum;
        });
      } else {
        setAlignGuides((prev) => (prev.length === 0 ? prev : []));
      }
    }

    clamped = !needsGateClamp ? clamped : clamped.map((c) => {
      if (c.type === "position" && c.position) {
        const node = nodesRef.current.find((n) => n.id === c.id);
        if (node?.type === "gate" && boundary.w > 0) {
          const gateW = 170, gateH = 100;
          const gx = c.position.x;
          const gy = c.position.y;
          const bx1 = boundary.x;
          const by1 = boundary.y;
          const bx2 = boundary.x + boundary.w;
          const by2 = boundary.y + boundary.h;

          // Check if gate overlaps boundary interior
          const overlapX = gx + gateW > bx1 && gx < bx2;
          const overlapY = gy + gateH > by1 && gy < by2;

          if (overlapX && overlapY) {
            // Push gate to nearest boundary edge
            const distLeft = Math.abs((gx + gateW) - bx1);
            const distRight = Math.abs(gx - bx2);
            const distTop = Math.abs((gy + gateH) - by1);
            const distBottom = Math.abs(gy - by2);
            const minDist = Math.min(distLeft, distRight, distTop, distBottom);

            let newX = gx, newY = gy;
            if (minDist === distLeft) newX = bx1 - gateW - 10;
            else if (minDist === distRight) newX = bx2 + 10;
            else if (minDist === distTop) newY = by1 - gateH - 10;
            else newY = by2 + 10;

            markGateSnapped(c.id);
            if (c.dragging === false) didClampGate = true;
            return { ...c, position: { x: newX, y: newY } };
          }
        }
      }
      return c;
    });
    return { applied: clamped, didClampGate };
  }, [markGateSnapped]);

  const flushDragBuffer = useCallback(() => {
    dragRafRef.current = null;
    if (dragBufferRef.current.size === 0) return;
    const buffered = Array.from(dragBufferRef.current.values());
    dragBufferRef.current.clear();
    const { applied } = applyChangesWithGateClamp(buffered);
    onNodesChange(applied);
  }, [applyChangesWithGateClamp, onNodesChange]);

  const onNodesChangeTracked = useCallback((changes: NodeChange[]) => {
    // Split: in-flight position changes (dragging === true) get coalesced via
    // rAF, everything else (select, dimensions, remove, drag-end) is flushed
    // immediately so semantics stay correct.
    const immediate: NodeChange[] = [];
    for (const c of changes) {
      if (c.type === "position" && c.dragging === true && c.position) {
        // Latest-wins per node id
        dragBufferRef.current.set(c.id, c as NodePositionChange);
      } else {
        immediate.push(c);
      }
    }

    // Log lifecycle deletes before the nodes vanish from state.
    for (const c of immediate) {
      if (c.type === "remove") {
        const n = nodes.find((nn) => nn.id === c.id);
        if (n && (n.type === "equipment" || n.type === "carrier" || n.type === "gate")) {
          logComponentEvent(n.id, {
            category: "lifecycle",
            action: `${n.type === "equipment" ? "Equipment" : n.type === "carrier" ? "Carrier" : "Gate"} deleted`,
            old_value: (n.data?.label as string) || n.id,
          });
        }
      }
    }

    if (dragBufferRef.current.size > 0 && dragRafRef.current == null) {
      dragRafRef.current = requestAnimationFrame(flushDragBuffer);
    }

    if (immediate.length === 0) return;

    // If a drag-end / non-position change arrives, flush any pending buffered
    // positions first so the final committed state is consistent.
    if (dragBufferRef.current.size > 0) {
      if (dragRafRef.current != null) {
        cancelAnimationFrame(dragRafRef.current);
        dragRafRef.current = null;
      }
      flushDragBuffer();
    }

    const { applied, didClampGate } = applyChangesWithGateClamp(immediate);
    onNodesChange(applied);
    if (applied.some((c) => c.type !== "select" && c.type !== "position")) markCanvasDirty();
    if (didClampGate) toast.warning("Gates cannot be inside the system boundary, snapped outside.");
  }, [applyChangesWithGateClamp, flushDragBuffer, onNodesChange, markCanvasDirty, nodes]);

  // Cancel any pending rAF on unmount
  useEffect(() => () => {
    if (dragRafRef.current != null) cancelAnimationFrame(dragRafRef.current);
  }, []);

  const onEdgesChangeTracked = useCallback(
    (changes: Parameters<typeof onEdgesChangeBase>[0]) => {
      const filtered = changes.filter((c) => {
        if (c.type === "remove") {
          if (!userDeleteIntent.current) return false;
        }
        return true;
      });
      if (filtered.length > 0) {
        onEdgesChangeBase(filtered);
        if (filtered.some((c) => c.type !== "select")) markCanvasDirty();
      }
      userDeleteIntent.current = false;
    },
    [onEdgesChangeBase, markCanvasDirty]
  );

  /** Build current plant settings snapshot */
  const buildPlantSettings = useCallback(() => ({
    hoursYear: plantHoursYear,
    plantAvailability,
    criticalPathNodeIds: [...criticalPathNodeIds],
    boundaryPadding: { ...manualPadding.current },
  }), [plantHoursYear, plantAvailability, criticalPathNodeIds]);

  /** Save canvas to cloud storage */
  const persistCanvas = useCallback(() => {
    void saveCanvasData(nodes, edges, buildPlantSettings());
    dirtyVersionRef.current = 0;
    setDirtyVersion(0);
    setIsDirty(false);
  }, [saveCanvasData, nodes, edges, buildPlantSettings]);

  /**
   * Create a new iteration from the live canvas state. The current
   * nodes/edges/settings are snapshotted and uploaded as the seed for
   * the new iteration so the fork captures unsaved work too.
   * Switching to the new iteration is just a route change — useCanvasData
   * resets and rehydrates cleanly for the new plantId.
   */
  /** Open the "name this iteration" dialog with a default like "Plant variation #N". */
  const openNewIterationDialog = useCallback(() => {
    const groupId = plant.projectGroupId || plant.id;
    setNewIterName(nextIterationLabel(groupId, allPlants));
    setNewIterDialogOpen(true);
  }, [allPlants, plant.projectGroupId, plant.id]);

  const handleCreateIteration = useCallback(async (customLabel?: string) => {
    if (creatingIteration) return;
    setCreatingIteration(true);
    try {
      // Flush current edits to source first so version history is preserved.
      try { await saveCanvasData(nodes, edges, buildPlantSettings()); } catch { /* non-fatal */ }
      const { plant: created, variantLabel } = await createIteration({
        source: plant,
        userId: authUser?.id,
        plants: allPlants,
        customVariantLabel: customLabel,
        liveCanvas: {
          nodes,
          edges,
          plantSettings: buildPlantSettings(),
          retiredDisplayIds: canvasData?.retiredDisplayIds ?? [],
        },
      });
      toast.success(`Created ${variantLabel}`);
      setNewIterDialogOpen(false);
      navigate(`/canvas/${created.id}`);
    } catch (err) {
      console.error("[PlantCanvas] iteration failed:", err);
      toast.error("Could not create iteration. Please try again.");
    } finally {
      setCreatingIteration(false);
    }
  }, [creatingIteration, saveCanvasData, nodes, edges, buildPlantSettings, plant, authUser?.id, allPlants, canvasData?.retiredDisplayIds, navigate]);

  /** Commit an inline rename of an iteration's variant label. */
  const handleRenameIteration = useCallback(async (id: string, label: string) => {
    const target = allPlants.find((p) => p.id === id);
    if (!target) return;
    const trimmed = label.trim();
    if (!trimmed || trimmed === target.variantLabel) {
      setRenamingId(null);
      return;
    }
    try {
      await renamePlantVariation({ plant: target, userId: authUser?.id, variantLabel: trimmed });
      toast.success(`Renamed to "${trimmed}"`);
    } catch (err) {
      console.error("[PlantCanvas] rename failed:", err);
      toast.error("Could not rename variation.");
    } finally {
      setRenamingId(null);
    }
  }, [allPlants, authUser?.id]);

  /** Permanently delete the requested iteration. If it's the current one, route to a sibling. */
  const confirmDeleteIteration = useCallback(async () => {
    if (!deleteTarget) return;
    const target = allPlants.find((p) => p.id === deleteTarget.id);
    if (!target) { setDeleteTarget(null); return; }
    setDeletingIteration(true);
    try {
      await deletePlantVariation({ plant: target, userId: authUser?.id });
      toast.success(`Deleted "${deleteTarget.label}"`);
      if (deleteTarget.id === plantId) {
        const sibling = iterationMembers.find((m) => m.id !== deleteTarget.id);
        if (sibling) navigate(`/canvas/${sibling.id}`);
        else navigate("/plant-builder");
      }
    } catch (err) {
      console.error("[PlantCanvas] delete failed:", err);
      toast.error("Could not delete variation.");
    } finally {
      setDeletingIteration(false);
      setDeleteTarget(null);
    }
  }, [deleteTarget, allPlants, authUser?.id, plantId, iterationMembers, navigate]);

  /** Auto-save: debounce every canvas mutation to cloud storage */
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Declared early so the plant-switch reset effect can clear it before
  // the settings-sync effect runs for the newly loaded plant.
  const settingsHydrated = useRef(false);
  useEffect(() => {
    hydratedPlantIdRef.current = null;
    didInitialFit.current = false;
    setNodes([]);
    setEdges([]);
    setIsDirty(false);
    setDirtyVersion(0);
    dirtyVersionRef.current = 0;
    // Reset the settings-hydration guard so the first sync of the freshly
    // loaded plant's settings is treated as hydration (no markCanvasDirty)
    // and doesn't trigger a phantom save on plant open/switch.
    settingsHydrated.current = false;
    if (autoSaveTimer.current) {
      clearTimeout(autoSaveTimer.current);
      autoSaveTimer.current = null;
    }
  }, [plantId, setNodes, setEdges]);
  const latestNodes = useRef(nodes);
  const latestEdges = useRef(edges);
  const latestSettings = useRef(buildPlantSettings());
  latestNodes.current = nodes;
  latestEdges.current = edges;
  latestSettings.current = buildPlantSettings();

  const unmountingRef = useRef(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

  // Auto-save: every dirty version is persisted in order. The latest version
  // is only marked clean after its own upload completes, so older uploads can
  // never hide newer unsaved edits/undo states.
  useEffect(() => {
    if (!isDirty || dirtyVersion === 0) return;
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    const versionToSave = dirtyVersion;
    autoSaveTimer.current = setTimeout(() => {
      console.log("[auto-save] Persisting canvas to cloud storage…");
      void saveCanvasData(latestNodes.current, latestEdges.current, latestSettings.current).then(() => {
        if (dirtyVersionRef.current === versionToSave) {
          dirtyVersionRef.current = 0;
          setDirtyVersion(0);
          setIsDirty(false);
        }
        setLastSavedAt(new Date());
      });
      autoSaveTimer.current = null;
    }, 400);
  }, [isDirty, dirtyVersion, saveCanvasData]);

  // Flush on true unmount only
  useEffect(() => {
    return () => {
      unmountingRef.current = true;
      if (autoSaveTimer.current) {
        clearTimeout(autoSaveTimer.current);
        autoSaveTimer.current = null;
        console.log("[auto-save] Flushing pending save on unmount…");
        void saveCanvasData(latestNodes.current, latestEdges.current, latestSettings.current);
      }
    };
  }, [saveCanvasData]);

  // Mark dirty when plant settings change (triggers auto-save)
  useEffect(() => {
    // Skip initial render and the first hydration from cloud data
    if (!canvasData) return;
    if (!settingsHydrated.current) {
      settingsHydrated.current = true;
      return;
    }
    markCanvasDirty();
  }, [plantHoursYear, plantAvailability, criticalPathNodeIds, markCanvasDirty]);

  // ── Phase 2: live broadcast of local edits to peers ──
  // Every time the canvas gets dirty, push a throttled snapshot through the
  // sync channel so peers converge well before the cloud autosave fires.
  useEffect(() => {
    if (!isDirty || dirtyVersion === 0) return;
    broadcastSnapshot(latestNodes.current, latestEdges.current, latestSettings.current);
  }, [isDirty, dirtyVersion, broadcastSnapshot]);

  // ── Phase 2: apply inbound peer snapshots ──
  // Skip while the local user is dragging or actively connecting to avoid
  // yanking nodes/edges out from under them. Also skip if we have unsaved
  // edits — the remote will overwrite ours otherwise. The next dirty cycle
  // will rebroadcast our state.
  const lastAppliedRemoteTsRef = useRef(0);
  useEffect(() => {
    if (!remoteSnapshot) return;
    if (remoteSnapshot.ts <= lastAppliedRemoteTsRef.current) return;
    if (isDraggingNodeRef.current) return;
    if (isDirty) return;
    lastAppliedRemoteTsRef.current = remoteSnapshot.ts;
    setNodes(remoteSnapshot.nodes);
    setEdges(remoteSnapshot.edges);
    if (remoteSnapshot.plantSettings) {
      setPlantHoursYear(remoteSnapshot.plantSettings.hoursYear);
      setPlantAvailability(remoteSnapshot.plantSettings.plantAvailability);
      setCriticalPathNodeIds(new Set(remoteSnapshot.plantSettings.criticalPathNodeIds));
      const bp = remoteSnapshot.plantSettings.boundaryPadding;
      if (bp) manualPadding.current = { ...bp };
    }
    toast.message(`${remoteSnapshot.originName} updated the plant`, { duration: 1800 });
  }, [remoteSnapshot, isDirty, setNodes, setEdges]);

  /** Navigate with save prompt if dirty */
  // onEdgesChange is now handled by onEdgesChangeTracked above
  // Persisted toolbar preferences (IDs toggle, debug overlay, legend,
  // component-library collapsed, layout orientation). Survives page reloads,
  // project switches, and syncs across tabs.
  const { prefs: toolbarPrefs, update: updateToolbarPref } = useCanvasToolbarPrefs();
  const { prefs: labelNormPrefs, update: updateLabelNormPref, reset: resetLabelNormPrefs } = useLabelNormalizationPrefs();
  const collapsed = toolbarPrefs.componentLibraryCollapsed;
  const setCollapsed = useCallback((next: boolean | ((v: boolean) => boolean)) => {
    updateToolbarPref(
      "componentLibraryCollapsed",
      typeof next === "function" ? (next as (v: boolean) => boolean)(collapsed) : next,
    );
  }, [collapsed, updateToolbarPref]);
  const { pushSnapshot, undo, canUndo } = useCanvasHistory();
  const onNodeDragStart = useCallback(() => {
    isDraggingNodeRef.current = true;
    pushSnapshot(nodesRef.current, edgesRef.current);
  }, [pushSnapshot]);

  // UUID-based node IDs to prevent collisions across sessions
  const genNodeId = useCallback(() => `node-${crypto.randomUUID().slice(0, 8)}`, []);
  const [showSummary, setShowSummary] = useState(false);
  const [showCheckPanel, setShowCheckPanel] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const [showExportDesign, setShowExportDesign] = useState(false);
  const [exportSnapshot, setExportSnapshot] = useState<ExportSnapshot | null>(null);
  const showLegend = toolbarPrefs.showLegend;
  const setShowLegend = useCallback((next: boolean | ((v: boolean) => boolean)) => {
    updateToolbarPref("showLegend", typeof next === "function" ? (next as (v: boolean) => boolean)(showLegend) : next);
  }, [showLegend, updateToolbarPref]);
  const showNodeIds = toolbarPrefs.showNodeIds;
  const setShowNodeIds = useCallback((next: boolean | ((v: boolean) => boolean)) => {
    updateToolbarPref("showNodeIds", typeof next === "function" ? (next as (v: boolean) => boolean)(showNodeIds) : next);
  }, [showNodeIds, updateToolbarPref]);
  const debugNodeIds = toolbarPrefs.debugNodeIds;
  const setDebugNodeIds = useCallback((next: boolean | ((v: boolean) => boolean)) => {
    updateToolbarPref("debugNodeIds", typeof next === "function" ? (next as (v: boolean) => boolean)(debugNodeIds) : next);
  }, [debugNodeIds, updateToolbarPref]);
  const [showFlowWarning, setShowFlowWarning] = useState(false);
  const layoutOrientation = toolbarPrefs.layoutOrientation;
  const setLayoutOrientation = useCallback((next: "horizontal" | "vertical") => {
    updateToolbarPref("layoutOrientation", next);
  }, [updateToolbarPref]);
  const compactNodes = toolbarPrefs.compactNodes;
  const setCompactNodes = useCallback((next: boolean) => {
    updateToolbarPref("compactNodes", next);
  }, [updateToolbarPref]);
  const straightEdges = toolbarPrefs.straightEdges;
  const setStraightEdges = useCallback((next: boolean) => {
    updateToolbarPref("straightEdges", next);
  }, [updateToolbarPref]);

  // Warn when a node action lands a pinned displayId that collides with a
  // retired/reserved one (e.g. after restoring an old snapshot or importing).
  // Uses a ref to only toast on transitions, so opening Plant Settings or
  // re-rendering doesn't re-fire the warning.
  const lastConflictKeyRef = useRef<string>("");
  useEffect(() => {
    const retired = new Set(canvasData?.retiredDisplayIds ?? []);
    if (retired.size === 0) { lastConflictKeyRef.current = ""; return; }
    const conflicts: Array<{ id: string; displayId: string; nodeLabel: string }> = [];
    for (const n of nodes) {
      const did = (n.data as { displayId?: unknown })?.displayId;
      if (typeof did !== "string" || !retired.has(did)) continue;
      const rawLabel = (n.data as { label?: unknown })?.label;
      const nodeLabel = typeof rawLabel === "string" && rawLabel.trim() ? rawLabel : "(unlabeled)";
      conflicts.push({ id: n.id, displayId: did, nodeLabel });
    }
    const key = conflicts.map((c) => `${c.id}:${c.displayId}`).sort().join("|");
    if (key === lastConflictKeyRef.current) return;
    // Only toast when new conflicts appear (not when they're cleared).
    const prev = new Set(lastConflictKeyRef.current.split("|").filter(Boolean));
    const fresh = conflicts.filter((c) => !prev.has(`${c.id}:${c.displayId}`));
    lastConflictKeyRef.current = key;
    if (fresh.length === 0) return;
    const first = fresh[0];
    const more = fresh.length > 1 ? ` (+${fresh.length - 1} more)` : "";
    toast.warning(`Display ID conflict: ${first.displayId}${more}`, {
      description: `${first.nodeLabel} reuses a retired/reserved ID. Open Plant Settings → Plant Display → ID Traceability to review.`,
      action: { label: "Review", onClick: () => setShowSettings(true) },
    });
  }, [nodes, canvasData?.retiredDisplayIds]);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [edgeContextMenu, setEdgeContextMenu] = useState<{ edgeId: string; x: number; y: number } | null>(null);
  const [nodeContextMenu, setNodeContextMenu] = useState<{ nodeId: string; nodeType: string; x: number; y: number } | null>(null);
  const [batchDialogEdgeId, setBatchDialogEdgeId] = useState<string | null>(null);
  const [, setReconnectingHandleType] = useState<"source" | "target" | null>(null);
  // (criticalPathMode, criticalPathNodeIds, plantHoursYear, plantAvailability declared above)
  /**
   * Detect a mergeable pair: any 2 selected equipment nodes.
   * Preferred case — a single carrier sits between them (A→carrier→B). The
   * carrier is then discarded on merge. If no such carrier exists, we still
   * allow the merge (carrier = null) and simply rewire any direct edges.
   */
  const mergeCandidate = useMemo(() => {
    if (selectedNodeIds.length !== 2) return null;
    const [idA, idB] = selectedNodeIds;
    const nodeA = nodes.find((n) => n.id === idA);
    const nodeB = nodes.find((n) => n.id === idB);
    if (!nodeA || !nodeB || nodeA.type !== "equipment" || nodeB.type !== "equipment") return null;

    // Look for a carrier that sits between them
    for (const carrier of nodes) {
      if (carrier.type !== "carrier") continue;
      const aToCarrier = edges.some((e) => e.source === idA && e.target === carrier.id);
      const carrierToB = edges.some((e) => e.source === carrier.id && e.target === idB);
      if (aToCarrier && carrierToB) return { first: nodeA, second: nodeB, carrier };

      const bToCarrier = edges.some((e) => e.source === idB && e.target === carrier.id);
      const carrierToA = edges.some((e) => e.source === carrier.id && e.target === idA);
      if (bToCarrier && carrierToA) return { first: nodeB, second: nodeA, carrier };
    }
    // Fallback: allow merge of any two equipment, no carrier in between
    return { first: nodeA, second: nodeB, carrier: null as Node | null };
  }, [selectedNodeIds, nodes, edges]);

  /** Merge two equipment nodes, discarding the carrier between them */
  const handleMergeEquipment = useCallback(() => {
    if (!mergeCandidate) return;
    const { first, second, carrier } = mergeCandidate;
    pushSnapshot(nodes, edges);

    const mergedLabel = `${first.data.label} & ${second.data.label}`;
    const mergedPos = {
      x: (first.position.x + second.position.x) / 2,
      y: (first.position.y + second.position.y) / 2,
    };
    const mergedId = `merged-${first.id}-${second.id}`;

    // Capture edges between the removed nodes for unmerge restoration
    const removedIds = new Set<string>([first.id, second.id]);
    if (carrier) removedIds.add(carrier.id);
    const removedEdges = edges.filter(
      (e) => removedIds.has(e.source) && removedIds.has(e.target)
    );

    const mergedNode: Node = {
      id: mergedId,
      type: "equipment",
      position: mergedPos,
      data: {
        label: mergedLabel,
        subtitle: first.data.subtitle || second.data.subtitle || undefined,
        manufacturer: first.data.manufacturer || second.data.manufacturer || undefined,
        model: first.data.model || second.data.model || undefined,
        merged: true,
        mergedFrom: [first.id, second.id],
        // Store originals for unmerge
        _mergeSnapshot: {
          firstNode: JSON.parse(JSON.stringify(first)),
          secondNode: JSON.parse(JSON.stringify(second)),
          carrierNode: carrier ? JSON.parse(JSON.stringify(carrier)) : null,
          removedEdges: JSON.parse(JSON.stringify(removedEdges)),
        },
      },
    };

    const newEdges = edges
      .filter((e) => !(removedIds.has(e.source) && removedIds.has(e.target)))
      .map((e) => {
        let updated = { ...e };
        if (removedIds.has(e.source)) updated = { ...updated, source: mergedId };
        if (removedIds.has(e.target)) updated = { ...updated, target: mergedId };
        return updated;
      });

    const newNodes = nodes.filter((n) => !removedIds.has(n.id)).concat(mergedNode);
    setNodes(newNodes);
    setEdges(newEdges);
    setSelectedNodeIds([]);
    markCanvasDirty();
  }, [mergeCandidate, nodes, edges, setNodes, setEdges, pushSnapshot, markCanvasDirty]);

  /** Detect if a single selected node is a merged node that can be unmerged */
  const unmergeCandidate = useMemo(() => {
    if (selectedNodeIds.length !== 1) return null;
    const node = nodes.find((n) => n.id === selectedNodeIds[0]);
    if (!node || !node.data.merged || !node.data._mergeSnapshot) return null;
    return node;
  }, [selectedNodeIds, nodes]);

  /** Unmerge a merged node back to its original two equipment nodes + carrier */
  const handleUnmergeEquipment = useCallback(() => {
    if (!unmergeCandidate) return;
    pushSnapshot(nodes, edges);

    const snapshot = unmergeCandidate.data._mergeSnapshot as {
      firstNode: Node;
      secondNode: Node;
      carrierNode: Node | null;
      removedEdges: Edge[];
    };
    const mergedId = unmergeCandidate.id;

    // Restore original nodes
    const restoredNodes = [snapshot.firstNode, snapshot.secondNode];
    if (snapshot.carrierNode) restoredNodes.push(snapshot.carrierNode);

    // Rewire edges that currently point to/from mergedId back to their original sources/targets
    const originalIds = new Set<string>([snapshot.firstNode.id, snapshot.secondNode.id]);
    if (snapshot.carrierNode) originalIds.add(snapshot.carrierNode.id);
    const newEdges = edges
      .filter((e) => e.source !== mergedId && e.target !== mergedId)
      .concat(snapshot.removedEdges);

    // For edges that were rewired to mergedId, restore them to the correct original node
    // Edges that targeted mergedId originally targeted first or carrier
    // Edges that sourced from mergedId originally sourced from second or carrier
    const rewiredEdges = edges.filter(
      (e) => (e.source === mergedId || e.target === mergedId)
    );
    for (const e of rewiredEdges) {
      const restored = { ...e };
      if (e.source === mergedId) {
        // This edge originally came from second node (output side)
        restored.source = snapshot.secondNode.id;
      }
      if (e.target === mergedId) {
        // This edge originally went into first node (input side)
        restored.target = snapshot.firstNode.id;
      }
      newEdges.push(restored);
    }

    const newNodes = nodes.filter((n) => n.id !== mergedId).concat(restoredNodes);
    setNodes(newNodes);
    setEdges(newEdges);
    setSelectedNodeIds([]);
    markCanvasDirty();
  }, [unmergeCandidate, nodes, edges, setNodes, setEdges, pushSnapshot, markCanvasDirty]);

  const onSelectionChange = useCallback(({ nodes: selectedNodes, edges: selectedEdges }: { nodes: Node[]; edges: Edge[] }) => {
    setSelectedNodeIds(selectedNodes.map((n) => n.id));
    const latestSelectedEdge = selectedEdges[selectedEdges.length - 1]?.id ?? null;
    setSelectedEdgeId(latestSelectedEdge);
  }, []);

  const handleUpdateEdgeFlowValue = useCallback((edgeId: string, flowValue: number | undefined, flowUnit: string) => {
    pushSnapshot(nodes, edges);
    setEdges((currentEdges) => currentEdges.map((edge) =>
      edge.id === edgeId
        ? { ...edge, data: { ...edge.data, flowValue, flowUnit } }
        : edge
    ));
    markCanvasDirty();
  }, [nodes, edges, pushSnapshot, setEdges, markCanvasDirty]);

  const handleDeleteEdgeFlowValue = useCallback((edgeId: string) => {
    pushSnapshot(nodes, edges);
    setEdges((currentEdges) => currentEdges.map((edge) =>
      edge.id === edgeId
        ? { ...edge, data: { ...edge.data, flowValue: undefined, flowUnit: undefined } }
        : edge
    ));
    markCanvasDirty();
  }, [nodes, edges, pushSnapshot, setEdges, markCanvasDirty]);

  const handleDeleteEdge = useCallback((edgeId: string) => {
    pushSnapshot(nodes, edges);
    setEdges((currentEdges) => currentEdges.filter((edge) => edge.id !== edgeId));
    setSelectedEdgeId((currentSelectedEdgeId) => currentSelectedEdgeId === edgeId ? null : currentSelectedEdgeId);
    markCanvasDirty();
  }, [nodes, edges, pushSnapshot, setEdges, markCanvasDirty]);

  /** Live update of an edge's manual bend offset (called many times per drag). */
  const handleUpdateEdgeRoute = useCallback((edgeId: string, bendOffsetX: number, bendOffsetY: number) => {
    setEdges((currentEdges) => currentEdges.map((edge) =>
      edge.id === edgeId
        ? { ...edge, data: { ...edge.data, bendOffsetX, bendOffsetY } }
        : edge,
    ));
    markCanvasDirty();
  }, [setEdges, markCanvasDirty]);

  /** Reset an edge's manual bend back to the auto-routed midpoint. */
  const handleResetEdgeRoute = useCallback((edgeId: string) => {
    pushSnapshot(nodes, edges);
    setEdges((currentEdges) => currentEdges.map((edge) =>
      edge.id === edgeId
        ? { ...edge, data: { ...edge.data, bendOffsetX: 0, bendOffsetY: 0 } }
        : edge,
    ));
    markCanvasDirty();
  }, [nodes, edges, pushSnapshot, setEdges, markCanvasDirty]);

  /** Switch an edge to batch flow with sensible defaults, then open the dialog. */
  const handleSwitchToBatch = useCallback((edgeId: string) => {
    pushSnapshot(nodes, edges);
    setEdges((currentEdges) => currentEdges.map((edge) => {
      if (edge.id !== edgeId) return edge;
      const d = (edge.data ?? {}) as { flowValue?: number; flowUnit?: string; batch?: BatchFlowConfig };
      if (d.batch) return edge;
      const seed = defaultBatchConfig(d.flowValue, d.flowUnit);
      const flowUnit = d.flowUnit ?? "kg/h";
      const derived = computeEquivalentRate(seed, flowUnit);
      return {
        ...edge,
        data: { ...edge.data, flowMode: "batch", batch: seed, flowUnit, flowValue: derived },
      };
    }));
    setBatchDialogEdgeId(edgeId);
    markCanvasDirty();
  }, [nodes, edges, pushSnapshot, setEdges, markCanvasDirty]);

  /** Switch an edge back to continuous, keeping the derived rate. */
  const handleSwitchToContinuous = useCallback((edgeId: string) => {
    pushSnapshot(nodes, edges);
    setEdges((currentEdges) => currentEdges.map((edge) => {
      if (edge.id !== edgeId) return edge;
      const d = (edge.data ?? {}) as { flowValue?: number; flowUnit?: string };
      return {
        ...edge,
        data: { ...edge.data, flowMode: "continuous", batch: undefined, flowValue: d.flowValue, flowUnit: d.flowUnit ?? "kg/h" },
      };
    }));
    markCanvasDirty();
  }, [nodes, edges, pushSnapshot, setEdges, markCanvasDirty]);

  /** Save updated batch config and refresh the derived equivalent rate. */
  const handleUpdateBatch = useCallback((edgeId: string, config: BatchFlowConfig) => {
    pushSnapshot(nodes, edges);
    setEdges((currentEdges) => currentEdges.map((edge) => {
      if (edge.id !== edgeId) return edge;
      const flowUnit = ((edge.data ?? {}) as { flowUnit?: string }).flowUnit ?? "kg/h";
      const derived = computeEquivalentRate(config, flowUnit);
      return {
        ...edge,
        data: { ...edge.data, flowMode: "batch", batch: config, flowValue: derived, flowUnit },
      };
    }));
    markCanvasDirty();
  }, [nodes, edges, pushSnapshot, setEdges, markCanvasDirty]);

  const handleOpenBatchDialog = useCallback((edgeId: string) => {
    setBatchDialogEdgeId(edgeId);
  }, []);

  /**
   * Reverse the direction of an edge (swap source ↔ target).
   * Also swaps the anchor handle roles so the new source uses the "-s"
   * variant of the same side and the new target uses the "-t" variant.
   */
  const handleReverseEdge = useCallback((edgeId: string) => {
    const currentNodes = nodesRef.current;
    const currentEdges = edgesRef.current;
    if (!currentEdges.some((edge) => edge.id === edgeId)) return;

    pushSnapshot(currentNodes, currentEdges);
    setEdges((edgesNow) => edgesNow.map((edge) => {
      if (edge.id !== edgeId) return { ...edge, selected: false };
      const reversed = normalizeConnection({
        rawSource: edge.target,
        rawTarget: edge.source,
        rawSourceHandle: edge.targetHandle,
        rawTargetHandle: edge.sourceHandle,
        startNodeId: null,
        nodes: currentNodes,
      });
      if (!reversed) return edge;
      // Avoid creating a React Flow key collision with another existing
      // edge that already uses the same source/target/handles tuple.
      const collides = edgesNow.some((other) =>
        other.id !== edge.id &&
        other.source === reversed.source &&
        other.target === reversed.target &&
        other.sourceHandle === reversed.sourceHandle &&
        other.targetHandle === reversed.targetHandle
      );
      if (collides) {
        toast.error("Cannot reverse: an edge with the same endpoints already exists.");
        return edge;
      }
      return { ...edge, ...reversed, selected: true };
    }));
    setSelectedEdgeId(edgeId);
    setEdgeContextMenu(null);
    markCanvasDirty();
  }, [pushSnapshot, setEdges, markCanvasDirty]);

  const { findings: checkFindings } = useEngineCheck();

  // Detail dialog state
  const [detailNode, setDetailNode] = useState<Node | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // Procurement warning state
  const [procurementOpen, setProcurementOpen] = useState(false);
  const [incompleteEquipment] = useState<Node[]>([]);

  // Flow balance engine — runs reactively on edge changes
  const balanceReport: BalanceReport = useMemo(
    () => runFlowBalance(nodes, edges),
    [nodes, edges]
  );

  // Annotate nodes with imbalance warnings for visual feedback (only when panel is visible)
  useEffect(() => {
    if (!showCheckPanel) {
      // Clear all warnings when panel is hidden
      setNodes((nds) => {
        if (!nds.some((n) => n.data.imbalanceWarning)) return nds;
        return nds.map((n) =>
          n.data.imbalanceWarning ? { ...n, data: { ...n.data, imbalanceWarning: undefined } } : n
        );
      });
      return;
    }
    const warningMap = new Map<string, string>();
    for (const imb of balanceReport.imbalances) {
      const sign = imb.loss > 0 ? "−" : "+";
      warningMap.set(imb.nodeId, `${sign}${Math.abs(imb.loss).toFixed(1)} ${imb.unit} (${Math.abs(imb.lossPercent).toFixed(1)}%)`);
    }
    setNodes((nds) => {
      let changed = false;
      const next = nds.map((n) => {
        const warning = warningMap.get(n.id);
        if (warning && n.data.imbalanceWarning !== warning) {
          changed = true;
          return { ...n, data: { ...n.data, imbalanceWarning: warning } };
        }
        if (!warning && n.data.imbalanceWarning) {
          changed = true;
          return { ...n, data: { ...n.data, imbalanceWarning: undefined } };
        }
        return n;
      });
      return changed ? next : nds;
    });
  }, [balanceReport.imbalances, setNodes, showCheckPanel]);

  // ── Dynamic system boundary: auto-resize to wrap all equipment & carrier nodes ──

  /** Store a ref to the React Flow instance for zoom access */
  const reactFlowInstance = useRef<ReturnType<typeof useReactFlow> | null>(null);
  const rf = useReactFlow();
  reactFlowInstance.current = rf;

  /** Compute the minimum boundary rect from equipment/carrier positions */
  const computeMinBoundary = useCallback(() => {
    const PADDING = 60;
    const TOP_PADDING = 50;
    const innerNodes = nodes.filter((n) => n.type === "equipment" || n.type === "carrier");
    if (innerNodes.length === 0) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of innerNodes) {
      const nw = n.type === "carrier" ? 72 : 140;
      const nh = n.type === "carrier" ? 72 : 80;
      minX = Math.min(minX, n.position.x);
      minY = Math.min(minY, n.position.y);
      maxX = Math.max(maxX, n.position.x + nw);
      maxY = Math.max(maxY, n.position.y + nh);
    }
    return {
      x: minX - PADDING,
      y: minY - PADDING - TOP_PADDING,
      w: maxX - minX + PADDING * 2,
      h: maxY - minY + PADDING * 2 + TOP_PADDING,
    };
  }, [nodes]);

  /** Clamp gates outside the current boundary */
  const clampGatesOutsideBoundary = useCallback(() => {
    const b = lastBoundaryRef.current;
    if (b.w === 0) return;
    setNodes((nds) =>
      nds.map((n) => {
        if (n.type !== "gate") return n;
        const gateW = 170, gateH = 100;
        const gx = n.position.x, gy = n.position.y;
        const overlapX = gx + gateW > b.x && gx < b.x + b.w;
        const overlapY = gy + gateH > b.y && gy < b.y + b.h;
        if (overlapX && overlapY) {
          const distLeft = Math.abs((gx + gateW) - b.x);
          const distRight = Math.abs(gx - (b.x + b.w));
          const distTop = Math.abs((gy + gateH) - b.y);
          const distBottom = Math.abs(gy - (b.y + b.h));
          const minDist = Math.min(distLeft, distRight, distTop, distBottom);
          let newX = gx, newY = gy;
          if (minDist === distLeft) newX = b.x - gateW - 10;
          else if (minDist === distRight) newX = b.x + b.w + 10;
          else if (minDist === distTop) newY = b.y - gateH - 10;
          else newY = b.y + b.h + 10;
          return { ...n, position: { x: newX, y: newY } };
        }
        return n;
      })
    );
  }, [setNodes, navigate, plantId]);

  /** Apply boundary rect (min + manual padding) and update boundary node */
  const updateBoundaryNode = useCallback((minRect: { x: number; y: number; w: number; h: number }) => {
    const mp = manualPadding.current;
    let bx = minRect.x - mp.left;
    let by = minRect.y - mp.top;
    let bw = minRect.w + mp.left + mp.right;
    let bh = minRect.h + mp.top + mp.bottom;

    // Enforce a minimum boundary size so the UPSTREAM/DOWNSTREAM and
    // "System Boundary" labels never overlap each other.
    // Horizontal layout: upstream sits bottom-left, downstream bottom-right;
    // the badge sits centered at the top.
    const MIN_W = 480; // ~ upstream + downstream pill widths + center gap
    const MIN_H = 220; // ~ top badge + bottom labels with breathing room
    if (bw < MIN_W) {
      const extra = MIN_W - bw;
      bx -= extra / 2;
      bw = MIN_W;
    }
    if (bh < MIN_H) {
      const extra = MIN_H - bh;
      by -= extra / 2;
      bh = MIN_H;
    }

    const prev = lastBoundaryRef.current;
    if (
      Math.abs(prev.x - bx) < 2 &&
      Math.abs(prev.y - by) < 2 &&
      Math.abs(prev.w - bw) < 2 &&
      Math.abs(prev.h - bh) < 2
    ) return;

    lastBoundaryRef.current = { x: bx, y: by, w: bw, h: bh };
    setNodes((nds) => {
      const hasBoundary = nds.some((n) => n.type === "boundary");
      const boundaryData = {
        width: bw,
        height: bh,
        orientation: "horizontal",
        onResizeDrag: (...args: [string, number, number]) => resizeDragRef.current(...args),
        onResizeEnd: () => resizeEndRef.current(),
        onOpenInfrastructure: () => navigate(`/canvas/${plantId}/infrastructure`),
      };
      if (!hasBoundary) {
        const boundaryNode: Node = {
          id: "b-system",
          type: "boundary",
          position: { x: bx, y: by },
          data: boundaryData,
          draggable: false,
          selectable: false,
          zIndex: -1,
        };
        // Place the boundary first so it renders behind other nodes
        return [boundaryNode, ...nds];
      }
      return nds.map((n) =>
        n.type === "boundary"
          ? {
              ...n,
              draggable: false,
              selectable: false,
              position: { x: bx, y: by },
              data: { ...n.data, ...boundaryData },
            }
          : n
      );
    });
  }, [setNodes]);

  /** Handle resize drag from BoundaryNode — use ref for stable identity */
  const resizeDragRef = useRef<(side: string, dx: number, dy: number) => void>(() => {});
  const resizeEndRef = useRef<() => void>(() => {});

  resizeDragRef.current = (side: string, dx: number, dy: number) => {
    isResizingBoundary.current = true;
    const mp = manualPadding.current;
    const zoom = reactFlowInstance.current?.getZoom?.() ?? 1;
    const scaledDx = dx / zoom;
    const scaledDy = dy / zoom;

    if (side === "left") mp.left = Math.max(0, mp.left - scaledDx);
    else if (side === "right") mp.right = Math.max(0, mp.right + scaledDx);
    else if (side === "top") mp.top = Math.max(0, mp.top - scaledDy);
    else if (side === "bottom") mp.bottom = Math.max(0, mp.bottom + scaledDy);

    const minRect = computeMinBoundary();
    if (minRect) updateBoundaryNode(minRect);
    clampGatesOutsideBoundary();
  };

  resizeEndRef.current = () => {
    isResizingBoundary.current = false;
    markCanvasDirty();
  };

  const boundaryKey = useMemo(
    () => nodes.filter((n) => n.type === "equipment" || n.type === "carrier")
      .map((n) => `${n.id}:${Math.round(n.position.x)}:${Math.round(n.position.y)}`)
      .join(","),
    [nodes]
  );
  useEffect(() => {
    if (isDraggingNodeRef.current) return;
    if (isResizingBoundary.current) return;
    const minRect = computeMinBoundary();
    if (!minRect) {
      lastBoundaryRef.current = { x: 0, y: 0, w: 0, h: 0 };
      setNodes((nds) => nds.some((n) => n.type === "boundary") ? nds.filter((n) => n.type !== "boundary") : nds);
      return;
    }
    updateBoundaryNode(minRect);
    // After boundary changes, always kick gates outside
    clampGatesOutsideBoundary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundaryKey, setNodes]);

  const onConnect = useCallback(
    (connection: Connection) => {
      pushSnapshot(nodes, edges);
      markCanvasDirty();

      // ── Determine stream color from either endpoint's carrier label ──
      const startNodeId = connectingFromRef.current?.nodeId ?? null;
      const provisionalSourceNode = nodes.find((n) => n.id === connection.source);
      const provisionalTargetNode = nodes.find((n) => n.id === connection.target);
      let streamColor = "hsl(174, 45%, 45%)";
      let isElectricity = false;
      for (const node of [provisionalSourceNode, provisionalTargetNode]) {
        if (node?.type === "carrier" && node.data?.label) {
          const carrierLabel = node.data.label as string;
          const color = getColorFromResource(carrierLabel);
          if (color) {
            streamColor = color;
            isElectricity = carrierLabel === "Electricity";
            break;
          }
        }
      }

      // ── Single-source normalization: enforces drag direction AND
      //    guarantees handles that actually exist on the target nodes. ──
      const normalized = normalizeConnection({
        rawSource: connection.source,
        rawTarget: connection.target,
        rawSourceHandle: connection.sourceHandle,
        rawTargetHandle: connection.targetHandle,
        startNodeId,
        nodes,
      });
      if (!normalized) return;

      setEdges((eds) => addEdge({
        source: normalized.source,
        target: normalized.target,
        sourceHandle: normalized.sourceHandle,
        targetHandle: normalized.targetHandle,
        type: "flowEdge",
        animated: false,
        style: {
          stroke: streamColor,
          strokeWidth: isElectricity ? 1.9 : 2,
          ...(isElectricity ? { strokeDasharray: "5 3", opacity: 0.95 } : {}),
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: streamColor, width: 18, height: 18 },
        data: { isElectricity },
      }, eds));
    },
    [setEdges, nodes, edges, pushSnapshot, markCanvasDirty]
  );

  // Track the source of an in-progress connection so we can flash it on failure.
  const connectingFromRef = useRef<{ nodeId: string | null; handleType: "source" | "target" | null } | null>(null);
  const [connectFlashNodeId, setConnectFlashNodeId] = useState<string | null>(null);
  const [isConnectingEdge, setIsConnectingEdge] = useState(false);

  const onConnectStart = useCallback(
    (_: unknown, params: { nodeId: string | null; handleId: string | null; handleType: "source" | "target" | null }) => {
      connectingFromRef.current = { nodeId: params.nodeId, handleType: params.handleType };
      setIsConnectingEdge(true);
    },
    []
  );

  const onConnectEnd = useCallback(
    (_: MouseEvent | TouchEvent, connectionState?: { isValid?: boolean | null; toNode?: { id?: string } | null }) => {
      const fromId = connectingFromRef.current?.nodeId ?? null;
      const fromHandleType = connectingFromRef.current?.handleType ?? null;
      connectingFromRef.current = null;
      setIsConnectingEdge(false);
      // If React Flow already accepted the connection, onConnect handled it.
      if (connectionState?.isValid) return;
      // Distinguish "dropped on empty canvas" vs "dropped on a node but rejected".
      const droppedOnNode = !!connectionState?.toNode?.id;
      const isSelfLoop = droppedOnNode && connectionState?.toNode?.id === fromId;
      if (isSelfLoop) {
        toast.error("Cannot connect a node to itself.", { duration: 2200 });
      } else if (droppedOnNode && fromId) {
        // User released over a node but didn't hit a small handle dot.
        // Auto-snap: build a synthetic Connection and let onConnect handle it.
        const toId = connectionState!.toNode!.id!;
        // If user started the drag on a target handle, fromId is the target.
        const startedOnTarget = fromHandleType === "target";
        const synthetic: Connection = startedOnTarget
          ? { source: toId, target: fromId, sourceHandle: null, targetHandle: null }
          : { source: fromId, target: toId, sourceHandle: null, targetHandle: null };
        // Pass startNodeId via the ref for normalizeConnection's direction logic.
        connectingFromRef.current = { nodeId: fromId, handleType: fromHandleType };
        onConnect(synthetic);
        connectingFromRef.current = null;
        return;
      } else if (fromId) {
        toast("Drop the arrow on another node to create a stream.", { duration: 1800 });
      }
      // Flash the source node so the user sees where their drag started.
      if (fromId) {
        setConnectFlashNodeId(fromId);
        window.setTimeout(() => setConnectFlashNodeId((cur) => (cur === fromId ? null : cur)), 900);
      }
    },
    [onConnect]
  );

  // ── Edge reconnection (drag endpoint to reroute) ──
  const edgeReconnectSuccessful = useRef(true);
  const [isReconnectingEdge, setIsReconnectingEdge] = useState(false);

  const onReconnectStart = useCallback((_: React.MouseEvent, edge: Edge, handleType: "source" | "target") => {
    edgeReconnectSuccessful.current = false;
    setSelectedEdgeId(edge.id);
    setReconnectingHandleType(handleType);
    setIsReconnectingEdge(true);
  }, []);

  const onReconnect = useCallback(
    (oldEdge: Edge, newConnection: Connection) => {
      if (!newConnection.source || !newConnection.target) return;

      pushSnapshot(nodes, edges);
      edgeReconnectSuccessful.current = true;
      markCanvasDirty();

      // For reconnects, the moving endpoint is the dragged one; we keep
      // the existing source/target roles assigned by React Flow rather
      // than swapping them.
      const normalized = normalizeConnection({
        rawSource: newConnection.source,
        rawTarget: newConnection.target,
        rawSourceHandle: newConnection.sourceHandle,
        rawTargetHandle: newConnection.targetHandle,
        startNodeId: null, // do not flip direction during reconnect
        nodes,
      });
      if (!normalized) return;

      setEdges((eds) => reconnectEdge(oldEdge, {
        source: normalized.source,
        target: normalized.target,
        sourceHandle: normalized.sourceHandle,
        targetHandle: normalized.targetHandle,
      }, eds));
    },
    [setEdges, nodes, edges, pushSnapshot, markCanvasDirty]
  );

  const onReconnectEnd = useCallback(
    (_: MouseEvent | TouchEvent, _edge: Edge) => {
      setIsReconnectingEdge(false);
      setReconnectingHandleType(null);
      if (!edgeReconnectSuccessful.current) {
        // Edge was dropped on empty space — keep original edge
      }
    },
    []
  );

  // Keep stream attachments persistent while dragging:
  // React Flow will recompute edge geometry automatically from node positions.
  // We intentionally do not mutate sourceHandle/targetHandle during node moves.

  const onNodeDragStop = useCallback(() => {
    isDraggingNodeRef.current = false;
    setAlignGuides([]);
    const minRect = computeMinBoundary();
    if (minRect) {
      updateBoundaryNode(minRect);
      clampGatesOutsideBoundary();
    }
    markCanvasDirty();
  }, [computeMinBoundary, updateBoundaryNode, clampGatesOutsideBoundary, markCanvasDirty]);

  /* ── Undo last action ── */
  const handleUndo = useCallback(() => {
    const snapshot = undo();
    if (snapshot) {
      setNodes(snapshot.nodes);
      setEdges(snapshot.edges);
      markCanvasDirty();
      void saveCanvasData(snapshot.nodes, snapshot.edges, latestSettings.current);
    }
  }, [undo, setNodes, setEdges, markCanvasDirty, saveCanvasData]);

  // Ctrl+Z keyboard shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handleUndo]);

  // Shift+I keyboard shortcut: toggle component ID badges from anywhere on the canvas.
  // Skipped while focus is in editable fields so it doesn't hijack typing.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      const isEditable =
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target?.isContentEditable;
      if (isEditable) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.shiftKey && (e.key === "I" || e.key === "i")) {
        e.preventDefault();
        setShowNodeIds((v) => !v);
        toast.success(`Component IDs ${!showNodeIds ? "shown" : "hidden"}`);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [setShowNodeIds, showNodeIds]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const raw = e.dataTransfer.getData("application/reactflow");
      if (!raw) return;
      const item = JSON.parse(raw);
      const position = rf.screenToFlowPosition({
        x: e.clientX,
        y: e.clientY,
      });
      const newId = genNodeId();
      const newNode: Node = {
        id: newId,
        type: item.type,
        position,
        data: {
          label: item.label,
          ...(item.gateType ? { gateType: item.gateType } : {}),
          ...(item.type === "equipment" ? { id: newId } : {}),
        },
      };

      // If dropping a gate, ensure it lands outside the system boundary
      if (item.type === "gate") {
        const b = lastBoundaryRef.current;
        if (b.w > 0) {
          const gateW = 170, gateH = 100;
          const gx = newNode.position.x, gy = newNode.position.y;
          const overlapX = gx + gateW > b.x && gx < b.x + b.w;
          const overlapY = gy + gateH > b.y && gy < b.y + b.h;
          if (overlapX && overlapY) {
            const distLeft = Math.abs((gx + gateW) - b.x);
            const distRight = Math.abs(gx - (b.x + b.w));
            const distTop = Math.abs((gy + gateH) - b.y);
            const distBottom = Math.abs(gy - (b.y + b.h));
            const minDist = Math.min(distLeft, distRight, distTop, distBottom);
            if (minDist === distLeft) newNode.position.x = b.x - gateW - 10;
            else if (minDist === distRight) newNode.position.x = b.x + b.w + 10;
            else if (minDist === distTop) newNode.position.y = b.y - gateH - 10;
            else newNode.position.y = b.y + b.h + 10;
            markGateSnapped(newId);
            toast.warning("Gates must stay outside the system boundary, repositioned.");
          }
        }
      }

      pushSnapshot(nodes, edges);
      logComponentEvent(newId, {
        category: "lifecycle",
        action: `${item.type === "equipment" ? "Equipment" : item.type === "carrier" ? "Carrier" : "Gate"} added`,
        new_value: item.label,
        details: `Dropped onto canvas at (${Math.round(position.x)}, ${Math.round(position.y)})`,
      });
      setNodes((nds) => {
        const next = [...nds, newNode];
        // If this is the first equipment/carrier and no boundary exists yet,
        // synthesize the boundary in the same update so it appears together.
        const isInner = item.type === "equipment" || item.type === "carrier";
        const hasBoundary = nds.some((n) => n.type === "boundary");
        if (isInner && !hasBoundary) {
          const PADDING = 60;
          const TOP_PADDING = 50;
          const inner = next.filter((n) => n.type === "equipment" || n.type === "carrier");
          let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
          for (const n of inner) {
            const nw = n.type === "carrier" ? 72 : 140;
            const nh = n.type === "carrier" ? 72 : 80;
            minX = Math.min(minX, n.position.x);
            minY = Math.min(minY, n.position.y);
            maxX = Math.max(maxX, n.position.x + nw);
            maxY = Math.max(maxY, n.position.y + nh);
          }
          const mp = manualPadding.current;
          const bx = minX - PADDING - mp.left;
          const by = minY - PADDING - TOP_PADDING - mp.top;
          const bw = (maxX - minX) + PADDING * 2 + mp.left + mp.right;
          const bh = (maxY - minY) + PADDING * 2 + TOP_PADDING + mp.top + mp.bottom;
          lastBoundaryRef.current = { x: bx, y: by, w: bw, h: bh };
          const boundaryNode: Node = {
            id: "b-system",
            type: "boundary",
            position: { x: bx, y: by },
            data: {
              width: bw,
              height: bh,
              orientation: "horizontal",
              onResizeDrag: (...args: [string, number, number]) => resizeDragRef.current(...args),
              onResizeEnd: () => resizeEndRef.current(),
            },
            draggable: false,
            selectable: false,
            zIndex: -1,
          };
          return [boundaryNode, ...next];
        }
        return next;
      });
      markCanvasDirty();
    },
    [rf, genNodeId, setNodes, nodes, edges, pushSnapshot, markCanvasDirty]
  );

  /* ── Double-click → open detail form ── */
  const onNodeDoubleClick = useCallback((_event: React.MouseEvent, node: Node) => {
    if (node.type === "boundary") return;
    if (criticalPathMode) return; // don't open detail in critical path mode
    setDetailNode(node);
    setDetailOpen(true);
  }, [criticalPathMode]);

  /** Single-click in critical path mode toggles equipment membership */
  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    // Clicking any node should deselect the currently highlighted stream
    setSelectedEdgeId(null);
    setEdgeContextMenu(null);
    // Clicking the system boundary frame behaves like a pane click → clear all selection
    if (node.type === "boundary") {
      setNodeContextMenu(null);
      setSelectedNodeIds([]);
      setEdges((eds) => eds.some((e) => e.selected) ? eds.map((e) => e.selected ? { ...e, selected: false } : e) : eds);
      setNodes((nds) => nds.some((n) => n.selected) ? nds.map((n) => n.selected ? { ...n, selected: false } : n) : nds);
      return;
    }
    if (!criticalPathMode || node.type !== "equipment") return;
    setCriticalPathNodeIds((prev) => {
      const next = new Set(prev);
      if (next.has(node.id)) next.delete(node.id);
      else next.add(node.id);
      return next;
    });
  }, [criticalPathMode, setEdges, setNodes]);

  /* ── Save detail form data back to node ── */
  const handleDetailSave = useCallback((nodeId: string, data: Record<string, unknown>) => {
    pushSnapshot(nodes, edges);
    // Lift the carrier-encoded procurement object back into a real nested
    // `procurement` record on the node — see ComponentDetailDialog.handleSupplierSelect.
    let cleanData = data;
    const procJson = data.__procurementJson;
    if (typeof procJson === "string" && procJson) {
      try {
        const procurement = JSON.parse(procJson);
        const { __procurementJson, ...rest } = data;
        cleanData = { ...rest, procurement };
      } catch {
        const { __procurementJson, ...rest } = data;
        cleanData = rest;
      }
    }
    setNodes((nds) =>
      nds.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...cleanData } } : n
      )
    );
    markCanvasDirty();
    // Sync detailNode so dialog shows updated data if reopened
    setDetailNode(null);
  }, [nodes, edges, pushSnapshot, setNodes, markCanvasDirty]);

  /* ── Save Plant Model — check flow issues first, then procurement, then export validation ── */
  const totalIssueCount = checkFindings.length + balanceReport.imbalances.length;

  const proceedToSave = useCallback(() => {
    setShowFlowWarning(false);
    // Always persist to cloud when user explicitly saves
    void saveCanvasData(nodes, edges, buildPlantSettings());
    dirtyVersionRef.current = 0;
    setDirtyVersion(0);
    setIsDirty(false);
    // Demo flow: skip the summary/save-prompt dialogs and go straight
    // to the Project Hub so users see the 4 module cards immediately.
    navigate(`/project-hub/${plantId || "rotterdam-rfnbo"}`);
  }, [saveCanvasData, nodes, edges, buildPlantSettings, navigate, plantId]);

  const handleSavePlantModel = useCallback(() => {
    // Demo flow: bypass the process-flow warning dialog and save directly.
    proceedToSave();
  }, [proceedToSave]);

  /* ── Auto-fill manufacturers ── */
  const handleAutoFill = useCallback((strategy: ProcurementStrategy) => {
    setNodes((nds) => {
      const updated = nds.map((n) => {
        if (n.type !== "equipment" || (n.data.manufacturer as string)) return n;
        const mfr = matchProcurement(n.data.label as string, strategy);
        if (!mfr) return n;
        return {
          ...n,
          data: { ...n.data, manufacturer: mfr.manufacturer, model: mfr.model },
        };
      });
      // Persist procurement data for the viability dashboard
      persistProcurementToPlant(plantId || "rotterdam-rfnbo", plant.name, updated, strategy);
      return updated;
    });
    // Don't close procurement dialog — it transitions to CAPEX summary step internally
  }, [setNodes, plantId, plant.name]);

  const handleProcurementSkip = useCallback(() => {
    setProcurementOpen(false);
    setShowSummary(true);
  }, []);

  /* ── Procurement Database browser ── */
  const [showProcurementDb, setShowProcurementDb] = useState(false);

  const equipmentNodes = nodes.filter((n) => n.type === "equipment");
  const carrierNodes = nodes.filter((n) => n.type === "carrier");
  const gateNodes = nodes.filter((n) => n.type === "gate");
  const inputGates = gateNodes.filter((n) => n.data.gateType === "input");
  // Bump on every carrier-color override change so legend recomputes & canvas
  // edges/bubbles re-read their resolved colors live.
  const [carrierColorVersion, setCarrierColorVersion] = useState(0);
  useEffect(() => {
    return subscribeCarrierOverrides(() => setCarrierColorVersion((v) => v + 1));
  }, []);
  const northseaFallbackLegendItems = useMemo(
    () => plantId === "northsea-hydrogen"
      ? NORTHSEA_V1_LEGEND_LABELS.map((label) => ({ label, color: getColorFromResource(label) }))
      : [],
    [plantId, carrierColorVersion],
  );
  const dynamicCarrierLegendItems = useMemo(
    () => carrierNodes
      .map((n) => {
        const label = n.data.label as string;
        return { label, color: getColorFromResource(label) };
      })
      .filter((item, index, items) => item.label && items.findIndex((candidate) => candidate.label === item.label) === index)
      .sort((a, b) => a.label.localeCompare(b.label)),
    [carrierNodes, carrierColorVersion],
  );
  const carrierLegendItems = dynamicCarrierLegendItems.length > 0
    ? dynamicCarrierLegendItems
    : northseaFallbackLegendItems;
  const outputGates = gateNodes.filter((n) => n.data.gateType === "output");

  const handleOpenExportDesign = useCallback(() => {
    const snapshotLegendItems = carrierLegendItems.length > 0
      ? carrierLegendItems
      : northseaFallbackLegendItems;

    setExportSnapshot({
      nodes,
      legendItems: snapshotLegendItems,
      signature: snapshotLegendItems.map((item) => `${item.label}:${item.color}`).join("|"),
    });
    setShowExportDesign(true);
  }, [nodes, carrierLegendItems, northseaFallbackLegendItems]);

  const handleExportDialogOpenChange = useCallback((open: boolean) => {
    setShowExportDesign(open);
    if (!open) setExportSnapshot(null);
  }, []);

  // Memoize the projected nodes/edges so React Flow doesn't see new object
  // identities for every node on every render — the renderer compares by
  // reference and re-mounts custom node components when identity changes,
  // which causes visible jank during drags.
  // NOTE: These hooks MUST be declared before any early returns below to
  // satisfy the Rules of Hooks (consistent hook count across renders).
  const projectedNodes = useMemo(() => nodes.map((n) => {
    let nodeData = n.data;
    let changed = false;
    if (n.type === "gate") {
      nodeData = { ...nodeData, isSnapped: snappedGates.has(n.id) };
      changed = true;
    }
    if (n.type === "equipment") {
      const isCritical = criticalPathNodeIds.has(n.id);
      nodeData = {
        ...nodeData,
        isCriticalPath: isCritical,
        criticalPathMode,
        operatingHours: isCritical ? effectiveOperatingHours : undefined,
      };
      changed = true;
    }
    const flashClass = connectFlashNodeId === n.id ? "node-connect-flash" : undefined;
    if (!changed && !flashClass) return n;
    return { ...n, data: nodeData, className: [n.className, flashClass].filter(Boolean).join(" ") || undefined };
  }), [nodes, snappedGates, criticalPathNodeIds, criticalPathMode, effectiveOperatingHours, connectFlashNodeId]);

  const projectedEdges = useMemo(() => balanceReport.annotatedEdges.map((edge) => ({
    ...edge,
    reconnectable: selectedEdgeId === edge.id,
    data: {
      ...edge.data,
      onUpdateFlowValue: handleUpdateEdgeFlowValue,
      onDeleteFlowValue: handleDeleteEdgeFlowValue,
      onDeleteStream: handleDeleteEdge,
      onUpdateEdgeRoute: handleUpdateEdgeRoute,
      onResetEdgeRoute: handleResetEdgeRoute,
      onOpenBatchDialog: handleOpenBatchDialog,
    },
  })), [balanceReport.annotatedEdges, selectedEdgeId, handleUpdateEdgeFlowValue, handleDeleteEdgeFlowValue, handleDeleteEdge, handleUpdateEdgeRoute, handleResetEdgeRoute, handleOpenBatchDialog]);

  if (canvasLoading) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <AppNav rightContent={<UserContextBar />} />
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <Cpu className="h-8 w-8 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Loading plant canvas…</p>
          </div>
        </div>
      </div>
    );
  }

  if (canvasError && (!canvasData || canvasData.nodes.length === 0)) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <AppNav rightContent={<UserContextBar />} />
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4 text-center max-w-md">
            <AlertTriangle className="h-10 w-10 text-muted-foreground" />
            <h2 className="text-lg font-semibold text-foreground">Unable to load canvas</h2>
            <p className="text-sm text-muted-foreground">{canvasError}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Global nav */}
      <AppNav rightContent={<UserContextBar />} />
      {/* Canvas top bar */}
      <header className="h-12 border-b border-border bg-card px-4 flex items-center justify-between shrink-0 z-10">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-sm font-semibold text-card-foreground">
              {getCollectionDisplayName(iterationMembers.length > 0 ? iterationMembers : [plant])}
            </h1>
            <p className="text-[10px] text-muted-foreground">
              <span className="text-foreground/70">{plant.variantLabel || "Plant variation"}</span>
              <span className="mx-1">·</span>
              {plant.subtitle}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleUndo}
            disabled={!canUndo}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-40 disabled:pointer-events-none"
            title="Undo last action (Ctrl+Z)"
          >
            <Undo2 className="h-3.5 w-3.5" />
            Undo
          </button>
          {mergeCandidate && (
            <button
              onClick={handleMergeEquipment}
              className="inline-flex items-center gap-1.5 rounded-md border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20 animate-in fade-in duration-200"
              title={`Merge "${mergeCandidate.first.data.label}" & "${mergeCandidate.second.data.label}"`}
            >
              <Merge className="h-3.5 w-3.5" />
              Merge Equipment
            </button>
          )}
          {unmergeCandidate && (
            <button
              onClick={handleUnmergeEquipment}
              className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/40 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-600 dark:text-amber-400 transition-colors hover:bg-amber-500/20 animate-in fade-in duration-200"
              title={`Split "${unmergeCandidate.data.label}" back into individual equipment`}
            >
              <Split className="h-3.5 w-3.5" />
              Unmerge Equipment
            </button>
          )}
          <button onClick={() => setShowSettings(true)} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
            <Settings2 className="h-3.5 w-3.5" />
            Plant Settings
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
                disabled={creatingIteration}
                title="Iterations of this plant"
              >
                {creatingIteration ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <GitBranch className="h-3.5 w-3.5" />
                )}
                Iterations
                {iterationMembers.length > 1 && (
                  <span className="ml-0.5 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                    {iterationMembers.length}
                  </span>
                )}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="w-80"
              onCloseAutoFocus={() => { setRenamingId(null); }}
            >
              <DropdownMenuLabel className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Iterations · {iterationMembers.length}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {iterationMembers.length === 0 && (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">No iterations yet.</div>
              )}
              {iterationMembers.map((m) => {
                const isCurrent = m.id === plantId;
                const isRenaming = renamingId === m.id;
                if (isRenaming) {
                  return (
                    <div
                      key={m.id}
                      className="px-2 py-1.5 flex items-center gap-1"
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.stopPropagation()}
                    >
                      <Input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") { e.preventDefault(); void handleRenameIteration(m.id, renameValue); }
                          else if (e.key === "Escape") { e.preventDefault(); setRenamingId(null); }
                        }}
                        className="h-7 text-xs flex-1 min-w-0"
                      />
                      <button
                        type="button"
                        title="Save (Enter)"
                        className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground shrink-0"
                        onClick={() => void handleRenameIteration(m.id, renameValue)}
                      >
                        <Check className="h-3.5 w-3.5 text-primary" />
                      </button>
                      <button
                        type="button"
                        title="Cancel (Esc)"
                        className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground shrink-0"
                        onClick={() => setRenamingId(null)}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  );
                }
                return (
                  <div key={m.id} className="flex items-center gap-0.5 px-1 min-w-0">
                    <button
                      type="button"
                      className={`flex-1 min-w-0 flex items-start gap-2 rounded-sm px-2 py-1.5 text-xs text-left hover:bg-accent hover:text-accent-foreground ${isCurrent ? "" : "cursor-pointer"}`}
                      onClick={() => { if (!isCurrent) navigate(`/canvas/${m.id}`); }}
                    >
                      <span className="mt-0.5 w-3.5 shrink-0">
                        {isCurrent && <Check className="h-3.5 w-3.5 text-primary" />}
                      </span>
                      <span className="flex flex-col min-w-0 flex-1">
                        <span className="font-medium text-foreground truncate">
                          {m.variantLabel || "Plant variation"}
                        </span>
                        <span className="text-[10px] text-muted-foreground truncate">
                          {getCollectionDisplayName(iterationMembers.length > 0 ? iterationMembers : [m])}
                        </span>
                      </span>
                    </button>
                    <button
                      type="button"
                      title="Rename variation"
                      className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground shrink-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenameValue(m.variantLabel || "");
                        setRenamingId(m.id);
                      }}
                    >
                      <Pencil className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      title="Delete variation"
                      disabled={iterationMembers.length <= 1}
                      className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive disabled:opacity-30 disabled:pointer-events-none shrink-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteTarget({ id: m.id, label: m.variantLabel || m.name });
                      }}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                );
              })}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-xs gap-2"
                onSelect={(e) => { e.preventDefault(); openNewIterationDialog(); }}
                disabled={creatingIteration}
              >
                <Plus className="h-3.5 w-3.5" />
                New iteration from current
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <button onClick={handleOpenExportDesign} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
            <Download className="h-3.5 w-3.5" />
            Export Design
          </button>
          
          <button onClick={() => setShowCheckPanel(true)} className="relative inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90">
            <Play className="h-3.5 w-3.5" />
            Check Process Flow
            {(checkFindings.length > 0 || !balanceReport.balanced) && (
              <Badge variant="destructive" className="absolute -top-2 -right-2 h-5 min-w-5 text-[10px] px-1 flex items-center justify-center">
                {checkFindings.length + balanceReport.imbalances.length}
              </Badge>
            )}
          </button>
          <button onClick={handleSavePlantModel} className="inline-flex items-center gap-1.5 rounded-md bg-success px-3 py-1.5 text-xs font-medium text-success-foreground transition-colors hover:bg-success/90">
            <BarChart3 className="h-3.5 w-3.5" />
            Analyze My Plant
          </button>
          <PresenceAvatars peers={presencePeers} />
        </div>
      </header>

      {/* Canvas area */}
      <div
        className="flex flex-1 overflow-hidden"
        ref={reactFlowWrapper}
        onMouseMove={(event) => {
          if (!presenceMe) return;
          const pt = rf.screenToFlowPosition({ x: event.clientX, y: event.clientY });
          publishCursor(pt.x, pt.y);
        }}
      >
        <ComponentLibrary collapsed={collapsed} onCollapse={() => setCollapsed(!collapsed)} onOpenProcurement={() => setShowProcurementDb(true)} />
        <div className="flex-1 relative">
          {criticalPathMode && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 animate-fade-in flex flex-col items-center gap-2">
              <div className="bg-amber-500 text-white text-sm font-medium px-5 py-2 rounded-xl shadow-xl flex items-center gap-3 backdrop-blur-sm ring-2 ring-amber-400/50">
                <Gauge className="h-4 w-4" />
                <span>Click equipment to toggle critical path · <strong>{criticalPathNodeIds.size}</strong> selected</span>
                <button onClick={() => setCriticalPathMode(false)} className="hover:bg-white/20 rounded-full p-0.5 transition-colors ml-1">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <button
                onClick={() => {
                  setCriticalPathMode(false);
                  setShowSettings(true);
                }}
                className="bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-semibold px-6 py-2 rounded-lg shadow-lg transition-all hover:scale-105 animate-[pulse_2s_cubic-bezier(0.4,0,0.6,1)_infinite] ring-2 ring-primary/40"
              >
                ✓ Confirm Selection
              </button>
            </div>
          )}
          <NodeIdVisibilityProvider value={showNodeIds}>
          <NodeIdDebugProvider value={debugNodeIds}>
          <LabelNormalizationProvider value={labelNormPrefs}>
          <CompactNodeProvider value={compactNodes}>
          <StraightEdgesProvider value={straightEdges}>
          <ReactFlow
            nodes={projectedNodes}
            edges={projectedEdges}
            onNodesChange={onNodesChangeTracked}
            onEdgesChange={onEdgesChangeTracked}
            onConnect={onConnect}
            onConnectStart={onConnectStart}
            onConnectEnd={onConnectEnd}
            onNodeDragStart={onNodeDragStart}
            onNodeDragStop={onNodeDragStop}
            onReconnect={onReconnect}
            onReconnectStart={onReconnectStart}
            onReconnectEnd={onReconnectEnd}
            onEdgeClick={(_, edge) => setSelectedEdgeId(edge.id)}
            onPaneClick={() => {
              setSelectedEdgeId(null);
              setEdgeContextMenu(null);
              setNodeContextMenu(null);
              setSelectedNodeIds([]);
              // Clear React Flow's internal selection so edges visually deselect
              setEdges((eds) => eds.some((e) => e.selected) ? eds.map((e) => e.selected ? { ...e, selected: false } : e) : eds);
              setNodes((nds) => nds.some((n) => n.selected) ? nds.map((n) => n.selected ? { ...n, selected: false } : n) : nds);
            }}
            onEdgeContextMenu={(event, edge) => {
              event.preventDefault();
              setSelectedEdgeId(edge.id);
              setEdgeContextMenu({ edgeId: edge.id, x: event.clientX, y: event.clientY });
            }}
            onNodeContextMenu={(event, node) => {
              if (node.type === "boundary") return;
              event.preventDefault();
              setEdgeContextMenu(null);
              setNodeContextMenu({ nodeId: node.id, nodeType: node.type ?? "", x: event.clientX, y: event.clientY });
            }}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            /* fitView removed — use one-time fit on data load instead */
            fitViewOptions={{ padding: 0.15 }}
            defaultEdgeOptions={{ type: "flowEdge", animated: false, style: { stroke: "hsl(174, 45%, 45%)", strokeWidth: 2.25 }, markerEnd: { type: MarkerType.ArrowClosed, color: "hsl(174, 45%, 45%)", width: 18, height: 18 }, data: {}, focusable: true, interactionWidth: 20 }}
            connectionLineStyle={{ stroke: "hsl(174, 45%, 45%)", strokeWidth: 2.5, opacity: 0.9 }}
            connectionLineType={straightEdges ? ConnectionLineType.Straight : ConnectionLineType.SmoothStep}
            connectionMode={ConnectionMode.Loose}
            connectionRadius={96}
            isValidConnection={(c) => !!c.source && !!c.target && c.source !== c.target}
            className={[isConnectingEdge ? "canvas-connecting" : "", isReconnectingEdge ? "canvas-reconnecting" : ""].filter(Boolean).join(" ") || undefined}
            proOptions={{ hideAttribution: true }}
            deleteKeyCode={["Backspace", "Delete"]}
            onBeforeDelete={async () => { pushSnapshot(nodes, edges); userDeleteIntent.current = true; return true; }}
            multiSelectionKeyCode="Shift"
            onSelectionChange={onSelectionChange}
            edgesFocusable
            edgesReconnectable
            onlyRenderVisibleElements={!showExportDesign}
            elevateNodesOnSelect={false}
            elevateEdgesOnSelect={false}
            nodeDragThreshold={2}
            minZoom={0.15}
            maxZoom={2.5}
          >
            <ZoomLegibilityBridge />
            <Controls className="!border-border !bg-card !shadow-sm [&>button]:!border-border [&>button]:!bg-card" />
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} className="!bg-background" />
            <PresenceCursors peers={presencePeers} />
            {alignGuides.length > 0 && (
              <ViewportPortal>
                {alignGuides.map((g, i) =>
                  g.orientation === "v" ? (
                    <div
                      key={`vg-${i}`}
                      style={{
                        position: "absolute",
                        left: g.position,
                        top: g.start,
                        width: 0,
                        height: g.end - g.start,
                        borderLeft: "1px dashed hsl(var(--primary))",
                        pointerEvents: "none",
                        zIndex: 1000,
                      }}
                    />
                  ) : (
                    <div
                      key={`hg-${i}`}
                      style={{
                        position: "absolute",
                        left: g.start,
                        top: g.position,
                        height: 0,
                        width: g.end - g.start,
                        borderTop: "1px dashed hsl(var(--primary))",
                        pointerEvents: "none",
                        zIndex: 1000,
                      }}
                    />
                  ),
                )}
              </ViewportPortal>
            )}
          </ReactFlow>
          </StraightEdgesProvider>
          </CompactNodeProvider>
          {edgeContextMenu && (
            (() => {
              const ctxEdge = edges.find((e) => e.id === edgeContextMenu.edgeId);
              const ctxMode = ((ctxEdge?.data ?? {}) as { flowMode?: "continuous" | "batch" }).flowMode ?? "continuous";
              return (
                <EdgeContextMenu
                  x={edgeContextMenu.x}
                  y={edgeContextMenu.y}
                  flowMode={ctxMode}
                  onReverse={() => handleReverseEdge(edgeContextMenu.edgeId)}
                  onDelete={() => handleDeleteEdge(edgeContextMenu.edgeId)}
                  onSwitchToBatch={() => handleSwitchToBatch(edgeContextMenu.edgeId)}
                  onSwitchToContinuous={() => handleSwitchToContinuous(edgeContextMenu.edgeId)}
                  onEditBatch={() => setBatchDialogEdgeId(edgeContextMenu.edgeId)}
                  onClose={() => setEdgeContextMenu(null)}
                />
              );
            })()
          )}
          {nodeContextMenu && (
            <NodeContextMenu
              x={nodeContextMenu.x}
              y={nodeContextMenu.y}
              nodeType={nodeContextMenu.nodeType}
              onRename={() => {
                window.dispatchEvent(
                  new CustomEvent("canvas:node-rename", { detail: { id: nodeContextMenu.nodeId } })
                );
              }}
              onEditDetails={() => {
                const node = nodes.find((n) => n.id === nodeContextMenu.nodeId);
                if (!node) return;
                setDetailNode(node);
                setDetailOpen(true);
              }}
              onDuplicate={() => {
                const node = nodes.find((n) => n.id === nodeContextMenu.nodeId);
                if (!node) return;
                pushSnapshot(nodes, edges);
                const newId = genNodeId();
                const copy: Node = {
                  ...node,
                  id: newId,
                  position: { x: (node.position?.x ?? 0) + 40, y: (node.position?.y ?? 0) + 40 },
                  data: { ...(node.data as Record<string, unknown>), id: newId },
                  selected: false,
                };
                setNodes((nds) => [...nds, copy]);
                markCanvasDirty();
              }}
              onDelete={() => {
                rf.deleteElements({ nodes: [{ id: nodeContextMenu.nodeId }] });
              }}
              onClose={() => setNodeContextMenu(null)}
            />
          )}
          </LabelNormalizationProvider>
          </NodeIdDebugProvider>
          </NodeIdVisibilityProvider>

          {/* Autosave status pill */}
          <div className="absolute bottom-4 left-16 z-10 inline-flex items-center gap-1.5 rounded-full border border-border bg-card/95 backdrop-blur-sm shadow-sm px-2.5 py-1 text-[11px] font-medium">
            {saving ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin text-primary" />
                <span className="text-muted-foreground">Saving changes…</span>
              </>
            ) : isDirty ? (
              <>
                <Cloud className="h-3 w-3 text-amber-500" />
                <span className="text-muted-foreground">Unsaved changes</span>
              </>
            ) : lastSavedAt ? (
              <button
                type="button"
                onClick={() => setShowVersionHistory(true)}
                className="inline-flex items-center gap-1.5 hover:text-foreground transition-colors cursor-pointer"
                title="View version history"
              >
                <CheckCircle2 className="h-3 w-3 text-success" />
                <span className="text-muted-foreground hover:text-foreground underline-offset-2 hover:underline">
                  Change saved · {lastSavedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
              </button>
            ) : (
              <>
                <Cloud className="h-3 w-3 text-muted-foreground" />
                <span className="text-muted-foreground">Auto-save enabled</span>
              </>
            )}
          </div>

          {/* Stream Color Legend, dynamic from actual carrier nodes */}
          {(() => {
            return showLegend ? (
              <div className="absolute bottom-4 right-4 z-10 rounded-lg border border-border bg-card/95 backdrop-blur-sm shadow-lg p-3 w-44 max-h-60 overflow-y-auto">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-[10px] font-semibold text-foreground uppercase tracking-wider">Stream Colors</p>
                  <button onClick={() => setShowLegend(false)} className="h-5 w-5 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                    <X className="h-3 w-3" />
                  </button>
                </div>
                <div className="space-y-1">
                  {carrierLegendItems.map((item) => (
                    <div key={item.label} className="flex items-center gap-2">
                      <span className="w-5 h-2 rounded-sm shrink-0" style={{ backgroundColor: item.color }} />
                      <span className="text-[10px] text-muted-foreground">{item.label}</span>
                    </div>
                  ))}
                  {carrierLegendItems.length === 0 && (
                    <span className="text-[10px] text-muted-foreground italic">No carriers on canvas</span>
                  )}
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowLegend(true)}
                className="absolute bottom-4 right-4 z-10 rounded-lg border border-border bg-card/95 backdrop-blur-sm shadow-sm px-3 py-2 flex items-center gap-2 hover:bg-accent transition-colors"
              >
                <span className="flex gap-0.5">
                  {carrierLegendItems.slice(0, 4).map((item) => (
                    <span key={item.label} className="w-3 h-2 rounded-sm" style={{ backgroundColor: item.color }} />
                  ))}
                </span>
                <span className="text-[10px] font-medium text-muted-foreground">Legend</span>
              </button>
            );
          })()}

        </div>
      </div>

      {/* Component Detail Dialog */}
      <ComponentDetailDialog
        open={detailOpen}
        onOpenChange={setDetailOpen}
        node={detailNode}
        onSave={handleDetailSave}
        isCriticalPath={!!detailNode && criticalPathNodeIds.has(detailNode.id)}
        plantAvailability={plantAvailability}
        scheduledOperatingHours={plantHoursYear}
        allNodes={nodes}
        allEdges={edges}
        plantSlug={plantId || ""}
      />

      {/* Procurement Warning Dialog */}
      <ProcurementWarningDialog
        open={procurementOpen}
        onOpenChange={setProcurementOpen}
        incompleteNodes={incompleteEquipment}
        allNodes={nodes}
        plantName={plant.name}
        onAutoFill={handleAutoFill}
        onSkip={handleProcurementSkip}
      />

      {/* Rule 9 Check Panel */}
      <CheckFindingsPanel
        open={showCheckPanel}
        onOpenChange={setShowCheckPanel}
        balanceReport={balanceReport}
      />

      {/* Flow Issues Warning Dialog */}
      <Dialog open={showFlowWarning} onOpenChange={setShowFlowWarning}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-5 w-5 text-warning" />
              Process Flow Issues Detected
            </DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground mt-2">
              Your plant model has <span className="font-semibold text-foreground">{totalIssueCount} issue{totalIssueCount !== 1 ? "s" : ""}</span> that
              should be resolved before saving. These include mass/energy balance violations
              and equipment capacity warnings.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 mt-2">
            <p className="text-xs text-muted-foreground">
              Use <span className="font-medium text-foreground">Check Process Flow</span> to review and fix
              all findings before exporting your plant model.
            </p>
          </div>
          <div className="flex gap-3 mt-4">
            <button
              onClick={() => {
                setShowFlowWarning(false);
                setShowCheckPanel(true);
              }}
              className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <Play className="h-3.5 w-3.5" />
              Review Issues
            </button>
            <button
              onClick={proceedToSave}
              className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              Skip for Now
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Plant Settings Dialog (popup with 4 tabs) */}
      <PlantSettingsDialog
        open={showSettings}
        onOpenChange={setShowSettings}
        project={plant}
        hoursYear={plantHoursYear}
        onHoursYearChange={setPlantHoursYear}
        plantAvailability={plantAvailability}
        onPlantAvailabilityChange={setPlantAvailability}
        criticalPathMode={criticalPathMode}
        onToggleCriticalPathMode={() => setCriticalPathMode((v) => !v)}
        criticalPathNodeIds={criticalPathNodeIds}
        onCriticalPathChange={setCriticalPathNodeIds}
        equipmentNodes={nodes.filter((n) => n.type === "equipment")}
        carrierNodes={nodes.filter((n) => n.type === "carrier")}
        listVersions={listVersions}
        restoreVersion={restoreVersion}
        onRestored={(restored) => {
          setNodes(restored.nodes);
          setEdges(restored.edges);
          if (restored.plantSettings) {
            setPlantHoursYear(restored.plantSettings.hoursYear);
            setPlantAvailability(restored.plantSettings.plantAvailability);
            setCriticalPathNodeIds(new Set(restored.plantSettings.criticalPathNodeIds));
            if (restored.plantSettings.boundaryPadding) {
              manualPadding.current = { ...restored.plantSettings.boundaryPadding };
            }
          }
          dirtyVersionRef.current = 0;
          setDirtyVersion(0);
          setIsDirty(false);
        }}
        showNodeIds={showNodeIds}
        onShowNodeIdsChange={(v) => setShowNodeIds(v)}
        debugNodeIds={debugNodeIds}
        onDebugNodeIdsChange={(v) => setDebugNodeIds(v)}
        layoutOrientation={layoutOrientation}
        onLayoutOrientationChange={setLayoutOrientation}
        compactNodes={compactNodes}
        onCompactNodesChange={setCompactNodes}
        straightEdges={straightEdges}
        onStraightEdgesChange={setStraightEdges}
        labelNormPrefs={labelNormPrefs}
        onLabelNormPrefChange={updateLabelNormPref}
        onResetLabelNormPrefs={resetLabelNormPrefs}
        allNodes={nodes}
        retiredDisplayIds={canvasData?.retiredDisplayIds ?? []}
      />

      {/* Version History */}
      <VersionHistoryDialog
        open={showVersionHistory}
        onOpenChange={setShowVersionHistory}
        listVersions={listVersions}
        restoreVersion={restoreVersion}
        onRestored={(restored) => {
          setNodes(restored.nodes);
          setEdges(restored.edges);
          if (restored.plantSettings) {
            setPlantHoursYear(restored.plantSettings.hoursYear);
            setPlantAvailability(restored.plantSettings.plantAvailability);
            setCriticalPathNodeIds(new Set(restored.plantSettings.criticalPathNodeIds));
            if (restored.plantSettings.boundaryPadding) {
              manualPadding.current = { ...restored.plantSettings.boundaryPadding };
            }
          }
          dirtyVersionRef.current = 0;
          setDirtyVersion(0);
          setIsDirty(false);
        }}
      />

      {/* Export Design Dialog (PNG/PDF), key forces fresh mount each open */}
      {showExportDesign && exportSnapshot && (
        <PlantExportDialog
          key={`export-${plantId}-${exportSnapshot.signature}`}
          open={showExportDesign}
          onOpenChange={handleExportDialogOpenChange}
          plantName={plant.name}
          companyName={plant.subtitle}
          plantCapacity={plant.capacity}
          nodes={exportSnapshot.nodes}
          legendItems={exportSnapshot.legendItems}
        />
      )}

      {/* Procurement Database Browser */}
      <SupplierPickerDialog
        open={showProcurementDb}
        onOpenChange={setShowProcurementDb}
        equipmentLabel=""
        onSelect={() => {}}
        onAddToCanvas={(selection) => {
          const newId = genNodeId();
          // Place in center of visible canvas
          const bounds = reactFlowWrapper.current?.getBoundingClientRect();
          const position = {
            x: (bounds ? bounds.width / 2 : 400) - (collapsed ? 0 : 128),
            y: (bounds ? bounds.height / 2 : 300) - 28,
          };
          pushSnapshot(nodes, edges);
          const baseNode: Node = {
            id: newId,
            type: "equipment",
            position,
            data: { label: selection.model, id: newId },
          };
          const newNode = applyProcurementToNode(baseNode, selection);
          setNodes((nds) => [...nds, newNode]);
          markCanvasDirty();
        }}
      />

      {/* Batch flow configuration dialog */}
      {batchDialogEdgeId && (() => {
        const edge = edges.find((e) => e.id === batchDialogEdgeId);
        if (!edge) return null;
        const d = (edge.data ?? {}) as { batch?: BatchFlowConfig; flowUnit?: string; flowValue?: number };
        const sourceNode = nodes.find((n) => n.id === edge.source);
        const targetNode = nodes.find((n) => n.id === edge.target);
        const carrierNode = [sourceNode, targetNode].find((n) => n?.type === "carrier");
        const carrierLabel = (carrierNode?.data as { label?: string } | undefined)?.label;
        const carrierColor = carrierLabel ? getColorFromResource(carrierLabel) ?? undefined : undefined;
        return (
          <BatchFlowDialog
            open={!!batchDialogEdgeId}
            onOpenChange={(o) => { if (!o) setBatchDialogEdgeId(null); }}
            initialConfig={d.batch ?? defaultBatchConfig(d.flowValue, d.flowUnit)}
            carrierLabel={carrierLabel}
            carrierColor={carrierColor}
            sourceLabel={(sourceNode?.data as { label?: string } | undefined)?.label ?? edge.source}
            targetLabel={(targetNode?.data as { label?: string } | undefined)?.label ?? edge.target}
            flowUnit={d.flowUnit ?? "kg/h"}
            onSave={(config) => { handleUpdateBatch(batchDialogEdgeId, config); }}
            onConvertToContinuous={(rate) => {
              handleSwitchToContinuous(batchDialogEdgeId);
              handleUpdateEdgeFlowValue(batchDialogEdgeId, rate, d.flowUnit ?? "kg/h");
              setBatchDialogEdgeId(null);
            }}
          />
        );
      })()}

      {/* Save Plant Model Summary Dialog */}
      <Dialog open={showSummary} onOpenChange={setShowSummary}>

        <DialogContent className="max-w-2xl max-h-[85vh] p-0 overflow-hidden flex flex-col">
          <div className="px-6 py-5 border-b border-border bg-card/80">
            <DialogHeader>
              <DialogTitle className="text-base font-semibold flex items-center gap-2.5">
                <span className="h-9 w-9 rounded-lg bg-success/10 flex items-center justify-center">
                  <CheckCircle2 className="h-5 w-5 text-success" />
                </span>
                Plant Model Saved
              </DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground mt-1">
                {plant.name}, {plant.subtitle}
              </DialogDescription>
            </DialogHeader>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4 space-y-4">
            {/* Plant overview stats */}
            <div className="grid grid-cols-4 gap-3">
              <div className="rounded-lg border border-border p-3 text-center">
                <Cpu className="h-4 w-4 text-primary mx-auto mb-1" />
                <p className="text-lg font-mono font-bold text-card-foreground">{equipmentNodes.length}</p>
                <p className="text-[10px] text-muted-foreground">Equipment</p>
              </div>
              <div className="rounded-lg border border-border p-3 text-center">
                <Zap className="h-4 w-4 text-success mx-auto mb-1" />
                <p className="text-lg font-mono font-bold text-card-foreground">{carrierNodes.length}</p>
                <p className="text-[10px] text-muted-foreground">Carriers</p>
              </div>
              <div className="rounded-lg border border-border p-3 text-center">
                <ArrowRightFromLine className="h-4 w-4 text-warning mx-auto mb-1" />
                <p className="text-lg font-mono font-bold text-card-foreground">{gateNodes.length}</p>
                <p className="text-[10px] text-muted-foreground">Gates</p>
              </div>
              <div className="rounded-lg border border-border p-3 text-center">
                <DollarSign className="h-4 w-4 text-primary mx-auto mb-1" />
                <p className="text-lg font-mono font-bold text-card-foreground">
                  {(() => {
                    let total = 0;
                    for (const n of equipmentNodes) {
                      const entry = getProcurementEntry(n.data.label as string);
                      if (entry) {
                        const qty = entry.plantScaleQty ?? 1;
                        total += entry.bestPrice.priceEur * qty;
                      }
                    }
                    if (total >= 1_000_000) return `€${(total / 1_000_000).toFixed(0)}M`;
                    if (total >= 1_000) return `€${(total / 1_000).toFixed(0)}k`;
                    return `€${total}`;
                  })()}
                </p>
                <p className="text-[10px] text-muted-foreground">Est. CAPEX</p>
              </div>
            </div>

            {/* Equipment with CAPEX breakdown */}
            <div className="space-y-2">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Equipment & CAPEX Breakdown</p>
              <div className="space-y-1.5">
                {equipmentNodes.map((n) => {
                  const entry = getProcurementEntry(n.data.label as string);
                  const opt = entry?.bestPrice;
                  const qty = entry?.plantScaleQty ?? 1;
                  const scaledPrice = opt ? opt.priceEur * qty : 0;
                  return (
                    <div key={n.id} className="flex items-center gap-3 rounded-lg border border-border bg-card p-3">
                      <span className="h-8 w-8 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
                        <Settings className="h-3.5 w-3.5 text-primary" />
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-foreground truncate">{n.data.label as string}</p>
                        <p className="text-[10px] text-muted-foreground">
                          {n.data.manufacturer
                            ? `${n.data.manufacturer as string}${n.data.model ? ` · ${n.data.model}` : ""}`
                            : opt
                              ? `${opt.manufacturer} · ${opt.model}`
                              : "No supplier assigned"}
                          {qty > 1 ? ` (×${qty})` : ""}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        {scaledPrice > 0 ? (
                          <>
                            <p className="text-sm font-mono font-bold text-primary">
                              {scaledPrice >= 1_000_000 ? `€${(scaledPrice / 1_000_000).toFixed(1)}M` : scaledPrice >= 1_000 ? `€${(scaledPrice / 1_000).toFixed(0)}k` : `€${scaledPrice}`}
                            </p>
                            <p className="text-[10px] text-muted-foreground">{opt?.priceDisplay}</p>
                          </>
                        ) : (
                          <p className="text-[10px] text-muted-foreground">–</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Quick Insights */}
            <div className="rounded-xl border border-border bg-muted/30 p-4 space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Quick Insights</p>
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg bg-card border border-border p-3 text-center">
                  <p className="text-[10px] text-muted-foreground">Avg. Lead Time</p>
                  <p className="text-lg font-mono font-bold text-foreground">
                    {(() => {
                      const leads: number[] = [];
                      for (const n of equipmentNodes) {
                        const entry = getProcurementEntry(n.data.label as string);
                        if (entry) leads.push(entry.bestPrice.leadTimeMonths);
                      }
                      return leads.length > 0 ? (leads.reduce((a, b) => a + b, 0) / leads.length).toFixed(0) : "–";
                    })()}
                    <span className="text-xs font-normal text-muted-foreground ml-0.5">mo</span>
                  </p>
                </div>
                <div className="rounded-lg bg-card border border-border p-3 text-center">
                  <p className="text-[10px] text-muted-foreground">Avg. TRL</p>
                  <p className="text-lg font-mono font-bold text-foreground">
                    {(() => {
                      const trls: number[] = [];
                      for (const n of equipmentNodes) {
                        const entry = getProcurementEntry(n.data.label as string);
                        if (entry) trls.push(entry.bestPrice.trl);
                      }
                      return trls.length > 0 ? (trls.reduce((a, b) => a + b, 0) / trls.length).toFixed(1) : "–";
                    })()}
                  </p>
                </div>
                <div className="rounded-lg bg-card border border-border p-3 text-center">
                  <p className="text-[10px] text-muted-foreground">Suppliers</p>
                  <p className="text-lg font-mono font-bold text-foreground">
                    {(() => {
                      const mfrs = new Set<string>();
                      for (const n of equipmentNodes) {
                        const entry = getProcurementEntry(n.data.label as string);
                        if (entry) mfrs.add(entry.bestPrice.manufacturer);
                      }
                      return mfrs.size;
                    })()}
                    <span className="text-xs font-normal text-muted-foreground ml-0.5">unique</span>
                  </p>
                </div>
              </div>
            </div>

            {/* Inputs & Outputs */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Inputs</p>
                {inputGates.map((n) => (
                  <div key={n.id} className="text-xs text-card-foreground rounded-md bg-primary/5 border border-primary/20 px-2.5 py-1.5">
                    {n.data.label as string}
                  </div>
                ))}
              </div>
              <div className="space-y-1.5">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Outputs</p>
                {outputGates.map((n) => (
                  <div key={n.id} className="text-xs text-card-foreground rounded-md bg-warning-soft border border-warning/20 px-2.5 py-1.5">
                    {n.data.label as string}
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <span>{edges.length} connections</span>
              <span>·</span>
              <span>{nodes.filter((n) => n.type !== "boundary").length} total components</span>
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-border bg-muted/20 flex items-center gap-3 shrink-0">
            <button onClick={() => setShowSummary(false)} className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border px-4 py-2.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
              Continue Editing
            </button>
            <div className="flex-1" />
            <button onClick={() => navigate(`/project-hub/${plantId || "rotterdam-rfnbo"}`)} className="inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90">
              Go to Project Hub
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Save confirmation prompt */}
      <SaveConfirmDialog
        open={showSavePrompt}
        context="canvas changes"
        onSave={() => {
          persistCanvas();
          setShowSavePrompt(false);
          if (pendingNavigation.current) {
            const url = pendingNavigation.current;
            pendingNavigation.current = null;
            guardProceed();
            navigate(url);
          } else {
            setShowSummary(true);
          }
        }}
        onDiscard={() => {
          setIsDirty(false);
          setShowSavePrompt(false);
          if (pendingNavigation.current) {
            const url = pendingNavigation.current;
            pendingNavigation.current = null;
            guardProceed();
            navigate(url);
          } else {
            setShowSummary(true);
          }
        }}
        onCancel={() => {
          setShowSavePrompt(false);
          pendingNavigation.current = null;
          guardReset();
        }}
      />

      {/* Name-new-iteration dialog */}
      <Dialog open={newIterDialogOpen} onOpenChange={(o) => { if (!creatingIteration) setNewIterDialogOpen(o); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Name this plant variation</DialogTitle>
            <DialogDescription>
              A new variation will be created from the current canvas. You can edit it independently from the others.
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Input
              autoFocus
              value={newIterName}
              onChange={(e) => setNewIterName(e.target.value)}
              placeholder="Plant variation #2"
              onKeyDown={(e) => {
                if (e.key === "Enter") { e.preventDefault(); void handleCreateIteration(newIterName); }
              }}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setNewIterDialogOpen(false)} disabled={creatingIteration}>Cancel</Button>
            <Button onClick={() => void handleCreateIteration(newIterName)} disabled={creatingIteration}>
              {creatingIteration ? (<><Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />Creating…</>) : "Create variation"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete variation confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => { if (!o && !deletingIteration) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this plant variation?</AlertDialogTitle>
            <AlertDialogDescription>
              "{deleteTarget?.label}" and all of its version history will be permanently removed. Other variations in this collection are not affected.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingIteration}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => { e.preventDefault(); void confirmDeleteIteration(); }}
              disabled={deletingIteration}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deletingIteration ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

const PlantCanvas = () => {
  const { plantId } = useParams();
  const plant = getProjectOrDefault(plantId);
  const { canAccess } = useProjectAccess();

  if (!canAccess(plant.projectGroupId)) {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <AppNav rightContent={<UserContextBar />} />
        <AccessRestricted projectName={plant.name} />
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <PlantCanvasInner />
    </ReactFlowProvider>
  );
};

export default PlantCanvas;
