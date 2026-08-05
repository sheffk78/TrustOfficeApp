import { Check, CreditCard, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { WINGPOINT_TIER } from './pricingConfig';

// WingPoint-exclusive plan card — only shown to WingPoint customers
// (user.is_wingpoint). Uses a fixed $99/mo display price and annual billing.
//
// Props:
//   onSubscribe  – (planId, period) => void
//   processing   – boolean
//   isTargetPlan – boolean (gold ring for ?plan= deep-link)
//   cardRef      – ref callback to register the card element
export default function WingPointPlanCard({
  onSubscribe,
  processing,
  isTargetPlan,
  cardRef,
}) {
  return (
    <div
      ref={cardRef}
      className={`card-trust relative border-gold/40 bg-gold/5 mb-8 ${isTargetPlan ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
      data-testid={`plan-card-${WINGPOINT_TIER.id}`}
    >
      <div className="absolute top-0 right-0 bg-gold text-white px-3 py-1 font-mono text-xs uppercase">
        WingPoint Exclusive
      </div>
      <h3 className="font-serif text-xl text-navy mb-2">{WINGPOINT_TIER.name}</h3>
      <p className="text-xs text-muted-foreground mb-3">{WINGPOINT_TIER.trustLimit}</p>
      <div className="flex items-baseline gap-1 mb-2">
        <span className="font-mono text-4xl text-navy">$99</span>
        <span className="text-muted-foreground">/month</span>
      </div>
      <p className="text-xs text-success mb-3 font-medium">
        $1,188/year · billed annually · 2 months free vs public pricing
      </p>
      <ul className="space-y-3 mb-6">
        {WINGPOINT_TIER.features.map((feature, i) => (
          <li key={i} className="flex items-center gap-2 text-sm">
            <Check className="w-4 h-4 text-success flex-shrink-0" />
            <span>{feature}</span>
          </li>
        ))}
      </ul>
      <Button
        onClick={() => onSubscribe('wingpoint', 'annual')}
        className="w-full btn-primary"
        disabled={processing}
        data-testid="subscribe-wingpoint-btn"
      >
        {processing ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Processing...
          </>
        ) : (
          <>
            <CreditCard className="w-4 h-4 mr-2" />
            Subscribe to WingPoint Annual
          </>
        )}
      </Button>
    </div>
  );
}