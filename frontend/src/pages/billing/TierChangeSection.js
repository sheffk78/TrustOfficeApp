import { Loader2 } from 'lucide-react';
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
          return (
            <div
              key={tier.id}
              ref={cardRef(tier.id)}
              className={`card-trust relative p-6 ${tier.popular ? 'border-gold/40' : ''} ${isCurrentTier ? 'ring-2 ring-navy' : ''} ${targetPlan === tier.id ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
              data-testid={`tier-change-card-${tier.id}`}
            >
              {tier.popular && !isCurrentTier && (
                <div className="absolute top-0 right-0 bg-gold text-white px-3 py-1 font-mono text-xs uppercase">
                  Most Popular
                </div>
              )}
              {isCurrentTier && (
                <div className="absolute top-0 right-0 bg-navy text-white px-3 py-1 font-mono text-xs uppercase">
                  Current
                </div>
              )}
              <h4 className="font-serif text-lg text-navy mb-1">{tier.name}</h4>
              <p className="text-xs text-muted-foreground mb-3">{tier.trustLimit}</p>
              <div className="flex items-baseline gap-1 mb-2">
                <span className="font-mono text-2xl text-navy">
                  ${billingPeriod === 'annual' ? tier.annual : tier.monthly}
                </span>
                <span className="text-muted-foreground text-sm">
                  /{billingPeriod === 'annual' ? 'year' : 'month'}
                </span>
              </div>
              <Button
                onClick={() => onChangePlan(tier.id, billingPeriod)}
                disabled={(isCurrentTier && billingPeriod === currentBillingPeriod) || actionLoading === 'change-plan'}
                variant={isUpgrade ? 'default' : 'outline'}
                className={`w-full mt-3 ${isUpgrade ? 'btn-primary' : ''}`}
                data-testid={`change-to-${tier.id}-btn`}
              >
                {actionLoading === 'change-plan' ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : null}
                {isCurrentTier && billingPeriod === currentBillingPeriod
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