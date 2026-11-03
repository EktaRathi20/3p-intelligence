/**
 * Simulator Mode zone catalog (SIMULATION ONLY).
 *
 * A single fictional training geography for the cyclone drills. Every
 * user-facing name carries a SIMULATED marker. This zone does not
 * correspond to a real administrative area.
 */

export interface SimPlace {
  name: string;
  kind: 'town' | 'village' | 'landmark';
}

export interface SimFacility {
  name: string;
  address: string;
  lat: number;
  lon: number;
  capacity: string;
}

export interface SimZone {
  id: string;
  /** Key used as the simulated region key across the app. */
  regionKey: string;
  name: string;
  shortName: string;
  state: string;
  country: string;
  bounds: { min_lat: number; max_lat: number; min_lon: number; max_lon: number };
  center: { lat: number; lon: number };
  population: number;
  places: SimPlace[];
  shelters: SimFacility[];
  hospitals: SimFacility[];
}

export const SIM_ZONES: SimZone[] = [
  {
    id: 'cyclone-bay',
    regionKey: 'sim-cyclone-bay',
    name: 'Cyclone Bay (SIMULATED)',
    shortName: 'Cyclone Bay',
    state: 'Demo Coast Province (SIMULATED)',
    country: 'Simuland (SIMULATED)',
    bounds: { min_lat: 17.3, max_lat: 18.1, min_lon: 82.9, max_lon: 83.7 },
    center: { lat: 17.72, lon: 83.3 },
    population: 1240000,
    places: [
      { name: 'Port Nimbus (SIMULATED)', kind: 'town' },
      { name: 'Old Harbour (SIMULATED)', kind: 'town' },
      { name: 'Mid-Coast Villages (SIMULATED)', kind: 'village' },
      { name: 'Northgate (SIMULATED)', kind: 'landmark' },
    ],
    shelters: [
      { name: 'Harbour Hall Shelter (SIMULATED)', address: 'Fisher Road, Old Harbour', lat: 17.78, lon: 83.36, capacity: '2,500' },
      { name: 'Northgate College Shelter (SIMULATED)', address: 'College Lane, Northgate', lat: 17.95, lon: 83.55, capacity: '1,800' },
    ],
    hospitals: [
      { name: 'Bayview Clinic (SIMULATED)', address: 'Clinic Street, Mid-Coast', lat: 17.68, lon: 83.2, capacity: '120 beds' },
      { name: 'Port Nimbus Care (SIMULATED)', address: 'Harbour View, Port Nimbus', lat: 17.86, lon: 83.46, capacity: '80 beds' },
    ],
  },
];

export function getSimZone(zoneId: string): SimZone | null {
  return SIM_ZONES.find((zone) => zone.id === zoneId) ?? null;
}
