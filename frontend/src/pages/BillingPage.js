import { useState, useEffect } from 'react';
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
import PageHelpButton from '@/components/PageHelpButton';

const PLANS = [
  {
    id: 'monthly',
    name: 'Monthly',
    price: 79,
    period: 'month',
    features: [
      'Up to 10 trusts & entities',
      'Governance health tracking',
      'Minutes & distribution management',
      'PDF generation',
      'CSV data export',
      'Priority support'
    ]
  },
  {
    id: 'annual',
    name: 'Annual',
    price: 790,
    period: 'year',
    savings: '2 months free',
    features: [
      'Everything in Monthly',
      '2 months free ($158 savings)',
      'Priority onboarding',
      'Dedicated account manager'
    ]
  }
];

export default function BillingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const [subscription, setSubscription] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);

  useEffect(() => {
    loadSubscription();
    
    // Check for payment verification
    const sessionId = searchParams.get('session_id');
    if (sessionId) {
      verifyPayment(sessionId);
    }
  }, [searchParams]);

  const loadSubscription = async () => {
    setLoading(true);
    try {
      const response = await fetchWithAuth('/subscription');
      if (response.ok) {
        setSubscription(await response.json());
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

  const handleSubscribe = async (planId) => {
    setProcessing(true);
    try {
      const currentUrl = window.location.origin;
      const checkoutData = {
        plan_type: planId,
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
        toast.error('Failed to start checkout');
        setProcessing(false);
      }
    } catch (error) {
      toast.error('Failed to start checkout');
      setProcessing(false);
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
        toast.error(error.detail || 'Failed to cancel subscription');
      }
    } catch (error) {
      toast.error('Failed to cancel subscription');
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
        toast.error(error.detail || 'Failed to reactivate subscription');
      }
    } catch (error) {
      toast.error('Failed to reactivate subscription');
    } finally {
      setActionLoading(null);
    }
  };

  const handleUpgrade = async () => {
    if (!window.confirm('Upgrade to annual plan? You will be charged the prorated difference for the remainder of your billing cycle.')) {
      return;
    }
    
    setActionLoading('upgrade');
    try {
      const response = await fetchWithAuth('/subscription/upgrade', { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        loadSubscription();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to upgrade subscription');
      }
    } catch (error) {
      toast.error('Failed to upgrade subscription');
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
        toast.error(error.detail || 'Failed to open billing portal');
      }
    } catch (error) {
      toast.error('Failed to open billing portal');
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
  const canUpgrade = isActivePaidSubscription && subscription?.plan_type === 'monthly' && !isCanceling;

  return (
    <div className="main-layout" data-testid="billing-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container max-w-4xl">
          {/* Back Button */}
          <Button 
            onClick={() => navigate('/settings')}
            variant="ghost"
            className="mb-4 text-navy hover:text-gold"
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
                    const plansSection = document.querySelector('[data-testid="plan-card-monthly"]');
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
              {PLANS.map(plan => (
                <div
                  key={plan.id}
                  className={`card-trust relative ${plan.id === 'annual' ? 'border-gold/30 bg-gold/5' : ''}`}
                  data-testid={`plan-card-${plan.id}`}
                >
                  {plan.savings && (
                    <div className="absolute top-0 right-0 bg-gold text-white px-3 py-1 font-mono text-xs uppercase">
                      {plan.savings}
                    </div>
                  )}
                  <h3 className="font-serif text-xl text-navy mb-2">{plan.name}</h3>
                  <div className="flex items-baseline gap-1 mb-4">
                    <span className="font-mono text-4xl text-navy">${plan.price}</span>
                    <span className="text-muted-foreground">/{plan.period}</span>
                  </div>
                  <ul className="space-y-3 mb-6">
                    {plan.features.map((feature, i) => (
                      <li key={i} className="flex items-center gap-2 text-sm">
                        <Check className="w-4 h-4 text-success flex-shrink-0" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                  <Button
                    onClick={() => handleSubscribe(plan.id)}
                    className={`w-full ${plan.id === 'annual' ? 'btn-primary' : 'btn-secondary'}`}
                    disabled={processing}
                    data-testid={`subscribe-${plan.id}-btn`}
                  >
                    {processing ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <CreditCard className="w-4 h-4 mr-2" />
                        Subscribe to {plan.name}
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
                    <h2 className="font-serif text-2xl text-navy capitalize">
                      {subscription?.plan_type === 'trial' ? 'Free Plan' : 
                       subscription?.plan_type === 'monthly' ? 'Monthly Plan' :
                       subscription?.plan_type === 'annual' ? 'Annual Plan' : 
                       subscription?.plan_type === 'forever_free' ? 'Free Plan' :
                       subscription?.plan_type === 'free' ? 'Free Plan' :
                       subscription?.plan_type || 'Unknown'}
                    </h2>
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
                      <p className="label-trust text-xs mb-1">Monthly Cost</p>
                      <p className="font-mono text-sm text-navy">
                        {subscription.plan_type === 'annual' ? '$65.83/month (billed annually)' : '$79/month'}
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
                        onClick={handleUpgrade}
                        className="btn-primary"
                        disabled={actionLoading === 'upgrade'}
                        data-testid="upgrade-btn"
                      >
                        {actionLoading === 'upgrade' ? (
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                          <ArrowUpCircle className="w-4 h-4 mr-2" />
                        )}
                        Upgrade to Annual (Save $158)
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
              </div>

              {/* Pricing Plans — Show for free plan, expired, or non-active subscriptions */}
              {(isFreePlan || !isActivePaidSubscription) && (
                <>
                  <h3 className="font-serif text-xl text-navy mb-4">Choose a Plan</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                    {PLANS.map(plan => (
                      <div 
                        key={plan.id}
                        className={`card-trust relative ${plan.id === 'annual' ? 'border-gold/30 bg-gold/5' : ''}`}
                        data-testid={`plan-card-${plan.id}`}
                      >
                        {plan.savings && (
                          <div className="absolute top-0 right-0 bg-gold text-white px-3 py-1 font-mono text-xs uppercase">
                            {plan.savings}
                          </div>
                        )}
                        
                        <h3 className="font-serif text-xl text-navy mb-2">{plan.name}</h3>
                        <div className="flex items-baseline gap-1 mb-4">
                          <span className="font-mono text-4xl text-navy">${plan.price}</span>
                          <span className="text-muted-foreground">/{plan.period}</span>
                        </div>
                        
                        <ul className="space-y-3 mb-6">
                          {plan.features.map((feature, i) => (
                            <li key={i} className="flex items-center gap-2 text-sm">
                              <Check className="w-4 h-4 text-success flex-shrink-0" />
                              <span>{feature}</span>
                            </li>
                          ))}
                        </ul>
                        
                        <Button 
                          onClick={() => handleSubscribe(plan.id)}
                          className={`w-full ${plan.id === 'annual' ? 'btn-primary' : 'btn-secondary'}`}
                          disabled={processing}
                          data-testid={`subscribe-${plan.id}-btn`}
                        >
                          {processing ? (
                            <>
                              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                              Processing...
                            </>
                          ) : (
                            <>
                              <CreditCard className="w-4 h-4 mr-2" />
                              Subscribe to {plan.name}
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
                      Yes! You can upgrade from monthly to annual at any time. The difference will be prorated for your current billing cycle.
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
                  <a href="mailto:support@trustoffice.com" className="text-navy hover:text-gold">
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
