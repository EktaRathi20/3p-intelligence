/**
 * Simulator Mode scenario catalog (SIMULATION ONLY).
 *
 * Cyclone-only drills in three severity zones: RED (emergency), ORANGE
 * (preparedness) and GREEN (calm monitoring). Each composes with the
 * Cyclone Bay training zone through the snapshot builder.
 */

export type SimTier = 'RED' | 'ORANGE' | 'GREEN';

export interface SimScenario {
  id: string;
  name: string;
  /** Short zone label shown in the picker, e.g. "Red Zone". */
  zoneLabel: string;
  hazardId: string;
  hazardName: string;
  tier: SimTier;
  severity: 'critical' | 'high' | 'moderate' | 'low';
  level: string;
  score: number;
  phase: string;
  blurb: string;
}

export const SIM_SCENARIOS: SimScenario[] = [
  {
    id: 'cyclone-red',
    name: 'Cyclone RED Drill (SIMULATED)',
    zoneLabel: 'Red Zone',
    hazardId: 'cyclone',
    hazardName: 'Cyclone',
    tier: 'RED',
    severity: 'critical',
    level: 'RED',
    score: 91,
    phase: 'Alert & verification',
    blurb: 'Full emergency: fictional cyclone closing in, alerts fresh, verification under way, tasks being assigned.',
  },
  {
    id: 'cyclone-orange',
    name: 'Cyclone ORANGE Drill (SIMULATED)',
    zoneLabel: 'Orange Zone',
    hazardId: 'cyclone',
    hazardName: 'Cyclone',
    tier: 'ORANGE',
    severity: 'high',
    level: 'ORANGE',
    score: 68,
    phase: 'Preparedness',
    blurb: 'Prepare-to-respond: fictional cyclone organising offshore, shelters opening, field teams staging.',
  },
  {
    id: 'cyclone-green',
    name: 'Cyclone GREEN Drill (SIMULATED)',
    zoneLabel: 'Green Zone',
    hazardId: 'cyclone',
    hazardName: 'Cyclone',
    tier: 'GREEN',
    severity: 'low',
    level: 'GREEN',
    score: 12,
    phase: 'Calm monitoring',
    blurb: 'All calm: routine fictional monitoring with seas quiet. The happy-path drill.',
  },
];

export function getSimScenario(scenarioId: string): SimScenario | null {
  return SIM_SCENARIOS.find((scenario) => scenario.id === scenarioId) ?? null;
}
