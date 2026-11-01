import React from 'react';
import { Home, Info, Plus } from 'lucide-react';
import type { InfrastructureResponse } from '@/types/api';

interface BottomRowCardsProps {
  infrastructure: InfrastructureResponse | null;
  isLightMode?: boolean;
}

export const BottomRowCards: React.FC<BottomRowCardsProps> = ({
  infrastructure,
  isLightMode = true,
}) => {
  const cardClass = isLightMode ? 'bg-white border-slate-300' : 'bg-slate-900 border-slate-800';
  const textClass = isLightMode ? 'text-[#18365b]' : 'text-slate-100';
  const mutedClass = isLightMode ? 'text-slate-500' : 'text-slate-400';
  const facilities = infrastructure ? [...infrastructure.shelters, ...infrastructure.hospitals] : [];

  return (
    <div className="mt-4 grid grid-cols-1 gap-4">

      {/* Card 1: Nearby Facilities */}
      <section className={`flex flex-col border p-4 shadow-sm ${cardClass}`}>
        <div className="mb-3 flex items-center gap-2">
          <Home size={16} className="text-emerald-600" />
          <h3 className={`text-sm font-bold ${textClass}`}>Nearby Facilities</h3>
        </div>

        <div className="flex-1">
          {!infrastructure ? (
            <p className={`text-sm ${mutedClass}`}>Facility data is unavailable.</p>
          ) : facilities.length === 0 ? (
            <div className="space-y-1">
              <p className={`text-sm ${mutedClass}`}>No facilities returned for this region.</p>
            </div>
          ) : (
            <div className="custom-scrollbar max-h-[180px] space-y-2 overflow-y-auto pr-2">
              {infrastructure.shelters.slice(0, 3).map((facility, index) => (
                <div key={`shelter-${index}`} className={`border p-2.5 transition-colors ${isLightMode ? 'bg-slate-50 hover:bg-slate-100 border-slate-200' : 'bg-slate-950 hover:bg-slate-900 border-slate-800'}`}>
                  <div className={`flex items-start gap-2.5 text-sm font-semibold ${isLightMode ? 'text-slate-900' : textClass}`}>
                    <Home size={15} className="mt-0.5 shrink-0 text-emerald-600" />
                    <div className="min-w-0">
                      <div>{facility.name}</div>
                      <div className={`mt-1 text-xs font-normal leading-relaxed ${mutedClass}`}>
                        {facility.address || 'Address not provided'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              {infrastructure.hospitals.slice(0, 3).map((facility, index) => (
                <div key={`hospital-${index}`} className={`border p-2.5 transition-colors ${isLightMode ? 'bg-slate-50 hover:bg-slate-100 border-slate-200' : 'bg-slate-950 hover:bg-slate-900 border-slate-800'}`}>
                  <div className={`flex items-start gap-2.5 text-sm font-semibold ${isLightMode ? 'text-slate-900' : textClass}`}>
                    <Plus size={15} className="mt-0.5 shrink-0 text-rose-600" strokeWidth={3} />
                    <div className="min-w-0">
                      <div>{facility.name}</div>
                      <div className={`mt-1 text-xs font-normal leading-relaxed ${mutedClass}`}>
                        {facility.address || 'Address not provided'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {infrastructure && facilities.length > 0 && (
          <div className={`mt-3 border-t pt-2.5 text-xs font-medium ${isLightMode ? 'border-slate-100' : 'border-slate-800'} ${mutedClass}`}>
            Showing {Math.min(infrastructure.shelters.length, 3)} of {infrastructure.shelters.length} shelters · {Math.min(infrastructure.hospitals.length, 3)} of {infrastructure.hospitals.length} hospitals
          </div>
        )}
      </section>

      {/* Card 2: Evacuation Routes */}
      <section className={`flex flex-col border p-4 shadow-sm ${cardClass}`}>
        <div className="mb-3 flex items-center gap-2">
          <Info size={16} className="text-amber-600" />
          <h3 className={`text-sm font-bold ${textClass}`}>Evacuation Routes</h3>
        </div>

        <div className={`flex flex-1 items-center justify-center border border-dashed p-8 text-center ${isLightMode ? 'bg-slate-50/50 border-slate-200' : 'bg-slate-950/50 border-slate-700'}`}>
          <p className={`max-w-[220px] text-sm leading-relaxed ${mutedClass}`}>
            Route data is not currently exposed by the backend API. No route status or safety recommendation is shown.
          </p>
        </div>
      </section>

    </div>
  );
};
