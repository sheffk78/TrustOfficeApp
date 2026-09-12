import { Link } from 'react-router-dom';
import { Sparkles, ShieldAlert, ShieldCheck, X } from 'lucide-react';

/**
 * Dashboard-level banners.
 *
 * The subscription upgrade banner ("Your current plan supports N trusts but
 * you have M...") has been REMOVED -- all upgrade/subscription/purchase
 * messaging is now consolidated into the single <UpgradeBar /> rendered at
 * the app root (App.js). This avoids two competing upgrade messages on the
 * dashboard.
 *
 * What remains here is the WingPoint persistent banner, which is NOT an
 * upgrade message -- it notifies the user that their WingPoint trust
 * documents are ready for review.
 *
 * The 2FA admin nag banner is persistent (non-dismissible): admin accounts
 * must enable two-factor authentication. It appears when the login/me
 * payload includes needs_2fa_enrollment: true, or when /auth/2fa/status
 * reports enforced: true with enabled: false.
 */
export function DashboardBanners({
  wpBannerVisible,
  twoFaBannerVisible,
  enrollmentNagVisible,
  onEnrollmentNagDismiss,
}) {
  return (
    <>
      {/* WingPoint persistent banner -- shows after welcome modal dismissal */}
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

      {/* 2FA admin nag - persistent while the account is unenrolled and enforced.
          Keeps priority over the enrollment nag: only one 2FA banner shows. */}
      {twoFaBannerVisible && (
        <div
          className="mx-auto max-w-4xl mt-4 mb-2 border border-error/30 bg-error/10"
          data-testid="twofa-admin-nag-banner"
        >
          <div className="flex items-center gap-4 p-4">
            <div className="w-10 h-10 bg-error/20 flex items-center justify-center flex-shrink-0">
              <ShieldAlert className="w-5 h-5 text-error" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-navy">
                Admin accounts must enable two-factor authentication.{' '}
                <Link to="/settings" className="font-semibold underline hover:text-navy/70" data-testid="twofa-nag-settings-link">
                  Enable it in Settings.
                </Link>
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Enrollment nag - shown to EVERY non-enrolled user (not just admins).
          Dismissible; hides for 7 days then resurfaces once. Skipped entirely
          when the admin enforcement nag is already showing. */}
      {enrollmentNagVisible && !twoFaBannerVisible && (
        <div
          className="mx-auto max-w-4xl mt-4 mb-2 border border-navy/20 bg-navy/5"
          data-testid="twofa-enrollment-nag-banner"
        >
          <div className="flex items-center gap-4 p-4">
            <div className="w-10 h-10 bg-navy/10 flex items-center justify-center flex-shrink-0">
              <ShieldCheck className="w-5 h-5 text-navy" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-navy">
                New: add two-factor authentication to your account. It is a free extra layer of protection when you sign in.{' '}
                <Link
                  to="/settings"
                  className="font-semibold underline hover:text-navy/70"
                  data-testid="twofa-enrollment-nag-settings-link"
                >
                  Enable now
                </Link>
              </p>
            </div>
            <button
              type="button"
              aria-label="Dismiss two-factor authentication reminder"
              onClick={onEnrollmentNagDismiss}
              className="text-navy/50 hover:text-navy flex-shrink-0"
              data-testid="twofa-enrollment-nag-dismiss"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}