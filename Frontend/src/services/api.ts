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
  WhatsAppConfigurationResponse,
} from '../types/api';
import type { ClimateAlert } from '../types/alerts';

// Backend ingestion can take minutes on a cold cache (the IBTrACS
// download and parse alone exceeds two minutes), so data endpoints get
// generous per-request timeouts instead of the 60s client default.
const TELEMETRY_TIMEOUT_MS = 120000;
const HISTORY_TIMEOUT_MS = 180000;
const INTELLIGENCE_TIMEOUT_MS = 300000;

export const api = {
  getRegions: (signal?: AbortSignal) => httpClient.get<Record<string, ApiRegion>>('/region', { signal }),
  getPopulation: (region: string, signal?: AbortSignal) =>
    httpClient.get<PopulationResponse>(`/population?region=${encodeURIComponent(region)}`, { signal, timeout: TELEMETRY_TIMEOUT_MS }),
  getForecast: (region: string, signal?: AbortSignal) =>
    httpClient.get<ForecastResponse>(`/forecast?region=${encodeURIComponent(region)}`, { signal, timeout: TELEMETRY_TIMEOUT_MS }),
  getInfrastructure: (region: string, signal?: AbortSignal) =>
    httpClient.get<InfrastructureResponse>(`/shelter?region=${encodeURIComponent(region)}`, { signal, timeout: TELEMETRY_TIMEOUT_MS }),
  getCurrentConditions: (region: string, signal?: AbortSignal) =>
    httpClient.get<CurrentConditionsResponse>(`/current-conditions?region=${encodeURIComponent(region)}`, { signal, timeout: TELEMETRY_TIMEOUT_MS }),
  getHistory: (
    region: string,
    params: { page: number; pageSize: number; search: string; sortBy: 'newest' | 'oldest' | 'wind' | 'distance'; hazard?: string },
    signal?: AbortSignal,
  ) =>
    httpClient.get<HistoricalResponse>(
      `/history?region=${encodeURIComponent(region)}&page=${params.page}&page_size=${params.pageSize}`
      + `&search=${encodeURIComponent(params.search)}&sort_by=${params.sortBy}`
      + (params.hazard ? `&hazard=${encodeURIComponent(params.hazard)}` : ''),
      { signal, timeout: HISTORY_TIMEOUT_MS },
    ),
  getWhatsAppConfiguration: (signal?: AbortSignal) =>
    httpClient.get<WhatsAppConfigurationResponse>('/whatsapp/configuration', { signal }),
  getClimateAlerts: (signal?: AbortSignal) =>
    httpClient.get<ClimateAlert[]>('/alerts', { params: { limit: 500 }, signal }),
  sendDispatchChat: (query: string, region: string) =>
    httpClient.post<DispatchChatResponse, DispatchChatRequest>('/dispatch-chat', { query, region }, { timeout: INTELLIGENCE_TIMEOUT_MS }),
  getDisasterIntelligence: (region: string, hazard = 'cyclone', signal?: AbortSignal) =>
    httpClient.get<DisasterIntelligenceResult>(
      `/disaster-intelligence/${encodeURIComponent(region)}?hazard=${encodeURIComponent(hazard)}`,
      { signal, timeout: INTELLIGENCE_TIMEOUT_MS },
    ),
  getHazardCapabilities: (region: string, signal?: AbortSignal) =>
    httpClient.get<DisasterIntelligenceCapabilities>(
      `/disaster-intelligence/${encodeURIComponent(region)}/capabilities`,
      { signal },
    ),
  startWhatsAppVerification: (phone: string) =>
    httpClient.post<{ status: string }>('/whatsapp/verification/start', { phone }),
  checkWhatsAppVerification: (phone: string, code: string, action: 'subscribe' | 'unsubscribe') =>
    httpClient.post<{ status: string; action: string; welcome_message: 'queued' | 'already_subscribed' | 'not_configured' | 'not_applicable' }>('/whatsapp/verification/check', { phone, code, action }),
};
