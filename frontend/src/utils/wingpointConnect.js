/**
 * WingPoint Connect Flow v2 — pure connect-flow logic.
 *
 * Spec: Kit/life/brands/TrustOffice/specs/2026-10-22-connect-flow-v2.md
 *
 * Kept as a dependency-free module (no React, no fetch) so every branch
 * decision is unit-testable in isolation and so the same helpers can be
 * reused by the connect page, the signup handoff, and the pricing handoff.
 *
 * The three branches, decided at connect entry off the member's email:
 *   'new'              -> prefilled + locked signup, straight to payment
 *   'needs_activation' -> set-a-password screen bound to the EXISTING account
 *   'activated'        -> prefilled login
 */

export const CONNECT_STATES = {
  NEW: 'new',
  NEEDS_ACTIVATION: 'needs_activation',
  ACTIVATED: 'activated',
};

export const CONNECT_STEPS = {
  CHECKING: 'checking',
  LOGIN: 'login',
  SIGNUP: 'signup',
  ACTIVATE: 'activate',
  CONFIRM: 'confirm',
  REDIRECTING: 'redirecting',
};

/** Map an API resolution payload to a normalized connect state. */
export function resolveConnectState(payload) {
  if (!payload || typeof payload !== 'object') return CONNECT_STATES.NEW;
  const state = payload.state;
  if (
    state === CONNECT_STATES.NEW
    || state === CONNECT_STATES.NEEDS_ACTIVATION
    || state === CONNECT_STATES.ACTIVATED
  ) {
    return state;
  }
  return CONNECT_STATES.NEW;
}

/**
 * Which screen does a resolved state open on?
 *
 * 'activated'        -> prefilled login
 * 'needs_activation' -> set-a-password (claim) screen
 * 'new'              -> prefilled signup
 */
export function stepForState(state) {
  switch (state) {
    case CONNECT_STATES.ACTIVATED:
      return CONNECT_STEPS.LOGIN;
    case CONNECT_STATES.NEEDS_ACTIVATION:
      return CONNECT_STEPS.ACTIVATE;
    case CONNECT_STATES.NEW:
    default:
      return CONNECT_STEPS.SIGNUP;
  }
}

/**
 * Read the connect context out of the URL search params.
 *
 * `app_id` may arrive as its own query param OR be embedded in the
 * WingPoint callback URL (`redirect_url=...&app_id=...`). The backend accepts
 * either; the frontend normalizes so the request body always carries both.
 */
export function readConnectContext(searchParams) {
  const get = (key) => {
    if (!searchParams || typeof searchParams.get !== 'function') return null;
    const value = searchParams.get(key);
    return value === undefined ? null : value;
  };

  const redirectUrl = get('redirect_url');
  const wpRef = get('wp_ref');
  const trustName = get('trust_name');
  const email = get('email');
  const plan = get('plan');
  const billing = get('billing');

  let appId = get('app_id');
  if (!appId && redirectUrl) {
    try {
      const url = new URL(redirectUrl, 'https://placeholder.invalid');
      appId = url.searchParams.get('app_id');
    } catch (e) {
      appId = null;
    }
  }

  return {
    wpRef: wpRef || '',
    appId: appId || '',
    trustName: trustName || '',
    redirectUrl: redirectUrl || '',
    email: email ? String(email).trim() : '',
    plan: plan || '',
    billing: billing || '',
  };
}

/**
 * Is the connect context usable? The backend enforces the same rules; this
 * only avoids firing a doomed request from the UI.
 */
export function isValidConnectContext(context) {
  if (!context) return false;
  if (!context.wpRef || !context.appId) return false;
  if (!context.redirectUrl) return false;
  try {
    const host = new URL(context.redirectUrl, 'https://placeholder.invalid').hostname.toLowerCase();
    if (!host) return false;
    return (
      host === 'wingpointtrust.com'
      || host.endsWith('.wingpointtrust.com')
      || host === 'wingpointtrusts.com'
      || host.endsWith('.wingpointtrusts.com')
    );
  } catch (e) {
    return false;
  }
}

/**
 * The prefilled email for a connect screen.
 *
 * `overridden` is set when the member taps "Use a different email" — the
 * prefill is cleared and the field becomes editable.
 */
export function prefilledEmail(context, overridden) {
  if (overridden) return '';
  if (!context) return '';
  return (context.email || '').trim();
}

/**
 * Build the connect request body for the scoped resolve endpoint.
 * The email is the member's WP-known address; it is sent in the body (never
 * logged) and the backend fingerprints it for rate limiting.
 */
export function buildResolveBody(context, email) {
  return {
    wp_ref: context?.wpRef || '',
    app_id: context?.appId || '',
    email: (email || '').trim(),
    redirect_url: context?.redirectUrl || '',
  };
}

/**
 * Build the connect handoff URL for the signup / pricing flow.
 *
 * The WingPoint-known email rides along as `email` so the signup screen can
 * prefill (and lock) it. `wp_ref` and `trust_name` keep the trust attached
 * through the payment handoff.
 */
export function buildConnectHandoffUrl(context, plan, billing) {
  const params = new URLSearchParams();
  if (context?.email) params.set('email', context.email);
  if (context?.wpRef) params.set('wp_ref', context.wpRef);
  if (context?.trustName) params.set('trust_name', context.trustName);
  if (context?.redirectUrl) params.set('redirect_url', context.redirectUrl);
  if (context?.appId) params.set('app_id', context.appId);
  if (context?.plan || plan) params.set('plan', context?.plan || plan);
  if (context?.billing || billing) params.set('billing', context?.billing || billing);
  if (context?.wpRef || context?.email) params.set('ref', 'wp');
  if (context?.wpRef) params.set('wp', '1');
  return params.toString();
}

/**
 * Remember the connect params so the pricing page can return the member to
 * the WingPoint connect callback after Stripe checkout completes.
 *
 * The pricing page reads `wp_connect_after` / `wp_connect_params` from
 * sessionStorage and builds the post-payment success URL from them — without
 * this stash the member would land on the dashboard and never reach the
 * WingPoint callback.
 */
export function stashConnectResumeParams(queryString) {
  if (!queryString) return;
  try {
    sessionStorage.setItem('wp_connect_after', '1');
    sessionStorage.setItem('wp_connect_params', queryString);
  } catch (e) {
    // sessionStorage can throw in private-mode / blocked-storage browsers.
    // The connect flow still works; only the post-payment auto-return is
    // lost, and the member can reach WingPoint from the TrustOffice app.
  }
}

/**
 * Shape-check and normalize a WingPoint provisioning ref (WP-XXXXXXXX-XXXX).
 *
 * The ref rides URL params under two names depending on the path: `wp_ref`
 * (login/signup handoffs) and `ref` (the admin_settings signup template).
 * Anything that doesn't match the provisioning-ref shape is ignored — free
 * text in `ref` is marketing attribution, not a WingPoint referral.
 */
const WP_REF_RE = /^WP-[A-Z0-9]{8}-[A-Z0-9]{4}$/;

export function pickWpRef(candidates) {
  if (!Array.isArray(candidates)) return null;
  for (const c of candidates) {
    if (typeof c === 'string' && WP_REF_RE.test(c.trim())) {
      return c.trim().toUpperCase();
    }
  }
  return null;
}

/**
 * Client-side password strength check — mirrors the backend
 * `validate_password_strength` (>= 8 chars, a letter, a digit).
 */
export function validateConnectPassword(password) {
  const value = password || '';
  if (value.length < 8) return 'Password must be at least 8 characters long';
  if (value.length > 128) return 'Password must be less than 128 characters';
  if (!/[A-Za-z]/.test(value)) return 'Password must contain at least one letter';
  if (!/\d/.test(value)) return 'Password must contain at least one number';
  return null;
}

/** Is a verification code well-formed? (6 digits) */
export function isValidConnectCode(code) {
  return /^\d{6}$/.test((code || '').trim());
}

/**
 * Human-readable copy for each branch. The spec pins the activation
 * screen's header ("Finish setting up your account") and the signup screen's
 * primary action ("Create account & pay").
 */
export function copyForState(state) {
  switch (state) {
    case CONNECT_STATES.ACTIVATED:
      return {
        heading: 'Sign in to connect your trust',
        subheading: 'Your TrustOffice account is ready. Sign in to finish connecting.',
        submitLabel: 'Sign In & Connect',
      };
    case CONNECT_STATES.NEEDS_ACTIVATION:
      return {
        heading: 'Finish setting up your account',
        subheading: 'Your trust is already in TrustOffice. Set a password to activate your account.',
        submitLabel: 'Activate Account',
      };
    case CONNECT_STATES.NEW:
    default:
      return {
        heading: 'Create your TrustOffice account',
        subheading: 'Your trust is ready. Create an account to start managing it.',
        submitLabel: 'Create account & pay',
      };
  }
}
