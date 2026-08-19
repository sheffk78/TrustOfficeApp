import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Gift,
  Sparkles,
  ArrowRight,
  Clock,
  Calendar,
  Lock,
  Zap,
  AlertTriangle,
} from 'lucide-react';

/**
 * UpgradeBar — THE single, unified upgrade / subscription / purchase banner
 * for the entire TrustOffice app. Rendered once at the app root (App.js), it
 * replaces GiftedBanner, TrialBanner, the upgrade portion of DashboardBanners,
 * and ReadOnlyBanner.
 *
 * Only ONE message is ever shown at a time. The bar picks the highest-priority
 * message from the list below and renders only that.
 *
 * Priority order (highest → lowest):
 *   1. Subscription expired / read-only (critical, NOT dismissible)
 *   2. Gifted access ending soon (≤3 days remaining) (critical, NOT dismissible)
 *   3. Gifted access active (dismissible)
 *   4. Free tier — non-forever-free (dismissible)
 *   5. Trust limit exceeded (dismissible)
 *   6. No message (forever_free, paid, admin) — render nothing
 *
 * `forever_free` plan NEVER sees this bar.
 */

// ─── Priority helpers ───────────────────────────────────────────────

const isAdminUser = (user) =>
  user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';

/**
 * Returns the single highest-priority message descriptor, or null if no
 * message should be shown.
 */
function pickMessage({ user, subscription, subscriptionExpired, isReadOnly }) {
  // No subscription loaded yet → nothing to show
  if (!subscription) return null;

  // forever_free never sees the bar
  if (subscription.plan_type === 'forever_free') return null;

  const daysRemaining =
    subscription.gift_days_remaining ?? subscription.trial_days_remaining;
  const giftType = subscription.gift_type || '14day';

  // Priority 1 — expired / read-only (critical)
  if (subscriptionExpired || isReadOnly) {
    const status = subscription.status;
    const isPastDue = status === 'past_due';
    const isCanceled = status === 'canceled';
    const isTrialExpired = status === 'expired';
    return {
      key: 'expired',
      critical: true,
      severity: 'warning',
      icon: isPastDue ? AlertTriangle : Lock,
      title: isPastDue
        ? 'Your payment was declined — your subscription is paused'
        : isTrialExpired
          ? 'Your free access has ended'
          : isCanceled
            ? 'Your subscription has been canceled'
            : 'Your access has ended',
      subtitle: isPastDue
        ? 'Your data is still fully accessible. Update your payment method to restore your subscription.'
        : 'Subscribe to make changes again. You can view all your data, but creating or editing is disabled until you subscribe.',
      ctaLabel: isPastDue ? 'Update Payment Method' : 'Subscribe Now',
      ctaLink: isPastDue
        ? '/settings/billing?action=update_payment'
        : '/settings/billing',
      testId: 'upgrade-bar-expired',
      ctaTestId: 'upgrade-bar-expired-cta',
    };
  }

  // Gifted users (only when active — expired handled above)
  if (subscription.is_gifted && subscription.is_active) {
    const isUrgent =
      giftType === '14day' &&
      daysRemaining !== null &&
      daysRemaining !== undefined &&
      daysRemaining <= 3;

    // Priority 2 — gifted ending soon (critical, not dismissible)
    if (isUrgent) {
      return {
        key: 'gifted-urgent',
        critical: true,
        severity: 'gold',
        icon: Clock,
        title: `Your gifted access ends in ${daysRemaining} day${daysRemaining !== 1 ? 's' : ''} — upgrade to keep your workspace`,
        subtitle: 'Upgrade now to avoid losing access to your trust workspace.',
        ctaLabel: 'Upgrade to Keep Access',
        ctaLink: '/settings/billing',
        testId: 'upgrade-bar-gifted-urgent',
        ctaTestId: 'upgrade-bar-gifted-urgent-cta',
      };
    }

    // Priority 3 — gifted active (dismissible)
    const giftLabel = (() => {
      switch (giftType) {
        case '14day':
          return '14 days';
        case 'monthly':
          return '1 month';
        case 'annual':
          return '1 year';
        default:
          return '14 days';
      }
    })();

    const expiryLabel =
      giftType === '14day' && daysRemaining !== null && daysRemaining !== undefined
        ? `${daysRemaining} day${daysRemaining !== 1 ? 's' : ''} remaining`
        : null;

    return {
      key: 'gifted-active',
      critical: false,
      severity: 'gold',
      icon: Gift,
      title: `You've been gifted ${giftLabel} of TrustOffice Pro`,
      subtitle: expiryLabel
        ? `${expiryLabel} — no credit card needed`
        : 'Full Pro access — no credit card needed',
      ctaLabel: 'Upgrade to Keep Access',
      ctaLink: '/settings/billing',
      testId: 'upgrade-bar-gifted-active',
      ctaTestId: 'upgrade-bar-gifted-active-cta',
    };
  }

  // Priority 4 — free tier (non-forever-free, non-gifted, active)
  const isActiveFreeTier =
    !subscription.is_gifted &&
    subscription.is_active &&
    (subscription.is_trial ||
      subscription.plan_type === 'free' ||
      subscription.plan_type === 'trial');

  if (isActiveFreeTier) {
    return {
      key: 'free-tier',
      critical: false,
      severity: 'navy',
      icon: Lock,
      title: 'Free Plan — upgrade to unlock full features',
      subtitle:
        'Your data is safe and fully viewable. Purchase a plan to unlock PDF exports, multiple trusts, advanced templates, and the ability to make changes.',
      ctaLabel: 'Upgrade Now',
      ctaLink: '/settings/billing',
      testId: 'upgrade-bar-free-tier',
      ctaTestId: 'upgrade-bar-free-tier-cta',
    };
  }

  // Priority 5 — trust limit exceeded (dismissible)
  if (
    subscription.needs_upgrade &&
    subscription.trust_limit !== null &&
    subscription.trust_limit !== undefined &&
    subscription.trust_count !== null &&
    subscription.trust_count !== undefined &&
    subscription.trust_count > subscription.trust_limit
  ) {
    return {
      key: 'trust-limit',
      critical: false,
      severity: 'warning',
      icon: Zap,
      title: `Your plan supports ${subscription.trust_limit} trusts but you have ${subscription.trust_count} — upgrade to manage all`,
      subtitle: 'Upgrade your plan to manage all of your trusts.',
      ctaLabel: 'Upgrade',
      ctaLink: '/settings/billing?wp=1&action=upgrade',
      testId: 'upgrade-bar-trust-limit',
      ctaTestId: 'upgrade-bar-trust-limit-cta',
    };
  }

  // Priority 6 — no message (paid, admin, forever_free handled above)
  return null;
}

// ─── Severity → styling map ─────────────────────────────────────────

const SEVERITY_STYLES = {
  warning: {
    bar: 'bg-warning/5 dark:bg-warning/10 border-b border-warning/20 dark:border-warning/30',
    iconWrap: 'bg-warning/10 dark:bg-warning/30 rounded-full',
    iconColor: 'text-warning',
    titleColor: 'text-warning',
    subColor: 'text-warning',
    ctaClass: 'bg-warning hover:bg-warning text-white',
  },
  gold: {
    bar: 'bg-gradient-to-r from-gold to-gold/90 text-navy shadow-lg',
    iconWrap: 'bg-white/20 rounded-full',
    iconColor: 'text-navy',
    titleColor: 'text-navy',
    subColor: 'text-navy/70',
    ctaClass: 'bg-navy hover:bg-navy/90 text-white',
  },
  navy: {
    bar: 'bg-gradient-to-r from-navy/5 to-gold/5 border-b border-navy/10',
    iconWrap: 'bg-success/10 rounded-full',
    iconColor: 'text-navy',
    titleColor: 'text-navy',
    subColor: 'text-muted-foreground',
    ctaClass: 'btn-primary',
  },
};

// ─── Component ──────────────────────────────────────────────────────

export const UpgradeBar = () => {
  const { user, subscription, subscriptionExpired, isReadOnly, loading } =
    useAuth();
  const [dismissed, setDismissed] = useState(false);
  const hasTrackedView = useRef(false);

  // Don't render while auth is still loading (prevents flicker)
  if (loading) return null;

  // Admins never see the bar
  if (isAdminUser(user)) return null;

  const message = pickMessage({
    user,
    subscription,
    subscriptionExpired,
    isReadOnly,
  });

  // No message → render nothing
  if (!message) return null;

  // Non-critical messages can be dismissed; critical ones cannot.
  // Reset dismissed state when the message key changes so a new message
  // type isn't accidentally suppressed.
  const isDismissed = dismissed && !message.critical;
  if (isDismissed) return null;

  const styles = SEVERITY_STYLES[message.severity] || SEVERITY_STYLES.warning;
  const Icon = message.icon;

  // Track view once per message key
  useEffect(() => {
    if (!hasTrackedView.current) {
      try {
        if (typeof window.gtag === 'function') {
          window.gtag('event', 'upgrade_bar_viewed', {
            message_key: message.key,
          });
        }
      } catch (e) {
        console.error('Failed to track upgrade bar view:', e);
      }
      hasTrackedView.current = true;
    }
    // Reset tracking flag when key changes
    return () => {
      hasTrackedView.current = false;
    };
  }, [message.key]);

  const handleCtaClick = () => {
    try {
      if (typeof window.gtag === 'function') {
        window.gtag('event', 'upgrade_bar_clicked', {
          message_key: message.key,
        });
      }
    } catch (e) {
      console.error('Failed to track upgrade bar click:', e);
    }
  };

  return (
    <div
      className={`fixed top-0 left-0 right-0 z-[90] ${styles.bar}`}
      data-testid={message.testId}
    >
      <div className="flex items-center justify-between px-4 py-2.5 max-w-7xl mx-auto lg:ml-64">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`flex items-center gap-2 p-2 flex-shrink-0 ${styles.iconWrap}`}
          >
            <Icon className={`w-4 h-4 ${styles.iconColor}`} />
          </div>
          <div className="min-w-0">
            <p className={`text-sm font-semibold truncate ${styles.titleColor}`}>
              {message.title}
            </p>
            {message.subtitle && (
              <p className={`text-xs truncate ${styles.subColor}`}>
                {message.subtitle}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <Link to={message.ctaLink} onClick={handleCtaClick}>
            <Button
              size="sm"
              className={`${styles.ctaClass} flex items-center gap-2 font-semibold whitespace-nowrap`}
              data-testid={message.ctaTestId}
            >
              <Sparkles className="w-3.5 h-3.5" />
              {message.ctaLabel}
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          </Link>
          {!message.critical && (
            <button
              onClick={() => setDismissed(true)}
              className="p-1.5 rounded-full hover:bg-black/10 dark:hover:bg-white/10 transition-colors flex-shrink-0"
              aria-label="Dismiss"
              data-testid="upgrade-bar-dismiss"
            >
              <svg
                className="w-4 h-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default UpgradeBar;