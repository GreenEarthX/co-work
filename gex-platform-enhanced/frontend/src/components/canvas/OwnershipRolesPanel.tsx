/**
 * OwnershipRolesPanel — RACI-like role assignment for plant components.
 * Persists assignments to localStorage with audit trail.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { Badge } from "@/components/ui/Badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  AlertTriangle,
  Building2,
  Check,
  ChevronDown,
  ChevronRight,
  Crown,
  Eye,
  FileUp,
  Info,
  Pencil,
  RotateCcw,
  Send,
  ShieldCheck,
  Upload,
  UserPlus,
  X,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";

/* ── Types ── */
interface TeamMember {
  user_id: string;
  name: string;
  email: string;
  global_role: string;
  organization: string;
  is_active: boolean;
}

export interface RoleAssignment {
  user_id: string;
  assigned_at: string;
  assigned_by: string;
}

export type OwnershipType = "Internal" | "External" | "Hybrid";

export type ValidationStatus = "Draft" | "Under Review" | "Validated";

interface OwnershipTypeLog {
  value: OwnershipType;
  changed_at: string;
  changed_by: string;
}

interface ValidationStatusLog {
  from: ValidationStatus;
  to: ValidationStatus;
  changed_at: string;
  changed_by: string;
  reason?: string;
}

export interface AuditLogEntry {
  timestamp: string;
  performed_by: string;
  action: string;
  category:
    | "role_assignment"
    | "role_change"
    | "status_transition"
    | "ownership_type"
    | "certification"
    | "system"
    | "field_edit"
    | "procurement"
    | "lifecycle";
  old_value?: string;
  new_value?: string;
  details?: string;
}

export interface ComponentOwnership {
  component_id: string;
  accountable: RoleAssignment | null;
  responsible: RoleAssignment | null;
  editors: RoleAssignment[];
  viewers: RoleAssignment[];
  ownership_type: OwnershipType;
  ownership_type_log: OwnershipTypeLog[];
  certification_file_name: string | null;
  certification_uploaded_at: string | null;
  validation_status: ValidationStatus;
  validation_status_log: ValidationStatusLog[];
  last_validated_at: string | null;
  last_validated_by: string | null;
  submitted_for_review_by: string | null;
  audit_log: AuditLogEntry[];
  /** When true, require two distinct approvers (Primary + Co-Approver). */
  four_eyes_enabled?: boolean;
}

const STORAGE_KEY_TEAM = "gex_team_members";
const STORAGE_KEY_OWNERSHIP = "gex_component_ownership";

const SEED_TEAM: TeamMember[] = [
  { user_id: "u-001", name: "Jan van der Berg", email: "jan@greenearthx.com", global_role: "Head of Engineering", organization: "", is_active: true },
  { user_id: "u-002", name: "Sophie Müller", email: "sophie.muller@greenearthx.com", global_role: "Manager", organization: "", is_active: true },
  { user_id: "u-003", name: "Ahmed El-Sayed", email: "ahmed@greenearthx.com", global_role: "Engineer", organization: "", is_active: true },
  { user_id: "u-004", name: "Lena Johansson", email: "lena@greenearthx.com", global_role: "Technician", organization: "", is_active: true },
  { user_id: "u-005", name: "Carlos Ferreira", email: "carlos@dnv.com", global_role: "External Partner", organization: "DNV GL", is_active: true },
];

function loadTeam(): TeamMember[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_TEAM);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch { /* ignore */ }
  // Auto-seed team members so assignment works everywhere
  localStorage.setItem(STORAGE_KEY_TEAM, JSON.stringify(SEED_TEAM));
  return SEED_TEAM;
}

function loadOwnership(componentId: string): ComponentOwnership {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_OWNERSHIP);
    if (raw) {
      const all: Record<string, ComponentOwnership> = JSON.parse(raw);
      if (all[componentId]) {
        // Migrate older records missing new fields
        const o = all[componentId];
        return {
          ...o,
          ownership_type: o.ownership_type ?? "Internal",
          ownership_type_log: o.ownership_type_log ?? [],
          certification_file_name: o.certification_file_name ?? null,
          certification_uploaded_at: o.certification_uploaded_at ?? null,
          validation_status: o.validation_status ?? "Draft",
          validation_status_log: o.validation_status_log ?? [],
          last_validated_at: o.last_validated_at ?? null,
          last_validated_by: o.last_validated_by ?? null,
          submitted_for_review_by: o.submitted_for_review_by ?? null,
          audit_log: o.audit_log ?? [],
          four_eyes_enabled: o.four_eyes_enabled ?? true,
        };
      }
    }
  } catch { /* ignore */ }
  return {
    component_id: componentId,
    accountable: null,
    responsible: null,
    editors: [],
    viewers: [],
    ownership_type: "Internal",
    ownership_type_log: [],
    certification_file_name: null,
    certification_uploaded_at: null,
    validation_status: "Draft",
    validation_status_log: [],
    last_validated_at: null,
    last_validated_by: null,
    submitted_for_review_by: null,
    audit_log: [],
    four_eyes_enabled: true,
  };
}

function saveOwnership(ownership: ComponentOwnership) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_OWNERSHIP);
    const all: Record<string, ComponentOwnership> = raw ? JSON.parse(raw) : {};
    all[ownership.component_id] = ownership;
    localStorage.setItem(STORAGE_KEY_OWNERSHIP, JSON.stringify(all));
  } catch { /* ignore */ }
}

/** Push an in-app notification stub for a newly-assigned user. */
const STORAGE_KEY_NOTIFICATIONS = "gex_role_notifications";
function pushAssignmentNotification(payload: {
  user_id: string;
  component_id: string;
  role: string;
  assigned_by: string;
}) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_NOTIFICATIONS);
    const list = raw ? (JSON.parse(raw) as unknown[]) : [];
    list.push({ ...payload, created_at: new Date().toISOString(), read: false });
    localStorage.setItem(STORAGE_KEY_NOTIFICATIONS, JSON.stringify(list));
  } catch { /* ignore */ }
}

function getCurrentUserId(): string {
  try {
    const raw = localStorage.getItem("gex_auth_user");
    if (raw) {
      const user = JSON.parse(raw);
      return user.id || "system";
    }
  } catch { /* ignore */ }
  return "system";
}

function getCurrentUserRole(): string {
  try {
    const raw = localStorage.getItem("gex_auth_user");
    if (raw) {
      const user = JSON.parse(raw);
      return user.role || "";
    }
  } catch { /* ignore */ }
  return "";
}

/** Append an audit log entry and save */
function appendAuditLog(
  ownership: ComponentOwnership,
  entry: Omit<AuditLogEntry, "timestamp" | "performed_by">,
): ComponentOwnership {
  const logEntry: AuditLogEntry = {
    ...entry,
    timestamp: new Date().toISOString(),
    performed_by: getCurrentUserId(),
  };
  return { ...ownership, audit_log: [...(ownership.audit_log || []), logEntry] };
}

/** Check whether editing should be unlocked */
export function isEditingUnlocked(componentId: string): boolean {
  const o = loadOwnership(componentId);
  return !!(o.accountable && o.responsible);
}

/** Check if certification is required but missing */
export function isCertificationRequired(componentId: string): boolean {
  const o = loadOwnership(componentId);
  return (o.ownership_type === "External" || o.ownership_type === "Hybrid") && !o.certification_file_name;
}

/** Get validation status for a component */
export function getValidationStatus(componentId: string): ValidationStatus {
  return loadOwnership(componentId).validation_status;
}

/** Get full ownership data for a component (for export validation) */
export function getComponentOwnership(componentId: string): ComponentOwnership {
  return loadOwnership(componentId);
}

/** Get audit log for a component */
export function getAuditLog(componentId: string): AuditLogEntry[] {
  return loadOwnership(componentId).audit_log || [];
}

/** Append a component event to the audit log (lifecycle, edit, procurement, …). */
export function logComponentEvent(
  componentId: string,
  entry: Omit<AuditLogEntry, "timestamp" | "performed_by">,
): void {
  const current = loadOwnership(componentId);
  const updated = appendAuditLog(current, entry);
  saveOwnership(updated);
  try {
    window.dispatchEvent(new CustomEvent("gex:audit-log-updated", { detail: { componentId } }));
  } catch { /* ignore */ }
}

/** Check if accountable person is deactivated */
export function isAccountableDeactivated(componentId: string): { deactivated: boolean; warning: string } {
  const o = loadOwnership(componentId);
  if (!o.accountable) return { deactivated: false, warning: "" };
  const allTeam = loadTeam();
  const member = allTeam.find((m) => m.user_id === o.accountable!.user_id);
  if (!member || !member.is_active) {
    const name = member?.name ?? "Unknown";
    return {
      deactivated: true,
      warning: `Component has no active Accountable. ${name} has been deactivated. A system administrator must reassign.`,
    };
  }
  return { deactivated: false, warning: "" };
}

/** Check if current user is a system administrator */
export function isSystemAdmin(): boolean {
  const role = getCurrentUserRole();
  return role === "System Administrator" || role === "Admin";
}

/** No-op kept for backwards compatibility — Locked status has been removed. */
export function lockComponent(_componentId: string): void {
  /* intentionally empty */
}

/** Load team members (for export dialog) */
export function getTeamMembers() {
  return loadTeam().filter((m) => m.is_active);
}

/** Validation status display config */
export const VALIDATION_STATUS_CONFIG: Record<ValidationStatus, { label: string; color: string; bg: string; border: string }> = {
  Draft: { label: "Draft", color: "text-muted-foreground", bg: "bg-muted", border: "border-border" },
  "Under Review": { label: "Under Review", color: "text-warning", bg: "bg-warning/10", border: "border-warning/30" },
  Validated: { label: "Validated", color: "text-success", bg: "bg-success/10", border: "border-success/30" },
};

const OWNERSHIP_TYPES: { value: OwnershipType; label: string; description: string; color: string }[] = [
  { value: "Internal", label: "Internal", description: "Owned by the internal engineering team", color: "bg-primary/10 text-primary border-primary/30" },
  { value: "External", label: "External", description: "Data from a third party, certification required", color: "bg-warning/10 text-warning border-warning/30" },
  { value: "Hybrid", label: "Hybrid", description: "Partially internal, partially external, certification required", color: "bg-accent text-accent-foreground border-accent-foreground/20" },
];

/* ── Component ── */
interface Props {
  componentId: string;
}

const OwnershipRolesPanel = ({ componentId }: Props) => {
  const [ownership, setOwnership] = useState<ComponentOwnership>(() => loadOwnership(componentId));
  const allTeamMembers = useMemo(() => loadTeam(), []);
  const team = useMemo(() => allTeamMembers.filter((m) => m.is_active), [allTeamMembers]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [statusOpen, setStatusOpen] = useState(false);
  const [ownershipOpen, setOwnershipOpen] = useState(false);

  // Detect deactivated accountable
  const accountableCheck = useMemo(() => {
    if (!ownership.accountable) return { deactivated: false, warning: "" };
    const member = allTeamMembers.find((m) => m.user_id === ownership.accountable!.user_id);
    if (!member || !member.is_active) {
      const name = member?.name ?? "Unknown";
      return {
        deactivated: true,
        warning: `${name} has been deactivated. A system administrator must reassign the Accountable role.`,
      };
    }
    return { deactivated: false, warning: "" };
  }, [ownership.accountable, allTeamMembers]);

  // Auto-assign Head of Engineering as Accountable on first mount if empty
  useEffect(() => {
    if (!ownership.accountable) {
      const hoe = team.find((m) => m.global_role === "Head of Engineering");
      if (hoe) {
        let updated: ComponentOwnership = {
          ...ownership,
          accountable: {
            user_id: hoe.user_id,
            assigned_at: new Date().toISOString(),
            assigned_by: "system",
          },
        };
        updated = appendAuditLog(updated, {
          action: "Accountable auto-assigned",
          category: "role_assignment",
          new_value: hoe.name,
          details: "Auto-assigned Head of Engineering on component creation",
        });
        setOwnership(updated);
        saveOwnership(updated);
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const getMemberName = useCallback(
    (userId: string) => allTeamMembers.find((m) => m.user_id === userId)?.name ?? "Unknown",
    [allTeamMembers],
  );

  const getMember = useCallback(
    (userId: string) => allTeamMembers.find((m) => m.user_id === userId),
    [allTeamMembers],
  );

  const addMulti = (role: "editors" | "viewers", userId: string) => {
    if (ownership[role].some((a) => a.user_id === userId)) return;
    const assignment: RoleAssignment = {
      user_id: userId,
      assigned_at: new Date().toISOString(),
      assigned_by: getCurrentUserId(),
    };
    let updated = { ...ownership, [role]: [...ownership[role], assignment] };
    updated = appendAuditLog(updated, {
      action: `${role.slice(0, -1).charAt(0).toUpperCase() + role.slice(1, -1)} added`,
      category: "role_assignment",
      new_value: getMemberName(userId),
    });
    setOwnership(updated);
    saveOwnership(updated);
    pushAssignmentNotification({
      user_id: userId,
      component_id: ownership.component_id,
      role: role.slice(0, -1),
      assigned_by: getCurrentUserId(),
    });
    toast({ title: "Role assigned", description: `${getMemberName(userId)} added as ${role.slice(0, -1)}.` });
  };

  const removeMulti = (role: "editors" | "viewers", userId: string) => {
    let updated = { ...ownership, [role]: ownership[role].filter((a) => a.user_id !== userId) };
    updated = appendAuditLog(updated, {
      action: `${role.slice(0, -1).charAt(0).toUpperCase() + role.slice(1, -1)} removed`,
      category: "role_change",
      old_value: getMemberName(userId),
    });
    setOwnership(updated);
    saveOwnership(updated);
  };

  /* ── Approvers (unified) ──
   * UI presents Accountable + Responsible as a single "Approvers" list.
   * Slot mapping:
   *   - 1st approver added → accountable
   *   - 2nd approver added → responsible (only when four-eyes is enabled)
   *   - When four-eyes is OFF, responsible mirrors accountable so existing
   *     export / four-eyes downstream logic keeps a single signer.
   */
  const approvers: RoleAssignment[] = useMemo(() => {
    const list: RoleAssignment[] = [];
    if (ownership.accountable) list.push(ownership.accountable);
    if (
      ownership.responsible &&
      ownership.responsible.user_id !== ownership.accountable?.user_id
    ) {
      list.push(ownership.responsible);
    }
    return list;
  }, [ownership.accountable, ownership.responsible]);

  const fourEyesOn = ownership.four_eyes_enabled !== false;

  const setFourEyes = (enabled: boolean) => {
    let updated: ComponentOwnership = { ...ownership, four_eyes_enabled: enabled };
    if (!enabled && updated.accountable) {
      // Mirror accountable into responsible to keep downstream checks happy.
      updated.responsible = { ...updated.accountable };
    }
    if (!enabled && updated.responsible && updated.accountable && updated.responsible.user_id !== updated.accountable.user_id) {
      updated.responsible = { ...updated.accountable };
    }
    updated = appendAuditLog(updated, {
      action: enabled ? "Four-eyes principle enabled" : "Four-eyes principle disabled",
      category: "system",
    });
    setOwnership(updated);
    saveOwnership(updated);
    toast({
      title: enabled ? "Four-eyes enabled" : "Four-eyes disabled",
      description: enabled
        ? "A second distinct approver is now required to validate."
        : "A single approver can now validate this component.",
    });
  };

  const addApprover = (userId: string) => {
    if (approvers.some((a) => a.user_id === userId)) return;
    const assignment: RoleAssignment = {
      user_id: userId,
      assigned_at: new Date().toISOString(),
      assigned_by: getCurrentUserId(),
    };
    let updated: ComponentOwnership = { ...ownership };
    if (!updated.accountable) {
      updated.accountable = assignment;
      if (!fourEyesOn) updated.responsible = assignment;
    } else if (fourEyesOn && (!updated.responsible || updated.responsible.user_id === updated.accountable.user_id)) {
      updated.responsible = assignment;
    } else {
      // Beyond two: parking into editors so we don't lose the assignment.
      if (!updated.editors.some((e) => e.user_id === userId)) {
        updated.editors = [...updated.editors, assignment];
      }
      toast({
        title: "Added as Editor",
        description: `${getMemberName(userId)}, only two approvers can be set; added as Editor instead.`,
      });
    }
    updated = appendAuditLog(updated, {
      action: "Approver assigned",
      category: "role_assignment",
      new_value: getMemberName(userId),
    });
    setOwnership(updated);
    saveOwnership(updated);
    pushAssignmentNotification({
      user_id: userId,
      component_id: ownership.component_id,
      role: "approver",
      assigned_by: getCurrentUserId(),
    });
    toast({ title: "Approver assigned", description: `${getMemberName(userId)} added as Approver.` });
  };

  const removeApprover = (userId: string) => {
    let updated: ComponentOwnership = { ...ownership };
    const removingAccountable = updated.accountable?.user_id === userId;
    const removingResponsible = updated.responsible?.user_id === userId;
    if (removingAccountable && updated.responsible && updated.responsible.user_id !== userId) {
      // Promote responsible → accountable
      updated.accountable = updated.responsible;
      updated.responsible = fourEyesOn ? null : updated.accountable;
    } else if (removingAccountable) {
      updated.accountable = null;
      updated.responsible = null;
    } else if (removingResponsible) {
      updated.responsible = fourEyesOn ? null : updated.accountable;
    }
    updated = appendAuditLog(updated, {
      action: "Approver removed",
      category: "role_change",
      old_value: getMemberName(userId),
    });
    setOwnership(updated);
    saveOwnership(updated);
  };

  const setOwnershipType = (value: OwnershipType) => {
    const oldValue = ownership.ownership_type;
    const logEntry: OwnershipTypeLog = {
      value,
      changed_at: new Date().toISOString(),
      changed_by: getCurrentUserId(),
    };
    let updated: ComponentOwnership = {
      ...ownership,
      ownership_type: value,
      ownership_type_log: [...ownership.ownership_type_log, logEntry],
      ...(value === "Internal" ? { certification_file_name: null, certification_uploaded_at: null } : {}),
    };
    updated = appendAuditLog(updated, {
      action: "Ownership type changed",
      category: "ownership_type",
      old_value: oldValue,
      new_value: value,
    });
    setOwnership(updated);
    saveOwnership(updated);
    toast({ title: "Ownership type updated", description: `Component set to ${value}.` });
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    let updated: ComponentOwnership = {
      ...ownership,
      certification_file_name: file.name,
      certification_uploaded_at: new Date().toISOString(),
    };
    updated = appendAuditLog(updated, {
      action: "Certification uploaded",
      category: "certification",
      new_value: file.name,
    });
    setOwnership(updated);
    saveOwnership(updated);
    toast({ title: "Document uploaded", description: `${file.name} attached as certification.` });
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeCertification = () => {
    const oldName = ownership.certification_file_name;
    let updated: ComponentOwnership = {
      ...ownership,
      certification_file_name: null,
      certification_uploaded_at: null,
    };
    updated = appendAuditLog(updated, {
      action: "Certification removed",
      category: "certification",
      old_value: oldName ?? undefined,
    });
    setOwnership(updated);
    saveOwnership(updated);
  };

  const unlocked = !!(ownership.accountable && ownership.responsible);
  const needsCert = ownership.ownership_type !== "Internal";
  const hasCert = !!ownership.certification_file_name;
  const currentUserId = getCurrentUserId();
  const status = ownership.validation_status;

  const isAccountableUser = ownership.accountable?.user_id === currentUserId;
  const isResponsible = ownership.responsible?.user_id === currentUserId;

  // Block transitions if accountable is deactivated
  const transitionsBlocked = accountableCheck.deactivated;

  const transitionStatus = (to: ValidationStatus, reason?: string) => {
    if (transitionsBlocked) {
      toast({ title: "Transition blocked", description: accountableCheck.warning, variant: "destructive" });
      return;
    }
    const logEntry: ValidationStatusLog = {
      from: ownership.validation_status,
      to,
      changed_at: new Date().toISOString(),
      changed_by: currentUserId,
      reason,
    };
    let updated: ComponentOwnership = {
      ...ownership,
      validation_status: to,
      validation_status_log: [...ownership.validation_status_log, logEntry],
      ...(to === "Under Review" ? { submitted_for_review_by: currentUserId } : {}),
      ...(to === "Validated" ? { last_validated_at: new Date().toISOString(), last_validated_by: currentUserId } : {}),
    };
    updated = appendAuditLog(updated, {
      action: `Status: ${ownership.validation_status} → ${to}`,
      category: "status_transition",
      old_value: ownership.validation_status,
      new_value: to,
      details: reason,
    });
    setOwnership(updated);
    saveOwnership(updated);
  };

  const handleSubmitForReview = () => {
    if (!isResponsible) return;
    transitionStatus("Under Review");
    toast({ title: "Submitted for review", description: "The Accountable person can now validate this component." });
  };

  const handleValidate = () => {
    if (!isAccountableUser) return;
    if (ownership.submitted_for_review_by === currentUserId) {
      toast({
        title: "Four-eyes principle",
        description: "You submitted this for review, a secondary sign-off from a CFO or CEO is required.",
        variant: "destructive",
      });
      return;
    }
    transitionStatus("Validated");
    toast({ title: "Component validated", description: "This component is now validated." });
  };

  const handleRollback = () => {
    if (!isAccountableUser) return;
    transitionStatus("Draft", "Rollback by Accountable");
    toast({ title: "Rolled back to Draft", description: "Component returned to Draft status for corrections." });
  };

  const statusConfig = VALIDATION_STATUS_CONFIG[status];

  /* ── Render ── */
  const StatusIcon =
    status === "Validated" ? ShieldCheck :
    status === "Under Review" ? Send :
    Pencil;

  return (
    <TooltipProvider delayDuration={150}>
      <div className="space-y-3">
        {/* ── Compact header: status as a small icon-toggle + warnings ── */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => setStatusOpen((o) => !o)}
                  className={`inline-flex items-center gap-1.5 h-7 px-2 rounded-md border ${statusConfig.border} ${statusConfig.bg} ${statusConfig.color} hover:opacity-90`}
                >
                  <StatusIcon className="h-3.5 w-3.5" />
                  <span className="text-[10px] font-semibold">{statusConfig.label}</span>
                  {statusOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-[11px] max-w-[240px]">
                Validation status of this component. Click to expand lifecycle actions.
              </TooltipContent>
            </Tooltip>

            {accountableCheck.deactivated && (
              <Badge variant="outline" className="h-5 text-[9px] border-destructive/50 text-destructive gap-1">
                <AlertTriangle className="h-2.5 w-2.5" /> No active Approver
              </Badge>
            )}
          </div>

          {/* Ownership Type, collapsed into icon toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => setOwnershipOpen((o) => !o)}
                className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:text-foreground hover:border-foreground/40"
              >
                <Building2 className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="text-[11px] max-w-[240px]">
              Ownership type & external certification document
            </TooltipContent>
          </Tooltip>
        </div>

        {/* Expanded status details */}
        {statusOpen && (
          <div className={`rounded-lg border p-3 space-y-2 ${statusConfig.border} ${statusConfig.bg}`}>
            <p className="text-[11px] text-foreground/80">
              {status === "Draft" && "Data may be incomplete. Editable by approvers and editors."}
              {status === "Under Review" && "Submitted for review. Only the primary approver can validate."}
              {status === "Validated" && "Approved. Can be rolled back to Draft if corrections are needed."}
            </p>
            {ownership.last_validated_at && (
              <p className="text-[10px] text-muted-foreground">
                Last validated {new Date(ownership.last_validated_at).toLocaleDateString()}
              </p>
            )}
            <div className="flex gap-2 pt-1">
              {status === "Draft" && isResponsible && unlocked && (
                <Button type="button" size="sm" className="h-7 text-[11px] gap-1.5" onClick={handleSubmitForReview}>
                  <Send className="h-3 w-3" /> Submit for Review
                </Button>
              )}
              {status === "Under Review" && isAccountableUser && (
                <Button
                  type="button"
                  size="sm"
                  className="h-7 text-[11px] gap-1.5 bg-success hover:bg-success/90 text-success-foreground"
                  onClick={handleValidate}
                >
                  <ShieldCheck className="h-3 w-3" /> Validate
                </Button>
              )}
              {status === "Validated" && isAccountableUser && (
                <Button type="button" variant="outline" size="sm" className="h-7 text-[11px] gap-1.5" onClick={handleRollback}>
                  <RotateCcw className="h-3 w-3" /> Rollback to Draft
                </Button>
              )}
            </div>
            {accountableCheck.deactivated && (
              <div className="rounded-md border border-destructive/40 bg-destructive/5 px-2.5 py-2 flex items-start gap-2 mt-2">
                <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0 mt-0.5" />
                <p className="text-[10px] text-destructive">{accountableCheck.warning}</p>
              </div>
            )}
          </div>
        )}

        {/* Expanded Ownership Type + Certification */}
        {ownershipOpen && (
          <div className="rounded-lg border border-border bg-card p-3 space-y-3">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-semibold text-foreground">Ownership Type</span>
              <Badge
                variant="outline"
                className={`text-[9px] h-4 px-1.5 ${
                  OWNERSHIP_TYPES.find((t) => t.value === ownership.ownership_type)?.color ?? ""
                }`}
              >
                {ownership.ownership_type}
              </Badge>
            </div>
            <div className="flex gap-1.5">
              {OWNERSHIP_TYPES.map((t) => (
                <Button
                  key={t.value}
                  type="button"
                  variant={ownership.ownership_type === t.value ? "default" : "outline"}
                  size="sm"
                  className="h-7 text-[11px] flex-1"
                  onClick={() => setOwnershipType(t.value)}
                >
                  {t.label}
                </Button>
              ))}
            </div>

            {needsCert && (
              <div className={`rounded-md border p-2.5 space-y-2 ${
                hasCert ? "border-success/40 bg-success/5" : "border-warning/40 bg-warning/5"
              }`}>
                <div className="flex items-center gap-2">
                  <FileUp className={`h-3.5 w-3.5 ${hasCert ? "text-success" : "text-warning"}`} />
                  <span className="text-[11px] font-semibold text-foreground">Certification document</span>
                  {!hasCert && (
                    <Badge variant="outline" className="text-[9px] h-4 px-1 border-warning text-warning">Required</Badge>
                  )}
                </div>
                {hasCert ? (
                  <div className="flex items-center justify-between rounded border border-success/30 bg-card px-2 py-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <Check className="h-3 w-3 text-success shrink-0" />
                      <p className="text-[11px] truncate">{ownership.certification_file_name}</p>
                    </div>
                    <button
                      type="button"
                      onClick={removeCertification}
                      className="text-muted-foreground hover:text-destructive p-1 rounded"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-full h-7 text-[11px] gap-1.5"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="h-3 w-3" /> Upload document
                  </Button>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                  onChange={handleFileUpload}
                />
              </div>
            )}
          </div>
        )}

        {/* ── Approvers (merged Accountable + Responsible) ── */}
        <RoleCard
          icon={ShieldCheck}
          color="text-primary"
          label="Approvers"
          tooltip="People who validate this component's data before final approval. The primary approver gives the final sign-off; when four-eyes is enabled, a second distinct co-approver is required for separation of duties."
          count={approvers.length}
        >
          <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-2 py-1.5">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-3 w-3 text-muted-foreground" />
              <span className="text-[10px] text-foreground/80">Four-eyes principle</span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="h-2.5 w-2.5 text-muted-foreground" />
                </TooltipTrigger>
                <TooltipContent side="top" className="text-[11px] max-w-[240px]">
                  When ON: two distinct approvers required; the person who submitted for review cannot validate (separation of duties). When OFF: a single approver suffices, recommended only for low-risk components.
                </TooltipContent>
              </Tooltip>
            </div>
            <Switch checked={fourEyesOn} onCheckedChange={setFourEyes} />
          </div>

          {/* Compact status line, full guidance lives in the (i) tooltip above */}
          <div className="px-0.5 text-[10px] text-muted-foreground">
            Status:{" "}
            <span
              className={
                approvers.length >= (fourEyesOn ? 2 : 1)
                  ? "text-success font-medium"
                  : "text-warning font-medium"
              }
            >
              {approvers.length}/{fourEyesOn ? 2 : 1} approver{(fourEyesOn ? 2 : 1) > 1 ? "s" : ""} assigned
            </span>
          </div>

          {approvers.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {approvers.map((a, idx) => {
                const m = getMember(a.user_id);
                const isExternal = !!(m?.organization && m.organization.trim() !== "");
                return (
                  <Badge
                    key={a.user_id}
                    variant="secondary"
                    className="text-[11px] pl-2 pr-1 py-0.5 gap-1 inline-flex items-center"
                  >
                    {m?.name ?? "Unknown"}
                    <span className="text-[8px] font-semibold text-primary">
                      ·{idx === 0 ? "PRIMARY" : "CO"}
                    </span>
                    <span className={`text-[8px] font-semibold ${isExternal ? "text-warning" : "text-success"}`}>
                      {isExternal ? "·EXT" : "·INT"}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeApprover(a.user_id)}
                      className="ml-0.5 rounded-full hover:bg-destructive/20 p-0.5"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </Badge>
                );
              })}
            </div>
          )}

          {(fourEyesOn ? approvers.length < 2 : approvers.length < 1) && (
            <Select onValueChange={addApprover}>
              <SelectTrigger className="h-8 text-xs">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <UserPlus className="h-3 w-3" />
                  {approvers.length === 0 ? "Add primary approver…" : "Add co-approver…"}
                </span>
              </SelectTrigger>
              <SelectContent>
                {team
                  .filter((m) => !approvers.some((a) => a.user_id === m.user_id))
                  .map((m) => (
                    <SelectItem key={m.user_id} value={m.user_id} className="text-xs">
                      <span className="flex items-center gap-2">
                        {m.name}
                        <span className="text-muted-foreground">· {m.global_role}</span>
                        {m.organization ? (
                          <Badge variant="outline" className="h-3.5 px-1 text-[8px] border-warning/40 text-warning">EXT</Badge>
                        ) : (
                          <Badge variant="outline" className="h-3.5 px-1 text-[8px] border-success/40 text-success">INT</Badge>
                        )}
                      </span>
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          )}
        </RoleCard>

        {/* ── Editors (multi) ── */}
        <MultiRoleCard
          icon={Pencil}
          color="text-accent-foreground"
          label="Editors"
          tooltip="People who can modify the technical data fields of this component. Changes still require approver validation."
          assignments={ownership.editors}
          team={team}
          getMember={getMember}
          onAdd={(uid) => addMulti("editors", uid)}
          onRemove={(uid) => removeMulti("editors", uid)}
        />

        {/* ── Viewers (multi) ── */}
        <MultiRoleCard
          icon={Eye}
          color="text-muted-foreground"
          label="Viewers"
          tooltip="People with read-only access. They can see all data but cannot edit or approve."
          assignments={ownership.viewers}
          team={team}
          getMember={getMember}
          onAdd={(uid) => addMulti("viewers", uid)}
          onRemove={(uid) => removeMulti("viewers", uid)}
        />
      </div>
    </TooltipProvider>
  );
};

/* ─────────────── Subcomponents ─────────────── */

function RoleCard({
  icon: Icon,
  color,
  label,
  tooltip,
  count,
  children,
}: {
  icon: typeof Crown;
  color: string;
  label: string;
  tooltip: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${color}`} />
        <span className="text-xs font-semibold text-foreground">{label}</span>
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button" className="text-muted-foreground hover:text-foreground">
              <Info className="h-3 w-3" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-[11px] max-w-[260px] leading-relaxed">
            {tooltip}
          </TooltipContent>
        </Tooltip>
        {count !== undefined && count > 0 && (
          <Badge variant="secondary" className="text-[9px] h-4 px-1.5">{count}</Badge>
        )}
      </div>
      {children}
    </div>
  );
}

function MultiRoleCard({
  icon,
  color,
  label,
  tooltip,
  assignments,
  team,
  getMember,
  onAdd,
  onRemove,
}: {
  icon: typeof Pencil;
  color: string;
  label: string;
  tooltip: string;
  assignments: RoleAssignment[];
  team: TeamMember[];
  getMember: (id: string) => TeamMember | undefined;
  onAdd: (userId: string) => void;
  onRemove: (userId: string) => void;
}) {
  const assignedIds = new Set(assignments.map((a) => a.user_id));
  const available = team.filter((m) => !assignedIds.has(m.user_id));

  return (
    <RoleCard icon={icon} color={color} label={label} tooltip={tooltip} count={assignments.length}>
      {assignments.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {assignments.map((a) => {
            const m = getMember(a.user_id);
            const isExternal = !!(m?.organization && m.organization.trim() !== "");
            return (
              <Badge
                key={a.user_id}
                variant="secondary"
                className="text-[11px] pl-2 pr-1 py-0.5 gap-1 inline-flex items-center"
              >
                {m?.name ?? "Unknown"}
                <span className={`text-[8px] font-semibold ${isExternal ? "text-warning" : "text-success"}`}>
                  {isExternal ? "·EXT" : "·INT"}
                </span>
                <button
                  type="button"
                  onClick={() => onRemove(a.user_id)}
                  className="ml-0.5 rounded-full hover:bg-destructive/20 p-0.5"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </Badge>
            );
          })}
        </div>
      )}

      {available.length > 0 && (
        <Select onValueChange={onAdd}>
          <SelectTrigger className="h-8 text-xs">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <UserPlus className="h-3 w-3" /> Add {label.toLowerCase().replace(/s$/, "")}…
            </span>
          </SelectTrigger>
          <SelectContent>
            {available.map((m) => (
              <SelectItem key={m.user_id} value={m.user_id} className="text-xs">
                <span className="flex items-center gap-2">
                  {m.name}
                  <span className="text-muted-foreground">· {m.global_role}</span>
                  {m.organization ? (
                    <Badge variant="outline" className="h-3.5 px-1 text-[8px] border-warning/40 text-warning">EXT</Badge>
                  ) : (
                    <Badge variant="outline" className="h-3.5 px-1 text-[8px] border-success/40 text-success">INT</Badge>
                  )}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </RoleCard>
  );
}

export default OwnershipRolesPanel;
