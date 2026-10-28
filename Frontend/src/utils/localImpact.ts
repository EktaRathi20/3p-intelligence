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
