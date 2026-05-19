import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

export default function AuthCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setUser, setLoading, loadTrusts, loadSubscriptionState } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    // Use ref to prevent double processing in StrictMode
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      // Security: OAuth callback now sends a one-time authorization code instead of a JWT in the URL.
      // The code is exchanged for the JWT via POST /api/auth/session (no token in browser history/referrer).
      const code = searchParams.get('code');
      const redirect = searchParams.get('redirect') || '/dashboard';
      const error = searchParams.get('error');
      
      console.log('[AuthCallback] Processing:', { hasCode: !!code, redirect, error });
      
      // Handle OAuth errors
      if (error) {
        const errorMessages = {
          'oauth_failed': 'Google sign-in was cancelled or failed',
          'missing_params': 'Invalid callback parameters',
          'invalid_state': 'Security verification failed. Please try again.',
          'state_expired': 'Session expired. Please try signing in again.',
          'token_exchange_failed': 'Failed to complete authentication',
          'no_access_token': 'Failed to get access from Google',
          'userinfo_failed': 'Failed to get your profile information',
          'no_email': 'Could not retrieve your email from Google',
          'network_error': 'Network error. Please check your connection.',
          'unexpected_error': 'An unexpected error occurred'
        };
        toast.error(errorMessages[error] || 'Authentication failed');
        navigate('/login', { replace: true });
        return;
      }
      
      // Handle custom Google OAuth (authorization code in URL)
      if (code) {
        try {
          setLoading(true);
          
          // Exchange the one-time auth code for a JWT + user data
          const response = await fetch(`${process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app'}/api/auth/session`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include', // Include cookies (session_token is set by backend)
            body: JSON.stringify({ code })
          });
          
          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            console.error('[AuthCallback] Auth code exchange failed:', response.status, errorData);
            throw new Error(errorData.detail || 'Authentication failed');
          }
          
          const data = await response.json();
          console.log('[AuthCallback] User loaded:', data.user?.email);
          
          // Security: Store token in localStorage for the current session.
          // The HttpOnly session_cookie is also set by the backend — this is the
          // Authorization header fallback used by api.js. Both mechanisms work together.
          if (data.token) {
            localStorage.setItem('auth_token', data.token);
          }
          
          setUser(data.user);
          
          // Load trusts and subscription state (pass email for admin override)
          await Promise.all([loadTrusts(), loadSubscriptionState(data.user.email)]);
          
          toast.success('Welcome!');
          
          console.log('[AuthCallback] Redirecting to:', redirect);
          navigate(redirect, { replace: true });
          return;
        } catch (err) {
          console.error('[AuthCallback] Error:', err);
          toast.error('Authentication failed');
          localStorage.removeItem('auth_token');
          hasProcessed.current = false; // Allow retry if user goes back
          navigate('/login', { replace: true });
        } finally {
          setLoading(false);
        }
        return;
      }
      
      // No code or error — invalid callback
      toast.error('Authentication failed');
      navigate('/', { replace: true });
    };

    processAuth();
  }, [navigate, setUser, setLoading, loadTrusts, loadSubscriptionState, searchParams]);

  return (
    <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto mb-4"></div>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Completing Sign In
        </p>
      </div>
    </div>
  );
}