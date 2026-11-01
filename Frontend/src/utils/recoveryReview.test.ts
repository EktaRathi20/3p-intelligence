import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  canReadAssessments,
  canSubmitDamage,
  canSubmitExpense,
  displayCount,
  formatFigureValue,
  isEditableFigureKey,
  isRole1Assessor,
  isRole2Planner,
  isRole3Field,
  isRole4Reviewer,
  statusLabel,
} from './recoveryReview.ts';
import type { AuthUser } from '@/types';

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user_4',
    name: 'Ananya Patel',
    email: 'ananya.demo@example.com',
    roleId: 'role_4',
    roleName: 'Insurance Recovery Officer',
    roleLevel: 4,
    ...overrides,
  };
}

describe('isRole4Reviewer', () => {
  it('accepts the Insurance Recovery Officer by level, id, or name', () => {
    assert.equal(isRole4Reviewer(user()), true);
    assert.equal(isRole4Reviewer(user({ roleLevel: 0 })), true);
    assert.equal(
      isRole4Reviewer(user({ roleId: 'x', roleLevel: 0, roleName: 'Recovery Officer' })),
      true,
    );
  });

  it('rejects other roles and unknown sessions', () => {
    assert.equal(isRole4Reviewer(user({ roleId: 'role_3', roleName: 'Field Operations Officer', roleLevel: 3 })), false);
    assert.equal(isRole4Reviewer(null), false);
    assert.equal(isRole4Reviewer(undefined), false);
  });
});

describe('canReadAssessments', () => {
  it('allows Role 4 and Role 1 oversight', () => {
    assert.equal(canReadAssessments(user()), true);
    assert.equal(
      canReadAssessments(user({ roleId: 'role_1', roleName: 'Disaster Assessment Officer', roleLevel: 1 })),
      true,
    );
  });

  it('denies field and unknown sessions', () => {
    assert.equal(canReadAssessments(user({ roleId: 'role_3', roleName: 'Field Operations Officer', roleLevel: 3 })), false);
    assert.equal(canReadAssessments(null), false);
  });
});

describe('formatFigureValue', () => {
  it('formats INR and people counts, keeps unknown honest', () => {
    assert.equal(formatFigureValue(150000, 'INR'), 'Rs.1,50,000');
    assert.equal(formatFigureValue(2200, 'people'), '2,200 people');
    assert.equal(formatFigureValue(null, 'INR'), 'Unknown');
    assert.equal(formatFigureValue(undefined, 'people'), 'Unknown');
  });
});

describe('statusLabel', () => {
  it('labels assessment states', () => {
    assert.equal(statusLabel('approved'), 'Government Approved');
    assert.equal(statusLabel('rejected'), 'Rejected');
    assert.equal(statusLabel('pending_review'), 'Pending Review');
  });
});

describe('displayCount', () => {
  it('never reports a failed load as zero', () => {
    assert.equal(displayCount({ loading: true, error: null, count: 0 }), '…');
    assert.equal(displayCount({ loading: false, error: 'boom', count: 0 }), '—');
    assert.equal(displayCount({ loading: false, error: null, count: 0 }), 0);
    assert.equal(displayCount({ loading: false, error: null, count: 5 }), 5);
  });
});

describe('role helpers', () => {
  it('matches Roles 1-3 by level, id, or name', () => {
    assert.equal(isRole1Assessor(user({ roleId: 'role_1', roleName: 'Disaster Assessment Officer', roleLevel: 1 })), true);
    assert.equal(isRole1Assessor(user({ roleId: 'x', roleLevel: 0, roleName: 'Disaster Assessment' })), true);
    assert.equal(isRole2Planner(user({ roleId: 'role_2', roleName: 'Operations Planner', roleLevel: 2 })), true);
    assert.equal(isRole3Field(user({ roleId: 'role_3', roleName: 'Field Operations Officer', roleLevel: 3 })), true);
    assert.equal(isRole1Assessor(user()), false);
    assert.equal(isRole2Planner(null), false);
    assert.equal(isRole3Field(undefined), false);
  });
});

describe('canSubmitDamage', () => {
  it('allows Roles 1, 3, and 4 only', () => {
    assert.equal(canSubmitDamage(user()), true);
    assert.equal(
      canSubmitDamage(user({ roleId: 'role_1', roleName: 'Disaster Assessment Officer', roleLevel: 1 })),
      true,
    );
    assert.equal(
      canSubmitDamage(user({ roleId: 'role_3', roleName: 'Field Operations Officer', roleLevel: 3 })),
      true,
    );
    assert.equal(
      canSubmitDamage(user({ roleId: 'role_2', roleName: 'Operations Planner', roleLevel: 2 })),
      false,
    );
    assert.equal(canSubmitDamage(null), false);
  });
});

describe('canSubmitExpense', () => {
  it('allows Roles 2, 3, and 4 only', () => {
    assert.equal(canSubmitExpense(user()), true);
    assert.equal(
      canSubmitExpense(user({ roleId: 'role_2', roleName: 'Operations Planner', roleLevel: 2 })),
      true,
    );
    assert.equal(
      canSubmitExpense(user({ roleId: 'role_3', roleName: 'Field Operations Officer', roleLevel: 3 })),
      true,
    );
    assert.equal(
      canSubmitExpense(user({ roleId: 'role_1', roleName: 'Disaster Assessment Officer', roleLevel: 1 })),
      false,
    );
    assert.equal(canSubmitExpense(undefined), false);
  });
});

describe('isEditableFigureKey', () => {
  it('accepts known figures and rejects unknown paths', () => {
    assert.equal(isEditableFigureKey('crop_loss_inr'), true);
    assert.equal(isEditableFigureKey('total_damage_inr'), true);
    assert.equal(isEditableFigureKey('figures.crop_loss_inr'), false);
    assert.equal(isEditableFigureKey('payout'), false);
  });
});
