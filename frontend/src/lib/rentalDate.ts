const RENTAL_BUSINESS_TIME_ZONE = "Africa/Nairobi";

function civilDayNumber(value: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (year < 1 || month < 1 || month > 12) return null;

  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthLengths = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (day < 1 || day > monthLengths[month - 1]) return null;

  const previousYear = year - 1;
  const daysBeforeYear = previousYear * 365 +
    Math.floor(previousYear / 4) -
    Math.floor(previousYear / 100) +
    Math.floor(previousYear / 400);
  const daysBeforeMonth = monthLengths.slice(0, month - 1).reduce((total, length) => total + length, 0);
  return daysBeforeYear + daysBeforeMonth + day - 1;
}

/** Return a rental business date without converting the instant to UTC first. */
export function rentalBusinessDate(at: Date = new Date()): string {
  if (Number.isNaN(at.getTime())) {
    throw new RangeError("A valid instant is required to determine the rental business date.");
  }

  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: RENTAL_BUSINESS_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(at);
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find(part => part.type === type)?.value;
  const year = value("year");
  const month = value("month");
  const day = value("day");

  if (!year || !month || !day) {
    throw new RangeError("The rental business date could not be derived from this instant.");
  }

  return `${year.padStart(4, "0")}-${month}-${day}`;
}

/**
 * Return due-date distance in calendar days: positive is not yet due,
 * zero is due today, and negative is overdue. Date-only values are never
 * interpreted as browser-local or UTC timestamps.
 */
export function daysUntilRentalDate(date: string | null | undefined, at: Date = new Date()): number | null {
  if (!date) return null;
  const dueDay = civilDayNumber(date);
  if (dueDay === null) return null;
  const today = civilDayNumber(rentalBusinessDate(at));
  if (today === null) return null;
  return dueDay - today;
}
