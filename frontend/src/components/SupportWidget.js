import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { MessageSquare, X, Send, Loader2, CheckCircle2, AlertCircle, Bug, Lightbulb, HelpCircle, MessageSquareText } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';
import { useAuth } from '@/context/AuthContext';
import { trackEvent } from '@/utils/analytics';

const PULSE_SEEN_KEY = 'to_support_widget_seen';
const MAX_CHARS = 1000;

const CATEGORIES = [
  { value: 'Bug', label: 'Bug', icon: Bug },
  { value: 'Feature Request', label: 'Feature Request', icon: Lightbulb },
  { value: 'Question', label: 'Question', icon: HelpCircle },
  { value: 'Feedback', label: 'Feedback', icon: MessageSquareText },
];

/**
 * SupportWidget — persistent floating support/feedback chat bubble.
 *
 * Appears in the bottom-right corner on all authenticated pages. Captures
 * page context (current route + selected trust) and submits a support
 * ticket to POST /feedback with category, page_context, trust_id.
 *
 * Behavior:
 *  - Navy circular bubble with a subtle pulse animation on first appearance
 *    (until the user interacts with it once; flag persisted in localStorage).
 *  - Clicking the bubble toggles a 320px × ~400px panel.
 *  - Panel shows current page route + trust name, category selector, message
 *    textarea (max 1000 chars with live count), and a submit button.
 *  - Success and error states with retry.
 */
export function SupportWidget() {
  const location = useLocation();
  const { user, selectedTrust } = useAuth();

  const [open, setOpen] = useState(false);
  const [pulse, setPulse] = useState(false);
  const [category, setCategory] = useState('Feedback');
  const [message, setMessage] = useState('');
  const [status, setStatus] = useState('idle'); // idle | submitting | success | error
  const panelRef = useRef(null);

  // Show a subtle pulse on first appearance until the user interacts once.
  useEffect(() => {
    if (localStorage.getItem(PULSE_SEEN_KEY) === 'true') return;
    setPulse(true);
  }, []);

  const markInteracted = () => {
    if (pulse) {
      setPulse(false);
      localStorage.setItem(PULSE_SEEN_KEY, 'true');
    }
  };

  const toggleOpen = () => {
    markInteracted();
    setOpen((prev) => !prev);
    trackEvent('support_widget_toggled', { opened: !open });
  };

  const handleClose = () => {
    markInteracted();
    setOpen(false);
  };

  const handleCategoryChange = (cat) => {
    markInteracted();
    setCategory(cat);
  };

  const handleMessageChange = (e) => {
    markInteracted();
    setMessage(e.target.value);
  };

  const reset = () => {
    setStatus('idle');
    setMessage('');
    setCategory('Feedback');
  };

  const submit = async () => {
    if (!message.trim()) return;
    markInteracted();
    setStatus('submitting');
    trackEvent('support_widget_submit_attempt', { category });

    try {
      const res = await fetchWithAuth('/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message.trim(),
          category,
          page_context: location.pathname + location.search,
          trust_id: selectedTrust?._id || selectedTrust?.id || null,
        }),
      });
      if (!res.ok) throw new Error('Failed to submit feedback');
      setStatus('success');
      trackEvent('support_widget_submit_success', { category });
    } catch (err) {
      console.error('Support widget submission error:', err);
      setStatus('error');
      trackEvent('support_widget_submit_error', { category, error: String(err) });
    }
  };

  const trustName = selectedTrust?.name || selectedTrust?.trust_name || null;
  const pageContext = location.pathname + (location.search || '');

  return (
    <>
      {/* Bubble */}
      <button
        onClick={toggleOpen}
        aria-label={open ? 'Close support panel' : 'Open support & feedback'}
        data-testid="support-widget-bubble"
        className={`fixed bottom-5 right-5 z-50 w-14 h-14 rounded-full bg-navy text-white shadow-lg flex items-center justify-center transition-all duration-200 hover:scale-105 hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 ${pulse ? 'to-support-pulse' : ''}`}
      >
        {open ? <X className="w-6 h-6" /> : <MessageSquare className="w-6 h-6" />}
      </button>

      {/* Panel */}
      {open && (
        <div
          ref={panelRef}
          data-testid="support-widget-panel"
          className="fixed bottom-24 right-5 z-50 w-[320px] max-w-[calc(100vw-2.5rem)] bg-white rounded-lg shadow-2xl border border-navy/10 overflow-hidden animate-fade-in flex flex-col"
          style={{ maxHeight: '75vh' }}
        >
          {/* Header */}
          <div className="bg-navy text-white px-4 py-3 flex items-center justify-between flex-shrink-0">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4" />
              <h3 className="font-serif text-base leading-none">Support &amp; Feedback</h3>
            </div>
            <button
              onClick={handleClose}
              aria-label="Close"
              data-testid="support-widget-close"
              className="text-white/80 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="p-4 flex flex-col gap-3 overflow-y-auto">
            {/* Context */}
            <div className="text-xs text-muted-foreground bg-subtle-bg/60 rounded-md px-3 py-2 border border-navy/5 space-y-0.5">
              <div className="flex gap-1.5">
                <span className="font-mono text-[10px] uppercase tracking-wider text-navy/50 mt-0.5">Page</span>
                <span className="truncate font-mono text-[11px] text-navy/80">{pageContext}</span>
              </div>
              {trustName && (
                <div className="flex gap-1.5">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-navy/50 mt-0.5">Trust</span>
                  <span className="truncate text-[11px] text-navy/80">{trustName}</span>
                </div>
              )}
            </div>

            {status === 'success' ? (
              <div className="flex flex-col items-center justify-center text-center py-6 gap-3">
                <CheckCircle2 className="w-10 h-10 text-green-600" />
                <p className="text-sm text-navy font-medium">
                  Thank you! Your message has been sent to our team.
                </p>
                <button
                  onClick={() => {
                    reset();
                    trackEvent('support_widget_reset');
                  }}
                  className="text-xs text-navy/60 hover:text-navy underline underline-offset-2"
                  data-testid="support-widget-send-another"
                >
                  Send another message
                </button>
              </div>
            ) : (
              <>
                {/* Category selector */}
                <div>
                  <label className="text-xs font-medium text-navy/70 mb-1.5 block">Category</label>
                  <div className="grid grid-cols-2 gap-1.5">
                    {CATEGORIES.map((cat) => {
                      const Icon = cat.icon;
                      const active = category === cat.value;
                      return (
                        <button
                          key={cat.value}
                          onClick={() => handleCategoryChange(cat.value)}
                          data-testid={`support-widget-cat-${cat.value.toLowerCase().replace(/\s+/g, '-')}`}
                          className={`flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs border transition-colors ${
                            active
                              ? 'bg-navy text-white border-navy'
                              : 'bg-white text-navy/70 border-navy/15 hover:border-navy/40 hover:bg-navy/5'
                          }`}
                        >
                          <Icon className="w-3.5 h-3.5" />
                          <span className="truncate">{cat.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Message */}
                <div>
                  <label className="text-xs font-medium text-navy/70 mb-1.5 block">Message</label>
                  <textarea
                    value={message}
                    onChange={handleMessageChange}
                    placeholder="Describe your issue, idea, or question…"
                    data-testid="support-widget-message"
                    className="input-trust w-full min-h-[110px] resize-none text-sm"
                    maxLength={MAX_CHARS}
                    disabled={status === 'submitting'}
                  />
                  <div className="flex justify-between items-center mt-1">
                    {status === 'error' ? (
                      <span className="flex items-center gap-1 text-xs text-rust">
                        <AlertCircle className="w-3.5 h-3.5" />
                        Could not send. Please try again.
                      </span>
                    ) : (
                      <span className="text-[10px] text-muted-foreground/60">Sent to the TrustOffice team</span>
                    )}
                    <span className={`text-[10px] ${message.length > MAX_CHARS - 50 ? 'text-rust' : 'text-muted-foreground/60'}`}>
                      {message.length}/{MAX_CHARS}
                    </span>
                  </div>
                </div>

                {/* Submit */}
                <button
                  onClick={submit}
                  disabled={status === 'submitting' || !message.trim()}
                  data-testid="support-widget-submit"
                  className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {status === 'submitting' ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Sending…</>
                  ) : status === 'error' ? (
                    <><Send className="w-4 h-4" /> Retry</>
                  ) : (
                    <><Send className="w-4 h-4" /> Send</>
                  )}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default SupportWidget;