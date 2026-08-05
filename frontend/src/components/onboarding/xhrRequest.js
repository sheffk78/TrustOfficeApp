import { API_URL } from './onboardingConstants';

/**
 * XMLHttpRequest-based JSON request for maximum mobile compatibility.
 * Returns a promise that resolves to the parsed JSON response.
 */
export function xhrRequest(method, url, data = null, token = null) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Accept', 'application/json');
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
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
            if (xhr.status === 401) {
              reject(new Error('Your session has expired. Please log in again.'));
              return;
            }
            const detail = response.detail || response.message || response.msg;
            const msg = typeof detail === 'string'
              ? detail
              : (detail?.message || detail?.msg || (detail && detail !== '{}' ? JSON.stringify(detail) : null) || 'We couldn\'t complete this action. Please try again, or contact support@trustoffice.app for help.');
            reject(new Error(msg));
          }
        } catch (e) {
          reject(new Error('Invalid server response'));
        }
      }
    };

    xhr.onerror = function () {
      reject(new Error('Network error - please check your connection'));
    };

    xhr.send(data ? JSON.stringify(data) : null);
  });
}
