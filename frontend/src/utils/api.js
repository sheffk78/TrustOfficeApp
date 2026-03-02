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
  
  // Handle 402 Payment Required (subscription expired - blocks all access)
  if (response.status === 402) {
    window.dispatchEvent(new CustomEvent('subscription-expired'));
  }
  
  // Handle 403 Forbidden (read-only mode - blocks write operations)
  // We check the X-Subscription-Status header to avoid consuming the body
  if (response.status === 403) {
    const subscriptionStatus = response.headers.get('X-Subscription-Status');
    if (subscriptionStatus) {
      // This is a subscription-related 403, dispatch event
      window.dispatchEvent(new CustomEvent('subscription-readonly', {
        detail: {
          status: subscriptionStatus
        }
      }));
    }
  }
  
  return response;
};

// Helper to check if a response is a read-only error
export const isReadOnlyError = (response) => {
  return response.status === 403;
};

// Helper to extract error message from response
export const getErrorMessage = async (response) => {
  try {
    const data = await response.json();
    return data.detail || 'An error occurred';
  } catch {
    return 'An error occurred';
  }
};
