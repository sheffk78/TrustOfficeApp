// WingPoint Connect Flow v2 — pure connect-flow logic tests.
// Spec: Kit/life/brands/TrustOffice/specs/2026-10-22-connect-flow-v2.md
import {
  CONNECT_STATES,
  CONNECT_STEPS,
  resolveConnectState,
  stepForState,
  readConnectContext,
  isValidConnectContext,
  prefilledEmail,
  buildResolveBody,
  buildConnectHandoffUrl,
  stashConnectResumeParams,
  validateConnectPassword,
  isValidConnectCode,
  copyForState,
} from '../wingpointConnect';

const params = (obj) => new URLSearchParams(obj);

describe('resolveConnectState', () => {
  test('maps the three documented states', () => {
    expect(resolveConnectState({ state: 'new' })).toBe(CONNECT_STATES.NEW);
    expect(resolveConnectState({ state: 'needs_activation' })).toBe(CONNECT_STATES.NEEDS_ACTIVATION);
    expect(resolveConnectState({ state: 'activated' })).toBe(CONNECT_STATES.ACTIVATED);
  });

  test('falls back to "new" for unknown or malformed payloads', () => {
    expect(resolveConnectState({ state: 'bogus' })).toBe(CONNECT_STATES.NEW);
    expect(resolveConnectState(null)).toBe(CONNECT_STATES.NEW);
    expect(resolveConnectState(undefined)).toBe(CONNECT_STATES.NEW);
    expect(resolveConnectState('nope')).toBe(CONNECT_STATES.NEW);
  });
});

describe('stepForState', () => {
  test('activated account opens the prefilled login', () => {
    expect(stepForState(CONNECT_STATES.ACTIVATED)).toBe(CONNECT_STEPS.LOGIN);
  });

  test('never-activated account opens the set-a-password (claim) screen', () => {
    expect(stepForState(CONNECT_STATES.NEEDS_ACTIVATION)).toBe(CONNECT_STEPS.ACTIVATE);
  });

  test('no account opens the prefilled signup', () => {
    expect(stepForState(CONNECT_STATES.NEW)).toBe(CONNECT_STEPS.SIGNUP);
  });
});

describe('readConnectContext', () => {
  test('reads the standard connect params', () => {
    const ctx = readConnectContext(params({
      redirect_url: 'https://wingpointtrust.com/trustoffice/callback?app_id=app_abc123',
      wp_ref: 'WP-20260904-2517',
      trust_name: 'Lookout Point 5B Ministries',
      email: 'member@example.com',
    }));
    expect(ctx.wpRef).toBe('WP-20260904-2517');
    expect(ctx.trustName).toBe('Lookout Point 5B Ministries');
    expect(ctx.email).toBe('member@example.com');
    expect(ctx.redirectUrl).toContain('wingpointtrust.com');
  });

  test('derives app_id from the redirect_url when it is not a top-level param', () => {
    const ctx = readConnectContext(params({
      redirect_url: 'https://wingpointtrust.com/trustoffice/callback?app_id=2bfeffcc-ba86-4d41-8536-08a2154fcf02',
      wp_ref: 'WP-1',
    }));
    expect(ctx.appId).toBe('2bfeffcc-ba86-4d41-8536-08a2154fcf02');
  });

  test('prefers an explicit app_id param over the one inside redirect_url', () => {
    const ctx = readConnectContext(params({
      redirect_url: 'https://wingpointtrust.com/trustoffice/callback?app_id=inner',
      app_id: 'outer',
      wp_ref: 'WP-1',
    }));
    expect(ctx.appId).toBe('outer');
  });

  test('tolerates missing params', () => {
    const ctx = readConnectContext(params({}));
    expect(ctx.wpRef).toBe('');
    expect(ctx.appId).toBe('');
    expect(ctx.email).toBe('');
  });
});

describe('isValidConnectContext', () => {
  const good = {
    wpRef: 'WP-20260904-2517',
    appId: 'app_abc123',
    redirectUrl: 'https://wingpointtrust.com/trustoffice/callback?app_id=app_abc123',
  };

  test('accepts a real WingPoint context', () => {
    expect(isValidConnectContext(good)).toBe(true);
  });

  test('accepts the wingpointtrusts.com variant', () => {
    expect(isValidConnectContext({ ...good, redirectUrl: 'https://wingpointtrusts.com/cb?app_id=x' })).toBe(true);
  });

  test('rejects a missing wp_ref, app_id, or redirect_url', () => {
    expect(isValidConnectContext({ ...good, wpRef: '' })).toBe(false);
    expect(isValidConnectContext({ ...good, appId: '' })).toBe(false);
    expect(isValidConnectContext({ ...good, redirectUrl: '' })).toBe(false);
  });

  test('rejects a non-WingPoint redirect host', () => {
    expect(isValidConnectContext({ ...good, redirectUrl: 'https://evil.example.com/cb?app_id=x' })).toBe(false);
  });

  test('rejects a lookalike host', () => {
    expect(isValidConnectContext({ ...good, redirectUrl: 'https://notwingpointtrust.com/cb?app_id=x' })).toBe(false);
  });
});

describe('prefilledEmail', () => {
  const ctx = { email: 'member@example.com' };

  test('prefills the WP-known email', () => {
    expect(prefilledEmail(ctx, false)).toBe('member@example.com');
  });

  test('"Use a different email" clears the prefill', () => {
    expect(prefilledEmail(ctx, true)).toBe('');
  });
});

describe('buildResolveBody', () => {
  test('carries the connect context and the email', () => {
    const body = buildResolveBody(
      { wpRef: 'WP-1', appId: 'app_1', redirectUrl: 'https://wingpointtrust.com/cb?app_id=app_1' },
      ' member@example.com ',
    );
    expect(body).toEqual({
      wp_ref: 'WP-1',
      app_id: 'app_1',
      email: 'member@example.com',
      redirect_url: 'https://wingpointtrust.com/cb?app_id=app_1',
    });
  });
});

describe('buildConnectHandoffUrl', () => {
  const ctx = {
    email: 'member@example.com',
    wpRef: 'WP-20260904-2517',
    trustName: 'Lookout Point 5B Ministries',
    redirectUrl: 'https://wingpointtrust.com/cb?app_id=app_1',
    appId: 'app_1',
  };

  test('passes the WingPoint-known email to the signup/pricing flow', () => {
    const qs = buildConnectHandoffUrl(ctx);
    const p = new URLSearchParams(qs);
    expect(p.get('email')).toBe('member@example.com');
    expect(p.get('wp_ref')).toBe('WP-20260904-2517');
    expect(p.get('trust_name')).toBe('Lookout Point 5B Ministries');
    expect(p.get('wp')).toBe('1');
    expect(p.get('ref')).toBe('wp');
  });

  test('carries the plan through when given', () => {
    const p = new URLSearchParams(buildConnectHandoffUrl(ctx, 'wingpoint', 'annual'));
    expect(p.get('plan')).toBe('wingpoint');
    expect(p.get('billing')).toBe('annual');
  });

  test('omits the email when the member chose a different one', () => {
    const p = new URLSearchParams(buildConnectHandoffUrl({ ...ctx, email: '' }));
    expect(p.get('email')).toBeNull();
  });
});

describe('stashConnectResumeParams', () => {
  beforeEach(() => { sessionStorage.clear(); });

  test('stashes the connect params for the post-checkout return', () => {
    stashConnectResumeParams('redirect_url=https%3A%2F%2Fwingpointtrust.com%2Fcb&wp_ref=WP-1');
    expect(sessionStorage.getItem('wp_connect_after')).toBe('1');
    expect(sessionStorage.getItem('wp_connect_params')).toContain('wp_ref=WP-1');
  });

  test('is a no-op with no query string', () => {
    stashConnectResumeParams('');
    expect(sessionStorage.getItem('wp_connect_after')).toBeNull();
  });

  test('does not throw when sessionStorage is unavailable', () => {
    const original = sessionStorage.setItem;
    sessionStorage.setItem = () => { throw new Error('blocked'); };
    expect(() => stashConnectResumeParams('a=1')).not.toThrow();
    sessionStorage.setItem = original;
  });
});

describe('validateConnectPassword', () => {
  test('accepts a strong password', () => {
    expect(validateConnectPassword('Sup3rSecret!')).toBeNull();
  });

  test('rejects short, letterless, and digitless passwords', () => {
    expect(validateConnectPassword('Ab1')).toBeTruthy();
    expect(validateConnectPassword('passwordonly')).toBeTruthy();
    expect(validateConnectPassword('12345678')).toBeTruthy();
  });

  test('rejects an over-long password', () => {
    expect(validateConnectPassword('a1'.repeat(100))).toBeTruthy();
  });
});

describe('isValidConnectCode', () => {
  test('accepts a 6-digit code', () => {
    expect(isValidConnectCode('123456')).toBe(true);
    expect(isValidConnectCode(' 123456 ')).toBe(true);
  });

  test('rejects malformed codes', () => {
    expect(isValidConnectCode('12345')).toBe(false);
    expect(isValidConnectCode('1234567')).toBe(false);
    expect(isValidConnectCode('12345a')).toBe(false);
    expect(isValidConnectCode('')).toBe(false);
  });
});

describe('copyForState', () => {
  test('the activation screen says "Finish setting up your account"', () => {
    expect(copyForState(CONNECT_STATES.NEEDS_ACTIVATION).heading).toBe('Finish setting up your account');
  });

  test('the signup screen says "Create account & pay"', () => {
    expect(copyForState(CONNECT_STATES.NEW).submitLabel).toBe('Create account & pay');
  });

  test('the login screen keeps the existing sign-in copy', () => {
    expect(copyForState(CONNECT_STATES.ACTIVATED).submitLabel).toBe('Sign In & Connect');
  });
});
