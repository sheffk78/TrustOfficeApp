import { CreditCard } from 'lucide-react';

// Static billing FAQ + Stripe support info block shown at the bottom of the
// existing-subscription view. Has no props.
export default function BillingFAQ() {
  return (
    <>
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
  );
}