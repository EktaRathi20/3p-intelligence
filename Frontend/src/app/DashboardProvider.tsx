import { useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { regionApi } from '../services/regionApi';
import { resolveDefaultRegionKey } from '../utils/regionDefault';
import { Outlet, useLocation } from 'react-router-dom';
import { api } from '../services/api';
import type {
  ApiRegion,
  DisasterIntelligenceCapabilities,
  DisasterIntelligenceResponse,
  RegionResponses,
} from '../types/api';
import { ClimateAlert } from '../services/climateAlerts';
import { useClimateAlerts } from '../hooks/useClimateAlerts';
import { createSimulatedIntelligence, SimulationTier } from '../features/simulator/simulator';
import { buildCity } from '../utils/transformers';
import type { DashboardOutletData } from '../types/dashboard';
import { isAbortError } from '../services/apiError';

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'The request failed unexpectedly.';

const routeModes = {
  '/overview': 'overview',
  '/baseline': 'baseline',
  '/threat': 'threat',
  '/tasks': 'tasks',
  '/landfall': 'landfall',
  '/recovery': 'recovery',
  '/simulator': 'simulator',
} as const;

export default function DashboardProvider() {
  const location = useLocation();
  const mode = routeModes[location.pathname as keyof typeof routeModes] ?? 'threat';
  const {
    alerts,
    simulationAlerts,
    latestLiveAlert,
    unreadCount,
    connectionState,
    error: alertsError,
    isLoading: alertsLoading,
    retry: retryAlerts,
    markAllRead,
  } = useClimateAlerts();

  const [regions, setRegions] = useState<Record<string, ApiRegion>>({});
  const [selectedRegionKey, setSelectedRegionKey] = useState('');
  const [defaultRegionKey, setDefaultRegionKey] = useState<string | null>(null);
  const [selectedHazard, setSelectedHazard] = useState('cyclone');
  const [hazardCapabilities, setHazardCapabilities] = useState<DisasterIntelligenceCapabilities | null>(null);
  const [regionResponses, setRegionResponses] = useState<RegionResponses | null>(null);
  const [simulationTier, setSimulationTier] = useState<SimulationTier | null>(null);
  const [simulatedIntelligence, setSimulatedIntelligence] = useState<DisasterIntelligenceResponse | null>(null);
  const [regionLoading, setRegionLoading] = useState(true);
  const [regionError, setRegionError] = useState<string | null>(null);
  const [regionDataError, setRegionDataError] = useState<string | null>(null);
  const [regionsRetry, setRegionsRetry] = useState(0);
  const [regionDataRetry, setRegionDataRetry] = useState(0);
  const [toastAlert, setToastAlert] = useState<ClimateAlert | null>(null);
  const [showMangroveLayer, setShowMangroveLayer] = useState(true);
  const [showHistoricalLayer, setShowHistoricalLayer] = useState(false);
  const [isEvacuationModalOpen, setIsEvacuationModalOpen] = useState(false);

  const setSelectedRegionKeyTracked: Dispatch<SetStateAction<string>> = (value) => {
    setSelectedRegionKey(value);
  };
  const selectedRegion = regions[selectedRegionKey];
  const activeIntelligence = mode === 'simulator'
    ? simulatedIntelligence ?? regionResponses?.disasterIntelligence ?? null
    : regionResponses?.disasterIntelligence ?? null;
  const displayedResponses = regionResponses
    ? { ...regionResponses, disasterIntelligence: activeIntelligence }
    : null;
  const selectedCity = selectedRegion ? buildCity(selectedRegionKey, selectedRegion, displayedResponses) : null;
  const availableCities = Object.entries(regions).map(([key, region]) => buildCity(key, region, null));

  const runSimulation = (tier: SimulationTier, regionKey = selectedRegionKey, region = selectedRegion) => {
    if (!region) return;
    setSimulatedIntelligence(createSimulatedIntelligence(
      regionKey === selectedRegionKey ? regionResponses?.disasterIntelligence ?? null : null,
      regionKey,
      region,
      tier,
    ));
    setSimulationTier(tier);
  };

  const resetSimulation = () => {
    setSimulatedIntelligence(null);
    setSimulationTier(null);
  };

  useEffect(() => {
    const onDefaultChanged = () => setRegionsRetry(value => value + 1);
    const onRegionHazardsChanged = () => setRegionDataRetry(value => value + 1);
    window.addEventListener('region-default-changed', onDefaultChanged);
    window.addEventListener('region-hazards-changed', onRegionHazardsChanged);
    return () => {
      window.removeEventListener('region-default-changed', onDefaultChanged);
      window.removeEventListener('region-hazards-changed', onRegionHazardsChanged);
    };
  }, []);
  useEffect(() => {
    if (!latestLiveAlert) return;
    setToastAlert(latestLiveAlert);
  }, [latestLiveAlert]);

  useEffect(() => {
    if (!toastAlert) return;
    const timeout = window.setTimeout(() => setToastAlert(null), 7000);
    return () => window.clearTimeout(timeout);
  }, [toastAlert]);

  useEffect(() => {
    const controller = new AbortController();
    setRegionLoading(true);
    setRegionError(null);
    setRegions({});
    setSelectedRegionKey('');
    setDefaultRegionKey(null);
    setHazardCapabilities(null);
    setRegionResponses(null);
    setSimulatedIntelligence(null);
    setSimulationTier(null);
    const loadDefaultRegion = async () => {
      try {
        const config = await regionApi.getConfiguration(controller.signal);
        if (controller.signal.aborted) return;
        if (!config.defaultRegionId) {
          throw new Error('No default region is configured. Set one in Region Management and retry.');
        }

        const [record, data] = await Promise.all([
          regionApi.getRegion(config.defaultRegionId, controller.signal),
          api.getRegions(controller.signal),
        ]);
        if (controller.signal.aborted) return;
        const resolvedKey = resolveDefaultRegionKey([record], config.defaultRegionId, Object.keys(data));
        if (!resolvedKey || !data[resolvedKey]) {
          throw new Error('The configured default region is not available in dashboard data. Update it in Region Management and retry.');
        }

        setRegions(data);
        setDefaultRegionKey(resolvedKey);
        setSelectedRegionKey(resolvedKey);
      } catch (error: unknown) {
        if (!controller.signal.aborted && !isAbortError(error)) {
          setRegionError(errorMessage(error));
        }
      } finally {
        if (!controller.signal.aborted) setRegionLoading(false);
      }
    };
    void loadDefaultRegion();
    return () => controller.abort();
  }, [regionsRetry]);

  useEffect(() => {
    if (!selectedRegion) return;
    const controller = new AbortController();
    setRegionLoading(true);
    setRegionResponses(null);
    setRegionDataError(null);
    Promise.allSettled([
      api.getPopulation(selectedRegionKey, controller.signal),
      api.getForecast(selectedRegionKey, controller.signal),
      api.getInfrastructure(selectedRegionKey, controller.signal),
      api.getCurrentConditions(selectedRegionKey, controller.signal),
      api.getDisasterIntelligence(selectedRegionKey, selectedHazard, controller.signal),
      api.getHazardCapabilities(selectedRegionKey, controller.signal),
    ]).then(([population, forecast, infrastructure, currentConditions, disasterIntelligence, capabilities]) => {
      if (controller.signal.aborted) return;
      setRegionResponses({
        population: population.status === 'fulfilled' ? population.value : null,
        forecast: forecast.status === 'fulfilled' ? forecast.value : null,
        infrastructure: infrastructure.status === 'fulfilled' ? infrastructure.value : null,
        currentConditions: currentConditions.status === 'fulfilled' ? currentConditions.value : null,
        disasterIntelligence: disasterIntelligence.status === 'fulfilled' ? disasterIntelligence.value : null,
        currentConditionsError: currentConditions.status === 'rejected' ? errorMessage(currentConditions.reason) : null,
        disasterIntelligenceError: disasterIntelligence.status === 'rejected'
          ? errorMessage(disasterIntelligence.reason)
          : null,
      });
      setHazardCapabilities(capabilities.status === 'fulfilled' ? capabilities.value : null);
      const hasFailedSources = [population, forecast, infrastructure, currentConditions, disasterIntelligence, capabilities]
        .some(result => result.status === 'rejected');
      setRegionDataError(hasFailedSources ? 'Some dashboard information is temporarily unavailable.' : null);
    }).finally(() => {
      if (!controller.signal.aborted) setRegionLoading(false);
    });
    return () => controller.abort();
  }, [selectedRegion, selectedRegionKey, selectedHazard, regionDataRetry]);

  const retryRegions = () => setRegionsRetry(value => value + 1);
  const retryRegionData = () => setRegionDataRetry(value => value + 1);

  const outletData: DashboardOutletData = {
    alerts,
    simulationAlerts,
    unreadCount,
    connectionState,
    alertsError,
    alertsLoading,
    retryAlerts,
    markAllRead,
    regions,
    selectedRegionKey,
    setSelectedRegionKey: setSelectedRegionKeyTracked,
    defaultRegionKey,
    selectedRegion,
    selectedCity,
    availableCities,
    regionResponses,
    displayedResponses,
    activeIntelligence,
    hazardCapabilities,
    selectedHazard,
    setSelectedHazard,
    regionLoading,
    regionError,
    regionDataError,
    retryRegions,
    retryRegionData,
    simulationTier,
    runSimulation,
    resetSimulation,
    showMangroveLayer,
    setShowMangroveLayer,
    showHistoricalLayer,
    setShowHistoricalLayer,
    isEvacuationModalOpen,
    setIsEvacuationModalOpen,
    toastAlert,
    setToastAlert,
  };

  return <Outlet context={outletData} />;
}