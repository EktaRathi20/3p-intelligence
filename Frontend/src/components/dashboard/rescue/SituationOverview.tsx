import {
  AlertTriangle,
  Ambulance,
  HeartPulse,
  Home,
  LifeBuoy,
  Siren,
  Users,
  UserCheck,
} from 'lucide-react';
import type { ClimateAlert } from '@/types/alerts';
import type { BackendTask } from '@/services/operationalApi';
import { DataBadge, type DataProvenance } from './rescueShared';

interface Kpi {
  label: string;
  value: string;
  hint: string;
  provenance: DataProvenance;
  provenanceTitle: string;
  icon: typeof Siren;
  critical?: boolean;
}

function KpiCard({ kpi }: { kpi: Kpi }) {
  const Icon = kpi.icon;
  return (
    <div
      className={`border bg-white px-3.5 py-3 shadow-sm ${
        kpi.critical ? 'border-red-300' : 'border-slate-300'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {kpi.label}
        </p>
        <Icon size={16} className={kpi.critical ? 'text-red-700' : 'text-[#18365b]'} />
      </div>
      <p className={`mt-1 text-2xl font-bold tracking-tight ${kpi.critical ? 'text-red-800' : 'text-[#18365b]'}`}>
        {kpi.value}
      </p>
      <p className="mt-0.5 min-h-4 text-[11px] leading-4 text-slate-500">{kpi.hint}</p>
      <div className="mt-1.5">
        <DataBadge provenance={kpi.provenance} title={kpi.provenanceTitle} />
      </div>
    </div>
  );
}

export function SituationOverview({
  alerts,
  alertsLive,
  tasks,
  shelterCount,
  hospitalCount,
  facilitiesProvenance,
  facilitiesTitle,
}: {
  alerts: ClimateAlert[];
  alertsLive: boolean;
  tasks: BackendTask[];
  shelterCount: number;
  hospitalCount: number;
  facilitiesProvenance: DataProvenance;
  facilitiesTitle: string;
}) {
  const operationalAlerts = alerts.filter((alert) => !alert.is_simulation);
  const criticalAlerts = operationalAlerts.filter(
    (alert) => alert.severity === 'critical' || alert.severity === 'high',
  );
  const activeDispatches = tasks.filter((task) => task.status !== 'Submitted');
  const deployedTeams = new Set(
    activeDispatches.map((task) => task.assigneeUserId).filter(Boolean),
  ).size;
  const emsActive = activeDispatches.filter(
    (task) => task.department.toLowerCase().includes('health') || task.department.toLowerCase().includes('ems'),
  ).length;
  const assisted = tasks.reduce(
    (sum, task) =>
      sum +
      (task.reports ?? []).reduce(
        (inner, report) => inner + (report.peopleAssisted ?? 0),
        0,
      ),
    0,
  );

  const alertsProvenance: DataProvenance =
    alerts.length === 0 ? 'unavailable' : alertsLive ? 'live' : 'stale';

  const kpis: Kpi[] = [
    {
      label: 'Active emergencies',
      value: String(operationalAlerts.length),
      hint: `${criticalAlerts.length} critical / high severity`,
      provenance: alertsProvenance,
      provenanceTitle: alertsLive
        ? 'Live alert stream is connected.'
        : 'Alert stream is not live; counts may be outdated.',
      icon: Siren,
      critical: criticalAlerts.length > 0,
    },
    {
      label: 'People requiring rescue',
      value: '—',
      hint: 'No casualty feed connected',
      provenance: 'unavailable',
      provenanceTitle: 'No backend feed reports people awaiting rescue. Do not estimate from other figures.',
      icon: LifeBuoy,
    },
    {
      label: 'People assisted (field)',
      value: assisted.toLocaleString('en-IN'),
      hint: 'Sum of field report counts',
      provenance: 'verified',
      provenanceTitle: 'Sum of peopleAssisted across backend-confirmed field reports. Partial: only reported tasks.',
      icon: UserCheck,
    },
    {
      label: 'Active dispatches',
      value: String(activeDispatches.length),
      hint: 'Backend tasks not yet submitted',
      provenance: 'verified',
      provenanceTitle: 'Counted from backend task records for this region.',
      icon: AlertTriangle,
    },
    {
      label: 'Teams deployed',
      value: String(deployedTeams),
      hint: 'Assignees on active dispatches',
      provenance: 'verified',
      provenanceTitle: 'Distinct assignees across active backend tasks. Availability beyond assignment is unknown.',
      icon: Users,
    },
    {
      label: 'Ambulances available',
      value: '—',
      hint: `${emsActive} active Health & EMS dispatches`,
      provenance: 'unavailable',
      provenanceTitle: 'No ambulance fleet feed exists. Health & EMS dispatch count is shown for context only.',
      icon: Ambulance,
    },
    {
      label: 'Shelters listed',
      value: String(shelterCount),
      hint: 'Facilities with coordinates',
      provenance: facilitiesProvenance,
      provenanceTitle: facilitiesTitle,
      icon: Home,
    },
    {
      label: 'Hospitals listed',
      value: String(hospitalCount),
      hint: 'Facilities with coordinates',
      provenance: facilitiesProvenance,
      provenanceTitle: facilitiesTitle,
      icon: HeartPulse,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 sm:gap-3 xl:grid-cols-4">
      {kpis.map((kpi) => (
        <KpiCard key={kpi.label} kpi={kpi} />
      ))}
    </div>
  );
}
