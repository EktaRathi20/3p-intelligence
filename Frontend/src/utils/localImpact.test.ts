import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { resolveLocalHeadline } from './localImpact.ts';
import type { DisasterIntelligenceResponse } from '@/types/api';

function block(overrides: Record<string, unknown> = {}) {
  return {
    regional_warning_level: 'RED',
    regional_warning_status: 'active',
    local_impact_status: 'outside_footprint',
    local_impact_zone: 'GREEN',
    distance_to_footprint_km: 856.0,
    reason: 'Outside all verified footprints with calm local observations.',
    source: 'GDACS test',
    updated_at: '2026-10-29T00:00:00+00:00',
    ...overrides,
  };
}

function makeIntelligence(overrides: Record<string, unknown> = {}) {
  return {
    status: 'success',
    region: 'in-gj-srt',
    generated_at: '2026-10-29T00:00:00+00:00',
    data_quality: {
      ingestion_status: 'SUCCESS',
      telemetry_status: 'AVAILABLE',
      ingestion_error: null,
      telemetry_timestamp: null,
      sources: {},
    },
    current_conditions: {
      wind_speed_kmh: 10,
      pressure_hpa: 1012,
      storm_surge_meters: null,
      alert_status: 'OK',
    },
    risk_assessment: {
      level: 'RED',
      score: 0,
      factors: [],
      method: 'test',
      official_warning: true,
      screening_level: 'GREEN',
      warning_floor: 'RED',
      level_basis: 'official_warning',
      note: 'test',
    },
    risk_zones: [],
    official_warnings: [],
    local_impact: {
      verdict: 'outside_footprint',
      basis: [],
      distance_to_footprint_km: 856.0,
      geometry_source: 'GDACS CAP polygon',
    },
    historical_context: { primary_analog: null, historical_analogs: [] },
    demography: {},
    critical_places: {},
    insurance_summary: {
      status: 'UNAVAILABLE',
      trigger_met: null,
      trigger_threshold_m: 1.2,
      observed_water_depth_m: null,
      estimated_payout_cr: null,
      headline: 'test',
      coverage_focus: [],
    },
    ai_analysis: { summary: null, recommended_tasks: [], reasoning_context: [] },
    ...overrides,
  } as unknown as DisasterIntelligenceResponse;
}

describe('resolveLocalHeadline', () => {
  it('labels outside-footprint GREEN local impact separately from the regional RED warning', () => {
    const headline = resolveLocalHeadline(makeIntelligence({
      local_impact_assessment: block(),
    }));
    assert.equal(headline?.zone, 'GREEN');
    assert.equal(headline?.headline, 'No direct impact detected from the verified footprint.');
    assert.equal(headline?.shortLabel, 'No direct impact');
    assert.equal(headline?.regionalText, 'Regional official warning: RED');
  });

  it('labels inside-footprint RED local impact as direct', () => {
    const headline = resolveLocalHeadline(makeIntelligence({
      local_impact_assessment: block({
        local_impact_status: 'inside_footprint',
        local_impact_zone: 'RED',
        distance_to_footprint_km: 0.0,
      }),
    }));
    assert.equal(headline?.zone, 'RED');
    assert.equal(headline?.headline, 'Direct cyclone impact indicated.');
    assert.equal(headline?.shortLabel, 'Direct impact');
    assert.equal(headline?.regionalText, 'Regional official warning: RED');
  });

  it('labels elevated local zones as potential impact to monitor', () => {
    for (const zone of ['ORANGE', 'YELLOW']) {
      const headline = resolveLocalHeadline(makeIntelligence({
        local_impact_assessment: block({ local_impact_zone: zone }),
      }));
      assert.equal(headline?.zone, zone);
      assert.equal(headline?.headline, 'Potential cyclone impact — monitor conditions.');
      assert.equal(headline?.shortLabel, 'Monitor');
    }
  });

  it('labels unknown local impact without claiming safety', () => {
    const headline = resolveLocalHeadline(makeIntelligence({
      local_impact_assessment: block({
        local_impact_status: 'uncertain',
        local_impact_zone: 'UNKNOWN',
        distance_to_footprint_km: null,
      }),
    }));
    assert.equal(headline?.headline, 'Unable to determine local impact.');
    assert.equal(headline?.shortLabel, 'Unknown');
  });

  it('reports expired regional warnings without a level', () => {
    const headline = resolveLocalHeadline(makeIntelligence({
      local_impact_assessment: block({
        regional_warning_level: null,
        regional_warning_status: 'expired',
      }),
    }));
    assert.equal(headline?.regionalText, 'Regional official warning: none active (expired)');
  });

  it('reports absent and unavailable regional warnings distinctly', () => {
    const none = resolveLocalHeadline(makeIntelligence({
      local_impact_assessment: block({
        regional_warning_level: null,
        regional_warning_status: 'none',
      }),
    }));
    assert.equal(none?.regionalText, 'No regional official warning');
    const unavailable = resolveLocalHeadline(makeIntelligence({
      local_impact_assessment: block({
        regional_warning_level: null,
        regional_warning_status: 'unavailable',
      }),
    }));
    assert.equal(unavailable?.regionalText, 'Regional warning source unavailable');
  });

  it('marks simulated assessments as not live', () => {
    const { local_impact_assessment: _dropped, ...withoutBlock } = makeIntelligence({
      local_impact_assessment: block(),
    });
    void _dropped;
    const headline = resolveLocalHeadline({
      ...withoutBlock,
      simulation: { tier: 'RED', label: 'RED zone scenario' },
    } as unknown as DisasterIntelligenceResponse);
    assert.equal(headline?.zone, 'RED');
    assert.match(headline?.headline ?? '', /Simulated RED scenario/);
    assert.equal(headline?.regionalText, 'No live regional warning (simulation)');
  });

  it('falls back to legacy fields when the contract block is missing', () => {
    const { local_impact_assessment: _dropped, ...legacy } = makeIntelligence({
      local_impact_assessment: block(),
    });
    void _dropped;
    const outside = resolveLocalHeadline(legacy as unknown as DisasterIntelligenceResponse);
    assert.equal(outside?.headline, 'No direct impact detected from the verified footprint.');
    assert.equal(outside?.regionalText, 'Regional official warning: RED');
  });

  it('returns null without a usable assessment', () => {
    assert.equal(resolveLocalHeadline(null), null);
    assert.equal(resolveLocalHeadline(undefined), null);
    assert.equal(
      resolveLocalHeadline({
        region: 'in-gj-srt',
        hazard: 'cyclone',
        status: 'not_configured',
        supported: false,
        message: 'not configured',
      }),
      null,
    );
  });
});
