import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  backendCoversLocal,
  buildOperationalTaskFromDecision,
  effectiveRecommendation,
  isRole2Reviewer,
  normalizePriority,
  pendingReviewRecord,
  recommendationKey,
  recommendationLabel,
  resolveAssigneeId,
  reviewCounts,
  summarizeAssignments,
} from './taskReview.ts';
import type { DisasterRecommendedTask } from '@/types/api';
import type { AuthUser } from '@/types';
import type { OperationalTask, ReviewRecord } from './taskReview.ts';

function rec(overrides: Partial<DisasterRecommendedTask> = {}): DisasterRecommendedTask {
  return {
    department: 'NDRF',
    location: 'Ward 08',
    description: 'Pre-position rescue boats near the riverside.',
    priority: 'high',
    ...overrides,
  };
}

function decision(overrides: Partial<ReviewRecord> = {}): ReviewRecord {
  return { ...pendingReviewRecord(), ...overrides };
}

function task(overrides: Partial<OperationalTask> = {}): OperationalTask {
  return {
    id: 'AI-01',
    source: 'ai',
    sourceRef: 'AI-01',
    title: 'Pre-position rescue boats near the riverside.',
    department: 'NDRF',
    location: 'Ward 08',
    priority: 'High',
    team: 'NDRF',
    officer: null,
    instructions: '',
    deadline: '2026-10-31T14:00:00.000Z',
    createdAt: '2026-10-30T10:00:00.000Z',
    createdBy: 'Priya Verma',
    backendState: 'local',
    ...overrides,
  };
}

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user_2',
    name: 'Priya Verma',
    email: 'priya.demo@example.com',
    roleId: 'role_2',
    roleName: 'Operations Planner',
    roleLevel: 2,
    ...overrides,
  };
}

describe('normalizePriority', () => {
  it('maps known AI priority spellings onto the fixed scale', () => {
    assert.equal(normalizePriority('critical'), 'Critical');
    assert.equal(normalizePriority('CRITICAL'), 'Critical');
    assert.equal(normalizePriority('high'), 'High');
    assert.equal(normalizePriority('moderate'), 'Medium');
    assert.equal(normalizePriority('medium'), 'Medium');
    assert.equal(normalizePriority('low'), 'Low');
  });

  it('falls back to Medium for missing or unknown values', () => {
    assert.equal(normalizePriority(undefined), 'Medium');
    assert.equal(normalizePriority(null), 'Medium');
    assert.equal(normalizePriority(''), 'Medium');
    assert.equal(normalizePriority('immediate'), 'Medium');
  });
});

describe('recommendationKey / recommendationLabel', () => {
  it('builds stable per-region keys and officer-facing labels', () => {
    assert.equal(recommendationKey('in-gj-srt', 0), 'in-gj-srt#0');
    assert.equal(recommendationKey('in-gj-srt', 3), 'in-gj-srt#3');
    assert.equal(recommendationLabel(0), 'AI-01');
    assert.equal(recommendationLabel(11), 'AI-12');
  });
});

describe('effectiveRecommendation', () => {
  it('uses raw AI values when the officer has not edited them', () => {
    assert.deepEqual(effectiveRecommendation(rec(), null), {
      description: 'Pre-position rescue boats near the riverside.',
      department: 'NDRF',
      location: 'Ward 08',
      priority: 'High',
    });
  });

  it('prefers officer edits for display and assignment', () => {
    const effective = effectiveRecommendation(rec(), {
      description: 'Edited task.',
      department: 'Health & EMS',
      location: 'Ward 09',
      priority: 'Critical',
      instructions: 'Carry extra stretchers.',
    });
    assert.equal(effective.description, 'Edited task.');
    assert.equal(effective.department, 'Health & EMS');
    assert.equal(effective.location, 'Ward 09');
    assert.equal(effective.priority, 'Critical');
  });
});

describe('reviewCounts', () => {
  it('treats undecided recommendations as pending', () => {
    const counts = reviewCounts(
      {
        'r#0': decision({ status: 'accepted' }),
        'r#1': decision({ status: 'rejected' }),
      },
      ['r#0', 'r#1', 'r#2'],
    );
    assert.deepEqual(counts, { pending: 1, accepted: 1, rejected: 1 });
  });
});

describe('buildOperationalTaskFromDecision', () => {
  it('builds an assignment row from an accepted recommendation', () => {
    const built = buildOperationalTaskFromDecision({
      index: 0,
      rec: rec(),
      decision: decision({
        status: 'accepted',
        decidedAt: '2026-10-30T10:00:00.000Z',
        decidedBy: 'Priya Verma',
        team: 'NDRF',
        officer: 'Rahul Singh',
        deadline: '2026-10-31T14:00:00.000Z',
        instructions: 'Report every two hours.',
        backendState: 'local',
      }),
    });
    assert.equal(built?.id, 'AI-01');
    assert.equal(built?.source, 'ai');
    assert.equal(built?.team, 'NDRF');
    assert.equal(built?.officer, 'Rahul Singh');
    assert.equal(built?.deadline, '2026-10-31T14:00:00.000Z');
    assert.equal(built?.createdBy, 'Priya Verma');
    assert.equal(built?.backendState, 'local');
  });

  it('carries officer edits into the assignment row', () => {
    const built = buildOperationalTaskFromDecision({
      index: 1,
      rec: rec(),
      decision: decision({
        status: 'accepted',
        decidedAt: '2026-10-30T10:00:00.000Z',
        team: 'Health & EMS',
        edited: {
          description: 'Edited task.',
          department: 'Health & EMS',
          location: 'Ward 09',
          priority: 'Critical',
          instructions: 'Carry extra stretchers.',
        },
      }),
    });
    assert.equal(built?.id, 'AI-02');
    assert.equal(built?.title, 'Edited task.');
    assert.equal(built?.location, 'Ward 09');
    assert.equal(built?.priority, 'Critical');
    assert.equal(built?.instructions, 'Carry extra stretchers.');
  });

  it('returns null unless the recommendation was accepted', () => {
    assert.equal(buildOperationalTaskFromDecision({ index: 0, rec: rec(), decision: undefined }), null);
    assert.equal(
      buildOperationalTaskFromDecision({ index: 0, rec: rec(), decision: decision({ status: 'pending' }) }),
      null,
    );
    assert.equal(
      buildOperationalTaskFromDecision({
        index: 0,
        rec: rec(),
        decision: decision({ status: 'rejected', rejectionReason: 'Duplicate.' }),
      }),
      null,
    );
  });
});

describe('summarizeAssignments', () => {
  it('counts accepted, assigned, and awaiting-assignment work', () => {
    const summary = summarizeAssignments([
      task({ id: 'AI-01', team: 'NDRF' }),
      task({ id: 'M-01', source: 'manual', team: null }),
      task({ id: 'M-02', source: 'manual', team: '  ' }),
    ]);
    assert.deepEqual(summary, { total: 3, assigned: 1, awaitingAssignment: 2 });
  });
});

describe('backendCoversLocal', () => {
  it('matches AI records by region and recommendation ref', () => {
    const backend = { source: 'ai', sourceRef: 'AI-01', regionKey: 'surat', title: 'Old title', createdAt: '2026-10-30T10:00:00.000Z' } as const;
    assert.equal(backendCoversLocal(backend, { source: 'ai', sourceRef: 'AI-01', regionKey: 'surat', title: 'New title', createdAt: '2026-10-31T10:00:00.000Z' }), true);
    assert.equal(backendCoversLocal(backend, { source: 'ai', sourceRef: 'AI-02', regionKey: 'surat', title: 'Old title', createdAt: '2026-10-30T10:00:00.000Z' }), false);
    assert.equal(backendCoversLocal(backend, { source: 'ai', sourceRef: 'AI-01', regionKey: 'vizag', title: 'Old title', createdAt: '2026-10-30T10:00:00.000Z' }), false);
    assert.equal(backendCoversLocal(backend, { source: 'manual', sourceRef: null, regionKey: 'surat', title: 'Old title', createdAt: '2026-10-30T10:00:00.000Z' }), false);
  });

  it('matches manual records by title and timestamp', () => {
    const backend = { source: 'manual', sourceRef: null, regionKey: 'surat', title: 'Boat drill', createdAt: '2026-10-30T10:00:00.000Z' } as const;
    assert.equal(backendCoversLocal(backend, { source: 'manual', sourceRef: null, regionKey: 'vizag', title: 'Boat drill', createdAt: '2026-10-30T10:00:00.000Z' }), true);
    assert.equal(backendCoversLocal(backend, { source: 'manual', sourceRef: null, regionKey: 'surat', title: 'Other', createdAt: '2026-10-30T10:00:00.000Z' }), false);
  });
});

describe('resolveAssigneeId', () => {
  const roster = [
    { id: 'user_3', name: 'Rahul Singh' },
    { id: 'user_9', name: 'Asha Devi' },
  ];

  it('prefers the stored id, then name, then the roster default', () => {
    assert.equal(resolveAssigneeId(roster, 'user_9', 'Rahul Singh'), 'user_9');
    assert.equal(resolveAssigneeId(roster, 'user_missing', 'Asha Devi'), 'user_9');
    assert.equal(resolveAssigneeId(roster, null, null), 'user_3');
    assert.equal(resolveAssigneeId(roster, undefined, 'Unknown Name'), 'user_3');
  });

  it('returns null when no roster is loaded', () => {
    assert.equal(resolveAssigneeId([], 'user_3', 'Rahul Singh'), null);
  });
});

describe('isRole2Reviewer', () => {
  it('accepts the Operations Planner by level, id, or name', () => {
    assert.equal(isRole2Reviewer(user()), true);
    assert.equal(isRole2Reviewer(user({ roleId: 'other', roleName: 'Other' })), true);
    assert.equal(
      isRole2Reviewer(user({ roleLevel: 9, roleId: 'role_2', roleName: 'Other' })),
      true,
    );
    assert.equal(
      isRole2Reviewer(user({ roleLevel: 9, roleId: 'other', roleName: 'Senior Operations Planner' })),
      true,
    );
  });

  it('rejects other roles and unknown sessions', () => {
    assert.equal(isRole2Reviewer(null), false);
    assert.equal(isRole2Reviewer(undefined), false);
    assert.equal(
      isRole2Reviewer(user({ roleId: 'role_1', roleName: 'Disaster Assessment Officer', roleLevel: 1 })),
      false,
    );
    assert.equal(
      isRole2Reviewer(user({ roleId: 'role_3', roleName: 'Field Operations Officer', roleLevel: 3 })),
      false,
    );
  });
});
