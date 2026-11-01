import { API_URL } from './onboardingConstants';
import { attemptSessionRefresh, handleRefreshFailure } from '../../utils/api';

/**
 * XMLHttpRequest-based JSON request for maximum mobile compatibility.
 * Returns a promise that resolves to the parsed JSON response.
 *
 * Mobile-compat note: XHR is kept (not a fetch rewrite) because parts of the
 * onboarding flow rely on XHR's per-request upload progress semantics and the
 * legacy browser behavior documented in the wizard steps. The 401 flow below
 * joins the app-wide single-flight refresh promise instead of kicking the
 * user out instantly (2026-11-01 session-kickout fix, council A4):
 * previously a 401 here dispatched session-expired IMMEDIATELY (and with no
 * withCredentials, cookies never even rode along cross-origin). Now: send
 * cookies (withCredentials = true), on 401 join ONE refresh, rebuild the
 * Bearer from localStorage.auth_token AFTER the refresh, retry once; only a
 * refresh failure or retry-401 dispatches session-expired and rejects.
 */
export function xhrRequest(method, url, data = null, token = null) {
  const doSend = (bearer, body) => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.withCredentials = true; // httpOnly session/refresh cookies cross-origin
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Accept', 'application/json');
    if (bearer) {
      xhr.setRequestHeader('Authorization', `Bearer ${bearer}`);
    }

    xhr.onreadystatechange = function () {
      if (xhr.readyState === 4) {
        try {
          const response = xhr.responseText ? JSON.parse(xhr.responseText) : {};
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(response);
          } else {
            if (xhr.status === 403) {
              const subStatus = xhr.getResponseHeader('X-Subscription-Status');
              if (subStatus || response.is_read_only) {
                window.dispatchEvent(new CustomEvent('subscription-readonly', {
                  detail: { status: subStatus || response.subscription_status || 'expired' },
                }));
              }
            }
            const detail = response.detail || response.message || response.msg;
            const msg = typeof detail === 'string'
              ? detail
              : (detail?.message || detail?.msg || (detail && detail !== '{}' ? JSON.stringify(detail) : null) || 'We couldn\'t complete this action. Please try again, or contact support@trustoffice.app for help.');
            reject(Object.assign(new Error(msg), { status: xhr.status }));
          }
        } catch (e) {
          reject(Object.assign(new Error('Invalid server response'), { status: xhr.status }));
        }
      }
    };

    xhr.onerror = function () {
      reject(new Error('Network error - please check your connection'));
    };

    xhr.send(body ? JSON.stringify(body) : null);
  });

  const first = () => doSend(token, data);

  return first().catch((err) => {
    if (err?.status !== 401) throw err;

    // 401-recovery: one single-flight refresh, one retry with the fresh token.
    return attemptSessionRefresh()
      .then(() => {
        const freshToken = localStorage.getItem('auth_token');
        if (!freshToken) {
          // Refresh "succeeded" but left no token — treat as failure.
          throw new Error('refresh produced no token');
        }
        return doSend(freshToken, data);
      })
      .catch((retryErr) => {
        if (retryErr?.status && retryErr.status !== 401 && retryErr.message !== 'refresh produced no token') {
          // Non-auth failure on the retry itself — surface it normally.
          throw retryErr;
        }
        // Refresh failed or retry still 401: clear token + session-expired, reject.
        handleRefreshFailure();
        throw new Error('Your session has expired. Please log in again.');
      });
  });
}