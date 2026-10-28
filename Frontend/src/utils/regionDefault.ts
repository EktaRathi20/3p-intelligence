import type { Region } from '../services/regionApi';

export function normalizeRegionKey(value: string | null | undefined): string {
  return (value ?? '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

export function resolveDefaultRegionKey(
  records: Region[],
  defaultRegionId: string | null | undefined,
  availableKeys: string[],
): string | null {
  if (!defaultRegionId || availableKeys.length === 0) return null;
  const record = records.find((item) => item.id === defaultRegionId);
  if (!record || record.active === false) return null;
  const normalized = new Map(availableKeys.map((key) => [normalizeRegionKey(key), key]));
  const candidates = [record.code, record.id, record.name, record.cityName, record.stateName];
  for (const candidate of candidates) {
    const normalizedCandidate = normalizeRegionKey(candidate);
    if (!normalizedCandidate) continue;
    const hit = normalized.get(normalizedCandidate);
    if (hit) return hit;
  }
  return null;
}
