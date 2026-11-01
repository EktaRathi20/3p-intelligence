import { useOutletContext } from 'react-router-dom';
import { LandfallRescueModeView } from '@/components/dashboard/modes/LandfallRescueModeView';
import type { DashboardOutletData } from '../types/dashboard';
import { buildMapPois } from '../utils/transformers';

export default function LandfallPage() {
  const dashboard = useOutletContext<DashboardOutletData>();
  const {
    selectedCity,
    selectedRegion,
    selectedRegionKey,
    displayedResponses,
    activeIntelligence,
    regionResponses,
  } = dashboard;
  if (!selectedCity || !selectedRegion) return null;

  return (
    <LandfallRescueModeView
      city={selectedCity}
      regionKey={selectedRegionKey}
      bounds={selectedRegion}
      pois={buildMapPois(displayedResponses, selectedRegion)}
      disasterIntelligence={activeIntelligence}
      intelligenceError={regionResponses?.disasterIntelligenceError ?? null}
      infrastructure={regionResponses?.infrastructure ?? null}
      regionDataError={dashboard.regionDataError}
      regionLoading={dashboard.regionLoading}
      alerts={dashboard.alerts}
      alertsError={dashboard.alertsError}
      alertsLoading={dashboard.alertsLoading}
      connectionState={dashboard.connectionState}
      retryAlerts={dashboard.retryAlerts}
      retryRegionData={dashboard.retryRegionData}
      isLightMode
    />
  );
}
