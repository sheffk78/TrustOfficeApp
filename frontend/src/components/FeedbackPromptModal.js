import { useState, useEffect, useRef } from 'react';
import { MessageSquareText, X, Send, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { trackEvent } from '@/utils/analytics';

const STORAGE_KEY = 'to_feedback_prompt_dismissed';

/**
 * Feedback Prompt — non-blocking corner toast.
 *
 * Shows a small, non-intrusive card pinned to the bottom-right corner asking
 * the user for product feedback after they've created their 3rd minutes entry.
 *
 * The card starts collapsed (just a label + expand button). Clicking expand
 * reveals the textarea and submit button. The user can dismiss it at any time;
 * dismissal is persisted in localStorage so it shows at most once per user.
 *
 * Props:
 *   show — boolean, parent controls visibility based on minutes count
 */
export function FeedbackPromptModal({ show }) {
  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const cardRef = useRef(null);

  useEffect(() => {
    if (!show) return;
    const dismissed = localStorage.getItem(STORAGE_KEY);
    if (!dismissed) {
      setVisible(true);
      trackEvent('feedback_prompt_shown', { source: 'third_minutes_created' });
    }
  }, [show]);

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    setVisible(false);
    trackEvent('feedback_prompt_dismissed', { source: 'third_minutes_created' });
  };

  const submit = async () => {
    if (!feedback.trim()) {
      toast.error('Please enter your feedback before submitting.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetchWithAuth('/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: feedback.trim() }),
      });
      if (!res.ok) throw new Error('Failed to submit feedback');
      localStorage.setItem(STORAGE_KEY, 'true');
      setVisible(false);
      setFeedback('');
      toast.success('Thank you! Your feedback helps us improve TrustOffice.');
      trackEvent('feedback_prompt_submitted', { source: 'third_minutes_created' });
    } catch (err) {
      console.error('Feedback submission error:', err);
      toast.error('Could not submit feedback. Please try again later.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!visible) return null;

  return (
    <div
      ref={cardRef}
      className="fixed bottom-4 right-4 z-40 w-80 max-w-[calc(100vw-2rem)]"
      data-testid="feedback-prompt-modal"
      role="dialog"
      aria-label="Feedback prompt"
    >
      <div className="bg-white dark:bg-slate-900 border border-navy/20 shadow-lg rounded-lg overflow-hidden">
        {/* Header bar — always visible, click to expand/collapse */}
        <div className="flex items-center justify-between p-3 bg-navy/5 dark:bg-white/5">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-2 text-navy dark:text-white text-sm font-medium hover:text-navy/70 transition-colors flex-1 text-left"
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse feedback form' : 'Expand feedback form'}
          >
            <MessageSquareText className="w-4 h-4 flex-shrink-0" />
            <span className="truncate">How can we improve TrustOffice?</span>
          </button>
          <div className="flex items-center gap-1 flex-shrink-0">
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1 text-muted-foreground hover:text-navy transition-colors"
              aria-label={expanded ? 'Collapse feedback form' : 'Expand feedback form'}
            >
              {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
            </button>
            <button
              onClick={dismiss}
              className="p-1 text-muted-foreground hover:text-navy transition-colors"
              data-testid="feedback-prompt-close"
              aria-label="Dismiss feedback prompt"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Expanded body — textarea + submit */}
        {expanded && (
          <div className="p-4" style={{ animation: 'feedback-slide-in 0.2s ease-out' }}>
            <p className="text-xs text-muted-foreground mb-3">
              You've been using TrustOffice for a bit now. We'd love to hear what's missing,
              what could be easier, or what could be clearer.
            </p>

            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="What's missing? How can it be easier? How can it be more clear?"
              className="w-full min-h-[80px] p-2 border border-navy/20 text-sm text-navy placeholder:text-muted-foreground/60 focus:outline-none focus:border-gold transition-colors resize-none rounded"
              data-testid="feedback-prompt-input"
              maxLength={1000}
              autoFocus
            />
            <p className="text-xs text-muted-foreground/60 mt-1 text-right">
              {feedback.length}/1000
            </p>

            <div className="flex gap-2 mt-3">
              <button
                onClick={submit}
                disabled={submitting || !feedback.trim()}
                className="btn-primary flex-1 flex items-center justify-center gap-1 text-sm py-2 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="feedback-prompt-submit"
              >
                {submitting ? (
                  <><Loader2 className="w-3 h-3 animate-spin" /> Submitting...</>
                ) : (
                  <><Send className="w-3 h-3" /> Submit</>
                )}
              </button>
              <button
                onClick={dismiss}
                className="flex-1 btn-secondary text-sm py-2 rounded"
                data-testid="feedback-prompt-later"
              >
                Maybe Later
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default FeedbackPromptModal;