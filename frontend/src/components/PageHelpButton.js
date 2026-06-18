import React from 'react';
import { Link } from 'react-router-dom';
import { HelpCircle, Bot, ArrowRight } from 'lucide-react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';

/**
 * PageHelpButton — Contextual help popover for every page.
 *
 * Props:
 *   items: Array of { text: string } — 2-3 bullet points about what to do on this page
 *   taPrompt: string — prompt sent to Trust Assistant when user clicks "Ask TA"
 *
 * Usage:
 *   <PageHelpButton
 *     items={[
 *       { text: 'View your trust metrics at a glance' },
 *       { text: 'Use Quick Actions to jump to common tasks' },
 *     ]}
 *     taPrompt="Walk me through the Dashboard"
 *   />
 */
const PageHelpButton = ({ items = [], taPrompt = '' }) => {
  const taPath = taPrompt
    ? `/trust-assistant?prompt=${encodeURIComponent(taPrompt)}`
    : '/trust-assistant';

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className="w-8 h-8 rounded-full border border-navy/20 text-navy/50 hover:text-navy hover:border-navy/40 hover:bg-navy/5 transition-all flex items-center justify-center flex-shrink-0"
          aria-label="Help"
          data-testid="page-help-btn"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end" sideOffset={8}>
        <div className="p-5">
          <h4 className="font-serif text-lg text-navy mb-3">About this page</h4>
          {items.length > 0 && (
            <ul className="space-y-2.5 text-sm text-muted-foreground">
              {items.map((item, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-gold mt-1.5 flex-shrink-0" />
                  <span>{item.text}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 pt-4 border-t border-navy/10">
            <Link
              to={taPath}
              className="flex items-center gap-2 text-sm text-gold hover:text-gold/80 font-medium transition-colors"
            >
              <Bot className="w-4 h-4" />
              Ask Trust Assistant about this page
              <ArrowRight className="w-3 h-3 ml-auto" />
            </Link>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default PageHelpButton;
