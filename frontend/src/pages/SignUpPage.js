import { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { Mail, Lock, Eye, EyeOff, User, Gift } from 'lucide-react';

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

export default function SignUpPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setUser } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  
  // Referral code from URL params (e.g., /signup?ref=ABCD1234)
  const [referralCode, setReferralCode] = useState('');
  const [referralInfo, setReferralInfo] = useState(null);
  
  // Coupon code from URL params (e.g., /signup?coupon=WINGPOINT3M)
  const [couponCode, setCouponCode] = useState('');
  const [couponInfo, setCouponInfo] = useState(null);
  
  // WingPoint partnership params (e.g., /signup?ref=wp&wp_ref=WP-123&trust_name=Smith+Family+Trust&coupon=WINGPOINT3M)
  const [isWingPoint, setIsWingPoint] = useState(false);
  const [wingPointTrustName, setWingPointTrustName] = useState('');
  const [wingPointRef, setWingPointRef] = useState('');
  
  // Check for referral code, coupon, and WingPoint params on mount
  useEffect(() => {
    const refCode = searchParams.get('ref');
    
    // WingPoint partnership flow
    if (refCode && refCode.toLowerCase() === 'wp') {
      setIsWingPoint(true);
      const trustName = searchParams.get('trust_name') || '';
      const wpRef = searchParams.get('wp_ref') || '';
      const coupon = searchParams.get('coupon') || 'WINGPOINT3M';
      
      setWingPointTrustName(decodeURIComponent(trustName));
      setWingPointRef(wpRef);
      
      // Auto-apply WingPoint coupon
      const couponUpper = coupon.toUpperCase();
      setCouponCode(couponUpper);
      if (couponUpper === 'WINGPOINT3M') {
        setCouponInfo({
          code: 'WINGPOINT3M',
          description: '50% off for your first 3 months',
          regularPrice: '$79/month',
          savings: 'Save $39.50/month for 3 months'
        });
      }
      
      // Store WingPoint ref for the backend
      if (wpRef) {
        sessionStorage.setItem('wp_ref', wpRef);
      }
      if (trustName) {
        sessionStorage.setItem('wp_trust_name', decodeURIComponent(trustName));
      }
    } else if (refCode) {
      setReferralCode(refCode.toUpperCase());
      validateReferralCode(refCode);
    }
    
    // Check for coupon parameter (non-WingPoint flow)
    const coupon = searchParams.get('coupon');
    if (coupon && !isWingPoint) {
      const couponUpper = coupon.toUpperCase();
      setCouponCode(couponUpper);
      
      // Set coupon info for known coupons
      if (couponUpper === 'TRUST49') {
        setCouponInfo({
          code: 'TRUST49',
          description: '$49/month for your first 3 months',
          regularPrice: '$79/month',
          savings: '$30 off per month'
        });
      } else if (couponUpper === 'WINGPOINT3M') {
        setCouponInfo({
          code: 'WINGPOINT3M',
          description: '50% off for your first 3 months',
          regularPrice: '$79/month',
          savings: 'Save $39.50/month for 3 months'
        });
      }
    }
  }, [searchParams]);
  
  const validateReferralCode = async (code) => {
    try {
      const response = await fetch(`${API_URL}/api/referrals/validate/${code}`);
      if (response.ok) {
        const data = await response.json();
        if (data.valid) {
          setReferralInfo(data);
        }
      }
    } catch (error) {
      console.error('Failed to validate referral code:', error);
    }
  };

  const handleSignUp = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    // Prevent double submission
    if (loading) return;
    
    const trimmedEmail = email.trim().toLowerCase();
    const trimmedName = name.trim();
    
    if (!trimmedEmail || !trimmedName || !password) {
      toast.error('Please fill in all fields');
      return;
    }
    
    if (password !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }

    if (password.length < 6) {
      toast.error('Password must be at least 6 characters');
      return;
    }

    setLoading(true);
    
    try {
      // Step 1: Register using XMLHttpRequest (include referral code, WingPoint ref, and trust name if present)
      const wpRef = sessionStorage.getItem('wp_ref') || null;
      const wpTrustName = sessionStorage.getItem('wp_trust_name') || null;
      await xhrPost(`${API_URL}/api/auth/register`, {
        email: trimmedEmail,
        password: password,
        name: trimmedName,
        referral_code: referralCode || null,
        wp_ref: wpRef,
        wp_trust_name: wpTrustName
      });
      
      // Step 2: Login using XMLHttpRequest
      const loginData = await xhrPost(`${API_URL}/api/auth/login`, {
        email: trimmedEmail,
        password: password
      });
      
      // Step 3: Store token and update user
      if (loginData.token) {
        localStorage.setItem('auth_token', loginData.token);
      }
      if (loginData.user) {
        setUser(loginData.user);
      }
      
      // Store coupon code for use after onboarding
      if (couponCode) {
        sessionStorage.setItem('pending_coupon', couponCode);
      }
      
      toast.success('Account created successfully');
      navigate('/onboarding');
    } catch (error) {
      console.error('Signup error:', error);
      toast.error(error.message || 'Failed to create account');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignUp = () => {
    // Use TrustOffice's own Google OAuth (branded consent screen)
    const redirectAfter = '/onboarding';
    window.location.href = `${API_URL}/api/auth/google/login?redirect=${encodeURIComponent(redirectAfter)}`;
  };

  return (
    <div className="min-h-screen flex" data-testid="signup-page">
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

      {/* Right side - Sign up form */}
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

          {/* Sign up card with corner marks */}
          <div className="card-trust corner-mark relative">
            {/* Coupon banner */}
            {couponInfo && !isWingPoint && !referralInfo && (
              <div className="bg-gradient-to-r from-green-500/20 to-emerald-100 dark:from-green-500/30 dark:to-emerald-900/30 -mx-6 -mt-6 px-6 py-4 mb-6 border-b border-green-500/30">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xl">🎉</span>
                  <span className="font-medium text-navy dark:text-white">Special Offer Applied!</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  <span className="font-semibold text-green-600 dark:text-green-400">{couponInfo.description}</span>
                  {' '}(regularly {couponInfo.regularPrice}). 
                  <span className="text-navy dark:text-white"> Applied at checkout.</span>
                </p>
              </div>
            )}
            
            {/* WingPoint partnership banner */}
            {isWingPoint && (
              <div className="bg-gradient-to-r from-navy/10 to-blue-50 dark:from-navy/30 dark:to-blue-900/30 -mx-6 -mt-6 px-6 py-5 mb-6 border-b border-navy/20">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xl">🤝</span>
                  <span className="font-medium text-navy dark:text-white">Welcome from WingPoint</span>
                </div>
                <p className="text-sm text-muted-foreground mb-2">
                  Your trust governance workspace is ready. Create your account to start managing your trust.
                </p>
                {wingPointTrustName && (
                  <p className="text-sm font-medium text-navy dark:text-white">
                    Trust: {wingPointTrustName}
                  </p>
                )}
                {couponInfo && (
                  <p className="text-sm text-green-600 dark:text-green-400 mt-1">
                    ✦ {couponInfo.description} — applied at checkout
                  </p>
                )}
              </div>
            )}
            
            {/* Referral banner */}
            {referralInfo && (
              <div className="bg-gradient-to-r from-gold/20 to-amber-100 dark:from-gold/30 dark:to-amber-900/30 -mx-6 -mt-6 px-6 py-4 mb-6 border-b border-gold/30">
                <div className="flex items-center gap-2 mb-1">
                  <Gift className="w-5 h-5 text-gold" />
                  <span className="font-medium text-navy">You've been referred!</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  {referralInfo.referrer_name} invited you to TrustOffice. 
                  Get <span className="font-semibold text-gold">{referralInfo.discount_percent}% off</span> your first payment!
                </p>
              </div>
            )}
            
            <h1 className="font-serif text-3xl text-navy mb-2">Create Account</h1>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground mb-8">
              Start managing your trusts
            </p>

            {/* Google sign up button */}
            <Button
              onClick={handleGoogleSignUp}
              className="w-full mb-6 bg-white border border-navy/20 text-navy hover:bg-navy hover:text-white font-sans uppercase tracking-wider text-xs h-12"
              data-testid="google-signup-btn"
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

            {/* Email sign up form */}
            <form onSubmit={handleSignUp}>
              <div className="space-y-4">
                <div>
                  <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Full Name
                  </Label>
                  <div className="relative mt-1">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="pl-10 input-trust"
                      placeholder="John Smith"
                      required
                      data-testid="name-input"
                    />
                  </div>
                </div>

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
                  <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Password
                  </Label>
                  <div className="relative mt-1">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-10 pr-10 input-trust"
                      placeholder="Create password"
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

                <div>
                  <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Confirm Password
                  </Label>
                  <div className="relative mt-1">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      type={showPassword ? 'text' : 'password'}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="pl-10 input-trust"
                      placeholder="Confirm password"
                      required
                      data-testid="confirm-password-input"
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  className="w-full btn-primary h-12"
                  disabled={loading}
                  data-testid="signup-submit-btn"
                >
                  {loading ? 'Creating Account...' : 'Create Account'}
                </Button>
              </div>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                Already have an account?{' '}
                <Link to="/" className="text-navy font-medium hover:text-gold" data-testid="login-link">
                  Sign In
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
