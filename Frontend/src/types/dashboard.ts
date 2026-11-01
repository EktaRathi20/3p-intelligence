import type { Dispatch, SetStateAction } from 'react';
import type { ClimateAlert } from './alerts';
import type {
  ApiRegion,
  DisasterIntelligenceCapabilities,
  DisasterIntelligenceResult,
  RegionResponses,
} from './api';
import type { CityLocation } from './domain';

export interface DashboardOutletData {
  alerts: ClimateAlert[];
  unreadCount: number;
  connectionState: 'connecting' | 'connected' | 'disconnected';
  alertsError: string | null;
  alertsLoading: boolean;
  retryAlerts: () => void;
  markAllRead: () => void;
  regions: Record<string, ApiRegion>;
  selectedRegionKey: string;
  setSelectedRegionKey: Dispatch<SetStateAction<string>>;
  defaultRegionKey: string | null;
  selectedRegion: ApiRegion | undefined;
  selectedCity: CityLocation | null;
  availableCities: CityLocation[];
  regionResponses: RegionResponses | null;
  displayedResponses: RegionResponses | null;
  activeIntelligence: DisasterIntelligenceResult | null;
  hazardCapabilities: DisasterIntelligenceCapabilities | null;
  selectedHazard: string;
  setSelectedHazard: Dispatch<SetStateAction<string>>;
  regionLoading: boolean;
  regionError: string | null;
  regionDataError: string | null;
  retryRegions: () => void;
  retryRegionData: () => void;
  showMangroveLayer: boolean;
  setShowMangroveLayer: Dispatch<SetStateAction<boolean>>;
  showHistoricalLayer: boolean;
  setShowHistoricalLayer: Dispatch<SetStateAction<boolean>>;
  isEvacuationModalOpen: boolean;
  setIsEvacuationModalOpen: Dispatch<SetStateAction<boolean>>;
  toastAlert: ClimateAlert | null;
  setToastAlert: Dispatch<SetStateAction<ClimateAlert | null>>;
}
