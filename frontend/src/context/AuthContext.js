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
  const [selectedTrust, setSelectedTrust] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [subscriptionExpired, setSubscriptionExpired] = useState(false);
  const authCheckComplete = useRef(false);

  const loadSubscription = useCallback(async () => {
    try {
      const response = await fetch(`${API}/subscription`, {
        credentials: 'include',
        headers: getAuthHeaders()
      });
      
      if (response.ok) {
        const subData = await response.json();
        setSubscription(subData);
        setSubscriptionExpired(!subData.is_active);
      }
    } catch (error) {
      console.error('Failed to load subscription:', error);
    }
  }, []);

  const checkAuth = useCallback(async () => {
    // Prevent duplicate auth checks
    if (authCheckComplete.current) {
      return;
    }
    
    // CRITICAL: If returning from OAuth callback, skip the /me check.
    // AuthCallback will exchange the session_id and establish the session first.
    if (window.location.hash?.includes('session_id=')) {
      setLoading(false);
      return;
    }

    // If no token exists, no need to call the API
    if (!hasStoredToken()) {
      setLoading(false);
      authCheckComplete.current = true;
      return;
    }

    try {
      const response = await fetch(`${API}/auth/me`, {
        credentials: 'include',
        headers: getAuthHeaders()
      });
      
      if (!response.ok) {
        throw new Error('Not authenticated');
      }
      
      const userData = await response.json();
      setUser(userData);
      
      // Load trusts and subscription after authentication
      await loadTrustsInternal();
      await loadSubscription();
    } catch (error) {
      setUser(null);
      localStorage.removeItem('auth_token');
    } finally {
      setLoading(false);
      authCheckComplete.current = true;
    }
  }, [loadSubscription]);

  // Internal function that doesn't depend on state
  const loadTrustsInternal = async () => {
    try {
      const response = await fetch(`${API}/trusts`, {
        credentials: 'include',
        headers: getAuthHeaders()
      });
      
      if (response.ok) {
        const data = await response.json();
        setTrusts(data);
        
        // Select first trust if none selected
        if (data.length > 0) {
          const storedTrustId = localStorage.getItem('selected_trust_id');
          const storedTrust = data.find(t => t.trust_id === storedTrustId);
          setSelectedTrust(storedTrust || data[0]);
        }
      }
    } catch (error) {
      console.error('Failed to load trusts:', error);
    }
  };

  const loadTrusts = useCallback(async () => {
    await loadTrustsInternal();
  }, []);

  const login = useCallback(async (email, password) => {
    const response = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, password })
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      throw new Error(data.detail || 'Login failed');
    }
    
    // Store token in localStorage as backup for cookie issues
    if (data.token) {
      localStorage.setItem('auth_token', data.token);
    }
    setUser(data.user);
    return data;
  }, []);

  const register = useCallback(async (email, password, name) => {
    const response = await fetch(`${API}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, name })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Registration failed');
    }
    
    return await response.json();
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
      setSubscriptionExpired(true);
      loadSubscription();
    };
    
    window.addEventListener('subscription-expired', handleSubscriptionExpired);
    return () => {
      window.removeEventListener('subscription-expired', handleSubscriptionExpired);
    };
  }, [loadSubscription]);

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
    selectedTrust,
    setSelectedTrust: selectTrust,
    subscription,
    subscriptionExpired,
    loadSubscription,
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
