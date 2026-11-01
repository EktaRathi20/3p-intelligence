import { useMemo } from 'react';
import { MapComponent, type AlertMarker } from '@/components/dashboard/MapComponent';
import type { ApiRegion, DisasterRiskZone } from '@/types/api';
import type { ClimateAlert } from '@/types/alerts';
import type { MapPOI } from '@/types/domain';
import { DataBadge, SectionCard } from './rescueShared';

const UNAVAILABLE_LAYERS = [
  { label: 'Rescue team GPS', reason: 'No team tracking feed' },
  { label: 'Ambulance GPS', reason: 'No fleet feed' },
  { label: 'Blocked roads', reason: 'No road-closure feed' },
  { label: 'Evacuation route geometry', reason: 'Routes are text guidance only' },
];

export function OperationsMap({
  bounds,
  pois,
  cityLabel,
  riskZones,
  alerts,
  isLoading,
  emptyMessage,
}: {
  bounds: ApiRegion;
  pois: MapPOI[];
  cityLabel: string;
  riskZones: DisasterRiskZone[];
  alerts: ClimateAlert[];
  isLoading: boolean;
  emptyMessage: string;
}) {
  const alertMarkers: AlertMarker[] = useMemo(
    () =>
      alerts
        .filter(
          (alert) =>
            !alert.is_simulation &&
            alert.location.latitude != null &&
            alert.location.longitude != null,
        )
        .map((alert) => ({
          id: alert.id,
          title: alert.title,
          severity: alert.severity,
          lat: alert.location.latitude as number,
          lon: alert.location.longitude as number,
        })),
    [alerts],
  );

  return (
    <SectionCard
      title="Operations Map"
      subtitle="Facilities, risk zones and alert locations from connected backend feeds."
      badge={<DataBadge provenance="verified" title="Markers come from backend snapshots. No positions are simulated." />}
    >
      <div className="min-h-0 flex-1 p-3">
        <MapComponent
          pois={pois}
          cityLabel={cityLabel}
          bounds={bounds}
          riskZones={riskZones}
          alertMarkers={alertMarkers}
          isLoading={isLoading}
          emptyMessage={emptyMessage}
        />
        <div className="mt-2.5 grid grid-cols-2 gap-1.5 text-[11px] sm:grid-cols-4" aria-label="Map layer availability">
          <LayerChip color="#059669" label="Shelters" available />
          <LayerChip color="#e11d48" label="Hospitals" available />
          <LayerChip color="#d97706" label="Risk zones" available={riskZones.length > 0} />
          <LayerChip color="#dc2626" label="Alerts" available={alertMarkers.length > 0} dashed />
        </div>
        <div className="mt-2 border border-slate-200 bg-slate-50 px-3 py-2">
          <p className="text-[11px] font-semibold text-slate-700">Layers not shown — no live feed</p>
          <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            {UNAVAILABLE_LAYERS.map((layer) => (
              <li key={layer.label} className="text-[11px] text-slate-500" title={layer.reason}>
                <span className="font-medium text-slate-600">{layer.label}</span> · {layer.reason}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </SectionCard>
  );
}

function LayerChip({
  color,
  label,
  available,
  dashed,
}: {
  color: string;
  label: string;
  available: boolean;
  dashed?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 border px-2 py-1 font-medium ${
        available ? 'border-slate-200 bg-white text-slate-700' : 'border-slate-200 bg-slate-50 text-slate-400'
      }`}
      title={available ? `${label}: plotted from backend data` : `${label}: no data returned`}
    >
      <span
        aria-hidden="true"
        className="inline-block h-2.5 w-2.5 rounded-full border border-white"
        style={{
          backgroundColor: available ? color : '#cbd5e1',
          outline: dashed ? `1px dashed ${available ? color : '#cbd5e1'}` : undefined,
          outlineOffset: 1,
        }}
      />
      {label}
      {!available && ' (none)'}
    </span>
  );
}
