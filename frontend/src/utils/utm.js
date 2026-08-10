// Marketing attribution helpers — capture UTM params from the URL and persist
// them so direct-to-checkout conversions can be attributed to ad campaigns.

const UTM_KEYS = ['utm_source', 'utm_campaign', 'utm_medium', 'referrer'];

function readFromUrl() {
  if (typeof window === 'undefined') return {};
  const params = new URLSearchParams(window.location.search);
  const out = {};
  for (const key of UTM_KEYS) {
    const val = params.get(key);
    if (val) out[key] = val.slice(0, 200);
  }
  return out;
}

function readFromStorage() {
  if (typeof window === 'undefined') return {};
  const out = {};
  for (const key of UTM_KEYS) {
    const val = sessionStorage.getItem(`utm_${key}`);
    if (val) out[key] = val.slice(0, 200);
  }
  return out;
}

/**
 * Capture UTM params from the current URL and persist them to sessionStorage
 * so they survive navigation to the signup/checkout pages. Call this once on
 * app load (e.g. in the router or a top-level component).
 */
export function captureUtmParams() {
  if (typeof window === 'undefined') return;
  const fromUrl = readFromUrl();
  for (const [key, val] of Object.entries(fromUrl)) {
    sessionStorage.setItem(`utm_${key}`, val);
  }
}

/**
 * Return the current attribution params (URL first, then sessionStorage).
 * Safe to call from any page.
 */
export function getUtmParams() {
  return { ...readFromStorage(), ...readFromUrl() };
}
