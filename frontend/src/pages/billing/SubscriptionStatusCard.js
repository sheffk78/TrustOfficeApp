import {
  AlertTriangle, ArrowUpCircle, Calendar, Check, Clock,
  ExternalLink, Loader2, RefreshCw, XCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import StatusBadge from './StatusBadge';
import { TIERS, planDisplayName, tierPriceFor } from './pricingConfig';

// The "Current Plan" status card for the existing-subscription view.
// Encapsulates the plan name header, free-plan info, details grid,
// expired warning, cancellation notice, and the active-subscription
// action buttons (Change Plan / Manage Payment Method / Cancel).
//
// Props:
//   subscription                – the subscription object
//   isFreePlan                  – boolean predicate
//   isActivePaidSubscription    – boolean predicate
//   isCanceling                 – boolean predicate (cancel_at_period_end)
//   isGrandfathered             – boolean predicate
//   legacyTrustLimit            – number | null
//   normalizedPlanType          – plan_type normalized to a TIERS id
//   canUpgrade                  – boolean predicate
//   formatDate                  – (isoString) => string
//   actionLoading               – the actionLoading string or null
//   onReactivate                – () => void
//   onManageBilling             – () => void
//   onCancel                    – () => void
export default function SubscriptionStatusCard({
  subscription,
  isFreePlan,
  isActivePaidSubscription,
  isCanceling,
  isGrandfathered,
  legacyTrustLimit,
  normalizedPlanType,
  canUpgrade,
  formatDate,
  actionLoading,
  onReactivate,
  onManageBilling,
  onCancel,
}) {
  const trustLimitLabel = () => {
    if (isGrandfathered) {
      return `Grandfathered: ${legacyTrustLimit} trusts`;
    }
    const tier = TIERS.find((t) => t.id === normalizedPlanType);
    return tier ? tier.trustLimit : '—';
  };

  const currentPriceLabel = (() => {
    const price = tierPriceFor(normalizedPlanType, subscription?.billing_period || 'monthly');
    if (price == null) return 'N/A';
    const periodLabel = subscription?.billing_period === 'annual' ? '/year' : '/month';
    return `$${price}${periodLabel}`;
  })();

  return (
    <div className="card-trust corner-mark mb-8" data-testid="subscription-status-card">
      <div className="flex items-start justify-between mb-6">
        <div>
          <p className="label-trust mb-2">Current Plan</p>
          <h2 className="font-serif text-2xl text-navy">
            {planDisplayName(subscription?.plan_type)}
          </h2>
          {isActivePaidSubscription && (
            <p className="text-sm text-muted-foreground mt-1">
              {subscription?.billing_period === 'annual' ? 'Annual billing' : 'Monthly billing'}
              {' · '}
              {trustLimitLabel()}
            </p>
          )}
          {isGrandfathered && (
            <p className="text-xs text-success mt-1 font-medium">
              Grandfathered: {legacyTrustLimit} trusts at your current price
            </p>
          )}
        </div>
        <StatusBadge subscription={subscription} />
      </div>

      {/* Free Plan Info */}
      {isFreePlan && (
        <div className="p-4 bg-success/5 border border-success/10 mb-6">
          <div className="flex items-start gap-3">
            <Check className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-navy">
                Core Features Only
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                You have full access to trust management, minutes, distributions, and governance tools. Upgrade to a paid plan for team features, priority support, and dedicated account management.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Subscription Details Grid (paid plans only) */}
      {isActivePaidSubscription && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6 p-4 bg-subtle-bg border border-border">
          <div>
            <p className="label-trust text-xs mb-1">
              {isCanceling ? 'Access Until' : 'Next Billing Date'}
            </p>
            <p className="font-mono text-sm text-navy flex items-center gap-2" data-testid="billing-date">
              <Calendar className="w-4 h-4 text-muted-foreground" />
              {formatDate(subscription.current_period_end) || 'N/A'}
            </p>
          </div>
          <div>
            <p className="label-trust text-xs mb-1">
              {subscription?.billing_period === 'annual' ? 'Annual Cost' : 'Monthly Cost'}
            </p>
            <p className="font-mono text-sm text-navy">
              {currentPriceLabel}
            </p>
          </div>
        </div>
      )}



      {/* Expired Access Warning */}
      {subscription?.status === 'expired' && (
        <div className="p-4 bg-error/10 border border-error/20 mb-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-error flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-error">Your free access has ended</p>
              <p className="text-sm text-error/80 mt-1">
                Subscribe now to continue using TrustOffice. Your data is safe and will be available once you subscribe.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Cancellation Notice */}
      {isCanceling && (
        <div className="p-4 bg-warning/10 border border-warning/20 mb-6">
          <div className="flex items-start gap-3">
            <Clock className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-warning">Subscription canceling</p>
              <p className="text-sm text-warning/80 mt-1">
                Your subscription is set to cancel on {formatDate(subscription.current_period_end)}. 
                You'll retain full access until then.
              </p>
              <Button
                onClick={onReactivate}
                variant="outline"
                size="sm"
                className="mt-3 border-warning text-warning hover:bg-warning/10"
                disabled={actionLoading === 'reactivate'}
                data-testid="reactivate-btn"
              >
                {actionLoading === 'reactivate' ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4 mr-2" />
                )}
                Keep My Subscription
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Active Paid Subscription Actions (not for free plan) */}
      {isActivePaidSubscription && !isCanceling && (
        <div className="flex flex-wrap gap-3">
          {canUpgrade && (
            <Button
              onClick={() => {
                const tierSection = document.querySelector('[data-testid="tier-change-section"]');
                if (tierSection) tierSection.scrollIntoView({ behavior: 'smooth' });
              }}
              className="btn-primary"
              data-testid="change-plan-btn"
            >
              <ArrowUpCircle className="w-4 h-4 mr-2" />
              Change Plan
            </Button>
          )}
          
          <Button
            onClick={onManageBilling}
            variant="outline"
            disabled={actionLoading === 'portal'}
            data-testid="manage-billing-btn"
          >
            {actionLoading === 'portal' ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <ExternalLink className="w-4 h-4 mr-2" />
            )}
            Manage Payment Method
          </Button>
          
          <Button
            onClick={onCancel}
            variant="ghost"
            className="text-muted-foreground hover:text-error"
            disabled={actionLoading === 'cancel'}
            data-testid="cancel-subscription-btn"
          >
            {actionLoading === 'cancel' ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <XCircle className="w-4 h-4 mr-2" />
            )}
            Cancel Subscription
          </Button>
        </div>
      )}
    </div>
  );
}