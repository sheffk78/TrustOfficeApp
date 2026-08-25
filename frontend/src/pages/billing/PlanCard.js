import { Check, CreditCard, Loader2, Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';

// Reusable pricing plan card for a single tier.
// Used by both the no-subscription plan picker and the free/expired plan
// picker. The highlighted (targetPlan) ring and ref forwarding are optional.
//
// Props:
//   tier            – tier object from pricingConfig.TIERS
//   billingPeriod   – 'monthly' | 'annual'
//   onSubscribe     – (planId, period) => void
//   processing      – boolean (disables button + shows spinner)
//   isTargetPlan    – boolean (adds gold ring for ?plan= deep-link)
//   cardRef         – ref callback to register the card element
//   userTrustCount  – number | undefined  (optional) count of trusts the
//                     user currently holds. If it exceeds tier.maxTrusts
//                     the card is grayed out and the button is disabled.
export default function PlanCard({
  tier,
  billingPeriod,
  onSubscribe,
  processing,
  isTargetPlan,
  cardRef,
  userTrustCount,
}) {
  // A tier is ineligible when the user has more trusts than the tier supports.
  // Infinity (unlimited) tiers are never ineligible.
  const isIneligible =
    userTrustCount != null &&
    tier.maxTrusts !== Infinity &&
    userTrustCount > tier.maxTrusts;

  return (
    <div
      ref={cardRef}
      className={`card-trust relative ${isIneligible ? 'opacity-50 pointer-events-none' : ''} ${tier.popular ? 'border-gold/30 bg-gold/5' : ''} ${isTargetPlan && !isIneligible ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
      data-testid={`plan-card-${tier.id}`}
    >
      {tier.popular && !isIneligible && (
        <div className="absolute top-0 right-0 bg-gold text-white px-3 py-1 font-mono text-xs uppercase">
          Most Popular
        </div>
      )}
      {isIneligible && (
        <div className="absolute top-0 right-0 bg-muted text-muted-foreground px-3 py-1 font-mono text-xs uppercase flex items-center gap-1">
          <Lock className="w-3 h-3" />
          Not Enough Trusts
        </div>
      )}
      <h3 className="font-serif text-xl text-navy mb-2">{tier.name}</h3>
      <p className="text-xs text-muted-foreground mb-3">{tier.trustLimit}</p>
      {isIneligible && (
        <p className="text-xs text-warning mb-3 font-medium">
          Your account has {userTrustCount} trust
          {userTrustCount !== 1 ? 's' : ''}. This plan supports up to{' '}
          {tier.maxTrusts === Infinity ? 'unlimited' : tier.maxTrusts}.
        </p>
      )}
      <div className="flex items-baseline gap-1 mb-1">
        <span className="font-mono text-4xl text-navy">
          ${billingPeriod === 'annual' ? (tier.annual / 12).toFixed(2).replace(/\.00$/, '') : tier.monthly}
        </span>
        <span className="text-muted-foreground">/month</span>
      </div>
      {billingPeriod === 'annual' ? (
        <>
          <p className="text-xs text-muted-foreground mb-2">
            ${tier.annual.toLocaleString()} billed annually · save ${tier.monthly * 2}
          </p>
          <p className="text-xs text-success mb-3 font-medium">
            2 months free
          </p>
        </>
      ) : (
        <p className="text-xs text-muted-foreground mb-3">
          ${tier.monthly * 12}/year · switch to annual to save ${tier.monthly * 2}
        </p>
      )}
      <ul className="space-y-3 mb-6">
        {tier.features.map((feature, i) => (
          <li key={i} className="flex items-center gap-2 text-sm">
            <Check className="w-4 h-4 text-success flex-shrink-0" />
            <span>{feature}</span>
          </li>
        ))}
      </ul>
      <Button
        onClick={() => onSubscribe(tier.id, billingPeriod)}
        className={`w-full ${tier.popular && !isIneligible ? 'btn-primary' : 'btn-secondary'}`}
        disabled={processing || isIneligible}
        data-testid={`subscribe-${tier.id}-btn`}
      >
        {processing ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Processing...
          </>
        ) : isIneligible ? (
          <>
            <Lock className="w-4 h-4 mr-2" />
            Not Enough Trusts
          </>
        ) : (
          <>
            <CreditCard className="w-4 h-4 mr-2" />
            Subscribe to {tier.name}
          </>
        )}
      </Button>
    </div>
  );
}