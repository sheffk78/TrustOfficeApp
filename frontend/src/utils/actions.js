/**
 * Shared action layer client — the ONE way the React UI calls TrustOffice
 * capabilities that also exist as agent tools.
 *
 * Pattern grafted from BuilderIO/agent-native (2026-09-21 deep-dive):
 * one action, many surfaces. POST /api/actions/<name> executes the same
 * handler the Trust Assistant's approval pipeline uses, so UI buttons and
 * chat approvals never drift apart.
 *
 * Usage:
 *   const res = await callAction('generate-minutes', {
 *     minutes_type: 'annual', meeting_date: '2026-09-21',
 *     participants: ['Jane Doe'], decisions: ['Approved budget'],
 *   }, { trustId });
 *   if (res.ok) const { record_id } = res.result;
 *
 * Discovery: listActions() returns every registered action + its field
 * schema (GET /api/actions) — handy for building dynamic forms later.
 */

import { getAuthHeaders, attemptSessionRefresh, handleRefreshFailure } from './api';

const API_BASE = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : 'https://api.trustoffice.app/api';

/**
 * One authed POST to the action layer, shared by callAction's
 * original-attempt and post-refresh retry (council A2).
 * credentials:'include' so the httpOnly session/refresh cookies ride along
 * cross-origin (2026-11-01 session-kickout fix).
 */
const doActionPost = (name, params, { trustId, conversationId } = {}) =>
  fetch(`${API_BASE}/actions/${encodeURIComponent(name)}`, {
    method: 'POST',
    credentials: 'include',
    headers: getAuthHeaders(), // freshly built at call time (token may have rotated)
    body: JSON.stringify({
      params,
      ...(trustId ? { trust_id: trustId } : {}),
      ...(conversationId ? { conversation_id: conversationId } : {}),
    }),
  });

/**
 * Call a registered action.
 * @param {string} name Action name (see GET /api/actions)
 * @param {object} params Action parameters (validated server-side)
 * @param {object} [options]
 * @param {string} [options.trustId] Trust scope; required for trust-scoped actions
 * @param {string} [options.conversationId] Chat conversation context, when called from the Trust Assistant
 * @returns {Promise<{ok: boolean, action: string, duration_ms: number, result?: object, error?: {code: string, detail: string}}>}
 */
export async function callAction(name, params = {}, { trustId, conversationId } = {}) {
  try {
    let response = await doActionPost(name, params, { trustId, conversationId });

    // 401-recovery (2026-11-01 session-kickout fix, council A2): access-token
    // expiry mid-form previously 401'd straight into a broken flow. Join the
    // ONE single-flight refresh, retry the action ONCE with fresh headers;
    // only then give up — dispatching session-expired (via the shared helper)
    // and returning the {ok:false} envelope. Never throws for auth states.
    if (response.status === 401) {
      try {
        await attemptSessionRefresh();
        response = await doActionPost(name, params, { trustId, conversationId });
      } catch (_refreshErr) {
        handleRefreshFailure();
        return { ok: false, action: name, duration_ms: 0, error: { code: 'session_expired', detail: 'Your session has expired. Please log in again.' } };
      }
      if (response.status === 401) {
        handleRefreshFailure();
        return { ok: false, action: name, duration_ms: 0, error: { code: 'session_expired', detail: 'Your session has expired. Please log in again.' } };
      }
    }

    // The layer returns ok=false in a 200 envelope for handled failures;
    // HTTP errors (404 unknown action, 401 auth) are surfaced uniformly.
    const data = await response.json().catch(() => ({}));
    if (!response.ok && !('ok' in data)) {
      const detail = typeof data?.detail === 'string'
        ? data.detail
        : (data?.detail?.message || `Request failed with status ${response.status}`);
      return { ok: false, action: name, duration_ms: 0, error: { code: 'http_error', detail } };
    }
    return data;
  } catch (err) {
    return {
      ok: false,
      action: name,
      duration_ms: 0,
      error: { code: 'network_error', detail: err?.message || 'Network error' },
    };
  }
}

/**
 * Fetch the manifest of every registered action (name, description,
 * write/trust_scoped flags, field schemas). Cached per page load.
 * @returns {Promise<Array<{name, description, write, trust_scoped, fields, surfaces}>>}
 */
export async function listActions({ trustId, conversationId } = {}) {
  try {
    let response = await fetch(`${API_BASE}/actions`, {
      credentials: 'include',
      headers: getAuthHeaders(),
    });

    // Same single-flight 401 recovery as callAction (council A2).
    if (response.status === 401) {
      try {
        await attemptSessionRefresh();
        response = await fetch(`${API_BASE}/actions`, { credentials: 'include', headers: getAuthHeaders() });
      } catch (_refreshErr) {
        handleRefreshFailure();
        return [];
      }
      if (response.status === 401) {
        handleRefreshFailure();
        return [];
      }
    }

    if (!response.ok) return [];
    const data = await response.json().catch(() => ({}));
    return Array.isArray(data.actions) ? data.actions : [];
  } catch {
    return [];
  }
}

/**
 * True when an action call result represents success.
 * Keeps `ok`-vs-HTTP semantics in one place for callers.
 */
export function actionSucceeded(res) {
  return Boolean(res && res.ok);
}