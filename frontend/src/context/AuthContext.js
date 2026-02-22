import { createContext, useContext, useState, useCallback, useEffect } from 'react';

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

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [trusts, setTrusts] = useState([]);
  const [selectedTrust, setSelectedTrust] = useState(null);

  const checkAuth = useCallback(async () => {
    // CRITICAL: If returning from OAuth callback, skip the /me check.
    // AuthCallback will exchange the session_id and establish the session first.
    if (window.location.hash?.includes('session_id=')) {
      setLoading(false);
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
      
      // Load trusts after authentication
      await loadTrustsInternal();
    } catch (error) {
      setUser(null);
      localStorage.removeItem('auth_token');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTrusts = useCallback(async () => {
    try {
      const response = await fetch(`${API}/trusts`, {
        credentials: 'include'
      });
      
      if (response.ok) {
        const data = await response.json();
        setTrusts(data);
        
        // Select first trust if none selected
        if (data.length > 0 && !selectedTrust) {
          setSelectedTrust(data[0]);
        }
      }
    } catch (error) {
      console.error('Failed to load trusts:', error);
    }
  }, [selectedTrust]);

  const login = useCallback(async (email, password) => {
    const response = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, password })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Login failed');
    }
    
    const data = await response.json();
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
        credentials: 'include'
      });
    } catch (error) {
      console.error('Logout error:', error);
    }
    
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
        credentials: 'include'
      });
      
      if (response.ok) {
        await loadTrusts();
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to seed demo data:', error);
    }
  }, [loadTrusts]);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const value = {
    user,
    setUser,
    loading,
    setLoading,
    trusts,
    setTrusts,
    selectedTrust,
    setSelectedTrust,
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
