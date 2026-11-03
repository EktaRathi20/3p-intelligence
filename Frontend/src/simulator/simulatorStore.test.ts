/**
 * Maintained regression coverage for Simulator Mode (SIMULATION ONLY).
 *
 * Exercises the drill lifecycle the UI depends on: entering builds an
 * isolated snapshot, exiting restores the inactive state, drill records
 * stay in memory, and the headline alert carries the simulated-toast
 * contract (is_simulation + tier + SIMULATED title).
 *
 * Run with: npm run test:simulator
 */
import { afterEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  enterSimulator,
  exitSimulator,
  getSimSnapshot,
  isSimulatorActive,
  simCreateTask,
  simGetHistory,
  simListNotifications,
  simListTasks,
  simMarkNotificationRead,
  simUpdateTask,
} from './simulatorStore.ts';

afterEach(() => {
  if (isSimulatorActive()) exitSimulator();
});

describe('simulator drill lifecycle', () => {
  it('enters with a coherent isolated snapshot and exits back to inactive', () => {
    assert.equal(isSimulatorActive(), false);
    const selection = enterSimulator('cyclone-bay', 'cyclone-red');
    assert.equal(selection.active, true);
    assert.equal(selection.zone?.id, 'cyclone-bay');
    assert.equal(selection.scenario?.id, 'cyclone-red');
    assert.equal(isSimulatorActive(), true);

    const snapshot = getSimSnapshot();
    assert.equal(snapshot.regionKey, 'sim-cyclone-bay');
    assert.ok(snapshot.regionConfig.defaultRegionId);
    assert.ok(snapshot.tasks.length > 0);
    assert.ok(snapshot.notifications.length > 0);

    // Drill-entry toast contract: headline alert is flagged simulated.
    const headline = snapshot.alerts[0];
    assert.ok(headline);
    assert.equal(headline.is_simulation, true);
    assert.ok(headline.simulation_tier);
    assert.match(headline.title, /\[SIMULATED\]/);

    exitSimulator();
    assert.equal(isSimulatorActive(), false);
    assert.throws(() => getSimSnapshot(), /not active/);
  });

  it('rejects unknown zones or scenarios without activating', () => {
    assert.throws(() => enterSimulator('no-such-zone', 'cyclone-red'), /Unknown/);
    assert.throws(() => enterSimulator('cyclone-bay', 'no-such-scenario'), /Unknown/);
    assert.equal(isSimulatorActive(), false);
  });

  it('offers red, orange and green cyclone drills with matching severity', () => {
    const expected = [
      { scenario: 'cyclone-red', tier: 'RED', severity: 'critical' },
      { scenario: 'cyclone-orange', tier: 'ORANGE', severity: 'high' },
      { scenario: 'cyclone-green', tier: 'GREEN', severity: 'low' },
    ] as const;
    for (const { scenario, tier, severity } of expected) {
      enterSimulator('cyclone-bay', scenario);
      const snapshot = getSimSnapshot();
      assert.equal(snapshot.intelligence.hazard, 'cyclone');
      assert.equal(snapshot.alerts[0].simulation_tier, tier);
      assert.equal(snapshot.alerts[0].severity, severity);
      exitSimulator();
    }
  });

  it('green drill stays calm with no pending recovery workload', () => {
    enterSimulator('cyclone-bay', 'cyclone-green');
    const snapshot = getSimSnapshot();
    assert.ok(snapshot.tasks.length > 0);
    assert.ok(snapshot.tasks.every((task) => task.status === 'Submitted'));
    assert.equal(snapshot.assessments.length, 0);
    assert.equal(snapshot.damages.length, 0);
    assert.equal(snapshot.expenses.length, 0);
  });

  it('rebuilds a fresh snapshot on every entry (no drill-to-drill leaks)', () => {
    enterSimulator('cyclone-bay', 'cyclone-orange');
    const before = simListTasks().length;
    simCreateTask({
      title: '[SIMULATED] Temporary drill task',
      department: 'NDRF',
      location: 'Port Nimbus (SIMULATED)',
      priority: 'Low',
      assigneeUserId: 'sim-officer-3',
    });
    assert.equal(simListTasks().length, before + 1);
    exitSimulator();

    enterSimulator('cyclone-bay', 'cyclone-orange');
    assert.equal(simListTasks().length, before);
  });
});

describe('simulated workflow records', () => {
  it('task assignment notifies the drill inbox; reports and read states update', () => {
    enterSimulator('cyclone-bay', 'cyclone-red');
    const unreadBefore = simListNotifications().unread;

    const task = simCreateTask({
      title: '[SIMULATED] Drill boat staging',
      department: 'NDRF',
      location: 'Port Nimbus (SIMULATED)',
      priority: 'High',
      assigneeUserId: 'sim-officer-3',
      notifyAssignee: true,
    });
    assert.equal(task.status, 'Assigned');
    assert.match(task.assigneeName, /SIMULATED/);

    const inbox = simListNotifications();
    assert.equal(inbox.unread, unreadBefore + 1);
    assert.equal(inbox.notifications[0].taskId, task.id);
    assert.match(inbox.notifications[0].message, /\[SIMULATED\]/);

    const updated = simUpdateTask(task.id, {
      status: 'Submitted',
      progress: 100,
      report: { text: '[SIMULATED] Drill complete.', peopleAssisted: 12, locationNote: 'Pier (sim)' },
    });
    assert.equal(updated.reports.length, 1);
    assert.equal(updated.reports[0].peopleAssisted, 12);

    const note = simMarkNotificationRead(inbox.notifications[0].id);
    assert.equal(note.read, true);
    assert.equal(simListNotifications().unread, unreadBefore);
  });

  it('simulated history paginates, searches, and sorts', () => {
    enterSimulator('cyclone-bay', 'cyclone-green');
    const page = simGetHistory({ page: 1, pageSize: 2, search: '', sortBy: 'newest' });
    assert.equal(page.historical_analogs.length, 2);
    assert.equal(page.total_events, 3);
    assert.match(page.source, /Simulator/);

    const searched = simGetHistory({ page: 1, pageSize: 10, search: '2021', sortBy: 'newest' });
    assert.equal(searched.matching_events, 1);

    const sorted = simGetHistory({ page: 1, pageSize: 10, search: '', sortBy: 'distance' });
    const kms = sorted.historical_analogs.map((event) => event.closest_approach_km);
    assert.deepEqual(kms, [...kms].sort((a, b) => a - b));
  });
});
