import { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import { useGeoSelection } from "../../hooks/useGeoSelection";
import {
  regionApi,
  RegionApiError,
  type Hazard,
  type Region,
  type RegionPayload,
} from "../../services/regionApi";
import {
  buildDefaultRegionCode,
  isValidRegionCode,
} from "../../utils/regionGeo";
import SearchableSelect from "./SearchableSelect";

interface RegionFormProps {
  initial: Region | null;
  hazards: Hazard[];
  onSaved: (message: string) => void;
  onCancel: () => void;
  onError: (message: string) => void;
}

const inputClass =
  "mt-1 w-full border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-[#18365b] focus:ring-1 focus:ring-[#18365b]";

export default function RegionForm({
  initial,
  hazards,
  onSaved,
  onCancel,
  onError,
}: RegionFormProps) {
  const isEdit = initial !== null;

  const geo = useGeoSelection({
    countryCode: initial?.countryCode,
    stateCode: initial?.stateCode,
    stateName: initial?.stateName,
    cityId: initial?.cityId,
    cityName: initial?.cityName,
  });

  // Saved values count as user-confirmed, so auto-defaults never overwrite
  // them when the saved city resolves.
  const [name, setName] = useState(initial?.name ?? "");
  const [nameTouched, setNameTouched] = useState(isEdit);
  const [code, setCode] = useState(initial?.code ?? "");
  const [codeTouched, setCodeTouched] = useState(isEdit);
  const [hazardIds, setHazardIds] = useState<string[]>(
    initial?.hazardIds ?? [],
  );
  const [hazardSearch, setHazardSearch] = useState("");
  const [active, setActive] = useState(initial?.active ?? true);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  // Selecting a city updates the default region name and code (while the
  // user has not edited them manually).
  useEffect(() => {
    if (!geo.city) {
      if (!nameTouched) setName("");
      if (!codeTouched) setCode("");
      return;
    }
    if (!nameTouched) setName(geo.city.name);
    if (!codeTouched) {
      setCode(
        buildDefaultRegionCode(
          geo.countryCode,
          geo.hasSubdivisions ? geo.stateCode : null,
          geo.city.name,
        ),
      );
    }
  }, [
    geo.city,
    geo.countryCode,
    geo.stateCode,
    geo.hasSubdivisions,
    nameTouched,
    codeTouched,
  ]);

  const geoLoading =
    geo.countriesStatus.loading ||
    geo.statesStatus.loading ||
    geo.citiesStatus.loading;

  const filteredHazards = hazards.filter((hazard) => {
    const needle = hazardSearch.trim().toLowerCase();
    if (!needle) return true;
    return (
      hazard.name.toLowerCase().includes(needle) ||
      (hazard.code ?? "").toLowerCase().includes(needle)
    );
  });

  const toggleHazard = (hazardId: string) => {
    setHazardIds((current) =>
      current.includes(hazardId)
        ? current.filter((id) => id !== hazardId)
        : [...current, hazardId],
    );
    setFieldErrors((current) => {
      const next = { ...current };
      delete next.hazards;
      return next;
    });
  };

  const validate = (): Record<string, string> => {
    const errors: Record<string, string> = {};
    if (!geo.countryCode) errors.country = "Country is required.";
    if (
      geo.countryCode &&
      !geo.statesStatus.loading &&
      !geo.statesStatus.error &&
      geo.hasSubdivisions &&
      !geo.stateCode
    ) {
      errors.state = "State/province is required for this country.";
    }
    if (!name.trim()) errors.name = "Region name is required.";
    if (code.trim() && !isValidRegionCode(code)) {
      errors.code =
        "Code must be 2-24 characters: letters, digits, hyphens or underscores.";
    }
    if (hazardIds.length === 0) {
      errors.hazards = "Please select at least one hazard.";
    }
    return errors;
  };

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving) return;

    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    const payload: RegionPayload = {
      name: name.trim(),
      type: initial?.type || "city",
      code: code.trim() || null,
      active,
      hazardIds,
      countryCode: geo.countryCode,
      stateCode:
        geo.hasSubdivisions && geo.stateCode ? geo.stateCode : null,
      cityId: geo.cityId || null,
    };

    setSaving(true);
    try {
      if (initial) {
        await regionApi.updateRegion(initial.id, payload);
        onSaved("Region updated successfully.");
      } else {
        await regionApi.createRegion(payload);
        onSaved("Region created successfully.");
      }
    } catch (error) {
      if (
        error instanceof RegionApiError &&
        error.status === 409 &&
        error.message.toLowerCase().includes("code")
      ) {
        setFieldErrors({ code: error.message });
        return;
      }
      onError(error instanceof Error ? error.message : "Failed to save region.");
    } finally {
      setSaving(false);
    }
  };

  const geoNotSynced = geo.geoStatus !== null && !geo.geoStatus.synced;

  return (
    <form
      onSubmit={save}
      className="space-y-4 border-b border-slate-300 bg-slate-50 p-4"
    >
      <h3 className="font-bold">{isEdit ? "Edit Region" : "Create Region"}</h3>

      {geoNotSynced && (
        <div
          role="alert"
          className="flex items-start gap-2 border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
        >
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <span>
            Geographic data is not synchronized yet.{" "}
            {geo.geoStatus?.error ??
              "Ask an administrator to run the geo sync."}
          </span>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <SearchableSelect
            id="region-country"
            label="Country"
            required
            value={geo.country}
            options={geo.countries}
            getKey={(item) => item.code}
            getLabel={(item) => item.name}
            getSublabel={(item) =>
              item.region ? `${item.code} · ${item.region}` : item.code
            }
            onChange={geo.selectCountry}
            placeholder="Choose a country"
            loading={geo.countriesStatus.loading}
            error={geo.countriesStatus.error}
            onRetry={() => void geo.reloadCountries()}
            emptyMessage="No countries found. Check the countries API."
          />
          {fieldErrors.country && (
            <p className="mt-1 text-xs text-red-700">{fieldErrors.country}</p>
          )}
        </div>

        <div>
          <SearchableSelect
            id="region-state"
            label="State / Province"
            required={geo.hasSubdivisions}
            value={geo.state}
            options={geo.states}
            getKey={(item) => item.code}
            getLabel={(item) => item.name}
            getSublabel={(item) =>
              item.type ? `${item.code} · ${item.type}` : item.code
            }
            onChange={geo.selectState}
            placeholder={
              !geo.countryCode
                ? "Select a country first"
                : "Choose a state or province"
            }
            disabled={
              !geo.countryCode ||
              (!geo.hasSubdivisions && !geo.statesStatus.loading)
            }
            loading={geo.statesStatus.loading}
            error={geo.statesStatus.error}
            onRetry={geo.retryStates}
            emptyMessage="No states or provinces found for this country."
            hint={
              geo.countryCode &&
              !geo.statesStatus.loading &&
              !geo.hasSubdivisions
                ? "This country has no state/province level; cities load directly."
                : undefined
            }
          />
          {fieldErrors.state && (
            <p className="mt-1 text-xs text-red-700">{fieldErrors.state}</p>
          )}
        </div>

        <div className="sm:col-span-2">
          <SearchableSelect
            id="region-city"
            label="City"
            value={geo.city}
            options={geo.cities}
            getKey={(item) => item.id}
            getLabel={(item) => item.name}
            getSublabel={(item) =>
              [item.stateName, item.countryCode]
                .filter(Boolean)
                .join(" · ") || null
            }
            onChange={geo.selectCity}
            placeholder={
              !geo.countryCode
                ? "Select a country first"
                : geo.hasSubdivisions && !geo.stateCode
                  ? "Select a state first"
                  : "Choose a city (optional)"
            }
            disabled={
              !geo.countryCode ||
              geo.statesStatus.loading ||
              (geo.hasSubdivisions && !geo.stateCode)
            }
            loading={geo.citiesStatus.loading && geo.cityPage === 1}
            error={geo.citiesStatus.error}
            onRetry={geo.retryCities}
            emptyMessage="No cities found for this selection."
            hint="Optional. Start typing to search cities by name."
            allowClear
            searchText={geo.citySearch}
            onSearchTextChange={geo.setCitySearch}
            searching={geo.citiesStatus.loading}
            totalCount={geo.cityTotal}
            hasMore={geo.cityPage < geo.cityTotalPages}
            onLoadMore={() => geo.setCityPage(geo.cityPage + 1)}
            loadingMore={
              geo.citiesStatus.loading && geo.cityPage > 1
            }
          />
        </div>

        <label className="block text-sm font-medium text-slate-700">
          Region Name <span className="text-red-600">*</span>
          <input
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setNameTouched(true);
            }}
            placeholder="e.g. Jodhpur"
            className={inputClass}
          />
          {!nameTouched && geo.city && (
            <span className="mt-1 block text-xs text-slate-500">
              Defaults to the selected city; you can edit it.
            </span>
          )}
          {fieldErrors.name && (
            <span className="mt-1 block text-xs text-red-700">
              {fieldErrors.name}
            </span>
          )}
        </label>

        <label className="block text-sm font-medium text-slate-700">
          Region Code
          <input
            value={code}
            onChange={(event) => {
              setCode(event.target.value.toUpperCase());
              setCodeTouched(true);
            }}
            placeholder="e.g. IN-RJ-JDH"
            className={inputClass}
          />
          <span className="mt-1 block text-xs text-slate-500">
            Optional. 2-24 chars (letters, digits, - or _), unique.
          </span>
          {fieldErrors.code && (
            <span className="mt-1 block text-xs text-red-700">
              {fieldErrors.code}
            </span>
          )}
        </label>

        <fieldset className="block text-sm font-medium text-slate-700">
          <legend className="text-sm font-medium text-slate-700">
            Status
          </legend>
          <div className="mt-1 flex gap-2">
            {(
              [
                { label: "Active", value: true },
                { label: "Inactive", value: false },
              ] as const
            ).map((option) => (
              <label
                key={option.label}
                className={`flex flex-1 cursor-pointer items-center justify-center gap-2 border px-3 py-2.5 text-sm font-semibold ${
                  active === option.value
                    ? "border-[#18365b] bg-[#eaf0f7] text-[#18365b]"
                    : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                <input
                  type="radio"
                  name="region-active"
                  checked={active === option.value}
                  onChange={() => setActive(option.value)}
                  className="h-4 w-4 accent-[#18365b]"
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>

      </div>

      <div className="border border-slate-300 bg-white p-3">
        <h4 className="text-sm font-semibold">
          Attach Hazards <span className="text-red-600">*</span>
        </h4>
        <input
          value={hazardSearch}
          onChange={(event) => setHazardSearch(event.target.value)}
          placeholder="Search hazards..."
          aria-label="Search hazards"
          className="mt-2 w-full border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#18365b] focus:ring-1 focus:ring-[#18365b]"
        />
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {filteredHazards.map((hazard) => (
            <label
              key={hazard.id}
              className="flex cursor-pointer items-center gap-2 border border-slate-200 p-3 hover:bg-slate-50"
            >
              <input
                type="checkbox"
                checked={hazardIds.includes(hazard.id)}
                onChange={() => toggleHazard(hazard.id)}
                className="h-4 w-4 accent-[#18365b]"
              />
              <span className="text-sm">{hazard.name}</span>
            </label>
          ))}
        </div>
        {hazards.length === 0 && (
          <p className="mt-2 text-sm text-amber-700">
            No hazards found. Check the hazard API.
          </p>
        )}
        {hazards.length > 0 && filteredHazards.length === 0 && (
          <p className="mt-2 text-sm text-slate-500">
            No hazards match this search.
          </p>
        )}
        {fieldErrors.hazards && (
          <p className="mt-2 text-xs text-red-700">{fieldErrors.hazards}</p>
        )}
        <p className="mt-2 text-xs text-slate-500">
          {hazardIds.length} hazard(s) selected
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-slate-500">
          {geo.geoStatus?.attribution ??
            "Geographic data by Countries States Cities Database (ODbL v1.0)."}
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || geoLoading || hazards.length === 0}
            className="inline-flex items-center gap-2 bg-[#18365b] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {saving && <Loader2 size={16} className="animate-spin" />}
            {isEdit ? "Update Region" : "Save Region"}
          </button>
        </div>
      </div>
    </form>
  );
}
