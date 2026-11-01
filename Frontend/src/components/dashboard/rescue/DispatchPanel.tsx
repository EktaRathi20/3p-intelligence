import { useMemo, useState, type FormEvent } from 'react';
import {
  Ambulance,
  CheckCircle2,
  ChevronDown,
  LoaderCircle,
  MapPin,
  Play,
  Plus,
  Search,
  ShieldAlert,
} from 'lucide-react';
import type { BackendTask } from '@/services/operationalApi';
import { tasksApi } from '@/services/operationalApi';
import type { AuthUser, OfficerUser } from '@/types';
import type { MapPOI } from '@/types/domain';
import type { TaskPriority } from '@/utils/taskReview';
import type { SessionEvent } from './useCommandCentreData';
import {
  ConfirmDialog,
  DataBadge,
  EmptyState,
  ErrorState,
  formatAge,
  formatDateTime,
  inputClass,
  outlineButtonClass,
  primaryButtonClass,
  SectionCard,
} from './rescueShared';

export const DISPATCH_DEPARTMENTS = [
  'Fire & Rescue',
  'Health & EMS',
  'NDRF',
  'Police',
  'Municipal Corp',
  'PWD Water Supply',
  'Power Utility',
  'Revenue Department',
];

const PRIORITIES: TaskPriority[] = ['Critical', 'High', 'Medium', 'Low'];

const PRIORITY_BADGE: Record<TaskPriority, string> = {
  Critical: 'border-red-700 bg-red-700 text-white',
  High: 'border-orange-600 bg-orange-50 text-orange-800',
  Medium: 'border-amber-500 bg-amber-50 text-amber-900',
  Low: 'border-slate-300 bg-slate-100 text-slate-700',
};

const STATUS_BADGE: Record<BackendTask['status'], string> = {
  Assigned: 'bg-slate-100 text-slate-700',
  'In Progress': 'bg-blue-50 text-blue-800',
  Submitted: 'bg-emerald-50 text-emerald-800',
};

type StatusFilter = 'All' | BackendTask['status'];

interface DispatchForm {
  title: string;
  department: string;
  location: string;
  destinationPoiId: string;
  priority: TaskPriority;
  assigneeUserId: string;
  instructions: string;
  deadline: string;
  notifyAssignee: boolean;
}

const emptyForm = (): DispatchForm => ({
  title: '',
  department: DISPATCH_DEPARTMENTS[0],
  location: '',
  destinationPoiId: '',
  priority: 'High',
  assigneeUserId: '',
  instructions: '',
  deadline: '',
  notifyAssignee: true,
});

export function DispatchPanel({
  tasks,
  tasksLoading,
  tasksError,
  officers,
  officersError,
  currentUser,
  planner,
  regionKey,
  pois,
  upsertTask,
  logSessionEvent,
  onRefresh,
}: {
  tasks: BackendTask[];
  tasksLoading: boolean;
  tasksError: string | null;
  officers: OfficerUser[];
  officersError: string | null;
  currentUser: AuthUser | null;
  planner: boolean;
  regionKey: string;
  pois: MapPOI[];
  upsertTask: (task: BackendTask) => void;
  logSessionEvent: (event: Omit<SessionEvent, 'id' | 'at'>) => void;
  onRefresh: () => void;
}) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('All');
  const [query, setQuery] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<DispatchForm>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [pendingCreate, setPendingCreate] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [pendingStatus, setPendingStatus] = useState<{ task: BackendTask; status: BackendTask['status'] } | null>(null);
  const [statusBusy, setStatusBusy] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [reassignDraft, setReassignDraft] = useState<Record<string, string>>({});
  const [pendingReassign, setPendingReassign] = useState<{ task: BackendTask; assigneeUserId: string } | null>(null);
  const [reassignBusy, setReassignBusy] = useState(false);
  const [reassignError, setReassignError] = useState<string | null>(null);

  const activeOfficers = useMemo(
    () => officers.filter((officer) => officer.isActive !== false),
    [officers],
  );

  const visibleTasks = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return tasks
      .filter((task) => statusFilter === 'All' || task.status === statusFilter)
      .filter((task) =>
        !needle ||
        `${task.title} ${task.location} ${task.department} ${task.assigneeName}`.toLowerCase().includes(needle),
      )
      .slice()
      .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
  }, [tasks, statusFilter, query]);

  const counts = useMemo(
    () => ({
      Assigned: tasks.filter((t) => t.status === 'Assigned').length,
      'In Progress': tasks.filter((t) => t.status === 'In Progress').length,
      Submitted: tasks.filter((t) => t.status === 'Submitted').length,
    }),
    [tasks],
  );

  const canUpdate = (task: BackendTask) =>
    planner || (currentUser != null && task.assigneeUserId === currentUser.id);

  const officerName = (id: string) =>
    officers.find((officer) => officer.id === id)?.name ?? 'Unknown officer';

  const destinationName = () => {
    if (!form.destinationPoiId) return null;
    const poi = pois.find((item) => item.id === form.destinationPoiId);
    return poi ? `${poi.name}${poi.details ? ` — ${poi.details}` : ''}` : null;
  };

  const formatDeadlinePreview = () => {
    if (!form.deadline) return '';
    const parsed = new Date(form.deadline);
    if (Number.isNaN(parsed.getTime())) return '';
    return ` · Deadline ${formatDateTime(parsed.toISOString())}`;
  };

  const openCreateConfirm = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    if (!planner) {
      setFormError('Only the Operations Planner (Role 2) can create dispatches.');
      return;
    }
    if (!form.title.trim() || !form.location.trim() || !form.assigneeUserId) {
      setFormError('Title, pickup / staging location and assigned team are required.');
      return;
    }
    setCreateError(null);
    setPendingCreate(true);
  };

  const confirmCreate = async () => {
    setCreateBusy(true);
    setCreateError(null);
    const destination = destinationName();
    try {
      const created = await tasksApi.create({
        title: form.title.trim(),
        department: form.department,
        location: form.location.trim(),
        priority: form.priority,
        assigneeUserId: form.assigneeUserId,
        instructions: [
          form.instructions.trim(),
          destination ? `Destination: ${destination}.` : '',
        ]
          .filter(Boolean)
          .join('\n'),
        deadline: form.deadline ? new Date(form.deadline).toISOString() : null,
        source: 'manual',
        regionKey,
        notifyAssignee: form.notifyAssignee,
      });
      upsertTask(created);
      logSessionEvent({
        title: `Dispatch created: ${created.title}`,
        detail: `${created.department} → ${created.assigneeName}. Backend-confirmed as ${created.id.slice(0, 8)}.`,
        tone: 'green',
      });
      setForm(emptyForm());
      setFormOpen(false);
      setPendingCreate(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to create the dispatch.';
      setCreateError(message);
      logSessionEvent({
        title: `Dispatch failed: ${form.title.trim() || 'untitled'}`,
        detail: message,
        tone: 'red',
      });
    } finally {
      setCreateBusy(false);
    }
  };

  const confirmStatusChange = async () => {
    if (!pendingStatus) return;
    setStatusBusy(true);
    setStatusError(null);
    try {
      const updated = await tasksApi.update(pendingStatus.task.id, { status: pendingStatus.status });
      upsertTask(updated);
      logSessionEvent({
        title: `Dispatch ${pendingStatus.status.toLowerCase()}: ${updated.title}`,
        detail: `Status confirmed by backend at ${formatDateTime(updated.updatedAt)}.`,
        tone: pendingStatus.status === 'Submitted' ? 'green' : 'slate',
      });
      setPendingStatus(null);
    } catch (error) {
      setStatusError(error instanceof Error ? error.message : 'Unable to update the dispatch status.');
    } finally {
      setStatusBusy(false);
    }
  };

  const confirmReassign = async () => {
    if (!pendingReassign) return;
    setReassignBusy(true);
    setReassignError(null);
    try {
      const updated = await tasksApi.update(pendingReassign.task.id, {
        assigneeUserId: pendingReassign.assigneeUserId,
        notifyAssignee: true,
      });
      upsertTask(updated);
      logSessionEvent({
        title: `Dispatch reassigned: ${updated.title}`,
        detail: `Now assigned to ${updated.assigneeName}. Backend-confirmed.`,
        tone: 'amber',
      });
      setReassignDraft((current) => ({ ...current, [updated.id]: '' }));
      setPendingReassign(null);
    } catch (error) {
      setReassignError(error instanceof Error ? error.message : 'Unable to reassign the dispatch.');
    } finally {
      setReassignBusy(false);
    }
  };

  return (
    <SectionCard
      title="Rescue & Ambulance Dispatch"
      subtitle="Dispatch requests are backend task records. Nothing is confirmed until the server confirms it."
      badge={<DataBadge provenance="verified" title="Dispatch list, status and progress come from GET /api/tasks." />}
      action={
        planner ? (
          <button
            type="button"
            onClick={() => {
              setFormOpen((open) => !open);
              setFormError(null);
            }}
            className={primaryButtonClass}
          >
            <Plus size={14} /> {formOpen ? 'Close form' : 'New dispatch'}
          </button>
        ) : undefined
      }
    >
      <div className="space-y-3 p-3 sm:p-4">
        {!planner && (
          <p className="flex items-start gap-2 border border-slate-300 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600">
            <ShieldAlert size={14} className="mt-0.5 shrink-0 text-[#18365b]" />
            <span>
              You are signed in as <strong>{currentUser?.roleName ?? 'a non-planner role'}</strong>. Dispatch
              creation and reassignment require the Operations Planner (Role 2); the backend rejects
              these actions for other roles. Tracking below is read-only for you.
            </span>
          </p>
        )}

        {formOpen && planner && (
          <form onSubmit={openCreateConfirm} className="space-y-3 border border-[#18365b] bg-blue-50/40 p-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="block text-xs font-semibold text-slate-700">
                Dispatch title <span className="text-red-700">*</span>
                <input
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="e.g. Rescue stranded families at Ward 17"
                  className={`${inputClass} mt-1.5`}
                />
              </label>
              <label className="block text-xs font-semibold text-slate-700">
                Team / department
                <select
                  value={form.department}
                  onChange={(e) => setForm({ ...form, department: e.target.value })}
                  className={`${inputClass} mt-1.5`}
                >
                  {DISPATCH_DEPARTMENTS.map((department) => (
                    <option key={department} value={department}>{department}</option>
                  ))}
                </select>
              </label>
              <label className="block text-xs font-semibold text-slate-700">
                Pickup / staging location <span className="text-red-700">*</span>
                <input
                  value={form.location}
                  onChange={(e) => setForm({ ...form, location: e.target.value })}
                  placeholder="Ward, road or landmark"
                  className={`${inputClass} mt-1.5`}
                />
              </label>
              <label className="block text-xs font-semibold text-slate-700">
                Destination facility (optional)
                <select
                  value={form.destinationPoiId}
                  onChange={(e) => setForm({ ...form, destinationPoiId: e.target.value })}
                  className={`${inputClass} mt-1.5`}
                >
                  <option value="">No fixed destination</option>
                  <optgroup label="Shelters">
                    {pois.filter((poi) => poi.type === 'shelter').map((poi) => (
                      <option key={poi.id} value={poi.id}>{poi.name}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Hospitals">
                    {pois.filter((poi) => poi.type === 'hospital').map((poi) => (
                      <option key={poi.id} value={poi.id}>{poi.name}</option>
                    ))}
                  </optgroup>
                </select>
              </label>
              <label className="block text-xs font-semibold text-slate-700">
                Priority
                <select
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: e.target.value as TaskPriority })}
                  className={`${inputClass} mt-1.5`}
                >
                  {PRIORITIES.map((priority) => (
                    <option key={priority} value={priority}>{priority}</option>
                  ))}
                </select>
              </label>
              <div className="block text-xs font-semibold text-slate-700">
                Assign team (officer) <span className="text-red-700">*</span>
                {officersError ? (
                  <div className="mt-1.5"><ErrorState message={officersError} onRetry={onRefresh} retryLabel="Reload" /></div>
                ) : (
                  <select
                    value={form.assigneeUserId}
                    onChange={(e) => setForm({ ...form, assigneeUserId: e.target.value })}
                    className={`${inputClass} mt-1.5`}
                  >
                    <option value="">Select officer…</option>
                    {activeOfficers.map((officer) => (
                      <option key={officer.id} value={officer.id}>
                        {officer.name} ({officer.email})
                      </option>
                    ))}
                  </select>
                )}
                <span className="mt-1 block text-[11px] font-normal text-slate-500">
                  Only active backend users are listed. Availability beyond assignment is not tracked.
                </span>
              </div>
              <label className="block text-xs font-semibold text-slate-700 sm:col-span-2">
                Instructions
                <textarea
                  value={form.instructions}
                  onChange={(e) => setForm({ ...form, instructions: e.target.value })}
                  rows={2}
                  placeholder="Access constraints, equipment, contact person…"
                  className={`${inputClass} mt-1.5 resize-y`}
                />
              </label>
              <label className="block text-xs font-semibold text-slate-700">
                Deadline (optional)
                <input
                  type="datetime-local"
                  value={form.deadline}
                  onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                  className={`${inputClass} mt-1.5`}
                />
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={form.notifyAssignee}
                  onChange={(e) => setForm({ ...form, notifyAssignee: e.target.checked })}
                  className="h-4 w-4 accent-[#18365b]"
                />
                Notify assigned team on creation
              </label>
            </div>
            {formError ? (
              <p role="alert" className="border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800">{formError}</p>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" onClick={() => setFormOpen(false)} className={outlineButtonClass}>Cancel</button>
              <button type="submit" className={primaryButtonClass}>
                <Ambulance size={14} /> Review & confirm dispatch
              </button>
            </div>
          </form>
        )}

        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter dispatches by status">
            {(['All', 'Assigned', 'In Progress', 'Submitted'] as StatusFilter[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setStatusFilter(item)}
                aria-pressed={statusFilter === item}
                className={`border px-2.5 py-1.5 text-xs font-semibold ${
                  statusFilter === item
                    ? 'border-[#18365b] bg-[#18365b] text-white'
                    : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {item === 'All' ? `All (${tasks.length})` : `${item} (${counts[item]})`}
              </button>
            ))}
          </div>
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search dispatches…"
              className="w-full border border-slate-300 py-1.5 pl-8 pr-2.5 text-xs outline-none focus:border-[#18365b] lg:w-52"
            />
          </div>
        </div>

        {tasksLoading ? (
          <p role="status" className="flex items-center gap-2 border border-slate-200 px-4 py-8 text-sm text-slate-600">
            <LoaderCircle size={16} className="animate-spin" /> Loading backend dispatch records…
          </p>
        ) : tasksError ? (
          <ErrorState message={`Dispatch list failed to load: ${tasksError}`} onRetry={onRefresh} />
        ) : visibleTasks.length === 0 ? (
          <EmptyState
            title={tasks.length === 0 ? 'No dispatches recorded' : 'No dispatches match the filter'}
            detail={
              tasks.length === 0
                ? 'The backend returned no task records for this region. New dispatches appear here after server confirmation.'
                : 'Adjust the status filter or search text.'
            }
          />
        ) : (
          <ul className="divide-y divide-slate-200 border border-slate-200">
            {visibleTasks.map((task) => {
              const expanded = expandedId === task.id;
              const updatable = canUpdate(task);
              return (
                <li key={task.id} className="bg-white">
                  <button
                    type="button"
                    onClick={() => setExpandedId(expanded ? null : task.id)}
                    aria-expanded={expanded}
                    className="block w-full p-3 text-left hover:bg-slate-50"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                          {task.department} · {task.id.slice(0, 8).toUpperCase()}
                        </p>
                        <p className="mt-0.5 text-sm font-semibold text-slate-900">{task.title}</p>
                      </div>
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className={`border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${PRIORITY_BADGE[task.priority]}`}>
                          {task.priority}
                        </span>
                        <span className={`px-2 py-1 text-[10px] font-semibold ${STATUS_BADGE[task.status]}`}>
                          {task.status}
                        </span>
                        <ChevronDown size={14} className={`text-slate-400 transition-transform ${expanded ? 'rotate-180' : ''}`} />
                      </span>
                    </div>
                    <p className="mt-1.5 flex items-center gap-1.5 text-xs text-slate-500">
                      <MapPin size={12} /> {task.location}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
                      <span>Team: <strong className="text-slate-700">{task.assigneeName || 'Unassigned'}</strong></span>
                      <span>Updated {formatAge(task.updatedAt)} · {task.reports?.length ?? 0} field reports</span>
                    </div>
                    <div className="mt-1.5 h-1.5 bg-slate-100" role="progressbar" aria-valuenow={task.progress} aria-valuemin={0} aria-valuemax={100} aria-label={`${task.title} progress`}>
                      <div className="h-1.5 bg-[#18365b]" style={{ width: `${task.progress}%` }} />
                    </div>
                  </button>

                  {expanded && (
                    <div className="space-y-3 border-t border-slate-100 bg-slate-50/60 p-3 text-xs leading-5 text-slate-600">
                      {task.instructions ? <p>{task.instructions}</p> : <p className="italic text-slate-400">No instructions recorded.</p>}
                      <p>
                        Created {formatDateTime(task.createdAt)} by {task.createdByName || 'unknown'}
                        {task.deadline ? ` · Deadline ${formatDateTime(task.deadline)}` : ' · No deadline set'}.
                      </p>
                      {updatable ? (
                        <div className="flex flex-wrap gap-2">
                          {task.status === 'Assigned' && (
                            <button
                              type="button"
                              onClick={() => {
                                setStatusError(null);
                                setPendingStatus({ task, status: 'In Progress' });
                              }}
                              className={outlineButtonClass}
                            >
                              <Play size={13} /> Mark In Progress
                            </button>
                          )}
                          {task.status !== 'Submitted' && (
                            <button
                              type="button"
                              onClick={() => {
                                setStatusError(null);
                                setPendingStatus({ task, status: 'Submitted' });
                              }}
                              className={primaryButtonClass}
                            >
                              <CheckCircle2 size={13} /> Mark Submitted
                            </button>
                          )}
                        </div>
                      ) : (
                        <p className="text-[11px] text-slate-500">
                          Status changes are limited to the Operations Planner and the assigned team member.
                        </p>
                      )}
                      {planner && task.status !== 'Submitted' && (
                        <div className="flex flex-col gap-2 border-t border-slate-200 pt-2.5 sm:flex-row sm:items-end">
                          <label className="block flex-1 text-xs font-semibold text-slate-700">
                            Reassign team
                            <select
                              value={reassignDraft[task.id] ?? ''}
                              onChange={(e) => setReassignDraft((current) => ({ ...current, [task.id]: e.target.value }))}
                              className={`${inputClass} mt-1`}
                            >
                              <option value="">Select officer…</option>
                              {activeOfficers
                                .filter((officer) => officer.id !== task.assigneeUserId)
                                .map((officer) => (
                                  <option key={officer.id} value={officer.id}>{officer.name}</option>
                                ))}
                            </select>
                          </label>
                          <button
                            type="button"
                            disabled={!reassignDraft[task.id]}
                            onClick={() => {
                              const assigneeUserId = reassignDraft[task.id];
                              if (!assigneeUserId) return;
                              setReassignError(null);
                              setPendingReassign({ task, assigneeUserId });
                            }}
                            className={outlineButtonClass}
                          >
                            Reassign…
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {pendingCreate && (
        <ConfirmDialog
          title="Confirm dispatch creation"
          summary={[
            `Title: ${form.title.trim()}`,
            `Team: ${form.department} → ${officerName(form.assigneeUserId)}`,
            `Location: ${form.location.trim()}`,
            ...(destinationName() ? [`Destination: ${destinationName()}`] : []),
            `Priority: ${form.priority}${formatDeadlinePreview()}`,
          ]}
          detail="This writes a backend task record and, if enabled, notifies the assigned team. The dispatch is tracked only after the server confirms it."
          confirmLabel="Confirm dispatch"
          busy={createBusy}
          error={createError}
          onConfirm={confirmCreate}
          onClose={() => {
            if (!createBusy) setPendingCreate(false);
          }}
        />
      )}
      {pendingStatus && (
        <ConfirmDialog
          title={`Confirm status: ${pendingStatus.status}`}
          summary={[
            `Dispatch: ${pendingStatus.task.title}`,
            `Team: ${pendingStatus.task.assigneeName || 'Unassigned'}`,
            `From ${pendingStatus.task.status} → ${pendingStatus.status}`,
          ]}
          detail={
            pendingStatus.status === 'Submitted'
              ? 'Submitting closes the dispatch and notifies the Operations Planner. Field history is preserved.'
              : 'This marks the dispatch as actively underway.'
          }
          confirmLabel={`Confirm ${pendingStatus.status}`}
          busy={statusBusy}
          error={statusError}
          onConfirm={confirmStatusChange}
          onClose={() => {
            if (!statusBusy) setPendingStatus(null);
          }}
        />
      )}
      {pendingReassign && (
        <ConfirmDialog
          title="Confirm reassignment"
          summary={[
            `Dispatch: ${pendingReassign.task.title}`,
            `From ${pendingReassign.task.assigneeName || 'Unassigned'} → ${officerName(pendingReassign.assigneeUserId)}`,
          ]}
          detail="The new team is notified immediately. The previous assignment stays in the activity history."
          confirmLabel="Confirm reassignment"
          busy={reassignBusy}
          error={reassignError}
          onConfirm={confirmReassign}
          onClose={() => {
            if (!reassignBusy) setPendingReassign(null);
          }}
        />
      )}
    </SectionCard>
  );
}
