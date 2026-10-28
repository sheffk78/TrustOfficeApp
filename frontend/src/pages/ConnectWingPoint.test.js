// Connect Flow v2 — component tests for the three connect branches.
// Spec: Kit/life/brands/TrustOffice/specs/2026-10-22-connect-flow-v2.md
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import ConnectWingPoint from '@/pages/ConnectWingPoint';
import { useAuth } from '@/context/AuthContext';

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));
jest.mock('@/utils/errors', () => ({
  showError: jest.fn(),
  reportErrorToBackend: jest.fn(),
}));
jest.mock('@/utils/twoFactor', () => ({
  is2faChallenge: jest.fn(() => false),
  login2fa: jest.fn(),
  get2faRateLimitMessage: jest.fn(() => null),
  get2faAttemptsRemaining: jest.fn(() => null),
}));
jest.mock('@/hooks/use2faLockout', () => ({
  use2faLockout: () => ({ active: false, secondsLeft: 0, trigger: jest.fn(), clear: jest.fn() }),
  formatLockout: (s) => `${s}s`,
}));
jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

// The page talks to the API over XMLHttpRequest — stub it so we can drive
// each branch deterministically without a live backend.
const xhrState = { handlers: null, sent: [] };

class MockXHR {
  constructor() {
    this.readyState = 0;
    this.status = 0;
    this.responseText = '';
    xhrState.sent.push(this);
  }

  open(method, url) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader() {}

  withCredentials = false;

  send(body) {
    this.body = body;
  }

  /** Drive a response back into the component. */
  respond(status, payload) {
    this.status = status;
    this.responseText = JSON.stringify(payload);
    this.readyState = 4;
    this.onreadystatechange();
  }
}

const WP_QUERY =
  'redirect_url=' + encodeURIComponent('https://wingpointtrust.com/trustoffice/callback?app_id=app_abc123')
  + '&wp_ref=WP-20260904-2517'
  + '&trust_name=' + encodeURIComponent('Lookout Point 5B Ministries')
  + '&email=member@example.com';

let mockSearchParams;

jest.mock('react-router-dom', () => ({
  useSearchParams: () => [new URLSearchParams(mockSearchParams), jest.fn()],
  useNavigate: () => jest.fn(),
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Navigate: ({ to }) => <span data-testid="navigate">{to}</span>,
  useParams: () => ({}),
  useLocation: () => ({ pathname: '/', search: '' }),
  Routes: ({ children }) => <>{children}</>,
  Route: () => null,
}));

const authUser = {
  email: 'member@example.com',
  name: 'John Matthews',
  setUser: jest.fn(),
  loadTrusts: jest.fn().mockResolvedValue(undefined),
  loadSubscriptionState: jest.fn().mockResolvedValue(undefined),
  loading: false,
  user: null,
};

beforeEach(() => {
  jest.clearAllMocks();
  xhrState.sent = [];
  mockSearchParams = WP_QUERY;
  useAuth.mockReturnValue({ ...authUser });
  localStorage.clear();
  global.XMLHttpRequest = MockXHR;
});

/** Respond to the resolve call with a given branch state. */
async function resolveTo(state) {
  await waitFor(() => {
    expect(xhrState.sent.some((x) => x.url.includes('/api/wingpoint-connect/resolve'))).toBe(true);
  });
  const resolveReq = xhrState.sent.find((x) => x.url.includes('/api/wingpoint-connect/resolve'));
  await act(async () => {
    resolveReq.respond(200, { state, email_locked: state !== 'activated', verification_required: state === 'needs_activation' });
  });
}

describe('ConnectWingPoint — Connect Flow v2 branches', () => {
  test('branch (a): no account shows the prefilled, locked signup', async () => {
    render(<ConnectWingPoint />);
    await resolveTo('new');

    expect(await screen.findByTestId('connect-wp-signup')).toBeInTheDocument();
    const emailInput = screen.getByTestId('connect-wp-signup-email');
    expect(emailInput).toHaveValue('member@example.com');
    // The WP-known email is locked.
    expect(emailInput).toHaveAttribute('readonly');
    expect(screen.getByTestId('connect-wp-signup-submit')).toHaveTextContent(/Create account & pay/i);
  });

  test('branch (a) puts the password field at the top of the form', async () => {
    render(<ConnectWingPoint />);
    await resolveTo('new');

    const form = (await screen.findByTestId('connect-wp-signup')).querySelector('form');
    const fields = Array.from(form.querySelectorAll('input[data-testid]'));
    expect(fields.map((f) => f.getAttribute('data-testid'))).toEqual([
      'connect-wp-signup-password',
      'connect-wp-signup-email',
      'connect-wp-signup-name',
    ]);
  });

  test('branch (a) offers "Use a different email"', async () => {
    render(<ConnectWingPoint />);
    await resolveTo('new');

    const escape = await screen.findByTestId('connect-wp-use-different-email');
    fireEvent.click(escape);

    // The escape is on the SIGNUP screen too — it must be reachable there.
    expect(screen.getByTestId('connect-wp-signup-email')).toHaveValue('');
    expect(screen.getByTestId('connect-wp-signup-email')).not.toHaveAttribute('readonly');
  });

  test('branch (b): never-activated account shows the set-a-password screen', async () => {
    render(<ConnectWingPoint />);
    await resolveTo('needs_activation');

    expect(await screen.findByTestId('connect-wp-activate')).toBeInTheDocument();
    expect(screen.getByText(/Finish setting up your account/i)).toBeInTheDocument();
    const emailInput = screen.getByTestId('connect-wp-claim-email');
    expect(emailInput).toHaveValue('member@example.com');
    expect(emailInput).toHaveAttribute('readonly');
    expect(screen.getByTestId('connect-wp-request-code')).toBeInTheDocument();
  });

  test('branch (b) requests a verification code, then verifies it', async () => {
    render(<ConnectWingPoint />);
    await resolveTo('needs_activation');

    fireEvent.click(await screen.findByTestId('connect-wp-request-code'));
    await waitFor(() => {
      expect(xhrState.sent.some((x) => x.url.includes('/api/wingpoint-connect/claim/request-code'))).toBe(true);
    });
    const codeReq = xhrState.sent.find((x) => x.url.includes('/claim/request-code'));
    expect(JSON.parse(codeReq.body).email).toBe('member@example.com');
    await act(async () => {
      codeReq.respond(200, { sent: true });
    });

    // The code + password form appears.
    const codeInput = await screen.findByTestId('connect-wp-claim-code');
    fireEvent.change(codeInput, { target: { value: '123456' } });
    fireEvent.change(screen.getByTestId('connect-wp-claim-password'), { target: { value: 'BrandNewPass1' } });
    fireEvent.click(screen.getByTestId('connect-wp-claim-submit'));

    await waitFor(() => {
      expect(xhrState.sent.some((x) => x.url.includes('/api/wingpoint-connect/claim/verify'))).toBe(true);
    });
    const verifyReq = xhrState.sent.find((x) => x.url.includes('/claim/verify'));
    const payload = JSON.parse(verifyReq.body);
    expect(payload.code).toBe('123456');
    expect(payload.new_password).toBe('BrandNewPass1');
    expect(payload.wp_ref).toBe('WP-20260904-2517');
  });

  test('branch (c): activated account shows the prefilled login', async () => {
    render(<ConnectWingPoint />);
    await resolveTo('activated');

    expect(await screen.findByTestId('connect-wp-login')).toBeInTheDocument();
    const emailInput = screen.getByTestId('connect-wp-login-email');
    expect(emailInput).toHaveValue('member@example.com');
    expect(emailInput).toHaveAttribute('readonly');
  });

  test('branch (c) login posts to the normal login endpoint', async () => {
    render(<ConnectWingPoint />);
    await resolveTo('activated');

    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'MyPassword1' } });
    fireEvent.click(screen.getByRole('button', { name: /Sign In & Connect/i }));

    await waitFor(() => {
      expect(xhrState.sent.some((x) => x.url.includes('/api/auth/login'))).toBe(true);
    });
    const loginReq = xhrState.sent.find((x) => x.url.includes('/api/auth/login'));
    expect(JSON.parse(loginReq.body).email).toBe('member@example.com');
  });

  test('the login branch also offers "Use a different email"', async () => {
    render(<ConnectWingPoint />);
    await resolveTo('activated');

    fireEvent.click(await screen.findByTestId('connect-wp-use-different-email'));
    const emailInput = screen.getByTestId('connect-wp-login-email');
    expect(emailInput).toHaveValue('');
    expect(emailInput).not.toHaveAttribute('readonly');
  });

  test('a resolve failure falls back to the login screen instead of dead-ending', async () => {
    render(<ConnectWingPoint />);
    await waitFor(() => {
      expect(xhrState.sent.some((x) => x.url.includes('/api/wingpoint-connect/resolve'))).toBe(true);
    });
    const resolveReq = xhrState.sent.find((x) => x.url.includes('/api/wingpoint-connect/resolve'));
    await act(async () => {
      resolveReq.respond(500, { detail: 'boom' });
    });

    expect(await screen.findByTestId('connect-wp-login')).toBeInTheDocument();
  });

  test('the resolve request carries the scoped WP connect context', async () => {
    render(<ConnectWingPoint />);
    await resolveTo('new');

    const resolveReq = xhrState.sent.find((x) => x.url.includes('/api/wingpoint-connect/resolve'));
    const payload = JSON.parse(resolveReq.body);
    expect(payload.wp_ref).toBe('WP-20260904-2517');
    expect(payload.app_id).toBe('app_abc123');
    expect(payload.email).toBe('member@example.com');
    expect(payload.redirect_url).toContain('wingpointtrust.com');
  });
});
