import { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { showError, reportErrorToBackend } from '@/utils/errors';
import { Mail, Lock, Eye, EyeOff, AlertCircle, X } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

// Use XMLHttpRequest for maximum mobile compatibility
const xhrPost = (url, data) => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Accept', 'application/json');
    
    xhr.onreadystatechange = function() {
      if (xhr.readyState === 4) {
        try {
          const response = xhr.responseText ? JSON.parse(xhr.responseText) : {};
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(response);
          } else {
            reject(new Error(response.detail || `Request failed with status ${xhr.status}`));
          }
        } catch (e) {
          reject(new Error('Invalid server response'));
        }
      }
    };
    
    xhr.onerror = function() {
      reject(new Error('Network error - please check your connection'));
    };
    
    xhr.send(JSON.stringify(data));
  });
};

export default function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, setUser, loadTrusts, loadSubscriptionState } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  // Redirect if already logged in — use wp-aware routing so params are preserved
  useEffect(() => {
    if (!user) return;
    const wp = searchParams.get('wp');
    const action = searchParams.get('action');
    if (wp === '1' && action) {
      const coupon = searchParams.get('coupon');
      const plan = searchParams.get('plan');
      if (action === 'subscribe') {
        const params = new URLSearchParams({ wp: '1', action: 'subscribe' });
        if (coupon) params.set('coupon', coupon);
        if (plan) params.set('plan', plan);
        navigate(`/pricing?${params.toString()}`, { replace: true });
      } else if (action === 'upgrade') {
        const params = new URLSearchParams({ wp: '1', action: 'upgrade' });
        if (plan) params.set('plan', plan);
        navigate(`/billing?${params.toString()}`, { replace: true });
      } else if (action === 'resubscribe') {
        navigate('/billing?wp=1&action=resubscribe', { replace: true });
      } else if (action === 'update_payment') {
        navigate('/billing?wp=1&action=update_payment', { replace: true });
      } else {
        navigate('/dashboard', { replace: true });
      }
    } else {
      navigate('/dashboard', { replace: true });
    }
  }, [user, searchParams, navigate]);

  const handleEmailLogin = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (loading) return;
    
    // Clear previous errors
    setLoginError('');
    
    // Basic validation
    if (!email.trim()) {
      setLoginError('Please enter your email address.');
      return;
    }
    if (!password) {
      setLoginError('Please enter your password.');
      return;
    }
    
    setLoading(true);
    setLoginError('');
    
    try {
      const data = await xhrPost(`${API_URL}/api/auth/login`, {
        email: email.trim().toLowerCase(),
        password: password
      });
      
      if (data.token) {
        localStorage.setItem('auth_token', data.token);
      }
      if (data.user) {
        setUser(data.user);
      }
      
      // Load trusts and subscription state after successful authentication
      await Promise.all([
        loadTrusts(),
        loadSubscriptionState(data.user?.email || data.user?.name)
      ]);
      
      toast.success('Welcome back');

      // WingPoint-aware routing: check URL params for wp=1 and action
      const wp = searchParams.get('wp');
      const action = searchParams.get('action');
      if (wp === '1' && action) {
        const coupon = searchParams.get('coupon');
        const plan = searchParams.get('plan');
        if (action === 'subscribe') {
          const params = new URLSearchParams({ wp: '1', action: 'subscribe' });
          if (coupon) params.set('coupon', coupon);
          if (plan) params.set('plan', plan);
          navigate(`/pricing?${params.toString()}`, { replace: true });
        } else if (action === 'upgrade') {
          const params = new URLSearchParams({ wp: '1', action: 'upgrade' });
          if (plan) params.set('plan', plan);
          navigate(`/billing?${params.toString()}`, { replace: true });
        } else if (action === 'resubscribe') {
          navigate('/billing?wp=1&action=resubscribe', { replace: true });
        } else if (action === 'update_payment') {
          navigate('/billing?wp=1&action=update_payment', { replace: true });
        } else if (action === 'welcome') {
          navigate('/dashboard', { replace: true });
        } else {
          navigate('/dashboard', { replace: true });
        }
      } else {
        navigate('/dashboard', { replace: true });
      }
    } catch (error) {
      const rawMsg = error.message || 'Login failed';
      // Provide more user-friendly messages for common error cases
      let friendlyMsg = rawMsg;
      if (rawMsg.includes('Network error')) {
        friendlyMsg = 'Unable to connect to the server. Please check your internet connection and try again.';
      } else if (rawMsg.includes('Invalid server response')) {
        friendlyMsg = 'The server returned an unexpected response. Please try again or contact support if the problem persists.';
      } else if (rawMsg.includes('401') || rawMsg.toLowerCase().includes('invalid credentials')) {
        friendlyMsg = 'Incorrect email or password. Please verify your credentials and try again.';
      } else if (rawMsg.includes('403') || rawMsg.toLowerCase().includes('not verified')) {
        friendlyMsg = 'Your email address has not been verified. Please check your inbox for a verification email.';
      }
      setLoginError(friendlyMsg);
      toast.error(friendlyMsg);
      // Report login errors to backend (except invalid credentials — too noisy)
      if (!rawMsg.includes('401') && !rawMsg.toLowerCase().includes('invalid credentials')) {
        reportErrorToBackend(error, { operation: 'login', page: 'Login' });
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    // Use TrustOffice's own Google OAuth (branded consent screen)
    const redirectAfter = '/dashboard';
    window.location.href = `${API_URL}/api/auth/google/login?redirect=${encodeURIComponent(redirectAfter)}`;
  };

  return (
    <div className="min-h-screen flex" data-testid="login-page">
      {/* Left side - Texture with overlay */}
      <div className="hidden lg:flex lg:w-1/2 login-texture relative">
        <div className="absolute inset-0 login-overlay flex flex-col justify-center items-center p-12">
          <img 
            src="/assets/trustoffice-logo-vertical.svg"
            alt="TrustOffice"
            className="w-48 mb-8"
          />
          <p className="text-white/80 font-mono text-xs uppercase tracking-widest text-center max-w-md">
            Trust Governance Workspace
          </p>
        </div>
      </div>

      {/* Right side - Login form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-subtle-bg">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="lg:hidden mb-12 text-center">
            <img 
              src="/assets/trustoffice-logo.svg"
              alt="TrustOffice"
              className="h-10 mx-auto"
            />
          </div>

          {/* Login card with corner marks */}
          <div className="card-trust corner-mark relative">
            <h1 className="font-serif text-3xl text-navy mb-2">Sign In</h1>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground mb-8">
              Sign in to your account
            </p>

            {/* WingPoint welcome-back banner — only when ?wp=1 present */}
            {searchParams.get('wp') === '1' && (
              <div className="mb-6 bg-gold/10 border border-gold/30 rounded-lg p-4 text-navy" data-testid="wp-welcome-banner">
                <p className="text-sm">
                  Welcome back. Your WingPoint trust is waiting in your TrustOffice account. Log in to continue setting up your management plan.
                </p>
              </div>
            )}

            {/* Google login button */}
            <Button
              onClick={handleGoogleLogin}
              className="w-full mb-6 bg-white border border-navy/20 text-navy hover:bg-navy hover:text-white font-sans uppercase tracking-wider text-xs h-12"
              data-testid="google-login-btn"
            >
              <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Continue with Google
            </Button>

            {/* Divider */}
            <div className="flex items-center gap-4 mb-6">
              <div className="flex-1 h-px bg-navy/10"></div>
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Or</span>
              <div className="flex-1 h-px bg-navy/10"></div>
            </div>

            {/* Email login form */}
            <form onSubmit={handleEmailLogin}>
              <div className="space-y-4">
                {/* Error state */}
                {loginError && (
                  <div className="p-3 bg-error/10 border border-error/20 flex items-start gap-2" data-testid="login-error">
                    <AlertCircle className="w-4 h-4 text-error flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-error">Sign-in failed</p>
                      <p className="text-xs text-error/80 mt-0.5">{loginError}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setLoginError('')}
                      className="text-error/60 hover:text-error flex-shrink-0"
                      aria-label="Dismiss error"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
                <div>
                  <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Email Address
                  </Label>
                  <div className="relative mt-1">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      type="email"
                      value={email}
                      onChange={(e) => { setEmail(e.target.value); if (loginError) setLoginError(''); }}
                      className={`pl-10 input-trust ${loginError ? 'border-error/40' : ''}`}
                      placeholder="your@email.com"
                      required
                      data-testid="email-input"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between">
                    <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                      Password
                    </Label>
                    <Link 
                      to="/forgot-password" 
                      className="text-xs text-navy hover:text-navy/70"
                      data-testid="forgot-password-link"
                    >
                      Forgot password?
                    </Link>
                  </div>
                  <div className="relative mt-1">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => { setPassword(e.target.value); if (loginError) setLoginError(''); }}
                      className={`pl-10 pr-10 input-trust ${loginError ? 'border-error/40' : ''}`}
                      placeholder="Enter password"
                      required
                      data-testid="password-input"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-navy"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <Button
                  type="submit"
                  className="w-full btn-primary h-12"
                  disabled={loading}
                  data-testid="login-submit-btn"
                >
                  {loading ? 'Signing In...' : 'Sign In'}
                </Button>
              </div>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                Don't have an account?{' '}
                <Link to="/signup" className="text-navy font-medium hover:text-navy/70" data-testid="signup-link">
                  Create Account
                </Link>
              </p>
            </div>
          </div>

          {/* Footer */}
          <div className="mt-8 text-center">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Powered by TrustOffice
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
