import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';

/**
 * Dashboard-level banners.
 *
 * The subscription upgrade banner ("Your current plan supports N trusts but
 * you have M…") has been REMOVED — all upgrade/subscription/purchase
 * messaging is now consolidated into the single <UpgradeBar /> rendered at
 * the app root (App.js). This avoids two competing upgrade messages on the
 * dashboard.
 *
 * What remains here is the WingPoint persistent banner, which is NOT an
 * upgrade message — it notifies the user that their WingPoint trust
 * documents are ready for review.
 */
export function DashboardBanners({ wpBannerVisible }) {
  return (
    <>
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