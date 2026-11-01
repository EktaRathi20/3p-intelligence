import { useMemo } from 'react';
import type { ClimateAlert } from '@/types/alerts';
import type { BackendTask, OperationalNotification } from '@/services/operationalApi';
import type { SessionEvent } from './useCommandCentreData';
import { DataBadge, EmptyState, ErrorState, formatAge, formatDateTime, SectionCard } from './rescueShared';

interface LogEntry {
  id: string;
  at: string;
  title: string;
  detail: string;
  source: 'Backend task' | 'Notification' | 'Alert' | 'This console';
  tone: 'green' | 'amber' | 'red' | 'slate';
}

const TONE_DOT: Record<LogEntry['tone'], string> = {
  green: 'bg-emerald-600',
  amber: 'bg-amber-500',
  red: 'bg-red-600',
  slate: 'bg-slate-400',
};

function taskEntries(tasks: BackendTask[]): LogEntry[] {
  const entries: LogEntry[] = [];
  for (const task of tasks) {
    entries.push({
      id: `task-created-${task.id}`,
      at: task.createdAt,
      title: `Dispatch opened: ${task.title}`,
      detail: `${task.department} → ${task.assigneeName || 'Unassigned'} · ${task.priority} priority.`,
      source: 'Backend task',
      tone: task.priority === 'Critical' ? 'red' : 'slate',
    });
    const created = new Date(task.createdAt).getTime();
    const updated = new Date(task.updatedAt).getTime();
    if (Number.isFinite(created) && Number.isFinite(updated) && updated - created > 60_000) {
      entries.push({
        id: `task-updated-${task.id}`,
        at: task.updatedAt,
        title: `Dispatch ${task.status.toLowerCase()}: ${task.title}`,
        detail: `Progress ${task.progress}% · team ${task.assigneeName || 'Unassigned'}.`,
        source: 'Backend task',
        tone: task.status === 'Submitted' ? 'green' : 'amber',
      });
    }
    for (const [index, report] of (task.reports ?? []).entries()) {
      entries.push({
        id: `task-report-${task.id}-${index}`,
        at: report.at,
        title: `Field report on ${task.title}`,
        detail: `${report.text.slice(0, 140)}${report.text.length > 140 ? '…' : ''} — ${report.byName}.`,
        source: 'Backend task',
        tone: 'slate',
      });
    }
  }
  return entries;
}

export function ActivityLog({
  tasks,
  tasksError,
  notifications,
  notificationsError,
  alerts,
  sessionEvents,
  onRefresh,
}: {
  tasks: BackendTask[];
  tasksError: string | null;
  notifications: OperationalNotification[];
  notificationsError: string | null;
  alerts: ClimateAlert[];
  sessionEvents: SessionEvent[];
  onRefresh: () => void;
}) {
  const entries = useMemo(() => {
    const merged: LogEntry[] = [
      ...taskEntries(tasks),
      ...notifications.map((note): LogEntry => ({
        id: `note-${note.id}`,
        at: note.createdAt,
        title: `Message from ${note.senderName}`,
        detail: note.message.slice(0, 160),
        source: 'Notification',
        tone: note.priority === 'Critical' ? 'red' : 'slate',
      })),
      ...alerts
        .filter((alert) => !alert.is_simulation)
        .map((alert): LogEntry => ({
          id: `alert-${alert.id}`,
          at: alert.received_at,
          title: `Alert: ${alert.title}`,
          detail: `${alert.hazard_type} · ${alert.severity} · ${alert.location.name}.`,
          source: 'Alert',
          tone: alert.severity === 'critical' || alert.severity === 'high' ? 'red' : 'amber',
        })),
      ...sessionEvents.map((event): LogEntry => ({
        id: event.id,
        at: event.at,
        title: event.title,
        detail: event.detail,
        source: 'This console',
        tone: event.tone,
      })),
    ];
    merged.sort((a, b) => (a.at < b.at ? 1 : -1));
    return merged.slice(0, 60);
  }, [tasks, notifications, alerts, sessionEvents]);

  return (
    <SectionCard
      title="Operations Activity Log"
      subtitle="Auditable timeline from backend records and this console session."
      badge={<DataBadge provenance="verified" title="Task, notification and alert entries are backend records. Session entries are local to this console." />}
    >
      <div className="space-y-2.5 p-3 sm:p-4">
        {tasksError ? <ErrorState message={`Task history unavailable: ${tasksError}`} onRetry={onRefresh} /> : null}
        {notificationsError ? (
          <ErrorState message={`Notification history unavailable: ${notificationsError}`} onRetry={onRefresh} />
        ) : null}
        {entries.length === 0 && !tasksError ? (
          <EmptyState
            title="No activity recorded"
            detail="Dispatches, messages, alerts and session actions will appear here in reverse chronological order."
          />
        ) : (
          <ol className="max-h-[560px] space-y-0 overflow-y-auto">
            {entries.map((entry) => (
              <li key={entry.id} className="relative border-l-2 border-slate-200 pb-4 pl-4 last:pb-0">
                <span
                  aria-hidden="true"
                  className={`absolute -left-[5px] top-1 h-2 w-2 rounded-full ${TONE_DOT[entry.tone]}`}
                />
                <p className="text-xs font-bold leading-4 text-slate-900">{entry.title}</p>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-600">{entry.detail}</p>
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-400">
                  <span>{formatDateTime(entry.at)} ({formatAge(entry.at)})</span>
                  <span className="border border-slate-200 bg-slate-50 px-1 py-px font-semibold uppercase tracking-wide text-slate-500">
                    {entry.source}
                  </span>
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </SectionCard>
  );
}
