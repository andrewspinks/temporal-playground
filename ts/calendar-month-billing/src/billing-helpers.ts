/**
 * Pure date math for monthly billing schedules.
 * Safe to import from workflow code — no Node.js APIs, no I/O.
 */

/** Returns the last day (1–31) of the given month. Month is 1-indexed (1=Jan, 12=Dec). */
export function lastDayOfMonth(year: number, month: number): number {
  // Day 0 of the following month equals the last day of the current month
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/**
 * Returns a Date for the last day of the month *after* `from`, at the given UTC hour.
 *
 * Example: from=2026-03-15 → returns 2026-04-30T09:00:00Z
 */
export function nextBillingDate(from: Date, hour = 9): Date {
  const year = from.getUTCFullYear();
  const month = from.getUTCMonth() + 1; // convert 0-indexed to 1-indexed

  let nextMonth = month + 1;
  let nextYear = year;
  if (nextMonth > 12) {
    nextMonth = 1;
    nextYear++;
  }

  const day = lastDayOfMonth(nextYear, nextMonth);
  return new Date(Date.UTC(nextYear, nextMonth - 1, day, hour, 0, 0, 0));
}
