import React from 'react';
import { AlertTriangle, CheckCircle2, CircleHelp, Clock3, LoaderCircle, Map, ShieldAlert, Wind } from 'lucide-react';
import {
  isAvailableDisasterIntelligence,
  type ApiRegion,
  type DisasterIntelligenceCapabilities,
  type DisasterIntelligenceResult,
} from '@/types/api';
import { CityLocation, MapPOI } from '@/types/domain';
import { MapComponent } from '@/components/dashboard/MapComponent';
import { ExternalLink, Radar } from 'lucide-react';
import { formatAffectedPopulation, formatImpactDistance, formatWarningUpdated, resolveLocalHeadline, verdictLabel } from '@/utils/localImpact';

interface ThreatDetectionModeViewProps {
  city: CityLocation;
  bounds: ApiRegion;
  pois: MapPOI[];
  disasterIntelligence: DisasterIntelligenceResult | null;
  hazardCapabilities: DisasterIntelligenceCapabilities | null;
  selectedHazard: string;
  onSelectHazard: (hazard: string) => void;
  isLoading: boolean;
  error: string | null;
  showMangroveLayer: boolean;
  onToggleMangrove: (value: boolean) => void;
  showHistoricalLayer: boolean;
  onToggleHistorical: (value: boolean) => void;
  isLightMode?: boolean;
}

const riskTone: Record<string, string> = {
  RED: 'border-rose-200 bg-rose-50 text-rose-800',
  ORANGE: 'border-orange-200 bg-orange-50 text-orange-800',
  YELLOW: 'border-amber-200 bg-amber-50 text-amber-800',
  GREEN: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  UNKNOWN: 'border-slate-200 bg-slate-50 text-slate-600',
};

const formatValue = (value: number | null | undefined, unit: string, digits = 0, isLoading = false) =>
  value == null ? isLoading ? 'Loading…' : 'Unavailable' : `${value.toFixed(digits)}${unit}`;

export const ThreatDetectionModeView: React.FC<ThreatDetectionModeViewProps> = ({
  city,
  bounds,
  pois,
  disasterIntelligence,
  hazardCapabilities,
  selectedHazard,
  onSelectHazard,
  isLoading,
  error,
  showMangroveLayer,
  onToggleMangrove,
  showHistoricalLayer,
  onToggleHistorical,
}) => {
  const availableIntelligence = isAvailableDisasterIntelligence(disasterIntelligence)
    ? disasterIntelligence
    : null;
  const hasAssessment = availableIntelligence !== null;
  const unavailableIntelligence = !isAvailableDisasterIntelligence(disasterIntelligence)
    ? disasterIntelligence
    : null;
  const assessment = availableIntelligence?.risk_assessment;
  const conditions = availableIntelligence?.current_conditions;
  const zones = availableIntelligence?.risk_zones ?? [];
  const analysis = availableIntelligence?.ai_analysis;
  const dataQuality = availableIntelligence?.data_quality;
  const dataUnavailable = !hasAssessment || dataQuality?.telemetry_status !== 'AVAILABLE';
  const riskLevel = assessment?.level ?? 'UNKNOWN';
  const screeningLevel = assessment?.screening_level ?? null;
  const warningFloor = assessment?.warning_floor ?? null;
  const screeningScore = assessment?.score ?? null;
  const mlProbability = availableIntelligence?.ml_probability ?? null;
  const mlScored = mlProbability?.status === 'SCORED' && typeof mlProbability.probability === 'number';
  const warnings = availableIntelligence?.official_warnings ?? [];
  const localImpact = availableIntelligence?.local_impact ?? null;
  const localHeadline = resolveLocalHeadline(disasterIntelligence);
  const localZone = localHeadline?.zone ?? 'UNKNOWN';
  const regionalLevel = availableIntelligence?.local_impact_assessment?.regional_warning_level ?? assessment?.warning_floor ?? null;
  const regionalStatus = availableIntelligence?.local_impact_assessment?.regional_warning_status ?? (warnings.length > 0 ? 'active' : null);
  const regionalChipTone = regionalLevel && riskTone[regionalLevel] ? riskTone[regionalLevel] : riskTone.UNKNOWN;
  const regionalChipText = regionalLevel ? `Regional: ${regionalLevel}` : regionalStatus ? `Regional: ${regionalStatus}` : 'Regional: none';
  return (
    <div className="w-full space-y-4 animate-in fade-in duration-300">
      <section className="flex flex-col gap-4 border-b-4 border-[#e5a044] bg-[#18365b] text-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className={`grid h-11 w-11 shrink-0 place-items-center  border ${localHeadline ? riskTone[localZone] ?? riskTone.UNKNOWN : riskTone[riskLevel] ?? riskTone.UNKNOWN}`}>
            {dataUnavailable ? <CircleHelp size={21} /> : <ShieldAlert size={21} />}
          </span>
          <div>
            <h1 className="text-lg font-bold text-slate-200">Threat Detection · {city.name}</h1>
            <p className="mt-0.5 text-xs text-slate-200">
              {isLoading
                ? 'Refreshing disaster intelligence…'
                : unavailableIntelligence
                  ? unavailableIntelligence.message
                  : localHeadline?.headline ?? assessment?.note}
            </p>
          </div>
        </div>
        <div className="flex w-fit flex-col items-end gap-1.5">
          <div className={`inline-flex w-fit items-center gap-2  border px-3 py-2 text-xs font-bold ${localHeadline ? riskTone[localZone] ?? riskTone.UNKNOWN : riskTone[riskLevel] ?? riskTone.UNKNOWN}`}>
            <span className="h-2 w-2 bg-current" />
            {unavailableIntelligence
              ? unavailableIntelligence.status === 'not_implemented' ? 'NOT IMPLEMENTED' : 'NOT CONFIGURED'
              : localHeadline
                ? localZone === 'UNKNOWN' ? 'IMPACT UNKNOWN' : `${localZone} LOCAL IMPACT`
                : riskLevel === 'UNKNOWN' ? 'DATA UNAVAILABLE' : `${riskLevel} RISK`}
          </div>
          
        </div>
      </section>

      <label className="flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-700">
        Hazard intelligence
        <select
          value={selectedHazard}
          onChange={event => onSelectHazard(event.target.value)}
          className=" border border-slate-300 bg-white px-3 py-2 text-xs"
          aria-label="Select hazard intelligence"
        >
          {(hazardCapabilities?.hazards ?? []).map(hazard => (
            <option key={hazard.id} value={hazard.id}>
              {hazard.name} · {hazard.intelligence_status.replace('_', ' ')}
            </option>
          ))}
          {!hazardCapabilities?.hazards.some(hazard => hazard.id === selectedHazard) && (
            <option value={selectedHazard}>{selectedHazard} · checking availability</option>
          )}
        </select>
      </label>

      {dataQuality?.ingestion_error && (
        <div role="status" className=" border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Ingestion is incomplete: {dataQuality.ingestion_error}
        </div>
      )}
      {Object.entries(dataQuality?.source_errors ?? {}).map(([source, sourceError]) => (
        <div key={source} role="status" className=" border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {source} data is unavailable: {sourceError}
        </div>
      ))}
      {!isLoading && unavailableIntelligence && (
        <div role="status" className=" border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {unavailableIntelligence.message}
        </div>
      )}
      {isLoading && <div role="status" aria-live="polite" className="flex items-center gap-2  border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs font-medium text-cyan-950"><LoaderCircle size={14} className="animate-spin" />Loading live telemetry, history, and response resources…</div>}
      {error && !disasterIntelligence && (
        <div role="status" className=" border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
          Data is temporarily unavailable. Retry after sometime.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric icon={<ShieldAlert size={16} />} label="Local impact" value={localHeadline?.shortLabel ?? 'Unavailable'} detail={localHeadline?.headline ?? 'Waiting for API response'} />
        <Metric icon={<Wind size={16} />} label="Wind speed" value={formatValue(conditions?.wind_speed_kmh, ' km/h', 1, isLoading)} detail="Current observation" />
        <Metric icon={<AlertTriangle size={16} />} label="Storm surge" value={formatValue(conditions?.storm_surge_meters, ' m', 2, isLoading)} detail="Measured source value only" />
        <Metric icon={<Map size={16} />} label="Screening zones" value={String(zones.length)} detail="Returned by disaster intelligence" />
      </div>

      {hasAssessment && localHeadline && (
        <section className=" border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 text-sm font-bold text-slate-900"><Radar size={16} className="text-blue-700" /> Regional warning vs local impact</h2>
            <span className={`inline-flex items-center gap-2  border px-2.5 py-1 text-xs font-bold ${regionalChipTone}`}>
              {regionalChipText}
            </span>
          </div>
          <p className="mt-2 text-xs font-semibold text-slate-700">{localHeadline.regionalText}</p>
          {localHeadline.reason && (
            <p className="mt-1 text-xs leading-relaxed text-slate-600">{localHeadline.reason}</p>
          )}
          {localImpact ? (
            <div className="mt-3  border border-slate-200 bg-slate-50 p-3">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className={`inline-flex items-center  border px-2 py-1 font-bold ${localImpact.verdict === 'inside_footprint' ? 'border-rose-200 bg-rose-50 text-rose-800' : localImpact.verdict === 'outside_footprint' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-slate-200 bg-white text-slate-600'}`}>
                  Local: {verdictLabel(localImpact.verdict)}
                </span>
              </div>
              {(localImpact.basis ?? []).map((line, index) => (
                <p key={`${index}-${line.slice(0, 24)}`} className="mt-1.5 text-xs leading-relaxed text-slate-600">{line}</p>
              ))}
              {localImpact.verdict === 'outside_footprint' && (
                <p className="mt-2  border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs leading-relaxed text-amber-900">
                  Outside the modeled hazard footprint — this refers to the modeled footprint and does not rule out other hazards. Regional warnings still apply.
                </p>
              )}
              {localImpact.verdict === 'uncertain' && (
                warnings.length > 0 ? (
                  <p className="mt-2 text-xs leading-relaxed text-slate-600">Precise local impact is uncertain: footprint geometry is unavailable. The regional warning level above still applies.</p>
                ) : (
                  <p className="mt-2 text-xs leading-relaxed text-slate-600">No official warnings currently apply to this region, so there is no verified footprint to assess against.</p>
                )
              )}
            </div>
          ) : warnings.length > 0 ? (
            <p className="mt-3 text-xs text-slate-600">Local impact assessment is unavailable for this response. The regional warning level above still applies.</p>
          ) : null}
          {warnings.length > 0 && (
            <ul className="mt-3 space-y-2">
              {warnings.map((warning, index) => (
                <li key={`${warning.event_id ?? warning.event_name ?? 'warning'}-${index}`} className=" border border-slate-200 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`inline-flex items-center  border px-2 py-0.5 text-[11px] font-bold ${riskTone[warning.alert_level ?? ''] ?? riskTone.UNKNOWN}`}>
                      {warning.alert_level ?? 'Unrated'}
                    </span>
                    <strong className="text-sm text-slate-900">{warning.event_name ?? 'Unnamed system'}</strong>
                    {warning.country && <span className="text-xs text-slate-500">{warning.country}</span>}
                    {warning.episode_alert_level && <span className="text-[11px] text-slate-500">Episode: {warning.episode_alert_level}</span>}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
                    <span>Max wind: {warning.max_wind_kmh == null ? 'Unavailable' : `${warning.max_wind_kmh.toFixed(0)} km/h`}</span>
                    <span>Impact zone: {formatAffectedPopulation(warning.population_affected)}</span>
                    <span>Updated: {formatWarningUpdated(warning.datemodified)}</span>
                  </div>
                  {warning.link && (
                    <a href={warning.link} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-center gap-1 text-xs font-semibold text-blue-700 underline underline-offset-2">
                      View official source (GDACS/UN) <ExternalLink size={13} />
                    </a>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {hasAssessment && (
        <details className=" border border-slate-200 bg-white p-4 shadow-sm">
          <summary className="cursor-pointer text-sm font-bold text-slate-900">Technical assessment details</summary>
          <div className="mt-3 space-y-4">
            <div>
              <h3 className="text-xs font-bold text-slate-800">Screening and warning floor</h3>
              <p className="mt-1 text-xs text-slate-600">
                Screening {screeningLevel ?? 'unavailable'}{screeningScore == null ? '' : ` (${screeningScore}/100)`} · Official warning floor {warningFloor ?? 'none'} · Combined regional level {riskLevel}
              </p>
              {assessment?.method && <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{assessment.method}</p>}
            </div>
            <div className="border-t border-slate-100 pt-3">
              <h3 className="text-xs font-bold text-slate-800">Model severity probability (H2O)</h3>
              {mlScored && mlProbability?.probability != null ? (
                <div className="mt-1">
                  <p className="text-lg font-black text-slate-900">{(mlProbability.probability * 100).toFixed(1)}%</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-600">{mlProbability.label}</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-600">Screening signal only — not an overall disaster probability and not evidence that the region is safe.{warningFloor ? ` An official ${warningFloor} warning applies regardless of this value.` : ''}</p>
                  {mlProbability.model_id && <p className="mt-1 text-[11px] text-slate-500">Model: {mlProbability.model_id}</p>}
                </div>
              ) : (
                <div className="mt-1">
                  <p className="text-sm font-bold text-slate-700">Unavailable</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-600">{mlProbability?.reason ?? 'No model probability was returned for this assessment.'}</p>
                </div>
              )}
            </div>
            <div className="border-t border-slate-100 pt-3">
              <h3 className="text-xs font-bold text-slate-800">Footprint geometry</h3>
              <p className="mt-1 text-xs text-slate-600">
                {localImpact?.distance_to_footprint_km == null
                  ? 'Distance to footprint: Unavailable'
                  : `Distance to footprint: approx. ${formatImpactDistance(localImpact.distance_to_footprint_km)} (nearest verified vertex)`}
              </p>
              {localImpact?.geometry_source && <p className="mt-1 break-all text-[11px] text-slate-500">Source: {localImpact.geometry_source}</p>}
            </div>
            {warnings.length > 0 && (
              <div className="border-t border-slate-100 pt-3">
                <h3 className="text-xs font-bold text-slate-800">Warning validity and CAP detail</h3>
                <ul className="mt-2 space-y-2">
                  {warnings.map((warning, index) => (
                    <li key={`${warning.event_id ?? warning.event_name ?? 'warning'}-${index}`} className=" border border-slate-200 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <strong className="text-xs text-slate-900">{warning.event_name ?? 'Unnamed system'}</strong>
                        {warning.footprint?.cap_severity && <span className="text-[11px] text-slate-500">CAP: {warning.footprint.cap_severity}</span>}
                        {warning.footprint?.cap_urgency && <span className="text-[11px] text-slate-500">Urgency: {warning.footprint.cap_urgency}</span>}
                        {warning.footprint?.cap_certainty && <span className="text-[11px] text-slate-500">Certainty: {warning.footprint.cap_certainty}</span>}
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
                        <span>Active window: {formatWarningUpdated(warning.fromdate)} to {formatWarningUpdated(warning.todate)}</span>
                        <span>Status: {warning.is_current ? 'Current' : 'Not current'}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </details>
      )}
        <section className="overflow-hidden  border border-slate-200 bg-white shadow-sm xl:col-span-8">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-4 py-3">
            <h2 className="flex items-center gap-2 text-sm font-bold text-slate-800"><Map size={16} className="text-blue-700" /> Response risk zones</h2>
            <span className="text-[11px] text-slate-500">{zones.length} mapped</span>
          </div>
          <MapComponent
            showMangroveLayer={showMangroveLayer}
            onToggleMangrove={onToggleMangrove}
            showHistoricalLayer={showHistoricalLayer}
            onToggleHistorical={onToggleHistorical}
            pois={pois}
            cityLabel={city.name}
            bounds={bounds}
            riskZones={zones}
            isLoading={isLoading}
            emptyMessage="The API returned no facility coordinates or verified risk zones for this region."
          />
        </section>

        <section className=" border border-slate-200 bg-white p-4 shadow-sm xl:col-span-4">
          <h2 className="text-sm font-bold text-slate-900">Assessment details</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">{assessment?.note ?? 'Risk assessment will appear when the API responds.'}</p>
          <div className="mt-4 space-y-2">
            <Fact label="Pressure" value={formatValue(conditions?.pressure_hpa, ' hPa', 1)} />
            <Fact label="Telemetry status" value={dataQuality?.telemetry_status ?? (isLoading ? 'Loading' : 'Unavailable')} />
            <Fact label="Historical analog" value={availableIntelligence?.historical_context.primary_analog ?? 'Unavailable'} />
            {assessment?.factors.map((factor, index) => (
              <div key={`${factor}-${index}`} className="flex gap-2  bg-slate-50 p-2 text-xs leading-relaxed text-slate-700">
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-600" />{factor}
              </div>
            ))}
            {assessment && dataQuality?.telemetry_status === 'AVAILABLE' && assessment.factors.length === 0 && (
              <div className="flex gap-2  bg-emerald-50 p-2 text-xs text-emerald-800">
                <CheckCircle2 size={14} className="shrink-0" />No elevated screening factors were returned.
              </div>
            )}
            {hasAssessment && dataQuality?.telemetry_status !== 'AVAILABLE' && !assessment?.warning_floor && (
              <div className="flex gap-2  bg-amber-50 p-2 text-xs text-amber-900">
                <CircleHelp size={14} className="shrink-0" />Risk factors cannot be assessed without current telemetry.
              </div>
            )}
          </div>
          <div className="mt-4 border-t border-slate-100 pt-3">
            <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase text-slate-500"><Clock3 size={13} /> AI analysis</div>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-700">{analysis?.summary ?? (isLoading ? 'Analysis is loading.' : 'AI analysis unavailable for this response.')}</p>
            {analysis?.reasoning_context.length ? <p className="mt-2 text-[11px] text-slate-500">Evidence: {analysis.reasoning_context.join(' · ')}</p> : null}
          </div>
        </section>
    </div>
  );
};

function Metric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail: string }) {
  return (
    <div className="min-w-0  border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-center gap-2 text-[10px] font-bold uppercase text-slate-500">{icon}{label}</div>
      <div className="mt-2 truncate text-lg font-black text-slate-900">{value}</div>
      <div className="mt-1 truncate text-[10px] text-slate-500" title={detail}>{detail}</div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-2 text-xs">
      <span className="shrink-0 text-slate-500">{label}</span>
      <strong className="max-w-[65%] truncate text-right text-slate-800" title={value}>{value}</strong>
    </div>
  );
}