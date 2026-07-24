import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Check, ArrowRight } from 'lucide-react';
import { trackCheckoutInitiated } from '@/utils/analytics';

const API_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

// Use XMLHttpRequest for maximum compatibility
const xhrPost = (url, data, token = null) => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Accept', 'application/json');
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }
    
    xhr.onreadystatechange = function() {
      if (xhr.readyState === 4) {
        try {
          const response = xhr.responseText ? JSON.parse(xhr.responseText) : {};
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(response);
          } else {
            reject(new Error(response.detail || `Request failed`));
          }
        } catch (e) {
          reject(new Error('Invalid server response'));
        }
      }
    };
    
    xhr.onerror = function() {
      reject(new Error('Network error'));
    };
    
    xhr.send(data ? JSON.stringify(data) : null);
  });
};

// 3-tier pricing structure (Phase 3)
// Annual = monthly × 10 (2 months free)
const TIERS = [
  {
    id: 'trustee',
    name: 'Trustee',
    tagline: '1 trust, all governance tools',
    monthly: 79,
    annual: 790,
    trustLimit: '1 trust',
    popular: false,
    features: [
      '1 trust record',
      'Guided minutes templates',
      'Schedule A asset tracking',
      'Distribution management',
      'PDF export with watermark control',
      'Defensibility scoring',
      'Email notifications',
      'Benevolence mode for charitable trusts'
    ]
  },
  {
    id: 'estate',
    name: 'Estate',
    tagline: 'Up to 8 trusts, multi-trust dashboard',
    monthly: 149,
    annual: 1490,
    trustLimit: 'Up to 8 trusts',
    popular: true, // "Most Popular" badge
    features: [
      'Up to 8 trusts & entities',
      'Everything in Trustee',
      'Multi-trust dashboard',
      'Recurring task automation',
      'Guided minutes templates',
      'Schedule A asset tracking',
      'Distribution management',
      'PDF export with watermark control',
      'Defensibility scoring',
      'Email notifications'
    ]
  },
  {
    id: 'advisor',
    name: 'Advisor',
    tagline: 'Unlimited trusts, client view, white-label',
    monthly: 399,
    annual: 3990,
    trustLimit: 'Unlimited trusts',
    popular: false,
    features: [
      'Unlimited trusts & entities',
      'Everything in Estate',
      'Client view',
      'White-label binder export',
      'Multi-signature approvals',
      'Multi-trust dashboard',
      'Recurring task automation',
      'PDF export with watermark control',
      'Defensibility scoring',
      'Priority email support'
    ]
  }
];

// Feature comparison rows for the table below the cards
// Each row: { label, trustee, estate, advisor } where values are true (check) / false (dash) / string
const COMPARISON_ROWS = [
  { label: 'Trust records', trustee: '1', estate: '8', advisor: 'Unlimited' },
  { label: 'Guided minutes templates', trustee: true, estate: true, advisor: true },
  { label: 'Schedule A asset tracking', trustee: true, estate: true, advisor: true },
  { label: 'Distribution management', trustee: true, estate: true, advisor: true },
  { label: 'PDF export with watermark control', trustee: true, estate: true, advisor: true },
  { label: 'Defensibility scoring', trustee: true, estate: true, advisor: true },
  { label: 'Email notifications', trustee: true, estate: true, advisor: true },
  { label: 'Benevolence mode for charitable trusts', trustee: true, estate: true, advisor: true },
  { label: 'Multi-trust dashboard', trustee: false, estate: true, advisor: true },
  { label: 'Recurring task automation', trustee: false, estate: true, advisor: true },
  { label: 'Client view', trustee: false, estate: false, advisor: true },
  { label: 'White-label binder export', trustee: false, estate: false, advisor: true },
  { label: 'Multi-signature approvals', trustee: false, estate: false, advisor: true },
  { label: 'Priority email support', trustee: false, estate: false, advisor: true },
];

// WingPoint plan descriptions shown on the pre-selected plan card.
const WP_PLAN_DESCRIPTIONS = {
  trustee: 'Perfect for your single WingPoint trust. Manage one trust with full access to documents and amendments.',
  estate: 'Ideal if you have WingPoints Estate Bundle. Manage up to 8 trusts for family, properties, or business entities.',
  advisor: 'For WingPoint Builder Bundle customers managing multiple trusts. Unlimited trusts, priority support.',
  wingpoint: 'Your exclusive WingPoint plan: unlimited trusts at a special annual rate not available on our public pricing page.'
};

export default function PricingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const [loading, setLoading] = useState(null);
  const [couponApplied, setCouponApplied] = useState(false);
  // Monthly / annual billing toggle (Phase 3)
  const [billingPeriod, setBillingPeriod] = useState('monthly');
  
  // Get coupon from URL if present
  const couponCode = searchParams.get('coupon') || searchParams.get('promo');

  // WingPoint flow: ?plan=XX triggers auto-scroll + highlight on the matching
  // tier card, exactly like BillingPage.js does.
  const targetPlan = searchParams.get('plan');
  const planCardRefs = useRef({});
  // Ref to the pricing tiers section so the pre-selected plan card's
  // "See other plans" link can scroll to it.
  const pricingTiersRef = useRef(null);

  // WingPoint flow flag - computed at component level so JSX can use it.
  const isWingPointFlow = searchParams.get('wp') === '1';
  // The pre-selected plan from the WingPoint flow (?plan=XX).
  const wingPointPlan = isWingPointFlow && targetPlan ? targetPlan : null;

  useEffect(() => {
    if (couponCode) {
      setCouponApplied(true);
      toast.success(`Coupon "${couponCode}" will be applied at checkout`);
    }
  }, [couponCode]);

  // Auto-scroll to the target plan card after the page has rendered.
  useEffect(() => {
    if (targetPlan && planCardRefs.current[targetPlan]) {
      planCardRefs.current[targetPlan].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [targetPlan]);

  // Phase 3: handleCheckout now takes a tier (trustee/estate/advisor) AND a billing period
  const handleCheckout = async (planType, period = billingPeriod) => {
    // If not logged in, redirect to signup first
    if (!user) {
      // Store intent in sessionStorage so we can continue after signup
      sessionStorage.setItem('checkout_intent', JSON.stringify({
        plan: planType,
        billing_period: period,
        coupon: couponCode
      }));
      toast.info('Please create an account first to start your subscription');
      navigate('/signup');
      return;
    }

    // Already-subscribed guard (Phase 3): authenticated users with an active
    // subscription should manage their plan in billing settings, not re-checkout.
    // WingPoint users arriving with ?wp=1 bypass this guard — they may need to
    // upgrade or change plans even with an active subscription.
    if (user?.subscription?.is_active && !isWingPointFlow) {
      toast.info("You're already subscribed. Manage your plan in Settings.");
      navigate('/settings/billing');
      return;
    }

    setLoading(planType);
    
    try {
      const token = localStorage.getItem('auth_token');
      const baseUrl = window.location.origin;
      
      const checkoutData = {
        plan_type: planType,
        billing_period: period,
        success_url: `${baseUrl}/dashboard?welcome=true`,
        cancel_url: `${baseUrl}/pricing${couponCode ? `?coupon=${couponCode}` : ''}`
      };
      
      // Add coupon if present
      if (couponCode) {
        checkoutData.promotion_code = couponCode;
      }
      
      // Add Rewardful referral ID for affiliate tracking
      if (typeof window !== 'undefined' && window.Rewardful && window.Rewardful.referral) {
        checkoutData.referral_id = window.Rewardful.referral;
      }
      
      const result = await xhrPost(
        `${API_URL}/api/subscription/create-checkout`,
        checkoutData,
        token
      );

      // Track checkout initiated for ad conversion tracking
      trackCheckoutInitiated({
        plan_type: planType,
        billing_period: period,
        origin: 'pricing_page',
      });

      if (result.checkout_url) {
        window.location.href = result.checkout_url;
      } else {
        throw new Error('Failed to create checkout session');
      }
    } catch (error) {
      console.error('Checkout error:', error);
      toast.error(error.message || 'Failed to start checkout');
    } finally {
      setLoading(null);
    }
  };

  const formatPrice = (tier) => {
    if (billingPeriod === 'annual') {
      return { amount: tier.annual, unit: '/year' };
    }
    return { amount: tier.monthly, unit: '/month' };
  };

  const renderComparisonCell = (value) => {
    if (value === true) {
      return <Check className="w-4 h-4 text-success mx-auto" />;
    }
    if (value === false) {
      return <span className="text-muted-foreground">—</span>;
    }
    return <span className="text-sm font-mono text-navy">{value}</span>;
  };

  return (
    <div className="min-h-screen bg-subtle-bg">
      {/* Header */}
      <header className="bg-navy text-white py-6 px-8">
        <div className="max-w-6xl mx-auto flex justify-between items-center">
          <Link to="/" className="flex items-center gap-3">
            <img 
              src="https://customer-assets.emergentagent.com/job_98ad4c89-4a05-4aed-ab1d-a934650bd7f4/artifacts/5h7i559r_Trust%20Office%20Logo%20%281%29.svg"
              alt="TrustOffice"
              className="h-8 brightness-0 invert"
            />
          </Link>
          {user ? (
            <Link to="/dashboard" className="text-sm hover:text-white/70 transition-colors">
              Go to Dashboard
            </Link>
          ) : (
            <Link to="/login" className="text-sm hover:text-white/70 transition-colors">
              Sign In
            </Link>
          )}
        </div>
      </header>

      {/* Hero */}
      <section className="py-16 px-8 text-center">
        <h1 className="font-serif text-4xl md:text-5xl text-navy mb-4">
          Trust Governance Made Simple
        </h1>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-4">
          The workspace for trustees who take their duties seriously.
        </p>
        {couponApplied && (
          <div className="inline-block bg-gold/20 text-navy px-4 py-2 rounded-full text-sm font-medium">
            Coupon "{couponCode}" will be applied at checkout
          </div>
        )}
      </section>

      {/* WingPoint Welcome Banner (only when ?wp=1) */}
      {isWingPointFlow && (
        <section className="pb-6 px-8" data-testid="wp-welcome-banner">
          <div className="max-w-3xl mx-auto bg-navy text-white rounded-lg p-8 text-center">
            <h2 className="font-serif text-3xl mb-4" data-testid="wp-banner-headline">
              Your trust is ready. Activate it with your exclusive WingPoint plan.
            </h2>
            <p className="text-base text-white/80 max-w-2xl mx-auto mb-6 leading-relaxed">
              You purchased your trust through WingPoint. TrustOffice is where that trust lives, managed, updated, and accessible whenever you need it. As a WingPoint customer, you get unlimited trusts at a special annual rate not available to the public.
            </p>
            <div className="inline-block bg-gold/20 text-white px-5 py-3 rounded-full text-sm font-medium mb-3">
              Unlimited trusts for $99/mo, billed annually. WingPoint exclusive.
            </div>
            <p className="text-sm text-white/60 mt-2">
              This special rate is available to WingPoint customers only. Annual commitment required.
            </p>
          </div>
        </section>
      )}

      {/* WingPoint Pre-Selected Plan Card (only when ?wp=1 AND ?plan=XX) */}
      {wingPointPlan && (() => {
        // WingPoint exclusive plan (not in TIERS — annual only, $99/mo, unlimited trusts)
        if (wingPointPlan === 'wingpoint') {
          return (
            <section className="pb-8 px-8" data-testid="wp-preselected-card">
              <div className="max-w-3xl mx-auto">
                <div className="card-trust corner-mark p-8 border-2 border-gold relative">
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gold text-navy px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-full shadow-md whitespace-nowrap z-10">
                    WingPoint Exclusive
                  </div>
                  <div className="text-center mt-4">
                    <h2 className="font-serif text-3xl text-navy mb-2">WingPoint Annual</h2>
                    <p className="text-base text-muted-foreground mb-4 max-w-xl mx-auto">
                      {WP_PLAN_DESCRIPTIONS['wingpoint']}
                    </p>
                    <div className="flex items-baseline justify-center gap-1 mb-2">
                      <span className="font-serif text-5xl text-navy">$99</span>
                      <span className="text-muted-foreground">/mo</span>
                    </div>
                    <p className="text-sm text-muted-foreground mb-4">billed annually ($1,188/year)</p>
                    <div className="inline-block bg-gold/20 text-navy px-4 py-2 rounded-full text-sm font-medium mb-6">
                      Unlimited trusts. Annual commitment required.
                    </div>
                  </div>
                  <Button
                    onClick={() => handleCheckout('wingpoint', 'annual')}
                    disabled={loading !== null}
                    className="w-full btn-primary text-lg py-6"
                    data-testid="wp-confirm-plan-btn"
                  >
                    {loading === 'wingpoint' ? 'Loading...' : 'Start Your WingPoint Plan'}
                    <ArrowRight className="w-5 h-5 ml-2" />
                  </Button>
                  <div className="text-center mt-4">
                    <p className="text-xs text-muted-foreground mb-2">
                      This exclusive rate renews annually. If you cancel, you won't be able to get this pricing again.
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        if (pricingTiersRef.current) {
                          pricingTiersRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                      }}
                      className="text-sm text-navy hover:underline font-medium"
                      data-testid="wp-see-other-plans-link"
                    >
                      See public plans
                    </button>
                  </div>
                </div>
              </div>
            </section>
          );
        }
        // Standard tier plan (trustee/estate/advisor)
        const wpTier = TIERS.find((t) => t.id === wingPointPlan);
        if (!wpTier) return null;
        const wpPrice = formatPrice(wpTier);
        return (
          <section className="pb-8 px-8" data-testid="wp-preselected-card">
            <div className="max-w-3xl mx-auto">
              <div className="card-trust corner-mark p-8 border-2 border-gold relative">
                <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gold text-navy px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-full shadow-md whitespace-nowrap z-10">
                  Recommended for You
                </div>
                <div className="text-center mt-4">
                  <h2 className="font-serif text-3xl text-navy mb-2">{wpTier.name} Plan</h2>
                  <p className="text-base text-muted-foreground mb-4 max-w-xl mx-auto">
                    {WP_PLAN_DESCRIPTIONS[wpTier.id]}
                  </p>
                  <div className="flex items-baseline justify-center gap-1 mb-4">
                    <span className="font-serif text-5xl text-navy">${wpPrice.amount}</span>
                    <span className="text-muted-foreground">{wpPrice.unit}</span>
                  </div>
                  <div className="inline-block bg-gold/20 text-navy px-4 py-2 rounded-full text-sm font-medium mb-6">
                    $50 off your first month, courtesy of WingPoint, already applied at checkout.
                  </div>
                </div>
                <Button
                  onClick={() => handleCheckout(wpTier.id)}
                  disabled={loading !== null}
                  className="w-full btn-primary text-lg py-6"
                  data-testid="wp-confirm-plan-btn"
                >
                  {loading === wpTier.id ? 'Loading...' : 'Confirm and Continue'}
                  <ArrowRight className="w-5 h-5 ml-2" />
                </Button>
                <div className="text-center mt-4">
                  <button
                    type="button"
                    onClick={() => {
                      if (pricingTiersRef.current) {
                        pricingTiersRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
                      }
                    }}
                    className="text-sm text-navy hover:underline font-medium"
                    data-testid="wp-see-other-plans-link"
                  >
                    See other plans
                  </button>
                </div>
              </div>
            </div>
          </section>
        );
      })()}

      {/* Billing Period Toggle (Monthly / Annual) */}
      <section className="pb-6 px-8">
        <div className="max-w-4xl mx-auto flex flex-col items-center">
          <div className="inline-flex items-center bg-subtle-bg border border-border rounded-full p-1" data-testid="billing-period-toggle">
            <button
              type="button"
              onClick={() => setBillingPeriod('monthly')}
              className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${billingPeriod === 'monthly' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
              data-testid="billing-period-monthly"
            >
              Monthly
            </button>
            <button
              type="button"
              onClick={() => setBillingPeriod('annual')}
              className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${billingPeriod === 'annual' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
              data-testid="billing-period-annual"
            >
              Annual
              <span className="ml-2 text-xs text-success">2 months free</span>
            </button>
          </div>
        </div>
      </section>

      {/* Pricing Cards — 3 tiers side by side */}
      <section ref={pricingTiersRef} className="pb-12 px-8 scroll-mt-4">
        <div className="max-w-6xl mx-auto grid md:grid-cols-3 gap-8">
          {TIERS.map((tier) => {
            const { amount, unit } = formatPrice(tier);
            const isPopular = tier.popular;
            return (
              <div
                key={tier.id}
                ref={(el) => { planCardRefs.current[tier.id] = el; }}
                className={`card-trust corner-mark p-8 relative ${isPopular ? 'border-2 border-gold mt-4' : ''} ${targetPlan === tier.id ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
                data-testid={`tier-card-${tier.id}`}
              >
                {isPopular && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gold text-navy px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-full shadow-md whitespace-nowrap z-10">
                    Most Popular
                  </div>
                )}
                <div className="text-center mb-8">
                  <h2 className="font-serif text-2xl text-navy mb-2">{tier.name}</h2>
                  <p className="text-sm text-muted-foreground mb-3">{tier.tagline}</p>
                  <div className="flex items-baseline justify-center gap-1">
                    <span className="font-serif text-5xl text-navy">${amount}</span>
                    <span className="text-muted-foreground">{unit}</span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-2">
                    {billingPeriod === 'annual'
                      ? `Billed annually (${tier.trustLimit.toLowerCase()})`
                      : `Billed monthly, cancel anytime (${tier.trustLimit.toLowerCase()})`}
                  </p>
                  {billingPeriod === 'annual' && (
                    <p className="text-sm text-success font-medium mt-1">
                      Save ${tier.monthly * 2} (2 months free)
                    </p>
                  )}
                </div>
                
                <ul className="space-y-3 mb-8">
                  {tier.features.map((feature, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <Check className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
                      <span className="text-sm">{feature}</span>
                    </li>
                  ))}
                </ul>
                
                <Button 
                  onClick={() => handleCheckout(tier.id)}
                  disabled={loading !== null}
                  className={`w-full ${isPopular ? 'btn-primary' : 'btn-secondary'}`}
                  data-testid={`${tier.id}-checkout-btn`}
                >
                  {loading === tier.id ? 'Loading...' : 'Get Started'}
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </div>
            );
          })}
        </div>
      </section>

      {/* Feature Comparison Table */}
      <section className="pb-20 px-8">
        <div className="max-w-5xl mx-auto">
          <h2 className="font-serif text-2xl text-navy text-center mb-8">Compare Plans</h2>
          <div className="card-trust overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left p-4 font-mono text-xs uppercase text-muted-foreground">Features</th>
                  <th className="text-center p-4 font-serif text-navy">Trustee</th>
                  <th className="text-center p-4 font-serif text-navy bg-gold/5">Estate</th>
                  <th className="text-center p-4 font-serif text-navy">Advisor</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON_ROWS.map((row, i) => (
                  <tr key={i} className={`border-b border-border/50 ${i % 2 === 1 ? 'bg-subtle-bg/50' : ''}`}>
                    <td className="text-left p-4 text-navy">{row.label}</td>
                    <td className="text-center p-4">{renderComparisonCell(row.trustee)}</td>
                    <td className="text-center p-4 bg-gold/5">{renderComparisonCell(row.estate)}</td>
                    <td className="text-center p-4">{renderComparisonCell(row.advisor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Trial Note */}
      <section className="pb-12 px-8">
        <p className="text-center text-sm text-muted-foreground max-w-2xl mx-auto">
          Subscribe to start — $79/month for Trustee, $149/month for Estate, or $399/month for Advisor. 
          Save 2 months with annual billing. The trust pays for governance tools the same way it pays for legal counsel.
        </p>
      </section>

      {/* Footer */}
      <footer className="bg-navy/5 py-8 px-8 text-center text-sm text-muted-foreground">
        <p>&copy; {new Date().getFullYear()} TrustOffice. All rights reserved.</p>
        <div className="mt-2 space-x-4">
          <a href="https://trustoffice.app/support" className="hover:text-navy">Support</a>
          <a href="https://trustoffice.app/privacy-policy/" className="hover:text-navy">Privacy</a>
          <a href="https://trustoffice.app/terms-of-service/" className="hover:text-navy">Terms</a>
        </div>
      </footer>
    </div>
  );
}