import React from 'react';
import PageHelpButton from './PageHelpButton';

/**
 * PageHeader — the one canonical page header.
 *
 * Title (Cormorant serif) + subtitle (JetBrains mono, uppercase) on the left,
 * action slot + help registrar on the right. Wraps exactly the markup pattern
 * used across the app (see DistributionsPage for the reference implementation).
 *
 * Props:
 *   title     — string (required)
 *   subtitle  — string
 *   actions   — JSX node(s): buttons on the right, primary action last
 *   help      — object passed straight to <PageHelpButton />:
 *               { items: [{ text }], taPrompt, contextAlerts }
 *   className — extra classes on the wrapper (rare)
 *
 * Do NOT hand-roll page-header markup in pages — copy-pasted headers are how
 * drift started (50+ divergent copies before this component existed).
 */
const PageHeader = ({ title, subtitle, actions = null, help = null, className = '' }) => (
  <div className={`page-header flex items-center justify-between flex-wrap gap-3 ${className}`.trim()}>
    <div className="min-w-0">
      <h1 className="page-title">{title}</h1>
      {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
    </div>
    {(actions || help) && (
      <div className="flex items-center gap-2 flex-wrap">
        {actions}
        {help ? <PageHelpButton {...help} /> : null}
      </div>
    )}
  </div>
);

export default PageHeader;