import { useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";
import type {
  ApiRegion,
  DisasterIntelligenceResult,
  FacilityResponse,
  InfrastructureResponse,
} from "@/types/api";
import { isAvailableDisasterIntelligence } from "@/types/api";
import type { ClimateAlert } from "@/types/alerts";
import type { CityLocation, MapPOI } from "@/types/domain";
import { ActivityLog } from "./ActivityLog";
import { DispatchPanel } from "./DispatchPanel";
import { OperationsMap } from "./OperationsMap";
import { RouteIntelligence } from "./RouteIntelligence";
import { ShelterReliefPanel } from "./ShelterReliefPanel";
import { SituationOverview } from "./SituationOverview";
import { TacticalAssistant, type RouteRecord } from "./TacticalAssistant";
import { useCommandCentreData } from "./useCommandCentreData";
import {
  DataBadge,
  ErrorState,
  formatAge,
  formatDateTime,
  outlineButtonClass,
  type DataProvenance,
} from "./rescueShared";

export interface RescueCommandCentreProps {
  city: CityLocation;
  regionKey: string;
  bounds: ApiRegion;
  pois: MapPOI[];
  disasterIntelligence: DisasterIntelligenceResult | null;
  intelligenceError: string | null;
  infrastructure: InfrastructureResponse | null;
  regionDataError: string | null;
  regionLoading: boolean;
  alerts: ClimateAlert[];
  alertsError: string | null;
  alertsLoading: boolean;
  connectionState: "connecting" | "connected" | "disconnected";
  retryAlerts: () => void;
  retryRegionData: () => void;
}

const RISK_BADGE: Record<CityLocation["riskLevel"], string> = {
  Red: "border-red-700 bg-red-700 text-white",
  Orange: "border-orange-600 bg-orange-50 text-orange-800",
  Moderate: "border-amber-500 bg-amber-50 text-amber-900",
  Normal: "border-emerald-700 bg-emerald-50 text-emerald-800",
  Unavailable: "border-slate-300 bg-slate-100 text-slate-600",
};

function normalizeFacilities(
  items:
    | Array<{
        name: string;
        address?: string | null;
        lat?: number | null;
        lon?: number | null;
      }>
    | undefined,
): FacilityResponse[] {
  return (items ?? []).map((item) => ({
    name: item.name,
    address: item.address ?? null,
    lat: item.lat ?? null,
    lon: item.lon ?? null,
  }));
}

export function RescueCommandCentre(props: RescueCommandCentreProps) {
  const {
    city,
    regionKey,
    bounds,
    pois,
    disasterIntelligence,
    intelligenceError,
    infrastructure,
    regionDataError,
    regionLoading,
    alerts,
    alertsError,
    alertsLoading,
    connectionState,
    retryAlerts,
    retryRegionData,
  } = props;

  const [routes, setRoutes] = useState<RouteRecord[]>([]);
  const command = useCommandCentreData(regionKey);

  const intelligence = isAvailableDisasterIntelligence(disasterIntelligence)
    ? disasterIntelligence
    : null;
  const riskZones = intelligence?.risk_zones ?? [];

  const {
    shelters,
    hospitals,
    facilitiesProvenance,
    facilitiesTitle,
    sourceErrors,
  } = useMemo(() => {
    const critical = intelligence?.critical_places;
    const hasIntelFacilities =
      (critical?.hospitals?.length ?? 0) > 0 ||
      (critical?.shelters?.length ?? 0) > 0;
    const useIntel = hasIntelFacilities || !infrastructure;
    const shelterList = useIntel
      ? normalizeFacilities(critical?.shelters)
      : (infrastructure?.shelters ?? []);
    const hospitalList = useIntel
      ? normalizeFacilities(critical?.hospitals)
      : (infrastructure?.hospitals ?? []);
    const errors = {
      ...(infrastructure?.source_errors ?? {}),
      ...((critical?.source_errors as Record<string, string> | undefined) ??
        {}),
    };
    const errorText = Object.values(errors).join(" ") || null;
    const provenance: DataProvenance =
      shelterList.length + hospitalList.length > 0 ? "verified" : "unavailable";
    return {
      shelters: shelterList,
      hospitals: hospitalList,
      facilitiesProvenance: provenance,
      facilitiesTitle:
        provenance === "verified"
          ? "Facility names, addresses and coordinates from the backend places feed (snapshot, no live status)."
          : (errorText ??
            "The backend returned no facility data for this region."),
      sourceErrors: errorText,
    };
  }, [intelligence, infrastructure]);

  const shelterCount = pois.filter((poi) => poi.type === "shelter").length;
  const hospitalCount = pois.filter((poi) => poi.type === "hospital").length;
  const alertsLive = connectionState === "connected";
  const generatedAt = intelligence?.generated_at ?? null;
  const showRiskBanner =
    city.riskLevel === "Red" || city.riskLevel === "Orange";

  const handleRoute = (record: RouteRecord) => {
    setRoutes((current) => [record, ...current].slice(0, 10));
  };

  const retryAll = () => {
    retryAlerts();
    retryRegionData();
    command.refresh();
  };

  return (
    <div className="space-y-3 sm:space-y-4">
      <div className="flex justify-end flex-wrap items-center gap-1.5">
        <span
          className={`border px-2 py-1 text-[11px] font-bold uppercase tracking-wide ${RISK_BADGE[city.riskLevel]}`}
        >
          Risk: {city.riskLevel}
        </span>
        <span
          className={`border px-2 py-1 text-[11px] font-bold uppercase tracking-wide ${
            alertsLive
              ? "border-emerald-300 bg-emerald-700 text-white"
              : "border-amber-300 bg-amber-600 text-white"
          }`}
          title={
            alertsLive
              ? "Live alert stream connected."
              : "Alert stream is not live; alert data may be stale."
          }
        >
          Alerts: {connectionState}
        </span>
        <button
          type="button"
          onClick={retryAll}
          className="inline-flex items-center gap-1.5 border border-dark px-2.5 py-1.5 text-xs font-semibold text-dark hover:bg-white/10"
        >
          <RotateCcw size={13} /> Retry all
        </button>
      </div>
  
        {showRiskBanner && (
          <p
            role="alert"
            className="mt-2.5 border border-red-300 bg-red-800  text-white px-3 py-2 text-xs font-semibold leading-5"
          >
            {city.riskLevel}-level risk for {city.name}:{" "}
            {city.officialWarning.title}
            {city.officialWarning.details
              ? ` — ${city.officialWarning.details}`
              : ""}
          </p>
        )}

      {alertsError ? (
        <ErrorState
          message={`Alert feed error: ${alertsError}`}
          onRetry={retryAlerts}
        />
      ) : null}
      {regionDataError ? (
        <ErrorState
          message={regionDataError}
          onRetry={retryRegionData}
          retryLabel="Reload region data"
        />
      ) : null}
      <SituationOverview
        alerts={alerts}
        alertsLive={alertsLive && !alertsLoading}
        tasks={command.tasks}
        shelterCount={shelterCount}
        hospitalCount={hospitalCount}
        facilitiesProvenance={facilitiesProvenance}
        facilitiesTitle={facilitiesTitle}
      />

      <div className="grid grid-cols-1 gap-3 sm:gap-4 xl:grid-cols-5">
        <div className="min-w-0 xl:col-span-3">
          <OperationsMap
            bounds={bounds}
            pois={pois}
            cityLabel={city.name}
            riskZones={riskZones}
            alerts={alerts}
            isLoading={regionLoading}
            emptyMessage={
              sourceErrors ??
              "The provider returned no facility coordinates for this region."
            }
          />
        </div>
        <div className="min-w-0 xl:col-span-2">
          <TacticalAssistant
            regionKey={regionKey}
            regionName={city.name}
            onRoute={handleRoute}
            logSessionEvent={command.logSessionEvent}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:gap-4 xl:grid-cols-5">
        <div className="min-w-0 xl:col-span-3">
          <DispatchPanel
            tasks={command.tasks}
            tasksLoading={command.tasksLoading}
            tasksError={command.tasksError}
            officers={command.officers}
            officersError={command.officersError}
            currentUser={command.currentUser}
            planner={command.planner}
            regionKey={regionKey}
            pois={pois}
            upsertTask={command.upsertTask}
            logSessionEvent={command.logSessionEvent}
            onRefresh={command.refresh}
          />
        </div>
        <div className="min-w-0 xl:col-span-2">
          <RouteIntelligence
            routes={routes}
            intelligence={intelligence}
            intelligenceError={intelligenceError}
            onRetry={retryRegionData}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:gap-4 xl:grid-cols-5">
        <div className="min-w-0 xl:col-span-3">
          <ShelterReliefPanel
            shelters={shelters}
            hospitals={hospitals}
            facilitiesProvenance={facilitiesProvenance}
            facilitiesTitle={facilitiesTitle}
            sourceErrors={sourceErrors}
            tasks={command.tasks}
            tasksError={command.tasksError}
            onRetry={() => {
              retryRegionData();
              command.refresh();
            }}
          />
        </div>
        <div className="min-w-0 xl:col-span-2">
          <ActivityLog
            tasks={command.tasks}
            tasksError={command.tasksError}
            notifications={command.notifications}
            notificationsError={command.notificationsError}
            alerts={alerts}
            sessionEvents={command.sessionEvents}
            onRefresh={command.refresh}
          />
        </div>
      </div>

      <footer className="flex flex-wrap items-center gap-2 border border-slate-200 bg-white px-3 py-2.5 text-[11px] text-slate-500">
        <span className="font-semibold text-slate-600">Data honesty key:</span>
        <DataBadge
          provenance="live"
          title="Streaming feed, currently connected."
        />
        <DataBadge
          provenance="verified"
          title="Backend-confirmed record or snapshot."
        />
        <DataBadge
          provenance="estimated"
          title="Model-derived or AI-assisted value. Treat as provisional."
        />
        <DataBadge
          provenance="stale"
          title=" Older than its freshness window or the live stream dropped."
        />
        <DataBadge
          provenance="unavailable"
          title="No connected feed provides this. Never estimated."
        />
        <button
          type="button"
          onClick={retryAll}
          className={`${outlineButtonClass} ml-auto !py-1.5`}
        >
          <RotateCcw size={12} /> Refresh all data
        </button>
      </footer>
    </div>
  );
}
