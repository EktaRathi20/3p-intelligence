/**
 * Simulator Mode entry dialog: pick a cyclone drill zone (Red, Orange or
 * Green) and switch the whole application into Simulator Mode.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FlaskConical, Play, Wind, X } from 'lucide-react';
import { SIM_SCENARIOS } from './simScenarios';
import { SIM_ZONES } from './simZones';
import { useSimulator } from './SimulatorContext';

interface SimulatorSetupModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const TIER_BAR: Record<string, string> = {
  RED: 'bg-[#b42318]',
  ORANGE: 'bg-orange-600',
  GREEN: 'bg-emerald-600',
};

export function SimulatorSetupModal({ isOpen, onClose }: SimulatorSetupModalProps) {
  const { enter } = useSimulator();
  const navigate = useNavigate();
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const zone = SIM_ZONES[0];

  useEffect(() => {
    if (isOpen) {
      setScenarioId(null);
      setError(null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleEnter = () => {
    if (!scenarioId || !zone) return;
    try {
      enter(zone.id, scenarioId);
      onClose();
      navigate('/overview');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start Simulator Mode.');
    }
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="simulator-setup-title"
    >
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto border border-slate-300 bg-white shadow-2xl">
        <div className="border-b-4 border-[#e5a044] bg-[#18365b] px-4 py-3 text-white">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1 border border-[#e5a044] bg-[#e5a044] px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-[#18365b]">
                  <FlaskConical size={11} /> Simulator
                </span>
                <h2 id="simulator-setup-title" className="text-base font-bold tracking-tight">
                  Cyclone drill — pick a zone
                </h2>
              </div>
              <p className="mt-1 text-[11px] leading-5 text-blue-100">
                Training area: {zone?.name ?? 'Cyclone Bay'}. Pick a severity zone and every module
                will switch to fictional drill data until you exit. Live records are never touched.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close simulator setup"
              className="flex h-8 w-8 shrink-0 items-center justify-center border border-white/30 hover:bg-white/10"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="p-4">
          <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-[#18365b]">
            <Wind size={14} /> Cyclone severity zone
          </p>
          <div className="mt-2 grid grid-cols-1 gap-2" role="radiogroup" aria-label="Cyclone drill zone">
            {SIM_SCENARIOS.map((scenario) => {
              const selected = scenarioId === scenario.id;
              return (
                <button
                  key={scenario.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setScenarioId(scenario.id)}
                  className={`border bg-white text-left ${
                    selected
                      ? 'border-[#18365b] ring-2 ring-[#18365b]'
                      : 'border-slate-300 hover:border-slate-400 hover:bg-slate-50'
                  }`}
                >
                  <div className={`h-1.5 ${TIER_BAR[scenario.tier]}`} aria-hidden="true" />
                  <div className="p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-black uppercase tracking-wide text-slate-900">
                        {scenario.zoneLabel}
                      </span>
                      <span className="text-[11px] text-slate-500">· {scenario.phase}</span>
                      {selected && (
                        <span className="ml-auto text-[10px] font-black uppercase tracking-wide text-[#18365b]">
                          Selected ✓
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs leading-5 text-slate-600">{scenario.blurb}</p>
                  </div>
                </button>
              );
            })}
          </div>

          {error && (
            <p role="alert" className="mt-2 border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800">
              {error}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2 border-t border-slate-200 bg-slate-50 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex items-start gap-1.5 text-[10px] leading-4 text-slate-500">
            <FlaskConical size={13} className="mt-0.5 shrink-0" />
            <span>
              Drill data is fictional and isolated in memory. Exiting restores the live application.
              Reloading the page also exits Simulator Mode.
            </span>
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!scenarioId}
              onClick={handleEnter}
              className="inline-flex items-center gap-1.5 border border-[#18365b] bg-[#18365b] px-4 py-2 text-xs font-bold text-white hover:bg-[#234d77] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Play size={14} /> Enter Simulator Mode
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
