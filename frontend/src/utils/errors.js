/**
 * TrustOffice Error Handling Utility
 *
 * Provides:
 * - `showError(toast, error, context)`: Extracts the best error message, auto-reports
 *   to the backend (Discord alert via /api/report-error), and shows a toast with
 *   actionable guidance.
 * - `reportErrorToBackend(error, context)`: Fire-and-forget error reporting to
 *   POST /api/report-error. Called automatically by showError, but can be used
 *   standalone for non-toast error paths.
 * - `SUPPORT_EMAIL`: Constant for the support contact.
 *
 * Usage pattern (replacing bare toast.error calls):
 *
 *   import { showError } from '../utils/errors';
 *   import { toast } from 'react-toastify';
 *
 *   // Before: toast.error('Failed to save');
 *   // After:
 *   catch (error) {
 *     showError(toast, error, { operation: 'save_trust', page: 'Onboarding' });
 *   }
 *
 * The default fallback message includes "Please try again. If the problem
 * continues, contact support@trustoffice.app." so users always have a next step.
 */

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';
const API = `${BACKEND_URL}/api`;

export const SUPPORT_EMAIL = 'support@trustoffice.app';

// Track if we've already set up the global uncaught error handler
let _globalHandlerInstalled = false;

// ---------------------------------------------------------------------------
// In-app error logging (POST /api/error-log → MongoDB, queryable via admin API)
// ---------------------------------------------------------------------------

// Debounce: don't send more than 1 error per 5 seconds from the same source
const ERROR_DEBOUNCE_MS = 5000;
const _errorLogTimestamps = new Map(); // key → last-sent timestamp

function _isDev() {
  return (
    process.env.NODE_ENV !== 'production' ||
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1'
  );
}

function _shouldDebounce(key) {
  const now = Date.now();
  const last = _errorLogTimestamps.get(key) || 0;
  if (now - last < ERROR_DEBOUNCE_MS) return true;
  _errorLogTimestamps.set(key, now);
  return false;
}

/**
 * Report an error to POST /api/error-log (MongoDB-backed, queryable).
 * Fire-and-forget — never throws, never blocks the UI.
 * Debounced to max 1 per 5 seconds per source key.
 * Skipped in development (NODE_ENV !== 'production' or localhost).
 *
 * @param {object} data - Error data to send
 * @param {string} debounceKey - Key for debouncing (defaults to error_type)
 */
export function reportToErrorLog(data, debounceKey = null) {
  try {
    if (_isDev()) return;

    const key = debounceKey || data.error_type || 'unknown';
    if (_shouldDebounce(key)) return;

    const payload = {
      error_type: data.error_type || 'uncaught_exception',
      error_message: data.error_message || data.message || '',
      stack_trace: data.stack || data.stack_trace || null,
      url: data.url || window.location.href,
      user_agent: data.user_agent || navigator.userAgent,
      component_stack: data.component_stack || null,
      boundary: data.boundary || false,
      metadata: data.metadata || {},
    };

    // Use fetch with keepalive so it works even during page unload
    fetch(`${API}/error-log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => { /* silent — never block on error reporting */ });
  } catch {
    // Error reporting must never throw
  }
}

/**
 * Extract the most useful error message from a thrown error or Response.
 * Handles: Response objects, Error objects, plain strings, and nested detail objects.
 */
export function extractErrorMessage(error) {
  if (!error) return 'An unexpected error occurred.';

  // If it's a Response object (from fetch)
  if (error instanceof Response) {
    return 'The server returned an error. Please try again.';
  }

  // If it has a .message (standard Error)
  if (error.message) {
    // Check for common network errors
    const msg = error.message;
    if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) {
      return 'Network error — please check your internet connection and try again.';
    }
    return msg;
  }

  // If it's a string
  if (typeof error === 'string') return error;

  // If it has a detail property (some API error wrappers)
  if (error.detail) {
    if (typeof error.detail === 'string') return error.detail;
    if (error.detail?.message) return error.detail.message;
    if (error.detail?.msg) return error.detail.msg;
  }

  return 'An unexpected error occurred.';
}

/**
 * Report an error to the backend via POST /api/report-error.
 * Fire-and-forget — never throws, never blocks the UI.
 * Includes user context when available.
 */
export async function reportErrorToBackend(error, context = {}) {
  try {
    // Get user context from localStorage (best-effort)
    let userId = null;
    let email = null;
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        userId = user.id || user._id || null;
        email = user.email || null;
      }
    } catch { /* ignore */ }

    const token = localStorage.getItem('auth_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const payload = {
      error_type: context.operation || 'frontend_error',
      message: extractErrorMessage(error),
      location: context.page || window.location.pathname,
      failing_operation: context.operation || null,
      stack: error?.stack || null,
      user_agent: navigator.userAgent,
      trust_id: context.trustId || null,
      context: {
        ...context,
        userId,
        email,
      },
    };

    // Fire-and-forget — use sendBeacon if available for reliability on unloads
    if (navigator.sendBeacon) {
      const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
      navigator.sendBeacon(`${API}/report-error`, blob);
    } else {
      fetch(`${API}/report-error`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(() => { /* silent — never block on error reporting */ });
    }
  } catch {
    // Error reporting must never throw
  }
}

/**
 * Show an error toast with actionable guidance and auto-report to backend.
 *
 * @param {object} toast - The react-toastify toast instance
 * @param {Error|string|object} error - The error that was caught
 * @param {object} context - Optional context: { operation, page, trustId, silent }
 *                           If `silent` is true, don't report to backend (just show toast)
 *
 * The toast message will always include a clear next step for the user.
 * If the error doesn't contain actionable info, the fallback is:
 * "We couldn't complete this action. Please try again, or contact support@trustoffice.app for help."
 */
export function showError(toast, error, context = {}) {
  const rawMessage = extractErrorMessage(error);

  // Build the user-facing message with a call-to-action
  let userMessage = rawMessage;

  // If the raw message doesn't already include guidance, add the default CTA
  const hasGuidance =
    userMessage.toLowerCase().includes('try again') ||
    userMessage.toLowerCase().includes('contact') ||
    userMessage.toLowerCase().includes('support') ||
    userMessage.toLowerCase().includes('subscribe') ||
    userMessage.toLowerCase().includes('upgrade') ||
    userMessage.toLowerCase().includes('sign in') ||
    userMessage.toLowerCase().includes('log in');

  if (!hasGuidance) {
    // Add actionable next step based on error type
    if (userMessage.toLowerCase().includes('network') || userMessage.toLowerCase().includes('connection')) {
      userMessage += ' Please check your internet connection and try again.';
    } else if (userMessage.toLowerCase().includes('not found') || userMessage.includes('404')) {
      userMessage += ' This may have been moved or deleted. Try refreshing the page.';
    } else if (userMessage.toLowerCase().includes('unauthorized') || userMessage.includes('401')) {
      userMessage += ' Please sign in and try again.';
    } else if (userMessage.toLowerCase().includes('forbidden') || userMessage.includes('403')) {
      userMessage += ' Your plan may not include this feature. Contact support@trustoffice.app to upgrade.';
    } else if (userMessage.toLowerCase().includes('server error') || userMessage.includes('500')) {
      userMessage += ` Our team has been notified. If this continues, contact ${SUPPORT_EMAIL}.`;
    } else {
      userMessage += ` Please try again. If the problem continues, contact ${SUPPORT_EMAIL}.`;
    }
  }

  toast.error(userMessage, { autoClose: 8000 });

  // Auto-report to backend (unless explicitly silenced)
  if (!context.silent) {
    reportErrorToBackend(error, context);
  }
}

/**
 * Install global uncaught error and unhandled rejection handlers.
 * Call once at app startup (e.g., in App.js or index.js).
 * These report to the backend but don't show toasts (to avoid spamming the user
 * with errors from background processes they can't see).
 */
export function installGlobalErrorHandlers() {
  if (_globalHandlerInstalled) return;
  _globalHandlerInstalled = true;

  window.addEventListener('error', (event) => {
    // Report to /api/report-error (Discord alert pipeline)
    reportErrorToBackend(event.error || event.message, {
      operation: 'uncaught_exception',
      page: window.location.pathname,
    });

    // Report to /api/error-log (MongoDB log, queryable via admin API)
    reportToErrorLog({
      error_type: 'uncaught_exception',
      error_message: event.message || (event.error && event.error.message) || 'Uncaught error',
      stack: (event.error && event.error.stack) || null,
      url: window.location.href,
      user_agent: navigator.userAgent,
      metadata: {
        filename: event.filename || null,
        lineno: event.lineno || null,
        colno: event.colno || null,
      },
    }, 'uncaught_exception');
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    const message = (reason && reason.message) || String(reason) || 'Unhandled promise rejection';
    const stack = (reason && reason.stack) || null;

    // Report to /api/report-error (Discord alert pipeline)
    reportErrorToBackend(reason, {
      operation: 'unhandled_promise_rejection',
      page: window.location.pathname,
    });

    // Report to /api/error-log (MongoDB log, queryable via admin API)
    reportToErrorLog({
      error_type: 'unhandled_promise_rejection',
      error_message: message,
      stack: stack,
      url: window.location.href,
      user_agent: navigator.userAgent,
      metadata: {},
    }, 'unhandled_promise_rejection');
  });
}