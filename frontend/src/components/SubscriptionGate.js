import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { 
  AlertTriangle, 
  CreditCard,
  Clock,
  CheckCircle
} from 'lucide-react';

/**
 * SubscriptionGate - Wraps protected content
 * 
 * BEHAVIOR (Read-Only Mode):
 * - If subscription is active (including free tier): Show content normally.
 *   Upgrade/subscription messaging is handled globally by <UpgradeBar /> at
 *   the app root (App.js), so this gate no longer renders TrialBanner or
 *   ReadOnlyBanner — those were consolidated into UpgradeBar to ensure a
 *   SINGLE upgrade message across the entire app.
 * - If subscription is expired/inactive: Show content in read-only mode.
 *   Users can VIEW all data but cannot CREATE/UPDATE/DELETE. The expired
 *   banner is shown by UpgradeBar at the app root.
 * - Admins always get full access with no banners
 * 
 * Use on pages that require subscription awareness (NOT on settings/billing pages)
 */
export const SubscriptionGate = ({ children }) => {
  const { user, subscription, subscriptionExpired, isReadOnly, loading } = useAuth();

  // Fallback for when /subscription/state never resolves (network hang, etc.).
  // After 10s we stop showing the spinner and render the content — mirroring
  // the DEFAULT_ERROR_SUBSCRIPTION pattern from AuthContext (expired / read-only).
  // If the real subscription state arrives later (loading flips false /
  // subscription becomes non-null), the normal render branches below take over
  // and this flag is cleared.
  const [subscriptionLoadTimedOut, setSubscriptionLoadTimedOut] = useState(false);
  useEffect(() => {
    if (!loading && subscription) {
      setSubscriptionLoadTimedOut(false);
      return;
    }
    const timer = setTimeout(() => {
      // Only trip the fallback if we're STILL waiting on subscription state.
      if (!subscription) {
        setSubscriptionLoadTimedOut(true);
      }
    }, 10000);
    return () => clearTimeout(timer);
  }, [loading, subscription]);

  // Don't block while loading - show loading spinner instead
  if (loading) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto"></div>
      </div>
    );
  }

  // ADMIN BYPASS: Primary admin always gets full access with no banners
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';
  if (isAdmin) {
    return children;
  }

  // Wait for subscription to load before deciding — prevents flash of wrong state.
  // If the load timed out, fall through to the read-only render below instead of
  // spinning forever.
  if (!subscription && !subscriptionLoadTimedOut) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto"></div>
      </div>
    );
  }

  // Timed out and still no subscription state — render content in read-only
  // mode. The expired/read-only banner is shown globally by UpgradeBar.
  if (!subscription && subscriptionLoadTimedOut) {
    return (
      <div className="flex flex-col min-h-screen">
        {children}
      </div>
    );
  }

  // Subscription is active — show content normally.
  // Upgrade messaging (free tier, gifted, etc.) is handled by UpgradeBar at
  // the app root, so we no longer render TrialBanner here.
  if (!subscriptionExpired && !isReadOnly) {
    return (
      <div className="flex flex-col min-h-screen">
        {children}
      </div>
    );
  }

  // Subscription expired or read-only — show content (read-only mode).
  // The expired banner is shown globally by UpgradeBar at the app root.
  return (
    <div className="flex flex-col min-h-screen">
      {children}
    </div>
  );
};

/**
 * FullSubscriptionGate - Hard paywall for features that absolutely require subscription
 * Use this sparingly - only for premium features that shouldn't be accessible at all
 * Admins always bypass this gate
 */
export const FullSubscriptionGate = ({ children }) => {
  const navigate = useNavigate();
  const { user, subscription, subscriptionExpired, isReadOnly, loading } = useAuth();
  const [subscriptionLoadTimedOut, setSubscriptionLoadTimedOut] = useState(false);

  useEffect(() => {
    if (!loading && subscription) {
      setSubscriptionLoadTimedOut(false);
      return;
    }
    const timer = setTimeout(() => setSubscriptionLoadTimedOut(true), 10000);
    return () => clearTimeout(timer);
  }, [loading, subscription]);

  // Don't block while loading - show loading spinner instead
  if ((loading || !subscription) && !subscriptionLoadTimedOut) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto"></div>
      </div>
    );
  }

  // ADMIN BYPASS: Primary admin always gets full access
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';
  if (isAdmin) {
    return children;
  }

  // If subscription is active (not expired, not read-only), show content
  if (!subscriptionExpired && !isReadOnly) {
    return children;
  }

  // Subscription expired - show paywall
  const isAccessExpired = subscription?.status === 'trialing' || subscription?.status === 'expired';

  return (
    <div className="min-h-screen bg-subtle-bg flex items-center justify-center p-4">
      <div className="max-w-lg w-full">
        <div className="card-trust corner-mark text-center" data-testid="subscription-paywall">
          {/* Icon */}
          <div className="w-16 h-16 mx-auto mb-6 bg-warning/10 flex items-center justify-center">
            {isAccessExpired ? (
              <Clock className="w-8 h-8 text-warning" />
            ) : (
              <AlertTriangle className="w-8 h-8 text-warning" />
            )}
          </div>

          {/* Title */}
          <h1 className="font-serif text-2xl text-navy mb-2">
            {isAccessExpired ? 'Free Access Has Ended' : 'Subscription Required'}
          </h1>

          {/* Message */}
          <p className="text-muted-foreground mb-6">
            {isAccessExpired 
              ? 'Subscribe now to continue managing your trusts with TrustOffice.'
              : 'Your subscription is inactive. Please subscribe to continue using TrustOffice.'}
          </p>

          {/* Features reminder */}
          <div className="bg-subtle-bg border border-border p-4 mb-6 text-left">
            <p className="label-trust text-xs mb-3">What you get with TrustOffice:</p>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                Trustee ($79/mo): 1 trust, all governance tools
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                Estate ($149/mo): up to 8 trusts, multi-trust dashboard
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                Advisor ($399/mo): unlimited trusts, client view, white-label
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                Defensibility tracking, minutes & distribution management
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                PDF generation & CSV export
              </li>
            </ul>
          </div>

          {/* CTA Buttons */}
          <div className="flex flex-col gap-3">
            <Button
              onClick={() => navigate('/settings/billing')}
              className="btn-primary w-full"
              data-testid="subscribe-cta-btn"
            >
              <CreditCard className="w-4 h-4 mr-2" />
              Subscribe Now
            </Button>
            
            <p className="text-xs text-muted-foreground">
              Starting at $79/month for Trustee, $149/month for Estate, or $399/month for Advisor — or save with annual billing
            </p>
          </div>

          {/* Data safety note */}
          <div className="mt-6 pt-4 border-t border-border">
            <p className="text-xs text-muted-foreground">
              Don't worry, your data is safe. It will be available as soon as you subscribe.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SubscriptionGate;
