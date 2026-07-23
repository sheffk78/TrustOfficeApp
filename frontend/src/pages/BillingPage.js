import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { 
  CreditCard, 
  Check,
  Clock,
  AlertTriangle,
  ArrowLeft,
  Loader2,
  Calendar,
  Gift,
  XCircle,
  RefreshCw,
  ArrowUpCircle,
  ExternalLink
} from 'lucide-react';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import PageHelpButton from '@/components/PageHelpButton';

// Phase 3: 3-tier pricing structure (Trustee, Estate, Advisor)
// Each tier supports both monthly and annual billing periods.
// Annual price = monthly × 10 (2 months free).
const TIERS = [
  {
    id: 'trustee',
    name: 'Trustee Plan',
    monthly: 79,
    annual: 790,
    trustLimit: '1 trust',
    features: [
      '1 trust record',
      'Governance health tracking',
      'Minutes & distribution management',
      'PDF generation',
      'CSV data export',
      'Priority support'
    ]
  },
  {
    id: 'estate',
    name: 'Estate Plan',
    monthly: 149,
    annual: 1490,
    trustLimit: 'Up to 8 trusts',
    popular: true,
    features: [
      'Everything in Trustee',
      'Up to 8 trusts & entities',
      'Multi-trust dashboard',
      'Recurring task automation',
      'Minutes & distribution management',
      'PDF generation & CSV export'
    ]
  },
  {
    id: 'advisor',
    name: 'Advisor Plan',
    monthly: 399,
    annual: 3990,
    trustLimit: 'Unlimited trusts',
    features: [
      'Everything in Estate',
      'Unlimited trusts & entities',
      'Client view',
      'White-label binder export',
      'Multi-signature approvals',
      'Dedicated account manager'
    ]
  }
];

// Map subscription plan_type to a display name.
// Handles the new tiers (trustee/estate/advisor) AND legacy values
// (monthly/annual) which are now grandfathered Trustee plans.
const planDisplayName = (planType) => {
  switch (planType) {
    case 'trustee': return 'Trustee Plan';
    case 'estate': return 'Estate Plan';
    case 'advisor': return 'Advisor Plan';
    case 'monthly': return 'Trustee Plan (Legacy)';
    case 'annual': return 'Trustee Plan (Legacy)';
    case 'forever_free':
    case 'free':
      return 'Free Plan';
    case 'trial':
      return 'Free Plan';
    default:
      return planType || 'Unknown';
  }
};

// Return the tier price for a given billing period.
const tierPriceFor = (tierId, period) => {
  const tier = TIERS.find((t) => t.id === tierId);
  if (!tier) return null;
  return period === 'annual' ? tier.annual : tier.monthly;
};

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

  const getStatusBadge = () => {
    if (!subscription) return null;
    
    const status = subscription.status;
    const cancelAtPeriodEnd = subscription.cancel_at_period_end;
    
    if (status === 'active' && cancelAtPeriodEnd) {
      return (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-warning/10 text-warning border border-warning/20">
          <Clock className="w-4 h-4" />
          <span className="font-mono text-xs uppercase">Canceling</span>
        </div>
      );
    }
    
    switch (status) {
      case 'active':
        if (subscription?.is_gifted) {
          return (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-gold/20 text-gold border border-gold/30">
              <Gift className="w-4 h-4" />
              <span className="font-mono text-xs uppercase">
                Gifted
              </span>
            </div>
          );
        }
        if (subscription?.plan_type === 'forever_free' || subscription?.plan_type === 'trial' || subscription?.plan_type === 'free') {
          return (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-success/10 text-success border border-success/20">
              <Check className="w-4 h-4" />
              <span className="font-mono text-xs uppercase">
                Free Access
              </span>
            </div>
          );
        }
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-success/10 text-success border border-success/20">
            <Check className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">Active</span>
          </div>
        );
      case 'trialing':
        if (subscription?.is_gifted) {
          return (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-gold/20 text-gold border border-gold/30">
              <Gift className="w-4 h-4" />
              <span className="font-mono text-xs uppercase">
                Gifted
              </span>
            </div>
          );
        }
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-success/10 text-success border border-success/20">
            <Check className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">
              Free Access
            </span>
          </div>
        );
      case 'expired':
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-error/10 text-error border border-error/20">
            <AlertTriangle className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">Access Expired</span>
          </div>
        );
      case 'past_due':
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-warning/10 text-warning border border-warning/20">
            <AlertTriangle className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">Payment Due</span>
          </div>
        );
      case 'canceled':
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-muted text-muted-foreground border border-border">
            <XCircle className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">Canceled</span>
          </div>
        );
      default:
        return null;
    }
  };

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

  // Trust limit display for the current subscription.
  const trustLimitLabel = () => {
    if (isGrandfathered) {
      return `Grandfathered: ${legacyTrustLimit} trusts`;
    }
    const tier = TIERS.find((t) => t.id === normalizedPlanType);
    return tier ? tier.trustLimit : '—';
  };

  return (
    <div className="main-layout" data-testid="billing-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container max-w-4xl">
          {/* WingPoint upgrade banner */}
          {actionParam === 'upgrade' && !isWp && (
            <div className="mb-4 p-4 bg-gold/10 border border-gold/30 rounded-lg flex items-center gap-3" data-testid="wp-upgrade-banner">
              <ArrowUpCircle className="w-5 h-5 text-navy flex-shrink-0" />
              <p className="text-sm text-navy font-medium">
                Upgrade your plan to manage all your trusts.
              </p>
            </div>
          )}

          {/* WingPoint upgrade banner (enhanced for ?wp=1) */}
          {actionParam === 'upgrade' && isWp && (
            <div className="mb-4 p-4 bg-gold/10 border border-gold/30 rounded-lg" data-testid="wp-upgrade-banner">
              <div className="flex items-start gap-3">
                <ArrowUpCircle className="w-5 h-5 text-navy flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-navy mb-1">
                    You have more trusts than your current plan supports.
                  </p>
                  <p className="text-sm text-navy/80 mb-2">
                    Your WingPoint purchase included additional trust credits, but your current plan covers fewer trusts than you now have. To access all your trusts, upgrade to a higher plan.
                  </p>
                  <p className="text-sm text-success font-medium mb-3">
                    Your $50 WingPoint coupon still applies if you upgrade now.
                  </p>
                  <Button
                    onClick={() => {
                      const tierSection = document.querySelector('[data-testid="tier-change-section"]');
                      if (tierSection) tierSection.scrollIntoView({ behavior: 'smooth' });
                    }}
                    className="btn-primary"
                    data-testid="wp-upgrade-cta"
                  >
                    <ArrowUpCircle className="w-4 h-4 mr-2" />
                    Upgrade My Plan
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* WingPoint resubscribe banner */}
          {actionParam === 'resubscribe' && !isWp && (
            <div className="mb-4 p-4 bg-gold/10 border border-gold/30 rounded-lg flex items-center gap-3" data-testid="wp-resubscribe-banner">
              <RefreshCw className="w-5 h-5 text-navy flex-shrink-0" />
              <p className="text-sm text-navy font-medium flex-1">
                Your new trust has been added. Reactivate your subscription to manage all your trusts.
              </p>
              <Button
                onClick={() => {
                  const reactivateBtn = document.querySelector('[data-testid="reactivate-btn"]');
                  if (reactivateBtn) {
                    reactivateBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  } else {
                    const statusCard = document.querySelector('[data-testid="subscription-status-card"]');
                    if (statusCard) statusCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  }
                }}
                variant="outline"
                size="sm"
                className="border-gold/40 text-navy hover:bg-gold/10"
                data-testid="wp-resubscribe-cta"
              >
                <RefreshCw className="w-4 h-4 mr-2" />
                Reactivate
              </Button>
            </div>
          )}

          {/* WingPoint resubscribe banner (enhanced for ?wp=1) */}
          {actionParam === 'resubscribe' && isWp && (
            <div className="mb-4 p-4 bg-gold/10 border border-gold/30 rounded-lg flex items-center gap-3" data-testid="wp-resubscribe-banner">
              <RefreshCw className="w-5 h-5 text-navy flex-shrink-0" />
              <p className="text-sm text-navy font-medium flex-1">
                Your new WingPoint trust has been added. Reactivate your subscription to manage all your trusts.
              </p>
              <Button
                onClick={() => {
                  const reactivateBtn = document.querySelector('[data-testid="reactivate-btn"]');
                  if (reactivateBtn) {
                    reactivateBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  } else {
                    const statusCard = document.querySelector('[data-testid="subscription-status-card"]');
                    if (statusCard) statusCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  }
                }}
                variant="outline"
                size="sm"
                className="border-gold/40 text-navy hover:bg-gold/10"
                data-testid="wp-resubscribe-cta"
              >
                <RefreshCw className="w-4 h-4 mr-2" />
                Reactivate
              </Button>
            </div>
          )}

          {/* WingPoint update payment banner */}
          {actionParam === 'update_payment' && !isWp && (
            <div className="mb-4 p-4 bg-gold/10 border border-gold/30 rounded-lg flex items-center gap-3" data-testid="wp-update-payment-banner">
              <CreditCard className="w-5 h-5 text-navy flex-shrink-0" />
              <p className="text-sm text-navy font-medium flex-1">
                Your trust has been added. Update your payment method to keep your subscription active.
              </p>
              <Button
                onClick={() => {
                  const manageBtn = document.querySelector('[data-testid="manage-billing-btn"]');
                  if (manageBtn) manageBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }}
                variant="outline"
                size="sm"
                className="border-gold/40 text-navy hover:bg-gold/10"
                data-testid="wp-update-payment-cta"
              >
                <CreditCard className="w-4 h-4 mr-2" />
                Update Payment
              </Button>
            </div>
          )}

          {/* WingPoint update payment banner (enhanced for ?wp=1) */}
          {actionParam === 'update_payment' && isWp && (
            <div className="mb-4 p-4 bg-gold/10 border border-gold/30 rounded-lg flex items-center gap-3" data-testid="wp-update-payment-banner">
              <CreditCard className="w-5 h-5 text-navy flex-shrink-0" />
              <p className="text-sm text-navy font-medium flex-1">
                Your WingPoint trust has been added. Update your payment method to keep your subscription active.
              </p>
              <Button
                onClick={() => {
                  const manageBtn = document.querySelector('[data-testid="manage-billing-btn"]');
                  if (manageBtn) manageBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }}
                variant="outline"
                size="sm"
                className="border-gold/40 text-navy hover:bg-gold/10"
                data-testid="wp-update-payment-cta"
              >
                <CreditCard className="w-4 h-4 mr-2" />
                Update Payment
              </Button>
            </div>
          )}

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
            {/* Phase 3: billing period toggle for the no-subscription plan picker */}
            <div className="flex justify-center mb-6">
              <div className="inline-flex items-center bg-subtle-bg border border-border rounded-full p-1">
                <button
                  type="button"
                  onClick={() => setPickerBillingPeriod('monthly')}
                  className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${pickerBillingPeriod === 'monthly' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
                >
                  Monthly
                </button>
                <button
                  type="button"
                  onClick={() => setPickerBillingPeriod('annual')}
                  className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${pickerBillingPeriod === 'annual' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
                >
                  Annual <span className="ml-1 text-xs text-success">2 months free</span>
                </button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              {TIERS.map(tier => (
                <div
                  key={tier.id}
                  ref={(el) => { planCardRefs.current[tier.id] = el; }}
                  className={`card-trust relative ${tier.popular ? 'border-gold/30 bg-gold/5' : ''} ${targetPlan === tier.id ? 'ring-2 ring-gold ring-offset-2 ring-offset-subtle-bg' : ''}`}
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
                      ${pickerBillingPeriod === 'annual' ? tier.annual : tier.monthly}
                    </span>
                    <span className="text-muted-foreground">/{pickerBillingPeriod === 'annual' ? 'year' : 'month'}</span>
                  </div>
                  {pickerBillingPeriod === 'annual' && (
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
                    onClick={() => handleSubscribe(tier.id, pickerBillingPeriod)}
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
              ))}
            </div>
            </>
          ) : (
            <>
              {/* Current Subscription Status */}
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
                  {getStatusBadge()}
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
                        {(() => {
                          // Resolve the price for the current tier + billing period.
                          // Legacy monthly/annual map to the Trustee tier price.
                          const price = tierPriceFor(normalizedPlanType, subscription?.billing_period || 'monthly');
                          if (price == null) return 'N/A';
                          const periodLabel = subscription?.billing_period === 'annual' ? '/year' : '/month';
                          return `$${price}${periodLabel}`;
                        })()}
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
                          onClick={handleReactivate}
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
                      onClick={handleManageBilling}
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
                      onClick={handleCancel}
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

                {/* Phase 3: Tier change section for active paid subscriptions.
                    Lets an existing subscriber switch to Trustee/Estate/Advisor
                    (or switch billing period) via the change-plan endpoint. */}
                {isActivePaidSubscription && !isCanceling && (
                  <div className="mt-8" data-testid="tier-change-section">
                    <h3 className="font-serif text-xl text-navy mb-1">Change Your Plan</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Upgrade or downgrade at any time. Changes are prorated for the remainder of your billing cycle.
                    </p>
                    <div className="flex justify-center mb-6">
                      <div className="inline-flex items-center bg-subtle-bg border border-border rounded-full p-1">
                        <button
                          type="button"
                          onClick={() => setChangePlanBillingPeriod('monthly')}
                          className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${changePlanBillingPeriod === 'monthly' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
                        >
                          Monthly
                        </button>
                        <button
                          type="button"
                          onClick={() => setChangePlanBillingPeriod('annual')}
                          className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${changePlanBillingPeriod === 'annual' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
                        >
                          Annual
                          <span className="ml-1 text-xs opacity-70">2 months free</span>
                        </button>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {TIERS.map((tier) => {
                        const isCurrentTier = tier.id === normalizedPlanType;
                        const isUpgrade = TIERS.findIndex((t) => t.id === tier.id) > currentTierIndex;
                        return (
                          <div
                            key={tier.id}
                            ref={(el) => { planCardRefs.current[tier.id] = el; }}
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
                                ${changePlanBillingPeriod === 'annual' ? tier.annual : tier.monthly}
                              </span>
                              <span className="text-muted-foreground text-sm">
                                /{changePlanBillingPeriod === 'annual' ? 'year' : 'month'}
                              </span>
                            </div>
                            <Button
                              onClick={() => handleChangePlan(tier.id, changePlanBillingPeriod)}
                              disabled={(isCurrentTier && changePlanBillingPeriod === currentBillingPeriod) || actionLoading === 'change-plan'}
                              variant={isUpgrade ? 'default' : 'outline'}
                              className={`w-full mt-3 ${isUpgrade ? 'btn-primary' : ''}`}
                              data-testid={`change-to-${tier.id}-btn`}
                            >
                              {actionLoading === 'change-plan' ? (
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                              ) : null}
                              {isCurrentTier && changePlanBillingPeriod === currentBillingPeriod
                                ? 'Current Plan'
                                : isCurrentTier && changePlanBillingPeriod !== currentBillingPeriod
                                ? `Switch to ${changePlanBillingPeriod === 'annual' ? 'Annual' : 'Monthly'}`
                                : isUpgrade ? 'Upgrade' : 'Switch'}
                            </Button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Pricing Plans — Show for free plan, expired, or non-active subscriptions */}
              {(isFreePlan || !isActivePaidSubscription) && (
                <>
                  <h3 className="font-serif text-xl text-navy mb-4">Choose a Plan</h3>
                  {/* Phase 3: billing period toggle for the no-subscription plan picker */}
                  <div className="flex justify-center mb-6">
                    <div className="inline-flex items-center bg-subtle-bg border border-border rounded-full p-1">
                      <button
                        type="button"
                        onClick={() => setPickerBillingPeriod('monthly')}
                        className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${pickerBillingPeriod === 'monthly' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
                      >
                        Monthly
                      </button>
                      <button
                        type="button"
                        onClick={() => setPickerBillingPeriod('annual')}
                        className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${pickerBillingPeriod === 'annual' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
                      >
                        Annual <span className="ml-1 text-xs text-success">2 months free</span>
                      </button>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                    {TIERS.map(tier => (
                      <div 
                        key={tier.id}
                        className={`card-trust relative ${tier.popular ? 'border-gold/30 bg-gold/5' : ''}`}
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
                            ${pickerBillingPeriod === 'annual' ? tier.annual : tier.monthly}
                          </span>
                          <span className="text-muted-foreground">/{pickerBillingPeriod === 'annual' ? 'year' : 'month'}</span>
                        </div>
                        {pickerBillingPeriod === 'annual' && (
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
                          onClick={() => handleSubscribe(tier.id, pickerBillingPeriod)}
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
                    ))}
                  </div>
                </>
              )}

              {/* Billing FAQ */}
              <div className="card-trust">
                <h3 className="font-serif text-lg text-navy mb-4">Frequently Asked Questions</h3>
                <div className="space-y-4 text-sm">
                  <div>
                    <p className="font-medium text-navy">What happens when I cancel?</p>
                    <p className="text-muted-foreground mt-1">
                      You'll retain full access until the end of your current billing period. After that, you won't be charged again.
                    </p>
                  </div>
                  <div>
                    <p className="font-medium text-navy">Can I switch between plans?</p>
                    <p className="text-muted-foreground mt-1">
                      Yes! You can upgrade, downgrade, or switch between monthly and annual billing at any time. Changes are prorated for your current billing cycle.
                    </p>
                  </div>
                  <div>
                    <p className="font-medium text-navy">Is my data safe after cancellation?</p>
                    <p className="text-muted-foreground mt-1">
                      Your data is retained for 90 days after cancellation. You can resubscribe at any time to regain access.
                    </p>
                  </div>
                </div>
              </div>

              {/* Support Info */}
              <div className="mt-8 text-center text-sm text-muted-foreground">
                <p>
                  Questions about billing?{' '}
                  <a href="mailto:support@trustoffice.app" className="text-navy hover:text-navy/70">
                    Contact support
                  </a>
                </p>
                <p className="mt-2 flex items-center justify-center gap-2">
                  <CreditCard className="w-4 h-4" />
                  Payments processed securely through Stripe
                </p>
              </div>
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
