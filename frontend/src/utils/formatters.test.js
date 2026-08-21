/**
 * TO-008 regression: EIN auto-formatting utility.
 *
 * formatEIN must:
 *   - strip all non-digit characters from input
 *   - cap at 9 digits
 *   - insert a hyphen after the second digit (XX-XXXXXXX format)
 *   - return partial formatted values as the user types
 *   - handle paste of already-formatted values without double-formatting
 *   - handle edge cases (empty, non-numeric, too long)
 *
 * rawEIN must:
 *   - return only digits, max 9
 *
 * Run: cd frontend && npx craco test --testPathPattern=formatters
 */

import { formatEIN, rawEIN } from '@/utils/formatters';

describe('TO-008: formatEIN utility', () => {
  // ── Typing character-by-character ──────────────────────────
  it('formats single digit as just the digit (no hyphen)', () => {
    expect(formatEIN('1')).toBe('1');
  });

  it('formats two digits without hyphen', () => {
    expect(formatEIN('12')).toBe('12');
  });

  it('inserts hyphen after second digit when third is typed', () => {
    expect(formatEIN('123')).toBe('12-3');
  });

  it('formats partial EIN mid-typing: 1234567 → 12-34567', () => {
    expect(formatEIN('1234567')).toBe('12-34567');
  });

  it('formats complete 9-digit EIN as XX-XXXXXXX', () => {
    expect(formatEIN('123456789')).toBe('12-3456789');
  });

  // ── Paste of raw digits ────────────────────────────────────
  it('handles paste of raw 9 digits', () => {
    expect(formatEIN('987654321')).toBe('98-7654321');
  });

  it('handles paste of raw 5 digits', () => {
    expect(formatEIN('12345')).toBe('12-345');
  });

  // ── Paste of already-formatted value (idempotent) ─────────
  it('does not double-format an already-formatted EIN', () => {
    expect(formatEIN('12-3456789')).toBe('12-3456789');
  });

  it('does not double-format partial already-formatted EIN', () => {
    expect(formatEIN('12-345')).toBe('12-345');
  });

  // ── Deletion (backspace through hyphen) ───────────────────
  it('rebuilds format after deletion: 12-3456 → 12-3456 (still formatted)', () => {
    // Simulates user backspacing from "12-34567" to "12-3456"
    expect(formatEIN('12-3456')).toBe('12-3456');
  });

  it('removes hyphen when backspaced to 2 digits', () => {
    // Simulates user backspacing from "12-3" to "12"
    expect(formatEIN('12')).toBe('12');
  });

  it('handles deletion to empty string', () => {
    expect(formatEIN('')).toBe('');
  });

  // ── Edge cases ─────────────────────────────────────────────
  it('strips non-numeric characters (letters, spaces, special chars)', () => {
    expect(formatEIN('12-34-56-78-9')).toBe('12-3456789');
    expect(formatEIN('12 3456789')).toBe('12-3456789');
    expect(formatEIN('12a3456b789c')).toBe('12-3456789');
    expect(formatEIN('(12)3456789')).toBe('12-3456789');
  });

  it('caps at 9 digits when more are entered', () => {
    expect(formatEIN('123456789012345')).toBe('12-3456789');
  });

  it('caps at 9 digits when more are pasted with formatting', () => {
    expect(formatEIN('12-3456-789-0123')).toBe('12-3456789');
  });

  it('returns empty string for all-non-numeric input', () => {
    expect(formatEIN('abcdef')).toBe('');
    expect(formatEIN('---')).toBe('');
  });

  it('returns empty string for null/undefined input', () => {
    expect(formatEIN(null)).toBe('');
    expect(formatEIN(undefined)).toBe('');
  });

  it('handles string with only 1 digit', () => {
    expect(formatEIN('5')).toBe('5');
  });

  it('handles string with exactly 3 digits', () => {
    expect(formatEIN('999')).toBe('99-9');
  });
});

describe('TO-008: rawEIN utility', () => {
  it('returns only digits from formatted EIN', () => {
    expect(rawEIN('12-3456789')).toBe('123456789');
  });

  it('returns only digits from raw EIN', () => {
    expect(rawEIN('123456789')).toBe('123456789');
  });

  it('strips letters and special characters', () => {
    expect(rawEIN('12a3456b789c')).toBe('123456789');
    expect(rawEIN('(12) 345-6789')).toBe('123456789');
  });

  it('caps at 9 digits', () => {
    expect(rawEIN('123456789012345')).toBe('123456789');
  });

  it('returns empty string for non-numeric input', () => {
    expect(rawEIN('abcdef')).toBe('');
    expect(rawEIN('---')).toBe('');
  });

  it('returns empty string for null/undefined', () => {
    expect(rawEIN(null)).toBe('');
    expect(rawEIN(undefined)).toBe('');
  });

  it('returns partial digits from partial formatted EIN', () => {
    expect(rawEIN('12-345')).toBe('12345');
    expect(rawEIN('12')).toBe('12');
  });
});
