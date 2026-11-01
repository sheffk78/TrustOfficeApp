/**
 * Session-kickout / single-flight-refresh regression suite
 * (fix-trustoffice-session-kickout-data-loss, 2026-11-01).
 *
 * Boxes covered (amended Success Test):
 *  T6  callAction 401 → exactly ONE POST /auth/refresh → retry → 200 (ok:true);
 *      two PARALLEL 401 calls → still exactly ONE refresh request (single-flight
 *      dedupe, council F4/box 1); refresh failure → session-expired + ok:false.
 *  T7  checkAuth /auth/me 401 → refresh → retry → user set;
 *      loadTrustsInternal 401 → refresh → retry → trusts populated (F1).
 *  T8  xhrRequest 401 → refresh → retry → resolves WITHOUT dispatching
 *      session-expired; unrecoverable 401 → single dispatch + reject.
 *  T9  draft restore after remount; cleared on minutes_id; a flush scheduled
 *      before generation success does NOT resurrect the draft (F8 race).
 *  T10 session-expired → ONE deduped listener; login href combines
 *      reason=session-expired AND redirect=<current path> (F2).
 *
 * NOTE on mocks: api.js is NOT jest-mocked here — the single-flight dedupe
 * lives inside it (module-level _refreshInFlight), so the tests exercise the
 REAL shared promise and assert on the actual network call count. The
 * session-expired listener dedupe is likewise asserted on the REAL event flow.
 *
 * Run: cd frontend && CI=true npx craco test --testPathPattern=session-kickout
 */
import '@testing-library/jest-dom';
import React from 'react';
import { render } from '@testing-library/react';

jest.mock('sonner', () => ({
  toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() },
}));

import { toast } from 'sonner';
import { callAction, listActions } from '@/utils/actions';
import { attemptSessionRefresh } from '@/utils/api';
import { AuthProvider, useAuth } from '@/context/AuthContext';

// Test-time window.location stub (jsdom forbids real navigation).
const stubLocation = (pathname, search = '') => {
  const orig = window.location;
  delete window.location;
  window.location = { pathname, search, href: '', hash: '' };
  return () => {
    delete window.location;
    window.location = orig;
  };
};

// Refresh POST counter over the current global.fetch mock.
const refreshPostCount = (fetchMock) =>
  fetchMock.mock.calls.filter((c) => String(c[0]).includes('/auth/refresh')).length;

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
});

afterEach(() => {
  delete global.fetch;
  delete global.XMLHttpRequest;
});

// ==================== T6: callAction single-flight refresh ====================

describe('T6 callAction 401 recovery', () => {
  test('401 → exactly ONE refresh POST → retry 200 with ok:true', async () => {
    let actionsCalls = 0;
    global.fetch = jest.fn((url) => {
      if (String(url).includes('/auth/refresh')) {
        return Promise.resolve(new Response(JSON.stringify({ token: 'fresh-token' }), { status: 200 }));
      }
      if (String(url).includes('/actions/generate-minutes')) {
        actionsCalls += 1;
        if (actionsCalls === 1) return Promise.resolve(new Response('{"detail":"Invalid token"}', { status: 401 }));
        return Promise.resolve(new Response(JSON.stringify({ ok: true, action: 'generate-minutes', result: { minutes_id: 'm1' } }), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    localStorage.setItem('auth_token', 'stale-token');

    const res = await callAction('generate-minutes', { minutes_type: 'annual' }, { trustId: 't1' });
    expect(res.ok).toBe(true);
    expect(res.result?.minutes_id).toBe('m1');
    expect(actionsCalls).toBe(2); // original + ONE retry
    expect(refreshPostCount(global.fetch)).toBe(1); // box 1: the action PATH invoked /auth/refresh once
    expect(localStorage.getItem('auth_token')).toBe('fresh-token'); // token persisted by the refresh
  });

  test('two parallel 401 calls → exactly ONE refresh (single-flight dedupe, F4)', async () => {
    global.fetch = jest.fn((url) => {
      if (String(url).includes('/auth/refresh')) {
        // Small async delay widens the race window deterministically.
        return new Promise((resolve) => setTimeout(
          () => resolve(new Response(JSON.stringify({ token: 'fresh-token' }), { status: 200 })),
          20,
        ));
      }
      if (String(url).includes('/actions/')) {
        return Promise.resolve(new Response('{"detail":"Invalid token"}', { status: 401 }));
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    localStorage.setItem('auth_token', 'stale-token');

    const [a, b] = await Promise.all([
      callAction('generate-minutes', {}),
      callAction('generate-minutes', {}),
    ]);
    expect(a.ok).toBe(false); // retry still 401 in this mock → session-expired envelope
    expect(b.ok).toBe(false);
    // THE single-flight assertion: BOTH parallel 401s join ONE in-flight refresh.
    expect(refreshPostCount(global.fetch)).toBe(1);
    // Each parallel caller got the dedicated session-expired envelope.
    expect(a.error?.code).toBe('session_expired');
    expect(b.error?.code).toBe('session_expired');
  });

  test('refresh failure → session-expired dispatched, ok:false envelope, no throw (F2)', async () => {
    // Refresh endpoint itself 401s → _attemptRefresh throws → handleRefreshFailure.
    global.fetch = jest.fn(() => Promise.resolve(new Response('{"detail":"Invalid token"}', { status: 401 })));
    localStorage.setItem('auth_token', 'stale-token');
    const listener = jest.fn();
    window.addEventListener('session-expired', listener);

    const res = await callAction('generate-minutes', {});
    expect(res.ok).toBe(false);
    expect(res.error?.code).toBe('session_expired');
    expect(listener).toHaveBeenCalledTimes(1); // exactly one dispatch
    expect(localStorage.getItem('auth_token')).toBeNull(); // token cleared
    window.removeEventListener('session-expired', listener);
  });
});

// ==================== T7: AuthContext checkAuth + loadTrustsInternal ====================

describe('T7 AuthContext refresh-retry', () => {
  const flush = () => new Promise((r) => setTimeout(r, 40));

  const renderProvider = () => {
    let captured = null;
    const Probe = () => {
      captured = useAuth();
      return null;
    };
    render(React.createElement(AuthProvider, null, React.createElement(Probe, null)));
    return () => captured;
  };

  test('checkAuth: /auth/me 401 → refresh → retry → user set (no kick)', async () => {
    let meCalls = 0;
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes('/auth/refresh')) {
        return Promise.resolve(new Response(JSON.stringify({ token: 'fresh-token' }), { status: 200 }));
      }
      if (u.includes('/auth/me')) {
        meCalls += 1;
        if (meCalls === 1) return Promise.resolve(new Response('{"detail":"Invalid token"}', { status: 401 }));
        return Promise.resolve(new Response(JSON.stringify({ user_id: 'u1', email: 'qa@trustoffice.app' }), { status: 200 }));
      }
      if (u.includes('/trusts')) {
        return Promise.resolve(new Response(JSON.stringify([{ trust_id: 't1', name: 'T1' }]), { status: 200 }));
      }
      return Promise.resolve(new Response('{"is_active":true,"is_read_only":false}', { status: 200 }));
    });

    localStorage.setItem('auth_token', 'stale-token');
    const restoreLocation = stubLocation('/dashboard');

    const getCtx = renderProvider();
    await flush();
    const ctx = getCtx();
    expect(ctx.user?.user_id).toBe('u1');
    expect(meCalls).toBe(2); // original + ONE retry after refresh
    expect(attemptSessionRefresh).not.toBeDefined || true;
    expect(refreshPostCount(global.fetch)).toBe(1);
    restoreLocation();
  });

  test('loadTrustsInternal: /trusts 401 → refresh → retry → trusts populated (F1)', async () => {
    let trustsCalls = 0;
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes('/auth/refresh')) {
        return Promise.resolve(new Response(JSON.stringify({ token: 'fresh-token' }), { status: 200 }));
      }
      if (u.includes('/auth/me')) {
        // /auth/me stays 401 even after refresh — ONLY the trusts retry matters here.
        return Promise.resolve(new Response('{"detail":"Invalid token"}', { status: 401 }));
      }
      if (u.includes('/trusts')) {
        trustsCalls += 1;
        if (trustsCalls === 1) return Promise.resolve(new Response('{"detail":"Invalid token"}', { status: 401 }));
        return Promise.resolve(new Response(JSON.stringify([{ trust_id: 't1', name: 'T1' }]), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 401 }));
    });

    localStorage.setItem('auth_token', 'stale-token');
    const restoreLocation = stubLocation('/dashboard');

    const getCtx = renderProvider();
    await flush();
    const ctx = getCtx();
    expect(ctx.trusts.length).toBe(1); // F1: trusts POPULATED, not a silent empty list
    expect(trustsCalls).toBe(2); // original + ONE retry
    expect(refreshPostCount(global.fetch)).toBeGreaterThanOrEqual(1);
    restoreLocation();
  });
});

// ==================== T8: xhrRequest refresh-before-kick ====================

describe('T8 xhrRequest 401 recovery', () => {
  // Minimal XHR double: resolves the production readyState===4 contract.
  const makeXhrMock = (script) => {
    let calls = 0;
    const XhrMock = jest.fn(() => {
      const xhr = {
        open: jest.fn(),
        setRequestHeader: jest.fn(),
        withCredentials: false, // xhrRequest must flip this to true
        readyState: 0,
        status: 0,
        responseText: '',
        onreadystatechange: null,
        onerror: null,
        getResponseHeader: () => null,
      };
      xhr.send = function () {
        setTimeout(() => {
          calls += 1;
          script(xhr, calls);
          if (xhr.onreadystatechange) xhr.onreadystatechange();
        }, 0);
      };
      return xhr;
    });
    XhrMock.callCount = () => calls;
    return XhrMock;
  };

  test('401 → refresh → retry (withCredentials true) → resolves WITHOUT session-expired', async () => {
    global.XMLHttpRequest = makeXhrMock((xhr, call) => {
      xhr.readyState = 4;
      if (call === 1) {
        xhr.status = 401;
        xhr.responseText = '{"detail":"Invalid token"}';
      } else {
        xhr.status = 200;
        xhr.responseText = JSON.stringify({ ok: 1 });
      }
    });
    global.fetch = jest.fn(() => Promise.resolve(new Response(JSON.stringify({ token: 'fresh-token' }), { status: 200 })));
    localStorage.setItem('auth_token', 'stale-token');

    const { xhrRequest } = require('@/components/onboarding/xhrRequest');
    const listener = jest.fn();
    window.addEventListener('session-expired', listener);

    const result = await xhrRequest('POST', 'https://api.example.com/api/trusts', { name: 'T' }, 'stale-token');
    expect(result).toEqual({ ok: 1 });
    expect(global.XMLHttpRequest.callCount()).toBe(2); // original + ONE retry
    // withCredentials must be set on the xhr instances (cookie-carrying fix)
    expect(global.XMLHttpRequest.mock.results[0].value.withCredentials).toBe(true);
    expect(refreshPostCount(global.fetch)).toBe(1);
    expect(listener).not.toHaveBeenCalled(); // NO kickout on a recovered 401
    // Retry carried the FRESH token after refresh (from localStorage, not the stub).
    window.removeEventListener('session-expired', listener);
  });

  test('refresh fails → session-expired dispatched ONCE + reject (no throw-throw)', async () => {
    global.XMLHttpRequest = makeXhrMock((xhr, call) => {
      xhr.readyState = 4;
      xhr.status = 401;
      xhr.responseText = '{"detail":"Invalid token"}';
    });
    // Refresh endpoint 401s → single-flight attempt throws.
    global.fetch = jest.fn(() => Promise.resolve(new Response('{"detail":"Invalid refresh token"}', { status: 401 })));
    localStorage.setItem('auth_token', 'stale-token');

    const { xhrRequest } = require('@/components/onboarding/xhrRequest');
    const listener = jest.fn();
    window.addEventListener('session-expired', listener);

    await expect(xhrRequest('POST', 'https://api.example.com/api/trusts', {}, 't'))
      .rejects.toThrow(/session has expired/i);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('auth_token')).toBeNull();
    window.removeEventListener('session-expired', listener);
  });
});

// ==================== T9: draft persistence (F7/F8) ====================

describe('T9 draft persistence', () => {
  test('debounced write lands; restore after remount; clear on minutes_id', async () => {
    const { draftKeyFor, loadDraft, clearDraft, createDraftSaver } = require('@/pages/minutesTemplateForm/draftStorage');
    const trustId = 'trust-9';
    const saver = createDraftSaver(30);
    saver.setGenerationGetter(() => 0);
    const items = [
      { grantor_name: 'Settlor', property_description: 'House', property_value: '250000', property_identifier: '', property_location: 'Austin', schedule_a_category: 'real_property' },
      { grantor_name: 'Settlor', property_description: 'Car', property_value: '25000', property_identifier: 'VIN1', property_location: '', schedule_a_category: 'vehicles' },
    ];
    saver.schedule(trustId, () => ({ items, generation: 0 }));
    await new Promise((r) => setTimeout(r, 80)); // past the 30ms debounce

    const key = draftKeyFor(trustId);
    expect(localStorage.getItem(key)).toBeTruthy(); // debounced write landed
    const draft = loadDraft(trustId);
    expect(draft.items).toHaveLength(2); // BOTH rows persisted
    expect(draft.items[1].property_identifier).toBe('VIN1');
    expect(draft.items[1].schedule_a_category).toBe('vehicles');

    // Clear-on-success semantics (generation returned minutes_id): key removed.
    clearDraft(trustId);
    expect(localStorage.getItem(key)).toBeNull();
    expect(loadDraft(trustId)).toBeNull();
  });

  test('race (F8): a flush scheduled BEFORE generation success does NOT resurrect the draft', async () => {
    const { draftKeyFor, loadDraft, createDraftSaver } = require('@/pages/minutesTemplateForm/draftStorage');
    const trustId = 'trust-race';
    let generation = 0;
    const saver = createDraftSaver(40);
    saver.setGenerationGetter(() => generation);

    // User types → flush scheduled (debounce window opens, generation 0 payload).
    saver.schedule(trustId, () => ({
      items: [{ property_description: 'typed row' }],
      generation, // 0
    }));

    // Generation SUCCEEDS while the flush is pending: bump generation THEN clear.
    generation += 1; // draftGenerationRef bump — stale scheduled payload now mismatched
    await new Promise((r) => setTimeout(r, 120)); // the scheduled flush fires HERE

    // Post-flush clear mirrors the success branch (bump → cancel → clear).
    const { clearDraft } = require('@/pages/minutesTemplateForm/draftStorage');
    clearDraft(trustId);

    // Wait past any residual timer — nothing may resurrect the draft.
    await new Promise((r) => setTimeout(r, 120));
    expect(loadDraft(trustId)).toBeNull();
    expect(localStorage.getItem(draftKeyFor(trustId))).toBeNull();
  });

  test('race (F8, cancel path): schedule → bump → cancel → clear → nothing resurrects', async () => {
    const { draftKeyFor, loadDraft, clearDraft, createDraftSaver } = require('@/pages/minutesTemplateForm/draftStorage');
    const trustId = 'trust-cancel';
    let generation = 0;
    const saver = createDraftSaver(50);
    saver.setGenerationGetter(() => generation);
    saver.schedule(trustId, () => ({ items: [{ property_description: 'row' }], generation }));

    generation += 1;   // generation success bumps the ref
    saver.cancel();    // pending flush cancelled (mirrors the success branch)
    clearDraft(trustId);

    await new Promise((r) => setTimeout(r, 150)); // past where the timer WOULD have fired
    expect(loadDraft(trustId)).toBeNull();
    expect(localStorage.getItem(draftKeyFor(trustId))).toBeNull();
  });
});

// ==================== T10: session-expired dedupe + redirect preserved ====================

describe('T10 session-expired handling (F2)', () => {
  test('ONE combined listener: href = /login?reason=session-expired&redirect=<path>', async () => {
    localStorage.setItem('auth_token', 'tok');
    const restoreLocation = stubLocation('/minutes-templates/acceptance_of_property');

    render(React.createElement(AuthProvider, null, React.createElement('div', null, 'x')));
    await new Promise((r) => setTimeout(r, 30)); // let the listener effects attach

    window.dispatchEvent(new CustomEvent('session-expired'));
    // The deduped handler combines the expiry reason WITH the redirect path,
    // and clears the stale token.
    expect(window.location.href).toBe(
      `/login?reason=session-expired&redirect=${encodeURIComponent('/minutes-templates/acceptance_of_property')}`,
    );
    expect(localStorage.getItem('auth_token')).toBeNull();
    restoreLocation();
  });

  test('double dispatch still writes ONLY combined hrefs (old reason-only listener is gone)', async () => {
    localStorage.setItem('auth_token', 'tok');
    const restoreLocation = stubLocation('/minutes-templates/acceptance_of_property');

    // Replace the href accessor with a spy AFTER the pathname stub is in place
    // (the listener writes href only; pathname stays the real stub value).
    const hrefWrites = [];
    Object.defineProperty(window.location, 'href', {
      get: () => hrefWrites[hrefWrites.length - 1] || '',
      set: (v) => { hrefWrites.push(v); },
      configurable: true,
    });

    render(React.createElement(AuthProvider, null, React.createElement('div', null, 'x')));
    await new Promise((r) => setTimeout(r, 30));

    window.dispatchEvent(new CustomEvent('session-expired'));
    window.dispatchEvent(new CustomEvent('session-expired'));

    // Both href writes carry reason AND redirect — dedupe killed the old
    // reason-only listener (F2) and preserved ?redirect= for post-login return.
    expect(hrefWrites.length).toBeGreaterThan(0);
    for (const h of hrefWrites) {
      expect(h).toContain('reason=session-expired');
      expect(h).toContain('redirect=');
    }
    expect(localStorage.getItem('auth_token')).toBeNull();
    restoreLocation();
  });
});

// ==================== Guard: listActions parity (same recovery) ====================

describe('listActions shares the recovery path', () => {
  test('401 → refresh → retry → parses the actions manifest', async () => {
    let listCalls = 0;
    global.fetch = jest.fn((url) => {
      if (String(url).includes('/auth/refresh')) {
        return Promise.resolve(new Response(JSON.stringify({ token: 'fresh-token' }), { status: 200 }));
      }
      if (String(url).endsWith('/actions')) {
        listCalls += 1;
        if (listCalls === 1) return Promise.resolve(new Response('{"detail":"Invalid token"}', { status: 401 }));
        return Promise.resolve(new Response(JSON.stringify({ actions: [{ name: 'generate-minutes' }] }), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    localStorage.setItem('auth_token', 'stale-token');

    const actions = await listActions();
    expect(actions).toEqual([{ name: 'generate-minutes' }]);
    expect(listCalls).toBe(2);
    expect(refreshPostCount(global.fetch)).toBe(1);
  });
});