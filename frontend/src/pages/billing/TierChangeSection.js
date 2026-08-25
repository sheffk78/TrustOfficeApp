import { Loader2, Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TIERS } from './pricingConfig';
import BillingPeriodToggle from './BillingPeriodToggle';

// Phase 3: Tier change section for active paid subscriptions.
// Lets an existing subscriber switch to Trustee/Estate/Advisor (or switch
// billing period) via the change-plan endpoint. Each tier card shows whether
// it's the current tier, an upgrade, or a billing-period switch.
//
// Props:
//   billingPeriod              – current toggle value ('monthly' | 'annual')
//   onBillingPeriodChange      – (period) => void
//   normalizedPlanType         – current plan_type (legacy monthly/annual → 'trustee')
//   currentTierIndex           – index into TIERS for the current tier
//   currentBillingPeriod       – the subscription's actual billing_period
//   targetPlan                 – deep-linked plan id (for gold ring highlight)
//   onChangePlan               – (planId, period) => void
//   actionLoading              – the actionLoading string or null
//   cardRef                    – (tierId) => ref callback for planCardRefs
//   userTrustCount             – number (optional) trust count the user
//                                currently holds; used to gray out tiers
//                                whose maxTrusts is exceeded
export default function TierChangeSection({
  billingPeriod,
  onBillingPeriodChange,
  normalizedPlanType,
  currentTierIndex,
  currentBillingPeriod,
  targetPlan,
  onChangePlan,
  actionLoading,
  cardRef,
  userTrustCount,
}) {
  return (
    <div className="mt-8" data-testid="tier-change-section">
      <h3 className="font-serif text-xl text-navy mb-1">Change Your Plan</h3>
      <p className="text-sm text-muted-foreground mb-4">
        Upgrade or downgrade at any time. Changes are prorated for the remainder of your billing cycle.
      </p>
      <BillingPeriodToggle value={billingPeriod} onChange={onBillingPeriodChange} />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {TIERS.map((tier) => {
          const isCurrentTier = tier.id === normalizedPlanType;
          const isUpgrade = TIERS.findIndex((t) => t.id === tier.id) > currentTierIndex;
          const isIneligible =
            userTrustCount != null &&
            tier.maxTrusts !== Infinity &&
            userTrustCount > tier.maxTrusts;
          return (
            <div
              key={tier.id}
              ref={cardRef(tier.id)}
              className={`card-trust relative p-6 ${isIneligible ? 'opacity-50 pointer-events-none' : ''} ${tier.popular ? 'border-gold/40' : ''} ${isCurrentTier && !isIneligible ? 'ring-2 ring-navy' : ''} ${targetPlan === tier.id && !isIneligible ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
              data-testid={`tier-change-card-${tier.id}`}
            >
              {tier.popular && !isCurrentTier && !isIneligible && (
                <div className="absolute top-0 right-0 bg-gold text-white px-3 py-1 font-mono text-xs uppercase">
                  Most Popular
                </div>
              )}
              {isCurrentTier && !isIneligible && (
                <div className="absolute top-0 right-0 bg-navy text-white px-3 py-1 font-mono text-xs uppercase">
                  Current
                </div>
              )}
              {isIneligible && (
                <div className="absolute top-0 right-0 bg-muted text-muted-foreground px-3 py-1 font-mono text-xs uppercase flex items-center gap-1">
                  <Lock className="w-3 h-3" />
                  Not Enough Trusts
                </div>
              )}
              <h4 className="font-serif text-lg text-navy mb-1">{tier.name}</h4>
              <p className="text-xs text-muted-foreground mb-3">{tier.trustLimit}</p>
              {isIneligible && (
                <p className="text-xs text-warning mb-3 font-medium">
                  Your account has {userTrustCount} trust
                  {userTrustCount !== 1 ? 's' : ''}. This plan supports up to{' '}
                  {tier.maxTrusts === Infinity ? 'unlimited' : tier.maxTrusts}.
                </p>
              )}
              <div className="flex items-baseline gap-1 mb-1">
                <span className="font-mono text-2xl text-navy">
                  ${billingPeriod === 'annual' ? (tier.annual / 12).toFixed(2).replace(/\.00$/, '') : tier.monthly}
                </span>
                <span className="text-muted-foreground text-sm">/month</span>
              </div>
              {billingPeriod === 'annual' ? (
                <p className="text-xs text-muted-foreground mb-2">
                  ${tier.annual.toLocaleString()}/yr
                </p>
              ) : (
                <p className="text-xs text-muted-foreground mb-2">
                  ${tier.monthly * 12}/yr
                </p>
              )}
              <Button
                onClick={() => onChangePlan(tier.id, billingPeriod)}
                disabled={(isCurrentTier && billingPeriod === currentBillingPeriod) || actionLoading === 'change-plan' || isIneligible}
                variant={isUpgrade ? 'default' : 'outline'}
                className={`w-full mt-3 ${isUpgrade && !isIneligible ? 'btn-primary' : ''}`}
                data-testid={`change-to-${tier.id}-btn`}
              >
                {actionLoading === 'change-plan' ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : null}
                {isIneligible ? (
                  <>
                    <Lock className="w-4 h-4 mr-2" />
                    Not Enough Trusts
                  </>
                ) : isCurrentTier && billingPeriod === currentBillingPeriod
                  ? 'Current Plan'
                  : isCurrentTier && billingPeriod !== currentBillingPeriod
                  ? `Switch to ${billingPeriod === 'annual' ? 'Annual' : 'Monthly'}`
                  : isUpgrade ? 'Upgrade' : 'Switch'}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}