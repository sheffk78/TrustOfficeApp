import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import {
  CreditCard,
  ArrowLeft,
} from 'lucide-react';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import PageHelpButton from '@/components/PageHelpButton';

// Extracted pricing config + components (frontend/src/pages/billing/)
import { TIERS, WINGPOINT_TIER, planDisplayName, tierPriceFor } from './billing/pricingConfig';
import PlanCard from './billing/PlanCard';
import WingPointPlanCard from './billing/WingPointPlanCard';
import BillingPeriodToggle from './billing/BillingPeriodToggle';
import WingPointBanners from './billing/WingPointBanners';
import SubscriptionStatusCard from './billing/SubscriptionStatusCard';
import TierChangeSection from './billing/TierChangeSection';
import BillingFAQ from './billing/BillingFAQ';

export default function BillingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const [subscription, setSubscription] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);
  // Phase 3: billing period toggle for the no-subscription plan picker
  const [pickerBillingPeriod, setPickerBillingPeriod] = useState('monthly');
  const [changePlanBillingPeriod, setChangePlanBillingPeriod] = useState('monthly');

  // WingPoint flow: ?plan=XX triggers auto-scroll + highlight on the matching
  // tier card; ?action=upgrade shows a contextual banner at the top.
  const targetPlan = searchParams.get('plan');
  const actionParam = searchParams.get('action');
  const wpParam = searchParams.get('wp');
  const isWp = wpParam === '1';
  const planCardRefs = useRef({});

  const registerCardRef = (tierId) => (el) => { planCardRefs.current[tierId] = el; };

  useEffect(() => {
    loadSubscription();
    
    // Check for payment verification
    const sessionId = searchParams.get('session_id');
    if (sessionId) {
      verifyPayment(sessionId);
    }
  }, [searchParams]);

  // Auto-scroll to the target plan card once data has loaded and the card
  // is present in the DOM.  Runs whenever loading flips to false or the
  // target plan param changes.
  useEffect(() => {
    if (!loading && targetPlan && planCardRefs.current[targetPlan]) {
      planCardRefs.current[targetPlan].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [loading, targetPlan]);

  const loadSubscription = async () => {
    setLoading(true);
    try {
      const response = await fetchWithAuth('/subscription');
      if (response.ok) {
        const data = await response.json();
        setSubscription(data);
        if (data?.billing_period) {
          setChangePlanBillingPeriod(data.billing_period);
        }
      }
    } catch (error) {
      console.error('Failed to load subscription:', error);
    } finally {
      setLoading(false);
    }
  };

  const verifyPayment = async (sessionId) => {
    setProcessing(true);
    try {
      const response = await fetchWithAuth(`/subscription/verify-payment?session_id=${sessionId}`);
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
          toast.success('Payment successful! Your subscription is now active.');
          loadSubscription();
          navigate('/settings/billing', { replace: true });
        }
      }
    } catch (error) {
      console.error('Payment verification failed:', error);
    } finally {
      setProcessing(false);
    }
  };

  const handleSubscribe = async (planId, period = 'monthly') => {
    setProcessing(true);
    try {
      const currentUrl = window.location.origin;
      const checkoutData = {
        plan_type: planId,
        billing_period: period,
        success_url: `${currentUrl}/dashboard?welcome=true`,
        cancel_url: `${currentUrl}/settings/billing`
      };
      
      // Add Rewardful referral ID for affiliate tracking
      if (typeof window !== 'undefined' && window.Rewardful && window.Rewardful.referral) {
        checkoutData.referral_id = window.Rewardful.referral;
      }
      
      const response = await fetchWithAuth('/subscription/create-checkout', {
        method: 'POST',
        body: JSON.stringify(checkoutData)
      });
      
      if (response.ok) {
        const data = await response.json();
        window.location.href = data.checkout_url;
      } else {
        showError(toast, new Error('Checkout session could not be started. Please try again or contact support@trustoffice.app.'), { operation: 'create_checkout', page: 'Billing' });
        setProcessing(false);
      }
    } catch (error) {
      showError(toast, error, { operation: 'create_checkout', page: 'Billing' });
      setProcessing(false);
    }
  };

  // Phase 3: change-plan endpoint for tier upgrades/downgrades.
  // Body: { plan_type, billing_period }. Used by the existing-subscription
  // "Change Plan" buttons rendered for each tier card below.
  const handleChangePlan = async (planId, period = 'monthly') => {
    if (!window.confirm(`Change your plan to ${planDisplayName(planId)} (${period})? Your billing will be prorated for the remainder of your current cycle.`)) {
      return;
    }
    setActionLoading('change-plan');
    try {
      const response = await fetchWithAuth('/subscription/change-plan', {
        method: 'POST',
        body: JSON.stringify({ plan_type: planId, billing_period: period })
      });
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message || `Plan changed to ${planDisplayName(planId)}.`);
        loadSubscription();
      } else {
        const error = await response.json();
        showError(toast, new Error(error.detail || 'Could not change plan. Please try again or contact support@trustoffice.app.'), { operation: 'change_plan', page: 'Billing' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'change_plan', page: 'Billing' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async () => {
    if (!window.confirm('Are you sure you want to cancel your subscription? You will retain access until the end of your current billing period.')) {
      return;
    }
    
    setActionLoading('cancel');
    try {
      const response = await fetchWithAuth('/subscription/cancel', { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        loadSubscription();
      } else {
        const error = await response.json();
        showError(toast, new Error(error.detail || 'Could not cancel subscription. Please try again or contact support@trustoffice.app.'), { operation: 'cancel_subscription', page: 'Billing' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'cancel_subscription', page: 'Billing' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleReactivate = async () => {
    setActionLoading('reactivate');
    try {
      const response = await fetchWithAuth('/subscription/reactivate', { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        loadSubscription();
      } else {
        const error = await response.json();
        showError(toast, new Error(error.detail || 'Could not reactivate subscription. Please try again or contact support@trustoffice.app.'), { operation: 'reactivate_subscription', page: 'Billing' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'reactivate_subscription', page: 'Billing' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleManageBilling = async () => {
    setActionLoading('portal');
    try {
      const currentUrl = window.location.origin;
      const response = await fetchWithAuth('/subscription/create-portal', {
        method: 'POST',
        body: JSON.stringify({
          return_url: `${currentUrl}/settings/billing`
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        window.location.href = data.portal_url;
      } else {
        const error = await response.json();
        showError(toast, new Error(error.detail || 'Could not open billing portal. Please try again or contact support@trustoffice.app.'), { operation: 'billing_portal', page: 'Billing' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'billing_portal', page: 'Billing' });
    } finally {
      setActionLoading(null);
    }
  };

  const formatDate = (isoString) => {
    if (!isoString) return null;
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    });
  };

  // ── Derived subscription predicates ──────────────────────────
  const isFreePlan = subscription?.plan_type === 'forever_free' || subscription?.plan_type === 'trial' || subscription?.plan_type === 'none' || subscription?.plan_type === 'free';
  const isActivePaidSubscription = subscription?.status === 'active' && !isFreePlan;
  const isCanceling = subscription?.cancel_at_period_end;

  // Phase 3: tier-aware upgrade logic.
  // The backend now returns plan_type as trustee/estate/advisor, with
  // billing_period as monthly/annual. Legacy monthly/annual subscribers are
  // grandfathered as Trustee. canUpgrade is true whenever there's a higher
  // tier available (or an Estate/Advisor user can switch to annual billing).
  const currentPlanType = subscription?.plan_type;
  // Normalize legacy plan types to the Trustee tier for tier comparison.
  const normalizedPlanType =
    currentPlanType === 'monthly' || currentPlanType === 'annual' ? 'trustee' : currentPlanType;
  const currentTierIndex = TIERS.findIndex((t) => t.id === normalizedPlanType);
  const currentBillingPeriod = subscription?.billing_period || 'monthly';
  const isLegacyPlan = currentPlanType === 'monthly' || currentPlanType === 'annual';
  const legacyTrustLimit = subscription?.legacy_trust_limit;
  const isGrandfathered = isLegacyPlan && legacyTrustLimit != null;

  // There are higher tiers available OR same tier with a different billing
  // period (e.g. switch from monthly to annual).
  const canUpgrade =
    isActivePaidSubscription &&
    !isCanceling &&
    (currentTierIndex < TIERS.length - 1 || currentBillingPeriod === 'monthly');

  // Shared ref-callback factory for plan/tier cards.
  const tierCardRef = (tierId) => registerCardRef(tierId);

  return (
    <div className="main-layout" data-testid="billing-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container max-w-4xl">
          {/* WingPoint contextual banners (upgrade / resubscribe / update_payment) */}
          <WingPointBanners actionParam={actionParam} isWp={isWp} />

          {/* Back Button */}
          <Button 
            onClick={() => navigate('/settings')}
            variant="ghost"
            className="mb-4 text-navy hover:text-navy/70"
            data-testid="back-to-settings-btn"
          >
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Settings
          </Button>

          {/* Page Header */}
          <div className="page-header flex items-start justify-between">
            <div>
              <h1 className="page-title">Billing & Subscription</h1>
              <p className="page-subtitle">
                Manage your subscription, billing history, and payment methods — upgrade, downgrade, or cancel at any time
              </p>
            </div>
            <PageHelpButton
              items={[
                { text: 'Manage your subscription plan, billing history, and payment methods' },
                { text: 'Upgrade, downgrade, or cancel your plan at any time' },
                { text: 'View invoices and payment receipts' },
              ]}
              taPrompt="Help me understand the Billing page and my subscription options"
            />
          </div>

          {loading ? (
            <div className="card-trust">
              <div className="skeleton h-32 w-full"></div>
            </div>
          ) : !subscription ? (
            /* Designed empty state — no subscription data loaded, show plans below */
            <>
            <div className="card-trust corner-mark" data-testid="billing-empty-state">
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="w-16 h-16 flex items-center justify-center bg-navy/5 mb-4">
                  <CreditCard className="w-8 h-8 text-navy/40" />
                </div>
                <h2 className="font-serif text-2xl text-navy mb-2">No Billing Information Yet</h2>
                <p className="text-sm text-muted-foreground max-w-md mb-6">
                  You don't have a subscription or billing history yet. Choose a plan below to unlock
                  full access to TrustOffice's trust governance tools, priority support, and PDF generation.
                </p>
                <Button
                  onClick={() => {
                    const plansSection = document.querySelector('[data-testid="plan-card-trustee"]');
                    if (plansSection) plansSection.scrollIntoView({ behavior: 'smooth' });
                  }}
                  className="btn-primary"
                  data-testid="view-plans-btn"
                >
                  <CreditCard className="w-4 h-4 mr-2" />
                  View Plans
                </Button>
              </div>
            </div>
            {/* Pricing Plans for no-subscription state */}
            <h3 className="font-serif text-xl text-navy mb-4">Choose a Plan</h3>
            <BillingPeriodToggle value={pickerBillingPeriod} onChange={setPickerBillingPeriod} />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              {TIERS.map(tier => (
                <PlanCard
                  key={tier.id}
                  tier={tier}
                  billingPeriod={pickerBillingPeriod}
                  onSubscribe={handleSubscribe}
                  processing={processing}
                  isTargetPlan={targetPlan === tier.id}
                  cardRef={tierCardRef(tier.id)}
                />
              ))}
            </div>
            {/* WingPoint-exclusive plan card — only for WingPoint customers */}
            {user?.is_wingpoint && (
              <WingPointPlanCard
                onSubscribe={handleSubscribe}
                processing={processing}
                isTargetPlan={targetPlan === WINGPOINT_TIER.id}
                cardRef={tierCardRef(WINGPOINT_TIER.id)}
              />
            )}
            </>
          ) : (
            <>
              {/* Current Subscription Status */}
              <SubscriptionStatusCard
                subscription={subscription}
                isFreePlan={isFreePlan}
                isActivePaidSubscription={isActivePaidSubscription}
                isCanceling={isCanceling}
                isGrandfathered={isGrandfathered}
                legacyTrustLimit={legacyTrustLimit}
                normalizedPlanType={normalizedPlanType}
                canUpgrade={canUpgrade}
                formatDate={formatDate}
                actionLoading={actionLoading}
                onReactivate={handleReactivate}
                onManageBilling={handleManageBilling}
                onCancel={handleCancel}
              />

              {/* Phase 3: Tier change section for active paid subscriptions. */}
              {isActivePaidSubscription && !isCanceling && (
                <TierChangeSection
                  billingPeriod={changePlanBillingPeriod}
                  onBillingPeriodChange={setChangePlanBillingPeriod}
                  normalizedPlanType={normalizedPlanType}
                  currentTierIndex={currentTierIndex}
                  currentBillingPeriod={currentBillingPeriod}
                  targetPlan={targetPlan}
                  onChangePlan={handleChangePlan}
                  actionLoading={actionLoading}
                  cardRef={tierCardRef}
                />
              )}

              {/* Pricing Plans — Show for free plan, expired, or non-active subscriptions */}
              {(isFreePlan || !isActivePaidSubscription) && (
                <>
                  <h3 className="font-serif text-xl text-navy mb-4">Choose a Plan</h3>
                  <BillingPeriodToggle value={pickerBillingPeriod} onChange={setPickerBillingPeriod} />
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                    {TIERS.map(tier => (
                      <PlanCard
                        key={tier.id}
                        tier={tier}
                        billingPeriod={pickerBillingPeriod}
                        onSubscribe={handleSubscribe}
                        processing={processing}
                        cardRef={tierCardRef(tier.id)}
                      />
                    ))}
                  </div>
                  {/* WingPoint-exclusive plan card — only for WingPoint customers */}
                  {user?.is_wingpoint && (
                    <WingPointPlanCard
                      onSubscribe={handleSubscribe}
                      processing={processing}
                      isTargetPlan={targetPlan === WINGPOINT_TIER.id}
                      cardRef={tierCardRef(WINGPOINT_TIER.id)}
                    />
                  )}
                </>
              )}

              <BillingFAQ />
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}