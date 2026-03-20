import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

export default function AuthCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { exchangeSession, setUser, setLoading, loadTrusts, loadSubscriptionState } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    // Use ref to prevent double processing in StrictMode
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      // Check for custom Google OAuth callback (token in query params)
      const token = searchParams.get('token');
      const redirect = searchParams.get('redirect') || '/dashboard';
      const error = searchParams.get('error');
      
      console.log('[AuthCallback] Processing:', { hasToken: !!token, redirect, error });
      
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
      
      // Handle custom Google OAuth (token in URL)
      if (token) {
        try {
          setLoading(true);
          
          // Store the token
          localStorage.setItem('auth_token', token);
          console.log('[AuthCallback] Token stored, fetching user...');
          
          // Fetch user data
          const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/auth/me`, {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          });
          
          console.log('[AuthCallback] /auth/me status:', response.status);
          
          if (response.ok) {
            const userData = await response.json();
            console.log('[AuthCallback] User loaded:', userData.email);
            setUser(userData);
            
            // Load trusts and subscription state
            await Promise.all([loadTrusts(), loadSubscriptionState()]);
            
            toast.success('Welcome!');
            
            console.log('[AuthCallback] Redirecting to:', redirect);
            // Use window.location for a full page navigation to ensure clean state
            window.location.href = redirect;
            return;
          } else {
            const errorText = await response.text();
            console.error('[AuthCallback] /auth/me error:', errorText);
            throw new Error('Failed to fetch user data');
          }
        } catch (err) {
          console.error('[AuthCallback] Error:', err);
          toast.error('Authentication failed');
          localStorage.removeItem('auth_token');
          navigate('/login', { replace: true });
        } finally {
          setLoading(false);
        }
        return;
      }
      
      // Legacy: Handle Emergent OAuth callback (session_id in hash)
      const hash = window.location.hash;
      const sessionIdMatch = hash.match(/session_id=([^&]+)/);
      
      if (!sessionIdMatch) {
        toast.error('Authentication failed');
        navigate('/', { replace: true });
        return;
      }

      const sessionId = sessionIdMatch[1];

      try {
        setLoading(true);
        const data = await exchangeSession(sessionId);
        
        // Load trusts after auth
        await loadTrusts();
        
        toast.success('Welcome!');
        
        // Navigate to onboarding with user data to skip auth check
        navigate('/onboarding', { 
          replace: true,
          state: { user: data.user }
        });
      } catch (error) {
        console.error('Auth callback error:', error);
        toast.error('Authentication failed');
        navigate('/', { replace: true });
      } finally {
        setLoading(false);
      }
    };

    processAuth();
  }, [exchangeSession, navigate, setUser, setLoading, loadTrusts, loadSubscriptionState, searchParams]);

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
