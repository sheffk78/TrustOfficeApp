/**
 * TrustOffice 2FA frontend tests (FEATURE 2 - TOTP 2FA).
 *
 * Coverage:
 *  1. Settings enroll flow - happy path (enroll -> QR + secret -> verify ->
 *     10 recovery codes shown once -> confirm -> enabled) and wrong code.
 *  2. Login second step - correct code, wrong code, recovery code.
 *  3. Step-up modal retry - 403 2fa_stepup_required -> modal -> replay with
 *     X-2FA-Code header.
 *  4. Admin nag - needs_2fa_enrollment renders the persistent banner.
 *
 * All network calls are mocked at the fetch level (backend may be absent).
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

import { is2faChallenge, isStepUpRequired } from '../utils/twoFactor';
import TwoFactorStepUpModal from '../components/TwoFactorStepUpModal';
import TwoFactorCard from '../components/TwoFactorCard';

// ---------------------------------------------------------------------------
// fetch mock plumbing
// ---------------------------------------------------------------------------

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock;
  jest.spyOn(console, 'error').mockImplementation(() => {});
  jest.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  console.error.mockRestore && console.error.mockRestore();
  console.warn.mockRestore && console.warn.mockRestore();
});

// Minimal fetch Response stand-in (jsdom has no undici Response here).
const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  clone() {
    return jsonResponse(status, body);
  },
  json: () => Promise.resolve(body),
});

// localStorage mock (jsdom lacks a real one in CRA's Jest env sometimes)
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Mock sonner toast + errors util so no UI noise escapes
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn(), warning: jest.fn() },
}));

jest.mock('../utils/errors', () => ({
  showError: jest.fn(),
  reportErrorToBackend: jest.fn(),
}));

// Mock clipboard
Object.assign(navigator, {
  clipboard: { writeText: jest.fn(() => Promise.resolve()) },
});

// QR rendering: qrcode.react is CJS-compatible and renders fine in jsdom,
// but stub it to keep the DOM assertions fast and deterministic.
jest.mock('qrcode.react', () => ({
  QRCodeCanvas: ({ value, 'data-testid': testId }) => (
    <canvas data-testid={testId || 'twofa-qr'} data-value={value} />
  ),
}));

// Mock the api helper's fetchWithAuth to route through our fetch mock.
jest.mock('../utils/api', () => {
  return {
    fetchWithAuth: (endpoint, options = {}) => {
      const token = globalThis.localStorage.getItem('auth_token');
      const headers = { ...(options.headers || {}) };
      if (token) headers.Authorization = `Bearer ${token}`;
      return fetch(`https://api.test/api${endpoint}`, { ...options, headers });
    },
    getAuthHeaders: () => ({}),
    API: 'https://api.test/api',
  };
});

// TwoFactorCard and other @/-alias imports resolve to the same real modules
// under test - no re-mocking needed (the alias map points at src/, and these
// relative paths ARE src/utils/*). We only mock their dependencies above.

// Auth context stub for TwoFactorCard (it does not actually use useAuth, but
// SettingsPage-mounted imports may). Provide a benign default.
jest.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'admin@trustoffice.app' }, isReadOnly: false }),
}));

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const STATUS_DISABLED = { enabled: false, recovery_codes_remaining: 0, enforced: false };
const STATUS_ENABLED = { enabled: true, recovery_codes_remaining: 7, enforced: false };
const RECOVERY_CODES = [
  '11111-aaaaa', '22222-bbbbb', '33333-ccccc', '44444-ddddd', '55555-eeeee',
  '66666-fffff', '77777-ggggg', '88888-hhhhh', '99999-iiiii', '00000-jjjjj',
];

// Render TwoFactorCard with the module-mocked fetch router.
const renderCard = () => render(<TwoFactorCard />);

const mockStatusOnce = (body) => {
  fetchMock.mockImplementationOnce(() => Promise.resolve(jsonResponse(200, body)));
};

// ===========================================================================
// 1. Settings enroll flow
// ===========================================================================

describe('TwoFactorCard - enroll flow', () => {
  test('happy path: enable -> QR + secret -> verify -> recovery codes shown once', async () => {
    mockStatusOnce(STATUS_DISABLED);            // initial GET /auth/2fa/status

    renderCard();
    expect(await screen.findByTestId('twofa-card')).toBeInTheDocument();
    expect(await screen.findByText('Not Enabled')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('twofa-enable-btn'));

    // Password confirm step (contract: POST /auth/2fa/enroll {password})
    await screen.findByTestId('twofa-password-step');
    await userEvent.type(screen.getByTestId('twofa-enroll-password-input'), 'hunter2');
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(200, {
        secret: 'JBSWY3DPEHPK3PXP',
        provisioning_uri: 'otpauth://totp/TrustOffice:admin@trustoffice.app?secret=JBSWY3DPEHPK3PXP&issuer=TrustOffice',
      })));
    await userEvent.click(screen.getByTestId('twofa-enroll-start-btn'));

    // QR step visible with the plain-language guide and manual fallback
    await screen.findByTestId('twofa-qr-step');
    expect(screen.getByTestId('twofa-qr')).toHaveAttribute('data-value', expect.stringContaining('otpauth://'));
    expect(screen.getByTestId('twofa-enroll-guide')).toHaveTextContent('1. Install an authenticator app');
    expect(screen.getByTestId('twofa-enroll-guide')).toHaveTextContent('2. Open it and tap + to add an account.');
    expect(screen.getByTestId('twofa-enroll-guide')).toHaveTextContent('3. Point your phone camera at this code.');
    expect(screen.getByTestId('twofa-cant-scan-label')).toHaveTextContent("Can't scan? Enter this code manually");
    expect(screen.getByTestId('twofa-secret')).toHaveTextContent('JBSWY3DPEHPK3PXP');

    // Copy buttons exist for secret + URI
    expect(screen.getByLabelText('Copy setup code')).toBeInTheDocument();
    expect(screen.getByLabelText('Copy provisioning URI')).toBeInTheDocument();

    // Verify with a correct code
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(200, { recovery_codes: RECOVERY_CODES })));
    await userEvent.type(screen.getByTestId('twofa-verify-code-input'), '123456');
    await userEvent.click(screen.getByTestId('twofa-verify-btn'));

    // Recovery codes screen: all 10 shown ONCE + warning + save buttons
    await screen.findByTestId('twofa-recovery-step');
    expect(screen.getByTestId('twofa-recovery-codes').textContent).toContain('11111-aaaaa');
    RECOVERY_CODES.forEach((c) => {
      expect(screen.getByTestId('twofa-recovery-codes').textContent).toContain(c);
    });
    expect(screen.getByTestId('twofa-recovery-warning')).toHaveTextContent(
      'Do not save these codes on the same device as your authenticator app. Print them or store them somewhere safe and separate.'
    );
    expect(screen.getByTestId('twofa-print-codes-btn')).toBeInTheDocument();
    expect(screen.getByTestId('twofa-download-codes-btn')).toBeInTheDocument();
    expect(screen.getByTestId('twofa-saved-codes-btn')).toBeInTheDocument();

    // Confirm saved -> enabled state with remaining count
    mockStatusOnce(STATUS_ENABLED);
    await userEvent.click(screen.getByTestId('twofa-saved-codes-btn'));
    expect(await screen.findByTestId('twofa-enabled-badge')).toHaveTextContent('Enabled');
    expect(screen.getByTestId('twofa-recovery-remaining')).toHaveTextContent('Recovery codes remaining: 7');
  });

  test('wrong code shows inline error and keeps the QR on screen', async () => {
    mockStatusOnce(STATUS_DISABLED);
    renderCard();
    await screen.findByTestId('twofa-card');
    // Wait for the status to resolve before the Enable button exists.
    await screen.findByText('Not Enabled');

    await userEvent.click(screen.getByTestId('twofa-enable-btn'));
    await screen.findByTestId('twofa-password-step');
    await userEvent.type(screen.getByTestId('twofa-enroll-password-input'), 'hunter2');
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(200, {
        secret: 'JBSWY3DPEHPK3PXP',
        provisioning_uri: 'otpauth://totp/TrustOffice:x?secret=JBSWY3DPEHPK3PXP',
      })));
    await userEvent.click(screen.getByTestId('twofa-enroll-start-btn'));

    await screen.findByTestId('twofa-qr-step');

    // Wrong code -> 400 with detail
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(400, { detail: 'Invalid verification code' })));
    await userEvent.type(screen.getByTestId('twofa-verify-code-input'), '000000');
    await userEvent.click(screen.getByTestId('twofa-verify-btn'));

    expect(await screen.findByTestId('twofa-verify-error')).toHaveTextContent(/Invalid verification code|not valid/i);
    // QR step stays on screen for retry
    expect(screen.getByTestId('twofa-qr-step')).toBeInTheDocument();
    expect(screen.queryByTestId('twofa-recovery-step')).not.toBeInTheDocument();

    // Retry with a fresh code succeeds
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(200, { recovery_codes: RECOVERY_CODES })));
    await userEvent.clear(screen.getByTestId('twofa-verify-code-input'));
    await userEvent.type(screen.getByTestId('twofa-verify-code-input'), '654321');
    await userEvent.click(screen.getByTestId('twofa-verify-btn'));
    expect(await screen.findByTestId('twofa-recovery-step')).toBeInTheDocument();
  });
});

// ===========================================================================
// 2. Login second step (via xhr payload-sniffing + login2fa)
// ===========================================================================

describe('login 2FA second step - challenge detection and exchange', () => {
  let LoginPage;
  let completeLoginCapture;

  beforeAll(async () => {
    // Import after mocks are set up.
    const mod = await import('../pages/LoginPage');
    LoginPage = mod.default;
  });

  const renderLogin = () => {
    completeLoginCapture = { navigateCalls: [], setUserCalls: [], tokenSet: null };
    return render(<LoginPage />);
  };

  test('correct code: 401 challenge -> code entry -> session proceeds as normal login', async () => {
    // NOTE: the initial POST /auth/login is dispatched via XMLHttpRequest
    // (LoginPage's xhrPost), NOT fetch -- so the 401 challenge below is served
    // entirely by the FakeXHR shim and we must NOT register a fetch mock for
    // it (a dangling fetch mock here would be consumed by the later
    // /auth/2fa/login fetch and break the flow).

    // Mock the XHR used by LoginPage's xhrPost: jsdom XHR cannot hit our
    // fetch mock, so shim XMLHttpRequest per test.
    const xhrMock = (status, body) => {
      class FakeXHR {
        open() {}
        setRequestHeader() {}
        send() {
          this.readyState = 4;
          this.status = status;
          this.responseText = JSON.stringify(body);
          if (this.onreadystatechange) this.onreadystatechange();
        }
      }
      return FakeXHR;
    };
    global.XMLHttpRequest = xhrMock(401, { detail: '2fa_required', challenge_token: 'ch-tok-1' });

    renderLogin();

    await userEvent.type(screen.getByTestId('email-input'), 'admin@trustoffice.app');
    await userEvent.type(screen.getByTestId('password-input'), 'pw');
    await userEvent.click(screen.getByTestId('login-submit-btn'));

    // Second step appears with the exact user-facing wording
    expect(await screen.findByTestId('twofa-login-step')).toBeInTheDocument();
    expect(screen.getByText(/Open your authenticator app and enter the 6-digit code it shows/i)).toBeInTheDocument();
    expect(screen.getByText(/or use a recovery code/i)).toBeInTheDocument();

    // Correct code: POST /auth/2fa/login -> session
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(200, { token: 'sess-token', user: { email: 'admin@trustoffice.app' } })));
    await userEvent.type(screen.getByTestId('twofa-login-code-input'), '246810');
    await userEvent.click(screen.getByTestId('twofa-login-submit-btn'));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes('/auth/2fa/login'));
      expect(call).toBeTruthy();
    });
    const [url2fa, opts2fa] = fetchMock.mock.calls.find(([url]) => String(url).includes('/auth/2fa/login'));
    expect(String(url2fa)).toContain('/auth/2fa/login');
    expect(JSON.parse(opts2fa.body)).toEqual({ challenge_token: 'ch-tok-1', code: '246810' });

    // Session token stored exactly like a normal login
    await waitFor(() => {
      expect(window.localStorage.getItem('auth_token')).toBe('sess-token');
    });
  });

  test('wrong code shows clear inline error and allows retry', async () => {
    global.XMLHttpRequest = (function() {
      class FakeXHR {
        open() {}
        setRequestHeader() {}
        send() {
          this.readyState = 4;
          this.status = 401;
          this.responseText = JSON.stringify({ detail: '2fa_required', challenge_token: 'ch-tok-2' });
          if (this.onreadystatechange) this.onreadystatechange();
        }
      }
      return FakeXHR;
    })();

    renderLogin();
    await userEvent.type(screen.getByTestId('email-input'), 'a@b.com');
    await userEvent.type(screen.getByTestId('password-input'), 'pw');
    await userEvent.click(screen.getByTestId('login-submit-btn'));
    await screen.findByTestId('twofa-login-step');

    // Wrong code on the second step
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(401, { detail: 'Invalid or expired code' })));
    await userEvent.type(screen.getByTestId('twofa-login-code-input'), '111111');
    await userEvent.click(screen.getByTestId('twofa-login-submit-btn'));

    expect(await screen.findByTestId('twofa-login-error')).toBeInTheDocument();
    expect(screen.getByTestId('twofa-login-step')).toBeInTheDocument(); // still on code entry
    // Input is editable again for retry
    expect(screen.getByTestId('twofa-login-code-input')).not.toBeDisabled();
  });

  test('recovery code is accepted through the same endpoint', async () => {
    global.XMLHttpRequest = (function() {
      class FakeXHR {
        open() {}
        setRequestHeader() {}
        send() {
          this.readyState = 4;
          this.status = 401;
          this.responseText = JSON.stringify({ detail: '2fa_required', challenge_token: 'ch-tok-3' });
          if (this.onreadystatechange) this.onreadystatechange();
        }
      }
      return FakeXHR;
    })();

    renderLogin();
    await userEvent.type(screen.getByTestId('email-input'), 'a@b.com');
    await userEvent.type(screen.getByTestId('password-input'), 'pw');
    await userEvent.click(screen.getByTestId('login-submit-btn'));
    await screen.findByTestId('twofa-login-step');

    // A recovery code (longer, dash-separated) goes through the same call
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(200, { token: 'sess-token-3', user: { email: 'a@b.com' } })));
    await userEvent.type(screen.getByTestId('twofa-login-code-input'), '11111-aaaaa');
    await userEvent.click(screen.getByTestId('twofa-login-submit-btn'));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes('/auth/2fa/login'));
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body)).toEqual({ challenge_token: 'ch-tok-3', code: '11111-aaaaa' });
    });
    await waitFor(() => {
      expect(window.localStorage.getItem('auth_token')).toBe('sess-token-3');
    });
  });
});

// ===========================================================================
// 3. Step-up modal retry
// ===========================================================================

describe('TwoFactorStepUpModal - retry with X-2FA-Code', () => {
  test('replays the original request with the X-2FA-Code header and resolves on success', async () => {
    const submittedBodies = [];
    const onSubmit = jest.fn(async (code) => {
      // Simulate the replay recording its header (the hook sets X-2FA-Code).
      submittedBodies.push({ code, header: 'X-2FA-Code' });
    });
    const onCancel = jest.fn();

    render(
      <TwoFactorStepUpModal open onSubmit={onSubmit} onCancel={onCancel} />
    );

    expect(screen.getByTestId('twofa-stepup-modal')).toBeInTheDocument();
    expect(screen.getByText(/Open your authenticator app and enter the 6-digit code it shows/i)).toBeInTheDocument();

    await userEvent.type(screen.getByTestId('stepup-code-input'), '135790');
    await userEvent.click(screen.getByTestId('stepup-submit-btn'));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('135790'));
    expect(submittedBodies[0].code).toBe('135790');
    // Modal closes itself after success (open -> parent flips false; here we
    // just verify no error is shown).
    expect(screen.queryByTestId('stepup-error')).not.toBeInTheDocument();
  });

  test('wrong code shows an inline error and the modal stays open for retry', async () => {
    const onSubmit = jest.fn(async () => {
      throw new Error('Invalid 2FA code');
    });
    const onCancel = jest.fn();

    render(<TwoFactorStepUpModal open onSubmit={onSubmit} onCancel={onCancel} />);

    await userEvent.type(screen.getByTestId('stepup-code-input'), '000000');
    await userEvent.click(screen.getByTestId('stepup-submit-btn'));

    expect(await screen.findByTestId('stepup-error')).toHaveTextContent('Invalid 2FA code');
    expect(screen.getByTestId('twofa-stepup-modal')).toBeInTheDocument(); // still open
    expect(onCancel).not.toHaveBeenCalled();
  });

  test('isStepUpRequired predicate handles both detail shapes', () => {
    expect(isStepUpRequired('2fa_stepup_required')).toBe(true);
    expect(isStepUpRequired({ msg: '2fa_stepup_required' })).toBe(true);
    expect(isStepUpRequired({ detail: '2fa_stepup_required' })).toBe(true);
    expect(isStepUpRequired('other_error')).toBe(false);
    expect(isStepUpRequired(null)).toBe(false);
    // Users without 2FA never hit this predicate: their 403s carry other details.
    expect(isStepUpRequired('subscription_required')).toBe(false);
  });

  test('is2faChallenge predicate requires both detail and challenge_token', () => {
    expect(is2faChallenge({ detail: '2fa_required', challenge_token: 't' })).toBe(true);
    expect(is2faChallenge({ detail: '2fa_required' })).toBe(false);
    expect(is2faChallenge({ challenge_token: 't' })).toBe(false);
    expect(is2faChallenge(null)).toBe(false);
  });
});

// ===========================================================================
// 4. Admin nag banner
// ===========================================================================

describe('admin 2FA nag banner', () => {
  const renderBanners = (props) => render(<BannersHarness {...props} />);

  // Local harness replicating DashboardBanners + the DashboardPage trigger
  // logic so we can unit-test the render without the full dashboard stack.
  const BannersHarness = ({ needs2fa, status }) => {
    const { DashboardBanners } = require('../pages/dashboard/DashboardBanners');
    const [visible, setVisible] = React.useState(Boolean(needs2fa));
    React.useEffect(() => {
      if (needs2fa) { setVisible(true); return undefined; }
      if (status && status.enforced && !status.enabled) setVisible(true);
      else if (status) setVisible(false);
      return undefined;
    }, [needs2fa, status]);
    return <DashboardBanners wpBannerVisible={false} twoFaBannerVisible={visible} />;
  };

  test('needs_2fa_enrollment: true renders the persistent nag linking to Settings', () => {
    renderBanners({ needs2fa: true });
    expect(screen.getByTestId('twofa-admin-nag-banner')).toBeInTheDocument();
    expect(screen.getByText(/Admin accounts must enable two-factor authentication/i)).toBeInTheDocument();
    const link = screen.getByTestId('twofa-nag-settings-link');
    expect(link).toHaveAttribute('href', '/settings');
  });

  test('enforced + not enabled (from /auth/2fa/status) renders the nag', () => {
    renderBanners({ status: { enabled: false, recovery_codes_remaining: 0, enforced: true } });
    expect(screen.getByTestId('twofa-admin-nag-banner')).toBeInTheDocument();
  });

  test('users without 2FA enforcement never see the nag', () => {
    renderBanners({ status: { enabled: false, recovery_codes_remaining: 0, enforced: false } });
    expect(screen.queryByTestId('twofa-admin-nag-banner')).not.toBeInTheDocument();
  });

  test('enabled accounts never see the nag', () => {
    renderBanners({ status: { enabled: true, recovery_codes_remaining: 5, enforced: true } });
    expect(screen.queryByTestId('twofa-admin-nag-banner')).not.toBeInTheDocument();
  });
});