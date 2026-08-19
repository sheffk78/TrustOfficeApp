/**
 * Ad-hoc verification for AuthContext subscription-state resilience.
 *
 * Tests through the real AuthProvider + useAuth() public interface,
 * mocking fetch for /auth/me, /trusts, and /subscription/state.
 * Uses real timers (retry delay is only 1.5s, acceptable in tests).
 *
 * Run: cd frontend && npx react-scripts test --watchAll=false --testPathPattern=hermes-verify-subscription
 */

import React from 'react';
import { render, act, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('@/utils/errors', () => ({
  reportErrorToBackend: jest.fn(),
}));

const fetchMock = jest.fn();
global.fetch = fetchMock;

jest.setTimeout(30000);

const okResp = (state) => ({ ok: true, status: 200, json: async () => state });
const errResp = (status) => ({ ok: false, status, json: async () => ({}) });

const ACTIVE_STATE = { is_active: true, is_read_only: false, plan_type: 'monthly', status: 'active', trust_count: 0, trust_limit: 10 };
const EXPIRED_STATE = { is_active: false, is_read_only: true, plan_type: 'monthly', status: 'expired', trust_count: 0, trust_limit: 0 };
const USER = { user_id: 'user_2891b4cddd89', email: 'broufs2020@gmail.com', name: 'Brent Roufs' };

beforeEach(() => {
  jest.clearAllMocks();
  fetchMock.mockReset();
  localStorage.clear();
  localStorage.setItem('auth_token', 'test-token');
  Object.defineProperty(window, 'location', {
    value: { pathname: '/dashboard', href: 'http://localhost/dashboard', hash: '' },
    writable: true,
  });
});

const { AuthProvider, useAuth } = require('@/context/AuthContext');

function renderProvider() {
  let contextValue = null;
  function Consumer() {
    contextValue = useAuth();
    return null;
  }
  const tree = render(
    React.createElement(AuthProvider, null, React.createElement(Consumer))
  );
  return {
    // Always call this fresh — contextValue is reassigned on every AuthProvider re-render.
    getContext: () => contextValue,
    unmount: () => tree.unmount(),
  };
}

function setupFetches(subscriptionFetches) {
  fetchMock.mockImplementation((url) => {
    if (url.includes('/auth/me')) return Promise.resolve(okResp(USER));
    if (url.includes('/trusts')) return Promise.resolve(okResp([]));
    if (url.includes('/subscription/state')) {
      const fn = subscriptionFetches.shift();
      return fn ? fn() : Promise.resolve(okResp(ACTIVE_STATE));
    }
    return Promise.resolve(okResp({}));
  });
}

async function settle() {
  for (let i = 0; i < 10; i++) {
    await new Promise((r) => setTimeout(r, 10));
  }
}

// ─────────────────────────────────────────────────────────────
test('1. active subscription — isReadOnly=false', async () => {
  setupFetches([() => Promise.resolve(okResp(ACTIVE_STATE))]);

  const harness = renderProvider();
  await settle();

  await waitFor(() => expect(harness.getContext().subscription).toEqual(ACTIVE_STATE));
  expect(harness.getContext().isReadOnly).toBe(false);
  expect(harness.getContext().subscriptionExpired).toBe(false);

  harness.unmount();
});

// ─────────────────────────────────────────────────────────────
test('2. transient 500 then 200 — retries and succeeds', async () => {
  setupFetches([
    () => Promise.resolve(errResp(500)),
    () => Promise.resolve(okResp(ACTIVE_STATE)),
  ]);

  const harness = renderProvider();
  await new Promise((r) => setTimeout(r, 2500));
  await settle();

  await waitFor(() => expect(harness.getContext().subscription).toEqual(ACTIVE_STATE));
  expect(harness.getContext().isReadOnly).toBe(false);

  // At least 2 subscription calls (initial + 1 retry). May be more if
  // checkAuth re-triggers (pre-existing race), so check >=.
  const subCalls = fetchMock.mock.calls.filter((c) => c[0].includes('/subscription/state'));
  expect(subCalls.length).toBeGreaterThanOrEqual(2);

  harness.unmount();
});

// ─────────────────────────────────────────────────────────────
test('3. all retries fail on first load — read-only + console.warn', async () => {
  setupFetches([
    () => Promise.reject(new Error('Network failure')),
    () => Promise.reject(new Error('Network failure')),
    () => Promise.reject(new Error('Network failure')),
  ]);
  const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

  const harness = renderProvider();
  await new Promise((r) => setTimeout(r, 5000));
  await settle();

  await waitFor(() => expect(harness.getContext().isReadOnly).toBe(true));

  expect(warnSpy).toHaveBeenCalledWith(
    expect.stringContaining('Subscription state fetch failed after retries, using fallback')
  );

  const subCalls = fetchMock.mock.calls.filter((c) => c[0].includes('/subscription/state'));
  // At least 3 (1 + 2 retries) per load attempt.
  expect(subCalls.length).toBeGreaterThanOrEqual(3);

  warnSpy.mockRestore();
  harness.unmount();
});

// ─────────────────────────────────────────────────────────────
test('4. 401 on subscription state — no retry, immediate fallback', async () => {
  setupFetches([() => Promise.resolve(errResp(401))]);

  const harness = renderProvider();
  await settle();

  await waitFor(() => expect(harness.getContext().isReadOnly).toBe(true));

  // 401 should not retry — but checkAuth may re-trigger, so we check
  // that the *pattern* of no retries: each load attempt makes exactly 1 call.
  // Just verify the state is read-only (already done above).
  const subCalls = fetchMock.mock.calls.filter((c) => c[0].includes('/subscription/state'));
  // No retries means each load is 1 call. With possible duplicate checkAuth,
  // could be 1 or 2, but never 3+ (which would indicate retries happened).
  expect(subCalls.length).toBeLessThanOrEqual(2);

  harness.unmount();
});

// ─────────────────────────────────────────────────────────────
test('5. soft fallback: keeps cached active state on second load failure', async () => {
  setupFetches([() => Promise.resolve(okResp(ACTIVE_STATE))]);

  const harness = renderProvider();
  await settle();

  await waitFor(() => expect(harness.getContext().subscription).toEqual(ACTIVE_STATE));
  expect(harness.getContext().isReadOnly).toBe(false);

  // Second call: all 3 attempts fail (network).
  fetchMock.mockImplementation((url) => {
    if (url.includes('/subscription/state')) return Promise.reject(new Error('Network down'));
    return Promise.resolve(okResp({}));
  });

  const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

  await act(async () => {
    await harness.getContext().loadSubscriptionState('broufs2020@gmail.com');
    await new Promise((r) => setTimeout(r, 5000));
  });

  // Should keep the active state (soft fallback), NOT read-only.
  await waitFor(() => expect(harness.getContext().isReadOnly).toBe(false));
  expect(harness.getContext().subscriptionExpired).toBe(false);
  expect(warnSpy).toHaveBeenCalledWith(
    expect.stringContaining('Subscription state fetch failed after retries, using fallback')
  );

  warnSpy.mockRestore();
  harness.unmount();
});

// ─────────────────────────────────────────────────────────────
test('6. genuine expired subscription — read-only applied, no retries', async () => {
  setupFetches([() => Promise.resolve(okResp(EXPIRED_STATE))]);

  const harness = renderProvider();
  await settle();

  await waitFor(() => expect(harness.getContext().subscription).toEqual(EXPIRED_STATE));
  expect(harness.getContext().isReadOnly).toBe(true);
  expect(harness.getContext().subscriptionExpired).toBe(true);

  const subCalls = fetchMock.mock.calls.filter((c) => c[0].includes('/subscription/state'));
  // 200 response — no retries. May have 1-2 calls due to possible checkAuth re-trigger.
  expect(subCalls.length).toBeLessThanOrEqual(2);

  harness.unmount();
});

// ─────────────────────────────────────────────────────────────
test('7. periodic re-check restores write access after transient failure', async () => {
  // First load: all 3 attempts fail → read-only + re-check timer starts.
  setupFetches([
    () => Promise.reject(new Error('Network failure')),
    () => Promise.reject(new Error('Network failure')),
    () => Promise.reject(new Error('Network failure')),
  ]);
  const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

  const harness = renderProvider();
  await new Promise((r) => setTimeout(r, 5000));
  await settle();

  await waitFor(() => expect(harness.getContext().isReadOnly).toBe(true));

  // Make the next fetch succeed (the 60s re-check will call it).
  fetchMock.mockImplementation((url) => {
    if (url.includes('/subscription/state')) return Promise.resolve(okResp(ACTIVE_STATE));
    return Promise.resolve(okResp({}));
  });

  // Wait 61s for the periodic re-check timer to fire.
  await new Promise((r) => setTimeout(r, 62000));
  await settle();

  await waitFor(() => expect(harness.getContext().isReadOnly).toBe(false));
  expect(harness.getContext().subscription).toEqual(ACTIVE_STATE);
  expect(harness.getContext().subscriptionExpired).toBe(false);

  warnSpy.mockRestore();
  harness.unmount();
});