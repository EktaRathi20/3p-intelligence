import { useEffect, useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { BellRing, CheckCheck, LoaderCircle, RotateCcw } from 'lucide-react';
import { Notification } from '@/components/dashboard/modes/NotificationModeView';
import type { DashboardOutletData } from '../types/dashboard';
import {
  notificationsApi,
  type OperationalNotification,
} from '../services/operationalApi';
import type { TaskPriority } from '../utils/taskReview';

const priorityStyles: Record<TaskPriority, string> = {
  Critical: 'border-rose-300 bg-rose-50 text-rose-800',
  High: 'border-orange-300 bg-orange-50 text-orange-800',
  Medium: 'border-amber-300 bg-amber-50 text-amber-900',
  Low: 'border-sky-300 bg-sky-50 text-sky-800',
};

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown time' : date.toLocaleString();
}

export default function AlertsPage() {
  const dashboard = useOutletContext<DashboardOutletData>();
  const navigate = useNavigate();
  const [opsItems, setOpsItems] = useState<OperationalNotification[]>([]);
  const [opsUnread, setOpsUnread] = useState(0);
  const [opsLoading, setOpsLoading] = useState(true);
  const [opsError, setOpsError] = useState<string | null>(null);
  const [opsRetry, setOpsRetry] = useState(0);
  const [markingId, setMarkingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setOpsLoading(true);
    setOpsError(null);
    notificationsApi
      .list('inbox')
      .then((result) => {
        if (cancelled) return;
        setOpsItems(result.notifications);
        setOpsUnread(result.unread);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setOpsItems([]);
          setOpsUnread(0);
          setOpsError(error instanceof Error ? error.message : 'Task notifications are unavailable.');
        }
      })
      .finally(() => {
        if (!cancelled) setOpsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [opsRetry]);

  const markRead = async (id: string) => {
    setMarkingId(id);
    try {
      await notificationsApi.markRead(id);
      setOpsItems((current) => current.map((item) => (item.id === id ? { ...item, read: true } : item)));
      setOpsUnread((current) => Math.max(0, current - 1));
    } catch {
      // Keep the item unread; the next refresh will retry the state.
    } finally {
      setMarkingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <section className="space-y-3" aria-label="Field task notifications">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
          <div className="flex items-center gap-2.5">
            <span className="border border-slate-200 bg-white p-2 text-[#18365b]">
              <BellRing size={17} />
            </span>
            <div>
              <h1 className="text-base font-bold text-slate-900">Field task notifications</h1>
              <p className="text-xs text-slate-500">
                Task assignments and field updates
                {opsUnread > 0 ? ` · ${opsUnread} unread` : ''}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpsRetry((value) => value + 1)}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#18365b] underline underline-offset-2"
          >
            <RotateCcw size={13} /> Refresh
          </button>
        </header>

        {opsLoading ? (
          <p role="status" className="flex items-center gap-2 rounded-md bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
            <LoaderCircle size={15} className="animate-spin" /> Loading task notifications…
          </p>
        ) : opsError ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <span>{opsError}</span>
            <button type="button" onClick={() => setOpsRetry((value) => value + 1)} className="inline-flex shrink-0 items-center gap-1.5 font-semibold underline underline-offset-2">
              <RotateCcw size={13} /> Retry
            </button>
          </div>
        ) : opsItems.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center">
            <BellRing size={22} className="mx-auto text-slate-400" />
            <p className="mt-2 text-sm font-medium text-slate-700">No task notifications yet</p>
            <p className="mt-1 text-xs text-slate-500">New task assignments and field updates will appear here.</p>
          </div>
        ) : (
          <ul className="space-y-2">
            {opsItems.map((item) => (
              <li
                key={item.id}
                className={`rounded-md border p-3 ${item.read ? 'border-slate-200 bg-white' : 'border-blue-300 bg-blue-50/60'}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-sm border px-1.5 py-0.5 text-[9px] font-bold uppercase ${priorityStyles[item.priority]}`}>
                    {item.priority}
                  </span>
                  {!item.read && (
                    <span className="rounded-sm bg-[#18365b] px-1.5 py-0.5 text-[9px] font-bold uppercase text-white">
                      New
                    </span>
                  )}
                  <time className="ml-auto text-[10px] text-slate-500">{formatDate(item.createdAt)}</time>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-slate-800">{item.message}</p>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[10px] text-slate-500">
                    From {item.senderName || 'Operations Planner'}
                    {item.taskId ? ` · linked task ${item.taskId.slice(0, 6).toUpperCase()}` : ''}
                  </p>
                  {!item.read && (
                    <button
                      type="button"
                      disabled={markingId === item.id}
                      onClick={() => markRead(item.id)}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#18365b] underline underline-offset-2 disabled:opacity-50"
                    >
                      <CheckCheck size={13} /> {markingId === item.id ? 'Saving…' : 'Mark read'}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Notification
        alerts={dashboard.alerts}
        connectionState={dashboard.connectionState}
        error={dashboard.alertsError}
        isLoading={dashboard.alertsLoading}
        onRetry={dashboard.retryAlerts}
        selectedRegionKey={dashboard.selectedRegionKey}
        regionName={dashboard.selectedCity?.name ?? ''}
        onBack={() => navigate('/overview')}
      />
    </div>
  );
}
