import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { ReadOnlyBanner } from '@/components/ReadOnlyBanner';
import { TrialBanner } from '@/components/TrialBanner';
import { 
  AlertTriangle, 
  CreditCard,
  Clock,
  CheckCircle
} from 'lucide-react';

/**
 * SubscriptionGate - Wraps protected content
 * 
 * NEW BEHAVIOR (Read-Only Mode):
 * - If subscription is active (including trial): Show content with TrialBanner (if trial)
 * - If subscription is expired/inactive: Show content with ReadOnlyBanner
 *   Users can VIEW all data but cannot CREATE/UPDATE/DELETE
 * - Admins always get full access with no banners
 * 
 * Use on pages that require subscription awareness (NOT on settings/billing pages)
 */
export const SubscriptionGate = ({ children }) => {
  const { user, subscription, subscriptionExpired, isReadOnly, loading } = useAuth();

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

  // Wait for subscription to load before deciding — prevents flash of wrong state
  if (!subscription) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto"></div>
      </div>
    );
  }

  // Check if it's an active trial
  const isActiveTrial = subscription?.is_trial && subscription?.is_active;

  // If subscription is active, show content with TrialBanner if applicable
  if (!subscriptionExpired && !isReadOnly) {
    return (
      <div className="flex flex-col min-h-screen">
        {isActiveTrial && <TrialBanner location="page" />}
        {children}
      </div>
    );
  }

  // Subscription expired or read-only - show content with ReadOnlyBanner
  // Users can still view all their data
  return (
    <div className="flex flex-col min-h-screen">
      <ReadOnlyBanner />
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

  // Don't block while loading - show loading spinner instead
  if (loading || !subscription) {
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
  const isTrialExpired = subscription?.status === 'trialing' || subscription?.status === 'expired';

  return (
    <div className="min-h-screen bg-subtle-bg flex items-center justify-center p-4">
      <div className="max-w-lg w-full">
        <div className="card-trust corner-mark text-center" data-testid="subscription-paywall">
          {/* Icon */}
          <div className="w-16 h-16 mx-auto mb-6 bg-warning/10 flex items-center justify-center">
            {isTrialExpired ? (
              <Clock className="w-8 h-8 text-warning" />
            ) : (
              <AlertTriangle className="w-8 h-8 text-warning" />
            )}
          </div>

          {/* Title */}
          <h1 className="font-serif text-2xl text-navy mb-2">
            {isTrialExpired ? 'Your Trial Has Ended' : 'Subscription Required'}
          </h1>

          {/* Message */}
          <p className="text-muted-foreground mb-6">
            {isTrialExpired 
              ? 'Your 14-day free trial has expired. Subscribe now to continue managing your trusts with TrustOffice.'
              : 'Your subscription is inactive. Please subscribe to continue using TrustOffice.'}
          </p>

          {/* Features reminder */}
          <div className="bg-subtle-bg border border-border p-4 mb-6 text-left">
            <p className="label-trust text-xs mb-3">What you get with TrustOffice:</p>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                Unlimited trusts & entities
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                Governance health tracking
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                Minutes & distribution management
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
              onClick={() => navigate('/pricing')}
              className="btn-primary w-full"
              data-testid="subscribe-cta-btn"
            >
              <CreditCard className="w-4 h-4 mr-2" />
              Subscribe Now
            </Button>
            
            <p className="text-xs text-muted-foreground">
              Starting at $79/month or save with annual billing
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
