/**
 * Safe date formatting utilities — wraps date-fns format/parseISO in try/catch
 * to prevent RangeError: Invalid time value from crashing React renders.
 *
 * Usage:
 *   import { safeFormatDate } from '@/utils/safeDate';
 *   safeFormatDate(isoString, 'MMM d, yyyy')  // returns formatted date or raw string
 */
import { format, parseISO } from 'date-fns';

/**
 * Safely format an ISO date string. Falls back to the raw value (or a custom
 * fallback) when the date can't be parsed, instead of throwing RangeError.
 *
 * @param {string|null|undefined} isoDate - ISO date string
 * @param {string} fmt - date-fns format string (default 'MMM d, yyyy')
 * @param {string} fallback - value to return if date is falsy (default '')
 * @returns {string} Formatted date, raw string on parse error, or fallback
 */
export function safeFormatDate(isoDate, fmt = 'MMM d, yyyy', fallback = '') {
  if (!isoDate) return fallback;
  try {
    return format(parseISO(isoDate), fmt);
  } catch {
    return isoDate;
  }
}

/**
 * Safely parse an ISO date string into a Date object. Returns undefined on
 * parse failure instead of throwing.
 *
 * @param {string|null|undefined} isoDate
 * @returns {Date|undefined}
 */
export function safeParseISO(isoDate) {
  if (!isoDate) return undefined;
  try {
    return parseISO(isoDate);
  } catch {
    return undefined;
  }
}