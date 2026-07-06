/**
 * projectAccess — Project-level access control layer.
 *
 * Manages which team members can access which projects.
 * Admin users bypass all restrictions.
 */

import { useMemo } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { projectRegistry } from "@/lib/projectRegistry";
import { getCachedPlants } from "@/lib/plantStore";
import { safeGetJson, safeSetJson } from "@/lib/safeStorage";

/* ── Types ── */
export type ProjectRole = "viewer" | "editor" | "manager";

export interface ProjectAssignment {
  userId: string;
  projectGroupId: string;
  role: ProjectRole;
}

const STORAGE_KEY = "gex_project_assignments";

/* Admin user IDs that bypass all access checks */
const ADMIN_IDS = ["admin-001"];

/* ── Seed assignments ── */
const seedAssignments: ProjectAssignment[] = [
  // Jan van der Berg — Head of Engineering → all projects as manager
  { userId: "u-001", projectGroupId: "rotterdam", role: "manager" },
  { userId: "u-001", projectGroupId: "hamburg", role: "manager" },
  { userId: "u-001", projectGroupId: "marseille", role: "editor" },
  { userId: "u-001", projectGroupId: "northsea", role: "manager" },
  { userId: "u-001", projectGroupId: "antwerp", role: "editor" },
  // Sophie Müller — Manager → Rotterdam + Hamburg
  { userId: "u-002", projectGroupId: "rotterdam", role: "manager" },
  { userId: "u-002", projectGroupId: "hamburg", role: "manager" },
  // Ahmed El-Sayed — Engineer → Rotterdam + North Sea
  { userId: "u-003", projectGroupId: "rotterdam", role: "editor" },
  { userId: "u-003", projectGroupId: "northsea", role: "editor" },
  // Lena Johansson — Technician → Rotterdam only
  { userId: "u-004", projectGroupId: "rotterdam", role: "viewer" },
  // Carlos Ferreira — External → Rotterdam (viewer)
  { userId: "u-005", projectGroupId: "rotterdam", role: "viewer" },
];

/* ── Persistence ── */
export function loadAssignments(): ProjectAssignment[] {
  const stored = safeGetJson<ProjectAssignment[] | null>(STORAGE_KEY, null);
  if (stored) return stored;

  safeSetJson(STORAGE_KEY, seedAssignments);
  return seedAssignments;
}

export function saveAssignments(assignments: ProjectAssignment[]) {
  safeSetJson(STORAGE_KEY, assignments);
}

/* ── Helpers ── */
export function getUniqueProjectGroups(): string[] {
  const groups = new Set(projectRegistry.map((p) => p.projectGroupId));
  return Array.from(groups);
}

export function getProjectGroupLabel(groupId: string): string {
  const first = projectRegistry.find((p) => p.projectGroupId === groupId);
  if (!first) return groupId;
  // Use the project name but strip the plant-specific suffix for the group label
  return first.name;
}

export function getUserAssignments(userId: string, assignments: ProjectAssignment[]): ProjectAssignment[] {
  return assignments.filter((a) => a.userId === userId);
}

export function getProjectRole(userId: string, projectGroupId: string, assignments: ProjectAssignment[]): ProjectRole | null {
  const match = assignments.find((a) => a.userId === userId && a.projectGroupId === projectGroupId);
  return match?.role ?? null;
}

/* ── Hook ── */
export function useProjectAccess() {
  const { user } = useAuth();

  const isAdmin = useMemo(() => {
    if (!user) return false;
    return ADMIN_IDS.includes(user.id) || user.email === "marwen@greenearthx.com";
  }, [user]);

  const assignments = useMemo(() => loadAssignments(), []);

  const assignedProjects = useMemo(() => {
    if (!user) return [];
    if (isAdmin) return getUniqueProjectGroups();
    // Always include groups for plants the current account owns —
    // ABAC team assignments only restrict OTHER members' plants,
    // never the account holder's own portfolio.
    const ownedGroupIds = getCachedPlants()
      .filter((p) => p.owned)
      .map((p) => p.projectGroupId);
    const teamGroupIds = assignments
      .filter((a) => a.userId === user.id)
      .map((a) => a.projectGroupId);
    return Array.from(new Set([...ownedGroupIds, ...teamGroupIds]));
  }, [user, isAdmin, assignments]);

  const canAccess = (projectGroupId: string): boolean => {
    if (isAdmin) return true;
    if (!user) return false;
    return assignedProjects.includes(projectGroupId);
  };

  const getRole = (projectGroupId: string): ProjectRole | null => {
    if (!user) return null;
    if (isAdmin) return "manager";
    return getProjectRole(user.id, projectGroupId, assignments);
  };

  return { isAdmin, assignedProjects, canAccess, getRole };
}

/* ── Role display helpers ── */
export const roleStyles: Record<ProjectRole, { bg: string; text: string; label: string }> = {
  viewer: { bg: "bg-muted", text: "text-muted-foreground", label: "Viewer" },
  editor: { bg: "bg-primary/10", text: "text-primary", label: "Editor" },
  manager: { bg: "bg-success/10", text: "text-success", label: "Manager" },
};
