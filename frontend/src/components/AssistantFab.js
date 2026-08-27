import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Bot, ArrowRight, HelpCircle } from 'lucide-react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { usePageHelp } from '@/context/PageHelpContext';
import { useAuth } from '@/context/AuthContext';
import { trackEvent } from '@/utils/analytics';

/**
 * AssistantFab — the single, unified Trust Assistant entry point.
 *
 * Replaces both the old per-page PageHelpButton (?) and the per-page
 * Trust Assistant FAB. Mounted globally in App.js so it appears on every
 * authenticated page.
 *
 * Behavior:
 *  - Gold circular FAB, bottom-right, stacked above the SupportWidget.
 *  - Click opens a popover with the current page's help items + a
 *    contextual "Ask Trust Assistant" link.
 *  - Reads help config from PageHelpContext (set by <PageHelpButton />).
 *  - Hidden on /trust-assistant itself (no FAB on the AI page).
 *  - Hidden when no trust is selected (matches old FAB gating).
 */
const HIDDEN_ROUTES = ['/trust-assistant'];

export function AssistantFab() {
  const location = useLocation();
  const { helpConfig } = usePageHelp();
  const { selectedTrust, user } = useAuth();
  const [open, setOpen] = useState(false);

  // Close popover on route change
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  // Don't render on the Trust Assistant page itself, or if no user/trust
  if (!user || !selectedTrust) return null;
  if (HIDDEN_ROUTES.some(r => location.pathname.startsWith(r))) return null;

  const { items = [], taPrompt = '', contextAlerts = [] } = helpConfig;
  const taPath = taPrompt
    ? `/trust-assistant?prompt=${encodeURIComponent(taPrompt)}`
    : '/trust-assistant';

  const handleOpen = (next) => {
    setOpen(next);
    if (next) trackEvent('assistant_fab_opened', { page: location.pathname });
  };

  return (
    <Popover open={open} onOpenChange={handleOpen}>
      <PopoverTrigger asChild>
        <button
          className="fixed bottom-24 md:bottom-24 right-5 z-40 w-14 h-14 rounded-full bg-gold text-navy shadow-lg flex items-center justify-center transition-all duration-200 hover:scale-105 hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-navy focus:ring-offset-2"
          aria-label="Ask Trust Assistant"
          data-testid="assistant-fab"
        >
          <Bot className="w-6 h-6" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end" sideOffset={8}>
        <div className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Bot className="w-4 h-4 text-gold" />
            <h4 className="font-serif text-lg text-navy">Trust Assistant</h4>
          </div>

          {/* Context alerts (proactive) */}
          {contextAlerts.length > 0 && (
            <div className="mb-3 pb-3 border-b border-navy/10">
              <p className="text-xs font-mono uppercase tracking-wider text-gold mb-2">
                Trust Assistant noticed
              </p>
              {contextAlerts.map((alert, i) => (
                <Link
                  key={i}
                  to={`/trust-assistant?prompt=${encodeURIComponent(alert.prompt)}`}
                  className="block text-sm text-navy hover:text-navy/70 py-1"
                  onClick={() => setOpen(false)}
                >
                  {alert.text}
                </Link>
              ))}
            </div>
          )}

          {/* Page help items */}
          {items.length > 0 && (
            <>
              <p className="text-xs font-mono uppercase tracking-wider text-navy/40 mb-2">
                About this page
              </p>
              <ul className="space-y-2.5 text-sm text-muted-foreground mb-4">
                {items.map((item, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-gold mt-1.5 flex-shrink-0" />
                    <span>{item.text}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {/* Ask Trust Assistant CTA */}
          <div className="pt-3 border-t border-navy/10">
            <Link
              to={taPath}
              className="flex items-center gap-2 text-sm text-gold hover:text-navy/60 font-medium transition-colors"
              onClick={() => {
                setOpen(false);
                trackEvent('assistant_fab_ask_clicked', { page: location.pathname });
              }}
            >
              <Bot className="w-4 h-4" />
              {taPrompt ? 'Ask Trust Assistant about this page' : 'Ask Trust Assistant'}
              <ArrowRight className="w-3 h-3 ml-auto" />
            </Link>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default AssistantFab;