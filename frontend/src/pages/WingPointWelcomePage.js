import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { Lock, Eye, EyeOff, ArrowRight, CheckCircle, AlertTriangle, CreditCard, LayoutDashboard, Mail, LogIn, ChevronDown, ChevronUp } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

const WINGPOINT_PACKAGES = [
  {
    name: 'Single Trust',
    price: '$3,000',
    credits: '1 trust credit',
    plan: 'Trustee',
    planPrice: '$79/mo',
    features: ['1 trust management record', 'Guided minutes templates', 'Schedule A asset tracking', 'Beneficiary management'],
  },
  {
    name: 'Estate Bundle',
    price: '$5,500',
    credits: '2 trust credits',
    plan: 'Estate',
    planPrice: '$149/mo',
    features: ['Up to 5 trusts', 'Multi-trust dashboard', 'Recurring task automation', 'Everything in Trustee'],
  },
  {
    name: 'Builder Bundle',
    price: '$9,500',
    credits: '4 trust credits',
    plan: 'Estate',
    planPrice: '$149/mo',
    features: ['Up to 5 trusts', 'Multi-trust dashboard', 'Recurring task automation', 'Everything in Trustee'],
  },
];

const FAQ_ITEMS = [
  {
    q: 'Why do I need a monthly subscription?',
    a: 'WingPoint created your trust. TrustOffice manages it: amendments, beneficiary updates, secure document storage, and access anytime. The monthly fee covers this ongoing service.',
  },
  {
    q: 'What is the $50 credit?',
    a: 'WingPoint included a $50 credit toward your first month of TrustOffice as part of your purchase.',
  },
  {
    q: 'I bought multiple trusts. Do I need a higher plan?',
    a: 'Your plan determines how many trusts you can manage. If you purchased WingPoint\'s Estate Bundle or Builder Bundle, you may need the Estate plan to manage all your trusts.',
  },
  {
    q: 'Is my trust ready?',
    a: 'Yes. Your trust was created when you purchased through WingPoint. TrustOffice is where you access and manage it.',
  },
];

export default function WingPointWelcomePage() {
  const { user, loading, subscription } = useAuth();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const action = searchParams.get('action');
  const token = searchParams.get('token');

  // Set password form state
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [settingPassword, setSettingPassword] = useState(false);
  const [tokenValid, setTokenValid] = useState(null); // null = not checked, true/false = result
  const [passwordSet, setPasswordSet] = useState(false);

  // Login form state
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [showLoginForm, setShowLoginForm] = useState(false);

  // FAQ expand state
  const [expandedFaq, setExpandedFaq] = useState(null);

  // Verify set-password token if present
  useEffect(() => {
    if (action === 'set_password' && token) {
      const verifyToken = async () => {
        try {
          const response = await fetch(`${API}/api/auth/verify-reset-token?token=${token}`);
          setTokenValid(response.ok);
        } catch (e) {
          setTokenValid(false);
        }
      };
      verifyToken();
    }
  }, [action, token]);

  // If user is logged in and we're showing set_password action, they probably already set it
  useEffect(() => {
    if (user && action === 'set_password') {
      // Redirect to the wingpoint page without the set_password params
      navigate('/wingpoint', { replace: true });
    }
  }, [user, action, navigate]);

  const handleSetPassword = async (e) => {
    e.preventDefault();
    if (password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    if (password !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    setSettingPassword(true);
    try {
      const response = await fetch(`${API}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to set password');
      }
      setPasswordSet(true);
      toast.success('Password set successfully. You can now log in.');
      // Clear the set_password params from URL
      setTimeout(() => {
        navigate('/wingpoint', { replace: true });
      }, 2000);
    } catch (error) {
      toast.error(error.message);
    } finally {
      setSettingPassword(false);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginLoading(true);
    try {
      const response = await fetch(`${API}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Login failed');
      }
      if (data.token) {
        localStorage.setItem('auth_token', data.token);
      }
      // Reload the page so AuthContext picks up the new session
      window.location.reload();
    } catch (error) {
      toast.error(error.message);
    } finally {
      setLoginLoading(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto mb-4"></div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-subtle-bg">
      {/* Top bar with TrustOffice logo */}
      <header className="bg-navy text-white py-4 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <Link to="/" className="text-xl font-bold tracking-tight">
            TrustOffice
          </Link>
          {user && (
            <Link to="/dashboard" className="text-sm text-white/70 hover:text-white transition-colors">
              Dashboard
            </Link>
          )}
          {!user && (
            <Link to="/login" className="text-sm text-white/70 hover:text-white transition-colors">
              Log in
            </Link>
          )}
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
        {/* 1. Welcome Section */}
        <section className="text-center mb-12">
          <div className="inline-block px-4 py-1.5 rounded-full bg-gold/10 border border-gold/30 mb-6">
            <span className="text-sm font-medium text-navy">WingPoint Customer</span>
          </div>
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-navy mb-4 tracking-tight">
            Welcome to TrustOffice
          </h1>
          <p className="text-lg sm:text-xl text-muted-foreground mb-3 font-medium">
            The management platform for your WingPoint trust
          </p>
          <p className="text-base text-muted-foreground max-w-2xl mx-auto mb-6">
            WingPoint created your trust. TrustOffice keeps it running: updated, secure, and accessible whenever you need it.
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold/10 border border-gold/30">
            <CreditCard className="w-4 h-4 text-navy" />
            <span className="text-sm text-navy font-medium">
              WingPoint has covered $50 of your first month as part of your purchase.
            </span>
          </div>
        </section>

        {/* 2. Package Recognition Section */}
        <section className="mb-12">
          <h2 className="text-xl sm:text-2xl font-bold text-navy text-center mb-2">
            Which package did you purchase?
          </h2>
          <p className="text-sm text-muted-foreground text-center mb-8">
            Recognize your WingPoint package below to find your matching TrustOffice plan.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6">
            {WINGPOINT_PACKAGES.map((pkg) => (
              <div
                key={pkg.name}
                className="bg-white rounded-xl border border-border p-6 flex flex-col"
              >
                <h3 className="text-lg font-bold text-navy mb-1">{pkg.name}</h3>
                <p className="text-2xl font-bold text-navy mb-1">{pkg.price}</p>
                <p className="text-sm text-muted-foreground mb-4">{pkg.credits}</p>
                <div className="px-3 py-2 rounded-lg bg-gold/10 border border-gold/30 mb-4">
                  <p className="text-xs text-muted-foreground">Maps to TrustOffice</p>
                  <p className="text-sm font-bold text-navy">{pkg.plan} plan, {pkg.planPrice}</p>
                </div>
                <ul className="space-y-2 flex-1">
                  {pkg.features.map((feat) => (
                    <li key={feat} className="flex items-start gap-2 text-sm text-muted-foreground">
                      <CheckCircle className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
                      <span>{feat}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* 3. Smart Action Section */}
        <section className="mb-12">
          <div className="bg-white rounded-xl border border-border p-6 sm:p-8">
            {!user ? (
              <NotLoggedInAction
                action={action}
                token={token}
                tokenValid={tokenValid}
                password={password}
                setPassword={setPassword}
                confirmPassword={confirmPassword}
                setConfirmPassword={setConfirmPassword}
                showPassword={showPassword}
                setShowPassword={setShowPassword}
                handleSetPassword={handleSetPassword}
                settingPassword={settingPassword}
                passwordSet={passwordSet}
                showLoginForm={showLoginForm}
                setShowLoginForm={setShowLoginForm}
                loginEmail={loginEmail}
                setLoginEmail={setLoginEmail}
                loginPassword={loginPassword}
                setLoginPassword={setLoginPassword}
                handleLogin={handleLogin}
                loginLoading={loginLoading}
                navigate={navigate}
              />
            ) : (
              <LoggedInAction
                subscription={subscription}
                navigate={navigate}
              />
            )}
          </div>
        </section>

        {/* 4. FAQ Section */}
        <section className="mb-12">
          <h2 className="text-xl sm:text-2xl font-bold text-navy text-center mb-6">
            Frequently Asked Questions
          </h2>
          <div className="max-w-3xl mx-auto space-y-3">
            {FAQ_ITEMS.map((item, idx) => (
              <div
                key={idx}
                className="bg-white rounded-lg border border-border overflow-hidden"
              >
                <button
                  onClick={() => setExpandedFaq(expandedFaq === idx ? null : idx)}
                  className="w-full flex items-center justify-between p-4 text-left hover:bg-subtle-bg/50 transition-colors"
                >
                  <span className="text-sm sm:text-base font-medium text-navy pr-4">{item.q}</span>
                  {expandedFaq === idx ? (
                    <ChevronUp className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                  )}
                </button>
                {expandedFaq === idx && (
                  <div className="px-4 pb-4 text-sm text-muted-foreground leading-relaxed">
                    {item.a}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* Footer link back to WingPoint */}
        <div className="text-center pb-8">
          <a
            href="https://wingpointtrust.com"
            className="text-sm text-muted-foreground hover:text-navy transition-colors"
          >
            wingpointtrust.com
          </a>
        </div>
      </div>
    </div>
  );
}

/* ---- Sub-components ---- */

function NotLoggedInAction({
  action, token, tokenValid,
  password, setPassword,
  confirmPassword, setConfirmPassword,
  showPassword, setShowPassword,
  handleSetPassword, settingPassword, passwordSet,
  showLoginForm, setShowLoginForm,
  loginEmail, setLoginEmail,
  loginPassword, setLoginPassword,
  handleLogin, loginLoading,
  navigate,
}) {
  // Case: set_password action with token (from email link)
  if (action === 'set_password' && token) {
    return (
      <div>
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-gold/10 border border-gold/30 flex items-center justify-center">
            <Lock className="w-5 h-5 text-navy" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-navy">Set Your Password</h3>
            <p className="text-sm text-muted-foreground">Create a password to access your TrustOffice account.</p>
          </div>
        </div>

        {tokenValid === null && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <div className="w-4 h-4 border-2 border-navy border-t-transparent animate-spin rounded-full"></div>
            Verifying your link...
          </div>
        )}

        {tokenValid === false && (
          <div className="p-4 rounded-lg bg-red-50 border border-red-200">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-red-900">This link has expired or is invalid.</p>
                <p className="text-sm text-red-700 mt-1">
                  Please check your email for a fresh setup link, or{' '}
                  <Link to="/forgot-password" className="underline font-medium">request a new one</Link>.
                </p>
              </div>
            </div>
          </div>
        )}

        {tokenValid === true && !passwordSet && (
          <form onSubmit={handleSetPassword} className="space-y-4 max-w-md">
            <div>
              <Label htmlFor="password">New Password</Label>
              <div className="relative mt-1">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  required
                  className="pr-10"
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
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <Input
                id="confirmPassword"
                type={showPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your password"
                required
                className="mt-1"
              />
            </div>
            <Button type="submit" disabled={settingPassword} className="w-full">
              {settingPassword ? 'Setting password...' : 'Set Password'}
            </Button>
          </form>
        )}

        {passwordSet && (
          <div className="p-4 rounded-lg bg-green-50 border border-green-200">
            <div className="flex items-start gap-2">
              <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-green-900">Password set successfully!</p>
                <p className="text-sm text-green-700 mt-1">You can now log in to your TrustOffice account.</p>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Case: subscribe action (WingPoint redirect asking to log in and subscribe)
  if (action === 'subscribe') {
    return (
      <div>
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-gold/10 border border-gold/30 flex items-center justify-center">
            <LogIn className="w-5 h-5 text-navy" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-navy">Log in to set up your account</h3>
            <p className="text-sm text-muted-foreground">Your trust is ready. Log in to activate your management plan.</p>
          </div>
        </div>
        <InlineLoginForm
          loginEmail={loginEmail}
          setLoginEmail={setLoginEmail}
          loginPassword={loginPassword}
          setLoginPassword={setLoginPassword}
          handleLogin={handleLogin}
          loginLoading={loginLoading}
          showLoginForm={showLoginForm}
          setShowLoginForm={setShowLoginForm}
        />
      </div>
    );
  }

  // Default: visiting from WingPoint button, no specific action
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-bold text-navy mb-4">Get started with TrustOffice</h3>

        {/* Path 1: New customer */}
        <div className="p-5 rounded-lg bg-gold/10 border border-gold/30 mb-4">
          <div className="flex items-start gap-3">
            <Mail className="w-5 h-5 text-navy flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-bold text-navy mb-1">New here? Check your email for setup instructions.</p>
              <p className="text-sm text-muted-foreground">
                We sent you an email with a link to set your password. Click the link in that email to create your account.
              </p>
            </div>
          </div>
        </div>

        {/* Path 2: Already have account */}
        <div className="p-5 rounded-lg border border-border">
          <div className="flex items-start gap-3">
            <LogIn className="w-5 h-5 text-navy flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-bold text-navy mb-1">Already have an account? Log in.</p>
              <p className="text-sm text-muted-foreground mb-4">
                If you have already set your password, log in to manage your trust and choose your plan.
              </p>
              <div className="flex flex-col sm:flex-row gap-3">
                <Button
                  onClick={() => navigate('/login?wp=1&action=subscribe&coupon=WINGPOINT50')}
                  className="w-full sm:w-auto"
                >
                  Log In
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowLoginForm(!showLoginForm)}
                  className="w-full sm:w-auto"
                >
                  {showLoginForm ? 'Hide form' : 'Log in here'}
                </Button>
              </div>
              {showLoginForm && (
                <div className="mt-4">
                  <InlineLoginForm
                    loginEmail={loginEmail}
                    setLoginEmail={setLoginEmail}
                    loginPassword={loginPassword}
                    setLoginPassword={setLoginPassword}
                    handleLogin={handleLogin}
                    loginLoading={loginLoading}
                    showLoginForm={showLoginForm}
                    setShowLoginForm={setShowLoginForm}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function InlineLoginForm({ loginEmail, setLoginEmail, loginPassword, setLoginPassword, handleLogin, loginLoading }) {
  return (
    <form onSubmit={handleLogin} className="space-y-4 max-w-md">
      <div>
        <Label htmlFor="loginEmail">Email</Label>
        <Input
          id="loginEmail"
          type="email"
          value={loginEmail}
          onChange={(e) => setLoginEmail(e.target.value)}
          placeholder="you@example.com"
          required
          className="mt-1"
        />
      </div>
      <div>
        <Label htmlFor="loginPassword">Password</Label>
        <Input
          id="loginPassword"
          type="password"
          value={loginPassword}
          onChange={(e) => setLoginPassword(e.target.value)}
          placeholder="Your password"
          required
          className="mt-1"
        />
      </div>
      <Button type="submit" disabled={loginLoading} className="w-full">
        {loginLoading ? 'Logging in...' : 'Log In'}
      </Button>
      <p className="text-xs text-muted-foreground text-center">
        <Link to="/forgot-password" className="underline">Forgot your password?</Link>
      </p>
    </form>
  );
}

function LoggedInAction({ subscription, navigate }) {
  const hasActiveSubscription = subscription?.is_active;
  const needsUpgrade = subscription?.needs_upgrade;
  const status = subscription?.status;
  const isPastDue = status === 'past_due';

  // Past due: need payment update
  if (hasActiveSubscription && isPastDue) {
    return (
      <ActionCard
        icon={<AlertTriangle className="w-5 h-5 text-navy" />}
        title="Update your payment method"
        description="Your subscription payment failed. Update your payment method to restore full access to your trust management tools."
        buttonText="Update Payment Method"
        onClick={() => navigate('/settings/billing?wp=1&action=update_payment')}
        buttonVariant="default"
      />
    );
  }

  // Needs upgrade
  if (hasActiveSubscription && needsUpgrade) {
    return (
      <ActionCard
        icon={<AlertTriangle className="w-5 h-5 text-navy" />}
        title="Upgrade your plan"
        description="You have more trusts than your current plan allows. Upgrade to continue managing all your trusts without interruption."
        buttonText="Upgrade Your Plan"
        onClick={() => navigate('/settings/billing?wp=1&action=upgrade')}
        buttonVariant="default"
      />
    );
  }

  // No active subscription
  if (!hasActiveSubscription) {
    return (
      <div className="space-y-4">
        <ActionCard
          icon={<CreditCard className="w-5 h-5 text-navy" />}
          title="Choose your management plan"
          description="Your trust is ready. Select a TrustOffice plan to start managing it. Remember, WingPoint covered $50 of your first month."
          buttonText="View Plans"
          onClick={() => navigate('/pricing?wp=1&coupon=WINGPOINT50&plan=trustee')}
          buttonVariant="default"
        />
        <div className="p-4 rounded-lg bg-gold/10 border border-gold/30">
          <p className="text-sm text-navy">
            <strong>Tip:</strong> The Trustee plan ($79/mo) is right for a single trust. The Estate plan ($149/mo) manages up to 5 trusts and is recommended if you purchased the Estate or Builder Bundle.
          </p>
        </div>
      </div>
    );
  }

  // All set: subscription active, no upgrade needed
  return (
    <ActionCard
      icon={<LayoutDashboard className="w-5 h-5 text-navy" />}
      title="You are all set!"
      description="Your TrustOffice account is active and your trust is ready to manage. Head to your dashboard to get started."
      buttonText="Go to Your Dashboard"
      onClick={() => navigate('/dashboard')}
      buttonVariant="default"
    />
  );
}

function ActionCard({ icon, title, description, buttonText, onClick, buttonVariant = 'default' }) {
  return (
    <div className="flex flex-col sm:flex-row items-start gap-4">
      <div className="w-12 h-12 rounded-full bg-gold/10 border border-gold/30 flex items-center justify-center flex-shrink-0">
        {icon}
      </div>
      <div className="flex-1">
        <h3 className="text-lg font-bold text-navy mb-2">{title}</h3>
        <p className="text-sm text-muted-foreground mb-4">{description}</p>
        <Button onClick={onClick} variant={buttonVariant} className="w-full sm:w-auto">
          {buttonText}
          <ArrowRight className="w-4 h-4 ml-2" />
        </Button>
      </div>
    </div>
  );
}