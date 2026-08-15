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

const useSubscriptionState = ({ setSubscription, setSubscriptionExpired, setIsReadOnly }) => {
  const loadSubscriptionState = useCallback(async (userEmail = null) => {
    // ADMIN OVERRIDE: If user is primary admin, always grant full access
    if (isPrimaryAdmin(userEmail)) {
      const adminState = buildAdminSubscriptionState();
      setSubscription(adminState);
      setSubscriptionExpired(false);
      setIsReadOnly(false);
      return adminState;
    }

    try {
      const response = await fetch(`${API}/subscription/state`, {
        credentials: 'include',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const state = await response.json();
        setSubscription(state);
        setSubscriptionExpired(!state.is_active);
        setIsReadOnly(state.is_read_only);
        return state;
      } else {
        console.error('[AuthContext] Subscription API returned:', response.status);
        applyErrorSubscriptionState(setSubscription, setSubscriptionExpired, setIsReadOnly);
      }
    } catch (error) {
      reportErrorToBackend(error, { operation: 'load_subscription', page: window.location.pathname, severity: 'major' });
      console.error('[AuthContext] Failed to load subscription state:', error);
      applyErrorSubscriptionState(setSubscription, setSubscriptionExpired, setIsReadOnly);
    }
    return null;
  }, [setSubscription, setSubscriptionExpired, setIsReadOnly]);

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
      reportErrorToBackend(error, { operation: 'load_trusts', page: window.location.pathname, severity: 'major' });
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
        // Don't report auth_check as 'major' on public pages — a 401 is
        // expected when visiting /pricing, /login, /signup, etc. without a
        // token. Only report as 'major' on authenticated pages.
        const publicPages = ['/pricing', '/login', '/signup', '/forgot-password', '/trust-governance-offer'];
        const isPublicPage = publicPages.some(p => window.location.pathname.startsWith(p));
        if (!isPublicPage) {
          reportErrorToBackend(error, { operation: 'auth_check', page: window.location.pathname, severity: 'major' });
        }
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

    return () => {
      window.removeEventListener('subscription-expired', handleSubscriptionExpired);
      window.removeEventListener('subscription-readonly', handleSubscriptionReadOnly);
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