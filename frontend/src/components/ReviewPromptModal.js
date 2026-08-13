import { useEffect, useState } from 'react';
import { Star, X, ExternalLink } from 'lucide-react';
import { trackEvent } from '@/utils/analytics';

const TRUSTPILOT_URL = 'https://www.trustpilot.com/evaluate/trustoffice.app';
const STORAGE_KEY = 'to_review_prompt_dismissed';

/**
 * TrustPilot Review Prompt Modal.
 *
 * Shows a non-intrusive popup inviting the user to leave a TrustPilot review.
 * Triggered when onboarding is complete (all steps done) OR checklist is dismissed.
 * Shows once per user — dismissal is persisted in localStorage.
 *
 * Props:
 *   show — boolean, parent controls visibility based on onboarding state
 */
export function ReviewPromptModal({ show }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!show) return;
    // Only show if not previously dismissed
    const dismissed = localStorage.getItem(STORAGE_KEY);
    if (!dismissed) {
      setVisible(true);
      trackEvent('review_prompt_shown', { source: 'onboarding_complete' });
    }
  }, [show]);

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    setVisible(false);
    trackEvent('review_prompt_dismissed', { source: 'onboarding_complete' });
  };

  const goToTrustpilot = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    setVisible(false);
    trackEvent('review_prompt_clicked', { source: 'onboarding_complete' });
    window.open(TRUSTPILOT_URL, '_blank', 'noopener,noreferrer');
  };

  if (!visible) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy/40" data-testid="review-prompt-modal">
      <div className="bg-white border border-gold/30 max-w-md w-full mx-4 p-6 relative" style={{ animation: 'zoom-in 0.2s ease-out' }}>
        {/* Close button */}
        <button
          onClick={dismiss}
          className="absolute right-4 top-4 text-muted-foreground hover:text-navy transition-colors"
          data-testid="review-prompt-close"
          aria-label="Dismiss"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Star icon */}
        <div className="flex items-center gap-1 mb-4">
          {[1, 2, 3, 4, 5].map(i => (
            <Star key={i} className="w-6 h-6 text-gold fill-gold" />
          ))}
        </div>

        <h2 className="font-serif text-xl text-navy mb-3">
          Enjoying TrustOffice?
        </h2>
        <p className="text-sm text-navy/80 mb-4 leading-relaxed">
          Your review helps others discover how TrustOffice makes trust administration
          simpler and more defensible. It takes just a minute — and it means a lot to us.
        </p>

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={goToTrustpilot}
            className="btn-primary flex-1 flex items-center justify-center gap-2"
            data-testid="review-prompt-cta"
          >
            Leave a Review
            <ExternalLink className="w-4 h-4" />
          </button>
          <button
            onClick={dismiss}
            variant="outline"
            className="flex-1 btn-secondary"
            data-testid="review-prompt-later"
          >
            Maybe Later
          </button>
        </div>
      </div>
    </div>
  );
}

export default ReviewPromptModal;