// UTM / Referral Attribution Capture Module — TrustOffice Frontend
// ================================================================
// Captures UTM params and referral identifiers from the URL and persists
// them to sessionStorage so they survive navigation to signup / checkout.
//
// Usage:
//   import { captureUtmParams, getUtmParams, clearUtmParams } from '@/utils/utmCapture';
//   captureUtmParams(); // Call once on app load
//   const utm = getUtmParams(); // Read before signup/checkout
//   clearUtmParams(); // Call after successful signup to avoid stale attribution

const UTM_KEYS = [
  'utm_source',
  'utm_campaign',
  'utm_medium',
  'utm_content',
  'utm_term',
  'referrer',
  'ref',           // Friend referral code (e.g. ?ref=JANE50)
  'wp_ref',        // WingPoint reference ID
  'wp_trust_name', // WingPoint trust name (pre-fill)
];

const STORAGE_PREFIX = 'utm_';
const MAX_LEN = 200;
const MAX_REF_LEN = 50; // Referral codes are short

function sanitize(value, maxLen = MAX_LEN) {
  if (!value) return null;
  const cleaned = String(value).trim();
  if (!cleaned) return null;
  // Strip control characters and angle brackets
  // eslint-disable-next-line no-control-regex
  return cleaned.replace(/[\x00-\x1f\x7f<>]/g, '').slice(0, maxLen);
}

function readFromUrl() {
  if (typeof window === 'undefined') return {};
  const params = new URLSearchParams(window.location.search);
  const out = {};
  for (const key of UTM_KEYS) {
    const val = params.get(key);
    if (val) {
      const maxLen = key === 'ref' || key === 'wp_ref' ? MAX_REF_LEN : MAX_LEN;
      const sanitized = sanitize(val, maxLen);
      if (sanitized) out[key] = sanitized;
    }
  }
  return out;
}

function readFromStorage() {
  if (typeof window === 'undefined') return {};
  const out = {};
  for (const key of UTM_KEYS) {
    const val = sessionStorage.getItem(`${STORAGE_PREFIX}${key}`);
    if (val) {
      const maxLen = key === 'ref' || key === 'wp_ref' ? MAX_REF_LEN : MAX_LEN;
      const sanitized = sanitize(val, maxLen);
      if (sanitized) out[key] = sanitized;
    }
  }
  return out;
}

/**
 * Capture UTM params from the current URL and persist them to sessionStorage.
 * Call this once on app load (e.g. in App.js useEffect or router init).
 *
 * Overwrites any previously stored params with the same keys — this ensures
 * that a fresh ad click updates attribution even if the user already has
 * stale params in sessionStorage.
 */
export function captureUtmParams() {
  if (typeof window === 'undefined') return;
  const fromUrl = readFromUrl();
  for (const [key, val] of Object.entries(fromUrl)) {
    sessionStorage.setItem(`${STORAGE_PREFIX}${key}`, val);
  }
}

/**
 * Return the current attribution params.
 *
 * Priority: URL params override sessionStorage (so a fresh campaign click
 * takes precedence), then sessionStorage provides fallback for internal
 * navigation.
 */
export function getUtmParams() {
  return { ...readFromStorage(), ...readFromUrl() };
}

/**
 * Return a normalized payload suitable for sending to the signup endpoint.
 * Maps `ref` → `referral_code` for backend compatibility.
 */
export function getSignupAttributionPayload() {
  const params = getUtmParams();
  return {
    utm_source: params.utm_source || null,
    utm_campaign: params.utm_campaign || null,
    utm_medium: params.utm_medium || null,
    referrer: params.referrer || null,
    referral_code: params.ref || null,
    wp_ref: params.wp_ref || null,
    wp_trust_name: params.wp_trust_name || null,
  };
}

/**
 * Clear all persisted UTM params from sessionStorage.
 * Call this after successful signup to avoid attributing future actions
 * to a campaign that already converted.
 */
export function clearUtmParams() {
  if (typeof window === 'undefined') return;
  for (const key of UTM_KEYS) {
    sessionStorage.removeItem(`${STORAGE_PREFIX}${key}`);
  }
}

/**
 * Check if the current user has any UTM attribution data stored.
 * Useful for conditional UI (e.g. showing a "You came from WingPoint" banner).
 */
export function hasUtmData() {
  const params = getUtmParams();
  return Object.keys(params).length > 0;
}
