import React from 'react';
import { ArrowLeft, History, Info, LoaderCircle, Search, TriangleAlert, Waves, Wind } from 'lucide-react';
import type { HistoricalResponse } from '@/types/api';

interface HistoricalDisastersViewProps {
  history: HistoricalResponse | null;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
  regionName: string;
  onBackToOverview?: () => void;
  page: number;
  onPageChange: (page: number) => void;
  searchQuery: string;
  onSearchChange: (search: string) => void;
  hazardFilter: string;
  onHazardFilterChange: (hazard: string) => void;
  availableHazards: string[];
  unsupportedHazards: string[];
  sortBy: 'newest' | 'oldest' | 'wind' | 'distance';
  onSortChange: (sort: 'newest' | 'oldest' | 'wind' | 'distance') => void;
}

export const HistoricalDisastersView: React.FC<HistoricalDisastersViewProps> = ({
  history,
  isLoading,
  error,
  onRetry,
  regionName,
  onBackToOverview,
  page,
  onPageChange,
  searchQuery,
  onSearchChange,
  hazardFilter,
  onHazardFilterChange,
  availableHazards,
  unsupportedHazards,
  sortBy,
  onSortChange,
}) => {
  const events = history?.historical_analogs ?? [];
  const totalPages = history?.total_pages ?? 0;
  const firstResult = history && history.matching_events > 0
    ? (history.page - 1) * history.page_size + 1
    : 0;
  const lastResult = history
    ? Math.min(history.page * history.page_size, history.matching_events)
    : 0;

  return (
    <div className="space-y-4">
     

      

      <section aria-label="History filters" className="border border-slate-300 bg-white px-4 py-3 shadow-sm">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-12 md:items-end">
          <label className="block md:col-span-6">
            <span className="mb-1 block text-xs font-semibold text-slate-700">Search records</span>
            <span className="relative block">
              <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={searchQuery}
                onChange={event => onSearchChange(event.target.value)}
                placeholder="Search cyclone or year"
                className="w-full border border-slate-300 bg-white py-2 pl-9 pr-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-[#18365b]"
              />
            </span>
          </label>
          <label className="block md:col-span-3">
            <span className="mb-1 block text-xs font-semibold text-slate-700">Sort by</span>
            <select
              value={sortBy}
              onChange={event => onSortChange(event.target.value as typeof sortBy)}
              className="w-full border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 outline-none focus:border-[#18365b]"
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="wind">Peak wind</option>
              <option value="distance">Closest approach</option>
            </select>
          </label>
          <label className="block md:col-span-3">
            <span className="mb-1 block text-xs font-semibold text-slate-700">Hazard</span>
            <select
              value={hazardFilter}
              onChange={event => onHazardFilterChange(event.target.value)}
              className="w-full border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 outline-none focus:border-[#18365b]"
            >
              <option value="all">All available hazards{availableHazards.length === 1 ? ` (${availableHazards[0]} only)` : ''}</option>
              {availableHazards.map(hazard => (
                <option key={hazard} value={hazard}>
                  {hazard.charAt(0).toUpperCase() + hazard.slice(1)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {unsupportedHazards.length > 0 && (
        <p className="flex items-start gap-2 border border-amber-300 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-900">
          <TriangleAlert size={14} className="mt-0.5 shrink-0" />
          <span>No historical records for: {unsupportedHazards.join(', ')}. The records on this page cover {availableHazards.length > 0 ? availableHazards.join(', ') : 'no recorded hazard types'} only.</span>
        </p>
      )}
      {history?.history_coverage && (
        <p className="flex items-start gap-2 text-xs leading-5 text-slate-500">
          <Info size={14} className="mt-0.5 shrink-0 text-slate-400" />
          <span>{history.history_coverage.note}</span>
        </p>
      )}

      {isLoading ? (
        <p role="status" className="flex items-center justify-center gap-2 border border-slate-200 bg-white px-4 py-12 text-sm text-slate-600">
          <LoaderCircle size={16} className="animate-spin text-[#18365b]" /> Loading historical analogs…
        </p>
      ) : error ? (
        <div className="border border-red-300 bg-red-50 px-4 py-10 text-center">
          <p role="alert" className="text-sm text-red-800">{error}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 bg-red-700 px-3 py-2 text-xs font-semibold text-white hover:bg-red-800"
          >
            Retry loading history
          </button>
        </div>
      ) : events.length === 0 ? (
        <div className="border border-dashed border-slate-300 bg-white px-4 py-12 text-center">
          <History size={22} className="mx-auto text-slate-400" />
          <p className="mt-2 text-sm font-medium text-slate-700">
            {history?.matching_events === 0 && searchQuery.trim()
              ? 'No historical records match your search.'
              : hazardFilter !== 'all'
                ? `No ${hazardFilter} historical records are available for this region.`
                : 'No historical disaster records were returned for this region.'}
          </p>
        </div>
      ) : (
        <>
          <p className="border border-slate-200 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600">
            Showing {firstResult}–{lastResult} of {history?.matching_events} matching historical records
            {' '}({history?.total_historical_events_analyzed} analyzed) · {history?.source}
            {' '}· refreshed {history?.timestamp ? new Date(history.timestamp).toLocaleString() : 'unknown'}
            {' '}· <a className="font-semibold text-[#18365b] underline underline-offset-2" href={history?.source_url} target="_blank" rel="noreferrer">source</a>
          </p>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {events.map((event, index) => (
              <article key={`${event.matched_cyclone}-${index}`} className="flex flex-col border border-slate-300 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-bold text-[#18365b]">{event.matched_cyclone}</h2>
                <p className="mt-1.5">
                  <span className="inline-block border border-slate-300 bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-700">
                    {event.hazard_type ?? 'Hazard type unavailable'}
                  </span>
                </p>
                <p className="mt-1.5 text-xs text-slate-500">
                  {event.reference_period.start_date} to {event.reference_period.end_date}
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div className="border border-slate-200 bg-slate-50 p-2.5">
                    <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500"><Wind size={13} className="text-[#18365b]" /> Peak wind</div>
                    <div className="mt-1 font-mono text-sm font-bold text-slate-900">{event.historical_peak_wind_kmh == null ? 'Unavailable' : `${event.historical_peak_wind_kmh} km/h`}</div>
                  </div>
                  <div className="border border-slate-200 bg-slate-50 p-2.5">
                    <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500"><Waves size={13} className="text-[#18365b]" /> Closest approach</div>
                    <div className="mt-1 font-mono text-sm font-bold text-slate-900">{event.closest_approach_km} km</div>
                  </div>
                </div>
                <p className="mt-2.5 border-t border-slate-100 pt-2 text-[11px] text-slate-500">Storm surge: not available in the track dataset.</p>
              </article>
            ))}
          </div>
          <nav className="flex items-center justify-between gap-3 border border-slate-300 bg-white px-4 py-3 shadow-sm" aria-label="Historical results pagination">
            <button
              type="button"
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1 || isLoading}
              className="border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 enabled:hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-xs font-medium text-slate-600" aria-live="polite">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages || isLoading}
              className="border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 enabled:hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Next
            </button>
          </nav>
        </>
      )}
    </div>
  );
}
