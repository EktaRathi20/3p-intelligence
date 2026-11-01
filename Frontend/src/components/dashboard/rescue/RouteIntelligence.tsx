import { Droplets, Route as RouteIcon } from 'lucide-react';
import type { DisasterIntelligenceResponse } from '@/types/api';
import type { VerifiedRoute } from '@/types/domain';
import type { RouteRecord } from './TacticalAssistant';
import {
  DataBadge,
  EmptyState,
  ErrorState,
  formatAge,
  formatDateTime,
  SectionCard,
  snapshotProvenance,
} from './rescueShared';

const CLEARANCE_STYLE: Record<VerifiedRoute['clearanceStatus'], string> = {
  VERIFIED_CLEAR: 'border-emerald-700 bg-emerald-50 text-emerald-800',
  CAUTION_RESTRICTED: 'border-amber-600 bg-amber-50 text-amber-900',
  IMPASSABLE_FLOOD: 'border-red-700 bg-red-50 text-red-800',
};

const ROUTE_STALE_AFTER_MS = 60 * 60 * 1000;

export function RouteIntelligence({
  routes,
  intelligence,
  intelligenceError,
  onRetry,
}: {
  routes: RouteRecord[];
  intelligence: DisasterIntelligenceResponse | null;
  intelligenceError: string | null;
  onRetry: () => void;
}) {
  const insurance = intelligence?.insurance_summary ?? null;
  const observedDepth = insurance?.observed_water_depth_m ?? null;
  const quality = intelligence?.data_quality ?? null;
  const generatedAt = intelligence?.generated_at ?? null;
  const snapshot = snapshotProvenance(generatedAt);
  const sources = quality ? Object.entries(quality.sources ?? {}) : [];

  return (
    <SectionCard
      title="Route Intelligence"
      subtitle="Advisory routes from this session plus flood context from disaster intelligence."
      badge={
        <DataBadge
          provenance={snapshot}
          title={generatedAt ? `Intelligence snapshot generated ${formatDateTime(generatedAt)}.` : 'No intelligence snapshot available.'}
        />
      }
    >
      <div className="space-y-3 p-3 sm:p-4">
        {intelligenceError && !intelligence ? (
          <ErrorState message={`Flood context failed to load: ${intelligenceError}`} onRetry={onRetry} />
        ) : (
          <div className="border border-slate-200 bg-slate-50/60 p-3">
            <div className="flex items-center gap-2 text-xs font-bold text-[#18365b]">
              <Droplets size={14} /> Flood & clearance context
            </div>
            <dl className="mt-2 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
              <div>
                <dt className="text-slate-500">Observed water depth</dt>
                <dd className="mt-0.5 font-mono text-sm font-bold text-slate-900">
                  {observedDepth != null ? `${observedDepth} m` : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Trigger threshold</dt>
                <dd className="mt-0.5 font-mono text-sm font-bold text-slate-900">
                  {insurance?.trigger_threshold_m != null ? `${insurance.trigger_threshold_m} m` : '—'}
                </dd>
              </div>
            </dl>
            <p className="mt-1.5 text-[11px] leading-4 text-slate-600">
              {insurance?.headline ?? 'No flood assessment returned.'}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <DataBadge
                provenance={observedDepth != null ? 'estimated' : 'unavailable'}
                title={
                  observedDepth != null
                    ? 'Model-derived estimate from the insurance summary, not a live gauge reading.'
                    : 'No water-depth value in the current intelligence snapshot.'
                }
              />
              <span className="text-[11px] text-slate-500">
                Snapshot {generatedAt ? `${formatDateTime(generatedAt)} (${formatAge(generatedAt)})` : 'unavailable'}
              </span>
            </div>
            {quality && (
              <div className="mt-2 border-t border-slate-200 pt-2 text-[11px] leading-5 text-slate-600">
                <p>
                  Ingestion: <strong>{quality.ingestion_status}</strong> · Telemetry:{' '}
                  <strong>{quality.telemetry_status}</strong>
                  {quality.telemetry_timestamp ? ` (${formatAge(quality.telemetry_timestamp)})` : ''}
                </p>
                {sources.length > 0 && (
                  <p className="mt-1">
                    <span className="font-semibold text-slate-700">Sources: </span>
                    {sources.map(([key, value]) => `${key}: ${value ?? 'n/a'}`).join(' · ')}
                  </p>
                )}
                {quality.ingestion_error && (
                  <p className="mt-1 text-amber-800">Ingestion note: {quality.ingestion_error}</p>
                )}
              </div>
            )}
          </div>
        )}

        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-bold text-[#18365b]">
            <RouteIcon size={14} /> Session route advisories ({routes.length})
          </div>
          {routes.length === 0 ? (
            <EmptyState
              title="No routes requested yet"
              detail="Ask the AI Tactical Assistant for a safe route. Each advisory is recorded here with its clearance, flood depth and verification time."
            />
          ) : (
            <ul className="space-y-2.5">
              {routes.map((record) => {
                const ageMs = Date.now() - new Date(record.at).getTime();
                const stale = Number.isFinite(ageMs) && ageMs > ROUTE_STALE_AFTER_MS;
                return (
                  <li key={record.id} className="border border-slate-200 bg-white p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-slate-900">
                          {record.route.origin} → {record.route.destination}
                        </p>
                        <p className="mt-0.5 text-[11px] text-slate-500">
                          Advised {formatDateTime(record.at)} ({formatAge(record.at)}) · Query: “{record.query}”
                        </p>
                      </div>
                      <span className="flex flex-wrap gap-1.5">
                        <span className={`border px-1.5 py-0.5 font-mono text-[10px] font-bold ${CLEARANCE_STYLE[record.route.clearanceStatus]}`}>
                          {record.route.clearanceStatus.replace(/_/g, ' ')}
                        </span>
                        <DataBadge
                          provenance={stale ? 'stale' : 'estimated'}
                          title={stale ? 'Advisory is over an hour old. Re-query before any movement.' : 'AI-assisted advisory, not surveyed clearance.'}
                        />
                      </span>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-700">{record.route.recommendedPath}</p>
                    <div className="mt-1.5 grid grid-cols-1 gap-1.5 text-[11px] text-slate-600 sm:grid-cols-2">
                      <span><strong className="text-slate-700">Water depth:</strong> {record.route.waterDepth}</span>
                      <span><strong className="text-slate-700">Validity:</strong> {record.route.validityWindow}</span>
                    </div>
                    <p className="mt-1 text-[11px] text-slate-500">
                      Data source: live facility feed + AI routing · {record.route.sensorVerification}
                    </p>
                    {stale && (
                      <p role="alert" className="mt-1.5 border border-orange-300 bg-orange-50 px-2 py-1 text-[11px] font-semibold text-orange-800">
                        Stale advisory — conditions may have changed. Re-verify before movement.
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-2 border border-slate-200 bg-slate-50 px-2.5 py-2 text-[11px] leading-4 text-slate-500">
            Blocked-road and surveyed-clearance feeds are not connected. Treat every advisory as
            provisional until ground teams confirm it.
          </p>
        </div>
      </div>
    </SectionCard>
  );
}
