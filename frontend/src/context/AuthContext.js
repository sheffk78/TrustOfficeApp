import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const AuthContext = createContext(null);

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

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  // Start loading as true ONLY if we have a token to validate
  // If no token, we know immediately user is not authenticated
  const [loading, setLoading] = useState(hasStoredToken());
  const [trusts, setTrusts] = useState([]);
  const [trustsLoading, setTrustsLoading] = useState(true);
  const [selectedTrust, setSelectedTrust] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [subscriptionExpired, setSubscriptionExpired] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const authCheckComplete = useRef(false);

  // Load the normalized subscription state from the new endpoint
  const loadSubscriptionState = useCallback(async (userEmail = null) => {
    console.log('[AuthContext] loadSubscriptionState called, userEmail:', userEmail);
    
    // ADMIN OVERRIDE: If user is primary admin, always grant full access
    const PRIMARY_ADMIN_EMAIL = 'contact@trustoffice.app';
    if (userEmail?.toLowerCase() === PRIMARY_ADMIN_EMAIL) {
      console.log('[AuthContext] Admin detected, granting full access');
      const adminState = {
        is_active: true,
        is_read_only: false,
        status: 'active',
        plan_type: 'forever_free',
        is_trial: false
      };
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
        console.log('[AuthContext] Subscription state loaded:', state.status, 'is_active:', state.is_active);
        setSubscription(state);
        setSubscriptionExpired(!state.is_active);
        setIsReadOnly(state.is_read_only);
        return state;
      } else {
        console.error('[AuthContext] Subscription API returned:', response.status);
        // Set default state on error so the app doesn't hang
        setSubscription({ is_active: false, is_read_only: true });
        setSubscriptionExpired(true);
        setIsReadOnly(true);
      }
    } catch (error) {
      console.error('[AuthContext] Failed to load subscription state:', error);
      // Set default state on error so the app doesn't hang
      setSubscription({ is_active: false, is_read_only: true });
      setSubscriptionExpired(true);
      setIsReadOnly(true);
    }
    return null;
  }, []);

  // Legacy method for backward compatibility
  const loadSubscription = useCallback(async () => {
    return loadSubscriptionState();
  }, [loadSubscriptionState]);

  const checkAuth = useCallback(async () => {
    console.log('[AuthContext] checkAuth called', { 
      pathname: window.location.pathname,
      hasToken: hasStoredToken(),
      authCheckComplete: authCheckComplete.current
    });
    
    // CRITICAL: If returning from OAuth callback path, skip the /me check.
    // AuthCallback will handle the token and establish the session.
    if (window.location.hash?.includes('session_id=') || 
        window.location.pathname === '/auth/callback' ||
        window.location.pathname === '/auth/google/callback') {
      console.log('[AuthContext] On callback path, skipping auth check');
      setLoading(false);
      return;
    }

    // If no token exists, no need to call the API
    if (!hasStoredToken()) {
      console.log('[AuthContext] No token, setting loading false');
      setLoading(false);
      authCheckComplete.current = true;
      return;
    }
    
    // Prevent duplicate auth checks - but allow if we have a token and no user
    if (authCheckComplete.current && user) {
      console.log('[AuthContext] Auth already complete with user');
      return;
    }

    try {
      console.log('[AuthContext] Fetching /auth/me');
      const response = await fetch(`${API}/auth/me`, {
        credentials: 'include',
        headers: getAuthHeaders()
      });
      
      if (!response.ok) {
        throw new Error('Not authenticated');
      }
      
      const userData = await response.json();
      console.log('[AuthContext] User data received:', userData.email);
      setUser(userData);
      
      // Load trusts and subscription after authentication
      console.log('[AuthContext] Loading trusts...');
      await loadTrustsInternal();
      console.log('[AuthContext] Loading subscription...');
      await loadSubscriptionState(userData.email);
      console.log('[AuthContext] All data loaded');
    } catch (error) {
      console.error('[AuthContext] Auth check failed:', error);
      setUser(null);
      localStorage.removeItem('auth_token');
    } finally {
      setLoading(false);
      authCheckComplete.current = true;
      console.log('[AuthContext] Auth check complete, loading=false');
    }
  }, [loadSubscriptionState]);

  // Internal function that doesn't depend on state
  const loadTrustsInternal = async (forceSelectNew = false) => {
    console.log('[AuthContext] loadTrustsInternal called');
    setTrustsLoading(true);
    try {
      const response = await fetch(`${API}/trusts`, {
        credentials: 'include',
        headers: getAuthHeaders()
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log('[AuthContext] Trusts loaded:', data.length);
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
      console.error('[AuthContext] Failed to load trusts:', error);
    } finally {
      setTrustsLoading(false);
      console.log('[AuthContext] trustsLoading set to false');
    }
  };

  const loadTrusts = useCallback(async () => {
    await loadTrustsInternal();
  }, []);

  const login = useCallback(async (email, password) => {
    // Use a simple fetch approach that works reliably on mobile
    const url = `${API}/auth/login`;
    const body = JSON.stringify({ email, password });
    
    const response = await fetch(url, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      credentials: 'include',
      body: body
    });
    
    // Read response text first (more reliable than .json() on mobile)
    const responseText = await response.text();
    let data = {};
    
    if (responseText) {
      try {
        data = JSON.parse(responseText);
      } catch (e) {
        throw new Error('Invalid server response');
      }
    }
    
    if (!response.ok) {
      throw new Error(data.detail || 'Login failed');
    }
    
    // Store token in localStorage
    if (data.token) {
      localStorage.setItem('auth_token', data.token);
    }
    setUser(data.user);
    return data;
  }, []);

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
    
    // Read response text first (more reliable than .json() on mobile)
    const responseText = await response.text();
    let data = {};
    
    if (responseText) {
      try {
        data = JSON.parse(responseText);
      } catch (e) {
        throw new Error('Invalid server response');
      }
    }
    
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
  }, []);

  const exchangeSession = useCallback(async (sessionId) => {
    const response = await fetch(`${API}/auth/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ session_id: sessionId })
    });
    
    if (!response.ok) {
      throw new Error('Session exchange failed');
    }
    
    const data = await response.json();
    
    // Store token in localStorage (CRITICAL for subsequent API calls)
    if (data.token) {
      localStorage.setItem('auth_token', data.token);
    }
    
    setUser(data.user);
    return data;
  }, []);

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
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // Listen for subscription expired events from API calls
  useEffect(() => {
    const handleSubscriptionExpired = () => {
      // Don't mark admin as expired
      if (user?.email?.toLowerCase() === 'contact@trustoffice.app') return;
      setSubscriptionExpired(true);
      setIsReadOnly(true);
      loadSubscriptionState(user?.email);
    };
    
    const handleSubscriptionReadOnly = (event) => {
      // Don't mark admin as read-only
      if (user?.email?.toLowerCase() === 'contact@trustoffice.app') return;
      setIsReadOnly(true);
      // Optionally refresh subscription state
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
    exchangeSession,
    seedDemoData
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
