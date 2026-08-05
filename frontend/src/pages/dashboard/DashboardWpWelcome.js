import { Button } from '@/components/ui/button';
import { Sparkles, ChevronRight } from 'lucide-react';

/**
 * WingPoint welcome modal — shown for WingPoint-provisioned users.
 * Offers two CTAs: go to trust documents or dismiss for later.
 */
export function DashboardWpWelcome({
  showWpWelcome,
  goToTrustDocsFromWp,
  dismissWpWelcome,
}) {
  if (!showWpWelcome) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy/40" data-testid="wp-welcome-modal">
      <div className="bg-white border border-gold/30 max-w-lg w-full mx-4 p-8">
        <div className="flex items-start gap-4 mb-6">
          <div className="w-12 h-12 bg-gold/10 flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-6 h-6 text-gold" />
          </div>
          <div className="flex-1">
            <h2 className="font-serif text-xl text-navy mb-3">Welcome to TrustOffice, your WingPoint trust is here.</h2>
          </div>
        </div>
        <div className="text-sm text-navy/80 space-y-3 mb-6">
          <p>You are all set. Your trust documents are ready to review, and your management plan is active. Here is what you can do right now:</p>
          <ul className="space-y-2 ml-4">
            <li className="flex items-start gap-2">
              <ChevronRight className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
              <span>Review your trust in the Trust Documents tab.</span>
            </li>
            <li className="flex items-start gap-2">
              <ChevronRight className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
              <span>Add beneficiaries to make sure your trust reflects your wishes.</span>
            </li>
            <li className="flex items-start gap-2">
              <ChevronRight className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
              <span>Schedule a consultation with a trust advisor.</span>
            </li>
          </ul>
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <Button
            onClick={goToTrustDocsFromWp}
            className="btn-primary flex-1"
            data-testid="wp-welcome-go-to-trust"
          >
            Go to My Trust Documents
          </Button>
          <Button
            onClick={dismissWpWelcome}
            variant="outline"
            className="flex-1 btn-secondary"
            data-testid="wp-welcome-dismiss"
          >
            Maybe Later
          </Button>
        </div>
      </div>
    </div>
  );
}