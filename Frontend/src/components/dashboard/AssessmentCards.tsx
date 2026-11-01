import React from 'react';
import { Building2, CloudRain, Database, Users } from 'lucide-react';
import { CityLocation } from '@/types/domain';
import type { InfrastructureResponse } from '@/types/api';

interface AssessmentCardsProps {
  city: CityLocation;
  infrastructure: InfrastructureResponse | null;
  isLightMode?: boolean;
}

export const AssessmentCards: React.FC<AssessmentCardsProps> = ({ city, infrastructure, isLightMode = true }) => {
  const cardClass = isLightMode ? 'bg-white border-slate-300' : 'bg-slate-900/90 border-slate-800';
  const titleClass = isLightMode ? 'text-[#18365b]' : 'text-slate-100';
  const mutedClass = isLightMode ? 'text-slate-500' : 'text-slate-400';
  const localZone = city.localImpact?.zone;
  const localColor = localZone === 'RED'
    ? 'text-rose-600'
    : localZone === 'ORANGE'
      ? 'text-orange-600'
      : localZone === 'YELLOW'
        ? 'text-amber-600'
        : localZone === 'GREEN'
          ? 'text-emerald-600'
          : localZone === 'UNKNOWN'
            ? 'text-slate-500'
            : null;
  const fallbackColor = city.riskLevel === 'Red'
    ? 'text-rose-600'
    : city.riskLevel === 'Orange'
      ? 'text-orange-600'
      : city.riskLevel === 'Moderate'
        ? 'text-amber-600'
        : city.riskLevel === 'Unavailable'
          ? 'text-slate-500'
          : 'text-emerald-600';
  const screeningText = city.riskScore == null
    ? 'Screening score unavailable'
    : `Screening ${city.riskScore}/100`;
  const cards = [
    { title: 'Population', value: city.populationFormatted, detail: 'Population API', icon: Users, color: 'text-blue-600' },
    { title: 'Forecast', value: city.tempRangeAvg, detail: city.forecastSummary, icon: CloudRain, color: 'text-cyan-600' },
    {
      title: 'Nearby facilities',
      value: infrastructure ? `${infrastructure.hospitals.length + infrastructure.shelters.length}` : 'Unavailable',
      detail: infrastructure ? `${infrastructure.hospitals.length} hospitals · ${infrastructure.shelters.length} shelters` : 'Facility API unavailable',
      icon: Building2,
      color: 'text-emerald-600',
    },
    {
      title: 'Local impact',
      value: city.localImpact?.shortLabel ?? city.operationalRisk.level,
      detail: !city.localImpact
        ? city.operationalRisk.level === 'Unavailable'
          ? 'Risk assessment unavailable'
          : screeningText
        : `${city.localImpact.regionalText} · ${screeningText}`,
      icon: Database,
      color: localColor ?? fallbackColor,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map(({ title, value, detail, icon: Icon, color }) => (
        <section key={title} className={`flex min-h-28 flex-col justify-between border p-3.5 shadow-sm ${cardClass}`}>
          <div className={`flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide ${mutedClass}`}>
            <Icon size={15} className={color} /> {title}
          </div>
          <div>
            <div className={`text-xl font-bold tracking-tight ${titleClass}`}>{value}</div>
            <div className={`mt-1 text-[11px] leading-4 ${mutedClass}`}>{detail}</div>
          </div>
        </section>
      ))}
    </div>
  );
};
