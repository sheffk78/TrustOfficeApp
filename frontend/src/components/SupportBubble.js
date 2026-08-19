import React, { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Send, Loader2, CheckCircle2, ChevronDown } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';

const CATEGORIES = [
  { value: 'bug', label: 'Bug Report' },
  { value: 'feedback', label: 'Feedback' },
  { value: 'question', label: 'Question' },
  { value: 'feature_request', label: 'Feature Request' },
];

const SupportBubble = () => {
  const { user, selectedTrust } = useAuth();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [category, setCategory] = useState('feedback');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [ticketNumber, setTicketNumber] = useState('');
  const textareaRef = useRef(null);

  // Auto-resize textarea
  const autoResize = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
  };

  useEffect(() => {
    if (open && textareaRef.current) {
      setTimeout(() => textareaRef.current?.focus(), 100);
    }
  }, [open]);

  // Reset state when reopened
  useEffect(() => {
    if (open) {
      setSubmitted(false);
      setTicketNumber('');
    }
  }, [open]);

  const handleSubmit = async () => {
    if (!message.trim() || submitting) return;
    setSubmitting(true);
    try {
      const response = await fetchWithAuth('/support/tickets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message.trim(),
          category,
          page_url: window.location.href,
          user_agent: navigator.userAgent,
          trust_id: selectedTrust?.trust_id || null,
          trust_name: selectedTrust?.name || null,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setTicketNumber(data.ticket_number);
        setSubmitted(true);
        setMessage('');
        if (textareaRef.current) textareaRef.current.style.height = 'auto';
      } else {
        const err = await response.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to submit. Please try again.');
      }
    } catch (err) {
      toast.error('Failed to submit. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  if (!user) return null; // Only show for logged-in users

  return (
    <>
      {/* Floating button — bottom right */}
      <button
        onClick={() => setOpen(!open)}
        className={`fixed bottom-6 right-6 z-50 flex items-center justify-center w-12 h-12 rounded-full shadow-lg transition-all duration-200 ${
          open
            ? 'bg-navy text-white rotate-90'
            : 'bg-navy text-white hover:bg-navy/90 hover:scale-105'
        }`}
        title="Support & Feedback"
        aria-label="Open support and feedback"
      >
        {open ? <X className="w-5 h-5" /> : <MessageCircle className="w-5 h-5" />}
      </button>

      {/* Panel — slides up from the button */}
      {open && (
        <div className="fixed bottom-20 right-6 z-50 w-[calc(100vw-3rem)] max-w-sm bg-white dark:bg-slate-800 border border-navy/15 dark:border-white/10 shadow-xl rounded-lg overflow-hidden flex flex-col"
             style={{ maxHeight: '70vh' }}>
          {/* Header */}
          <div className="px-4 py-3 border-b border-navy/10 dark:border-white/10 bg-navy/5 dark:bg-white/5">
            <h3 className="font-serif text-base text-navy dark:text-white">
              {submitted ? 'Ticket Submitted' : 'Support & Feedback'}
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {submitted
                ? 'We received your message'
                : 'Tell us what\'s on your mind — we read every one.'}
            </p>
          </div>

          {submitted ? (
            /* Success state */
            <div className="p-6 flex flex-col items-center text-center gap-3">
              <CheckCircle2 className="w-10 h-10 text-gold" />
              <p className="text-sm text-foreground">
                Thanks{user?.name ? `, ${user.name.split(' ')[0]}` : ''}! Your ticket is in.
              </p>
              <div className="px-3 py-1.5 bg-navy/5 dark:bg-white/5 border border-navy/10 dark:border-white/10 rounded">
                <span className="font-mono text-xs text-muted-foreground">Ticket: </span>
                <span className="font-mono text-xs font-medium text-navy dark:text-white">{ticketNumber}</span>
              </div>
              <p className="text-xs text-muted-foreground">
                We'll review this and get back to you via email.
              </p>
              <button
                onClick={() => setOpen(false)}
                className="mt-2 text-xs font-medium text-navy dark:text-white hover:underline"
              >
                Close
              </button>
            </div>
          ) : (
            /* Form state */
            <div className="flex flex-col flex-1 min-h-0">
              {/* Category selector */}
              <div className="px-4 pt-3 pb-2">
                <div className="flex flex-wrap gap-1.5">
                  {CATEGORIES.map((cat) => (
                    <button
                      key={cat.value}
                      onClick={() => setCategory(cat.value)}
                      className={`text-[10px] uppercase tracking-wider px-2.5 py-1 border transition-colors ${
                        category === cat.value
                          ? 'border-navy bg-navy text-white dark:border-white dark:bg-white dark:text-navy'
                          : 'border-navy/15 text-navy/60 hover:bg-navy/5 dark:border-white/15 dark:text-white/60 dark:hover:bg-white/5'
                      }`}
                    >
                      {cat.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Message textarea */}
              <div className="px-4 pb-3 flex-1 flex flex-col min-h-0">
                <textarea
                  ref={textareaRef}
                  value={message}
                  onChange={(e) => { setMessage(e.target.value); autoResize(); }}
                  onKeyDown={handleKeyDown}
                  placeholder="Describe what you need help with or what you'd like to share…"
                  className="flex-1 min-h-[120px] resize-none text-sm bg-transparent border-0 focus:outline-none placeholder:text-muted-foreground/50 text-foreground leading-relaxed"
                  style={{ maxHeight: '200px' }}
                />
              </div>

              {/* Context indicator */}
              <div className="px-4 pb-2">
                <p className="text-[10px] text-muted-foreground/60 font-mono">
                  Includes your account info, current page, and trust context
                </p>
              </div>

              {/* Submit bar */}
              <div className="px-4 py-3 border-t border-navy/10 dark:border-white/10 flex items-center justify-between">
                <span className="text-[10px] text-muted-foreground font-mono">
                  ⌘+↵ to send
                </span>
                <button
                  onClick={handleSubmit}
                  disabled={!message.trim() || submitting}
                  className="btn-primary px-4 py-2 text-xs font-medium flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {submitting ? (
                    <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Sending…</>
                  ) : (
                    <>Send <Send className="w-3.5 h-3.5" /></>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
};

export default SupportBubble;