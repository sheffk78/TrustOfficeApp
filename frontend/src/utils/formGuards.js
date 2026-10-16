// Shared pre-submit form guards (TICKET-20261001-CLIENT-GUARDS).
//
// Goal: bad form input never leaves the page. The backend's validation is
// correct and stays the source of truth — these guards exist so the common
// client-bad-input cases (invalid email, malformed EIN, empty required text,
// out-of-range numbers) are caught BEFORE the network round-trip. That keeps
// the error-log free of 422 noise that isn't an application bug.
//
// Rules for consumers:
// - Show the problem at the field (inline) when the form has an error slot;
//   otherwise toast. Never report a caught-by-a-guard submit to the error log.
// - Guards are deliberately strict on FORMAT, lenient on CONTENT. Format rules
//   here mirror backend pydantic validators 1:1 so a guard pass means the
//   server will accept the field.

// Standard RFC-ish pragmatic email check — same shape the backend accepts.
// (Pydantic EmailStr rejects special-use TLDs like .local; anything that
// matches this regex and has a normal TLD passes server-side.)
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(value) {
  if (typeof value !== 'string') return false;
  const v = value.trim();
  if (!v || v.length > 254) return false;
  if (/\s/.test(v)) return false;
  return EMAIL_RE.test(v);
}

// Backend validator: EIN must be 9 digits once "-" is stripped; it normalizes
// to XX-XXXXXXX. Accept "123456789" or "12-3456789" (or any dash placement).
export function normalizeEin(value) {
  if (typeof value !== 'string') return '';
  return value.replace(/\D/g, '');
}

export function isValidEin(value) {
  if (typeof value !== 'string') return false;
  if (!value.trim()) return false; // empty string is NOT valid here — caller treats ''/null as "no EIN"
  return normalizeEin(value).length === 9;
}

// Generic non-negative numeric guard for money fields ("", "1200", "1200.50").
// Returns true only when the string parses to a finite number >= 0.
export function isNonNegativeNumber(value) {
  if (value === '' || value == null) return true; // empty = unset, caller decides if required
  if (typeof value === 'string' && !value.trim()) return true;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0;
}

// Trust year-end month/day — mirrors TrustCreate.validate_tax_fields bounds.
export function isValidMonthDay(month, day) {
  const m = month === '' || month == null ? null : Number(month);
  const d = day === '' || day == null ? null : Number(day);
  if (m != null && (!Number.isInteger(m) || m < 1 || m > 12)) return false;
  if (d != null && (!Number.isInteger(d) || d < 1 || d > 31)) return false;
  return true;
}

// Org-grant expiry, in months — backend hard-caps at 365 days.
export function isValidGrantMonths(months) {
  const m = Number(months);
  return Number.isFinite(m) && m >= 1 && m <= 12;
}

// ---------------------------------------------------------------------------
// Form-level validators (TICKET-20261001-CLIENT-GUARDS)
// Each returns an error STRING for the first failing rule, or null when the
// form is clean enough to submit. Message copy is user-facing (toast text).
// ---------------------------------------------------------------------------

const TRUST_CONTACT_EMAIL_FIELDS = [
  ['successor_trustee_email', 'successor trustee'],
  ['secondary_successor_trustee_email', 'secondary successor trustee'],
  ['trust_protector_email', 'trust protector'],
  ['attorney_email', 'attorney'],
  ['cpa_email', 'CPA'],
  ['financial_advisor_email', 'financial advisor'],
];

// Settings → Trust create dialog (newTrustData): no contact-email fields on
// this form; EIN format + tax month/day bounds mirror TrustCreate validators.
export function validateTrustCreateForm(form) {
  if ((form.ein || '').trim() && !isValidEin(form.ein)) {
    return 'EIN must be 9 digits (format: XX-XXXXXXX).';
  }
  if (!isValidMonthDay(form.tax_year_end_month, form.tax_year_end_day)) {
    return 'Tax year-end month must be 1–12 and day 1–31.';
  }
  if (!(form.name || '').trim()) return 'Trust name is required';
  if (!(form.jurisdiction || '').trim()) return 'Jurisdiction is required';
  return null;
}

// Settings → trust update (trustData): carries all contact emails.
export function validateTrustUpdateForm(form) {
  for (const [field, who] of TRUST_CONTACT_EMAIL_FIELDS) {
    const v = (form[field] || '').trim();
    if (v && !isValidEmail(v)) {
      return `The ${who} email doesn't look right — check it and try again.`;
    }
  }
  if ((form.ein || '').trim() && !isValidEin(form.ein)) {
    return 'EIN must be 9 digits (format: XX-XXXXXXX).';
  }
  if (!isValidMonthDay(form.tax_year_end_month, form.tax_year_end_day)) {
    return 'Tax year-end month must be 1–12 and day 1–31.';
  }
  return null;
}

// Schedule A asset dialog (ScheduleAItemCreate mirrors: category + description
// required, approximate_value >= 0, date_conveyed a real date when present).
export function validateScheduleAForm(form) {
  if (!form.category) return 'Choose a category for this asset';
  if (!(form.description || '').trim()) return 'Asset description is required';
  if (!isNonNegativeNumber(form.approximate_value)) {
    return 'Approximate value must be a number (0 or more)';
  }
  if (form.date_conveyed) {
    const parsed = new Date(form.date_conveyed);
    if (isNaN(parsed.getTime())) return 'Date Conveyed is not a valid date';
  }
  return null;
}