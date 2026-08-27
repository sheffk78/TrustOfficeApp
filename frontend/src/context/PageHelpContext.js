import React, { createContext, useContext, useState, useRef } from 'react';

/**
 * PageHelpContext — lets any page register its help items, Trust Assistant
 * prompt, and context alerts by rendering <PageHelpButton /> (which now sets
 * this context instead of rendering a visible button).
 *
 * The global <AssistantFab /> consumes this context to show page-specific
 * help inside its popover.
 */
const PageHelpContext = createContext({
  helpConfig: { items: [], taPrompt: '', contextAlerts: [] },
  setHelpConfig: () => {},
});

export const PageHelpProvider = ({ children }) => {
  const [helpConfig, setHelpConfig] = useState({
    items: [],
    taPrompt: '',
    contextAlerts: [],
  });
  // Keep a ref so we can reset on page change without stale closures
  const configRef = useRef(helpConfig);
  configRef.current = helpConfig;

  return (
    <PageHelpContext.Provider value={{ helpConfig, setHelpConfig }}>
      {children}
    </PageHelpContext.Provider>
  );
};

export const usePageHelp = () => {
  const ctx = useContext(PageHelpContext);
  if (!ctx) {
    return { helpConfig: { items: [], taPrompt: '', contextAlerts: [] }, setHelpConfig: () => {} };
  }
  return ctx;
};

export default PageHelpContext;