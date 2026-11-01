import { useEffect, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw, X } from 'lucide-react';

/** Provenance of a displayed value. Never claim more than the feed provides. */
export type DataProvenance =
  | 'live'
  | 'verified'
  | 'estimated'
  | 'stale'
  | 'unavailable'
  | 'local';

const PROVENANCE_STYLE: Record<DataProvenance, { label: string; className: string }> = {
  live: { label: 'Live', className: 'border-emerald-700 bg-emerald-700 text-white' },
  verified: { label: 'Verified', className: 'border-blue-800 bg-blue-50 text-blue-900' },
  estimated: { label: 'Estimated', className: 'border-amber-600 bg-amber-50 text-amber-900' },
  stale: { label: 'Stale', className: 'border-orange-600 bg-orange-50 text-orange-800' },
  unavailable: { label: 'Unavailable', className: 'border-slate-300 bg-slate-100 text-slate-600' },
  local: { label: 'This console', className: 'border-slate-400 bg-white text-slate-600' },
};

export function DataBadge({ provenance, title }: { provenance: DataProvenance; title?: string }) {
  const style = PROVENANCE_STYLE[provenance];
  return (
    <span
      title={title ?? style.label}
      className={`inline-block border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${style.className}`}
    >
      {style.label}
    </span>
  );
}

export const inputClass =
  'w-full border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 outline-none focus:border-[#18365b] disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500';
export const primaryButtonClass =
  'inline-flex items-center justify-center gap-1.5 bg-[#18365b] px-3 py-2 text-xs font-semibold text-white hover:bg-[#102744] disabled:cursor-not-allowed disabled:opacity-50';
export const outlineButtonClass =
  'inline-flex items-center justify-center gap-1.5 border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50';

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatAge(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return 'unknown age';
  const parsed = new Date(iso).getTime();
  if (Number.isNaN(parsed)) return 'unknown age';
  const minutes = Math.max(0, Math.floor((now - parsed) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ${minutes % 60} min ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

/** Freshness for timestamped backend snapshots (intelligence, conditions). */
export function snapshotProvenance(
  iso: string | null | undefined,
  staleAfterMs = 3 * 60 * 60 * 1000,
): DataProvenance {
  if (!iso) return 'unavailable';
  const parsed = new Date(iso).getTime();
  if (Number.isNaN(parsed)) return 'unavailable';
  return Date.now() - parsed > staleAfterMs ? 'stale' : 'verified';
}

export function SectionCard({
  title,
  subtitle,
  badge,
  action,
  children,
  className = '',
}: {
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`flex min-w-0 flex-col border border-slate-300 bg-white shadow-sm ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-200 px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-bold text-[#18365b]">{title}</h2>
            {badge}
          </div>
          {subtitle ? <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p> : null}
        </div>
        {action}
      </div>
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </section>
  );
}

export function ErrorState({
  message,
  onRetry,
  retryLabel = 'Retry',
}: {
  message: string;
  onRetry: () => void;
  retryLabel?: string;
}) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-2 border border-amber-300 bg-amber-50 px-3 py-2.5 text-xs text-amber-900"
    >
      <span className="flex min-w-0 items-start gap-1.5">
        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
        <span>{message}</span>
      </span>
      <button type="button" onClick={onRetry} className="inline-flex shrink-0 items-center gap-1.5 font-semibold underline underline-offset-2">
        <RotateCcw size={12} /> {retryLabel}
      </button>
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center">
      <p className="text-sm font-semibold text-slate-700">{title}</p>
      <p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p>
    </div>
  );
}

export function ConfirmDialog({
  title,
  summary,
  detail,
  confirmLabel,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  title: string;
  summary: string[];
  detail?: string;
  confirmLabel: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/55 p-3 sm:p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto border border-slate-300 bg-white shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 bg-[#18365b] px-4 py-3 text-white">
          <h2 className="text-sm font-bold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="Close dialog"
            className="border border-white/40 p-1.5 text-white hover:bg-white/10 disabled:opacity-50"
          >
            <X size={15} />
          </button>
        </div>
        <div className="space-y-3 p-4">
          <ul className="space-y-1.5 border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-700">
            {summary.map((line) => (
              <li key={line} className="flex gap-2">
                <span aria-hidden="true" className="font-bold text-[#18365b]">•</span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
          {detail ? <p className="text-xs leading-5 text-slate-600">{detail}</p> : null}
          {error ? (
            <p role="alert" className="border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" onClick={onClose} disabled={busy} className={outlineButtonClass}>
              Cancel
            </button>
            <button type="button" onClick={onConfirm} disabled={busy} className={primaryButtonClass}>
              {busy ? 'Confirming…' : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
