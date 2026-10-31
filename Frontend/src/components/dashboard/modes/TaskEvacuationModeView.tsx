import { useEffect, useMemo, useRef, useState, type FC, type FormEvent, type ReactNode } from 'react';
import {
  AlertTriangle,
  BellRing,
  Building2,
  CalendarClock,
  CheckCheck,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Eye,
  FileText,
  History,
  LoaderCircle,
  MapPin,
  Pencil,
  Plus,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  Users,
  X,
  XCircle,
} from 'lucide-react';
import { MapComponent } from '@/components/dashboard/MapComponent';
import type { CityLocation, MapPOI } from '@/types/domain';
import {
  isAvailableDisasterIntelligence,
  type ApiRegion,
  type DisasterIntelligenceResult,
  type DisasterRecommendedTask,
} from '@/types/api';
import { api } from '@/services/api';
import { getUsers, verifyToken } from '@/services/authApi';
import {
  notificationsApi,
  tasksApi,
  type BackendTask,
  type CreateNotificationInput,
  type CreateTaskInput,
  type OperationalNotification,
} from '@/services/operationalApi';
import type { AuthUser, OfficerUser } from '@/types';
import type { ClimateAlert } from '@/types/alerts';
import {
  backendCoversLocal,
  buildOperationalTaskFromDecision,
  effectiveRecommendation,
  isRole2Reviewer,
  pendingReviewRecord,
  recommendationKey,
  recommendationLabel,
  resolveAssigneeId,
  reviewCounts,
  summarizeAssignments,
  type BackendConfirmation,
  type OperationalTask,
  type RecommendationEdits,
  type ReviewRecord,
  type TaskPriority,
} from '@/utils/taskReview';

const TASK_DEADLINE_MS = 48 * 60 * 60 * 1000;
const DEPARTMENTS = [
  'NDRF',
  'Municipal Corp',
  'PWD Water Supply',
  'Health & EMS',
  'Power Utility',
  'Police',
  'Fire & Rescue',
  'Revenue Department',
];
const PRIORITIES: TaskPriority[] = ['Critical', 'High', 'Medium', 'Low'];
const REVIEW_STORAGE_VERSION = 1;

const formatCountdown = (milliseconds: number) => {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
};

const inputClass =
  'w-full border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 outline-none focus:border-[#18365b] disabled:bg-slate-100 disabled:text-slate-500';
const primaryButtonClass =
  'inline-flex items-center justify-center gap-1.5 bg-[#18365b] px-3 py-2 text-xs font-semibold text-white hover:bg-[#102744] disabled:cursor-not-allowed disabled:opacity-50';
const outlineButtonClass =
  'inline-flex items-center justify-center gap-1.5 border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50';
const dangerOutlineButtonClass =
  'inline-flex items-center justify-center gap-1.5 border border-red-300 bg-white px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50';

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function toDatetimeLocalValue(iso: string | null | undefined): string {
  if (!iso) return '';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '';
  const pad = (part: number) => String(part).padStart(2, '0');
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}` +
    `T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  );
}

function defaultDeadlineValue(): string {
  return toDatetimeLocalValue(new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString());
}

// ---------------------------------------------------------------------------
// Local review store + backend seams
// ---------------------------------------------------------------------------

interface AlertRecord {
  id: string;
  createdAt: string;
  createdBy: string | null;
  recipientTeam: string;
  message: string;
  priority: TaskPriority;
  status: 'not_sent' | 'sent';
  statusNote: string;
}

interface StoredReviewState {
  version: number;
  decisions: Record<string, ReviewRecord>;
  manualTasks: OperationalTask[];
  alertRecords: AlertRecord[];
}

const emptyStoredState = (): StoredReviewState => ({
  version: REVIEW_STORAGE_VERSION,
  decisions: {},
  manualTasks: [],
  alertRecords: [],
});

const storageKey = (regionKey: string) => `3p-task-review:${regionKey}`;

function loadStoredState(regionKey: string): StoredReviewState {
  try {
    const raw = localStorage.getItem(storageKey(regionKey));
    if (!raw) return emptyStoredState();
    const parsed = JSON.parse(raw) as StoredReviewState;
    if (parsed.version !== REVIEW_STORAGE_VERSION) return emptyStoredState();
    return {
      version: REVIEW_STORAGE_VERSION,
      decisions: parsed.decisions ?? {},
      manualTasks: Array.isArray(parsed.manualTasks) ? parsed.manualTasks : [],
      alertRecords: Array.isArray(parsed.alertRecords) ? parsed.alertRecords : [],
    };
  } catch {
    return emptyStoredState();
  }
}

function saveStoredState(regionKey: string, state: StoredReviewState): void {
  try {
    localStorage.setItem(storageKey(regionKey), JSON.stringify(state));
  } catch {
    // Private-mode storage failures must not break the review workflow.
  }
}

/**
 * Persist an assignment to POST /api/tasks. Returns persisted: true only
 * after the server confirms, with the backend task id for later updates.
 * Failures fall back to a local record so the officer never loses work.
 */
async function persistTaskToBackend(
  input: CreateTaskInput,
): Promise<{ persisted: boolean; id: string | null; note: string }> {
  try {
    const task = await tasksApi.create(input);
    return { persisted: true, id: task.id, note: 'Confirmed by backend' };
  } catch (error) {
    return {
      persisted: false,
      id: null,
      note: error instanceof Error ? error.message : 'Backend save failed; kept as a local record.',
    };
  }
}

async function updateTaskOnBackend(
  backendId: string,
  input: Parameters<typeof tasksApi.update>[1],
): Promise<{ persisted: boolean; note: string }> {
  try {
    await tasksApi.update(backendId, input);
    return { persisted: true, note: 'Confirmed by backend' };
  } catch (error) {
    return {
      persisted: false,
      note: error instanceof Error ? error.message : 'Backend update failed; kept as a local record.',
    };
  }
}

/**
 * Send an operational alert via POST /api/notifications so it appears in
 * the recipient's notification page. Returns sent: true only after the
 * server confirms; failures are kept as local drafts.
 */
async function dispatchAlertToBackend(
  input: CreateNotificationInput,
): Promise<{ sent: boolean; id: string | null; note: string }> {
  try {
    const notification = await notificationsApi.create(input);
    return { sent: true, id: notification.id, note: 'Delivered to the field officer inbox' };
  } catch (error) {
    return {
      sent: false,
      id: null,
      note: error instanceof Error ? error.message : 'Dispatch failed; saved as a local draft.',
    };
  }
}

function mapBackendTaskToOperational(task: BackendTask): OperationalTask {
  return {
    id: `T-${task.id.slice(0, 6).toUpperCase()}`,
    source: task.source,
    sourceRef: task.sourceRef,
    title: task.title,
    department: task.department,
    location: task.location,
    priority: task.priority,
    team: task.assigneeName || null,
    officer: null,
    instructions: task.instructions || '',
    deadline: task.deadline,
    createdAt: task.createdAt,
    createdBy: task.createdByName || null,
    backendState: 'confirmed',
    backendId: task.id,
    assigneeUserId: task.assigneeUserId,
  };
}

// ---------------------------------------------------------------------------
// Small presentational pieces
// ---------------------------------------------------------------------------

const PRIORITY_BADGE: Record<TaskPriority, string> = {
  Critical: 'border-red-700 bg-red-700 text-white',
  High: 'border-orange-600 bg-orange-50 text-orange-800',
  Medium: 'border-amber-500 bg-amber-50 text-amber-900',
  Low: 'border-slate-300 bg-slate-100 text-slate-700',
};

function PriorityBadge({ priority }: { priority: TaskPriority }) {
  return (
    <span className={`inline-block border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${PRIORITY_BADGE[priority]}`}>
      {priority}
    </span>
  );
}

function ReviewStatusBadge({ status }: { status: ReviewRecord['status'] }) {
  if (status === 'accepted') {
    return (
      <span className="inline-flex items-center gap-1 border border-emerald-700 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-800">
        <CheckCircle2 size={11} /> Accepted
      </span>
    );
  }
  if (status === 'rejected') {
    return (
      <span className="inline-flex items-center gap-1 border border-red-700 bg-red-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-red-800">
        <XCircle size={11} /> Rejected
      </span>
    );
  }
  return (
    <span className="inline-block border border-amber-600 bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-900">
      Pending review
    </span>
  );
}

function SourceBadge({ source }: { source: OperationalTask['source'] }) {
  if (source === 'ai') {
    return (
      <span className="inline-flex items-center gap-1 border border-blue-800 bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-900">
        <Sparkles size={11} /> AI recommended
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 border border-slate-400 bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-700">
      <FileText size={11} /> Manual task
    </span>
  );
}

function BackendStateLine({ state, note }: { state: BackendConfirmation; note: string | null }) {
  if (state === 'confirmed') {
    return <span className="text-[11px] font-semibold text-emerald-800">Confirmed by backend</span>;
  }
  return (
    <span className="text-[11px] text-amber-900" title={note ?? undefined}>
      Local record — awaiting backend confirmation
    </span>
  );
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold text-slate-700">
        {label} {required ? <span className="text-red-700">*</span> : null}
      </span>
      {children}
      {hint ? <span className="mt-1 block text-[11px] font-normal leading-4 text-slate-500">{hint}</span> : null}
    </label>
  );
}

function StatCell({ label, value, hint }: { label: string; value: string | number; hint: string }) {
  return (
    <div className="border border-slate-300 bg-white px-4 py-3 shadow-sm">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold tracking-tight text-[#18365b]">{value}</p>
      <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p>
    </div>
  );
}

function Modal({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/55 p-3 sm:p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto border border-slate-300 bg-white shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 bg-[#18365b] px-4 py-3 text-white">
          <div>
            <h2 className="text-sm font-bold">{title}</h2>
            {subtitle ? <p className="mt-0.5 text-xs text-blue-100">{subtitle}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="border border-white/40 p-1.5 text-white hover:bg-white/10"
          >
            <X size={15} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

interface TaskEvacuationModeViewProps {
  city: CityLocation;
  bounds: ApiRegion;
  pois: MapPOI[];
  disasterIntelligence: DisasterIntelligenceResult | null;
  isLoading: boolean;
  error: string | null;
  isLightMode?: boolean;
}

interface AssignmentDraft {
  description: string;
  department: string;
  location: string;
  priority: TaskPriority;
  team: string;
  officer: string;
  /** Selected Role 3 officer user id (Accept & Assign flow). */
  assigneeId: string;
  instructions: string;
  deadline: string;
  notifyTeam: boolean;
}

interface AuditEntry {
  at: string;
  item: string;
  action: string;
  detail: string;
  officer: string;
  tone: 'green' | 'red' | 'amber' | 'slate';
}

type FeedbackTone = 'success' | 'warning' | 'error' | 'info';

export const TaskEvacuationModeView: FC<TaskEvacuationModeViewProps> = ({
  city,
  bounds,
  pois,
  disasterIntelligence,
  isLoading,
  error,
  isLightMode,
}) => {
  // Retained for API compatibility; this console always uses the light
  // government-portal theme.
  void isLightMode;

  const hasAssessment = isAvailableDisasterIntelligence(disasterIntelligence);
  const regionKey = disasterIntelligence?.region ?? city.id;
  const recommendations: DisasterRecommendedTask[] = hasAssessment
    ? disasterIntelligence.ai_analysis.recommended_tasks
    : [];
  const riskZones = hasAssessment ? disasterIntelligence.risk_zones : [];
  const reasoningContext = hasAssessment ? disasterIntelligence.ai_analysis.reasoning_context : [];
  const ingestionError = hasAssessment ? disasterIntelligence.data_quality.ingestion_error : null;
  const generatedAt = hasAssessment ? disasterIntelligence.generated_at : null;
  const riskLevel = hasAssessment ? disasterIntelligence.risk_assessment.level : null;

  const [decisions, setDecisions] = useState<Record<string, ReviewRecord>>({});
  const [manualTasks, setManualTasks] = useState<OperationalTask[]>([]);
  const [alertRecords, setAlertRecords] = useState<AlertRecord[]>([]);
  const [hydratedFor, setHydratedFor] = useState<string | null>(null);

  // Field completion updates: Role 3 submissions notified to this Role 2 inbox.
  const [completionNotices, setCompletionNotices] = useState<OperationalNotification[]>([]);
  const [completionTasks, setCompletionTasks] = useState<BackendTask[]>([]);
  const [completionLoading, setCompletionLoading] = useState(false);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const [completionRefresh, setCompletionRefresh] = useState(0);
  const [markingNoticeId, setMarkingNoticeId] = useState<string | null>(null);

  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [userLoading, setUserLoading] = useState(true);
  const [userError, setUserError] = useState<string | null>(null);
  const [officers, setOfficers] = useState<OfficerUser[]>([]);
  const [officersError, setOfficersError] = useState<string | null>(null);

  const [recentAlerts, setRecentAlerts] = useState<ClimateAlert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [alertsRefresh, setAlertsRefresh] = useState(0);
  const [waConfig, setWaConfig] = useState<{
    verification_configured: boolean;
    delivery_configured: boolean;
  } | null>(null);

  const [currentTime, setCurrentTime] = useState(() => Date.now());
  const [operationalDeadline] = useState(() => Date.now() + TASK_DEADLINE_MS);
  const [feedback, setFeedback] = useState<{ tone: FeedbackTone; message: string } | null>(null);

  const [assignIndex, setAssignIndex] = useState<number | null>(null);
  const [assignDraft, setAssignDraft] = useState<AssignmentDraft | null>(null);
  const [assignSaving, setAssignSaving] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);

  const [rejectIndex, setRejectIndex] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectSaving, setRejectSaving] = useState(false);
  const [rejectError, setRejectError] = useState<string | null>(null);

  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<RecommendationEdits | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [editingManualId, setEditingManualId] = useState<string | null>(null);
  const [createDraft, setCreateDraft] = useState<AssignmentDraft | null>(null);
  const [createSaving, setCreateSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [detailTask, setDetailTask] = useState<OperationalTask | null>(null);

  const [composeMessage, setComposeMessage] = useState('');
  const [composePriority, setComposePriority] = useState<TaskPriority>('High');
  const [composeSaving, setComposeSaving] = useState(false);
  const alertSectionRef = useRef<HTMLElement | null>(null);
  const decisionsRef = useRef(decisions);
  decisionsRef.current = decisions;
  const manualTasksRef = useRef(manualTasks);
  manualTasksRef.current = manualTasks;
  const syncedRegionsRef = useRef<Set<string>>(new Set());

  const canWrite = isRole2Reviewer(currentUser);
  const userName = currentUser?.name ?? null;
  // Assignment and alerts always target the Role 3 officer (from Database/users.json via GET /users).
  const role3Officer = officers.length > 0 ? officers[0] : null;
  const role3OfficerName = role3Officer?.name ?? null;

  // Hydrate the per-region local review store, and reset transient UI.
  useEffect(() => {
    const stored = loadStoredState(regionKey);
    setDecisions(stored.decisions);
    setManualTasks(stored.manualTasks);
    setAlertRecords(stored.alertRecords);
    setHydratedFor(regionKey);
    setAssignIndex(null);
    setRejectIndex(null);
    setEditIndex(null);
    setCreateOpen(false);
    setDetailTask(null);
    setFeedback(null);
  }, [regionKey]);

  // Merge backend-confirmed tasks for this region so accepted work survives
  // reloads and shows "Confirmed by backend" instead of a local record.
  useEffect(() => {
    if (hydratedFor !== regionKey) return;
    let cancelled = false;
    tasksApi
      .list({ regionKey })
      .then((backendTasks) => {
        if (cancelled) return;
        const aiByRef = new Map<string, BackendTask>();
        const backendManual: OperationalTask[] = [];
        for (const task of backendTasks) {
          if (task.source === 'ai' && task.sourceRef) {
            const existing = aiByRef.get(task.sourceRef);
            if (!existing || task.createdAt > existing.createdAt) {
              aiByRef.set(task.sourceRef, task);
            }
          } else {
            backendManual.push(mapBackendTaskToOperational(task));
          }
        }
        if (aiByRef.size > 0) {
          setDecisions((current) => {
            const next = { ...current };
            aiByRef.forEach((task, ref) => {
              const parsed = Number.parseInt(ref.slice(3), 10) - 1;
              if (!Number.isInteger(parsed) || parsed < 0) return;
              const key = recommendationKey(regionKey, parsed);
              next[key] = {
                ...(current[key] ?? pendingReviewRecord()),
                status: 'accepted',
                edited: {
                  description: task.title,
                  department: task.department,
                  location: task.location,
                  priority: task.priority,
                  instructions: task.instructions || '',
                },
                editedAt: task.createdAt,
                rejectionReason: null,
                decidedAt: task.createdAt,
                decidedBy: task.createdByName || null,
                team: task.assigneeName || null,
                officer: null,
                deadline: task.deadline,
                instructions: task.instructions || '',
                notifyRequested: current[key]?.notifyRequested ?? false,
                backendState: 'confirmed',
                backendNote: null,
                backendId: task.id,
                assigneeUserId: task.assigneeUserId,
              };
            });
            return next;
          });
        }
        if (backendManual.length > 0) {
          setManualTasks((current) => {
            const localOnly = current.filter((task) => task.backendState !== 'confirmed' && !task.backendId);
            const knownIds = new Set(localOnly.map((task) => task.backendId));
            const fresh = backendManual.filter((task) => !knownIds.has(task.backendId));
            return [...fresh, ...localOnly].sort((left, right) =>
              right.createdAt.localeCompare(left.createdAt),
            );
          });
        }
      })
      .catch(() => {
        // Backend unavailable: keep the local review store as the fallback.
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydratedFor, regionKey]);

  // Merge backend-sent notifications so the alert centre shows confirmed
  // deliveries alongside any local drafts.
  useEffect(() => {
    if (hydratedFor !== regionKey) return;
    let cancelled = false;
    notificationsApi
      .list('sent')
      .then((result) => {
        if (cancelled) return;
        const sent = result.notifications
          .filter((item) => !item.regionKey || item.regionKey === regionKey)
          .map((item) => ({
            id: item.id,
            createdAt: item.createdAt,
            createdBy: item.senderName || null,
            recipientTeam: item.recipientName,
            message: item.message,
            priority: item.priority,
            status: 'sent' as const,
            statusNote: 'Delivered to the field officer inbox',
          }));
        if (sent.length === 0) return;
        setAlertRecords((current) => {
          const drafts = current.filter((alert) => alert.status === 'not_sent');
          const known = new Set(drafts.map((alert) => alert.id));
          const fresh = sent.filter((alert) => !known.has(alert.id));
          return [...fresh, ...drafts];
        });
      })
      .catch(() => {
        // Backend unavailable: keep local drafts only.
      });
    return () => {
      cancelled = true;
    };
  }, [hydratedFor, regionKey]);

  // Field completion updates: tasks Role 3 marked submitted, plus the inbox
  // notices the backend addressed to this Role 2 officer.
  useEffect(() => {
    if (hydratedFor !== regionKey) return;
    let cancelled = false;
    setCompletionLoading(true);
    setCompletionError(null);
    Promise.all([
      notificationsApi.list('inbox').catch(() => null),
      tasksApi.list({ regionKey }).catch(() => [] as BackendTask[]),
    ])
      .then(([inbox, backendTasks]) => {
        if (cancelled) return;
        const notices = (inbox?.notifications ?? []).filter(
          (item) => item.taskId && (!item.regionKey || item.regionKey === regionKey),
        );
        setCompletionNotices(notices);
        setCompletionTasks(
          (backendTasks ?? []).filter((task) => task.status === 'Submitted'),
        );
        if (inbox === null && (backendTasks ?? []).length === 0) {
          setCompletionError('Completion updates are unavailable right now.');
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setCompletionNotices([]);
          setCompletionTasks([]);
          setCompletionError(
            error instanceof Error ? error.message : 'Completion updates are unavailable right now.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setCompletionLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [hydratedFor, regionKey, completionRefresh]);

  const markCompletionNoticeRead = async (id: string) => {
    setMarkingNoticeId(id);
    try {
      await notificationsApi.markRead(id);
      setCompletionNotices((current) =>
        current.map((item) => (item.id === id ? { ...item, read: true } : item)),
      );
    } catch {
      // Keep the item unread; the next refresh will retry the state.
    } finally {
      setMarkingNoticeId(null);
    }
  };

  // One-way repair: push local-only accepted records to the backend so the
  // assigned Role 3 officer actually sees them. Covers assignments made
  // before the backend endpoints existed, or while a save failed. Runs once
  // per region; backendCoversLocal prevents duplicates.
  useEffect(() => {
    if (hydratedFor !== regionKey || !canWrite || officers.length === 0) return;
    if (syncedRegionsRef.current.has(regionKey)) return;
    syncedRegionsRef.current.add(regionKey);
    let cancelled = false;
    (async () => {
      try {
        const backendTasks = await tasksApi.list({ regionKey });
        if (cancelled) return;
        const snapshot = decisionsRef.current;
        const manuals = manualTasksRef.current;
        const assigneeName = (id: string | null) =>
          officers.find((officer) => officer.id === id)?.name ?? null;
        let synced = 0;
        let failed = 0;

        for (const [key, record] of Object.entries(snapshot)) {
          if (!key.startsWith(`${regionKey}#`) || record.status !== 'accepted' || record.backendId) continue;
          const parsed = Number.parseInt(key.slice(regionKey.length + 1), 10);
          if (!Number.isInteger(parsed) || parsed < 0) continue;
          const edited = record.edited;
          if (!edited) continue;
          const label = recommendationLabel(parsed);
          if (backendTasks.some((task) => backendCoversLocal(task, {
            source: 'ai', sourceRef: label, regionKey, title: edited.description, createdAt: record.decidedAt ?? '',
          }))) continue;
          const assigneeId = resolveAssigneeId(officers, record.assigneeUserId, record.team);
          if (!assigneeId) { failed += 1; continue; }
          const persistence = await persistTaskToBackend({
            title: edited.description,
            department: edited.department,
            location: edited.location,
            priority: edited.priority,
            assigneeUserId: assigneeId,
            instructions: record.instructions ?? edited.instructions,
            deadline: record.deadline,
            source: 'ai',
            sourceRef: label,
            regionKey,
          });
          if (cancelled) return;
          if (!persistence.persisted || !persistence.id) { failed += 1; continue; }
          const confirmedId = persistence.id;
          synced += 1;
          setDecisions((current) => ({
            ...current,
            [key]: {
              ...(current[key] ?? pendingReviewRecord()),
              team: assigneeName(assigneeId) ?? current[key]?.team ?? null,
              backendState: 'confirmed',
              backendNote: null,
              backendId: confirmedId,
              assigneeUserId: assigneeId,
            },
          }));
        }

        for (const manual of manuals) {
          if (manual.backendId || manual.backendState === 'confirmed') continue;
          if (backendTasks.some((task) => backendCoversLocal(task, {
            source: 'manual', sourceRef: null, regionKey, title: manual.title, createdAt: manual.createdAt,
          }))) continue;
          const assigneeId = resolveAssigneeId(officers, manual.assigneeUserId, manual.officer ?? manual.team);
          if (!assigneeId) continue; // Still awaiting assignment; leave local.
          const persistence = await persistTaskToBackend({
            title: manual.title,
            department: manual.department,
            location: manual.location,
            priority: manual.priority,
            assigneeUserId: assigneeId,
            instructions: manual.instructions,
            deadline: manual.deadline,
            source: 'manual',
            sourceRef: null,
            regionKey,
          });
          if (cancelled) return;
          if (!persistence.persisted || !persistence.id) { failed += 1; continue; }
          const confirmedId = persistence.id;
          synced += 1;
          setManualTasks((current) => current.map((task) =>
            task.id === manual.id
              ? { ...task, backendState: 'confirmed', backendId: confirmedId, assigneeUserId: assigneeId }
              : task,
          ));
        }

        if (synced > 0) {
          showFeedback('success', `Synced ${synced} pending assignment(s) to the backend — now visible to the field officer.`);
        } else if (failed > 0) {
          showFeedback('warning', `${failed} local record(s) could not reach the backend yet and stay local-only.`);
        }
      } catch {
        // Backend unreachable: local records stay as-is; next visit retries.
        syncedRegionsRef.current.delete(regionKey);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydratedFor, regionKey, canWrite, officers]);

  useEffect(() => {
    if (hydratedFor !== regionKey) return;
    saveStoredState(regionKey, {
      version: REVIEW_STORAGE_VERSION,
      decisions,
      manualTasks,
      alertRecords,
    });
  }, [hydratedFor, regionKey, decisions, manualTasks, alertRecords]);

  useEffect(() => {
    let cancelled = false;
    setUserLoading(true);
    setUserError(null);
    verifyToken()
      .then((user) => {
        if (!cancelled) setCurrentUser(user);
      })
      .catch((fetchError: unknown) => {
        if (!cancelled) {
          setCurrentUser(null);
          setUserError(fetchError instanceof Error ? fetchError.message : 'Unable to verify the session.');
        }
      })
      .finally(() => {
        if (!cancelled) setUserLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getUsers()
      .then((users) => {
        if (!cancelled) {
          setOfficers(users.filter((user) => user.roleId === 'role_3' && user.isActive));
          setOfficersError(null);
        }
      })
      .catch((fetchError: unknown) => {
        if (!cancelled) {
          setOfficers([]);
          setOfficersError(
            fetchError instanceof Error ? fetchError.message : 'Role 3 roster is unavailable.',
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setAlertsLoading(true);
    setAlertsError(null);
    api
      .getClimateAlerts(controller.signal)
      .then((alerts) => setRecentAlerts(alerts.filter((alert) => !alert.is_simulation).slice(0, 6)))
      .catch((fetchError: unknown) => {
        if (fetchError instanceof Error && fetchError.name === 'AbortError') return;
        setRecentAlerts([]);
        setAlertsError(fetchError instanceof Error ? fetchError.message : 'Alerts are unavailable.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setAlertsLoading(false);
      });
    api
      .getWhatsAppConfiguration(controller.signal)
      .then((config) => setWaConfig(config))
      .catch(() => setWaConfig(null));
    return () => controller.abort();
  }, [alertsRefresh]);

  useEffect(() => {
    const intervalId = window.setInterval(() => setCurrentTime(Date.now()), 1000);
    return () => window.clearInterval(intervalId);
  }, []);

  const keys = useMemo(
    () => recommendations.map((_, index) => recommendationKey(regionKey, index)),
    [recommendations, regionKey],
  );
  const counts = useMemo(() => reviewCounts(decisions, keys), [decisions, keys]);

  const operationalTasks = useMemo(() => {
    const accepted = recommendations
      .map((rec, index) =>
        buildOperationalTaskFromDecision({ index, rec, decision: decisions[keys[index]] }),
      )
      .filter((task): task is OperationalTask => task !== null);
    return [...accepted, ...manualTasks].sort((left, right) =>
      right.createdAt.localeCompare(left.createdAt),
    );
  }, [recommendations, decisions, keys, manualTasks]);

  const summary = useMemo(() => summarizeAssignments(operationalTasks), [operationalTasks]);

  const auditEntries = useMemo<AuditEntry[]>(() => {
    const entries: AuditEntry[] = [];
    for (let index = 0; index < recommendations.length; index += 1) {
      const record = decisions[keys[index]];
      if (!record || record.status === 'pending') continue;
      const label = recommendationLabel(index);
      if (record.status === 'accepted') {
        entries.push({
          at: record.decidedAt ?? '',
          item: label,
          action: 'Accepted & assigned',
          detail: `${record.team ?? 'Unassigned'}${record.officer ? ` · ${record.officer}` : ''}${record.deadline ? ` · due ${formatDateTime(record.deadline)}` : ''}`,
          officer: record.decidedBy ?? '—',
          tone: 'green',
        });
      } else {
        entries.push({
          at: record.decidedAt ?? '',
          item: label,
          action: 'Rejected',
          detail: record.rejectionReason ?? 'No reason recorded.',
          officer: record.decidedBy ?? '—',
          tone: 'red',
        });
      }
      if (record.edited && record.editedAt) {
        entries.push({
          at: record.editedAt,
          item: label,
          action: 'Edited before review',
          detail: record.edited.description,
          officer: record.decidedBy ?? '—',
          tone: 'amber',
        });
      }
    }
    for (const task of manualTasks) {
      entries.push({
        at: task.createdAt,
        item: task.id,
        action: 'Manual task created',
        detail: `${task.title} · ${task.team ?? 'Awaiting assignment'}`,
        officer: task.createdBy ?? '—',
        tone: 'slate',
      });
    }
    for (const alert of alertRecords) {
      const sent = alert.status === 'sent';
      entries.push({
        at: alert.createdAt,
        item: sent ? 'Alert sent' : 'Alert draft',
        action: sent ? 'Alert sent' : 'Alert saved (not sent)',
        detail: `${alert.recipientTeam}: ${alert.message.slice(0, 120)}${alert.message.length > 120 ? '…' : ''}`,
        officer: alert.createdBy ?? '—',
        tone: sent ? 'green' : 'amber',
      });
    }
    return entries.sort((left, right) => right.at.localeCompare(left.at));
  }, [recommendations, decisions, keys, manualTasks, alertRecords]);

  const showFeedback = (tone: FeedbackTone, message: string) => {
    setFeedback({ tone, message });
  };

  const requireWriter = (): boolean => {
    if (canWrite) return true;
    showFeedback('error', 'Read-only access: task review and assignment require the Operations Planner (Role 2) role.');
    return false;
  };

  const openAssign = (index: number) => {
    if (!requireWriter()) return;
    const rec = recommendations[index];
    if (!rec) return;
    const record = decisions[keys[index]] ?? pendingReviewRecord();
    const effective = effectiveRecommendation(rec, record.edited);
    setAssignDraft({
      description: effective.description,
      department: effective.department,
      location: effective.location,
      priority: effective.priority,
      team: '',
      officer: '',
      assigneeId: record.assigneeUserId ?? officers[0]?.id ?? '',
      instructions: record.instructions ?? record.edited?.instructions ?? '',
      deadline: toDatetimeLocalValue(record.deadline) || defaultDeadlineValue(),
      notifyTeam: record.notifyRequested,
    });
    setAssignError(null);
    setAssignIndex(index);
  };

  const confirmAssign = async () => {
    if (assignIndex === null || !assignDraft || !requireWriter()) return;
    if (!assignDraft.description.trim() || !assignDraft.department.trim() || !assignDraft.location.trim()) {
      setAssignError('Task description, department, and location are required.');
      return;
    }
    const assignee = officers.find((officer) => officer.id === assignDraft.assigneeId) ?? role3Officer;
    if (!assignee) {
      setAssignError(officersError ?? 'The Role 3 roster is still loading. Wait a moment and retry.');
      return;
    }
    if (!assignDraft.deadline) {
      setAssignError('Set a deadline for the field team.');
      return;
    }
    setAssignSaving(true);
    try {
      const label = recommendationLabel(assignIndex);
      const now = new Date().toISOString();
      const deadlineIso = new Date(assignDraft.deadline).toISOString();
      const existing = decisions[keys[assignIndex]];
      const taskInput: CreateTaskInput = {
        title: assignDraft.description.trim(),
        department: assignDraft.department.trim(),
        location: assignDraft.location.trim(),
        priority: assignDraft.priority,
        assigneeUserId: assignee.id,
        instructions: assignDraft.instructions.trim(),
        deadline: deadlineIso,
        source: 'ai',
        sourceRef: label,
        regionKey,
        notifyAssignee: assignDraft.notifyTeam,
      };
      // Backend-only: the assignment is stored in the task backend first, and
      // the local record is created only after the server confirms — so the
      // assigned Role 3 officer can always read it. Failures keep the dialog
      // open with an error instead of a misleading local record.
      let backendId: string | null = existing?.backendId ?? null;
      if (backendId) {
        const updated = await updateTaskOnBackend(backendId, {
          title: taskInput.title,
          department: taskInput.department,
          location: taskInput.location,
          priority: taskInput.priority,
          instructions: taskInput.instructions,
          deadline: deadlineIso,
          assigneeUserId: assignee.id,
          notifyAssignee: assignDraft.notifyTeam,
        });
        if (!updated.persisted) {
          setAssignError(`Backend save failed: ${updated.note} The assignment was not recorded — retry.`);
          return;
        }
      } else {
        const persistence = await persistTaskToBackend(taskInput);
        if (!persistence.persisted || !persistence.id) {
          setAssignError(`Backend save failed: ${persistence.note} The assignment was not recorded — retry.`);
          return;
        }
        backendId = persistence.id;
      }
      setDecisions((current) => ({
        ...current,
        [keys[assignIndex]]: {
          ...(current[keys[assignIndex]] ?? pendingReviewRecord()),
          status: 'accepted',
          edited: {
            description: assignDraft.description.trim(),
            department: assignDraft.department.trim(),
            location: assignDraft.location.trim(),
            priority: assignDraft.priority,
            instructions: assignDraft.instructions.trim(),
          },
          editedAt: now,
          rejectionReason: null,
          decidedAt: now,
          decidedBy: userName,
          team: assignee.name,
          officer: null,
          deadline: deadlineIso,
          instructions: assignDraft.instructions.trim(),
          notifyRequested: assignDraft.notifyTeam,
          backendState: 'confirmed',
          backendNote: null,
          backendId,
          assigneeUserId: assignee.id,
        },
      }));
      if (assignDraft.notifyTeam) {
        // The backend auto-creates the in-app notification on assignment, so
        // no separate dispatch is needed here (that would deliver it twice).
        // Pull the confirmed record so the alert history shows it immediately.
        try {
          const sent = await notificationsApi.list('sent');
          const match = sent.notifications.find((item) => item.taskId === backendId);
          if (match) {
            setAlertRecords((current) => {
              if (current.some((alert) => alert.id === match.id)) return current;
              return [
                {
                  id: match.id,
                  createdAt: match.createdAt,
                  createdBy: match.senderName || null,
                  recipientTeam: match.recipientName,
                  message: match.message,
                  priority: match.priority,
                  status: 'sent' as const,
                  statusNote: 'Delivered to the field officer inbox',
                },
                ...current,
              ];
            });
          }
        } catch {
          // The alert history refreshes from the backend on the next visit.
        }
        showFeedback(
          'success',
          `${label} assigned to ${assignee.name} and confirmed by the backend. The officer was notified in-app and the task is visible on the Field Operations page.`,
        );
      } else {
        showFeedback(
          'success',
          `${label} assigned to ${assignee.name} and confirmed by the backend. It is now visible on the Field Operations page (no notification was sent).`,
        );
      }
      setAssignIndex(null);
      setAssignDraft(null);
    } catch (saveError) {
      setAssignError(saveError instanceof Error ? saveError.message : 'Unable to save the assignment.');
    } finally {
      setAssignSaving(false);
    }
  };

  const openReject = (index: number) => {
    if (!requireWriter()) return;
    const record = decisions[keys[index]];
    setRejectReason(record?.rejectionReason ?? '');
    setRejectError(null);
    setRejectIndex(index);
  };

  const confirmReject = async () => {
    if (rejectIndex === null || !requireWriter()) return;
    if (rejectReason.trim().length < 4) {
      setRejectError('Record a short rejection reason for the audit history.');
      return;
    }
    setRejectSaving(true);
    try {
      // Rejections need no backend task record; they stay in the audit history.
      const now = new Date().toISOString();
      setDecisions((current) => ({
        ...current,
        [keys[rejectIndex]]: {
          ...(current[keys[rejectIndex]] ?? pendingReviewRecord()),
          status: 'rejected',
          rejectionReason: rejectReason.trim(),
          decidedAt: now,
          decidedBy: userName,
          backendState: 'local',
          backendNote: 'Rejections are kept in the local audit history.',
        },
      }));
      showFeedback(
        'info',
        `${recommendationLabel(rejectIndex)} rejected and kept in the audit history.`,
      );
      setRejectIndex(null);
      setRejectReason('');
    } catch (saveError) {
      setRejectError(saveError instanceof Error ? saveError.message : 'Unable to record the rejection.');
    } finally {
      setRejectSaving(false);
    }
  };

  const openEdit = (index: number) => {
    if (!requireWriter()) return;
    const rec = recommendations[index];
    if (!rec) return;
    const record = decisions[keys[index]];
    const effective = effectiveRecommendation(rec, record?.edited);
    setEditDraft({
      description: effective.description,
      department: effective.department,
      location: effective.location,
      priority: effective.priority,
      instructions: record?.edited?.instructions ?? '',
    });
    setEditError(null);
    setEditIndex(index);
  };

  const saveEdit = () => {
    if (editIndex === null || !editDraft || !requireWriter()) return;
    if (!editDraft.description.trim() || !editDraft.department.trim() || !editDraft.location.trim()) {
      setEditError('Task description, department, and location are required.');
      return;
    }
    const now = new Date().toISOString();
    setDecisions((current) => ({
      ...current,
      [keys[editIndex]]: {
        ...(current[keys[editIndex]] ?? pendingReviewRecord()),
        status: 'pending',
        edited: {
          description: editDraft.description.trim(),
          department: editDraft.department.trim(),
          location: editDraft.location.trim(),
          priority: editDraft.priority,
          instructions: editDraft.instructions.trim(),
        },
        editedAt: now,
        decidedBy: userName,
      },
    }));
    showFeedback('info', `${recommendationLabel(editIndex)} updated. Review the modified task below, then Accept & Assign.`);
    setEditIndex(null);
    setEditDraft(null);
  };

  const blankDraft = (): AssignmentDraft => ({
    description: '',
    department: 'Municipal Corp',
    location: city.name,
    priority: 'High',
    team: '',
    officer: '',
    assigneeId: '',
    instructions: '',
    deadline: '',
    notifyTeam: true,
  });

  const openCreate = () => {
    if (!requireWriter()) return;
    setEditingManualId(null);
    setCreateDraft(blankDraft());
    setCreateError(null);
    setCreateOpen(true);
  };

  const openEditManual = (task: OperationalTask) => {
    if (!requireWriter()) return;
    setEditingManualId(task.id);
    setCreateDraft({
      description: task.title,
      department: task.department,
      location: task.location,
      priority: task.priority,
      team: task.team ?? '',
      officer: task.officer ?? '',
      assigneeId: task.assigneeUserId ?? '',
      instructions: task.instructions,
      deadline: toDatetimeLocalValue(task.deadline),
      notifyTeam: true,
    });
    setCreateError(null);
    setCreateOpen(true);
  };

  const nextManualId = (): string => {
    const used = new Set(manualTasks.map((task) => task.id));
    let counter = manualTasks.length + 1;
    while (used.has(`M-${String(counter).padStart(2, '0')}`)) counter += 1;
    return `M-${String(counter).padStart(2, '0')}`;
  };

  const confirmCreate = async () => {
    if (!createDraft || !requireWriter()) return;
    if (!createDraft.description.trim() || !createDraft.department.trim() || !createDraft.location.trim()) {
      setCreateError('Task description, department, and location are required.');
      return;
    }
    const editingTask = editingManualId ? manualTasks.find((task) => task.id === editingManualId) : undefined;
    // Auto-send: manual tasks always go to Role 3. Edits keep the previously
    // assigned officer when they are still on the roster.
    const preserved = editingTask?.assigneeUserId
      ? (officers.find((officer) => officer.id === editingTask.assigneeUserId) ?? null)
      : null;
    const assignee = preserved ?? role3Officer;
    if (createDraft.notifyTeam && !assignee) {
      setCreateError(officersError ?? 'The Role 3 roster is still loading. Wait a moment and retry.');
      return;
    }
    setCreateSaving(true);
    try {
      const now = new Date().toISOString();
      const team = assignee?.name ?? editingTask?.team ?? null;
      const officerName = assignee?.name ?? editingTask?.officer ?? null;
      const deadlineIso = createDraft.deadline ? new Date(createDraft.deadline).toISOString() : null;
      let backendId: string | null = editingTask?.backendId ?? null;
      // Backend-only once an officer is assigned: store first, record locally
      // only after the server confirms. Drafts stay local only while the
      // Role 3 roster is unavailable.
      const backendState: 'confirmed' | 'local' = assignee ? 'confirmed' : 'local';
      const backendNote: string | null = assignee
        ? null
        : 'Awaiting auto-send: the Role 3 roster is unavailable right now.';
      if (assignee) {
        if (backendId) {
          const updated = await updateTaskOnBackend(backendId, {
            title: createDraft.description.trim(),
            department: createDraft.department.trim(),
            location: createDraft.location.trim(),
            priority: createDraft.priority,
            instructions: createDraft.instructions.trim(),
            deadline: deadlineIso,
            assigneeUserId: assignee.id,
            notifyAssignee: createDraft.notifyTeam,
          });
          if (!updated.persisted) {
            setCreateError(`Backend save failed: ${updated.note} The task was not recorded — retry.`);
            return;
          }
        } else {
          const persistence = await persistTaskToBackend({
            title: createDraft.description.trim(),
            department: createDraft.department.trim(),
            location: createDraft.location.trim(),
            priority: createDraft.priority,
            assigneeUserId: assignee.id,
            instructions: createDraft.instructions.trim(),
            deadline: deadlineIso,
            source: 'manual',
            sourceRef: null,
            regionKey,
            notifyAssignee: createDraft.notifyTeam,
          });
          if (!persistence.persisted || !persistence.id) {
            setCreateError(`Backend save failed: ${persistence.note} The task was not recorded — retry.`);
            return;
          }
          backendId = persistence.id;
        }
      }
      if (editingManualId) {
        setManualTasks((current) =>
          current.map((task) =>
            task.id === editingManualId
              ? {
                  ...task,
                  title: createDraft.description.trim(),
                  department: createDraft.department.trim(),
                  location: createDraft.location.trim(),
                  priority: createDraft.priority,
                  team,
                  officer: officerName,
                  instructions: createDraft.instructions.trim(),
                  deadline: deadlineIso,
                  backendState,
                  backendId,
                  assigneeUserId: assignee?.id ?? task.assigneeUserId ?? null,
                }
              : task,
          ),
        );
        showFeedback(
          backendState === 'confirmed' ? 'success' : 'warning',
          backendState === 'confirmed'
            ? `${editingManualId} updated and confirmed by the backend.`
            : `${editingManualId} updated as a local draft (${backendNote ?? 'awaiting assignment'}).`,
        );
      } else {
        const id = backendId ? `T-${backendId.slice(0, 6).toUpperCase()}` : nextManualId();
        setManualTasks((current) => [
          {
            id,
            source: 'manual',
            sourceRef: null,
            title: createDraft.description.trim(),
            department: createDraft.department.trim(),
            location: createDraft.location.trim(),
            priority: createDraft.priority,
            team,
            officer: officerName,
            instructions: createDraft.instructions.trim(),
            deadline: deadlineIso,
            createdAt: now,
            createdBy: userName,
            backendState,
            backendId,
            assigneeUserId: assignee?.id ?? null,
          },
          ...current,
        ]);
        showFeedback(
          backendState === 'confirmed' ? 'success' : 'warning',
          backendState === 'confirmed'
            ? `${id} created${team ? ` and assigned to ${team}` : ''}; the backend confirmed the record.`
            : `${id} created as a local draft (${backendNote ?? 'awaiting assignment'}).`,
        );
      }
      if (createDraft.notifyTeam && assignee && backendId) {
        // The backend auto-creates the in-app notification on assignment;
        // refresh the confirmed record instead of dispatching a duplicate.
        try {
          const sent = await notificationsApi.list('sent');
          const match = sent.notifications.find((item) => item.taskId === backendId);
          if (match) {
            setAlertRecords((current) => {
              if (current.some((alert) => alert.id === match.id)) return current;
              return [
                {
                  id: match.id,
                  createdAt: match.createdAt,
                  createdBy: match.senderName || null,
                  recipientTeam: match.recipientName,
                  message: match.message,
                  priority: match.priority,
                  status: 'sent' as const,
                  statusNote: 'Delivered to the field officer inbox',
                },
                ...current,
              ];
            });
          }
        } catch {
          // The alert history refreshes from the backend on the next visit.
        }
      }
      setCreateOpen(false);
      setCreateDraft(null);
      setEditingManualId(null);
    } catch (saveError) {
      setCreateError(saveError instanceof Error ? saveError.message : 'Unable to save the task.');
    } finally {
      setCreateSaving(false);
    }
  };

  const sendAlert = async (event: FormEvent) => {
    event.preventDefault();
    if (!requireWriter()) return;
    if (!role3Officer) {
      showFeedback('error', officersError ?? 'The Role 3 roster is still loading. Wait a moment and retry.');
      return;
    }
    if (composeMessage.trim().length < 10) {
      showFeedback('error', 'Write the alert message (at least 10 characters) before sending it.');
      return;
    }
    setComposeSaving(true);
    try {
      const dispatch = await dispatchAlertToBackend({
        recipientUserId: role3Officer.id,
        message: composeMessage.trim(),
        priority: composePriority,
        regionKey,
      });
      const now = new Date().toISOString();
      setAlertRecords((current) => [
        {
          id: dispatch.id ?? `alert-${Date.now()}`,
          createdAt: now,
          createdBy: userName,
          recipientTeam: role3OfficerName ?? role3Officer.name,
          message: composeMessage.trim(),
          priority: composePriority,
          status: dispatch.sent ? 'sent' : 'not_sent',
          statusNote: dispatch.note,
        },
        ...current,
      ]);
      if (dispatch.sent) {
        showFeedback('success', `Alert sent to ${role3OfficerName}. It is visible in the field officer notification page.`);
        setComposeMessage('');
      } else {
        showFeedback('warning', `Alert for ${role3OfficerName} saved as a draft. ${dispatch.note}`);
      }
    } finally {
      setComposeSaving(false);
    }
  };

  const prefillAlertForTask = (task: OperationalTask) => {
    if (!requireWriter()) return;
    setComposeMessage(
      `Task ${task.id} (${task.priority}): ${task.title} — ${task.location}.` +
        (task.deadline ? ` Due ${formatDateTime(task.deadline)}.` : '') +
        (task.instructions ? ` Instructions: ${task.instructions}` : ''),
    );
    setComposePriority(task.priority);
    showFeedback('info', `Alert draft for ${task.id} is ready in the alert centre below. Review it and save.`);
    window.setTimeout(() => {
      alertSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
  };

  const feedbackClass: Record<FeedbackTone, string> = {
    success: 'border-emerald-700 bg-emerald-50 text-emerald-900',
    warning: 'border-amber-600 bg-amber-50 text-amber-900',
    error: 'border-red-700 bg-red-50 text-red-900',
    info: 'border-blue-800 bg-blue-50 text-blue-900',
  };

  return (
    <div className="space-y-4">
      <div className="border border-[#0f2a4a] bg-[#18365b] text-white shadow-sm">
        <div className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <div className="border border-white/30 bg-white/10 p-2">
              <ShieldCheck size={20} />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-200">
                District Disaster Management · Emergency Task Review
              </p>
              <h2 className="mt-0.5 text-lg font-bold leading-snug">Task Review & Field Assignment</h2>
              <p className="mt-1 text-xs text-blue-100">
                {city.name} · Risk level: {riskLevel ?? 'Unavailable'} · AI brief:{' '}
                {generatedAt ? formatDateTime(generatedAt) : 'Unavailable'}
              </p>
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            {riskZones.some((zone) => zone.color === 'red') && (
              <div
                role="timer"
                aria-label={`48-hour operational window: ${formatCountdown(Math.max(0, operationalDeadline - currentTime))} remaining`}
                className="flex items-center justify-center gap-2 border border-white/40 bg-white/10 px-3 py-2 text-xs font-bold"
              >
                <Clock3 size={14} />
                <span>T-{formatCountdown(Math.max(0, operationalDeadline - currentTime))}</span>
              </div>
            )}
            <button
              type="button"
              onClick={openCreate}
              disabled={!canWrite}
              title={canWrite ? undefined : 'Requires the Operations Planner (Role 2) role'}
              className="inline-flex items-center justify-center gap-1.5 bg-white px-4 py-2 text-xs font-bold text-[#18365b] hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Plus size={15} /> Create Emergency Task
            </button>
            
          </div>
        </div>
        
        <dl className="grid grid-cols-2 gap-px border-t border-white/20 bg-white/20 text-xs lg:grid-cols-4">
          <div className="bg-[#18365b] px-4 py-2.5">
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-blue-200">Reviewing officer</dt>
            <dd className="mt-0.5 font-semibold">
              {userLoading ? 'Verifying session…' : (userName ?? 'Unknown session')}
              {currentUser ? ` · ${currentUser.roleName}` : ''}
            </dd>
          </div>
          <div className="bg-[#18365b] px-4 py-2.5">
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-blue-200">Region</dt>
            <dd className="mt-0.5 font-semibold">{city.name}</dd>
          </div>
          <div className="bg-[#18365b] px-4 py-2.5">
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-blue-200">AI recommendations</dt>
            <dd className="mt-0.5 font-semibold">{recommendations.length} received</dd>
          </div>
          <div className="bg-[#18365b] px-4 py-2.5">
            <dt className="text-[10px] font-semibold uppercase tracking-wide text-blue-200">Review progress</dt>
            <dd className="mt-0.5 font-semibold">
              {counts.pending} pending · {counts.accepted} accepted · {counts.rejected} rejected
            </dd>
          </div>
        </dl>
      </div>

      {feedback && (
        <div role="status" className={`flex items-start justify-between gap-3 border px-3 py-2 text-xs shadow-sm ${feedbackClass[feedback.tone]}`}>
          <span className="leading-5">{feedback.message}</span>
          <button type="button" onClick={() => setFeedback(null)} aria-label="Dismiss message" className="shrink-0 p-0.5 hover:opacity-70">
            <X size={14} />
          </button>
        </div>
      )}

      {!userLoading && !canWrite && (
        <div role="note" className="flex items-start gap-2 border border-slate-300 bg-slate-100 px-3 py-2 text-xs text-slate-700">
          <Eye size={14} className="mt-0.5 shrink-0" />
          <span>
            Read-only access: reviewing, assigning, editing, and alerting require the Operations Planner
            (Role 2) role{currentUser ? `; this session is ${currentUser.roleName}` : ''}.
            {userError ? ` Session check: ${userError}` : ''}
          </span>
        </div>
      )}

      {error && !disasterIntelligence && (
        <div role="status" className="flex items-start gap-2 border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>Data is temporarily unavailable. Retry after sometime.</span>
        </div>
      )}
      {isLoading && (
        <div role="status" aria-live="polite" className="flex items-center gap-2 border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-950">
          <LoaderCircle size={14} className="animate-spin" /> Loading live response recommendations and mapped resources…
        </div>
      )}
      {ingestionError && (
        <div role="status" className="flex items-start gap-2 border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>Ingestion is incomplete: {ingestionError}</span>
        </div>
      )}
      {!isLoading && disasterIntelligence && !hasAssessment && (
        <div role="status" className="border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {disasterIntelligence.message}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCell label="Total accepted tasks" value={summary.total} hint="Accepted AI + manual tasks" />
        <StatCell label="Awaiting assignment" value={summary.awaitingAssignment} hint="No field team recorded" />
        <StatCell label="Assigned to field teams" value={summary.assigned} hint="Synced to the field officer queue" />
        <StatCell
          label="Notifications sent (confirmed)"
          value={alertRecords.filter((alert) => alert.status === 'sent').length}
          hint={`${alertRecords.filter((alert) => alert.status === 'not_sent').length} draft(s) held · visible in field inbox`}
        />
      </div>

      <section className="border border-slate-300 bg-white shadow-sm" aria-label="Field completion updates">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
              <CheckCircle2 size={15} /> Field completion updates
              {completionNotices.filter((notice) => !notice.read).length > 0 && (
                <span className="bg-[#18365b] px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">
                  {completionNotices.filter((notice) => !notice.read).length} new
                </span>
              )}
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Tasks Role 3 marked submitted ({completionTasks.length} completed) and the
              completion notices sent to your inbox.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setCompletionRefresh((value) => value + 1)}
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#18365b] underline underline-offset-2"
          >
            <RotateCcw size={12} /> Refresh
          </button>
        </div>
        <div className="p-4">
          {completionLoading ? (
            <p role="status" className="flex items-center gap-2 border border-slate-200 px-3 py-4 text-xs text-slate-600">
              <LoaderCircle size={14} className="animate-spin" /> Loading completion updates…
            </p>
          ) : completionError ? (
            <div role="alert" className="flex flex-wrap items-center justify-between gap-2 border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <span>{completionError}</span>
              <button type="button" onClick={() => setCompletionRefresh((value) => value + 1)} className="inline-flex shrink-0 items-center gap-1.5 font-semibold underline underline-offset-2">
                <RotateCcw size={13} /> Retry
              </button>
            </div>
          ) : completionTasks.length === 0 && completionNotices.length === 0 ? (
            <p className="border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-600">
              No completed tasks yet. When a field officer marks a task submitted, it will
              appear here and in your notification inbox.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div>
                <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-600">
                  Completed tasks ({completionTasks.length})
                </h4>
                {completionTasks.length === 0 ? (
                  <p className="border border-slate-200 px-3 py-4 text-xs text-slate-600">
                    No submitted tasks for this region yet.
                  </p>
                ) : (
                  <ul className="divide-y divide-slate-200 border border-slate-200">
                    {completionTasks.map((task) => {
                      const latestReport = (task.reports ?? [])[(task.reports ?? []).length - 1];
                      return (
                        <li key={task.id} className="px-3 py-2.5 text-xs">
                          <div className="flex flex-wrap items-center gap-2">
                            <PriorityBadge priority={task.priority} />
                            <span className="inline-flex items-center gap-1 border border-emerald-700 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-800">
                              <CheckCircle2 size={11} /> Completed
                            </span>
                            <time className="ml-auto text-[10px] text-slate-500">{formatDateTime(task.updatedAt)}</time>
                          </div>
                          <p className="mt-1 font-semibold leading-5 text-slate-900">{task.title}</p>
                          <p className="mt-0.5 text-[11px] text-slate-500">
                            {task.assigneeName || 'Field officer'} · {task.location}
                            {(task.reports ?? []).length > 0 ? ` · ${(task.reports ?? []).length} report(s)` : ' · no written report'}
                          </p>
                          {latestReport && (
                            <p className="mt-1 line-clamp-2 border-l-2 border-emerald-600 bg-emerald-50/50 px-2 py-1 text-[11px] leading-4 text-slate-700">
                              {latestReport.text}
                            </p>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
              <div>
                <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-600">
                  Completion notices ({completionNotices.filter((notice) => !notice.read).length} unread)
                </h4>
                {completionNotices.length === 0 ? (
                  <p className="border border-slate-200 px-3 py-4 text-xs text-slate-600">
                    No completion notices in your inbox for this region.
                  </p>
                ) : (
                  <ul className="divide-y divide-slate-200 border border-slate-200">
                    {completionNotices.map((notice) => (
                      <li key={notice.id} className={`px-3 py-2.5 text-xs ${notice.read ? '' : 'bg-blue-50/50'}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          <PriorityBadge priority={notice.priority} />
                          {!notice.read && (
                            <span className="bg-[#18365b] px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">
                              New
                            </span>
                          )}
                          <time className="ml-auto text-[10px] text-slate-500">{formatDateTime(notice.createdAt)}</time>
                        </div>
                        <p className="mt-1 leading-5 text-slate-700">{notice.message}</p>
                        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                          <p className="text-[10px] text-slate-500">From {notice.senderName || 'field officer'}</p>
                          {!notice.read && (
                            <button
                              type="button"
                              disabled={markingNoticeId === notice.id}
                              onClick={() => markCompletionNoticeRead(notice.id)}
                              className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#18365b] underline underline-offset-2 disabled:opacity-50"
                            >
                              <CheckCheck size={13} /> {markingNoticeId === notice.id ? 'Saving…' : 'Mark read'}
                            </button>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      </section>


      <section className="border border-slate-300 bg-white shadow-sm" aria-label="Risk zones and response resources">
        <div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-2.5">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
            <MapPin size={15} /> Risk zones & response resources
          </h3>
          <span className="text-[11px] text-slate-500">
            {riskZones.length} zone(s) · {pois.length} mapped facilities
          </span>
        </div>
        <MapComponent
          cityLabel={city.name}
          bounds={bounds}
          pois={pois}
          riskZones={riskZones}
          isLoading={isLoading}
          emptyMessage="Facility locations were not returned for this region."
        />
        {riskZones.length > 0 && (
          <ul className="grid grid-cols-1 gap-2 border-t border-slate-200 p-3 sm:grid-cols-2 xl:grid-cols-3">
            {riskZones.map((zone) => (
              <li
                key={zone.id}
                className={`border p-3 ${zone.color === 'red' ? 'border-red-300 bg-red-50' : zone.color === 'orange' ? 'border-orange-300 bg-orange-50' : zone.color === 'yellow' ? 'border-amber-300 bg-amber-50' : 'border-emerald-300 bg-emerald-50'}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <strong className="text-xs text-slate-900">{zone.label}</strong>
                  <span className="text-[10px] font-semibold uppercase text-slate-600">{zone.radius_km} km radius</span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-slate-700">
                  {zone.description ?? 'Screening zone from disaster intelligence.'}
                </p>
                {zone.basis?.length ? <p className="mt-1 text-[10px] text-slate-500">Basis: {zone.basis.join(' · ')}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="border border-slate-300 bg-white shadow-sm" aria-label="AI recommended tasks for officer review">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
              <Sparkles size={15} /> AI-Recommended Emergency Tasks — Officer Review
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              {counts.pending} pending · {counts.accepted} accepted · {counts.rejected} rejected · AI
              suggestions require officer review before assignment.
            </p>
          </div>
          <span className="font-mono text-[10px] text-slate-500">ai_analysis.recommended_tasks</span>
        </div>
        {reasoningContext.length > 0 && (
          <details className="border-b border-slate-200 px-4 py-2 text-xs text-slate-600">
            <summary className="cursor-pointer font-semibold text-[#18365b]">
              AI reasoning context ({reasoningContext.length})
            </summary>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 leading-5">
              {reasoningContext.map((line, lineIndex) => (
                <li key={`${lineIndex}-${line.slice(0, 24)}`}>{line}</li>
              ))}
            </ul>
          </details>
        )}
        {isLoading && recommendations.length === 0 ? (
          <p role="status" className="flex items-center gap-2 px-4 py-6 text-sm text-slate-600">
            <LoaderCircle size={15} className="animate-spin" /> Loading AI recommendations…
          </p>
        ) : recommendations.length === 0 ? (
          <p className="px-4 py-6 text-sm text-slate-600">
            No AI recommendations were returned for this region.
          </p>
        ) : (
          <div className="divide-y divide-slate-200">
            {recommendations.map((rec, index) => {
              const record = decisions[keys[index]];
              const status = record?.status ?? 'pending';
              const effective = effectiveRecommendation(rec, record?.edited);
              const contextBits = [
                rec.sub_team ? `Suggested team: ${rec.sub_team}` : null,
                rec.status_text ?? null,
              ].filter((bit): bit is string => Boolean(bit));
              return (
                <article key={keys[index]} className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-bold text-slate-500">{recommendationLabel(index)}</span>
                    <span className="inline-flex items-center gap-1 border border-blue-800 bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-900">
                      <Sparkles size={11} /> AI recommended
                    </span>
                    {record?.edited ? (
                      <span className="border border-slate-400 bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-700">
                        Modified by officer
                      </span>
                    ) : null}
                    <PriorityBadge priority={effective.priority} />
                    <span className="ml-auto">
                      <ReviewStatusBadge status={status} />
                    </span>
                  </div>

                  <p className="mt-2 text-sm font-semibold leading-6 text-slate-900">{effective.description}</p>

                  <dl className="mt-2 grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
                    <div className="border border-slate-200 bg-slate-50 px-2.5 py-2">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Recommended department</dt>
                      <dd className="mt-0.5 font-semibold text-slate-800">{effective.department}</dd>
                    </div>
                    <div className="border border-slate-200 bg-slate-50 px-2.5 py-2">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Target location / ward</dt>
                      <dd className="mt-0.5 font-semibold text-slate-800">{effective.location}</dd>
                    </div>
                    <div className="border border-slate-200 bg-slate-50 px-2.5 py-2">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Supporting context</dt>
                      <dd className="mt-0.5 text-slate-700">{contextBits.length > 0 ? contextBits.join(' · ') : 'None provided.'}</dd>
                    </div>
                  </dl>

                  {status === 'accepted' && record && (
                    <div className="mt-3 border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                      <p className="leading-5">
                        <strong>Assigned to {record.team ?? '—'}</strong>
                        {record.officer ? ` · Officer: ${record.officer}` : ''}
                        {record.deadline ? ` · Due ${formatDateTime(record.deadline)}` : ''}
                      </p>
                      {record.instructions ? <p className="mt-1 leading-5">Instructions: {record.instructions}</p> : null}
                      <p className="mt-1 text-[11px] leading-5">
                        Decided by {record.decidedBy ?? '—'} · {formatDateTime(record.decidedAt)} ·{' '}
                        <BackendStateLine state={record.backendState} note={record.backendNote} />
                      </p>
                    </div>
                  )}
                  {status === 'rejected' && record && (
                    <div className="mt-3 border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
                      <p className="leading-5"><strong>Rejected:</strong> {record.rejectionReason ?? 'No reason recorded.'}</p>
                      <p className="mt-1 text-[11px] leading-5">
                        Decided by {record.decidedBy ?? '—'} · {formatDateTime(record.decidedAt)} · Rejection
                        preserved in the audit history below.
                      </p>
                    </div>
                  )}

                  {status === 'pending' ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button type="button" onClick={() => openAssign(index)} disabled={!canWrite} className={primaryButtonClass}>
                        <CheckCircle2 size={13} /> Accept & Assign
                      </button>
                      <button type="button" onClick={() => openEdit(index)} disabled={!canWrite} className={outlineButtonClass}>
                        <Pencil size={13} /> Edit
                      </button>
                      <button type="button" onClick={() => openReject(index)} disabled={!canWrite} className={dangerOutlineButtonClass}>
                        <XCircle size={13} /> Reject
                      </button>
                    </div>
                  ) : status === 'accepted' ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button type="button" onClick={() => openAssign(index)} disabled={!canWrite} className={outlineButtonClass}>
                        <Pencil size={13} /> Edit assignment
                      </button>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="border border-slate-300 bg-white shadow-sm" aria-label="Task assignment overview">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
            <ClipboardList size={15} /> Task Assignment Overview
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Administrative assignment record — detailed field tracking will be handled on a separate
            operational screen.
          </p>
        </div>
        {operationalTasks.length === 0 ? (
          <p className="px-4 py-6 text-sm text-slate-600">
            No tasks accepted or created yet. Accepted AI recommendations and manual tasks will appear here.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1020px] text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2 font-semibold">Task ID</th>
                  <th className="px-3 py-2 font-semibold">Description</th>
                  <th className="px-3 py-2 font-semibold">Department</th>
                  <th className="px-3 py-2 font-semibold">Location</th>
                  <th className="px-3 py-2 font-semibold">Priority</th>
                  <th className="px-3 py-2 font-semibold">Assigned to</th>
                  <th className="px-3 py-2 font-semibold">Assignment date</th>
                  <th className="px-3 py-2 font-semibold">Status</th>
                  <th className="px-3 py-2 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {operationalTasks.map((task) => (
                  <tr key={task.id} className="align-top hover:bg-slate-50">
                    <td className="px-3 py-2.5">
                      <span className="font-mono font-bold text-[#18365b]">{task.id}</span>
                      <div className="mt-1">
                        <SourceBadge source={task.source} />
                      </div>
                    </td>
                    <td className="max-w-72 px-3 py-2.5 font-medium leading-5 text-slate-900">{task.title}</td>
                    <td className="px-3 py-2.5 text-slate-700">{task.department}</td>
                    <td className="px-3 py-2.5 text-slate-700">{task.location}</td>
                    <td className="px-3 py-2.5">
                      <PriorityBadge priority={task.priority} />
                    </td>
                    <td className="px-3 py-2.5 text-slate-700">
                      {task.team ?? <span className="font-semibold text-amber-800">Awaiting assignment</span>}
                      {task.officer ? <div className="mt-0.5 text-[11px] text-slate-500">{task.officer}</div> : null}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-slate-700">{formatDateTime(task.createdAt)}</td>
                    <td className="px-3 py-2.5">
                      <BackendStateLine
                        state={task.backendState}
                        note={task.backendState === 'confirmed' ? null : 'Stored locally; awaiting backend confirmation.'}
                      />
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1.5">
                        <button
                          type="button"
                          title="View details"
                          aria-label={`View details of ${task.id}`}
                          onClick={() => setDetailTask(task)}
                          className="border border-slate-300 p-1.5 text-slate-600 hover:bg-slate-100"
                        >
                          <Eye size={13} />
                        </button>
                        <button
                          type="button"
                          title="Edit assignment"
                          aria-label={`Edit assignment of ${task.id}`}
                          disabled={!canWrite}
                          onClick={() => {
                            if (task.source === 'ai' && task.sourceRef) {
                              const parsed = Number.parseInt(task.sourceRef.slice(3), 10) - 1;
                              if (Number.isInteger(parsed) && parsed >= 0) openAssign(parsed);
                            } else {
                              openEditManual(task);
                            }
                          }}
                          className="border border-slate-300 p-1.5 text-slate-600 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          type="button"
                          title={role3Officer ? 'Prepare alert for Role 3' : 'Role 3 roster unavailable'}
                          aria-label={`Prepare alert for ${task.id}`}
                          disabled={!canWrite || !role3Officer}
                          onClick={() => prefillAlertForTask(task)}
                          className="border border-slate-300 p-1.5 text-slate-600 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <Send size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section
        ref={alertSectionRef}
        className="scroll-mt-4 border border-slate-300 bg-white shadow-sm"
        aria-label="Notifications and alerts"
      >
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
            <BellRing size={15} /> Notifications & Alerts — Role 2 Alert Centre
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Recent backend alerts, delivery status, and operational alert drafts for assigned Role 3 teams.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
          <div className="space-y-4">
            <div>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">Recent alerts (backend)</h4>
                <button
                  type="button"
                  onClick={() => setAlertsRefresh((value) => value + 1)}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#18365b] underline underline-offset-2"
                >
                  <RotateCcw size={12} /> Refresh
                </button>
              </div>
              {alertsLoading ? (
                <p role="status" className="flex items-center gap-2 border border-slate-200 px-3 py-4 text-xs text-slate-600">
                  <LoaderCircle size={14} className="animate-spin" /> Loading recent alerts…
                </p>
              ) : alertsError ? (
                <p role="alert" className="border border-amber-300 bg-amber-50 px-3 py-3 text-xs text-amber-900">
                  {alertsError}
                </p>
              ) : recentAlerts.length === 0 ? (
                <p className="border border-slate-200 px-3 py-4 text-xs text-slate-600">
                  No alerts have been published for the monitored regions yet.
                </p>
              ) : (
                <ul className="divide-y divide-slate-200 border border-slate-200">
                  {recentAlerts.map((alert) => (
                    <li key={alert.id} className="px-3 py-2.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${PRIORITY_BADGE[alert.severity === 'critical' ? 'Critical' : alert.severity === 'high' ? 'High' : alert.severity === 'moderate' ? 'Medium' : 'Low']}`}
                        >
                          {alert.severity}
                        </span>
                        <time className="ml-auto text-[10px] text-slate-500">{formatDateTime(alert.received_at)}</time>
                      </div>
                      <p className="mt-1 text-xs font-semibold leading-5 text-slate-900">{alert.title}</p>
                      <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-slate-600">{alert.description}</p>
                      <p className="mt-1 text-[10px] text-slate-500">{alert.location.name} · {alert.source}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="border border-slate-200">
              <h4 className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold uppercase tracking-wide text-slate-600">
                Delivery status
              </h4>
              <ul className="space-y-1.5 px-3 py-2.5 text-xs text-slate-700">
                <li>
                  WhatsApp verification:{' '}
                  <strong>{waConfig ? (waConfig.verification_configured ? 'Configured' : 'Not configured') : 'Unknown'}</strong>
                </li>
                <li>
                  WhatsApp delivery:{' '}
                  <strong>{waConfig ? (waConfig.delivery_configured ? 'Configured' : 'Not configured') : 'Unknown'}</strong>
                </li>
                <li>
                  Operational dispatch: <strong>Available</strong> — sent alerts reach the field officer inbox.
                </li>
              </ul>
            </div>
          </div>

          <div className="space-y-4">
            <form onSubmit={sendAlert} className="space-y-3 border border-slate-200 p-3">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">Send operational alert</h4>
                <p className="mt-1 text-[11px] leading-4 text-slate-500">
                  Sent alerts appear in the recipient&apos;s notification page. Failed sends are kept
                  as local drafts and marked not sent.
                </p>
              </div>
              <div className="border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Recipient (Role 3)</p>
                <p className="mt-0.5 font-semibold text-slate-800">
                  {role3OfficerName ?? (officersError ? 'Role 3 roster unavailable' : 'Loading Role 3 roster…')}
                </p>
              </div>
              <Field label="Priority">
                <select
                  value={composePriority}
                  onChange={(event) => setComposePriority(event.target.value as TaskPriority)}
                  disabled={!canWrite}
                  className={inputClass}
                >
                  {PRIORITIES.map((priority) => (
                    <option key={priority} value={priority}>
                      {priority}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Message" required>
                <textarea
                  value={composeMessage}
                  onChange={(event) => setComposeMessage(event.target.value)}
                  rows={4}
                  disabled={!canWrite}
                  placeholder="Alert text for the field team…"
                  className={`${inputClass} resize-y`}
                />
              </Field>
              <button type="submit" disabled={composeSaving || !canWrite} className={primaryButtonClass}>
                <Send size={13} /> {composeSaving ? 'Saving…' : 'Send alert'}
              </button>
            </form>

            <div>
              <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-600">
                Alert history ({alertRecords.filter((alert) => alert.status === 'sent').length} sent ·{' '}
                {alertRecords.filter((alert) => alert.status === 'not_sent').length} draft(s))
              </h4>
              {alertRecords.length === 0 ? (
                <p className="border border-slate-200 px-3 py-4 text-xs text-slate-600">
                  No alerts yet. Sent alerts and any local drafts are listed here with their honest
                  delivery state.
                </p>
              ) : (
                <ul className="divide-y divide-slate-200 border border-slate-200">
                  {alertRecords.map((alert) => (
                    <li key={alert.id} className="px-3 py-2.5 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <strong className="text-slate-900">{alert.recipientTeam}</strong>
                        <PriorityBadge priority={alert.priority} />
                        {alert.status === 'sent' ? (
                          <span className="ml-auto border border-emerald-700 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-800">
                            Sent
                          </span>
                        ) : (
                          <span className="ml-auto border border-red-700 bg-red-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-red-800">
                            Not sent
                          </span>
                        )}
                      </div>
                      <p className="mt-1 leading-5 text-slate-700">{alert.message}</p>
                      <p className="mt-1 text-[10px] text-slate-500">
                        {formatDateTime(alert.createdAt)} · by {alert.createdBy ?? '—'} · {alert.statusNote}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="border border-slate-300 bg-white shadow-sm" aria-label="Decision and audit history">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
            <History size={15} /> Decision & Audit History
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Acceptances, rejections, edits, manual tasks, and alerts for this region.
          </p>
        </div>
        {auditEntries.length === 0 ? (
          <p className="px-4 py-6 text-sm text-slate-600">
            No decisions recorded yet for this region. Reviews will be listed here with timestamps and reasons.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2 font-semibold">Time</th>
                  <th className="px-3 py-2 font-semibold">Item</th>
                  <th className="px-3 py-2 font-semibold">Action</th>
                  <th className="px-3 py-2 font-semibold">Detail</th>
                  <th className="px-3 py-2 font-semibold">Officer</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {auditEntries.map((entry, entryIndex) => (
                  <tr key={`${entry.at}-${entry.item}-${entryIndex}`} className="align-top hover:bg-slate-50">
                    <td className="whitespace-nowrap px-3 py-2.5 text-slate-700">{formatDateTime(entry.at)}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 font-mono font-semibold text-slate-800">{entry.item}</td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      <span
                        className={`border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${entry.tone === 'green' ? 'border-emerald-700 bg-emerald-50 text-emerald-800' : entry.tone === 'red' ? 'border-red-700 bg-red-50 text-red-800' : entry.tone === 'amber' ? 'border-amber-600 bg-amber-50 text-amber-900' : 'border-slate-300 bg-slate-100 text-slate-700'}`}
                      >
                        {entry.action}
                      </span>
                    </td>
                    <td className="max-w-md px-3 py-2.5 leading-5 text-slate-700">{entry.detail}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-slate-700">{entry.officer}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="border border-slate-300 bg-slate-50 px-3 py-2 text-[11px] leading-5 text-slate-600">
        Accepted tasks sync to the backend and appear in the assigned field officer&apos;s queue and inbox.
        Anything the backend has not confirmed stays labelled as a local record. Role 2 write access is
        enforced in this view and on the backend.
      </p>

      {assignIndex !== null && assignDraft && (
        <Modal
          title={`Accept & Assign ${recommendationLabel(assignIndex)}`}
          subtitle="Review every field before confirming the assignment."
          onClose={() => {
            if (!assignSaving) {
              setAssignIndex(null);
              setAssignDraft(null);
            }
          }}
        >
          <div className="space-y-3">
            <Field label="Task description" required>
              <textarea
                value={assignDraft.description}
                onChange={(event) => setAssignDraft({ ...assignDraft, description: event.target.value })}
                rows={3}
                autoFocus
                className={`${inputClass} resize-y`}
              />
            </Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Department" required hint="Type to use a non-listed department.">
                <input
                  value={assignDraft.department}
                  onChange={(event) => setAssignDraft({ ...assignDraft, department: event.target.value })}
                  list="dept-options-assign"
                  className={inputClass}
                />
                <datalist id="dept-options-assign">
                  {DEPARTMENTS.map((dept) => (
                    <option key={dept} value={dept} />
                  ))}
                </datalist>
              </Field>
              <Field label="Target location / ward" required>
                <input
                  value={assignDraft.location}
                  onChange={(event) => setAssignDraft({ ...assignDraft, location: event.target.value })}
                  className={inputClass}
                />
              </Field>
              <Field label="Priority" required>
                <select
                  value={assignDraft.priority}
                  onChange={(event) => setAssignDraft({ ...assignDraft, priority: event.target.value as TaskPriority })}
                  className={inputClass}
                >
                  {PRIORITIES.map((priority) => (
                    <option key={priority} value={priority}>
                      {priority}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Deadline" required>
                <input
                  type="datetime-local"
                  value={assignDraft.deadline}
                  onChange={(event) => setAssignDraft({ ...assignDraft, deadline: event.target.value })}
                  className={inputClass}
                />
              </Field>
            </div>
            <Field
              label="Assigned to (Role 3)"
              required
              hint={officersError ?? (officers.length === 0 ? 'Loading the Role 3 roster…' : 'Only the selected officer sees this task.')}
            >
              {officers.length > 0 ? (
                <select
                  value={assignDraft.assigneeId || officers[0].id}
                  onChange={(event) => setAssignDraft({ ...assignDraft, assigneeId: event.target.value })}
                  className={inputClass}
                >
                  {officers.map((officer) => (
                    <option key={officer.id} value={officer.id}>
                      {officer.name}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs font-semibold text-slate-800">
                  {officersError ?? 'Loading Role 3 roster…'}
                </div>
              )}
            </Field>
            <Field label="Instructions for the field team">
              <textarea
                value={assignDraft.instructions}
                onChange={(event) => setAssignDraft({ ...assignDraft, instructions: event.target.value })}
                rows={3}
                placeholder="Access routes, equipment, reporting cadence…"
                className={`${inputClass} resize-y`}
              />
            </Field>
            <label className="flex items-start gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                checked={assignDraft.notifyTeam}
                onChange={(event) => setAssignDraft({ ...assignDraft, notifyTeam: event.target.checked })}
                className="mt-0.5 accent-[#18365b]"
              />
              <span>
                Send in-app notification to the assigned officer{' '}
                <span className="text-slate-500">(appears in their notification page)</span>
              </span>
            </label>
            {assignError && (
              <p role="alert" className="border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
                {assignError}
              </p>
            )}
            <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
              <button
                type="button"
                disabled={assignSaving}
                onClick={() => {
                  setAssignIndex(null);
                  setAssignDraft(null);
                }}
                className={outlineButtonClass}
              >
                Cancel
              </button>
              <button type="button" disabled={assignSaving || !role3Officer} onClick={confirmAssign} className={primaryButtonClass}>
                <CheckCircle2 size={13} /> {assignSaving ? 'Confirming…' : 'Confirm Assignment'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {rejectIndex !== null && (
        <Modal
          title={`Reject ${recommendationLabel(rejectIndex)}`}
          subtitle="Confirm the rejection and record a reason for the audit history."
          onClose={() => {
            if (!rejectSaving) setRejectIndex(null);
          }}
        >
          <div className="space-y-3">
            <div className="border border-slate-200 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-700">
              {effectiveRecommendation(
                recommendations[rejectIndex],
                decisions[keys[rejectIndex]]?.edited,
              ).description}
            </div>
            <Field label="Rejection reason" required hint="Kept in the audit history with your name and timestamp.">
              <textarea
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                rows={3}
                autoFocus
                placeholder="e.g. Duplicate of an existing task; area already covered…"
                className={`${inputClass} resize-y`}
              />
            </Field>
            {rejectError && (
              <p role="alert" className="border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
                {rejectError}
              </p>
            )}
            <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
              <button
                type="button"
                disabled={rejectSaving}
                onClick={() => setRejectIndex(null)}
                className={outlineButtonClass}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={rejectSaving}
                onClick={confirmReject}
                className="inline-flex items-center justify-center gap-1.5 bg-red-700 px-3 py-2 text-xs font-semibold text-white hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <XCircle size={13} /> {rejectSaving ? 'Rejecting…' : 'Confirm Rejection'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {editIndex !== null && editDraft && (
        <Modal
          title={`Edit ${recommendationLabel(editIndex)}`}
          subtitle="Changes stay pending for review — accept & assign afterwards."
          onClose={() => {
            setEditIndex(null);
            setEditDraft(null);
          }}
        >
          <div className="space-y-3">
            <Field label="Task description" required>
              <textarea
                value={editDraft.description}
                onChange={(event) => setEditDraft({ ...editDraft, description: event.target.value })}
                rows={3}
                autoFocus
                className={`${inputClass} resize-y`}
              />
            </Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Department" required>
                <input
                  value={editDraft.department}
                  onChange={(event) => setEditDraft({ ...editDraft, department: event.target.value })}
                  list="dept-options-edit"
                  className={inputClass}
                />
                <datalist id="dept-options-edit">
                  {DEPARTMENTS.map((dept) => (
                    <option key={dept} value={dept} />
                  ))}
                </datalist>
              </Field>
              <Field label="Target location / ward" required>
                <input
                  value={editDraft.location}
                  onChange={(event) => setEditDraft({ ...editDraft, location: event.target.value })}
                  className={inputClass}
                />
              </Field>
              <Field label="Priority" required>
                <select
                  value={editDraft.priority}
                  onChange={(event) => setEditDraft({ ...editDraft, priority: event.target.value as TaskPriority })}
                  className={inputClass}
                >
                  {PRIORITIES.map((priority) => (
                    <option key={priority} value={priority}>
                      {priority}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="Instructions for the field team">
              <textarea
                value={editDraft.instructions}
                onChange={(event) => setEditDraft({ ...editDraft, instructions: event.target.value })}
                rows={3}
                placeholder="Access routes, equipment, reporting cadence…"
                className={`${inputClass} resize-y`}
              />
            </Field>
            {editError && (
              <p role="alert" className="border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
                {editError}
              </p>
            )}
            <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
              <button
                type="button"
                onClick={() => {
                  setEditIndex(null);
                  setEditDraft(null);
                }}
                className={outlineButtonClass}
              >
                Cancel
              </button>
              <button type="button" onClick={saveEdit} className={primaryButtonClass}>
                <Pencil size={13} /> Save for Review
              </button>
            </div>
          </div>
        </Modal>
      )}

      {createOpen && createDraft && (
        <Modal
          title={editingManualId ? `Edit Manual Task ${editingManualId}` : 'Create Emergency Task'}
          subtitle="Independent of AI recommendations — saved as a manual task, never AI-generated."
          onClose={() => {
            if (!createSaving) {
              setCreateOpen(false);
              setCreateDraft(null);
              setEditingManualId(null);
            }
          }}
        >
          <div className="space-y-3">
            <Field label="Task title / description" required>
              <textarea
                value={createDraft.description}
                onChange={(event) => setCreateDraft({ ...createDraft, description: event.target.value })}
                rows={3}
                autoFocus
                placeholder="What must the field team do?"
                className={`${inputClass} resize-y`}
              />
            </Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Department" required>
                <input
                  value={createDraft.department}
                  onChange={(event) => setCreateDraft({ ...createDraft, department: event.target.value })}
                  list="dept-options-create"
                  className={inputClass}
                />
                <datalist id="dept-options-create">
                  {DEPARTMENTS.map((dept) => (
                    <option key={dept} value={dept} />
                  ))}
                </datalist>
              </Field>
              <Field label="Location / ward" required>
                <input
                  value={createDraft.location}
                  onChange={(event) => setCreateDraft({ ...createDraft, location: event.target.value })}
                  className={inputClass}
                />
              </Field>
              <Field label="Priority" required>
                <select
                  value={createDraft.priority}
                  onChange={(event) => setCreateDraft({ ...createDraft, priority: event.target.value as TaskPriority })}
                  className={inputClass}
                >
                  {PRIORITIES.map((priority) => (
                    <option key={priority} value={priority}>
                      {priority}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Deadline" hint="Optional for unassigned tasks.">
                <input
                  type="datetime-local"
                  value={createDraft.deadline}
                  onChange={(event) => setCreateDraft({ ...createDraft, deadline: event.target.value })}
                  className={inputClass}
                />
              </Field>
            </div>
            <div className="border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Assigned to (Role 3) · auto-send</p>
              <p className="mt-0.5 font-semibold text-slate-800">
                {role3OfficerName ?? (officersError ? 'Role 3 roster unavailable' : 'Loading Role 3 roster…')}
              </p>
            </div>
            <Field label="Instructions for the field team">
              <textarea
                value={createDraft.instructions}
                onChange={(event) => setCreateDraft({ ...createDraft, instructions: event.target.value })}
                rows={3}
                placeholder="Access routes, equipment, reporting cadence…"
                className={`${inputClass} resize-y`}
              />
            </Field>
            <label className="flex items-start gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                checked={createDraft.notifyTeam}
                onChange={(event) => setCreateDraft({ ...createDraft, notifyTeam: event.target.checked })}
                className="mt-0.5 accent-[#18365b]"
              />
              <span>
                Send in-app notification to the assigned officer{' '}
                <span className="text-slate-500">(appears in their notification page)</span>
              </span>
            </label>
            {createError && (
              <p role="alert" className="border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
                {createError}
              </p>
            )}
            <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
              <button
                type="button"
                disabled={createSaving}
                onClick={() => {
                  setCreateOpen(false);
                  setCreateDraft(null);
                  setEditingManualId(null);
                }}
                className={outlineButtonClass}
              >
                Cancel
              </button>
              <button type="button" disabled={createSaving} onClick={confirmCreate} className={primaryButtonClass}>
                <Plus size={13} /> {createSaving ? 'Saving…' : editingManualId ? 'Save Changes' : 'Create Task'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {detailTask && (
        <Modal
          title={`Task ${detailTask.id}`}
          subtitle="Full assignment record."
          onClose={() => setDetailTask(null)}
        >
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <SourceBadge source={detailTask.source} />
              <PriorityBadge priority={detailTask.priority} />
            </div>
            <p className="font-semibold leading-6 text-slate-900">{detailTask.title}</p>
            <dl className="space-y-2 text-xs">
              <div className="flex items-start gap-2 border border-slate-200 bg-slate-50 px-2.5 py-2">
                <Building2 size={13} className="mt-0.5 shrink-0 text-slate-500" />
                <div><dt className="font-semibold uppercase tracking-wide text-slate-500">Department</dt><dd className="mt-0.5 text-slate-800">{detailTask.department}</dd></div>
              </div>
              <div className="flex items-start gap-2 border border-slate-200 bg-slate-50 px-2.5 py-2">
                <MapPin size={13} className="mt-0.5 shrink-0 text-slate-500" />
                <div><dt className="font-semibold uppercase tracking-wide text-slate-500">Location</dt><dd className="mt-0.5 text-slate-800">{detailTask.location}</dd></div>
              </div>
              <div className="flex items-start gap-2 border border-slate-200 bg-slate-50 px-2.5 py-2">
                <Users size={13} className="mt-0.5 shrink-0 text-slate-500" />
                <div><dt className="font-semibold uppercase tracking-wide text-slate-500">Assigned team / officer</dt><dd className="mt-0.5 text-slate-800">{detailTask.team ?? 'Awaiting assignment'}{detailTask.officer ? ` · ${detailTask.officer}` : ''}</dd></div>
              </div>
              <div className="flex items-start gap-2 border border-slate-200 bg-slate-50 px-2.5 py-2">
                <CalendarClock size={13} className="mt-0.5 shrink-0 text-slate-500" />
                <div><dt className="font-semibold uppercase tracking-wide text-slate-500">Deadline</dt><dd className="mt-0.5 text-slate-800">{formatDateTime(detailTask.deadline)}</dd></div>
              </div>
              <div className="flex items-start gap-2 border border-slate-200 bg-slate-50 px-2.5 py-2">
                <FileText size={13} className="mt-0.5 shrink-0 text-slate-500" />
                <div><dt className="font-semibold uppercase tracking-wide text-slate-500">Instructions</dt><dd className="mt-0.5 leading-5 text-slate-800">{detailTask.instructions || 'None recorded.'}</dd></div>
              </div>
              <div className="flex items-start gap-2 border border-slate-200 bg-slate-50 px-2.5 py-2">
                <Clock3 size={13} className="mt-0.5 shrink-0 text-slate-500" />
                <div><dt className="font-semibold uppercase tracking-wide text-slate-500">Record</dt><dd className="mt-0.5 text-slate-800">Created {formatDateTime(detailTask.createdAt)} · by {detailTask.createdBy ?? '—'} · <BackendStateLine state={detailTask.backendState} note={null} /></dd></div>
              </div>
            </dl>
            <div className="flex justify-end border-t border-slate-200 pt-3">
              <button type="button" onClick={() => setDetailTask(null)} className={outlineButtonClass}>
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};


