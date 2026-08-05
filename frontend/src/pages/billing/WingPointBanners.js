import { ArrowUpCircle, CreditCard, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

// WingPoint contextual banners driven by ?action= and ?wp= query params.
// Each action has a standard variant (!isWp) and an enhanced variant (isWp).
//
// Props:
//   actionParam – string | null  (the ?action= value)
//   isWp        – boolean        (the ?wp=1 flag)
//
// Internal helpers scroll to the relevant on-page section by testid.
const scrollToTestId = (testid, opts = { behavior: 'smooth', block: 'center' }) => {
  const el = document.querySelector(`[data-testid="${testid}"]`);
  if (el) el.scrollIntoView(opts);
};

// ── Upgrade banner ───────────────────────────────────────────────
const UpgradeBanner = ({ isWp }) => {
  if (isWp) {
    return (
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
              onClick={() => scrollToTestId('tier-change-section')}
              className="btn-primary"
              data-testid="wp-upgrade-cta"
            >
              <ArrowUpCircle className="w-4 h-4 mr-2" />
              Upgrade My Plan
            </Button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="mb-4 p-4 bg-gold/10 border border-gold/30 rounded-lg flex items-center gap-3" data-testid="wp-upgrade-banner">
      <ArrowUpCircle className="w-5 h-5 text-navy flex-shrink-0" />
      <p className="text-sm text-navy font-medium">
        Upgrade your plan to manage all your trusts.
      </p>
    </div>
  );
};

// ── Resubscribe banner ──────────────────────────────────────────
const ResubscribeBanner = ({ isWp }) => (
  <div className="mb-4 p-4 bg-gold/10 border border-gold/30 rounded-lg flex items-center gap-3" data-testid="wp-resubscribe-banner">
    <RefreshCw className="w-5 h-5 text-navy flex-shrink-0" />
    <p className="text-sm text-navy font-medium flex-1">
      {isWp
        ? 'Your new WingPoint trust has been added. Reactivate your subscription to manage all your trusts.'
        : 'Your new trust has been added. Reactivate your subscription to manage all your trusts.'}
    </p>
    <Button
      onClick={() => {
        const reactivateBtn = document.querySelector('[data-testid="reactivate-btn"]');
        if (reactivateBtn) {
          reactivateBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
          scrollToTestId('subscription-status-card', { behavior: 'smooth', block: 'center' });
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
);

// ── Update payment banner ───────────────────────────────────────
const UpdatePaymentBanner = ({ isWp }) => (
  <div className="mb-4 p-4 bg-gold/10 border border-gold/30 rounded-lg flex items-center gap-3" data-testid="wp-update-payment-banner">
    <CreditCard className="w-5 h-5 text-navy flex-shrink-0" />
    <p className="text-sm text-navy font-medium flex-1">
      {isWp
        ? 'Your WingPoint trust has been added. Update your payment method to keep your subscription active.'
        : 'Your trust has been added. Update your payment method to keep your subscription active.'}
    </p>
    <Button
      onClick={() => scrollToTestId('manage-billing-btn', { behavior: 'smooth', block: 'center' })}
      variant="outline"
      size="sm"
      className="border-gold/40 text-navy hover:bg-gold/10"
      data-testid="wp-update-payment-cta"
    >
      <CreditCard className="w-4 h-4 mr-2" />
      Update Payment
    </Button>
  </div>
);

// Renders the single matching banner for the current action, or null.
export default function WingPointBanners({ actionParam, isWp }) {
  if (!actionParam) return null;
  if (actionParam === 'upgrade') return <UpgradeBanner isWp={isWp} />;
  if (actionParam === 'resubscribe') return <ResubscribeBanner isWp={isWp} />;
  if (actionParam === 'update_payment') return <UpdatePaymentBanner isWp={isWp} />;
  return null;
}