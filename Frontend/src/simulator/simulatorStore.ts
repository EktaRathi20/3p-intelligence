/**
 * Simulator Mode store (SIMULATION ONLY).
 *
 * Framework-agnostic singleton holding the active drill: selected zone,
 * scenario, and the isolated in-memory snapshot. Service modules consult
 * this store and, when a drill is active, serve or mutate the snapshot
 * instead of touching the backend — live records are never read or written
 * in Simulator Mode.
 *
 * All drill state is in-memory: reloading the page exits Simulator Mode.
 */
import type {
  AssessmentDetail,
  AssessmentSummary,
  DamageAssessment,
  DamageAssessmentInput,
  EvidenceAttachment,
  EvidenceInput,
  ExpenseInput,
  ExpenseRecord,
  FeedbackItem,
  ObservedInputs,
  ReportVersion,
} from '@/services/recoveryApi';
import type {
  BackendTask,
  CreateNotificationInput,
  CreateTaskInput,
  OperationalNotification,
  UpdateTaskInput,
} from '@/services/operationalApi';
import type { DispatchChatResponse, HistoricalResponse } from '@/types/api';
import type { OfficerUser } from '@/types';
import { buildSimSnapshot, simDispatchReply, type SimSnapshot } from './simSnapshot.ts';
import { getSimZone, type SimZone } from './simZones.ts';
import { getSimScenario, type SimScenario } from './simScenarios.ts';

export interface SimulatorSelection {
  active: boolean;
  zone: SimZone | null;
  scenario: SimScenario | null;
}

interface SimulatorState extends SimulatorSelection {
  snapshot: SimSnapshot | null;
}

let state: SimulatorState = { active: false, zone: null, scenario: null, snapshot: null };
let simSeq = 100;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((listener) => listener());
}

export function subscribeSimulator(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getSimulatorState(): SimulatorState {
  return state;
}

export function isSimulatorActive(): boolean {
  return state.active;
}

export function getSimSnapshot(): SimSnapshot {
  if (!state.active || !state.snapshot) {
    throw new Error('Simulator Mode is not active.');
  }
  return state.snapshot;
}

export function enterSimulator(zoneId: string, scenarioId: string): SimulatorSelection {
  const zone = getSimZone(zoneId);
  const scenario = getSimScenario(scenarioId);
  if (!zone || !scenario) {
    throw new Error('Unknown simulator zone or scenario.');
  }
  simSeq = 100;
  state = { active: true, zone, scenario, snapshot: buildSimSnapshot(zone, scenario) };
  notify();
  return { active: true, zone, scenario };
}

export function exitSimulator(): void {
  state = { active: false, zone: null, scenario: null, snapshot: null };
  notify();
}

const SIM_OPERATOR_ID = 'sim-operator';
const SIM_OPERATOR_NAME = 'Simulator operator (simulated)';

function nextId(prefix: string): string {
  simSeq += 1;
  return `${prefix}-${simSeq}`;
}

function officerName(officers: OfficerUser[], id: string | undefined, fallback: string): string {
  if (!id) return fallback;
  return officers.find((officer) => officer.id === id)?.name ?? fallback;
}

// ---------------------------------------------------------------------------
// Simulated operational records (tasks + notifications, in-memory only)
// ---------------------------------------------------------------------------

export function simListTasks(params?: { assigneeUserId?: string; regionKey?: string; status?: string }): BackendTask[] {
  const snapshot = getSimSnapshot();
  return snapshot.tasks.filter((task) => {
    if (params?.assigneeUserId && task.assigneeUserId !== params.assigneeUserId) return false;
    if (params?.regionKey && task.regionKey !== params.regionKey) return false;
    if (params?.status && task.status !== params.status) return false;
    return true;
  });
}

export function simCreateTask(input: CreateTaskInput): BackendTask {
  const snapshot = getSimSnapshot();
  const now = new Date().toISOString();
  const task: BackendTask = {
    id: nextId('sim-task'),
    title: input.title,
    department: input.department,
    location: input.location,
    priority: input.priority,
    assigneeUserId: input.assigneeUserId,
    assigneeName: officerName(snapshot.officers, input.assigneeUserId, 'Simulated team'),
    instructions: input.instructions ?? '',
    deadline: input.deadline ?? null,
    status: 'Assigned',
    progress: 0,
    source: input.source ?? 'manual',
    sourceRef: input.sourceRef ?? null,
    regionKey: input.regionKey ?? snapshot.regionKey,
    createdAt: now,
    createdById: SIM_OPERATOR_ID,
    createdByName: SIM_OPERATOR_NAME,
    updatedAt: now,
    reports: [],
  };
  snapshot.tasks.unshift(task);
  if (input.notifyAssignee) {
    simCreateNotification({
      recipientUserId: task.assigneeUserId,
      message: `[SIMULATED] Drill assignment: "${task.title}" assigned to ${task.assigneeName}. No real dispatch occurred.`,
      priority: task.priority,
      taskId: task.id,
      regionKey: task.regionKey,
    });
  }
  return task;
}

export function simUpdateTask(taskId: string, input: UpdateTaskInput): BackendTask {
  const snapshot = getSimSnapshot();
  const task = snapshot.tasks.find((item) => item.id === taskId);
  if (!task) throw new Error('Simulated task not found.');
  const now = new Date().toISOString();
  if (input.status !== undefined) task.status = input.status;
  if (input.progress !== undefined) task.progress = input.progress;
  if (input.title !== undefined) task.title = input.title;
  if (input.department !== undefined) task.department = input.department;
  if (input.location !== undefined) task.location = input.location;
  if (input.priority !== undefined) task.priority = input.priority;
  if (input.instructions !== undefined) task.instructions = input.instructions;
  if (input.deadline !== undefined) task.deadline = input.deadline;
  if (input.assigneeUserId !== undefined) {
    task.assigneeUserId = input.assigneeUserId;
    task.assigneeName = officerName(snapshot.officers, input.assigneeUserId, task.assigneeName);
  }
  if (input.report) {
    task.reports.push({
      at: now,
      byId: SIM_OPERATOR_ID,
      byName: SIM_OPERATOR_NAME,
      text: input.report.text,
      peopleAssisted: input.report.peopleAssisted ?? null,
      locationNote: input.report.locationNote ?? null,
      photos: input.report.photos ?? [],
    });
  }
  task.updatedAt = now;
  if (input.notifyAssignee) {
    simCreateNotification({
      recipientUserId: task.assigneeUserId,
      message: `[SIMULATED] Drill update on "${task.title}": ${task.status} at ${task.progress}%. No real dispatch occurred.`,
      priority: task.priority,
      taskId: task.id,
      regionKey: task.regionKey,
    });
  }
  return task;
}

export function simListNotifications(): { notifications: OperationalNotification[]; unread: number } {
  const snapshot = getSimSnapshot();
  const notifications = [...snapshot.notifications].sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
  return { notifications, unread: notifications.filter((item) => !item.read).length };
}

export function simCreateNotification(input: CreateNotificationInput): OperationalNotification {
  const snapshot = getSimSnapshot();
  const notification: OperationalNotification = {
    id: nextId('sim-note'),
    recipientUserId: input.recipientUserId,
    recipientName: officerName(snapshot.officers, input.recipientUserId, 'Simulated officer'),
    senderId: SIM_OPERATOR_ID,
    senderName: SIM_OPERATOR_NAME,
    message: input.message,
    priority: input.priority,
    taskId: input.taskId ?? null,
    regionKey: input.regionKey ?? snapshot.regionKey,
    read: false,
    createdAt: new Date().toISOString(),
  };
  snapshot.notifications.unshift(notification);
  return notification;
}

export function simMarkNotificationRead(notificationId: string): OperationalNotification {
  const snapshot = getSimSnapshot();
  const notification = snapshot.notifications.find((item) => item.id === notificationId);
  if (!notification) throw new Error('Simulated notification not found.');
  notification.read = true;
  return notification;
}

// ---------------------------------------------------------------------------
// Simulated recovery records (in-memory only)
// ---------------------------------------------------------------------------

function toSummary(detail: AssessmentDetail): AssessmentSummary {
  return {
    id: detail.id,
    publicId: detail.publicId,
    regionKey: detail.aiAssessment.regionKey,
    regionName: detail.aiAssessment.regionName,
    hazardId: detail.aiAssessment.hazardId,
    hazardName: detail.aiAssessment.hazardName,
    status: detail.status,
    version: detail.version,
    overallConfidence: detail.aiAssessment.overallConfidence,
    totals: detail.current.totals,
    editCount: detail.officialEdits.length,
    reportCount: detail.reportVersions.length,
    createdAt: detail.createdAt,
    createdByName: detail.createdByName,
    updatedAt: detail.updatedAt,
  };
}

export function simListAssessments(params?: { status?: string; regionKey?: string; hazardId?: string }): AssessmentSummary[] {
  const snapshot = getSimSnapshot();
  return snapshot.assessments
    .filter((detail) => {
      if (params?.status && detail.status !== params.status) return false;
      if (params?.regionKey && detail.aiAssessment.regionKey !== params.regionKey) return false;
      if (params?.hazardId && detail.aiAssessment.hazardId !== params.hazardId) return false;
      return true;
    })
    .map((detail) => toSummary(detail));
}

export function simGetAssessment(assessmentId: string): AssessmentDetail {
  const snapshot = getSimSnapshot();
  const detail = snapshot.assessments.find((item) => item.id === assessmentId);
  if (!detail) throw new Error('Simulated assessment not found.');
  return detail;
}

export function simCreateAssessment(input: {
  regionKey: string;
  hazardId: string;
  observed: ObservedInputs;
  notes?: string;
}): AssessmentDetail {
  const snapshot = getSimSnapshot();
  const now = new Date().toISOString();
  const id = nextId('sim-assess');
  const template = snapshot.assessments[0];
  const detail: AssessmentDetail = {
    ...structuredClone(template),
    id,
    publicId: `SIM-A-${String(100 + snapshot.assessments.length).padStart(4, '0')}`,
    status: 'pending_review',
    version: 1,
    officialEdits: [],
    versions: [{ version: 1, at: now, byId: SIM_OPERATOR_ID, byName: SIM_OPERATOR_NAME, action: 'generated', reason: 'Simulated drill assessment created for training.' }],
    approvalHistory: [],
    decision: null,
    approvedSnapshot: null,
    reportVersions: [],
    createdAt: now,
    createdByName: SIM_OPERATOR_NAME,
    updatedAt: now,
  };
  detail.aiAssessment.generatedAt = now;
  detail.aiAssessment.regionKey = input.regionKey;
  detail.aiAssessment.hazardId = input.hazardId;
  const observedInputs: Record<string, number | null> = {};
  for (const key in input.observed) {
    observedInputs[key] = input.observed[key as keyof ObservedInputs] ?? null;
  }
  detail.aiAssessment.observedInputs = observedInputs;
  detail.aiAssessment.officerNotes = input.notes ?? '[SIMULATED] Drill assessment created during the exercise.';
  snapshot.assessments.unshift(detail);
  return detail;
}

export function simEditAssessment(
  assessmentId: string,
  edits: { path: string; newValue: number | null; reason: string }[],
): AssessmentDetail {
  const detail = simGetAssessment(assessmentId);
  const now = new Date().toISOString();
  edits.forEach((edit) => {
    const key = edit.path.split('.').pop() ?? edit.path;
    const figure = detail.current.figures.find((item) => item.key === key);
    const oldValue = figure?.currentValue ?? figure?.value ?? null;
    if (figure) {
      figure.currentValue = edit.newValue;
      figure.edited = true;
    }
    detail.officialEdits.push({
      at: now,
      byId: SIM_OPERATOR_ID,
      byName: SIM_OPERATOR_NAME,
      path: edit.path,
      label: figure?.label ?? key,
      aiValue: figure?.value ?? null,
      oldValue,
      newValue: edit.newValue,
      reason: edit.reason,
    });
  });
  detail.version += 1;
  detail.updatedAt = now;
  detail.versions.push({ version: detail.version, at: now, byId: SIM_OPERATOR_ID, byName: SIM_OPERATOR_NAME, action: 'edited', reason: 'Simulated official edits for training.' });
  return detail;
}

export function simDecideAssessment(
  assessmentId: string,
  input: { action: 'accept' | 'reject'; reason: string },
): AssessmentDetail {
  const detail = simGetAssessment(assessmentId);
  const now = new Date().toISOString();
  detail.status = input.action === 'accept' ? 'approved' : 'rejected';
  detail.decision = {
    action: input.action === 'accept' ? 'accepted' : 'rejected',
    byId: SIM_OPERATOR_ID,
    byName: SIM_OPERATOR_NAME,
    at: now,
    reason: input.reason,
    version: detail.version,
  };
  detail.approvalHistory.push({ at: now, byId: SIM_OPERATOR_ID, byName: SIM_OPERATOR_NAME, action: detail.status, reason: input.reason, version: detail.version });
  if (input.action === 'accept') {
    detail.approvedSnapshot = {
      figures: detail.current.figures,
      totals: detail.current.totals,
      overridden: detail.current.overridden,
      approvedAt: now,
      version: detail.version,
    };
  }
  detail.updatedAt = now;
  return detail;
}

export function simAssessmentReports(assessmentId: string): ReportVersion[] {
  return simGetAssessment(assessmentId).reportVersions;
}

export function simRegenerateReport(assessmentId: string, reason: string): ReportVersion[] {
  const detail = simGetAssessment(assessmentId);
  const version = detail.reportVersions.length + 1;
  detail.reportVersions.push({
    version,
    filename: `${detail.publicId}-report-v${version}.txt`,
    byteSize: 512,
    sha256: 'simulated',
    generatedAt: new Date().toISOString(),
    generatedById: SIM_OPERATOR_ID,
    generatedByName: SIM_OPERATOR_NAME,
    reason,
    assessmentVersion: detail.version,
  });
  return detail.reportVersions;
}

export function simDownloadReport(assessmentId: string, version?: number): { blob: Blob; filename: string } {
  const detail = simGetAssessment(assessmentId);
  const text = [
    '[SIMULATED] Training assessment report — not an official document.',
    `Assessment: ${detail.publicId} (${detail.aiAssessment.regionName})`,
    `Hazard: ${detail.aiAssessment.hazardName} | Status: ${detail.status} | Report version: ${version ?? detail.reportVersions.length}`,
    '',
    ...detail.current.figures.map((figure) => `- ${figure.label}: ${figure.currentValue ?? figure.value ?? 'n/a'} ${figure.unit} [${figure.confidence} confidence]`),
    '',
    '[SIMULATED] Generated from fictional drill data. Do not use for real decisions.',
  ].join('\n');
  return { blob: new Blob([text], { type: 'text/plain' }), filename: `${detail.publicId}-simulated-report.txt` };
}

export function simListDamages(params?: { regionKey?: string; hazardId?: string }): DamageAssessment[] {
  const snapshot = getSimSnapshot();
  return snapshot.damages.filter((item) => {
    if (params?.regionKey && item.regionKey !== params.regionKey) return false;
    if (params?.hazardId && item.hazardId !== params.hazardId) return false;
    return true;
  });
}

export function simCreateDamage(input: DamageAssessmentInput): DamageAssessment {
  const snapshot = getSimSnapshot();
  const now = new Date().toISOString();
  const record: DamageAssessment = {
    id: nextId('sim-damage'),
    regionKey: input.regionKey,
    hazardId: input.hazardId,
    householdsAffected: input.householdsAffected ?? null,
    housesDamaged: input.housesDamaged ?? null,
    housesDestroyed: input.housesDestroyed ?? null,
    cropHectares: input.cropHectares ?? null,
    livestockLost: input.livestockLost ?? null,
    infraSites: input.infraSites ?? null,
    roadsKm: input.roadsKm ?? null,
    locationNote: input.locationNote ?? null,
    notes: input.notes ?? '[SIMULATED] Drill damage entry.',
    createdAt: now,
    createdById: SIM_OPERATOR_ID,
    createdByName: SIM_OPERATOR_NAME,
    updatedAt: now,
  };
  snapshot.damages.unshift(record);
  return record;
}

export function simListExpenses(params?: { regionKey?: string; hazardId?: string; kind?: string }): { expenses: ExpenseRecord[]; totalInr: number } {
  const snapshot = getSimSnapshot();
  const expenses = snapshot.expenses.filter((item) => {
    if (params?.regionKey && item.regionKey !== params.regionKey) return false;
    if (params?.hazardId && item.hazardId !== params.hazardId) return false;
    if (params?.kind && item.kind !== params.kind) return false;
    return true;
  });
  return { expenses, totalInr: expenses.reduce((sum, item) => sum + item.amountInr, 0) };
}

export function simCreateExpense(input: ExpenseInput): ExpenseRecord {
  const snapshot = getSimSnapshot();
  const now = new Date().toISOString();
  const record: ExpenseRecord = {
    id: nextId('sim-expense'),
    regionKey: input.regionKey,
    hazardId: input.hazardId ?? null,
    kind: input.kind,
    category: input.category,
    amountInr: input.amountInr,
    receiptRef: input.receiptRef ?? null,
    vendor: input.vendor ?? null,
    spentAt: input.spentAt ?? null,
    notes: input.notes ?? '[SIMULATED] Training expense; no real money moved.',
    assessmentId: null,
    createdAt: now,
    createdById: SIM_OPERATOR_ID,
    createdByName: SIM_OPERATOR_NAME,
    updatedAt: now,
  };
  snapshot.expenses.unshift(record);
  return record;
}

export function simListEvidence(params?: { regionKey?: string; linkedKind?: string; linkedId?: string }): EvidenceAttachment[] {
  const snapshot = getSimSnapshot();
  return snapshot.evidence.filter((item) => {
    if (params?.regionKey && item.regionKey !== params.regionKey) return false;
    if (params?.linkedKind && item.linkedKind !== params.linkedKind) return false;
    if (params?.linkedId && item.linkedId !== params.linkedId) return false;
    return true;
  });
}

export function simCreateEvidence(input: EvidenceInput): EvidenceAttachment {
  const snapshot = getSimSnapshot();
  const record: EvidenceAttachment = {
    id: nextId('sim-evidence'),
    linkedKind: input.linkedKind,
    linkedId: input.linkedId,
    regionKey: input.regionKey ?? snapshot.regionKey,
    hazardId: input.hazardId ?? null,
    caption: input.caption ?? null,
    photos: input.photos,
    photoCount: input.photos.length,
    uploadedAt: new Date().toISOString(),
    uploadedById: SIM_OPERATOR_ID,
    uploadedByName: SIM_OPERATOR_NAME,
  };
  snapshot.evidence.unshift(record);
  return record;
}

export function simListFeedback(params?: { status?: string; hazardId?: string }): FeedbackItem[] {
  const snapshot = getSimSnapshot();
  return snapshot.feedback.filter((item) => {
    if (params?.status && item.status !== params.status) return false;
    if (params?.hazardId && item.hazardId !== params.hazardId) return false;
    return true;
  });
}

export function simGetHistory(params: {
  page: number;
  pageSize: number;
  search: string;
  sortBy: 'newest' | 'oldest' | 'wind' | 'distance';
  hazard?: string;
}): HistoricalResponse {
  const snapshot = getSimSnapshot();
  const scenario = getSimScenario(snapshot.scenarioId);
  const query = params.search.trim().toLowerCase();
  const events = snapshot.historyEvents.filter((event) => {
    if (params.hazard && event.hazard_type !== params.hazard) return false;
    if (query && !event.matched_cyclone.toLowerCase().includes(query)) return false;
    return true;
  });
  const endDate = (event: (typeof events)[number]) => event.reference_period.end_date;
  if (params.sortBy === 'oldest') events.sort((a, b) => endDate(a).localeCompare(endDate(b)));
  else if (params.sortBy === 'wind') events.sort((a, b) => (b.historical_peak_wind_kmh ?? -1) - (a.historical_peak_wind_kmh ?? -1));
  else if (params.sortBy === 'distance') events.sort((a, b) => a.closest_approach_km - b.closest_approach_km);
  else events.sort((a, b) => endDate(b).localeCompare(endDate(a)));
  const totalPages = Math.max(1, Math.ceil(events.length / params.pageSize));
  const page = Math.min(Math.max(1, params.page), totalPages);
  const analogs = events.slice((page - 1) * params.pageSize, page * params.pageSize);
  return {
    timestamp: new Date().toISOString(),
    region_target: snapshot.regionKey,
    source: 'Simulator training dataset',
    source_url: '',
    total_historical_events_analyzed: snapshot.historyEvents.length,
    page,
    page_size: params.pageSize,
    total_events: snapshot.historyEvents.length,
    matching_events: events.length,
    total_pages: totalPages,
    historical_analogs: analogs,
    available_hazards: scenario ? [scenario.hazardId] : [],
    hazards_with_records: scenario ? [scenario.hazardId] : [],
    history_coverage: { complete: true, note: '[SIMULATED] Fictional drill history.' },
  };
}

export function simDispatchChat(query: string): DispatchChatResponse {
  const snapshot = getSimSnapshot();
  const zone = getSimZone(snapshot.zoneId);
  const scenario = getSimScenario(snapshot.scenarioId);
  if (!zone || !scenario) throw new Error('Simulator Mode is not active.');
  const shelter = zone.shelters[0];
  return {
    text: simDispatchReply(query, zone, scenario).text,
    verifiedRoute: {
      origin: 'Drill staging post (sim)',
      destination: shelter.name,
      clearanceStatus: 'CAUTION_RESTRICTED',
      waterDepth: 'Simulated: not measured',
      recommendedPath: `[SIMULATED] Fictional drill route to ${shelter.name}. Not a verified real route.`,
      waypoints: [zone.places[0].name, shelter.name],
      sensorVerification: '[SIMULATED] No live sensors in Simulator Mode.',
      validityWindow: 'Drill session only',
    },
  };
}
