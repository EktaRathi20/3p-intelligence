import React from 'react';
import { AlertCircle, CheckCircle2, Database } from 'lucide-react';
import { CityLocation } from '@/types/domain';
import { AlertConnectionState, ClimateAlert } from '@/services/climateAlerts';

interface RightColumnCardsProps {
  city: CityLocation;
  alerts: ClimateAlert[];
  connectionState: AlertConnectionState;
  onOpenAlerts: () => void;
  isLightMode?: boolean;
}

export const RightColumnCards: React.FC<RightColumnCardsProps> = ({ city, alerts, connectionState, onOpenAlerts, isLightMode = true }) => {
  const panelClass = isLightMode ? 'bg-white border-slate-300' : 'bg-slate-900/90 border-slate-800';
  const titleClass = isLightMode ? 'text-[#18365b]' : 'text-slate-100';
  const mutedClass = isLightMode ? 'text-slate-500' : 'text-slate-400';
  const regionAlerts = alerts.filter(alert => !alert.location.region_key || alert.location.region_key === city.id).slice(0, 3);

  return (
    <div className="space-y-4">
      <section className={`border p-3.5 shadow-sm ${panelClass}`}>
        <h2 className={`flex items-center gap-2 text-sm font-bold ${titleClass}`}>
          <Database size={15} className="text-blue-600" /> Backend Data Sources
        </h2>
        <div className="mt-3 space-y-2.5">
          {city.evidenceQuality.items.map(source => (
            <div key={source.label} className="text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className={isLightMode ? 'text-slate-700' : 'text-slate-200'}>{source.label}</span>
                <span className={`flex shrink-0 items-center gap-1 font-semibold ${source.available ? 'text-emerald-700' : 'text-rose-700'}`}>
                  <CheckCircle2 size={13} /> {source.available ? 'Connected' : 'Unavailable'}
                </span>
              </div>
              {!source.available && source.detail && <p className="mt-1 break-words text-[10px] leading-relaxed text-amber-800">{source.detail}</p>}
            </div>
          ))}
        </div>
      </section>

      <section className={`border p-3.5 shadow-sm ${panelClass}`}>
        <h2 className={`flex items-center gap-2 text-sm font-bold ${titleClass}`}>
          <AlertCircle size={15} className="text-amber-600" /> Climate Alerts
        </h2>
        <div className="mt-2 flex items-center justify-between text-[10px]">
          <span className={mutedClass}>{regionAlerts.length} recent for this location</span>
          <span className={`font-bold uppercase tracking-wide ${connectionState === 'connected' ? 'text-emerald-700' : 'text-amber-800'}`}>
            {connectionState === 'connected' ? 'Live' : 'Offline'}
          </span>
        </div>
        <div className="mt-2 space-y-1.5">
          {regionAlerts.map(alert => (
            <button key={alert.id} onClick={onOpenAlerts} className="w-full border border-slate-200 bg-white px-2.5 py-2 text-left hover:bg-slate-50">
              <span className="block truncate text-xs font-semibold text-slate-900">{alert.title}</span>
              <span className="mt-0.5 block truncate text-[10px] text-slate-500">
                {alert.severity.toUpperCase()} · {alert.hazard_type} · {alert.location.name}
              </span>
              <span className="mt-1 block line-clamp-2 text-[10px] leading-relaxed text-slate-600">{alert.description}</span>
            </button>
          ))}
          {regionAlerts.length === 0 && (
            <p className={`border border-dashed border-slate-300 bg-slate-50 px-2.5 py-3 text-xs ${mutedClass}`}>
              No reported climate alerts for this location.
            </p>
          )}
        </div>
        <button onClick={onOpenAlerts} className="mt-2.5 text-xs font-semibold text-[#18365b] underline underline-offset-2 hover:text-[#102744]">
          View all alerts
        </button>
      </section>
    </div>
  );
};
