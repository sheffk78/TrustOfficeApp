const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

// Helper to get auth headers including localStorage token as fallback
export const getAuthHeaders = () => {
  const token = localStorage.getItem('auth_token');
  const headers = {
    'Content-Type': 'application/json'
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
};

// Robust POST request for auth endpoints (works on mobile)
export const authPost = async (endpoint, data) => {
  const url = `${API}${endpoint}`;
  const body = JSON.stringify(data);
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: body
    });
    
    // Read response as text first (more reliable on mobile)
    const responseText = await response.text();
    
    let responseData = {};
    if (responseText) {
      try {
        responseData = JSON.parse(responseText);
      } catch (e) {
        console.error('Failed to parse response:', responseText);
        throw new Error('Invalid server response');
      }
    }
    
    if (!response.ok) {
      throw new Error(responseData.detail || `Request failed with status ${response.status}`);
    }
    
    return responseData;
  } catch (error) {
    // Check if it's a network error vs server error
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      throw new Error('Network error - please check your connection');
    }
    throw error;
  }
};

// Generic fetch with auth
export const fetchWithAuth = async (endpoint, options = {}) => {
  const defaultOptions = {
    credentials: 'include',
    headers: getAuthHeaders()
  };
  
  const response = await fetch(`${API}${endpoint}`, {
    ...defaultOptions,
    ...options,
    headers: {
      ...defaultOptions.headers,
      ...options.headers
    }
  });
  
  // Handle 402 Payment Required (subscription expired)
  if (response.status === 402) {
    // Emit a custom event for subscription expiration
    window.dispatchEvent(new CustomEvent('subscription-expired'));
  }
  
  return response;
};
