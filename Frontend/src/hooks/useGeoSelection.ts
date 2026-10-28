import { useCallback, useEffect, useRef, useState } from "react";

import { isAbortError } from "../services/apiError";
import {
  regionApi,
  type CityOption,
  type Country,
  type GeoStatus,
  type StateOption,
} from "../services/regionApi";

export interface GeoInitialSelection {
  countryCode?: string | null;
  stateCode?: string | null;
  stateName?: string | null;
  cityId?: string | null;
  cityName?: string | null;
}

interface LevelStatus {
  loading: boolean;
  error: string;
}

const idleStatus: LevelStatus = { loading: false, error: "" };

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message;
  return fallback;
}

export function useGeoSelection(initial?: GeoInitialSelection) {
  const [countries, setCountries] = useState<Country[]>([]);
  const [countriesStatus, setCountriesStatus] =
    useState<LevelStatus>(idleStatus);

  const [countryCode, setCountryCode] = useState(
    initial?.countryCode ?? "",
  );
  const [states, setStates] = useState<StateOption[]>([]);
  const [hasSubdivisions, setHasSubdivisions] = useState(true);
  const [statesStatus, setStatesStatus] = useState<LevelStatus>(idleStatus);
  const [stateCode, setStateCode] = useState(initial?.stateCode ?? "");
  // Display details for a saved state/city before their option lists load.
  const [stateOverride, setStateOverride] = useState<StateOption | null>(
    initial?.stateCode
      ? {
          code: initial.stateCode,
          name: initial.stateName || initial.stateCode,
          countryCode: initial.countryCode ?? "",
        }
      : null,
  );

  const [cities, setCities] = useState<CityOption[]>([]);
  const [cityId, setCityId] = useState(initial?.cityId ?? "");
  const [cityOverride, setCityOverride] = useState<CityOption | null>(
    initial?.cityId
      ? {
          id: initial.cityId,
          name: initial.cityName || initial.cityId,
          stateCode: initial.stateCode ?? null,
          stateName: initial.stateName ?? null,
          countryCode: initial.countryCode ?? "",
        }
      : null,
  );
  const [citySearch, setCitySearch] = useState("");
  const [debouncedCitySearch, setDebouncedCitySearch] = useState("");
  const [cityPage, setCityPage] = useState(1);
  const [cityTotal, setCityTotal] = useState(0);
  const [cityTotalPages, setCityTotalPages] = useState(0);
  const [citiesStatus, setCitiesStatus] = useState<LevelStatus>(idleStatus);

  const [geoStatus, setGeoStatus] = useState<GeoStatus | null>(null);

  const requestSeq = useRef(0);

  // Debounce server-side city search.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedCitySearch(citySearch);
      setCityPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [citySearch]);

  const loadCountries = useCallback(async (signal?: AbortSignal) => {
    setCountriesStatus({ loading: true, error: "" });
    try {
      const result = await regionApi.getCountries(signal);
      setCountries(result.items);
      setCountriesStatus(idleStatus);
    } catch (error) {
      if (isAbortError(error)) return;
      setCountriesStatus({
        loading: false,
        error: errorMessage(error, "Failed to load countries."),
      });
    }
  }, []);

  const loadGeoStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      setGeoStatus(await regionApi.getGeoStatus(signal));
    } catch (error) {
      if (isAbortError(error)) return;
      setGeoStatus({
        synced: false,
        countries: null,
        states: 0,
        cities: 0,
        error: errorMessage(error, "Failed to load geo status."),
      });
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadCountries(controller.signal);
    void loadGeoStatus(controller.signal);
    return () => controller.abort();
  }, [loadCountries, loadGeoStatus]);

  // Load states whenever the country changes.
  useEffect(() => {
    if (!countryCode) {
      setStates([]);
      setHasSubdivisions(true);
      setStatesStatus(idleStatus);
      return;
    }
    const controller = new AbortController();
    const seq = ++requestSeq.current;
    setStatesStatus({ loading: true, error: "" });
    regionApi
      .getStates(countryCode, controller.signal)
      .then((result) => {
        if (requestSeq.current !== seq || controller.signal.aborted) return;
        setStates(result.items);
        setHasSubdivisions(result.hasSubdivisions);
        setStatesStatus(idleStatus);
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        if (requestSeq.current !== seq) return;
        setStates([]);
        setStatesStatus({
          loading: false,
          error: errorMessage(error, "Failed to load states."),
        });
      });
    return () => controller.abort();
  }, [countryCode]);

  const statesReady = !statesStatus.loading && countryCode !== "";

  // Load cities (paginated, server-side search).
  useEffect(() => {
    if (!countryCode) {
      setCities([]);
      setCityTotal(0);
      setCityTotalPages(0);
      setCitiesStatus(idleStatus);
      return;
    }
    if (hasSubdivisions && !stateCode) {
      setCities([]);
      setCityTotal(0);
      setCityTotalPages(0);
      setCitiesStatus(idleStatus);
      return;
    }
    const controller = new AbortController();
    const seq = ++requestSeq.current;
    setCitiesStatus({ loading: cityPage === 1, error: "" });
    regionApi
      .getCities(
        {
          countryCode,
          stateCode: hasSubdivisions ? stateCode : null,
          search: debouncedCitySearch,
          page: cityPage,
          limit: 20,
        },
        controller.signal,
      )
      .then((result) => {
        if (requestSeq.current !== seq || controller.signal.aborted) return;
        setCities((current) =>
          cityPage === 1 ? result.items : [...current, ...result.items],
        );
        setCityTotal(result.total);
        setCityTotalPages(result.totalPages);
        setCitiesStatus(idleStatus);
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        if (requestSeq.current !== seq) return;
        if (cityPage === 1) setCities([]);
        setCitiesStatus({
          loading: false,
          error: errorMessage(error, "Failed to load cities."),
        });
      });
    return () => controller.abort();
  }, [
    countryCode,
    stateCode,
    hasSubdivisions,
    debouncedCitySearch,
    cityPage,
    statesReady,
  ]);

  const selectCountry = useCallback(
    (country: Country | null) => {
      const code = country?.code ?? "";
      if (code === countryCode) return;
      setCountryCode(code);
      setStates([]);
      setStateCode("");
      setStateOverride(null);
      setCities([]);
      setCityId("");
      setCityOverride(null);
      setCitySearch("");
      setCityPage(1);
      setCitiesStatus(idleStatus);
    },
    [countryCode],
  );

  const selectState = useCallback(
    (state: StateOption | null) => {
      const code = state?.code ?? "";
      if (code === stateCode) return;
      setStateCode(code);
      setStateOverride(null);
      setCities([]);
      setCityId("");
      setCityOverride(null);
      setCitySearch("");
      setCityPage(1);
      setCitiesStatus(idleStatus);
    },
    [stateCode],
  );

  const selectCity = useCallback((city: CityOption | null) => {
    setCityId(city?.id ?? "");
    setCityOverride(null);
  }, []);

  const retryStates = useCallback(() => {
    if (!countryCode) return;
    setStatesStatus({ loading: true, error: "" });
    const seq = ++requestSeq.current;
    regionApi
      .getStates(countryCode)
      .then((result) => {
        if (requestSeq.current !== seq) return;
        setStates(result.items);
        setHasSubdivisions(result.hasSubdivisions);
        setStatesStatus(idleStatus);
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        if (requestSeq.current !== seq) return;
        setStatesStatus({
          loading: false,
          error: errorMessage(error, "Failed to load states."),
        });
      });
  }, [countryCode]);

  const retryCities = useCallback(() => {
    setCitiesStatus({ loading: true, error: "" });
    setCityPage(1);
    const code = countryCode;
    const state = stateCode;
    const search = debouncedCitySearch;
    const seq = ++requestSeq.current;
    regionApi
      .getCities({
        countryCode: code,
        stateCode: hasSubdivisions ? state : null,
        search,
        page: 1,
        limit: 20,
      })
      .then((result) => {
        if (requestSeq.current !== seq) return;
        setCities(result.items);
        setCityTotal(result.total);
        setCityTotalPages(result.totalPages);
        setCitiesStatus(idleStatus);
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        if (requestSeq.current !== seq) return;
        setCitiesStatus({
          loading: false,
          error: errorMessage(error, "Failed to load cities."),
        });
      });
  }, [countryCode, stateCode, hasSubdivisions, debouncedCitySearch]);

  const country = countries.find((item) => item.code === countryCode) ?? null;
  const state =
    states.find((item) => item.code === stateCode) ?? stateOverride;
  const city = cities.find((item) => item.id === cityId) ?? cityOverride;

  return {
    countries,
    countriesStatus,
    reloadCountries: loadCountries,
    countryCode,
    country,
    selectCountry,
    states,
    statesStatus,
    hasSubdivisions,
    stateCode,
    state: stateCode ? state : null,
    selectState,
    retryStates,
    cities,
    citiesStatus,
    citySearch,
    setCitySearch,
    cityTotal,
    cityTotalPages,
    cityPage,
    setCityPage,
    cityId,
    city: cityId ? city : null,
    selectCity,
    retryCities,
    geoStatus,
  };
}
