import { useNavigate, useOutletContext } from 'react-router-dom';
import { LayoutDashboard } from 'lucide-react';
import { AssessmentCards } from '@/components/dashboard/AssessmentCards';
import { BottomRowCards } from '@/components/dashboard/BottomRowCards';
import { MapComponent } from '@/components/dashboard/MapComponent';
import { RightColumnCards } from '@/components/dashboard/RightColumnCards';
import { WeatherHazardChart } from '@/components/dashboard/WeatherHazardChart';
import type { DashboardOutletData } from '../types/dashboard';
import { buildMapPois } from '../utils/transformers';
import { isAvailableDisasterIntelligence } from '../types/api';

const RISK_BADGE: Record<string, string> = {
  Red: 'border-red-300 bg-red-700 text-white',
  Orange: 'border-orange-300 bg-orange-600 text-white',
  Moderate: 'border-amber-300 bg-amber-500 text-white',
  Normal: 'border-emerald-300 bg-emerald-600 text-white',
  Unavailable: 'border-white/40 bg-white/10 text-white',
};

export default function OverviewPage() {
  const dashboard = useOutletContext<DashboardOutletData>();
  const navigate = useNavigate();
  const { selectedCity, selectedRegion, regionResponses, activeIntelligence, displayedResponses } = dashboard;
  if (!selectedCity || !selectedRegion) return null;
  const riskZones = isAvailableDisasterIntelligence(activeIntelligence)
    ? activeIntelligence.risk_zones
    : [];

  return (
    <div className="space-y-4">
      <header className="border border-slate-300 bg-[#18365b] px-4 py-3 text-white shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center border border-white/30 bg-white/10">
              <LayoutDashboard size={20} />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-blue-200">
                Overview of current situation
              </p>
              <h1 className="mt-0.5 text-lg font-bold leading-6 sm:text-xl">
                Dashboard — {selectedCity.name}
              </h1>
              <p className="mt-1 text-xs text-blue-100">
                {selectedCity.coordinatesFormatted} · Population {selectedCity.populationFormatted}
              </p>
            </div>
          </div>
          <span className={`border px-2 py-1 text-[11px] font-bold uppercase tracking-wide ${RISK_BADGE[selectedCity.riskLevel] ?? RISK_BADGE.Unavailable}`}>
            Risk: {selectedCity.riskLevel}
          </span>
        </div>
      </header>

      <AssessmentCards city={selectedCity} infrastructure={regionResponses?.infrastructure ?? null} isLightMode />
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8 space-y-4">
          <MapComponent
            showMangroveLayer={dashboard.showMangroveLayer}
            onToggleMangrove={dashboard.setShowMangroveLayer}
            showHistoricalLayer={dashboard.showHistoricalLayer}
            onToggleHistorical={dashboard.setShowHistoricalLayer}
            systemStatusLabel="System: Operational"
            systemStatusColor="amber"
            isLightMode
            pois={buildMapPois(displayedResponses, selectedRegion)}
            cityLabel={selectedCity.name}
            bounds={selectedRegion}
            riskZones={riskZones}
            isLoading={dashboard.regionLoading}
            emptyMessage={Object.values(regionResponses?.infrastructure?.source_errors ?? {}).join(' ') || 'The provider returned no facility coordinates for this region.'}
          />
          <WeatherHazardChart forecast={regionResponses?.forecast?.forecast ?? []} isLightMode />
        </div>
        <div className="lg:col-span-4">
          <RightColumnCards
            city={selectedCity}
            alerts={dashboard.alerts}
            connectionState={dashboard.connectionState}
            onOpenAlerts={() => {
              dashboard.markAllRead();
              navigate('/alerts');
            }}
            isLightMode
          />
          <BottomRowCards infrastructure={regionResponses?.infrastructure ?? null} isLightMode />
        </div>
      </div>
    </div>
  );
}
