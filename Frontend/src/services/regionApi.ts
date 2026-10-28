// Region Management API client.
//
// Uses VITE_API_BASE_URL (same convention as httpClient, defaulting to the
// Vite '/api' proxy) instead of a hardcoded localhost URL. Backend `detail`
// messages are preserved so validation errors (400/409) and sync errors
// (503) reach the UI verbatim.

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "/api"
).replace(/\/$/, "");

export interface Country {
  id?: string;
  code: string;
  name: string;
  officialName?: string;
  flag?: string;
  region?: string;
  subregion?: string;
  iso3?: string;
  capital?: string;
}

export interface StateOption {
  code: string;
  name: string;
  countryCode: string;
  type?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface CityOption {
  id: string;
  name: string;
  stateCode?: string | null;
  stateName?: string | null;
  countryCode: string;
  latitude?: number | null;
  longitude?: number | null;
}

export interface Region {
  id: string;
  name: string;
  type?: string;
  parentRegionId?: string | null;
  parentName?: string;
  code?: string | null;
  active: boolean;
  hazardIds?: string[];
  countryCode?: string | null;
  countryName?: string | null;
  stateCode?: string | null;
  stateName?: string | null;
  cityId?: string | null;
  cityName?: string | null;
  createdAt?: unknown;
  updatedAt?: unknown;
}

export interface Hazard {
  id: string;
  name: string;
  code?: string;
  description?: string;
  active?: boolean;
}

export interface RegionConfiguration {
  defaultRegionId: string | null;
}

export interface RegionPayload {
  name: string;
  type?: string;
  parentRegionId?: string | null;
  code?: string | null;
  active?: boolean;
  hazardIds?: string[];
  countryCode?: string | null;
  stateCode?: string | null;
  cityId?: string | null;
}

export interface CitiesResult {
  items: CityOption[];
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}

export interface GeoStatus {
  synced: boolean;
  countries: number | null;
  states: number;
  cities: number;
  dataset?: string;
  datasetUrl?: string;
  license?: string;
  attribution?: string;
  error?: string | null;
}

export class RegionApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "RegionApiError";
  }
}

function authHeaders(): Record<string, string> {
  if (typeof sessionStorage === "undefined") return {};
  const token = sessionStorage.getItem("apada_access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const REGION_API_TIMEOUT_MS = 60000;

async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
  const callerSignal = init.signal;
  const timeoutController = new AbortController();
  const timeoutId = globalThis.setTimeout(() => {
    timeoutController.abort(new DOMException('Request timed out.', 'TimeoutError'));
  }, REGION_API_TIMEOUT_MS);
  const onCallerAbort = () => timeoutController.abort(
    callerSignal instanceof AbortSignal ? callerSignal.reason : undefined,
  );
  if (callerSignal?.aborted) {
    onCallerAbort();
  } else {
    callerSignal?.addEventListener('abort', onCallerAbort, { once: true });
  }
  try {
    return await fetch(url, { ...init, signal: timeoutController.signal });
  } finally {
    globalThis.clearTimeout(timeoutId);
    callerSignal?.removeEventListener('abort', onCallerAbort);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetchWithTimeout(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...options.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && (error.name === "AbortError" || error.name === "TimeoutError")) {
      throw error;
    }
    throw new Error(
      "We couldn't connect to the service. Check your connection and try again.",
    );
  }

  if (!response.ok) {
    const result = await response.json().catch(() => null);
    const detail =
      typeof result?.detail === "string"
        ? result.detail
        : `API error: ${response.status}`;
    throw new RegionApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

function buildQuery(params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

export const regionApi = {
  async getRegions(signal?: AbortSignal) {
    const result = await request<{
      items?: Region[];
      regions?: Region[];
      count?: number;
    }>("/regions?activeOnly=false&limit=500", { signal });

    const items = result.items ?? result.regions ?? [];

    return { items, count: result.count ?? items.length };
  },

  async getRegion(id: string, signal?: AbortSignal) {
    const result = await request<{ region: Region }>(
      `/regions/${encodeURIComponent(id)}`,
      { signal },
    );

    return result.region;
  },

  async createRegion(data: RegionPayload) {
    const result = await request<{ region: Region }>("/regions", {
      method: "POST",
      body: JSON.stringify(data),
    });

    return result.region;
  },

  async updateRegion(id: string, data: RegionPayload) {
    const result = await request<{ region: Region }>(
      `/regions/${encodeURIComponent(id)}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );

    return result.region;
  },

  async deleteRegion(id: string) {
    return request<{ success: boolean; message: string }>(
      `/regions/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    );
  },

  async getHazards(signal?: AbortSignal) {
    const result = await request<{
      items?: Hazard[];
      hazards?: Hazard[];
      count?: number;
    }>("/hazard-types", { signal });

    const items = result.items ?? result.hazards ?? [];

    return { items, count: result.count ?? items.length };
  },

  async getCountries(signal?: AbortSignal) {
    const result = await request<{
      items?: Country[];
      countries?: Country[];
      count?: number;
    }>(`/countries${buildQuery({ limit: 500 })}`, { signal });

    const items = (result.items ?? result.countries ?? []).map((country) => ({
      ...country,
      code: country.code || country.id || "",
    }));

    return { items, count: result.count ?? items.length };
  },

  async getStates(countryCode: string, signal?: AbortSignal) {
    const result = await request<{
      items?: StateOption[];
      states?: StateOption[];
      count?: number;
      hasSubdivisions?: boolean;
    }>(`/states${buildQuery({ countryCode })}`, { signal });

    const items = result.items ?? result.states ?? [];

    return {
      items,
      count: result.count ?? items.length,
      hasSubdivisions: result.hasSubdivisions ?? items.length > 0,
    };
  },

  async getCities(
    args: {
      countryCode: string;
      stateCode?: string | null;
      search?: string;
      page?: number;
      limit?: number;
    },
    signal?: AbortSignal,
  ): Promise<CitiesResult> {
    const result = await request<{
      items?: CityOption[];
      cities?: CityOption[];
      page: number;
      limit: number;
      total: number;
      totalPages: number;
    }>(
      `/cities${buildQuery({
        countryCode: args.countryCode,
        stateCode: args.stateCode ?? undefined,
        search: args.search || undefined,
        page: args.page ?? 1,
        limit: args.limit ?? 20,
      })}`,
      { signal },
    );

    return {
      items: (result.items ?? result.cities ?? []).map((city) => ({
        ...city,
        id: String(city.id),
      })),
      page: result.page,
      limit: result.limit,
      total: result.total,
      totalPages: result.totalPages,
    };
  },

  async getGeoStatus(signal?: AbortSignal): Promise<GeoStatus> {
    return request<GeoStatus>("/geo/status", { signal });
  },

  async getConfiguration(): Promise<RegionConfiguration> {
    const result = await request<{
      configuration?: RegionConfiguration;
      defaultRegionId?: string | null;
    }>("/region-configuration");

    return (
      result.configuration ?? {
        defaultRegionId: result.defaultRegionId ?? null,
      }
    );
  },

  async saveConfiguration(config: RegionConfiguration) {
    // Check whether the region configuration record already exists.
    const current = await request<{
      exists?: boolean;
      configuration?: RegionConfiguration;
      defaultRegionId?: string | null;
    }>("/region-configuration");

    // Existing document: update it. Missing document: create it.
    if (current.exists === true) {
      return request("/region-configuration", {
        method: "PUT",
        body: JSON.stringify(config),
      });
    }

    try {
      return await request("/region-configuration", {
        method: "POST",
        body: JSON.stringify(config),
      });
    } catch (error) {
      // Handle a concurrent create or a backend that doesn't return `exists`.
      if (
        error instanceof Error &&
        error.message.toLowerCase().includes("already exists")
      ) {
        return request("/region-configuration", {
          method: "PUT",
          body: JSON.stringify(config),
        });
      }

      throw error;
    }
  },
};
