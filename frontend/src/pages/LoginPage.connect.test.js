// WingPoint connect email carriage on LoginPage (2026-11-24).
//
// The WingPoint admin template now passes the member's known email as ?email=.
// LoginPage must carry it across (a) the post-redirect guard for /pricing and
// (b) the Create Account link to /signup, so the checkout form stays prefilled.
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import LoginPage from '@/pages/LoginPage';
import { useAuth } from '@/context/AuthContext';

const mockNavigate = jest.fn();

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));

jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));

jest.mock('@/utils/errors', () => ({
  showError: jest.fn(),
  reportErrorToBackend: jest.fn(),
}));

jest.mock('react-router-dom', () => ({
  useSearchParams: () => [new URLSearchParams(mockSearchParams), jest.fn()],
  useNavigate: () => mockNavigate,
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
  useParams: () => ({}),
  useLocation: () => ({ pathname: '/login', search: '' }),
}));

let mockSearchParams = '';

beforeEach(() => {
  jest.clearAllMocks();
  mockSearchParams = '';
  useAuth.mockReturnValue({
    user: null,
    setUser: jest.fn(),
    loadTrusts: jest.fn(() => Promise.resolve()),
    loadSubscriptionState: jest.fn(() => Promise.resolve()),
  });
  window.localStorage.clear();
});

const getQuery = (href) => new URLSearchParams(href.split('?')[1]);

describe('LoginPage — WingPoint email carriage', () => {
  test('post-redirect guard carries email from login?action=subscribe to /pricing', () => {
    mockSearchParams = 'wp=1&action=subscribe&plan=wingpoint&wp_ref=WP-20261124-0001&email=member@example.com';
    useAuth.mockReturnValue({
      user: { email: 'member@example.com', name: 'Member' },
      setUser: jest.fn(),
      loadTrusts: jest.fn(() => Promise.resolve()),
      loadSubscriptionState: jest.fn(() => Promise.resolve()),
    });
    render(<LoginPage />);

    expect(mockNavigate).toHaveBeenCalledTimes(1);
    const target = mockNavigate.mock.calls[0][0];
    expect(target).toMatch(/^\/pricing\?/);
    const params = getQuery(target);
    expect(params.get('wp')).toBe('1');
    expect(params.get('action')).toBe('subscribe');
    expect(params.get('email')).toBe('member@example.com');
    expect(params.get('wp_ref')).toBe('WP-20261124-0001');
    expect(params.get('plan')).toBe('wingpoint');
  });

  test('Create Account link includes email when arriving with ?email=', () => {
    mockSearchParams = 'wp=1&action=subscribe&plan=wingpoint&wp_ref=WP-20261124-0001&email=member@example.com';
    render(<LoginPage />);

    const link = screen.getByTestId('signup-link');
    const href = link.getAttribute('href');
    const params = getQuery(href);
    expect(params.get('ref')).toBe('wp');
    expect(params.get('email')).toBe('member@example.com');
    expect(params.get('wp_ref')).toBe('WP-20261124-0001');
    expect(params.get('plan')).toBe('wingpoint');
  });

  test('post-login routing carries email to /pricing after subscribe', async () => {
  mockSearchParams = 'wp=1&action=subscribe&plan=wingpoint&wp_ref=WP-20261124-0001&email=member@example.com';
  const setUser = jest.fn();
  const loadTrusts = jest.fn(() => Promise.resolve());
  const loadSubscriptionState = jest.fn(() => Promise.resolve());
  useAuth.mockReturnValue({ user: null, setUser, loadTrusts, loadSubscriptionState });
  render(<LoginPage />);

  // xhrPost uses XMLHttpRequest; shim a 200 so completeLogin is reached.
  const FakeXHR = class {
    open() {}
    setRequestHeader() {}
    send() {
      this.readyState = 4;
      this.status = 200;
      this.responseText = JSON.stringify({ token: 'tok-123', user: { email: 'member@example.com' } });
      if (this.onreadystatechange) this.onreadystatechange();
    }
  };
  global.XMLHttpRequest = FakeXHR;

  const form = screen.getByTestId('email-input').closest('form');
  fireEvent.input(screen.getByTestId('email-input'), { target: { value: 'member@example.com' } });
  fireEvent.input(screen.getByTestId('password-input'), { target: { value: 'password' } });
  fireEvent.submit(form);

  await waitFor(() => {
    expect(loadTrusts).toHaveBeenCalled();
  });

  expect(loadSubscriptionState).toHaveBeenCalled();
  const call = mockNavigate.mock.calls.find(([to]) => typeof to === 'string' && to.startsWith('/pricing'));
  expect(call).toBeTruthy();
  const params = getQuery(call[0]);
  expect(params.get('email')).toBe('member@example.com');
  expect(params.get('wp_ref')).toBe('WP-20261124-0001');
  });

  test('omits email param entirely when not provided', () => {
    mockSearchParams = 'wp=1&action=subscribe&plan=wingpoint&wp_ref=WP-20261124-0001';
    useAuth.mockReturnValue({
      user: { email: 'other@example.com', name: 'Other' },
      setUser: jest.fn(),
      loadTrusts: jest.fn(() => Promise.resolve()),
      loadSubscriptionState: jest.fn(() => Promise.resolve()),
    });
    render(<LoginPage />);

    const target = mockNavigate.mock.calls[0][0];
    const params = getQuery(target);
    expect(params.has('email')).toBe(false);
    expect(params.get('wp_ref')).toBe('WP-20261124-0001');
  });
});
