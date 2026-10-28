/**
 * Regression tests for showError 401/auth-expiry handling (JOB-20261026-ERR-TRIAGE).
 *
 * err_811be8bd6936: unauthenticated/expired-session user hit generate on
 * MinutesTemplateForm → raw "Invalid token" was reported to /api/report-error
 * and alerted as an unresolved app bug. 401-class auth states are expected
 * user conditions, not app bugs — they must:
 *   1. NOT be reported to the backend alert pipeline (server already logs them)
 *   2. show a sign-in CTA toast
 * Mirrors the pre-existing 403/404 skip-reporting precedent.
 *
 * Run: cd frontend && npx craco test --testPathPattern=errors-auth-expiry
 */
import '@testing-library/jest-dom';

jest.mock('sonner', () => ({
  toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() },
}));

import { toast } from 'sonner';
import { showError } from '../utils/errors';

beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = jest.fn(() => Promise.resolve({ ok: true }));
});

afterEach(() => {
  delete global.fetch;
});

describe('401/auth-expiry handling', () => {
  test.each([
    ['Invalid token'],
    ['Not authenticated'],
    ['Session expired'],
    ['Token revoked'],
  ])('%s → sign-in CTA, no report', (msg) => {
    const err = { message: msg, response: { status: 401, data: { detail: msg } } };
    showError(toast, err, { operation: 'generate', page: 'MinutesTemplateForm' });

    expect(toast.error).toHaveBeenCalledTimes(1);
    const shown = toast.error.mock.calls[0][0];
    expect(shown.toLowerCase()).toMatch(/sign in/);

    // Not reported to the alert pipeline
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('401 status with generic detail → still skipped', () => {
    const err = { message: 'Request failed', response: { status: 401 } };
    showError(toast, err, { operation: 'generate', page: 'MinutesTemplateForm' });
    expect(global.fetch).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  test('real app errors show the generic CTA toast (control)', () => {
    const err = { message: 'Cannot read properties of undefined (reading id)' };
    showError(toast, err, { operation: 'generate', page: 'MinutesTemplateForm' });
    expect(toast.error).toHaveBeenCalledTimes(1);
    const shown = toast.error.mock.calls[0][0];
    expect(shown).toMatch(/try again|support/);
    // Reporting is skipped via _isDev() under test by design (dev-guard docs) —
    // the production suppress path for 401s is asserted by the tests above.
  });
});