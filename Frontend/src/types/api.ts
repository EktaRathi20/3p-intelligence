import type { VerifiedRoute } from './domain';

export interface DispatchChatRequest {
  query: string;
  region: string;
}

export interface DispatchChatResponse {
  text: string;
  verifiedRoute: VerifiedRoute;
}

export interface ApiRegion {
  min_lon: number;
  min_lat: number;
  max_lon: number;
  max_lat: number;
  name: string;
}

export interface PopulationResponse {
  timestamp: string;
  region_target: string;
  total_population: number | null;
  source_error?: string;
}

export interface ForecastDayResponse {
  date: string;
  max_temp_c: number;
  min_temp_c: number;
  condition: string;
}

export interface ForecastResponse {
  region_target: string;
  latitude: number;
  longitude: number;
  forecast: ForecastDayResponse[];
}

export interface FacilityResponse {
  name: string;
  address: string | null;
  lat: number | null;
  lon: number | null;
}

export interface InfrastructureResponse {
  hospitals: FacilityResponse[];
  shelters: FacilityResponse[];
  source_errors?: Record<string, string>;
}

export interface CurrentConditionsResponse {
  timestamp: string;
  region_target: string;
  temperature_c: number | null;
  condition: string | null;
  wind_speed_kmh: number | null;
  wind_direction: string | null;
  pressure_hpa: number | null;
  relative_humidity_percent: number | null;
}

export interface HistoricalEventResponse {
  matched_cyclone: string;
  hazard_type?: string;
  historical_peak_wind_kmh: number | null;
  historical_surge_meters: number | null;
  closest_approach_km: number;
  source: string;
  reference_period: {
    start_date: string;
    end_date: string;
  };
}

export interface HistoricalResponse {
  timestamp: string;
  region_target: string;
  source: string;
  source_url: string;
  total_historical_events_analyzed: number;
  page: number;
  page_size: number;
  total_events: number;
  matching_events: number;
  total_pages: number;
  historical_analogs: HistoricalEventResponse[];
  available_hazards?: string[];
  hazards_with_records?: string[];
  history_coverage?: {
    complete: boolean;
    note: string;
  };
}

export interface HazardCapability {
  id: string;
  name: string;
  code: string | null;
  configured: boolean;
  implemented: boolean;
  intelligence_status: 'available' | 'not_configured' | 'not_implemented';
}

export interface DisasterIntelligenceCapabilities {
  region: string;
  hazards: HazardCapability[];
  configured_hazards: string[];
  implemented_hazards: string[];
  not_implemented_hazards: string[];
  historical_hazards: string[];
  history_coverage: {
    complete: boolean;
    note: string;
  };
}

export interface DisasterRiskZone {
  id: string;
  label: string;
  color: 'red' | 'orange' | 'yellow' | 'green';
  lat: number | null;
  lon: number | null;
  radius_km: number;
  description?: string;
  basis?: string[];
}

export interface DisasterWarningFootprint {
  polygons: number[][][];
  circles: Array<{ center: [number, number]; radius_km: number }>;
  cap_severity?: string | null;
  cap_urgency?: string | null;
  cap_certainty?: string | null;
  cap_headline?: string | null;
  cap_sent?: string | null;
  simplified?: boolean;
  source_url?: string | null;
}

export interface DisasterOfficialWarning {
  event_id?: string | null;
  episode_id?: string | null;
  event_name?: string | null;
  event_type?: string | null;
  title?: string | null;
  description?: string | null;
  alert_level?: string | null;
  episode_alert_level?: string | null;
  severity_text?: string | null;
  max_wind_kmh?: number | null;
  population_affected?: number | null;
  vulnerability?: string | null;
  iso3?: string | null;
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  bbox?: { lonmin: number; lonmax: number; latmin: number; latmax: number } | null;
  fromdate?: string | null;
  todate?: string | null;
  datemodified?: string | null;
  is_current?: boolean;
  link?: string | null;
  cap_url?: string | null;
  glide?: string | null;
  matched_region?: string;
  footprint?: DisasterWarningFootprint | null;
}

export interface DisasterLocalImpact {
  verdict: 'inside_footprint' | 'outside_footprint' | 'uncertain' | string;
  basis: string[];
  distance_to_footprint_km: number | null;
  geometry_source: string | null;
}

export interface DisasterLocalImpactAssessment {
  regional_warning_level: string | null;
  regional_warning_status: 'active' | 'expired' | 'unavailable' | 'none' | string;
  local_impact_status: 'inside_footprint' | 'outside_footprint' | 'uncertain' | string;
  local_impact_zone: 'RED' | 'ORANGE' | 'YELLOW' | 'GREEN' | 'UNKNOWN' | string;
  distance_to_footprint_km: number | null;
  reason: string;
  source: string | null;
  updated_at: string | null;
}

export interface DisasterMlProbability {
  status: 'SCORED' | 'UNAVAILABLE' | string;
  probability: number | null;
  model_id: string | null;
  features_used: Record<string, number> | null;
  label: string;
  reason: string | null;
  note: string;
}

export interface DisasterInsuranceSummary {
  status: 'UNAVAILABLE' | 'EVALUATED';
  trigger_met: boolean | null;
  trigger_threshold_m: number | null;
  observed_water_depth_m: number | null;
  estimated_payout_cr: number | null;
  headline: string;
  coverage_focus: string[];
  note?: string;
}

export interface DisasterRecommendedTask {
  department: string;
  location: string;
  description: string;
  priority?: 'critical' | 'high' | 'moderate' | 'low' | string;
  sub_team?: string;
  status_text?: string;
}

export interface DisasterIntelligenceResponse {
  status: string;
  region: string;
  hazard?: string;
  supported?: true;
  generated_at: string;
  ml_probability?: DisasterMlProbability;
  local_impact_assessment?: DisasterLocalImpactAssessment;
  data_quality: {
    ingestion_status: 'SUCCESS' | 'FAILED' | string;
    telemetry_status: 'AVAILABLE' | 'UNAVAILABLE' | 'NO_CURRENT_MEASUREMENTS' | string;
    ingestion_error: string | null;
    telemetry_timestamp: string | null;
    source_errors?: Record<string, string>;
    sources: Record<string, string | null>;
  };
  current_conditions: {
    wind_speed_kmh: number | null;
    pressure_hpa: number | null;
    storm_surge_meters: number | null;
    wave_height_m?: number | null;
    alert_status: string;
  };
  risk_assessment: {
    level: string;
    score: number;
    factors: string[];
    method: string;
    official_warning: boolean;
    screening_level?: string;
    warning_floor?: string | null;
    level_basis?: string;
    note: string;
  };
  risk_zones: DisasterRiskZone[];
  official_warnings?: DisasterOfficialWarning[];
  local_impact?: DisasterLocalImpact;
  historical_context: {
    primary_analog: string | null;
    historical_analogs: Array<Record<string, unknown>>;
  };
  demography: {
    total_population?: number | null;
    [key: string]: unknown;
  };
  critical_places: {
    hospitals?: Array<{ name: string; address?: string | null; lat?: number | null; lon?: number | null }>;
    shelters?: Array<{ name: string; address?: string | null; lat?: number | null; lon?: number | null }>;
    source_errors?: Record<string, string>;
    [key: string]: unknown;
  };
  insurance_summary: DisasterInsuranceSummary;
  ai_analysis: {
    summary: string | null;
    recommended_tasks: DisasterRecommendedTask[];
    reasoning_context: string[];
  };
}

export interface UnavailableDisasterIntelligenceResponse {
  region: string;
  hazard: string;
  status: 'not_configured' | 'not_implemented';
  supported: false;
  message: string;
}

export type DisasterIntelligenceResult =
  | DisasterIntelligenceResponse
  | UnavailableDisasterIntelligenceResponse;

export function isAvailableDisasterIntelligence(
  result: DisasterIntelligenceResult | null | undefined,
): result is DisasterIntelligenceResponse {
  return result !== null && result !== undefined && 'risk_assessment' in result;
}

export interface RegionResponses {
  population: PopulationResponse | null;
  forecast: ForecastResponse | null;
  infrastructure: InfrastructureResponse | null;
  currentConditions: CurrentConditionsResponse | null;
  disasterIntelligence: DisasterIntelligenceResult | null;
  currentConditionsError: string | null;
  disasterIntelligenceError: string | null;
}
