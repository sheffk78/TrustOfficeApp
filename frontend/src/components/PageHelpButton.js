import React, { useEffect } from 'react';
import { usePageHelp } from '@/context/PageHelpContext';

/**
 * PageHelpButton — Contextual help registrar for the current page.
 *
 * This component is now INVISIBLE. It registers its help items, Trust
 * Assistant prompt, and context alerts into PageHelpContext so the global
 * <AssistantFab /> can display them in its popover.
 *
 * Props:
 *   items: Array of { text: string } — 2-3 bullet points about what to do on this page
 *   taPrompt: string — prompt sent to Trust Assistant when user clicks "Ask TA"
 *   contextAlerts: Array of { text: string, prompt: string } — proactive alerts
 *
 * Usage (unchanged from before):
 *   <PageHelpButton
 *     items={[{ text: '...' }, { text: '...' }]}
 *     taPrompt="Walk me through the Dashboard"
 *   />
 */
const PageHelpButton = ({ items = [], taPrompt = '', contextAlerts = [] }) => {
  const { setHelpConfig } = usePageHelp();

  // Push help config into context whenever props change.
  // The AssistantFab reads this to populate its popover.
  useEffect(() => {
    setHelpConfig({ items, taPrompt, contextAlerts });
    // Cleanup: reset when component unmounts (page navigation)
    return () => setHelpConfig({ items: [], taPrompt: '', contextAlerts: [] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(items), taPrompt, JSON.stringify(contextAlerts)]);

  return null; // renders nothing — AssistantFab is the visible UI
};

export default PageHelpButton;