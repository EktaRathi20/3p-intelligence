// Pure helpers for Region Management geography defaults.
// Mirrors Backend/services/geo_validation.py defaults on the client.

export function slugToken(name: string, length = 3): string {
  const folded = (name || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "");
  const cleaned = folded.replace(/[^A-Za-z]/g, "").toUpperCase();
  if (!cleaned) return "X".repeat(length);
  if (cleaned.length <= length) return cleaned;
  const consonants = cleaned.replace(/[AEIOU]/g, "");
  if (consonants.length >= length) return consonants.slice(0, length);
  return cleaned.slice(0, length);
}

export function buildDefaultRegionCode(
  countryCode: string,
  stateCode?: string | null,
  cityName?: string | null,
): string {
  const parts = [(countryCode || "XX").trim().toUpperCase() || "XX"];
  const state = (stateCode || "").trim().toUpperCase();
  if (state) parts.push(state);
  if (cityName && cityName.trim()) parts.push(slugToken(cityName));
  return parts.join("-");
}

export function normalizeRegionCode(value: string): string {
  return (value || "").trim().toUpperCase();
}

export function isValidRegionCode(value: string): boolean {
  const normalized = normalizeRegionCode(value);
  if (normalized.length < 2 || normalized.length > 24) return false;
  return /^[A-Z0-9][A-Z0-9\-_]{0,22}[A-Z0-9]$/.test(normalized);
}

export function formatGeoBreadcrumb(region: {
  countryName?: string | null;
  countryCode?: string | null;
  stateName?: string | null;
  cityName?: string | null;
}): string {
  const parts = [
    region.cityName,
    region.stateName,
    region.countryName || region.countryCode,
  ].filter((part): part is string => !!part && part.trim().length > 0);
  return parts.join(" · ");
}
