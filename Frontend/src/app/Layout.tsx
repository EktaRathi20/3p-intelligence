import { useEffect, useState } from 'react';
import { BellRing, CloudRain, LoaderCircle, MapPin, RotateCcw, X } from 'lucide-react';
import { Outlet, useLocation, useNavigate, useOutletContext } from 'react-router-dom';
import { ClimateAlert } from '../services/climateAlerts';
import type { AuthUser } from '../types';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { EvacuationModal } from '@/components/dashboard/modals/EvacuationModal';
import { SimulatorBanner } from '@/simulator/SimulatorBanner';
import { SimulatorSetupModal } from '@/simulator/SimulatorSetupModal';
import { useSimulator } from '@/simulator/SimulatorContext';
import type { DashboardOutletData } from '../types/dashboard';

interface LayoutProps {
  currentUser: AuthUser;
  onLogout: () => void;
}

const routeModes = {
  '/overview': 'overview',
  '/baseline': 'baseline',
  '/threat': 'threat',
  '/tasks': 'tasks',
  '/fieldOps': 'fieldOps',
  '/landfall': 'landfall',
  '/recovery': 'recovery',
} as const;

export default function Layout({ currentUser, onLogout }: LayoutProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const dashboard = useOutletContext<DashboardOutletData>();
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const simulator = useSimulator();
  const [isSimulatorSetupOpen, setIsSimulatorSetupOpen] = useState(false);
  const currentMode = routeModes[location.pathname as keyof typeof routeModes] ?? 'threat';
  const isHistoricalView = location.pathname === '/history';
  const isNotificationView = location.pathname === '/alerts';
  const isRegionView = location.pathname === '/region-management';
  const isOverviewMode = location.pathname === '/overview';

  useEffect(() => {
    if (!isMobileSidebarOpen) return;

    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsMobileSidebarOpen(false);
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', closeOnEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [isMobileSidebarOpen]);

  if (!dashboard.selectedCity || !dashboard.selectedRegion) {
    return (
      <div className="min-h-screen grid place-items-center bg-slate-100 p-6 text-sm text-slate-700">
        {dashboard.regionLoading ? (
          <div role="status" className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-sm">
            <LoaderCircle size={18} className="animate-spin text-cyan-800" />
            <span>Loading the configured default region</span>
          </div>
        ) : (
          <div role="alert" className="w-full max-w-lg rounded-lg border border-amber-300 bg-white p-5 shadow-sm">
            <h1 className="font-semibold text-slate-900">Unable to load the default region</h1>
            <p className="mt-2 text-slate-600">
              {dashboard.regionError ?? 'No dashboard region is available. Configure a default region in Region Management and retry.'}
            </p>
            <button
              type="button"
              onClick={dashboard.retryRegions}
              className="mt-4 inline-flex items-center gap-1.5 font-semibold text-cyan-900 underline underline-offset-2"
            >
              <RotateCcw size={14} /> Retry
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col font-sans selection:bg-blue-600 selection:text-white bg-slate-100 text-slate-800" style={{overflow: 'hidden'}}>
      <Header
        onOpenMobileNavigation={() => setIsMobileSidebarOpen(true)}
        isMobileNavigationOpen={isMobileSidebarOpen}
        selectedCity={dashboard.selectedCity}
        availableCities={dashboard.availableCities}
        isDefaultRegion={dashboard.defaultRegionKey !== null && dashboard.selectedRegionKey === dashboard.defaultRegionKey}
        onSelectCity={(city) => {
          dashboard.setSelectedRegionKey(city.id);
        }}
        onOpenNotifications={() => {
          navigate('/alerts');
          dashboard.markAllRead();
        }}
        onOpenHistoricalDisasters={() => {
          navigate('/history');
        }}
        unreadAlertsCount={dashboard.unreadCount}
        currentUser={currentUser}
        onLogout={onLogout}
         onOpenRegionPage={() => navigate("/region-management")}
        onOpenSimulator={() => setIsSimulatorSetupOpen(true)}
        onExitSimulator={() => {
          simulator.exit();
          navigate('/overview');
        }}
        simulatorActive={simulator.active}
      />

      <SimulatorBanner />

      <div className="flex min-h-0 min-w-0 flex-1 flex-row" style={{maxHeight: '80vh'}}>
        <Sidebar
          isMobileOpen={isMobileSidebarOpen}
          onCloseMobile={() => setIsMobileSidebarOpen(false)}
          currentMode={currentMode}
          onSelectMode={(mode) => {
            setIsMobileSidebarOpen(false);
            navigate(`/${mode}`);
          }}
          isHistoricalView={isHistoricalView}
          onSelectHistoricalView={(isHistory) => {
            setIsMobileSidebarOpen(false);
            if (isHistory) {
              navigate('/history');
            }
          }}
          isNotificationView={isNotificationView}
          onSelectNotificationView={(isNotification) => {
            setIsMobileSidebarOpen(false);
            if (isNotification) {
              navigate('/alerts');
              dashboard.markAllRead();
            }
          }}
          onOpenAlerts={() => {
            setIsMobileSidebarOpen(false);
            navigate('/alerts');
            dashboard.markAllRead();
          }}
          alertsCount={dashboard.unreadCount}
          roleId={currentUser.roleId}
          roleName={currentUser.roleName}
          roleLevel={currentUser.roleLevel}
        />

        <main className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto p-3 sm:p-4 lg:p-6 max-w-[1600px] w-full mx-auto" style={{ maxHeight: '80vh' }}>
          {(dashboard.regionError || dashboard.regionDataError) && (
            <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <span>
                Data is temporarily unavailable. Retry after sometime.
              </span>
              <button
                type="button"
                onClick={() => {
                  if (dashboard.regionError) dashboard.retryRegions();
                  dashboard.retryRegionData();
                }}
                className="inline-flex shrink-0 items-center gap-1.5 font-semibold underline underline-offset-2"
              >
                <RotateCcw size={13} /> Retry
              </button>
            </div>
          )}
          {dashboard.regionLoading && (
            <div role="status" aria-live="polite" className="mb-4 flex items-center gap-2 rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2.5 text-xs font-medium text-cyan-950">
              <LoaderCircle size={15} className="animate-spin" /> Loading live region data and disaster intelligence
            </div>
          )}
          {isOverviewMode && (
            <section className="bg-white border border-slate-200/90  p-4 mb-4 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <div className="w-10 h-10  border bg-blue-50 border-blue-200 text-blue-600 flex items-center justify-center shrink-0">
                  <MapPin size={22} />
                </div>
                <div className="min-w-0">
                  <h1 className="break-words text-base sm:text-lg font-bold tracking-tight text-slate-900">
                    {dashboard.selectedCity.name}, {dashboard.selectedCity.region}, {dashboard.selectedCity.country}
                  </h1>
                  <div className="mt-0.5 break-words text-[10px] sm:text-xs font-mono text-slate-500">
                    {dashboard.selectedCity.coordinatesFormatted} <span className="text-slate-300">|</span> Population (est.): <span className="font-semibold text-slate-800">{dashboard.selectedCity.populationFormatted}</span>
                  </div>
                </div>
              </div>
              <div className="flex w-full min-w-0 flex-col gap-2 text-xs md:w-auto md:flex-row md:gap-3 shrink-0 self-start md:self-center">
                <div className="flex min-w-0 items-center gap-2.5 px-3 py-1.5  border bg-slate-50 border-slate-200">
                  <CloudRain size={20} className="text-blue-600 shrink-0" />
                  <div>
                    <div className="text-[10px] text-slate-500 font-medium">Current Conditions</div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="font-bold text-sm font-mono text-slate-900">
                        {dashboard.regionResponses?.currentConditions?.temperature_c == null ? 'Unavailable' : `${dashboard.regionResponses.currentConditions.temperature_c}Â°C`}
                      </span>
                      <span className="max-w-48 truncate text-[11px] font-medium text-slate-600">
                        {dashboard.regionResponses?.currentConditions?.condition ?? dashboard.regionResponses?.currentConditionsError ?? 'Waiting for current weather data'}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex min-w-0 items-center gap-2.5 px-3 py-1.5  border bg-slate-50 border-slate-200">
                  <CloudRain size={20} className="text-cyan-600 shrink-0" />
                  <div>
                    <div className="text-[10px] text-slate-500 font-medium">Next 7 Days (avg.)</div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="font-bold text-sm font-mono text-slate-900">{dashboard.selectedCity.tempRangeAvg}</span>
                      <span className="text-[11px] font-medium text-slate-600">{dashboard.selectedCity.forecastSummary}</span>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          )}
          <Outlet context={dashboard} />
        </main>
      </div>

      <SimulatorSetupModal
        isOpen={isSimulatorSetupOpen}
        onClose={() => setIsSimulatorSetupOpen(false)}
      />
      <EvacuationModal
        isOpen={dashboard.isEvacuationModalOpen}
        onClose={() => dashboard.setIsEvacuationModalOpen(false)}
        isLightMode
        regionName={dashboard.selectedCity.name}
      />
      {dashboard.toastAlert && <AlertToast alert={dashboard.toastAlert} onClose={() => dashboard.setToastAlert(null)} />}
    </div>
  );
}

function AlertToast({ alert, onClose }: { alert: ClimateAlert; onClose: () => void }) {
  const tone = alert.simulation_tier === 'RED' || alert.severity === 'critical'
    ? 'border-rose-300 bg-rose-50 text-rose-950'
    : alert.simulation_tier === 'ORANGE' || alert.severity === 'high'
      ? 'border-orange-300 bg-orange-50 text-orange-950'
      : alert.simulation_tier === 'YELLOW' || alert.severity === 'moderate'
        ? 'border-amber-300 bg-amber-50 text-amber-950'
        : 'border-emerald-300 bg-emerald-50 text-emerald-950';
  const zoneLabel = alert.simulation_tier ? `${alert.simulation_tier} ZONE` : alert.severity.toUpperCase();

  return (
    <aside role="alert" aria-live="assertive" className={`fixed right-4 top-4 z-[80] w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-lg border shadow-xl ${tone}`}>
      <div className="flex items-start gap-3 p-4">
        <BellRing size={17} className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <strong className="text-[10px] font-black uppercase tracking-wide">{zoneLabel}</strong>
            {alert.is_simulation && <span className="rounded border border-current/30 px-1.5 py-0.5 text-[9px] font-bold">TEST</span>}
          </div>
          <p className="mt-1 text-sm font-bold leading-snug">{alert.title}</p>
          <p className="mt-1 line-clamp-3 text-xs leading-relaxed opacity-85">{alert.description}</p>
          <p className="mt-2 text-[10px] font-semibold opacity-75">{alert.location.name} Â· closes automatically</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Dismiss alert toast" className="rounded p-1 opacity-70 hover:bg-black/5 hover:opacity-100"><X size={16} /></button>
      </div>
    </aside>
  );
}
