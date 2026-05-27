import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { Mail, Lock, Eye, EyeOff } from 'lucide-react';

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
  const { user, setUser, loadTrusts, loadSubscriptionState } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  // Redirect if already logged in
  if (user) {
    navigate('/dashboard', { replace: true });
    return null;
  }

  const handleEmailLogin = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (loading) return;
    
    setLoading(true);
    
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
      navigate('/dashboard', { replace: true });
    } catch (error) {
      toast.error(error.message || 'Login failed');
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
            className="w-48 mb-8 brightness-0 invert"
          />
          <p className="text-white/80 font-mono text-xs uppercase tracking-widest text-center max-w-md">
            Trust Governance Workspace
          </p>
          <div className="mt-16 text-white/60 font-mono text-[10px] uppercase tracking-widest">
            TrustOffice
          </div>
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
              className="h-12 mx-auto dark:brightness-0 dark:invert"
            />
          </div>

          {/* Login card with corner marks */}
          <div className="card-trust corner-mark relative">
            <h1 className="font-serif text-3xl text-navy mb-2">Sign In</h1>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground mb-8">
              Sign in to your account
            </p>

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
                <div>
                  <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Email Address
                  </Label>
                  <div className="relative mt-1">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-10 input-trust"
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
                      className="text-xs text-navy hover:text-gold"
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
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-10 pr-10 input-trust"
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
                <Link to="/signup" className="text-navy font-medium hover:text-gold" data-testid="signup-link">
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
