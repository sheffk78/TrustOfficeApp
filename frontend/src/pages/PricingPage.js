import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { getUtmParams } from '@/utils/utm';
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
    tagline: 'Unlimited trusts, white-label exports',
    monthly: 399,
    annual: 3990,
    trustLimit: 'Unlimited trusts',
    popular: false,
    features: [
      'Unlimited trusts & entities',
      'Everything in Estate',
      'Multi-trust dashboard',
      'Recurring task automation',
      'White-label binder export',
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
  { label: 'Client view', trustee: false, estate: false, advisor: 'Q3 2026' },
  { label: 'White-label binder export', trustee: false, estate: false, advisor: true },
  { label: 'Multi-signature approvals', trustee: false, estate: false, advisor: 'Q3 2026' },
  { label: 'Priority email support', trustee: false, estate: false, advisor: true },
];

// WingPoint plan descriptions shown on the pre-selected plan card.
const WP_PLAN_DESCRIPTIONS = {
  trustee: 'Perfect for your single WingPoint trust. Manage one trust with full access to documents and amendments.',
  estate: 'Ideal if you have WingPoints Estate Bundle. Manage up to 8 trusts for family, properties, or business entities.',
  advisor: 'For WingPoint Builder Bundle customers managing multiple trusts. Unlimited trusts, priority support.',
  wingpoint: 'Your exclusive WingPoint plan: unlimited trusts at a special rate not available on our public pricing page. Choose monthly for flexibility or annual for the best value.'
};

export default function PricingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const [loading, setLoading] = useState(null);
  const [couponApplied, setCouponApplied] = useState(false);
  // Monthly / annual billing toggle (Phase 3)
  const [billingPeriod, setBillingPeriod] = useState('monthly');
  // WingPoint card has its own billing period toggle (defaults to annual for best value)
  const [wingPointPeriod, setWingPointPeriod] = useState('annual');
  // Trustee card in the WingPoint section has its own toggle (defaults to monthly)
  const [trusteePeriod, setTrusteePeriod] = useState('monthly');
  
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
      
            // If WingPoint connect flow, redirect to connect page after successful checkout
      const wpConnectAfter = sessionStorage.getItem('wp_connect_after');
      const wpConnectParams = sessionStorage.getItem('wp_connect_params');
      let successUrl = `${baseUrl}/dashboard?welcome=true`;
      if (wpConnectAfter === '1' && wpConnectParams) {
        // After checkout, redirect to the WingPoint connect flow
        successUrl = `${baseUrl}/connect/wingpoint?${wpConnectParams}&from_checkout=1`;
      }

      const checkoutData = {
        plan_type: planType,
        billing_period: period,
        success_url: successUrl,
        cancel_url: `${baseUrl}/pricing${couponCode ? `?coupon=${couponCode}` : ''}`
      };

      // Add marketing attribution (UTM) so direct-to-checkout conversions can
      // be attributed to ad campaigns.
      const utm = getUtmParams();
      if (utm.utm_source) checkoutData.utm_source = utm.utm_source;
      if (utm.utm_campaign) checkoutData.utm_campaign = utm.utm_campaign;
      if (utm.utm_medium) checkoutData.utm_medium = utm.utm_medium;
      if (utm.referrer) checkoutData.referrer = utm.referrer;
      
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
      {/* Skip-to-content link for keyboard / screen-reader users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-navy focus:text-white focus:rounded"
      >
        Skip to main content
      </a>
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
      <section id="main-content" className="py-16 px-8 text-center">
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
          <div className="max-w-3xl mx-auto bg-subtle-bg border border-border rounded-lg p-8 text-center">
            <h2 className="font-serif text-3xl text-navy mb-4" data-testid="wp-banner-headline">
              Your trust is ready. Activate it with your exclusive WingPoint plan.
            </h2>
            <p className="text-base text-muted-foreground max-w-2xl mx-auto mb-6 leading-relaxed">
              You purchased your trust through WingPoint. TrustOffice is where that trust lives, managed, updated, and accessible whenever you need it. As a WingPoint customer, you get unlimited trusts at a special rate not available to the public.
            </p>
            <div className="inline-block bg-gold/10 text-navy px-5 py-3 rounded-full text-sm font-medium mb-3">
              Unlimited trusts from $99/mo (annual) or $119/mo (monthly). WingPoint exclusive.
            </div>
            <p className="text-sm text-success mt-2 font-medium">
              Save $240/year with annual billing. Monthly available for flexibility.
            </p>
          </div>
        </section>
      )}

      {/* WingPoint Two-Card Choice: Trustee vs WingPoint Annual
          (shown whenever ?wp=1 is present, regardless of ?plan=) */}
      {isWingPointFlow && (() => {
        const trusteeTier = TIERS.find((t) => t.id === 'trustee');
        return (
          <section className="pb-8 px-8 pt-6" data-testid="wp-preselected-card">
            <div className="max-w-4xl mx-auto">
              <div className="grid md:grid-cols-2 gap-8 items-stretch">
                {/* Card 1: Trustee Plan — $79/mo or $66/mo (1 trust) */}
                <div className="card-trust corner-mark p-8 border border-border relative overflow-visible flex flex-col">
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-navy text-white px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-full shadow-md whitespace-nowrap z-10">
                    1 Trust
                  </div>
                  <div className="text-center mt-4 flex-1 flex flex-col">
                    <h2 className="font-serif text-3xl text-navy mb-2">Trustee Plan</h2>
                    <p className="text-base text-muted-foreground mb-4 max-w-xs mx-auto">
                      {WP_PLAN_DESCRIPTIONS['trustee']}
                    </p>

                    {/* Monthly/Annual toggle */}
                    <div className="flex justify-center mb-4">
                      <div className="inline-flex items-center bg-subtle-bg border border-border rounded-full p-1">
                        <button
                          type="button"
                          onClick={() => setTrusteePeriod('monthly')}
                          className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${trusteePeriod === 'monthly' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
                        >
                          Monthly
                        </button>
                        <button
                          type="button"
                          onClick={() => setTrusteePeriod('annual')}
                          className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${trusteePeriod === 'annual' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
                        >
                          Annual <span className="ml-1 text-success">2 months free</span>
                        </button>
                      </div>
                    </div>

                    {/* Price display */}
                    {trusteePeriod === 'monthly' ? (
                      <>
                        <div className="flex items-baseline justify-center gap-1 mb-1">
                          <span className="font-serif text-5xl text-navy">$79</span>
                          <span className="text-muted-foreground">/mo</span>
                        </div>
                        <p className="text-sm text-muted-foreground mb-4">billed monthly · cancel anytime</p>
                      </>
                    ) : (
                      <>
                        <div className="flex items-baseline justify-center gap-1 mb-1">
                          <span className="font-serif text-5xl text-navy">$66</span>
                          <span className="text-muted-foreground">/mo</span>
                        </div>
                        <p className="text-sm text-success font-medium mb-1">Save $158/yr (2 months free)</p>
                        <p className="text-sm text-muted-foreground mb-4">billed annually ($790/year)</p>
                      </>
                    )}

                    <div className="inline-block bg-subtle-bg border border-border text-navy px-4 py-2 rounded-full text-sm font-medium mb-6 self-center">
                      1 trust &middot; all governance tools
                    </div>
                  </div>
                  <Button
                    onClick={() => handleCheckout('trustee', trusteePeriod)}
                    disabled={loading !== null}
                    className="w-full btn-primary text-lg py-6"
                    data-testid="wp-confirm-plan-btn"
                  >
                    {loading === 'trustee' ? 'Loading...' : `Choose Trustee (${trusteePeriod === 'annual' ? 'Annual' : 'Monthly'})`}
                    <ArrowRight className="w-5 h-5 ml-2" />
                  </Button>
                </div>

                {/* Card 2: WingPoint — $119/mo or $99/mo (unlimited trusts) */}
                <div className="card-trust corner-mark p-8 border-2 border-gold relative overflow-visible flex flex-col">
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gold text-navy px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-full shadow-md whitespace-nowrap z-10">
                    WingPoint Exclusive
                  </div>
                  <div className="text-center mt-4 flex-1 flex flex-col">
                    <h2 className="font-serif text-3xl text-navy mb-2">WingPoint Plan</h2>
                    <p className="text-base text-muted-foreground mb-4 max-w-xs mx-auto">
                      {WP_PLAN_DESCRIPTIONS['wingpoint']}
                    </p>

                    {/* Monthly/Annual toggle */}
                    <div className="flex justify-center mb-4">
                      <div className="inline-flex items-center bg-subtle-bg border border-border rounded-full p-1">
                        <button
                          type="button"
                          onClick={() => setWingPointPeriod('monthly')}
                          className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${wingPointPeriod === 'monthly' ? 'bg-gold text-white' : 'text-muted-foreground hover:text-navy'}`}
                        >
                          Monthly
                        </button>
                        <button
                          type="button"
                          onClick={() => setWingPointPeriod('annual')}
                          className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${wingPointPeriod === 'annual' ? 'bg-gold text-white' : 'text-muted-foreground hover:text-navy'}`}
                        >
                          Annual <span className="ml-1 text-success">save $240/yr</span>
                        </button>
                      </div>
                    </div>

                    {/* Price display */}
                    {wingPointPeriod === 'monthly' ? (
                      <>
                        <div className="flex items-baseline justify-center gap-1 mb-1">
                          <span className="font-serif text-5xl text-navy">$119</span>
                          <span className="text-muted-foreground">/mo</span>
                        </div>
                        <p className="text-sm text-muted-foreground mb-4">billed monthly · cancel anytime</p>
                      </>
                    ) : (
                      <>
                        <div className="flex items-baseline justify-center gap-1 mb-1">
                          <span className="font-serif text-5xl text-navy">$99</span>
                          <span className="text-muted-foreground">/mo</span>
                        </div>
                        <p className="text-sm text-muted-foreground mb-4">billed annually ($1,188/year)</p>
                      </>
                    )}

                    {/* Savings callout — makes it clear this is the best deal */}
                    <div className="bg-navy/5 border border-navy/10 rounded-lg p-4 mb-4 text-left">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">Public Advisor plan</span>
                        <span className="text-sm font-mono text-muted-foreground line-through">${wingPointPeriod === 'monthly' ? '399/mo' : '3,990/yr'}</span>
                      </div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium text-navy">Your WingPoint rate</span>
                        <span className="text-sm font-mono font-bold text-navy">${wingPointPeriod === 'monthly' ? '119/mo' : '1,188/yr'}</span>
                      </div>
                      <div className="flex items-center justify-between pt-2 border-t border-navy/10">
                        <span className="text-sm font-bold text-gold">You save</span>
                        <span className="text-lg font-mono font-bold text-gold">${wingPointPeriod === 'monthly' ? '280/mo' : '2,802/year'}</span>
                      </div>
                    </div>

                    <div className="inline-block bg-gold/20 text-navy px-4 py-2 rounded-full text-sm font-medium mb-6 self-center">
                      Unlimited trusts &middot; {wingPointPeriod === 'annual' ? 'annual' : 'monthly'}
                    </div>
                  </div>
                  <Button
                    onClick={() => handleCheckout('wingpoint', wingPointPeriod)}
                    disabled={loading !== null}
                    className="w-full btn-primary text-lg py-6"
                    data-testid="wp-confirm-wingpoint-btn"
                  >
                    {loading === 'wingpoint' ? 'Loading...' : `Start Your WingPoint Plan (${wingPointPeriod === 'annual' ? 'Annual' : 'Monthly'})`}
                    <ArrowRight className="w-5 h-5 ml-2" />
                  </Button>
                </div>
              </div>

              {/* Comparison line between the two options */}
              <div className="text-center mt-4">
                <p className="text-sm text-muted-foreground">
                  <span className="font-medium text-navy">1 trust</span> vs{' '}
                  <span className="font-medium text-navy">Unlimited trusts</span> &mdash; choose the plan that fits you.
                </p>
              </div>

              {/* "See other plans" link so users can still scroll to Estate/Advisor */}
              <div className="text-center mt-2">
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
                className={`card-trust corner-mark p-8 relative overflow-visible ${isPopular ? 'border-2 border-gold mt-4' : ''} ${targetPlan === tier.id ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
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