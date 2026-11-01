import type { AuthUser } from '@/types';

// Pure helpers for the Role 4 recovery-assessment console.
// No runtime imports so the repo's `node --test` convention can run its tests.

export type AssessmentStatus = 'pending_review' | 'approved' | 'rejected';

/**
 * Only the Insurance Recovery Officer (Role 4) may generate, edit, decide,
 * and regenerate reports. Role 1 gets a read-only oversight view.
 * Backend endpoints must still enforce this server-side.
 */
export function isRole4Reviewer(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  if (user.roleLevel === 4) return true;
  if (String(user.roleId ?? '').trim().toLowerCase() === 'role_4') return true;
  const name = String(user.roleName ?? '').toLowerCase();
  return name.includes('insurance recovery') || name.includes('recovery officer');
}

export function canReadAssessments(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  if (isRole4Reviewer(user)) return true;
  if (user.roleLevel === 1) return true;
  if (String(user.roleId ?? '').trim().toLowerCase() === 'role_1') return true;
  return String(user.roleName ?? '').toLowerCase().includes('disaster assessment');
}

function matchesRole(
  user: AuthUser | null | undefined,
  level: number,
  roleId: string,
  namePart: string,
): boolean {
  if (!user) return false;
  if (user.roleLevel === level) return true;
  if (String(user.roleId ?? '').trim().toLowerCase() === roleId) return true;
  return String(user.roleName ?? '').toLowerCase().includes(namePart);
}

export function isRole1Assessor(user: AuthUser | null | undefined): boolean {
  return matchesRole(user, 1, 'role_1', 'disaster assessment');
}

export function isRole2Planner(user: AuthUser | null | undefined): boolean {
  return matchesRole(user, 2, 'role_2', 'operations planner');
}

export function isRole3Field(user: AuthUser | null | undefined): boolean {
  return matchesRole(user, 3, 'role_3', 'field operations');
}

/**
 * Officers who may submit observed damage counts (mirrors the backend
 * damage-assessments guard: Roles 1, 3, 4). Backend still enforces this.
 */
export function canSubmitDamage(user: AuthUser | null | undefined): boolean {
  return isRole1Assessor(user) || isRole3Field(user) || isRole4Reviewer(user);
}

/**
 * Officers who may record preparedness/recovery spend (mirrors the backend
 * expenses guard: Roles 2, 3, 4). Backend still enforces this.
 */
export function canSubmitExpense(user: AuthUser | null | undefined): boolean {
  return isRole2Planner(user) || isRole3Field(user) || isRole4Reviewer(user);
}

/** Display an INR figure or people count; null stays an honest "Unknown". */
export function formatFigureValue(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'Unknown';
  if (unit === 'people') return `${Math.round(value).toLocaleString('en-IN')} people`;
  return `Rs.${Math.round(value).toLocaleString('en-IN')}`;
}

/**
 * Stat display that never misreports a failed load as zero:
 * loading shows an ellipsis, a failed load shows a dash,
 * and only a successful load shows the real count.
 */
export function displayCount(args: { loading: boolean; error: string | null; count: number }): string | number {
  if (args.loading) return '…';
  if (args.error) return '—';
  return args.count;
}

export function statusLabel(status: AssessmentStatus): string {
  if (status === 'approved') return 'Government Approved';
  if (status === 'rejected') return 'Rejected';
  return 'Pending Review';
}

/** Editable figure paths (mirrors the backend FIGURE_KEYS). */
export const EDITABLE_FIGURE_KEYS = [
  'affected_people',
  'housing_loss_inr',
  'crop_loss_inr',
  'livestock_loss_inr',
  'infrastructure_loss_inr',
  'total_damage_inr',
  'preparation_cost_inr',
  'recovery_cost_inr',
  'indicative_relief_inr',
] as const;

export function isEditableFigureKey(key: string): boolean {
  return (EDITABLE_FIGURE_KEYS as readonly string[]).includes(key);
}
