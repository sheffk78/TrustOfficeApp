import { Link } from 'react-router-dom';
import { ArrowRight, Zap, X, Sparkles } from 'lucide-react';

/**
 * Subscription upgrade banner + WingPoint persistent banner.
 * Shown at the top of the dashboard above the page container.
 */
export function DashboardBanners({
  subscription,
  upgradeBannerDismissed,
  setUpgradeBannerDismissed,
  wpBannerVisible,
}) {
  return (
    <>
      {/* Subscription Banners */}
      {subscription?.needs_upgrade && !upgradeBannerDismissed && (
        <div
          className="mx-auto max-w-4xl mt-4 mb-2 border border-warning/30 bg-gradient-to-r from-warning/10 to-warning/5"
          data-testid="upgrade-banner"
        >
          <div className="flex items-center gap-4 p-4">
            <div className="w-10 h-10 bg-warning/20 flex items-center justify-center flex-shrink-0">
              <Zap className="w-5 h-5 text-warning" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-warning">
                Your current plan supports{' '}
                <span className="font-semibold">{subscription.trust_limit}</span> trusts but you have{' '}
                <span className="font-semibold">{subscription.trust_count}</span>. Upgrade to manage all your trusts.
              </p>
            </div>
            <Link
              to="/settings/billing?wp=1&action=upgrade"
              className="inline-flex items-center gap-1.5 h-9 px-4 text-sm font-medium bg-warning text-white hover:bg-warning/90 transition-colors flex-shrink-0"
              data-testid="upgrade-banner-cta"
            >
              Upgrade <ArrowRight className="w-4 h-4" />
            </Link>
            <button
              onClick={() => setUpgradeBannerDismissed(true)}
              className="text-warning/60 hover:text-warning flex-shrink-0"
              aria-label="Dismiss upgrade banner"
              data-testid="upgrade-banner-dismiss"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}

      {/* WingPoint persistent banner — shows after welcome modal dismissal */}
      {wpBannerVisible && (
        <div
          className="mx-auto max-w-4xl mt-4 mb-2 border border-gold/30 bg-gold/10"
          data-testid="wp-persistent-banner"
        >
          <div className="flex items-center gap-4 p-4">
            <div className="w-10 h-10 bg-gold/20 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-5 h-5 text-gold" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-navy">
                Your WingPoint trust is ready.{' '}
                <Link to="/vault" className="font-semibold underline hover:text-navy/70">
                  Review your trust documents.
                </Link>
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}