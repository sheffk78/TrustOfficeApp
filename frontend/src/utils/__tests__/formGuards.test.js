// Regression suite for utils/formGuards — TICKET-20261001-CLIENT-GUARDS.
// These validators mirror backend pydantic rules; if one of these tests and a
// backend test disagree, the backend wins and these must be updated.
import {
  isValidEmail,
  isValidEin,
  isValidMonthDay,
  isNonNegativeNumber,
  isValidGrantMonths,
  validateTrustCreateForm,
  validateTrustUpdateForm,
  validateScheduleAForm,
} from '../formGuards';

const CLEAN_TRUST_CREATE = {
  name: 'Smith Family Trust',
  jurisdiction: 'TX',
  ein: '',
  tax_year_end_month: '',
  tax_year_end_day: '',
};

const CLEAN_TRUST_UPDATE = {
  ...CLEAN_TRUST_CREATE,
  successor_trustee_email: 'heir@example.com',
  secondary_successor_trustee_email: '',
  trust_protector_email: 'protector@example.com',
  attorney_email: 'law@firm.com',
  cpa_email: 'cpa@accounting.com',
  financial_advisor_email: '',
};

const TRUST_EMAIL_CASES = [
  ['successor_trustee_email', 'successor trustee'],
  ['secondary_successor_trustee_email', 'secondary successor trustee'],
  ['trust_protector_email', 'trust protector'],
  ['attorney_email', 'attorney'],
  ['cpa_email', 'CPA'],
  ['financial_advisor_email', 'financial advisor'],
];

describe('isValidEmail', () => {
  test.each([
    ['colleague@example.com', true],
    [' btudsbury@fastmail.com ', true], // trims
    ['jeff+kohler@sub.domain.co.uk', true],
    ['', false],
    ['   ', false],
    ['not-an-email', false],
    ['missing@tld', false],
    ['spaces in@address.com', false],
    ['@no-local-part.com', false],
  ])('%s -> %s', (input, expected) => {
    expect(isValidEmail(input)).toBe(expected);
  });
});

describe('isValidEin (explicit)', () => {
  test('accepts 9 digits with or without dash', () => {
    expect(isValidEin('12-3456789')).toBe(true);
    expect(isValidEin('123456789')).toBe(true);
    expect(isValidEin(' 123456789 ')).toBe(true);
  });
  test('rejects wrong digit counts and empties', () => {
    expect(isValidEin('12345678')).toBe(false);
    expect(isValidEin('1234567890')).toBe(false);
    expect(isValidEin('')).toBe(false);
    expect(isValidEin('   ')).toBe(false);
    expect(isValidEin(null)).toBe(false);
  });
});

describe('isValidMonthDay', () => {
  test('accepts bounds and empties', () => {
    expect(isValidMonthDay(1, 31)).toBe(true);
    expect(isValidMonthDay(12, 1)).toBe(true);
    expect(isValidMonthDay('', '')).toBe(true); // unset = fine (not fiscal)
    expect(isValidMonthDay(null, null)).toBe(true);
    expect(isValidMonthDay('3', '31')).toBe(true); // numeric strings
  });
  test('rejects out-of-range and fractional', () => {
    expect(isValidMonthDay(0, 15)).toBe(false);
    expect(isValidMonthDay(13, 1)).toBe(false);
    expect(isValidMonthDay(2, 30)).toBe(true); // day bound is 1-31 by backend rule, not calendar-exact
    expect(isValidMonthDay(1.5, 3)).toBe(false);
  });
});

describe('isNonNegativeNumber', () => {
  test('empty = unset (allowed)', () => {
    expect(isNonNegativeNumber('')).toBe(true);
    expect(isNonNegativeNumber(null)).toBe(true);
    expect(isNonNegativeNumber('   ')).toBe(true);
  });
  test('numbers and numeric strings', () => {
    expect(isNonNegativeNumber('1200')).toBe(true);
    expect(isNonNegativeNumber('1200.50')).toBe(true);
    expect(isNonNegativeNumber(0)).toBe(true);
  });
  test('rejects negatives and garbage', () => {
    expect(isNonNegativeNumber('-5')).toBe(false);
    expect(isNonNegativeNumber('abc')).toBe(false);
    expect(isNonNegativeNumber('1,200')).toBe(false); // comma-formatted string
  });
});

describe('isValidGrantMonths', () => {
  test.each([
    ['1', true], ['3', true], ['6', true], ['12', true], [12, true],
    [0, false], [13, false], ['0', false], ['18', false], [NaN, false], ['abc', false],
  ])('%p -> %s', (input, expected) => {
    expect(isValidGrantMonths(input)).toBe(expected);
  });
});

describe('validateTrustCreateForm', () => {
  test('clean form passes', () => {
    expect(validateTrustCreateForm(CLEAN_TRUST_CREATE)).toBeNull();
  });
  test('rejects malformed EIN before name/jurisdiction', () => {
    expect(validateTrustCreateForm({ ...CLEAN_TRUST_CREATE, ein: '12345' })).toBe(
      'EIN must be 9 digits (format: XX-XXXXXXX).'
    );
  });
  test('rejects 9-digit EIN with stray character', () => {
    expect(validateTrustCreateForm({ ...CLEAN_TRUST_CREATE, ein: '12-34567O9' })).toBeTruthy();
  });
  test('rejects out-of-range tax month', () => {
    expect(validateTrustCreateForm({ ...CLEAN_TRUST_CREATE, tax_year_end_month: '13' })).toBeTruthy();
  });
  test('rejects missing name and jurisdiction', () => {
    expect(validateTrustCreateForm({ ...CLEAN_TRUST_CREATE, name: '  ' })).toBe('Trust name is required');
    expect(validateTrustCreateForm({ ...CLEAN_TRUST_CREATE, jurisdiction: '' })).toBe('Jurisdiction is required');
  });
  test('ignores contact emails (not fields on the create form)', () => {
    const form = { ...CLEAN_TRUST_CREATE, attorney_email: 'definitely not an email' };
    expect(validateTrustCreateForm(form)).toBeNull();
  });
});

describe('validateTrustUpdateForm', () => {
  test('clean form passes', () => {
    expect(validateTrustUpdateForm(CLEAN_TRUST_UPDATE)).toBeNull();
  });
  test.each(TRUST_EMAIL_CASES)('rejects bad %s', (field, who) => {
    const form = { ...CLEAN_TRUST_UPDATE, [field]: 'nope@nospace' };
    expect(validateTrustUpdateForm(form)).toBe(`The ${who} email doesn't look right — check it and try again.`);
  });
  test('rejects bad EIN', () => {
    expect(validateTrustUpdateForm({ ...CLEAN_TRUST_UPDATE, ein: '12345678' })).toBeTruthy();
  });
  test('rejects bad tax day', () => {
    expect(validateTrustUpdateForm({ ...CLEAN_TRUST_UPDATE, tax_year_end_day: '0' })).toBeTruthy();
  });
});

describe('validateScheduleAForm', () => {
  const CLEAN_ASSET = {
    category: 'real_property',
    description: 'Primary residence',
    identifier: '',
    approximate_value: '',
    date_conveyed: '2026-01-15',
  };
  test('clean form passes', () => {
    expect(validateScheduleAForm(CLEAN_ASSET)).toBeNull();
  });
  test('requires category', () => {
    expect(validateScheduleAForm({ ...CLEAN_ASSET, category: '' })).toBe('Choose a category for this asset');
  });
  test('requires description (server-required field)', () => {
    expect(validateScheduleAForm({ ...CLEAN_ASSET, description: '   ' })).toBe('Asset description is required');
  });
  test('rejects negative value', () => {
    expect(validateScheduleAForm({ ...CLEAN_ASSET, approximate_value: '-10' })).toBe(
      'Approximate value must be a number (0 or more)'
    );
  });
  test('rejects non-numeric value', () => {
    expect(validateScheduleAForm({ ...CLEAN_ASSET, approximate_value: 'about 5k' })).toBeTruthy();
  });
  test('rejects unparseable date', () => {
    expect(validateScheduleAForm({ ...CLEAN_ASSET, date_conveyed: 'not a date' })).toBe('Date Conveyed is not a valid date');
  });
});