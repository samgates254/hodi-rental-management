/** Integer minor-unit helpers. Never use binary floating point for money. */

const SAFE = Number.MAX_SAFE_INTEGER;

export function formatMinor(
  minor: number | null | undefined,
  currency = "KES",
  options?: { trailingZeros?: boolean },
): string {
  if (minor == null || !Number.isSafeInteger(Number(minor))) return "—";
  const value = Number(minor);
  const sign = value < 0 ? "-" : "";
  const absolute = Math.abs(value);
  const whole = Math.trunc(absolute / 100);
  const fraction = absolute % 100;
  const body = whole.toLocaleString("en-KE");
  const trailingZeros = options?.trailingZeros !== false;
  if (!trailingZeros && fraction === 0) return `${sign}${currency} ${body}`;
  return `${sign}${currency} ${body}.${String(fraction).padStart(2, "0")}`;
}

/** Exact major-unit string. Empty when the cent value is not a safe integer. */
export function centsToDecimal(minor: number): string {
  if (!Number.isSafeInteger(minor)) return "";
  const sign = minor < 0 ? "-" : "";
  const absolute = Math.abs(minor);
  const whole = Math.trunc(absolute / 100);
  const fraction = absolute % 100;
  return `${sign}${whole}.${String(fraction).padStart(2, "0")}`;
}

/** Parse a shilling amount typed by a person. Rejects more than two decimal places. */
export function shillingsToCents(raw: string): number | undefined {
  const trimmed = raw.trim().replace(/,/g, "").replace(/ /g, "");
  if (!trimmed || /[eE]/.test(trimmed)) return undefined;
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return undefined;
  const [whole, frac = ""] = trimmed.split(".");
  if (whole.length > 15) return undefined;
  const cents = Number(whole) * 100 + Number((frac + "00").slice(0, 2));
  if (!Number.isSafeInteger(cents) || cents > SAFE) return undefined;
  return cents;
}

/** Whole Kenyan shillings only. Used where a rail, such as M-Pesa STK, rejects cents. */
export function wholeShillingsToCents(raw: string): number | undefined {
  const trimmed = raw.trim().replace(/,/g, "").replace(/ /g, "");
  if (!/^\d+$/.test(trimmed)) return undefined;
  return shillingsToCents(trimmed);
}

/** Whole-shilling payment for a cent balance. Undefined when cents remain. */
export function payableWholeShillings(cents: number): number | undefined {
  if (!Number.isSafeInteger(cents) || cents <= 0 || cents % 100 !== 0) return undefined;
  return cents / 100;
}

/** Even split into whole shillings. Undefined for odd shillings or leftover cents. */
export function payableHalfShillings(cents: number): number | undefined {
  const whole = payableWholeShillings(cents);
  if (whole == null || whole < 2 || whole % 2 !== 0) return undefined;
  return whole / 2;
}

export function minorToShillingsInput(minor: number): string {
  if (!Number.isSafeInteger(minor)) return "";
  const sign = minor < 0 ? "-" : "";
  const absolute = Math.abs(minor);
  const whole = Math.trunc(absolute / 100);
  const fraction = absolute % 100;
  return fraction
    ? `${sign}${whole}.${String(fraction).padStart(2, "0")}`
    : `${sign}${whole}`;
}
