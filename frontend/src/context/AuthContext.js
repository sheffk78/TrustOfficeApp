import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { reportErrorToBackend } from '@/utils/errors';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';
const API = `${BACKEND_URL}/api`;

const AuthContext = createContext(null);

const PRIMARY_ADMIN_EMAIL = 'contact@trustoffice.app';

// ==================== Auth helpers ====================

// Helper to get auth headers including localStorage token as fallback
const getAuthHeaders = () => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    return { 'Authorization': `Bearer ${token}` };
  }
  return {};
};

// Check if we have a token to validate (synchronous check)
const hasStoredToken = () => {
  return localStorage.getItem('auth_token') !== null;
};

// Public routes that don't require authentication (mirrors App.js routes
// that are NOT wrapped in ProtectedRoute / SubscriptionProtectedRoute).
// A 401 from /auth/me on these pages is expected (visitor with a stale token)
// and must NOT be reported as a 'major' auth_check error.
const PUBLIC_PAGES = [
  '/',
  '/login',
  '/signup',
  '/register',
  '/wingpoint',
  '/connect/wingpoint',
  '/pricing',
  '/affiliate',
  '/help',
  '/about',
  '/forgot-password',
  '/reset-password',
  '/successor-access',
  '/trust-governance-offer',
  '/auth/callback',
  '/auth/google/callback',
];

const isPublicPage = (pathname) => {
  return PUBLIC_PAGES.some(p => {
    if (p === '/') return pathname === '/';
    // /successor-access has a :token param, so use startsWith
    return pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p);
  });
};

// Named predicate: is the given email the primary admin?
const isPrimaryAdmin = (email) => {
  return Boolean(email) && email.toLowerCase() === PRIMARY_ADMIN_EMAIL;
};

// Named predicate: are we currently on an OAuth callback route?
const isOAuthCallbackRoute = () => {
  const hash = window.location.hash;
  const pathname = window.location.pathname;
  return (
    (hash && hash.includes('session_id=')) ||
    pathname === '/auth/callback' ||
    pathname === '/auth/google/callback'
  );
};

// Named predicate: has the auth check already completed with a known user?
const isAuthCheckAlreadyDone = (authCheckComplete, user) => {
  return authCheckComplete && Boolean(user);
};

// Canonical admin override subscription state
const buildAdminSubscriptionState = () => ({
  is_active: true,
  is_read_only: false,
  status: 'active',
  plan_type: 'forever_free',
  is_trial: false,
  trust_count: 0,
  trust_limit: 999,
  needs_upgrade: false,
});

// Default subscription state used on API error so the app doesn't hang
const DEFAULT_ERROR_SUBSCRIPTION = Object.freeze({
  is_active: false,
  is_read_only: true,
  trust_count: 0,
  trust_limit: 0,
  needs_upgrade: false,
});

// Apply the error subscription state to the setters
const applyErrorSubscriptionState = (setSubscription, setSubscriptionExpired, setIsReadOnly) => {
  setSubscription({ ...DEFAULT_ERROR_SUBSCRIPTION });
  setSubscriptionExpired(true);
  setIsReadOnly(true);
};

// Parse a fetch response as JSON, tolerant of empty bodies (mobile-friendly).
// Returns `{}` for empty bodies; throws Error('Invalid server response') on bad JSON.
const parseJsonResponse = async (response) => {
  const responseText = await response.text();
  if (!responseText) {
    return {};
  }
  try {
    return JSON.parse(responseText);
  } catch (e) {
    throw new Error('Invalid server response');
  }
};

// ==================== useAuthActions hook ====================
// Encapsulates the auth action callbacks (login/register/logout/exchange/seed)
// so the AuthProvider component body stays flat and readable.

const useAuthActions = ({
  setUser,
  setTrusts,
  setSelectedTrust,
  loadTrustsInternal,
}) => {
  const login = useCallback(async (email, password) => {
    // Use a simple fetch approach that works reliably on mobile
    const url = `${API}/auth/login`;
    const body = JSON.stringify({ email, password });

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        credentials: 'include',
        body: body
      });

      const data = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(data.detail || 'Login failed');
      }

      // Store token in localStorage
      if (data.token) {
        localStorage.setItem('auth_token', data.token);
      }
      setUser(data.user);
      return data;
    } catch (error) {
      reportErrorToBackend(error, { operation: 'auth_login', page: window.location.pathname, severity: 'major' });
      throw error;
    }
  }, [setUser]);

  const register = useCallback(async (email, password, name) => {
    // Use a simple fetch approach that works reliably on mobile
    const url = `${API}/auth/register`;
    const body = JSON.stringify({ email, password, name });

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: body
    });

    const data = await parseJsonResponse(response);

    if (!response.ok) {
      throw new Error(data.detail || 'Registration failed');
    }

    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch(`${API}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
        headers: getAuthHeaders()
      });
    } catch (error) {
      console.error('Logout error:', error);
    }

    localStorage.removeItem('auth_token');
    localStorage.removeItem('selected_trust_id');
    setUser(null);
    setTrusts([]);
    setSelectedTrust(null);
  }, [setUser, setTrusts, setSelectedTrust]);

  const exchangeAuthCode = useCallback(async (code) => {
    // Security: Exchange one-time authorization code for JWT.
    // This replaces the old JWT-in-URL OAuth flow and the session_id (Emergent) flow.
    const response = await fetch(`${API}/auth/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ code })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Auth code exchange failed');
    }

    const data = await response.json();

    // Security: Store token in localStorage for Authorization header fallback.
    // The HttpOnly session_cookie is also set by the backend response.
    if (data.token) {
      localStorage.setItem('auth_token', data.token);
    }

    setUser(data.user);
    return data;
  }, [setUser]);

  const seedDemoData = useCallback(async () => {
    try {
      const response = await fetch(`${API}/demo/seed`, {
        method: 'POST',
        credentials: 'include',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const result = await response.json();
        await loadTrustsInternal();
        return result;
      }
      return { seeded: false, message: 'Request failed' };
    } catch (error) {
      console.error('Failed to seed demo data:', error);
      return { seeded: false, message: error.message };
    }
  }, [loadTrustsInternal]);

  return { login, register, logout, exchangeAuthCode, seedDemoData };
};

// ─── useSubscriptionState: extracted from AuthProvider ──────────────
// Encapsulates subscription state loading + admin override logic.
//
// Resilience: A paid user with an active subscription should NEVER be locked
// out of saving because of a transient network issue. To that end:
//   1. Transient API failures (non-401/403) are retried up to 2 times with
//      a 1.5s delay before falling back.
//   2. On retry exhaustion, if we have a previously-cached active subscription
//      state, we keep it instead of forcing read-only mode (soft fallback).
//      Only the very first load (no cached state) falls back to read-only.
//   3. If the user ends up read-only due to an API error (not a genuine
//      expired/inactive subscription), a 60s periodic re-check timer keeps
//      retrying. When it succeeds and shows the user is active, write access
//      is automatically restored.

const SUBSCRIPTION_MAX_RETRIES = 2;
const SUBSCRIPTION_RETRY_DELAY_MS = 1500;
const SUBSCRIPTION_RECHECK_INTERVAL_MS = 60000;

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Fetch the subscription state once. Returns { state, status } where:
//   - status: 'ok' (200 response) | 'auth' (401/403) | 'error' (anything else)
//   - state:  parsed JSON body on 'ok', null otherwise
const fetchSubscriptionStateOnce = async () => {
  const response = await fetch(`${API}/subscription/state`, {
    credentials: 'include',
    headers: getAuthHeaders(),
  });

  if (response.ok) {
    const state = await response.json();
    return { state, status: 'ok' };
  }

  if (response.status === 401 || response.status === 403) {
    return { state: null, status: 'auth' };
  }

  // Any other non-ok status (500, 502, 503, timeout-as-500, etc.) is transient.
  return { state: null, status: 'error' };
};

const useSubscriptionState = ({ setSubscription, setSubscriptionExpired, setIsReadOnly }) => {
  // Refs survive re-renders without being stale inside async callbacks.
  const lastGoodStateRef = useRef(null);   // most recent successful state
  const recheckTimerRef = useRef(null);      // 60s periodic re-check interval id
  const isReadOnlyDueToErrorRef = useRef(false); // true only when read-only is from API failure, not genuine expiry

  // Apply a successful subscription state to all setters + cache it.
  const applyGoodSubscriptionState = useCallback((state) => {
    lastGoodStateRef.current = state;
    isReadOnlyDueToErrorRef.current = false;
    setSubscription(state);
    setSubscriptionExpired(!state.is_active);
    setIsReadOnly(state.is_read_only);
    // A successful load means any periodic re-check can stop.
    if (recheckTimerRef.current) {
      clearInterval(recheckTimerRef.current);
      recheckTimerRef.current = null;
    }
  }, [setSubscription, setSubscriptionExpired, setIsReadOnly]);

  // Start (or restart) the 60s periodic re-check timer. Used only when the
  // user has been forced into read-only mode by an API error.
  const startPeriodicRecheck = useCallback((userEmail) => {
    // Don't stack timers
    if (recheckTimerRef.current) return;
    recheckTimerRef.current = setInterval(() => {
      // Fire-and-forget; loadSubscriptionState handles the retry/fallback logic
      loadSubscriptionStateRef.current(userEmail);
    }, SUBSCRIPTION_RECHECK_INTERVAL_MS);
  }, []);

  // Keep a ref to loadSubscriptionState so the interval always calls the latest
  // version without re-creating the interval on every render.
  const loadSubscriptionStateRef = useRef(null);

  const loadSubscriptionState = useCallback(async (userEmail = null) => {
    // ADMIN OVERRIDE: If user is primary admin, always grant full access
    if (isPrimaryAdmin(userEmail)) {
      const adminState = buildAdminSubscriptionState();
      applyGoodSubscriptionState(adminState);
      return adminState;
    }

    let lastError = null;
    let lastStatus = null;

    // Retry loop: try up to (1 + SUBSCRIPTION_MAX_RETRIES) attempts.
    for (let attempt = 0; attempt <= SUBSCRIPTION_MAX_RETRIES; attempt++) {
      try {
        const { state, status } = await fetchSubscriptionStateOnce();

        if (status === 'ok') {
          // Success — apply the real state and stop any re-check timer.
          applyGoodSubscriptionState(state);
          return state;
        }

        if (status === 'auth') {
          // 401/403 — auth failure, not transient. Don't retry, don't re-check.
          // Apply the error state directly (existing behavior for auth failures).
          lastStatus = 'auth';
          lastError = new Error(`Subscription API returned ${status === 'auth' ? '401/403' : 'error'}`);
          break; // out of retry loop
        }

        // status === 'error' — transient failure, retry if attempts remain
        lastStatus = 'error';
        lastError = new Error('Subscription API transient failure');
        if (attempt < SUBSCRIPTION_MAX_RETRIES) {
          await delay(SUBSCRIPTION_RETRY_DELAY_MS);
        }
      } catch (error) {
        // Network error / timeout — transient, retry if attempts remain
        lastStatus = 'error';
        lastError = error;
        if (attempt < SUBSCRIPTION_MAX_RETRIES) {
          await delay(SUBSCRIPTION_RETRY_DELAY_MS);
        }
      }
    }

    // ── Retry exhaustion / non-retriable failure — apply fallback ──

    // Auth failures (401/403) always fall back to the hard error state.
    if (lastStatus === 'auth') {
      reportErrorToBackend(lastError, { operation: 'load_subscription', page: window.location.pathname, severity: 'major' });
      console.error('[AuthContext] Subscription API returned auth failure (401/403)');
      applyErrorSubscriptionState(setSubscription, setSubscriptionExpired, setIsReadOnly);
      return null;
    }

    // Transient failure after all retries: report once, then soft-fallback.
    reportErrorToBackend(lastError, { operation: 'load_subscription', page: window.location.pathname, severity: 'major' });
    console.warn('[AuthContext] Subscription state fetch failed after retries, using fallback');

    // Soft fallback: if we have a previously-cached active state, keep it so
    // the user isn't locked out by a transient blip. Only fall back to
    // read-only if there's no previous good state (first load).
    const cached = lastGoodStateRef.current;
    if (cached && cached.is_active && !cached.is_read_only) {
      // Keep the user's previous active state — don't lock them out.
      // Mark that we're in an error-induced state so the re-check timer kicks in.
      isReadOnlyDueToErrorRef.current = false; // user is NOT read-only, so no timer needed
      setSubscription({ ...cached });
      setSubscriptionExpired(false);
      setIsReadOnly(false);
      // Still start a background re-check so we pick up real changes eventually.
      startPeriodicRecheck(userEmail);
      return { ...cached };
    }

    // No cached active state (first load) — fall back to read-only error state
    // and start the periodic re-check so we can recover when the API comes back.
    applyErrorSubscriptionState(setSubscription, setSubscriptionExpired, setIsReadOnly);
    isReadOnlyDueToErrorRef.current = true;
    startPeriodicRecheck(userEmail);
    return null;
  }, [setSubscription, setSubscriptionExpired, setIsReadOnly, applyGoodSubscriptionState, startPeriodicRecheck]);

  // Keep the ref in sync so the periodic re-check calls the latest closure.
  loadSubscriptionStateRef.current = loadSubscriptionState;

  // Clean up the periodic re-check timer on unmount.
  useEffect(() => {
    return () => {
      if (recheckTimerRef.current) {
        clearInterval(recheckTimerRef.current);
        recheckTimerRef.current = null;
      }
    };
  }, []);

  return { loadSubscriptionState };
};

// ─── useTrustsLoader: extracted from AuthProvider ───────────────────
// Encapsulates trust loading + selection persistence.

const useTrustsLoader = ({ setTrusts, setTrustsLoading, setSelectedTrust, selectedTrust }) => {
  const loadTrustsInternal = useCallback(async (forceSelectNew = false) => {
    setTrustsLoading(true);
    try {
      const response = await fetch(`${API}/trusts`, {
        credentials: 'include',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setTrusts(data);

        // Select first trust if none selected, or if forced
        if (data.length > 0 && (!selectedTrust || forceSelectNew)) {
          const storedTrustId = localStorage.getItem('selected_trust_id');
          const storedTrust = data.find(t => t.trust_id === storedTrustId);
          if (!selectedTrust) {
            setSelectedTrust(storedTrust || data[0]);
          }
        }
      } else {
        console.error('[AuthContext] Trusts API returned:', response.status);
      }
    } catch (error) {
      // Transient network errors (Failed to fetch) are NOT application bugs.
      // Don't report them to the backend error pipeline.
      const isNetworkError = error && error.message && (
        error.message.includes('Failed to fetch') ||
        error.message.includes('NetworkError') ||
        error.message.includes('network')
      );
      if (!isNetworkError) {
        reportErrorToBackend(error, { operation: 'load_trusts', page: window.location.pathname, severity: 'major' });
      }
      console.error('[AuthContext] Failed to load trusts:', error);
    } finally {
      setTrustsLoading(false);
    }
  }, [setTrusts, setTrustsLoading, setSelectedTrust, selectedTrust]);

  const loadTrusts = useCallback(async () => {
    await loadTrustsInternal();
  }, [loadTrustsInternal]);

  return { loadTrustsInternal, loadTrusts };
};

// ─── useAuthCheck: extracted from AuthProvider ───────────────────────
// Encapsulates the initial auth-check flow (skip on callback routes, validate
// token, load trusts + subscription after success).

const useAuthCheck = ({
  user,
  setUser,
  setLoading,
  setTrustsLoading,
  authCheckComplete,
  loadTrustsInternal,
  loadSubscriptionState,
}) => {
  const checkAuth = useCallback(async () => {
    // CRITICAL: If returning from OAuth callback path, skip the /me check.
    if (isOAuthCallbackRoute()) {
      setLoading(false);
      setTrustsLoading(false);
      return;
    }

    // If no token exists, no need to call the API
    if (!hasStoredToken()) {
      setLoading(false);
      setTrustsLoading(false);
      authCheckComplete.current = true;
      return;
    }

    // Skip the /auth/me check entirely on public pages. A visitor with a
    // stale token on /pricing, /login, /signup, etc. doesn't need auth —
    // calling /auth/me just produces an expected 401 that gets reported as
    // a spurious 'auth_check' error. Clear the stale token silently and
    // let the public page render without authentication.
    if (isPublicPage(window.location.pathname)) {
      console.info('[AuthContext] Skipping auth check on public page:', window.location.pathname);
      localStorage.removeItem('auth_token');
      setLoading(false);
      setTrustsLoading(false);
      authCheckComplete.current = true;
      return;
    }

    // Prevent duplicate auth checks - but allow if we have a token and no user
    if (isAuthCheckAlreadyDone(authCheckComplete.current, user)) {
      return;
    }

    try {
      const response = await fetch(`${API}/auth/me`, {
        credentials: 'include',
        headers: getAuthHeaders()
      });

      if (!response.ok) {
        // Only clear the token on 401 (unauthorized) — the token is truly invalid.
        // On 5xx or other errors, keep the token and let the user stay logged in
        // (transient backend failures should NOT wipe the session).
        if (response.status === 401) {
          throw new Error('Not authenticated');
        }
        // Server error (5xx) — don't wipe the session, just log and stop loading
        console.error('[AuthContext] Auth check returned status:', response.status, '— keeping session');
        setLoading(false);
        authCheckComplete.current = true;
        return;
      }

      const userData = await response.json();
      setUser(userData);

      // Load trusts and subscription after authentication
      await loadTrustsInternal();
      await loadSubscriptionState(userData.email);
    } catch (error) {
      // Network errors (fetch throws) should NOT wipe the token — the backend may
      // be temporarily unreachable. Only wipe on explicit 401 (caught above).
      if (error.message === 'Not authenticated') {
        // We should only reach here on authenticated (non-public) pages because
        // public pages skip the /auth/me call entirely (see isPublicPage guard
        // above). Report the 401 as an auth_check error so we can detect
        // real auth regressions — but an expired session on a protected page
        // is a normal user flow (token expiry, cookie loss), not a defect.
        // The 401 already clears the session and routes to login, so report
        // at 'info' severity instead of 'major' to avoid paging on every expiry.
        reportErrorToBackend(error, { operation: 'auth_check', page: window.location.pathname, severity: 'info' });
        console.error('[AuthContext] Auth check failed: token invalid');
        setUser(null);
        localStorage.removeItem('auth_token');
      } else {
        // Network error — keep token, user stays logged in with cached data
        console.error('[AuthContext] Auth check network error (keeping session):', error.message);
      }
    } finally {
      setLoading(false);
      authCheckComplete.current = true;
    }
  }, [user, setUser, setLoading, setTrustsLoading, authCheckComplete, loadTrustsInternal, loadSubscriptionState]);

  return { checkAuth };
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  // Start loading as true ONLY if we have a token to validate
  const [loading, setLoading] = useState(hasStoredToken());
  const [trusts, setTrusts] = useState([]);
  const [trustsLoading, setTrustsLoading] = useState(true);
  const [selectedTrust, setSelectedTrust] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [subscriptionExpired, setSubscriptionExpired] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const authCheckComplete = useRef(false);

  // Subscription state loader
  const { loadSubscriptionState } = useSubscriptionState({
    setSubscription, setSubscriptionExpired, setIsReadOnly,
  });

  // Trusts loader (depends on selectedTrust)
  const { loadTrustsInternal, loadTrusts } = useTrustsLoader({
    setTrusts, setTrustsLoading, setSelectedTrust, selectedTrust,
  });

  // Auth check (depends on user + loaders)
  const { checkAuth } = useAuthCheck({
    user, setUser, setLoading, setTrustsLoading, authCheckComplete,
    loadTrustsInternal, loadSubscriptionState,
  });

  // Auth actions (login/register/logout/etc.)
  const { login, register, logout, exchangeAuthCode, seedDemoData } = useAuthActions({
    setUser,
    setTrusts,
    setSelectedTrust,
    loadTrustsInternal,
  });

  // Legacy method for backward compatibility
  const loadSubscription = useCallback(async () => {
    return loadSubscriptionState();
  }, [loadSubscriptionState]);

  // Initial auth check on mount
  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // Listen for session-expired events from fetchWithAuth (401 on API calls)
  // This catches expired JWTs mid-session — clears the token and redirects to login
  useEffect(() => {
    const handleSessionExpired = () => {
      // Clear the stale token
      localStorage.removeItem('auth_token');
      localStorage.removeItem('selected_trust_id');
      setUser(null);
      setTrusts([]);
      setSelectedTrust(null);
      // Redirect to login (only if not already there)
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login?reason=session-expired';
      }
    };

    window.addEventListener('session-expired', handleSessionExpired);

    return () => {
      window.removeEventListener('session-expired', handleSessionExpired);
    };
  }, [setUser, setTrusts, setSelectedTrust]);

  // Listen for subscription expired events from API calls
  useEffect(() => {
    const handleSubscriptionExpired = () => {
      if (isPrimaryAdmin(user?.email)) return;
      setSubscriptionExpired(true);
      setIsReadOnly(true);
      loadSubscriptionState(user?.email);
    };

    const handleSubscriptionReadOnly = () => {
      if (isPrimaryAdmin(user?.email)) return;
      setIsReadOnly(true);
      loadSubscriptionState(user?.email);
    };

    window.addEventListener('subscription-expired', handleSubscriptionExpired);
    window.addEventListener('subscription-readonly', handleSubscriptionReadOnly);

    // Handle session-expired (401 on authenticated API call — JWT expired/invalid)
    const handleSessionExpired = () => {
      console.warn('[AuthContext] Session expired (401 on API call) — redirecting to login');
      setUser(null);
      setTrusts([]);
      setSelectedTrust(null);
      setLoading(false);
      // Redirect to login page (preserve current path for post-login redirect)
      const currentPath = window.location.pathname;
      if (currentPath !== '/login' && currentPath !== '/signup') {
        window.location.href = `/login?redirect=${encodeURIComponent(currentPath)}`;
      }
    };
    window.addEventListener('session-expired', handleSessionExpired);

    return () => {
      window.removeEventListener('subscription-expired', handleSubscriptionExpired);
      window.removeEventListener('subscription-readonly', handleSubscriptionReadOnly);
      window.removeEventListener('session-expired', handleSessionExpired);
    };
  }, [loadSubscriptionState, user?.email]);

  // Wrapper to persist trust selection
  const selectTrust = useCallback((trust) => {
    setSelectedTrust(trust);
    if (trust) {
      localStorage.setItem('selected_trust_id', trust.trust_id);
    }
  }, []);

  const value = {
    user,
    setUser,
    loading,
    setLoading,
    trusts,
    setTrusts,
    trustsLoading,
    selectedTrust,
    setSelectedTrust: selectTrust,
    subscription,
    subscriptionExpired,
    isReadOnly,
    loadSubscription,
    loadSubscriptionState,
    checkAuth,
    loadTrusts,
    login,
    register,
    logout,
    exchangeAuthCode,
    seedDemoData,
    isStatsUser: user?.is_stats_user || false,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};