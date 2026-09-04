import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';

// Post-checkout welcome (checkout-first model). After Stripe payment the
// webhook provisions the account WITHOUT a password; the welcome email has a
// set-password link. This page greets the new subscriber and routes them to
// set their password (or login if already set).
export default function PostCheckoutPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const [checking, setChecking] = useState(true);
  const [sessionValid, setSessionValid] = useState(false);

  const welcome = searchParams.get('welcome') === 'true';
  const sessionId = searchParams.get('session_id');

  useEffect(() => {
    // Give AuthContext a moment to restore any session, then decide routing.
    const t = setTimeout(() => {
      setSessionValid(Boolean(user));
      setChecking(false);
    }, 1500);
    return () => clearTimeout(t);
  }, [user]);

  const handleContinue = () => {
    if (sessionValid) {
      navigate('/dashboard', { replace: true });
    } else {
      navigate('/login', { replace: true });
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-navy/5 p-4" data-testid="post-checkout-page">
      <div className="bg-white rounded-xl shadow-lg max-w-md w-full p-8 text-center">
        <div className="text-4xl mb-4" aria-hidden="true">✓</div>
        <h1 className="text-2xl font-semibold text-navy">
          {welcome || sessionId ? 'Welcome to TrustOffice' : 'You\u2019re all set'}
        </h1>
        <p className="text-sm text-muted-foreground mt-3" data-testid="post-checkout-message">
          Your subscription is active and your account has been created. We've emailed
          you a link to set your password — check your inbox (and spam folder).
        </p>
        <div className="mt-6 space-y-3">
          <Button
            onClick={handleContinue}
            className="w-full bg-navy hover:bg-navy/90 text-white"
            data-testid="post-checkout-continue"
          >
            {sessionValid ? 'Go to your dashboard' : 'Log in to your new account'}
          </Button>
          <p className="text-xs text-muted-foreground">
            No password yet? Use "Forgot password" on the login page and enter the
            email you paid with — we'll send you a link to set one.
          </p>
        </div>
      </div>
    </div>
  );
}