import { httpClient } from './httpClient';
import type {
  ApiRegion,
  CurrentConditionsResponse,
  DispatchChatRequest,
  DispatchChatResponse,
  DisasterIntelligenceCapabilities,
  DisasterIntelligenceResult,
  ForecastResponse,
  HistoricalResponse,
  InfrastructureResponse,
  PopulationResponse,
} from '../types/api';
import type { ClimateAlert } from '../types/alerts';
import {
  getSimSnapshot,
  isSimulatorActive,
  simDispatchChat,
  simGetHistory,
} from '../simulator/simulatorStore';

// Backend ingestion can take minutes on a cold cache (the IBTrACS
// download and parse alone exceeds two minutes), so data endpoints get
// generous per-request timeouts instead of the 60s client default.
const TELEMETRY_TIMEOUT_MS = 120000;
const HISTORY_TIMEOUT_MS = 180000;
const INTELLIGENCE_TIMEOUT_MS = 300000;

// Simulator Mode: when a drill is active, every read below is served from
// the isolated in-memory drill snapshot instead of the backend. Live paths
// are untouched and run exactly as before when the simulator is off.

export const api = {
  getRegions: (signal?: AbortSignal) => {
    if (isSimulatorActive()) return Promise.resolve<Record<string, ApiRegion>>(getSimSnapshot().apiRegions);
    return httpClient.get<Record<string, ApiRegion>>('/region', { signal });
  },
  getPopulation: (region: string, signal?: AbortSignal) => {
    if (isSimulatorActive()) return Promise.resolve<PopulationResponse>(getSimSnapshot().population);
    return httpClient.get<PopulationResponse>(`/population?region=${encodeURIComponent(region)}`, { signal, timeout: TELEMETRY_TIMEOUT_MS });
  },
  getForecast: (region: string, signal?: AbortSignal) => {
    if (isSimulatorActive()) return Promise.resolve<ForecastResponse>(getSimSnapshot().forecast);
    return httpClient.get<ForecastResponse>(`/forecast?region=${encodeURIComponent(region)}`, { signal, timeout: TELEMETRY_TIMEOUT_MS });
  },
  getInfrastructure: (region: string, signal?: AbortSignal) => {
    if (isSimulatorActive()) return Promise.resolve<InfrastructureResponse>(getSimSnapshot().infrastructure);
    return httpClient.get<InfrastructureResponse>(`/shelter?region=${encodeURIComponent(region)}`, { signal, timeout: TELEMETRY_TIMEOUT_MS });
  },
  getCurrentConditions: (region: string, signal?: AbortSignal) => {
    if (isSimulatorActive()) return Promise.resolve<CurrentConditionsResponse>(getSimSnapshot().currentConditions);
    return httpClient.get<CurrentConditionsResponse>(`/current-conditions?region=${encodeURIComponent(region)}`, { signal, timeout: TELEMETRY_TIMEOUT_MS });
  },
  getHistory: (
    region: string,
    params: { page: number; pageSize: number; search: string; sortBy: 'newest' | 'oldest' | 'wind' | 'distance'; hazard?: string },
    signal?: AbortSignal,
  ) => {
    if (isSimulatorActive()) return Promise.resolve<HistoricalResponse>(simGetHistory(params));
    return httpClient.get<HistoricalResponse>(
      `/history?region=${encodeURIComponent(region)}&page=${params.page}&page_size=${params.pageSize}`
      + `&search=${encodeURIComponent(params.search)}&sort_by=${params.sortBy}`
      + (params.hazard ? `&hazard=${encodeURIComponent(params.hazard)}` : ''),
      { signal, timeout: HISTORY_TIMEOUT_MS },
    );
  },
  getClimateAlerts: (signal?: AbortSignal) => {
    if (isSimulatorActive()) return Promise.resolve<ClimateAlert[]>([...getSimSnapshot().alerts]);
    return httpClient.get<ClimateAlert[]>('/alerts', { params: { limit: 500 }, signal });
  },
  sendDispatchChat: (query: string, region: string) => {
    if (isSimulatorActive()) return Promise.resolve<DispatchChatResponse>(simDispatchChat(query));
    return httpClient.post<DispatchChatResponse, DispatchChatRequest>('/dispatch-chat', { query, region }, { timeout: INTELLIGENCE_TIMEOUT_MS });
  },
  getDisasterIntelligence: (region: string, hazard = 'cyclone', signal?: AbortSignal) => {
    if (isSimulatorActive()) return Promise.resolve<DisasterIntelligenceResult>(getSimSnapshot().intelligence);
    return httpClient.get<DisasterIntelligenceResult>(
      `/disaster-intelligence/${encodeURIComponent(region)}?hazard=${encodeURIComponent(hazard)}`,
      { signal, timeout: INTELLIGENCE_TIMEOUT_MS },
    );
  },
  getHazardCapabilities: (region: string, signal?: AbortSignal) => {
    if (isSimulatorActive()) return Promise.resolve<DisasterIntelligenceCapabilities>(getSimSnapshot().capabilities);
    return httpClient.get<DisasterIntelligenceCapabilities>(
      `/disaster-intelligence/${encodeURIComponent(region)}/capabilities`,
      { signal },
    );
  },
};
