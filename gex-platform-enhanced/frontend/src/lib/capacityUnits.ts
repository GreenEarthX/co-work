export const CAPACITY_DAYS_PER_YEAR = 365;
export const ANNUAL_CAPACITY_ROUNDING_STEP = 10;

export const CAPACITY_UNITS = ["MTPD", "MT/yr"] as const;
export type CapacityUnit = (typeof CAPACITY_UNITS)[number];

function finiteVolume(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

export function roundAnnualCapacityMtYr(value: number): number {
  const volume = finiteVolume(value);
  return Math.ceil(volume / ANNUAL_CAPACITY_ROUNDING_STEP) * ANNUAL_CAPACITY_ROUNDING_STEP;
}

export function capacityMtpdToMtYr(mtpd: number): number {
  return roundAnnualCapacityMtYr(finiteVolume(mtpd) * CAPACITY_DAYS_PER_YEAR);
}

export function capacityMtYrToMtpd(mtYr: number): number {
  return Math.ceil(finiteVolume(mtYr) / CAPACITY_DAYS_PER_YEAR);
}

export function capacityDisplayValue(valueMtpd: number, unit: CapacityUnit): number {
  return unit === "MTPD" ? finiteVolume(valueMtpd) : capacityMtpdToMtYr(valueMtpd);
}

export function capacityInputToMtpd(value: number, unit: CapacityUnit): number {
  return unit === "MTPD" ? Math.ceil(finiteVolume(value)) : capacityMtYrToMtpd(value);
}
