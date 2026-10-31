import type { DisasterRecommendedTask } from '@/types/api';
import type { AuthUser } from '@/types';

// Pure helpers for the Role 2 emergency-task review console
// (TaskEvacuationModeView). This module has no runtime imports so the
// repository's `node --test` convention can execute its test file.

export type TaskPriority = 'Critical' | 'High' | 'Medium' | 'Low';
export type ReviewStatus = 'pending' | 'accepted' | 'rejected';
export type BackendConfirmation = 'local' | 'confirmed' | 'failed';

export interface RecommendationEdits {
  description: string;
  department: string;
  location: string;
  priority: TaskPriority;
  instructions: string;
}

export interface ReviewRecord {
  status: ReviewStatus;
  edited: RecommendationEdits | null;
  editedAt: string | null;
  rejectionReason: string | null;
  decidedAt: string | null;
  decidedBy: string | null;
  team: string | null;
  officer: string | null;
  deadline: string | null;
  instructions: string | null;
  notifyRequested: boolean;
  backendState: BackendConfirmation;
  backendNote: string | null;
  /** Backend task id from POST /api/tasks (present when confirmed). */
  backendId?: string | null;
  /** Role 3 assignee user id used for the backend record. */
  assigneeUserId?: string | null;
}

export interface OperationalTask {
  id: string;
  source: 'ai' | 'manual';
  sourceRef: string | null;
  title: string;
  department: string;
  location: string;
  priority: TaskPriority;
  team: string | null;
  officer: string | null;
  instructions: string;
  deadline: string | null;
  createdAt: string;
  createdBy: string | null;
  backendState: BackendConfirmation;
  /** Backend task id from POST /api/tasks (present when confirmed). */
  backendId?: string | null;
  assigneeUserId?: string | null;
}

export interface ReviewCounts {
  pending: number;
  accepted: number;
  rejected: number;
}

export interface AssignmentSummary {
  total: number;
  awaitingAssignment: number;
  assigned: number;
}

export function pendingReviewRecord(): ReviewRecord {
  return {
    status: 'pending',
    edited: null,
    editedAt: null,
    rejectionReason: null,
    decidedAt: null,
    decidedBy: null,
    team: null,
    officer: null,
    deadline: null,
    instructions: null,
    notifyRequested: true,
    backendState: 'local',
    backendNote: null,
  };
}

/** Map free-text AI priority values onto the console's fixed scale. */
export function normalizePriority(raw: unknown): TaskPriority {
  const value = String(raw ?? '').trim().toLowerCase();
  if (value === 'critical' || value === 'urgent' || value === 'severe') return 'Critical';
  if (value === 'high') return 'High';
  if (value === 'low') return 'Low';
  return 'Medium';
}

/** Stable per-region key for one AI recommendation row. */
export function recommendationKey(regionKey: string, index: number): string {
  return `${regionKey}#${index}`;
}

/** Display label for one AI recommendation row. */
export function recommendationLabel(index: number): string {
  return `AI-${String(index + 1).padStart(2, '0')}`;
}

export interface EffectiveRecommendation {
  description: string;
  department: string;
  location: string;
  priority: TaskPriority;
}

/** Officer edits win over the raw AI values for display and assignment. */
export function effectiveRecommendation(
  rec: DisasterRecommendedTask,
  edited: RecommendationEdits | null | undefined,
): EffectiveRecommendation {
  return {
    description: edited?.description ?? rec.description,
    department: edited?.department ?? rec.department,
    location: edited?.location ?? rec.location,
    priority: edited?.priority ?? normalizePriority(rec.priority),
  };
}

/** Count review outcomes over the current region's recommendation keys. */
export function reviewCounts(
  decisions: Record<string, ReviewRecord>,
  keys: string[],
): ReviewCounts {
  const counts: ReviewCounts = { pending: 0, accepted: 0, rejected: 0 };
  for (const key of keys) {
    const status = decisions[key]?.status ?? 'pending';
    counts[status] += 1;
  }
  return counts;
}

export interface BackendTaskFingerprint {
  source: 'ai' | 'manual';
  sourceRef: string | null;
  regionKey: string | null;
  title: string;
  createdAt: string;
}

export interface LocalRecordFingerprint {
  source: 'ai' | 'manual';
  sourceRef: string | null;
  regionKey: string | null;
  title: string;
  createdAt: string;
}

/**
 * True when a backend task already covers a local record, so a sync pass
 * must skip it instead of creating a duplicate. AI records match by
 * region + recommendation ref; manual records match by title + timestamp.
 */
export function backendCoversLocal(
  backend: BackendTaskFingerprint,
  local: LocalRecordFingerprint,
): boolean {
  if (backend.source !== local.source) return false;
  if (local.source === 'ai') {
    return (
      (local.sourceRef ?? '') !== '' &&
      backend.sourceRef === local.sourceRef &&
      (backend.regionKey ?? null) === (local.regionKey ?? null)
    );
  }
  return backend.title === local.title && backend.createdAt === local.createdAt;
}

export interface RosterOfficer {
  id: string;
  name: string;
}

/**
 * Resolve which Role 3 officer a record belongs to: the stored assignee id
 * wins, then a stored officer/team name match, then the roster default
 * (first active Role 3 officer). Returns null when no roster is loaded.
 */
export function resolveAssigneeId(
  officers: RosterOfficer[],
  preferredId?: string | null,
  preferredName?: string | null,
): string | null {
  if (preferredId && officers.some((officer) => officer.id === preferredId)) {
    return preferredId;
  }
  if (preferredName) {
    const match = officers.find((officer) => officer.name === preferredName);
    if (match) return match.id;
  }
  return officers[0]?.id ?? null;
}

export function buildOperationalTaskFromDecision(args: {
  index: number;
  rec: DisasterRecommendedTask;
  decision: ReviewRecord | undefined;
}): OperationalTask | null {
  const { index, rec, decision } = args;
  if (!decision || decision.status !== 'accepted') return null;
  const effective = effectiveRecommendation(rec, decision.edited);
  return {
    id: recommendationLabel(index),
    source: 'ai',
    sourceRef: recommendationLabel(index),
    title: effective.description,
    department: effective.department,
    location: effective.location,
    priority: effective.priority,
    team: decision.team,
    officer: decision.officer,
    instructions: decision.instructions ?? decision.edited?.instructions ?? '',
    deadline: decision.deadline,
    createdAt: decision.decidedAt ?? '',
    createdBy: decision.decidedBy,
    backendState: decision.backendState,
    backendId: decision.backendId ?? null,
    assigneeUserId: decision.assigneeUserId ?? null,
  };
}

/** Accepted-work overview: assigned means a field team is recorded. */
export function summarizeAssignments(tasks: OperationalTask[]): AssignmentSummary {
  const assigned = tasks.filter((task) => (task.team ?? '').trim().length > 0).length;
  return {
    total: tasks.length,
    assigned,
    awaitingAssignment: tasks.length - assigned,
  };
}

/**
 * Only the Operations Planner (Role 2) may review, assign, and alert from
 * this console. Role 1/3/4/5 officers who can open the route get a
 * read-only view. Backend endpoints must still enforce this server-side.
 */
export function isRole2Reviewer(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  if (user.roleLevel === 2) return true;
  if (String(user.roleId ?? '').trim().toLowerCase() === 'role_2') return true;
  return String(user.roleName ?? '').toLowerCase().includes('operations planner');
}
