import { useState } from 'react';
import { BedDouble, Droplets, HeartPulse, Home, Truck, UtensilsCrossed } from 'lucide-react';
import type { FacilityResponse } from '@/types/api';
import type { BackendTask } from '@/services/operationalApi';
import {
  DataBadge,
  EmptyState,
  ErrorState,
  formatAge,
  SectionCard,
  type DataProvenance,
} from './rescueShared';

const SUPPLY_ROWS: { label: string; icon: typeof BedDouble; reason: string }[] = [
  { label: 'Shelter capacity', icon: BedDouble, reason: 'No shelter-management feed reports bed capacity.' },
  { label: 'Current occupancy', icon: Home, reason: 'No occupancy reporting feed is connected.' },
  { label: 'Food stock', icon: UtensilsCrossed, reason: 'No relief-inventory feed is connected.' },
  { label: 'Drinking water', icon: Droplets, reason: 'No water-stock feed is connected.' },
  { label: 'Medical supplies', icon: HeartPulse, reason: 'No medical-inventory feed is connected.' },
];

const RELIEF_DEPARTMENTS = ['municipal corp', 'pwd water supply', 'health', 'ems', 'revenue'];

export function ShelterReliefPanel({
  shelters,
  hospitals,
  facilitiesProvenance,
  facilitiesTitle,
  sourceErrors,
  tasks,
  tasksError,
  onRetry,
}: {
  shelters: FacilityResponse[];
  hospitals: FacilityResponse[];
  facilitiesProvenance: DataProvenance;
  facilitiesTitle: string;
  sourceErrors: string | null;
  tasks: BackendTask[];
  tasksError: string | null;
  onRetry: () => void;
}) {
  const [tab, setTab] = useState<'shelters' | 'hospitals'>('shelters');
  const reliefMovements = tasks.filter(
    (task) =>
      task.status !== 'Submitted' &&
      RELIEF_DEPARTMENTS.some((dept) => task.department.toLowerCase().includes(dept)),
  );

  const rows = tab === 'shelters' ? shelters : hospitals;

  return (
    <SectionCard
      title="Shelter & Relief Coordination"
      subtitle="Listed facilities from the backend places feed. Stock and capacity feeds are not connected."
      badge={<DataBadge provenance={facilitiesProvenance} title={facilitiesTitle} />}
    >
      <div className="space-y-3 p-3 sm:p-4">
        {sourceErrors ? (
          <ErrorState message={`Facility feed reported errors: ${sourceErrors}`} onRetry={onRetry} />
        ) : null}

        <div>
          <p className="mb-1.5 text-xs font-bold text-[#18365b]">Capacity & supplies</p>
          <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 xl:grid-cols-5">
            {SUPPLY_ROWS.map((row) => {
              const Icon = row.icon;
              return (
                <li key={row.label} className="border border-slate-200 bg-white px-2.5 py-2" title={row.reason}>
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-700">
                    <Icon size={13} className="text-slate-400" /> {row.label}
                  </div>
                  <p className="mt-1 text-sm font-bold text-slate-400">—</p>
                  <div className="mt-1">
                    <DataBadge provenance="unavailable" title={row.reason} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>

        <div>
          <div className="mb-2 flex flex-wrap items-center gap-1.5" role="group" aria-label="Facility list">
            {(['shelters', 'hospitals'] as const).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setTab(item)}
                aria-pressed={tab === item}
                className={`border px-2.5 py-1.5 text-xs font-semibold capitalize ${
                  tab === item
                    ? 'border-[#18365b] bg-[#18365b] text-white'
                    : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {item} ({item === 'shelters' ? shelters.length : hospitals.length})
              </button>
            ))}
          </div>
          {rows.length === 0 ? (
            <EmptyState
              title={`No ${tab} listed`}
              detail="The backend returned no facilities of this type for the selected region."
            />
          ) : (
            <ul className="max-h-64 divide-y divide-slate-200 overflow-y-auto border border-slate-200">
              {rows.map((facility, index) => (
                <li key={`${facility.name}-${index}`} className="bg-white px-3 py-2">
                  <p className="text-xs font-bold text-slate-900">{facility.name}</p>
                  <p className="mt-0.5 text-[11px] leading-4 text-slate-500">
                    {facility.address ?? 'Address not provided'}
                    {facility.lat != null && facility.lon != null
                      ? ` · ${facility.lat.toFixed(4)}, ${facility.lon.toFixed(4)}`
                      : ' · coordinates unavailable'}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="mb-1.5 flex items-center gap-2 text-xs font-bold text-[#18365b]">
            <Truck size={14} /> Active relief movements ({reliefMovements.length})
          </div>
          {tasksError ? (
            <ErrorState message={`Relief movements failed to load: ${tasksError}`} onRetry={onRetry} />
          ) : reliefMovements.length === 0 ? (
            <EmptyState
              title="No active relief movements"
              detail="No backend-confirmed dispatches from supply-related departments are currently underway."
            />
          ) : (
            <ul className="max-h-56 divide-y divide-slate-200 overflow-y-auto border border-slate-200">
              {reliefMovements.map((task) => (
                <li key={task.id} className="flex flex-wrap items-center justify-between gap-2 bg-white px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-slate-900">{task.title}</p>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {task.department} · {task.assigneeName || 'Unassigned'} · updated {formatAge(task.updatedAt)}
                    </p>
                  </div>
                  <span className={`px-2 py-1 text-[10px] font-semibold ${task.status === 'In Progress' ? 'bg-blue-50 text-blue-800' : 'bg-slate-100 text-slate-700'}`}>
                    {task.status} · {task.progress}%
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-1.5 text-[11px] text-slate-500">
            Incoming third-party relief consignments are <strong>unavailable</strong> — no logistics
            feed is connected. Only backend-confirmed dispatches are listed above.
          </p>
        </div>
      </div>
    </SectionCard>
  );
}
