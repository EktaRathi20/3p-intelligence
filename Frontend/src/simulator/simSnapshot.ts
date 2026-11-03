/**
 * Simulator Mode snapshot builder (SIMULATION ONLY).
 *
 * Composes the Cyclone Bay training zone with one cyclone severity drill
 * (RED, ORANGE or GREEN) into a single coherent training dataset covering
 * every module: dashboard, threat, alerts, tasks, rescue, field operations,
 * recovery, and history.
 *
 * All user-facing strings are marked SIMULATED. No official warnings are
 * ever fabricated: the simulated intelligence explicitly reports screening
 * output, not authoritative warnings.
 */
import type {
  ApiRegion,
  CurrentConditionsResponse,
  DisasterIntelligenceResponse,
  ForecastResponse,
  HistoricalEventResponse,
  InfrastructureResponse,
  PopulationResponse,
} from '@/types/api';
import type { DisasterIntelligenceCapabilities } from '@/types/api';
import type { ClimateAlert } from '@/types/alerts';
import type { OfficerUser } from '@/types';
import type {
  BackendTask,
  OperationalNotification,
} from '@/services/operationalApi';
import type {
  AssessmentDetail,
  AssessmentFigure,
  AssessmentTotals,
  DamageAssessment,
  EvidenceAttachment,
  ExpenseRecord,
  FeedbackItem,
} from '@/services/recoveryApi';
import type { Hazard, Region, RegionConfiguration } from '@/services/regionApi';
import type { SimZone } from './simZones';
import type { SimScenario } from './simScenarios';

export interface SimSnapshot {
  zoneId: string;
  scenarioId: string;
  regionKey: string;
  builtAt: string;
  apiRegions: Record<string, ApiRegion>;
  regionRecord: Region;
  regionConfig: RegionConfiguration;
  regionItems: Region[];
  hazards: Hazard[];
  population: PopulationResponse;
  forecast: ForecastResponse;
  infrastructure: InfrastructureResponse;
  currentConditions: CurrentConditionsResponse;
  intelligence: DisasterIntelligenceResponse;
  capabilities: DisasterIntelligenceCapabilities;
  alerts: ClimateAlert[];
  historyEvents: HistoricalEventResponse[];
  tasks: BackendTask[];
  notifications: OperationalNotification[];
  officers: OfficerUser[];
  assessments: AssessmentDetail[];
  damages: DamageAssessment[];
  expenses: ExpenseRecord[];
  evidence: EvidenceAttachment[];
  feedback: FeedbackItem[];
}

const SIM_TAG = '[SIMULATED]';

const isoHoursAgo = (base: number, hours: number) =>
  new Date(base - hours * 3600 * 1000).toISOString();

const isoDaysAhead = (base: number, days: number) =>
  new Date(base + days * 86400 * 1000).toISOString().slice(0, 10);

interface SeedTask {
  title: string;
  department: string;
  place: number;
  priority: 'Critical' | 'High' | 'Medium' | 'Low';
  status: 'Assigned' | 'In Progress' | 'Submitted';
  progress: number;
  officer: number;
  hoursAgo: number;
  report?: { text: string; assisted: number; location: string };
}

interface SeedNotification {
  message: string;
  priority: 'Critical' | 'High' | 'Medium' | 'Low';
  task: number | null;
  hoursAgo: number;
  read: boolean;
}

interface ScenarioNarrative {
  tempC: number;
  condition: string;
  windKmh: number;
  windDir: string;
  pressureHpa: number;
  humidity: number;
  surgeM: number;
  forecastConditions: string[];
  intelSummary: string;
  factors: string[];
  reasoning: string[];
  analog: string;
  historyEvents: { name: string; wind: number; surge: number; km: number; year: number }[];
  alerts: { title: string; description: string; severity: ClimateAlert['severity']; tier: 'YELLOW' | 'ORANGE' | 'RED' | 'GREEN'; hoursAgo: number }[];
  recommended: { department: string; place: number; description: string; priority: string; team: string }[];
  tasks: SeedTask[];
  notifications: SeedNotification[];
  recoveryDepth: { assessments: number; damages: number; expenses: number };
  figureScale: { homes: number; damageCr: number; prepCr: number; recoveryCr: number; people: number };
}

const NARRATIVES: Record<string, ScenarioNarrative> = {
  'cyclone-red': {
    tempC: 29,
    condition: 'Overcast with gusty winds',
    windKmh: 112,
    windDir: 'SE',
    pressureHpa: 982,
    humidity: 89,
    surgeM: 1.9,
    forecastConditions: ['Heavy rain', 'Very heavy rain', 'Thunderstorm', 'Heavy rain', 'Moderate rain', 'Partly cloudy', 'Partly cloudy'],
    intelSummary: `${SIM_TAG} Simulated screening: a fictional cyclone is approaching the simulated zone. Verification is under way and early assignments are being drafted. This is training output, not an official warning.`,
    factors: [
      `${SIM_TAG} Mock sustained winds rising past the simulated RED threshold.`,
      `${SIM_TAG} Fictional storm surge building along the simulated shoreline.`,
      `${SIM_TAG} Simulated screening score 91/100 for drill purposes only.`,
    ],
    reasoning: [
      `${SIM_TAG} Fictional sensor grid shows a tightening mock circulation.`,
      `${SIM_TAG} Drill rulebook maps these readings to a simulated RED tier.`,
      `${SIM_TAG} No official warning exists for this fictional event.`,
    ],
    analog: `${SIM_TAG} Fictional analog: Drill Cyclone 2019 (training record)`,
    historyEvents: [
      { name: 'Drill Cyclone Vayu-2019', wind: 165, surge: 2.4, km: 42, year: 2019 },
      { name: 'Drill Cyclone Mora-2021', wind: 140, surge: 1.8, km: 88, year: 2021 },
      { name: 'Drill Cyclone Pika-2016', wind: 120, surge: 1.2, km: 150, year: 2016 },
      { name: 'Drill Cyclone Lila-2023', wind: 155, surge: 2.1, km: 65, year: 2023 },
      { name: 'Drill Cyclone Orca-2014', wind: 110, surge: 1.0, km: 210, year: 2014 },
    ],
    alerts: [
      { title: `${SIM_TAG} RED cyclone alert — fictional landfall expected`, description: `${SIM_TAG} Drill alert: a fictional cyclone is projected to make a simulated landfall. Training notification only — not an official warning and not delivered anywhere.`, severity: 'critical', tier: 'RED', hoursAgo: 2 },
      { title: `${SIM_TAG} ORANGE preparedness advisory — drill shelters opening`, description: `${SIM_TAG} Drill advisory: simulated shelters in the training zone are opening for the exercise.`, severity: 'high', tier: 'ORANGE', hoursAgo: 9 },
      { title: `${SIM_TAG} YELLOW watch — fictional disturbance tracked`, description: `${SIM_TAG} Earliest drill notice for this fictional system, kept for the training timeline.`, severity: 'moderate', tier: 'YELLOW', hoursAgo: 26 },
    ],
    recommended: [
      { department: 'NDRF', place: 0, description: `${SIM_TAG} Pre-position fictional rescue teams near the simulated landfall point.`, priority: 'critical', team: 'Rescue Unit (sim)' },
      { department: 'Municipal Corp', place: 1, description: `${SIM_TAG} Open simulated shelters and publish the mock capacity board.`, priority: 'high', team: 'Team Alpha (sim)' },
      { department: 'Health & EMS', place: 2, description: `${SIM_TAG} Stage fictional medical kits at the simulated shelter sites.`, priority: 'moderate', team: 'Team Charlie (sim)' },
      { department: 'Power Utility', place: 3, description: `${SIM_TAG} Drill-switch simulated feeders to backup power.`, priority: 'low', team: 'Team Charlie (sim)' },
    ],
    tasks: [
      { title: `${SIM_TAG} Verify drill alert evidence pack`, department: 'Municipal Corp', place: 0, priority: 'Critical', status: 'Submitted', progress: 100, officer: 0, hoursAgo: 20, report: { text: 'Simulated evidence reviewed against the fictional sensor grid. Drill verification complete.', assisted: 0, location: 'Drill control room (sim)' } },
      { title: `${SIM_TAG} Open simulated shelters`, department: 'Municipal Corp', place: 1, priority: 'High', status: 'In Progress', progress: 60, officer: 1, hoursAgo: 8 },
      { title: `${SIM_TAG} Evacuate fictional shoreline belt`, department: 'NDRF', place: 0, priority: 'Critical', status: 'Assigned', progress: 10, officer: 2, hoursAgo: 3 },
      { title: `${SIM_TAG} Stage fictional medical kits`, department: 'Health & EMS', place: 2, priority: 'Medium', status: 'Assigned', progress: 0, officer: 3, hoursAgo: 2 },
    ],
    notifications: [
      { message: `${SIM_TAG} Drill assignment: evacuate the fictional shoreline belt (linked mock task). No real dispatch occurred.`, priority: 'Critical', task: 2, hoursAgo: 3, read: false },
      { message: `${SIM_TAG} Drill update: simulated shelters opening; mock capacity board published.`, priority: 'High', task: 1, hoursAgo: 7, read: false },
      { message: `${SIM_TAG} Drill verification complete for the fictional cyclone evidence pack.`, priority: 'Medium', task: 0, hoursAgo: 19, read: true },
    ],
    recoveryDepth: { assessments: 2, damages: 3, expenses: 3 },
    figureScale: { homes: 12400, damageCr: 24, prepCr: 4.2, recoveryCr: 9.8, people: 46000 },
  },
  'cyclone-orange': {
    tempC: 28,
    condition: 'Cloudy with strengthening winds',
    windKmh: 78,
    windDir: 'SE',
    pressureHpa: 994,
    humidity: 84,
    surgeM: 1.1,
    forecastConditions: ['Heavy rain', 'Heavy rain', 'Thunderstorm', 'Moderate rain', 'Moderate rain', 'Partly cloudy', 'Partly cloudy'],
    intelSummary: `${SIM_TAG} Simulated screening: a fictional cyclone is organising offshore and the drill is in preparedness mode. Training output, not an official warning.`,
    factors: [
      `${SIM_TAG} Mock winds approaching the simulated ORANGE threshold.`,
      `${SIM_TAG} Fictional swell rising along the simulated shoreline.`,
      `${SIM_TAG} Simulated screening score 68/100 for drill purposes only.`,
    ],
    reasoning: [
      `${SIM_TAG} Fictional sensor grid shows an organising mock circulation.`,
      `${SIM_TAG} Drill rulebook maps these readings to a simulated ORANGE tier.`,
      `${SIM_TAG} No official warning exists for this fictional event.`,
    ],
    analog: `${SIM_TAG} Fictional analog: Drill Cyclone 2021 (training record)`,
    historyEvents: [
      { name: 'Drill Cyclone Mora-2021', wind: 140, surge: 1.8, km: 88, year: 2021 },
      { name: 'Drill Cyclone Pika-2016', wind: 120, surge: 1.2, km: 150, year: 2016 },
      { name: 'Drill Cyclone Lila-2023', wind: 155, surge: 2.1, km: 65, year: 2023 },
      { name: 'Drill Cyclone Orca-2014', wind: 110, surge: 1.0, km: 210, year: 2014 },
    ],
    alerts: [
      { title: `${SIM_TAG} ORANGE cyclone advisory — fictional storm organising`, description: `${SIM_TAG} Drill advisory: a fictional cyclone is organising offshore. Training notification only — not an official warning and not delivered anywhere.`, severity: 'high', tier: 'ORANGE', hoursAgo: 6 },
      { title: `${SIM_TAG} YELLOW watch — fictional disturbance tracked`, description: `${SIM_TAG} Earliest drill notice for this fictional system, kept for the training timeline.`, severity: 'moderate', tier: 'YELLOW', hoursAgo: 30 },
    ],
    recommended: [
      { department: 'Municipal Corp', place: 1, description: `${SIM_TAG} Place simulated shelters on standby and check the mock rosters.`, priority: 'high', team: 'Team Alpha (sim)' },
      { department: 'NDRF', place: 0, description: `${SIM_TAG} Stage fictional rescue equipment at the simulated depot.`, priority: 'high', team: 'Rescue Unit (sim)' },
      { department: 'Power Utility', place: 3, description: `${SIM_TAG} Inspect fictional backup generators in the drill log.`, priority: 'low', team: 'Team Charlie (sim)' },
    ],
    tasks: [
      { title: `${SIM_TAG} Place simulated shelters on standby`, department: 'Municipal Corp', place: 1, priority: 'High', status: 'In Progress', progress: 45, officer: 1, hoursAgo: 7 },
      { title: `${SIM_TAG} Stage fictional rescue equipment`, department: 'NDRF', place: 0, priority: 'High', status: 'Assigned', progress: 0, officer: 2, hoursAgo: 4 },
      { title: `${SIM_TAG} Inspect fictional backup generators`, department: 'Power Utility', place: 3, priority: 'Low', status: 'Assigned', progress: 0, officer: 4, hoursAgo: 2 },
    ],
    notifications: [
      { message: `${SIM_TAG} Drill assignment: place simulated shelters on standby (linked mock task). No real dispatch occurred.`, priority: 'High', task: 0, hoursAgo: 7, read: false },
      { message: `${SIM_TAG} Drill watch issued for the fictional offshore disturbance.`, priority: 'Medium', task: null, hoursAgo: 29, read: true },
    ],
    recoveryDepth: { assessments: 1, damages: 2, expenses: 1 },
    figureScale: { homes: 3200, damageCr: 8, prepCr: 3.1, recoveryCr: 2.4, people: 18000 },
  },
  'cyclone-green': {
    tempC: 30,
    condition: 'Sunny and calm',
    windKmh: 14,
    windDir: 'NE',
    pressureHpa: 1014,
    humidity: 55,
    surgeM: 0,
    forecastConditions: ['Sunny', 'Sunny', 'Partly cloudy', 'Sunny', 'Partly cloudy', 'Light rain', 'Sunny'],
    intelSummary: `${SIM_TAG} Simulated screening: seas are calm and the drill is in routine monitoring mode. Training output, not an official warning.`,
    factors: [
      `${SIM_TAG} Mock winds well below every simulated threshold.`,
      `${SIM_TAG} Fictional seas calm across the simulated zone.`,
      `${SIM_TAG} Simulated screening score 12/100 for drill purposes only.`,
    ],
    reasoning: [
      `${SIM_TAG} Fictional sensor grid shows no developing circulation.`,
      `${SIM_TAG} Drill rulebook maps these readings to a simulated GREEN tier.`,
      `${SIM_TAG} No official warning exists for this fictional event.`,
    ],
    analog: `${SIM_TAG} Fictional analog: calm drill season 2022 (training record)`,
    historyEvents: [
      { name: 'Drill Cyclone Pika-2016', wind: 120, surge: 1.2, km: 150, year: 2016 },
      { name: 'Drill Cyclone Mora-2021', wind: 140, surge: 1.8, km: 88, year: 2021 },
      { name: 'Drill Cyclone Orca-2014', wind: 110, surge: 1.0, km: 210, year: 2014 },
    ],
    alerts: [
      { title: `${SIM_TAG} GREEN all-clear — seas calm in the drill area`, description: `${SIM_TAG} Drill notice: routine fictional monitoring continues with no threat. Training notification only — not an official warning and not delivered anywhere.`, severity: 'low', tier: 'GREEN', hoursAgo: 3 },
    ],
    recommended: [
      { department: 'Municipal Corp', place: 2, description: `${SIM_TAG} Continue the routine mock watch and log fictional readings.`, priority: 'low', team: 'Team Alpha (sim)' },
    ],
    tasks: [
      { title: `${SIM_TAG} Log routine fictional watch readings`, department: 'Municipal Corp', place: 2, priority: 'Low', status: 'Submitted', progress: 100, officer: 0, hoursAgo: 5, report: { text: 'Simulated watch log updated. Fictional seas calm; drill remains green.', assisted: 0, location: 'Drill control room (sim)' } },
    ],
    notifications: [
      { message: `${SIM_TAG} Drill notice: routine monitoring log updated; drill remains green.`, priority: 'Low', task: 0, hoursAgo: 4, read: true },
    ],
    recoveryDepth: { assessments: 0, damages: 0, expenses: 0 },
    figureScale: { homes: 0, damageCr: 0, prepCr: 0.1, recoveryCr: 0, people: 0 },
  },
};

const OFFICER_SEEDS = [
  { name: 'Aarav Sharma (SIMULATED)', roleId: 'role_1' },
  { name: 'Meera Iyer (SIMULATED)', roleId: 'role_2' },
  { name: 'Kabir Singh (SIMULATED)', roleId: 'role_3' },
  { name: 'Divya Nair (SIMULATED)', roleId: 'role_4' },
  { name: 'Arjun Rao (SIMULATED)', roleId: 'role_5' },
];

function figure(
  key: string,
  label: string,
  value: number | null,
  unit: string,
  confidence: 'High' | 'Medium' | 'Low',
): AssessmentFigure {
  return {
    key,
    label: `${label} (SIMULATED)`,
    value,
    unit,
    calculation: `${SIM_TAG} Derived from fictional drill inputs for training only.`,
    assumptions: [`${SIM_TAG} All inputs are fictional drill values.`],
    sources: [{ name: 'Simulator training dataset', detail: 'In-memory drill snapshot; no live source.', fetchedAt: new Date().toISOString() }],
    confidence,
    explanation: `${SIM_TAG} Training figure. Not a real estimate and not usable for official decisions.`,
    calibratedFrom: null,
  };
}

export function buildSimSnapshot(zone: SimZone, scenario: SimScenario): SimSnapshot {
  const narrative = NARRATIVES[scenario.id];
  if (!narrative) throw new Error(`Unknown simulator scenario: ${scenario.id}`);
  const base = Date.now();
  const builtAt = new Date(base).toISOString();
  const regionKey = zone.regionKey;
  const recovery = narrative.recoveryDepth;
  const placeName = (index: number) => zone.places[index % zone.places.length].name;

  const officers: OfficerUser[] = OFFICER_SEEDS.map((seed, index) => ({
    id: `sim-officer-${index + 1}`,
    name: seed.name,
    email: `sim.officer${index + 1}@simulator.local`,
    roleId: seed.roleId,
    isActive: true,
  }));

  const tasks: BackendTask[] = narrative.tasks.map((seed, index) => ({
    id: `sim-task-${index + 1}`,
    title: seed.title,
    department: seed.department,
    location: placeName(seed.place),
    priority: seed.priority,
    assigneeUserId: officers[seed.officer % officers.length].id,
    assigneeName: officers[seed.officer % officers.length].name,
    instructions: `${SIM_TAG} Drill instructions for the fictional ${scenario.hazardName.toLowerCase()} exercise at ${placeName(seed.place)}.`,
    deadline: isoDaysAhead(base, 2),
    status: seed.status,
    progress: seed.progress,
    source: index % 2 === 0 ? 'ai' : 'manual',
    sourceRef: index % 2 === 0 ? `sim-rec-${index + 1}` : null,
    regionKey,
    createdAt: isoHoursAgo(base, seed.hoursAgo),
    createdById: officers[1].id,
    createdByName: officers[1].name,
    updatedAt: isoHoursAgo(base, Math.max(0, seed.hoursAgo - 2)),
    reports: seed.report
      ? [{
        at: isoHoursAgo(base, Math.max(0, seed.hoursAgo - 3)),
        byId: officers[seed.officer % officers.length].id,
        byName: officers[seed.officer % officers.length].name,
        text: `${SIM_TAG} ${seed.report.text}`,
        peopleAssisted: seed.report.assisted,
        locationNote: seed.report.location,
      }]
      : [],
  }));

  const notifications: OperationalNotification[] = narrative.notifications.map((seed, index) => ({
    id: `sim-note-${index + 1}`,
    recipientUserId: officers[(index + 2) % officers.length].id,
    recipientName: officers[(index + 2) % officers.length].name,
    senderId: officers[1].id,
    senderName: officers[1].name,
    message: seed.message,
    priority: seed.priority,
    taskId: seed.task === null ? null : tasks[seed.task % tasks.length].id,
    regionKey,
    read: seed.read,
    createdAt: isoHoursAgo(base, seed.hoursAgo),
  }));

  const alerts: ClimateAlert[] = narrative.alerts.map((seed, index) => ({
    id: `sim-alert-${index + 1}`,
    hazard_type: scenario.hazardId,
    severity: seed.severity,
    title: seed.title,
    description: seed.description,
    location: { name: zone.name, region_key: regionKey, latitude: zone.center.lat, longitude: zone.center.lon },
    source: 'Simulator training dataset',
    observed_at: isoHoursAgo(base, seed.hoursAgo),
    received_at: isoHoursAgo(base, seed.hoursAgo),
    measurements: { simulated: true, drillTier: seed.tier },
    is_simulation: true,
    simulation_tier: seed.tier,
  }));

  const historyEvents: HistoricalEventResponse[] = narrative.historyEvents.map((event) => ({
    matched_cyclone: `SIMULATED Cyclone ${event.name} (SIMULATED)`,
    hazard_type: scenario.hazardId,
    historical_peak_wind_kmh: event.wind || null,
    historical_surge_meters: event.surge || null,
    closest_approach_km: event.km,
    source: 'Simulator training dataset',
    reference_period: { start_date: `${event.year}-01-01`, end_date: `${event.year}-12-31` },
  }));

  const { homes, damageCr, prepCr, recoveryCr, people } = narrative.figureScale;
  const totals: AssessmentTotals = {
    damageTotalInr: damageCr * 10000000,
    damageTotalDerived: damageCr * 10000000,
    damageTotalOverride: false,
    preparationInr: prepCr * 10000000,
    recoveryInr: recoveryCr * 10000000,
    reliefEnvelopeInr: Math.round((prepCr + recoveryCr) * 10000000),
    affectedPeople: people,
    grandTotalInr: Math.round((damageCr + prepCr + recoveryCr) * 10000000),
  };
  const figures: AssessmentFigure[] = [
    figure('houses_damaged', 'Houses damaged', homes, 'count', 'Medium'),
    figure('damage_total_inr', 'Damage total', totals.damageTotalInr, 'INR', 'Low'),
    figure('preparation_inr', 'Preparation spend', totals.preparationInr, 'INR', 'Medium'),
    figure('recovery_inr', 'Recovery spend', totals.recoveryInr, 'INR', 'Low'),
    figure('affected_people', 'Affected people', people, 'count', 'Medium'),
  ];

  const makeAssessment = (index: number, status: 'pending_review' | 'approved'): AssessmentDetail => ({
    id: `sim-assess-${index + 1}`,
    publicId: `SIM-A-${String(index + 1).padStart(4, '0')}`,
    status,
    version: 1,
    aiAssessment: {
      engineVersion: 'simulator-1.0',
      generatedAt: isoHoursAgo(base, 15 - index * 4),
      narrative: `${SIM_TAG} Training assessment narrative for the fictional ${scenario.hazardName.toLowerCase()} drill in ${zone.shortName}.`,
      narrativeSource: 'Simulator training dataset',
      reasoning: narrative.reasoning,
      regionKey,
      regionName: zone.name,
      regionDetail: { country: zone.country, state: zone.state, code: regionKey },
      hazardId: scenario.hazardId,
      hazardName: scenario.hazardName,
      affectedAreas: zone.places.map((place) => place.name),
      figures,
      overallConfidence: 'Medium',
      evidenceSummary: {
        taskCount: tasks.length,
        submittedTaskCount: tasks.filter((task) => task.status === 'Submitted').length,
        reportCount: tasks.reduce((sum, task) => sum + task.reports.length, 0),
        peopleAssistedSum: tasks.reduce(
          (sum, task) => sum + task.reports.reduce((inner, report) => inner + (report.peopleAssisted ?? 0), 0),
          0,
        ),
        verifiedFeedbackCount: 0,
        gaps: [`${SIM_TAG} Training snapshot: evidence is fictional drill content.`],
      },
      evidenceExcerpts: [],
      observedInputs: { householdsAffected: homes, housesDamaged: homes, preparationCostInr: totals.preparationInr, recoveryCostInr: totals.recoveryInr },
      officerNotes: `${SIM_TAG} Drill officer notes (fictional).`,
      insuranceNotes: `${SIM_TAG} Training insurance notes. Not usable for real claims.`,
      disclaimer: `${SIM_TAG} Simulated assessment for training only. Not a real estimate.`,
    },
    officialEdits: [],
    versions: [{ version: 1, at: isoHoursAgo(base, 15 - index * 4), byId: officers[3].id, byName: officers[3].name, action: 'generated', reason: 'Simulated drill assessment generated.' }],
    approvalHistory: status === 'approved'
      ? [{ at: isoHoursAgo(base, 6), byId: officers[3].id, byName: officers[3].name, action: 'approved', reason: 'Simulated drill approval for training.', version: 1 }]
      : [],
    decision: status === 'approved'
      ? { action: 'accepted', byId: officers[3].id, byName: officers[3].name, at: isoHoursAgo(base, 6), reason: 'Simulated drill approval for training.', version: 1 }
      : null,
    approvedSnapshot: status === 'approved'
      ? { figures, totals, overridden: [], approvedAt: isoHoursAgo(base, 6), version: 1 }
      : null,
    reportVersions: status === 'approved'
      ? [{ version: 1, filename: `SIM-A-000${index + 1}-report.txt`, byteSize: 512, sha256: 'simulated', generatedAt: isoHoursAgo(base, 5), generatedById: officers[3].id, generatedByName: officers[3].name, reason: 'Simulated drill report.', assessmentVersion: 1 }]
      : [],
    createdAt: isoHoursAgo(base, 15 - index * 4),
    createdByName: officers[3].name,
    updatedAt: isoHoursAgo(base, 5),
    current: { figures, totals, overridden: [] },
  });

  const assessments = [
    { status: 'pending_review' as const, index: 0 },
    { status: 'approved' as const, index: 1 },
  ]
    .slice(0, recovery.assessments)
    .map(({ status, index }) => makeAssessment(index, status));

  const damages: DamageAssessment[] = zone.places
    .slice(0, 3)
    .slice(0, recovery.damages)
    .map((place, index) => ({
      id: `sim-damage-${index + 1}`,
      regionKey,
      hazardId: scenario.hazardId,
      householdsAffected: 400 + index * 150,
      housesDamaged: 120 + index * 40,
      housesDestroyed: 12 + index * 5,
      cropHectares: 60 + index * 20,
      livestockLost: 8 + index * 3,
      infraSites: 2 + index,
      roadsKm: 3 + index,
      locationNote: place.name,
      notes: `${SIM_TAG} Fictional drill damage entry for training.`,
      createdAt: isoHoursAgo(base, 12 - index * 2),
      createdById: officers[2].id,
      createdByName: officers[2].name,
      updatedAt: isoHoursAgo(base, 11 - index * 2),
    }));

  const expenses: ExpenseRecord[] = [
    { kind: 'preparedness' as const, category: 'Fictional shelter supplies', amountInr: Math.round(prepCr * 10000000 * 0.6), spentAt: isoDaysAhead(base, -1) },
    { kind: 'preparedness' as const, category: 'Fictional drill fuel and transport', amountInr: Math.round(prepCr * 10000000 * 0.4), spentAt: isoDaysAhead(base, -1) },
    { kind: 'recovery' as const, category: 'Fictional debris clearance', amountInr: Math.round(recoveryCr * 10000000 * 0.5), spentAt: isoDaysAhead(base, 0) },
  ]
    .slice(0, recovery.expenses)
    .map((seed, index) => ({
      id: `sim-expense-${index + 1}`,
      regionKey,
      hazardId: scenario.hazardId,
      kind: seed.kind,
      category: `${seed.category} (SIMULATED)`,
      amountInr: seed.amountInr,
      receiptRef: `SIM-R-${index + 1}`,
      vendor: `Fictional Vendor ${index + 1} (sim)`,
      spentAt: seed.spentAt,
      notes: `${SIM_TAG} Training expense; no real money moved.`,
      assessmentId: assessments[0].id,
      createdAt: isoHoursAgo(base, 10 - index * 2),
      createdById: officers[3].id,
      createdByName: officers[3].name,
      updatedAt: isoHoursAgo(base, 9 - index * 2),
    }));

  const evidence: EvidenceAttachment[] = damages.length > 0
    ? [
      {
        id: 'sim-evidence-1',
        linkedKind: 'damage_assessment',
        linkedId: damages[0].id,
        regionKey,
        hazardId: scenario.hazardId,
        caption: `${SIM_TAG} Fictional drill photo log (no real imagery).`,
        photos: [],
        photoCount: 0,
        uploadedAt: isoHoursAgo(base, 10),
        uploadedById: officers[2].id,
        uploadedByName: officers[2].name,
      },
    ]
    : [];

  const feedback: FeedbackItem[] = assessments.length > 0
    ? [
      {
        id: 'sim-feedback-1',
        assessmentId: assessments[0].id,
        assessmentPublicId: assessments[0].publicId,
        regionKey,
        hazardId: scenario.hazardId,
        path: 'figures.houses_damaged',
        label: 'Houses damaged (SIMULATED)',
        category: 'damage',
        aiValue: homes,
        correctedValue: Math.round(homes * 0.9),
        deltaPct: -10,
        reason: `${SIM_TAG} Drill correction for training review.`,
        officerName: officers[3].name,
        at: isoHoursAgo(base, 7),
        status: 'verified',
        engineVersion: 'simulator-1.0',
      },
    ]
    : [];

  const forecastDays = narrative.forecastConditions.map((condition, index) => ({
    date: isoDaysAhead(base, index),
    max_temp_c: narrative.tempC + 2 - index * 0.4,
    min_temp_c: narrative.tempC - 5 - index * 0.2,
    condition: `${condition} (sim)`,
  }));

  const regionRecord: Region = {
    id: regionKey,
    name: zone.name,
    type: 'district',
    code: regionKey,
    active: true,
    hazardIds: [scenario.hazardId],
    countryCode: 'SIM',
    countryName: zone.country,
    stateCode: 'SIM-ST',
    stateName: zone.state,
  };

  const primaryZoneColor: 'red' | 'orange' | 'green' =
    scenario.tier === 'RED' ? 'red' : scenario.tier === 'ORANGE' ? 'orange' : 'green';

  return {
    zoneId: zone.id,
    scenarioId: scenario.id,
    regionKey,
    builtAt,
    apiRegions: {
      [regionKey]: {
        min_lon: zone.bounds.min_lon,
        min_lat: zone.bounds.min_lat,
        max_lon: zone.bounds.max_lon,
        max_lat: zone.bounds.max_lat,
        name: zone.name,
      },
    },
    regionRecord,
    regionConfig: { defaultRegionId: regionKey },
    regionItems: [regionRecord],
    hazards: [{ id: scenario.hazardId, name: `${scenario.hazardName} (SIMULATED)`, code: scenario.hazardId, active: true }],
    population: { timestamp: builtAt, region_target: zone.name, total_population: zone.population },
    forecast: { region_target: zone.name, latitude: zone.center.lat, longitude: zone.center.lon, forecast: forecastDays },
    infrastructure: {
      hospitals: zone.hospitals.map((facility) => ({ name: facility.name, address: facility.address, lat: facility.lat, lon: facility.lon })),
      shelters: zone.shelters.map((facility) => ({ name: facility.name, address: facility.address, lat: facility.lat, lon: facility.lon })),
    },
    currentConditions: {
      timestamp: builtAt,
      region_target: zone.name,
      temperature_c: narrative.tempC,
      condition: `${narrative.condition} (sim)`,
      wind_speed_kmh: narrative.windKmh,
      wind_direction: narrative.windDir,
      pressure_hpa: narrative.pressureHpa,
      relative_humidity_percent: narrative.humidity,
    },
    intelligence: {
      status: 'available',
      region: regionKey,
      hazard: scenario.hazardId,
      supported: true,
      generated_at: builtAt,
      ml_probability: {
        status: 'SCORED',
        probability: scenario.score / 100,
        model_id: 'simulator-drill-v1',
        features_used: { drill_wind_kmh: narrative.windKmh, drill_surge_m: narrative.surgeM },
        label: `${SIM_TAG} Simulated screening signal for training.`,
        reason: null,
        note: `${SIM_TAG} Drill score only; not a real disaster probability.`,
      },
      local_impact_assessment: {
        regional_warning_level: null,
        regional_warning_status: 'none',
        local_impact_status: 'inside_footprint',
        local_impact_zone: scenario.tier,
        distance_to_footprint_km: 0,
        reason: `${SIM_TAG} Simulated footprint for the fictional ${scenario.hazardName.toLowerCase()} drill.`,
        source: 'Simulator training dataset',
        updated_at: builtAt,
      },
      data_quality: {
        ingestion_status: 'SUCCESS',
        telemetry_status: 'AVAILABLE',
        ingestion_error: null,
        telemetry_timestamp: builtAt,
        sources: { drill_sensors: 'simulator', drill_rulebook: 'simulator' },
      },
      current_conditions: {
        wind_speed_kmh: narrative.windKmh,
        pressure_hpa: narrative.pressureHpa,
        storm_surge_meters: narrative.surgeM,
        alert_status: `${scenario.tier} (SIMULATED)`,
      },
      risk_assessment: {
        level: scenario.level,
        score: scenario.score,
        factors: narrative.factors,
        method: `${SIM_TAG} Fictional drill rulebook applied to simulated readings for training.`,
        official_warning: false,
        screening_level: scenario.level,
        warning_floor: null,
        level_basis: 'simulated-screening',
        note: narrative.intelSummary,
      },
      risk_zones: [
        { id: 'sim-zone-primary', label: `${scenario.tier} drill zone — ${zone.places[0].name}`, color: primaryZoneColor, lat: zone.center.lat + 0.08, lon: zone.center.lon + 0.08, radius_km: 7, description: `${SIM_TAG} Primary fictional drill area.` },
        { id: 'sim-zone-buffer', label: `Buffer drill area — ${zone.places[1].name}`, color: 'yellow', lat: zone.center.lat - 0.06, lon: zone.center.lon - 0.04, radius_km: 14, description: `${SIM_TAG} Secondary fictional drill area.` },
        { id: 'sim-zone-safe', label: `Staging drill area — ${zone.places[3].name}`, color: 'green', lat: zone.center.lat - 0.16, lon: zone.center.lon - 0.14, radius_km: 20, description: `${SIM_TAG} Fictional staging area for drill teams.` },
      ],
      official_warnings: [],
      local_impact: {
        verdict: 'inside_footprint',
        basis: [`${SIM_TAG} Simulated footprint covers the fictional drill zone.`, `${SIM_TAG} Training geometry only; not a real hazard footprint.`],
        distance_to_footprint_km: 0,
        geometry_source: 'Simulator training dataset',
      },
      historical_context: { primary_analog: narrative.analog, historical_analogs: [] },
      demography: { total_population: zone.population },
      critical_places: {
        hospitals: zone.hospitals.map((facility) => ({ name: facility.name, address: facility.address, lat: facility.lat, lon: facility.lon })),
        shelters: zone.shelters.map((facility) => ({ name: facility.name, address: facility.address, lat: facility.lat, lon: facility.lon })),
      },
      insurance_summary: {
        status: 'EVALUATED',
        trigger_met: scenario.tier !== 'GREEN',
        trigger_threshold_m: 1.5,
        observed_water_depth_m: narrative.surgeM,
        estimated_payout_cr: Math.round(narrative.figureScale.damageCr * 0.4 * 10) / 10,
        headline: `${SIM_TAG} Simulated parametric trigger review (training).`,
        coverage_focus: [`${SIM_TAG} Fictional drill policies only.`],
        note: `${SIM_TAG} Not a real insurance evaluation.`,
      },
      ai_analysis: {
        summary: narrative.intelSummary,
        recommended_tasks: narrative.recommended.map((rec) => ({
          department: rec.department,
          location: placeName(rec.place),
          description: rec.description,
          priority: rec.priority,
          sub_team: rec.team,
          status_text: 'simulated',
        })),
        reasoning_context: narrative.reasoning,
      },
    },
    capabilities: {
      region: regionKey,
      hazards: [{ id: scenario.hazardId, name: `${scenario.hazardName} (SIMULATED)`, code: scenario.hazardId, configured: true, implemented: true, intelligence_status: 'available' }],
      configured_hazards: [scenario.hazardId],
      implemented_hazards: [scenario.hazardId],
      not_implemented_hazards: [],
      historical_hazards: [scenario.hazardId],
      history_coverage: { complete: true, note: `${SIM_TAG} Fictional drill history.` },
    },
    alerts,
    historyEvents,
    tasks,
    notifications,
    officers,
    assessments,
    damages,
    expenses,
    evidence,
    feedback,
  };
}

/** Canned drill reply for the rescue tactical assistant in Simulator Mode. */
export function simDispatchReply(query: string, zone: SimZone, scenario: SimScenario): { text: string } {
  const shelter = zone.shelters[0];
  return {
    text: `${SIM_TAG} Drill reply for the fictional ${scenario.hazardName.toLowerCase()} exercise in ${zone.shortName}: `
      + `direct fictional callers to ${shelter.name} (${shelter.address}); fictional field teams report no verified hazards beyond the exercise script. `
      + `Your drill query was: "${query.slice(0, 140)}". Real emergencies must always contact local emergency services — this assistant is running fictional training data.`,
  };
}
