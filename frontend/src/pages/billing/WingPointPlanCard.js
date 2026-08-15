import { useState } from 'react';
import { Check, CreditCard, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { WINGPOINT_TIER, TRUSTEE_TIER } from './pricingConfig';

// WingPoint-exclusive purchase section — only shown to WingPoint customers
// (user.is_wingpoint). Renders BOTH options Jeff requires:
//   (a) Trustee — $79/mo  (annual $790/yr)
//   (b) WingPoint — $99/mo  (annual $1,188/yr)
//
// Each card carries its own Monthly/Annual toggle. Because the backend only
// supports the wingpoint plan as annual (PRICE_IDS has ("wingpoint","annual")
// only; checkout returns 400 for wingpoint + non-annual), the WingPoint card
// always calls onSubscribe('wingpoint','annual') — the toggle is purely a
// presentation aid so the user can compare the monthly-equivalent ($99/mo)
// against the annual price ($1,188/yr). The Trustee card uses the real
// monthly and annual prices.
//
// Props:
//   onSubscribe     – (planId, period) => void
//   processing      – boolean
//   isTargetPlan    – boolean | string (gold ring for ?plan= deep-link; when a
//                     string, matches the tier id)
//   registerCardRef – (tierId) => ref callback (optional; registers both the
//                     trustee and wingpoint cards for auto-scroll)

// ── Trustee $79 option card ─────────────────────────────────────
function TrusteeOptionCard({ onSubscribe, processing, isTargetPlan, cardRef }) {
  const [period, setPeriod] = useState('monthly');
  const price = period === 'annual' ? TRUSTEE_TIER.annual : TRUSTEE_TIER.monthly;

  return (
    <div
      ref={cardRef}
      className={`card-trust relative border-border bg-card ${isTargetPlan ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
      data-testid="plan-card-trustee"
    >
      <div className="absolute top-0 right-0 bg-navy text-white px-3 py-1 font-mono text-xs uppercase">
        1 Trust
      </div>
      <h3 className="font-serif text-xl text-navy mb-2">Trustee Plan</h3>
      <p className="text-xs text-muted-foreground mb-3">{TRUSTEE_TIER.trustLimit}</p>

      {/* Monthly/Annual toggle */}
      <div className="flex justify-center mb-4">
        <div className="inline-flex items-center bg-subtle-bg border border-border rounded-full p-1">
          <button
            type="button"
            onClick={() => setPeriod('monthly')}
            className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${period === 'monthly' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
          >
            Monthly
          </button>
          <button
            type="button"
            onClick={() => setPeriod('annual')}
            className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${period === 'annual' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
          >
            Annual <span className="ml-1 text-success">2 months free</span>
          </button>
        </div>
      </div>

      <div className="flex items-baseline gap-1 mb-2">
        <span className="font-mono text-4xl text-navy">${price}</span>
        <span className="text-muted-foreground">/{period === 'annual' ? 'year' : 'month'}</span>
      </div>
      {period === 'annual' && (
        <p className="text-xs text-success mb-3 font-medium">
          Save ${TRUSTEE_TIER.monthly * 2} (2 months free)
        </p>
      )}

      <ul className="space-y-3 mb-6">
        {TRUSTEE_TIER.features.map((feature, i) => (
          <li key={i} className="flex items-center gap-2 text-sm">
            <Check className="w-4 h-4 text-success flex-shrink-0" />
            <span>{feature}</span>
          </li>
        ))}
      </ul>
      <Button
        onClick={() => onSubscribe('trustee', period)}
        className="w-full btn-secondary"
        disabled={processing}
        data-testid="subscribe-trustee-btn"
      >
        {processing ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Processing...
          </>
        ) : (
          <>
            <CreditCard className="w-4 h-4 mr-2" />
            Subscribe to Trustee {period === 'annual' ? 'Annual' : 'Monthly'}
          </>
        )}
      </Button>
    </div>
  );
}

// ── WingPoint $99 option card ──────────────────────────────────
function WingPointOptionCard({ onSubscribe, processing, isTargetPlan, cardRef }) {
  const [period, setPeriod] = useState('monthly');
  // WingPoint is annual-only on the backend. $99/mo is the monthly-equivalent
  // (1188/12). Both toggle selections purchase the annual plan; the toggle is
  // purely a presentation aid for price comparison.
  const displayPrice = period === 'annual' ? WINGPOINT_TIER.annual : WINGPOINT_TIER.monthly;

  return (
    <div
      ref={cardRef}
      className={`card-trust relative border-gold/40 bg-gold/5 ${isTargetPlan ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
      data-testid={`plan-card-${WINGPOINT_TIER.id}`}
    >
      <div className="absolute top-0 right-0 bg-gold text-white px-3 py-1 font-mono text-xs uppercase">
        WingPoint Exclusive
      </div>
      <h3 className="font-serif text-xl text-navy mb-2">WingPoint Plan</h3>
      <p className="text-xs text-muted-foreground mb-3">{WINGPOINT_TIER.trustLimit}</p>

      {/* Monthly/Annual toggle (presentation only — both purchase annual) */}
      <div className="flex justify-center mb-4">
        <div className="inline-flex items-center bg-subtle-bg border border-border rounded-full p-1">
          <button
            type="button"
            onClick={() => setPeriod('monthly')}
            className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${period === 'monthly' ? 'bg-gold text-white' : 'text-muted-foreground hover:text-navy'}`}
          >
            Monthly
          </button>
          <button
            type="button"
            onClick={() => setPeriod('annual')}
            className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${period === 'annual' ? 'bg-gold text-white' : 'text-muted-foreground hover:text-navy'}`}
          >
            Annual <span className="ml-1 text-success">save vs public</span>
          </button>
        </div>
      </div>

      {/* Discount comparison: show the normal Estate price struck through
          alongside the WingPoint price, plus a gold savings badge. */}
      {period === 'monthly' ? (
        <>
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-mono text-4xl text-navy">${displayPrice}</span>
            <span className="text-muted-foreground">/month</span>
            <span className="font-mono text-lg text-muted-foreground line-through ml-2">$149</span>
            <span className="text-xs text-muted-foreground">/mo</span>
          </div>
          <div className="inline-block bg-gold/10 text-gold px-2 py-1 rounded font-mono text-xs font-semibold mb-2">
            Save $50/mo vs Estate $149/mo
          </div>
          <p className="text-xs text-success mb-3 font-medium">
            $99/month · billed annually at $1,188/year
          </p>
        </>
      ) : (
        <>
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-mono text-4xl text-navy">${displayPrice}</span>
            <span className="text-muted-foreground">/year</span>
            <span className="font-mono text-lg text-muted-foreground line-through ml-2">$1,490</span>
            <span className="text-xs text-muted-foreground">/yr</span>
          </div>
          <div className="inline-block bg-gold/10 text-gold px-2 py-1 rounded font-mono text-xs font-semibold mb-2">
            Save $302/yr vs Estate $1,490/yr
          </div>
          <p className="text-xs text-success mb-3 font-medium">
            $1,188/year · billed annually
          </p>
        </>
      )}

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

// ── Combined WingPoint purchase section ────────────────────────
// Replaces the previous single WingPointPlanCard. Renders the two options
// Jeff requires side by side so a WingPoint customer sees both a $79 Trustee
// plan and a $99 WingPoint plan, each with a monthly/annual billing toggle.
export default function WingPointPlanCard({
  onSubscribe,
  processing,
  isTargetPlan,
  registerCardRef,
}) {
  return (
    <div className="mb-8" data-testid="wingpoint-purchase-section">
      <div className="flex items-center gap-2 mb-1">
        <h3 className="font-serif text-xl text-navy">Choose Your WingPoint Plan</h3>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        WingPoint customers get two exclusive options — both include annual billing savings.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <TrusteeOptionCard
          onSubscribe={onSubscribe}
          processing={processing}
          isTargetPlan={isTargetPlan === true || isTargetPlan === 'trustee'}
          cardRef={registerCardRef ? registerCardRef('trustee') : undefined}
        />
        <WingPointOptionCard
          onSubscribe={onSubscribe}
          processing={processing}
          isTargetPlan={isTargetPlan === true || isTargetPlan === 'wingpoint'}
          cardRef={registerCardRef ? registerCardRef('wingpoint') : undefined}
        />
      </div>
    </div>
  );
}