import { Check, CreditCard, Loader2 } from 'lucide-react';
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
export default function PlanCard({
  tier,
  billingPeriod,
  onSubscribe,
  processing,
  isTargetPlan,
  cardRef,
}) {
  return (
    <div
      ref={cardRef}
      className={`card-trust relative ${tier.popular ? 'border-gold/30 bg-gold/5' : ''} ${isTargetPlan ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
      data-testid={`plan-card-${tier.id}`}
    >
      {tier.popular && (
        <div className="absolute top-0 right-0 bg-gold text-white px-3 py-1 font-mono text-xs uppercase">
          Most Popular
        </div>
      )}
      <h3 className="font-serif text-xl text-navy mb-2">{tier.name}</h3>
      <p className="text-xs text-muted-foreground mb-3">{tier.trustLimit}</p>
      <div className="flex items-baseline gap-1 mb-4">
        <span className="font-mono text-4xl text-navy">
          ${billingPeriod === 'annual' ? tier.annual : tier.monthly}
        </span>
        <span className="text-muted-foreground">/{billingPeriod === 'annual' ? 'year' : 'month'}</span>
      </div>
      {billingPeriod === 'annual' && (
        <p className="text-xs text-success mb-3 font-medium">
          Save ${tier.monthly * 2} (2 months free)
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
        className={`w-full ${tier.popular ? 'btn-primary' : 'btn-secondary'}`}
        disabled={processing}
        data-testid={`subscribe-${tier.id}-btn`}
      >
        {processing ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Processing...
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