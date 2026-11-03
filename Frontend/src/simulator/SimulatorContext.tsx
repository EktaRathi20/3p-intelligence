/**
 * Simulator Mode React bindings.
 *
 * Thin wrapper over the framework-agnostic simulator store so components
 * re-render on mode switches. Service modules use the store directly.
 */
import { createContext, useContext, useMemo, useSyncExternalStore, type ReactNode } from 'react';
import {
  enterSimulator,
  exitSimulator,
  getSimulatorState,
  subscribeSimulator,
  type SimulatorSelection,
} from './simulatorStore';

interface SimulatorContextValue extends SimulatorSelection {
  enter: (zoneId: string, scenarioId: string) => void;
  exit: () => void;
  /** Changes on every mode switch; used to remount data-driven subtrees. */
  modeKey: string;
}

const SimulatorContext = createContext<SimulatorContextValue | null>(null);

export function SimulatorProvider({ children }: { children: ReactNode }) {
  const selection = useSyncExternalStore(
    subscribeSimulator,
    () => getSimulatorState(),
  );

  const value = useMemo<SimulatorContextValue>(
    () => ({
      active: selection.active,
      zone: selection.zone,
      scenario: selection.scenario,
      enter: (zoneId: string, scenarioId: string) => {
        enterSimulator(zoneId, scenarioId);
      },
      exit: () => exitSimulator(),
      modeKey: selection.active
        ? `sim-${selection.zone?.id ?? 'none'}-${selection.scenario?.id ?? 'none'}`
        : 'live',
    }),
    [selection],
  );

  return <SimulatorContext.Provider value={value}>{children}</SimulatorContext.Provider>;
}

export function useSimulator(): SimulatorContextValue {
  const context = useContext(SimulatorContext);
  if (!context) throw new Error('useSimulator must be used inside SimulatorProvider.');
  return context;
}
