import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  CheckCircle2, CreditCard, Clock,
} from './onboardingConstants';

const SUBSCRIPTION_FEATURES = [
  'Up to 10 trusts & entities',
  'AI-powered minutes generation',
  'Defensibility tracking',
  'PDF generation & exports',
  'Distribution management',
  'Beneficiary tracking',
];

/**
 * Step shown when the user's subscription has expired — presents upgrade options
 * and a read-only fallback.
 */
export default function ExpiredSubscriptionStep() {
  const navigate = useNavigate();
  return (
    <div className="mt-8">
      <div className="card-trust corner-mark mb-8">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-warning/10 dark:bg-warning/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <Clock className="w-8 h-8 text-warning" />
          </div>
          <h1 className="font-serif text-4xl text-navy mb-3">
            Your Free Access Has Ended
          </h1>
          <p className="text-lg text-muted-foreground max-w-xl mx-auto">
            Subscribe now to continue using TrustOffice and manage your trusts professionally.
          </p>
        </div>

        <div className="bg-navy/5 border border-navy/10 p-6 mb-8">
          <p className="font-medium text-navy mb-4">What you get with TrustOffice:</p>
          <div className="grid md:grid-cols-2 gap-3">
            {SUBSCRIPTION_FEATURES.map(feature => (
              <div key={feature} className="flex items-center gap-2 text-sm">
                <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                <span>{feature}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <Button
            onClick={() => navigate('/pricing')}
            className="btn-primary w-full py-6 text-lg"
            data-testid="subscribe-now-cta"
          >
            <CreditCard className="w-5 h-5 mr-2" />
            Subscribe Now - Starting at $79/month
          </Button>

          <div className="text-center">
            <p className="text-sm text-muted-foreground mb-2">Save 17% with annual billing</p>
          </div>

          <div className="border-t border-border pt-4 mt-2">
            <p className="text-xs text-muted-foreground text-center mb-3">
              Your data is safe. You can view everything in read-only mode.
            </p>
            <Button
              variant="outline"
              onClick={() => {
                localStorage.setItem('skip_onboarding', 'true');
                navigate('/dashboard');
              }}
              className="w-full"
              data-testid="view-readonly-btn"
            >
              Continue in Read-Only Mode
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
