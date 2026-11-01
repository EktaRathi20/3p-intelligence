import type {
  DisasterIntelligenceResponse,
  DisasterIntelligenceResult,
} from '@/types/api';

export type LocalImpactZone = 'RED' | 'ORANGE' | 'YELLOW' | 'GREEN' | 'UNKNOWN';

export interface LocalHeadline {
  zone: LocalImpactZone;
  headline: string;
  shortLabel: string;
  regionalText: string;
  reason: string | null;
}

type RiskAssessment = DisasterIntelligenceResponse['risk_assessment'];
type LocalImpact = DisasterIntelligenceResponse['local_impact'];

export function verdictLabel(verdict: string | null | undefined): string {
  switch (verdict) {
    case 'inside_footprint':
      return 'Inside footprint';
    case 'outside_footprint':
      return 'Outside footprint';
    case 'uncertain':
      return 'Uncertain';
    default:
      return 'Unavailable';
  }
}

export function formatImpactDistance(km: number | null | undefined): string {
  if (km === null || km === undefined || Number.isNaN(km)) return 'Unavailable';
  return `${km.toFixed(0)} km`;
}

export function formatWarningUpdated(iso: string | null | undefined): string {
  if (!iso || iso.length < 10) return 'Unavailable';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return 'Unavailable';
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
}

export function formatAffectedPopulation(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'Unavailable';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M people`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k people`;
  return `${value} people`;
}

const ZONES: ReadonlySet<string> = new Set(['RED', 'ORANGE', 'YELLOW', 'GREEN', 'UNKNOWN']);

function asZone(value: unknown): LocalImpactZone {
  if (typeof value === 'string' && ZONES.has(value.toUpperCase())) {
    return value.toUpperCase() as LocalImpactZone;
  }
  return 'UNKNOWN';
}

function zoneHeadline(zone: LocalImpactZone): { headline: string; shortLabel: string } {
  switch (zone) {
    case 'RED':
      return { headline: 'Direct cyclone impact indicated.', shortLabel: 'Direct impact' };
    case 'ORANGE':
    case 'YELLOW':
      return { headline: 'Potential cyclone impact — monitor conditions.', shortLabel: 'Monitor' };
    case 'GREEN':
      return { headline: 'No direct impact detected from the verified footprint.', shortLabel: 'No direct impact' };
    default:
      return { headline: 'Unable to determine local impact.', shortLabel: 'Unknown' };
  }
}

function legacyHeadline(
  assessment: RiskAssessment,
  localImpact: LocalImpact | null | undefined,
): LocalHeadline {
  const regionalText = assessment.warning_floor
    ? `Regional official warning: ${assessment.warning_floor}`
    : 'No regional official warning';
  const verdict = localImpact?.verdict;
  const screening = (assessment.screening_level ?? 'UNKNOWN').toUpperCase();
  if (verdict === 'inside_footprint' && asZone(assessment.level) !== 'UNKNOWN') {
    const zone = asZone(assessment.level);
    return { zone, ...zoneHeadline(zone), regionalText, reason: null };
  }
  if (verdict === 'outside_footprint' && screening === 'GREEN') {
    return { zone: 'GREEN', ...zoneHeadline('GREEN'), regionalText, reason: null };
  }
  if (screening === 'RED' || screening === 'ORANGE' || screening === 'YELLOW') {
    const zone = asZone(screening);
    return { zone, ...zoneHeadline(zone), regionalText, reason: null };
  }
  return { zone: 'UNKNOWN', ...zoneHeadline('UNKNOWN'), regionalText, reason: null };
}

/**
 * Resolve the ordinary-user local-impact headline from a disaster
 * intelligence response. Prefers the backend `local_impact_assessment`
 * contract; falls back to a best-effort mapping from the legacy
 * combined level and footprint verdict.
 * Returns null when no usable assessment exists.
 */
export function resolveLocalHeadline(
  intelligence: DisasterIntelligenceResult | null | undefined,
): LocalHeadline | null {
  if (!intelligence || !('risk_assessment' in intelligence)) return null;
  const block = intelligence.local_impact_assessment ?? null;
  if (!block) {
    return legacyHeadline(intelligence.risk_assessment, intelligence.local_impact ?? null);
  }
  const zone = asZone(block.local_impact_zone);
  const { headline, shortLabel } = zoneHeadline(zone);
  const level = block.regional_warning_level;
  let regionalText: string;
  if (block.regional_warning_status === 'active') {
    regionalText = level ? `Regional official warning: ${level}` : 'Regional official warning: active';
  } else if (block.regional_warning_status === 'expired') {
    regionalText = 'Regional official warning: none active (expired)';
  } else if (block.regional_warning_status === 'unavailable') {
    regionalText = 'Regional warning source unavailable';
  } else {
    regionalText = 'No regional official warning';
  }
  return { zone, headline, shortLabel, regionalText, reason: block.reason ?? null };
}
