/**
 * Persistent SIMULATION MODE indicator with zone/scenario context and Exit.
 * Rendered on every page while a drill is active.
 */
import { useNavigate } from 'react-router-dom';
import { FlaskConical, LogOut, MapPin } from 'lucide-react';
import { useSimulator } from './SimulatorContext';

export function SimulatorBanner() {
  const { active, zone, scenario, exit } = useSimulator();
  const navigate = useNavigate();
  if (!active || !zone || !scenario) return null;

  const handleExit = () => {
    exit();
    navigate('/overview');
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className="border-b-4 border-[#e5a044] bg-[#7c2d12] text-white"
    >
      <div className="mx-auto flex max-w-[1600px] flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center sm:justify-between sm:px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center border border-white/40 bg-white/10">
            <FlaskConical size={17} />
          </span>
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs font-black uppercase tracking-widest">
              <span className="bg-[#e5a044] px-1.5 py-0.5 text-[#7c2d12]">Simulation Mode</span>
              <span className="font-bold normal-case tracking-normal">
                {zone.name} · {scenario.name}
              </span>
            </p>
            <p className="mt-0.5 flex items-center gap-1 text-[11px] text-orange-100">
              <MapPin size={11} className="shrink-0" />
              <span className="truncate">
                Every module now shows fictional drill data. Nothing here is real, and no live records change.
              </span>
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleExit}
          title="Exit Simulator Mode and return to live data"
          className="inline-flex shrink-0 items-center gap-1.5 border border-white bg-white px-4 py-2 text-xs font-bold text-[#7c2d12] hover:bg-orange-50"
        >
          <LogOut size={14} /> Exit Simulator
        </button>
      </div>
    </div>
  );
}
