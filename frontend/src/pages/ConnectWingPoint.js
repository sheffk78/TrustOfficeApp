import { useState, useEffect, useCallback } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { showError, reportErrorToBackend } from '@/utils/errors';
import { Mail, Lock, Eye, EyeOff, AlertCircle, X, ShieldCheck, ArrowLeft } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

// Use XMLHttpRequest for maximum mobile compatibility (matches LoginPage pattern)
const xhrPost = (url, data, headers = {}) => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.withCredentials = true; // send cookies (session_token fallback)
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Accept', 'application/json');
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));

    xhr.onreadystatechange = function () {
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

    xhr.onerror = function () {
      reject(new Error('Network error - please check your connection'));
    };

    xhr.send(JSON.stringify(data));
  });
};

const getAuthHeaders = () => {
  const token = localStorage.getItem('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const hasStoredToken = () => localStorage.getItem('auth_token') !== null;

export default function ConnectWingPoint() {
  const [searchParams] = useSearchParams();
  const { user, setUser, loadTrusts, loadSubscriptionState, loading } = useAuth();

  // URL params from WingPoint
  const redirectUrl = searchParams.get('redirect_url');
  const wpRef = searchParams.get('wp_ref');
  const trustName = searchParams.get('trust_name');

  // Local state
  const [step, setStep] = useState('checking'); // 'checking' | 'login' | 'confirm' | 'redirecting'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [confirmError, setConfirmError] = useState('');

  // Validate we have a redirect_url — without it the flow is meaningless
  const hasRedirectUrl = !!redirectUrl;

  // Determine step based on auth state once loading completes
  useEffect(() => {
    if (loading) return; // still checking auth

    // If we have a stored token AND a user object from context, go to confirm
    if (hasStoredToken() && user) {
      setStep('confirm');
    } else if (hasStoredToken() && !user) {
      // Token exists but user didn't load — token may be invalid/expired.
      // Treat as not logged in so they can log in fresh.
      setStep('login');
    } else {
      setStep('login');
    }
  }, [loading, user]);

  // ── Login handler (inline login — doesn't navigate away) ──────────────────
  const handleLogin = async (e) => {
    e.preventDefault();
    e.stopPropagation();

    if (loginLoading) return;

    setLoginError('');

    if (!email.trim()) {
      setLoginError('Please enter your email address.');
      return;
    }
    if (!password) {
      setLoginError('Please enter your password.');
      return;
    }

    setLoginLoading(true);

    try {
      const data = await xhrPost(`${API_URL}/api/auth/login`, {
        email: email.trim().toLowerCase(),
        password: password,
      });

      if (data.token) {
        localStorage.setItem('auth_token', data.token);
      }
      if (data.user) {
        setUser(data.user);
      }

      // Load trusts + subscription so the rest of the app is consistent
      await Promise.all([
        loadTrusts(),
        loadSubscriptionState(data.user?.email || data.user?.name),
      ]);

      toast.success('Welcome back');
      setStep('confirm');
    } catch (error) {
      const rawMsg = error.message || 'Login failed';
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
      if (!rawMsg.includes('401') && !rawMsg.toLowerCase().includes('invalid credentials')) {
        reportErrorToBackend(error, { operation: 'wingpoint_connect_login', page: 'ConnectWingPoint' });
      }
    } finally {
      setLoginLoading(false);
    }
  };

  // ── Confirm connection handler ────────────────────────────────────────────
  const handleConfirm = async () => {
    if (confirmLoading) return;
    if (!user) {
      setConfirmError('Your session has expired. Please log in again.');
      setStep('login');
      return;
    }
    if (!hasRedirectUrl) {
      setConfirmError('Missing redirect URL from WingPoint. Please restart the connection flow from WingPoint.');
      return;
    }

    setConfirmLoading(true);
    setConfirmError('');

    try {
      const data = await xhrPost(
        `${API_URL}/api/auth/connect/wingpoint/confirm`,
        { wp_ref: wpRef || null, trust_name: trustName || null },
        getAuthHeaders(),
      );

      // Build the redirect URL with user_id + connect_token
      const callback = new URL(redirectUrl);
      callback.searchParams.set('trustoffice_user_id', data.trustoffice_user_id);
      if (data.connect_token) {
        callback.searchParams.set('connect_token', data.connect_token);
      }

      setStep('redirecting');
      // Small delay so the user sees the redirecting state
      setTimeout(() => {
        window.location.href = callback.toString();
      }, 400);
    } catch (error) {
      const rawMsg = error.message || 'Failed to confirm connection';
      let friendlyMsg = rawMsg;
      if (rawMsg.includes('401') || rawMsg.toLowerCase().includes('not authenticated')) {
        friendlyMsg = 'Your session has expired. Please log in again to confirm the connection.';
        // Send them back to the login step
        localStorage.removeItem('auth_token');
        setUser(null);
        setStep('login');
      } else if (rawMsg.includes('Network error')) {
        friendlyMsg = 'Unable to reach TrustOffice. Please check your connection and try again.';
      }
      setConfirmError(friendlyMsg);
      toast.error(friendlyMsg);
      reportErrorToBackend(error, { operation: 'wingpoint_connect_confirm', page: 'ConnectWingPoint' });
    } finally {
      setConfirmLoading(false);
    }
  };

  // ── Loading state ──────────────────────────────────────────────────────────
  if (step === 'checking' || loading) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto mb-4"></div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading</p>
        </div>
      </div>
    );
  }

  // ── Missing redirect_url — show error ─────────────────────────────────────
  if (!hasRedirectUrl && step !== 'login') {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center p-6">
        <div className="w-full max-w-md card-trust corner-mark relative text-center">
          <AlertCircle className="w-10 h-10 text-error mx-auto mb-4" />
          <h1 className="font-serif text-2xl text-navy mb-2">Connection Error</h1>
          <p className="text-sm text-muted-foreground mb-6">
            This link is missing the required redirect information from WingPoint.
            Please go back to WingPoint and try connecting again.
          </p>
          <a
            href="https://app.wingpointtrusts.com"
            className="text-sm text-navy hover:text-navy/70 underline"
          >
            Return to WingPoint
          </a>
        </div>
      </div>
    );
  }

  // ── Redirecting state ──────────────────────────────────────────────────────
  if (step === 'redirecting') {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto mb-4"></div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            Connecting to WingPoint…
          </p>
        </div>
      </div>
    );
  }

  // ── Login step ─────────────────────────────────────────────────────────────
  if (step === 'login') {
    return (
      <div className="min-h-screen flex" data-testid="connect-wp-login">
        {/* Left side - Texture with overlay (matches LoginPage) */}
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

            {/* WingPoint connect banner */}
            <div className="mb-6 bg-gold/10 border border-gold/30 rounded-lg p-4 text-navy">
              <p className="text-sm">
                <strong>Connect to WingPoint.</strong> Log in to your TrustOffice
                account to confirm the connection.
              </p>
            </div>

            <div className="card-trust corner-mark relative">
              <h1 className="font-serif text-3xl text-navy mb-2">Sign In</h1>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground mb-8">
                Log in to connect your WingPoint account
              </p>

              <form onSubmit={handleLogin}>
                <div className="space-y-4">
                  {/* Error state */}
                  {loginError && (
                    <div className="p-3 bg-error/10 border border-error/20 flex items-start gap-2">
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
                        autoFocus
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
                    disabled={loginLoading}
                    className="w-full h-12 uppercase tracking-wider text-xs"
                  >
                    {loginLoading ? 'Signing in…' : 'Sign In & Connect'}
                  </Button>

                  {/* Google login */}
                  <Button
                    type="button"
                    onClick={() => {
                      // Preserve the connect flow params through Google OAuth
                      const connectPath = `/connect/wingpoint?${searchParams.toString()}`;
                      window.location.href = `${API_URL}/api/auth/google/login?redirect=${encodeURIComponent(connectPath)}`;
                    }}
                    className="w-full bg-white border border-navy/20 text-navy hover:bg-navy hover:text-white font-sans uppercase tracking-wider text-xs h-12"
                  >
                    <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
                      <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                      <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                      <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                      <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                    </svg>
                    Continue with Google
                  </Button>
                </div>
              </form>

              <p className="text-center text-xs text-muted-foreground mt-6">
                Need an account?{' '}
                <Link to={`/signup?${searchParams.toString()}`} className="text-navy hover:text-navy/70">
                  Sign up
                </Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Confirm step (logged in) ────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-subtle-bg flex items-center justify-center p-6" data-testid="connect-wp-confirm">
      <div className="w-full max-w-md">
        {/* Mobile logo */}
        <div className="lg:hidden mb-8 text-center">
          <img
            src="/assets/trustoffice-logo.svg"
            alt="TrustOffice"
            className="h-10 mx-auto"
          />
        </div>

        <div className="card-trust corner-mark relative">
          {/* Header */}
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-full bg-gold/10 border border-gold/30 flex items-center justify-center">
              <ShieldCheck className="w-6 h-6 text-gold" />
            </div>
            <div>
              <h1 className="font-serif text-2xl text-navy">Connect to WingPoint</h1>
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Confirm account connection
              </p>
            </div>
          </div>

          {/* Connection details card */}
          <div className="bg-subtle-bg/50 border border-navy/10 rounded-lg p-4 mb-6 space-y-3">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">
                Your TrustOffice Account
              </p>
              <p className="text-sm text-navy font-medium">{user?.email}</p>
            </div>
            <div className="h-px bg-navy/10" />
            <div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">
                Connecting To
              </p>
              <p className="text-sm text-navy font-medium">
                WingPoint{trustName ? ` — ${trustName}` : ''}
              </p>
            </div>
            {wpRef && (
              <>
                <div className="h-px bg-navy/10" />
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">
                    Reference
                  </p>
                  <p className="text-xs text-muted-foreground font-mono break-all">{wpRef}</p>
                </div>
              </>
            )}
          </div>

          {/* Explanation */}
          <p className="text-sm text-muted-foreground mb-6">
            Clicking <strong>Confirm Connection</strong> will share your TrustOffice
            user ID with WingPoint so they can link your accounts. No password or
            sensitive data is shared.
          </p>

          {/* Error state */}
          {confirmError && (
            <div className="p-3 bg-error/10 border border-error/20 flex items-start gap-2 mb-4">
              <AlertCircle className="w-4 h-4 text-error flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium text-error">Connection failed</p>
                <p className="text-xs text-error/80 mt-0.5">{confirmError}</p>
              </div>
              <button
                type="button"
                onClick={() => setConfirmError('')}
                className="text-error/60 hover:text-error flex-shrink-0"
                aria-label="Dismiss error"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Actions */}
          <Button
            onClick={handleConfirm}
            disabled={confirmLoading}
            className="w-full h-12 uppercase tracking-wider text-xs"
            data-testid="confirm-connection-btn"
          >
            {confirmLoading ? 'Confirming…' : 'Confirm Connection'}
          </Button>

          <a
            href="https://app.wingpointtrusts.com"
            className="flex items-center justify-center gap-1 text-xs text-muted-foreground hover:text-navy mt-4 transition-colors"
          >
            <ArrowLeft className="w-3 h-3" />
            Cancel and return to WingPoint
          </a>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-4">
          Logged in as {user?.email}. Not you?{' '}
          <button
            onClick={() => {
              localStorage.removeItem('auth_token');
              setUser(null);
              setStep('login');
            }}
            className="text-navy hover:text-navy/70 underline"
          >
            Log out
          </button>
        </p>
      </div>
    </div>
  );
}