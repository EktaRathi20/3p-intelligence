import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Edit2,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";

import { regionApi } from "../services/regionApi";
import type {
  Hazard,
  Region,
  RegionConfiguration,
} from "../services/regionApi";
import { formatGeoBreadcrumb } from "../utils/regionGeo";
import ConfirmDialog from "../components/regions/ConfirmDialog";
import RegionForm from "../components/regions/RegionForm";
import { useSimulator } from "../simulator/SimulatorContext";

interface RegionPageProps {
  currentUserRole?: string;
  initialDefaultRegionId?: string;
}

const isRoleOne = (role?: string) =>
  ["role_1", "1", "level_1"].includes(
    (role || "").toLowerCase().trim()
  );

const inputClass =
  "mt-1 w-full border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-[#18365b] focus:ring-1 focus:ring-[#18365b]";

export default function RegionPage({
  currentUserRole,
  initialDefaultRegionId,
}: RegionPageProps) {
  const canManage = isRoleOne(currentUserRole);

  const [regions, setRegions] = useState<Region[]>([]);
  const [hazards, setHazards] = useState<Hazard[]>([]);
  const [defaultRegionId, setDefaultRegionId] = useState<string | null>(
    initialDefaultRegionId ?? null
  );

  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Region | null>(null);
  const [listSearch, setListSearch] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const { active: simulatorActive, exit: exitSimulator, zone: simulatorZone } = useSimulator();

  const activeRegions = regions.filter((region) => region.active !== false);
  const selectedDefault = regions.find(
    (region) => region.id === defaultRegionId
  );
  const editingRegion =
    regions.find((region) => region.id === editingId) ?? null;

  const hazardName = useCallback(
    (hazardId: string) =>
      hazards.find((hazard) => hazard.id === hazardId)?.name || hazardId,
    [hazards]
  );

  const filteredRegions = regions.filter((region) => {
    const needle = listSearch.trim().toLowerCase();
    if (!needle) return true;
    const haystack = [
      region.name,
      region.code ?? "",
      formatGeoBreadcrumb(region),
      (region.hazardIds ?? []).map(hazardName).join(" "),
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(needle);
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [regionResult, hazardResult, config] = await Promise.all([
        regionApi.getRegions(),
        regionApi.getHazards(),
        regionApi.getConfiguration(),
      ]);

      setRegions(regionResult.items);
      setHazards(hazardResult.items);

      setDefaultRegionId(
        config.defaultRegionId ?? initialDefaultRegionId ?? null
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load regions."
      );
    } finally {
      setLoading(false);
    }
  }, [initialDefaultRegionId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const resetForm = () => {
    setEditingId(null);
    setShowForm(false);
  };

  const openCreateForm = () => {
    setError("");
    setMessage("");
    setEditingId(null);
    setShowForm(true);
  };

  const openEditForm = (region: Region) => {
    setError("");
    setMessage("");
    setEditingId(region.id);
    setShowForm(true);
  };

  const handleSaved = async (savedMessage: string) => {
    resetForm();
    setMessage(savedMessage);
    await loadData();
    window.dispatchEvent(new CustomEvent("region-hazards-changed"));
  };

  const deleteRegion = async (region: Region) => {
    if (!canManage) return;

    setSaving(true);
    setError("");
    setMessage("");

    try {
      await regionApi.deleteRegion(region.id);

      if (editingId === region.id) resetForm();

      setMessage("Region deleted successfully.");
      await loadData();
      window.dispatchEvent(new CustomEvent("region-hazards-changed"));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete region."
      );
    } finally {
      setPendingDelete(null);
      setSaving(false);
    }
  };

  const saveDefault = async () => {
    if (!defaultRegionId) {
      setError("Please select a default region.");
      return;
    }

    setSaving(true);
    setError("");
    setMessage("");

    try {
      const config: RegionConfiguration = await regionApi.getConfiguration();

      await regionApi.saveConfiguration({
        ...config,
        defaultRegionId,
      });

      window.dispatchEvent(new CustomEvent("region-default-changed"));
      setMessage("Default region saved successfully.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save default region."
      );
    } finally {
      setSaving(false);
    }
  };

  if (simulatorActive) {
    return (
      <div className="min-h-full bg-[#f3f5f7] p-4 text-slate-800 sm:p-6">
        <div className="mx-auto max-w-2xl border border-amber-300 bg-amber-50 p-6 text-center">
          <p className="text-[10px] font-black uppercase tracking-widest text-amber-800">
            Simulation Mode
          </p>
          <h1 className="mt-1 text-lg font-bold text-slate-900">Region Management is paused during drills</h1>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600">
            The drill is running in {simulatorZone?.name ?? 'the simulated zone'} with fictional
            geography. Region configuration stays on live data and is disabled until you exit
            Simulator Mode, so live records can never change mid-drill.
          </p>
          <button
            type="button"
            onClick={exitSimulator}
            className="mt-4 border border-[#18365b] bg-[#18365b] px-4 py-2 text-xs font-bold text-white hover:bg-[#234d77]"
          >
            Exit Simulator to manage regions
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-64 items-center justify-center gap-3 bg-slate-50 text-sm text-slate-600">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading regions...
      </div>
    );
  }

  return (
    <div className="min-h-full bg-[#f3f5f7] p-4 text-slate-800 sm:p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        {/* Messages */}

        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 border border-red-300 bg-red-50 p-3 text-sm text-red-800"
          >
            <AlertCircle size={17} className="mt-0.5 shrink-0" />
            <span className="flex-1">{error}</span>
            <button type="button" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}

        {message && (
          <div
            role="status"
            className="flex items-center gap-2 border border-green-300 bg-green-50 p-3 text-sm text-green-800"
          >
            <CheckCircle2 size={17} />
            <span>{message}</span>
          </div>
        )}

        {/* Default region: all roles */}

        <section className="border border-slate-300 bg-white">
          <div className="border-b border-slate-300 bg-slate-100 p-4">
            <h2 className="font-bold">Default Dashboard Region</h2>
            <p className="mt-1 text-xs text-slate-600">
              Available to all roles.
            </p>
          </div>

          <div className="space-y-4 p-4">
            <label className="block text-sm font-semibold">
              Select region
              <select
                value={defaultRegionId ?? ""}
                onChange={(event) =>
                  setDefaultRegionId(event.target.value || null)
                }
                className={inputClass}
              >
                <option value="">Choose a region</option>
                {activeRegions.map((region) => (
                  <option key={region.id} value={region.id}>
                    {region.name}
                    {region.code ? ` (${region.code})` : ""}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex flex-wrap items-center justify-between gap-3 border border-slate-200 bg-slate-50 p-3">
              <div>
                <p className="text-xs text-slate-500">Current default</p>
                <p className="mt-1 font-semibold text-[#18365b]">
                  {selectedDefault?.name || "No default selected"}
                </p>
              </div>

              <button
                type="button"
                disabled={saving || !defaultRegionId}
                onClick={() => void saveDefault()}
                className="inline-flex items-center gap-2 bg-[#18365b] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#102846] disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Save size={16} />
                )}
                Set Default
              </button>
            </div>
          </div>
        </section>

        {/* Region management: Role 1 only */}

        {canManage && (
          <section className="border border-slate-300 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-300 bg-slate-100 p-4">
              <div>
                <h2 className="font-bold">Regions</h2>
                <p className="mt-1 text-xs text-slate-600">
                  Create, edit or delete a region and its applicable hazards.
                </p>
              </div>

              <button
                type="button"
                onClick={showForm ? resetForm : openCreateForm}
                className="inline-flex items-center gap-2 bg-[#18365b] px-3 py-2.5 text-sm font-semibold text-white hover:bg-[#102846]"
              >
                {showForm ? <X size={16} /> : <Plus size={16} />}
                {showForm ? "Cancel" : "Create Region"}
              </button>
            </div>

            {/* Create/Edit form */}

            {showForm && (
              <RegionForm
                key={editingId ?? "new"}
                initial={editingRegion}
                hazards={hazards}
                onSaved={(savedMessage) => void handleSaved(savedMessage)}
                onCancel={resetForm}
                onError={(messageText) => setError(messageText)}
              />
            )}

            {/* Region search */}

            <div className="border-b border-slate-200 p-4">
              <div className="flex items-center gap-2 border border-slate-300 bg-white px-3">
                <Search size={15} className="shrink-0 text-slate-400" />
                <input
                  value={listSearch}
                  onChange={(event) => setListSearch(event.target.value)}
                  placeholder="Search regions by name, code, geography, or hazard..."
                  aria-label="Search regions"
                  className="w-full py-2.5 text-sm outline-none"
                />
                {listSearch && (
                  <button
                    type="button"
                    aria-label="Clear search"
                    onClick={() => setListSearch("")}
                  >
                    <X size={15} className="text-slate-400" />
                  </button>
                )}
              </div>
            </div>

            {/* Region list */}

            <div className="divide-y divide-slate-200">
              {filteredRegions.map((region) => {
                const breadcrumb = formatGeoBreadcrumb(region);
                return (
                  <div
                    key={region.id}
                    className="flex flex-wrap items-center justify-between gap-3 p-4"
                  >
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 font-semibold text-slate-900">
                        {region.name}
                        <span
                          className={`text-xs font-semibold ${
                            region.active !== false
                              ? "text-green-700"
                              : "text-slate-500"
                          }`}
                        >
                          {region.active !== false ? "Active" : "Inactive"}
                        </span>
                        {region.id === defaultRegionId && (
                          <span className="text-xs font-medium text-green-700">
                            Default
                          </span>
                        )}
                      </p>

                      <p className="mt-1 text-xs text-slate-500">
                        {breadcrumb || "No geography set"}
                        {" · "}Code: {region.code || "—"} · Parent:{" "}
                        {region.parentName ||
                          regions.find(
                            (item) => item.id === region.parentRegionId
                          )?.name ||
                          "—"}
                      </p>

                      <p className="mt-1 text-xs text-slate-500">
                        Hazards:{" "}
                        {region.hazardIds?.length
                          ? region.hazardIds.map(hazardName).join(", ")
                          : "Not assigned"}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => openEditForm(region)}
                        className="inline-flex items-center gap-1 border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-[#18365b] hover:bg-slate-50"
                      >
                        <Edit2 size={14} />
                        Edit
                      </button>

                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => setPendingDelete(region)}
                        className="inline-flex items-center gap-1 border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                      >
                        <Trash2 size={14} />
                        Delete
                      </button>

                      {region.id !== defaultRegionId && (
                        <button
                          type="button"
                          onClick={() => setDefaultRegionId(region.id)}
                          className="border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50"
                        >
                          Select Default
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}

              {regions.length === 0 && (
                <p className="p-8 text-center text-sm text-slate-500">
                  No regions available. Create your first region.
                </p>
              )}

              {regions.length > 0 && filteredRegions.length === 0 && (
                <p className="p-8 text-center text-sm text-slate-500">
                  No regions match this search.
                </p>
              )}
            </div>

            <div className="flex justify-end border-t border-slate-200 bg-slate-50 p-4">
              <button
                type="button"
                disabled={saving || !defaultRegionId}
                onClick={() => void saveDefault()}
                className="inline-flex items-center gap-2 bg-[#18365b] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
              >
                <Save size={16} />
                Save Default Region
              </button>
            </div>
          </section>
        )}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => void loadData()}
            className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-[#18365b]"
          >
            <RefreshCw size={14} />
            Refresh data
          </button>
        </div>

        {pendingDelete && (
          <ConfirmDialog
            title="Delete Region"
            message={`Delete region "${pendingDelete.name}"? This action cannot be undone.`}
            confirmLabel="Delete Region"
            busy={saving}
            onConfirm={() => void deleteRegion(pendingDelete)}
            onCancel={() => {
              if (!saving) setPendingDelete(null);
            }}
          />
        )}
      </div>
    </div>
  );
}
