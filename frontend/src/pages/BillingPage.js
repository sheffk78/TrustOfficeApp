import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { 
  CreditCard, 
  Check,
  Clock,
  AlertTriangle,
  ArrowLeft,
  Loader2
} from 'lucide-react';
import { toast } from 'sonner';

const PLANS = [
  {
    id: 'monthly',
    name: 'Monthly',
    price: 79,
    period: 'month',
    features: [
      'Unlimited trusts & entities',
      'Governance health tracking',
      'Minutes & distribution management',
      'PDF generation',
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
          // Remove session_id from URL
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
      const response = await fetchWithAuth('/subscription/create-checkout', {
        method: 'POST',
        body: JSON.stringify({
          plan_type: planId,
          success_url: `${currentUrl}/settings/billing?session_id={CHECKOUT_SESSION_ID}`,
          cancel_url: `${currentUrl}/settings/billing`
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        // Redirect to Stripe Checkout
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

  const getStatusBadge = () => {
    if (!subscription) return null;
    
    switch (subscription.status) {
      case 'active':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-success/10 text-success">
            <Check className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">Active</span>
          </div>
        );
      case 'trialing':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-navy/10 text-navy">
            <Clock className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">
              Trial • {subscription.days_remaining} days left
            </span>
          </div>
        );
      case 'expired':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-error/10 text-error">
            <AlertTriangle className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">Trial Expired</span>
          </div>
        );
      case 'past_due':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-warning/10 text-warning">
            <AlertTriangle className="w-4 h-4" />
            <span className="font-mono text-xs uppercase">Payment Due</span>
          </div>
        );
      default:
        return null;
    }
  };

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
          >
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Settings
          </Button>

          {/* Page Header */}
          <div className="page-header">
            <h1 className="page-title">Billing & Subscription</h1>
            <p className="page-subtitle">
              Manage your TrustOffice subscription
            </p>
          </div>

          {loading ? (
            <div className="card-trust">
              <div className="skeleton h-32 w-full"></div>
            </div>
          ) : (
            <>
              {/* Current Status */}
              <div className="card-trust corner-mark mb-8">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="label-trust mb-2">Current Plan</p>
                    <h2 className="font-serif text-2xl text-navy capitalize">
                      {subscription?.plan_type || 'Trial'}
                    </h2>
                  </div>
                  {getStatusBadge()}
                </div>

                {subscription?.status === 'expired' && (
                  <div className="mt-6 p-4 bg-error/10 border border-error/20">
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="w-5 h-5 text-error flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="font-medium text-error">Your trial has expired</p>
                        <p className="text-sm text-error/80 mt-1">
                          Subscribe now to continue using TrustOffice. Your data is safe and will be available once you subscribe.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {subscription?.status === 'trialing' && (
                  <div className="mt-6 p-4 bg-navy/5 border border-navy/10">
                    <p className="text-sm text-navy">
                      Your free trial ends in <strong>{subscription.days_remaining} days</strong>. 
                      Subscribe now to ensure uninterrupted access.
                    </p>
                  </div>
                )}

                {subscription?.status === 'active' && (
                  <div className="mt-6 p-4 bg-success/5 border border-success/10">
                    <p className="text-sm text-success">
                      Your subscription is active. Thank you for using TrustOffice!
                    </p>
                  </div>
                )}
              </div>

              {/* Pricing Plans */}
              {subscription?.status !== 'active' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {PLANS.map(plan => (
                    <div 
                      key={plan.id}
                      className={`card-trust ${plan.id === 'annual' ? 'border-gold/30 bg-gold/5' : ''}`}
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
              )}

              {/* FAQ or Additional Info */}
              <div className="mt-8 text-center text-sm text-muted-foreground">
                <p>
                  Questions? Contact us at{' '}
                  <a href="mailto:support@trustoffice.com" className="text-navy hover:text-gold">
                    support@trustoffice.com
                  </a>
                </p>
                <p className="mt-2">
                  Payments are processed securely through Stripe.
                </p>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
