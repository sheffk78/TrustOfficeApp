/**
 * Shared severity styles for risk/compliance UI components.
 *
 * Used by: RiskDashboardPage, StateCompliancePage
 *
 * Shape (object form for RiskDashboard-style usage):
 *   { border, bg, text, icon, badge, label }
 *
 * Shape (string form for StateCompliance-style usage):
 *   'bg-red-100 text-red-700 border-red-200'
 *
 * Access via SEVERITY_STYLES[severity].badge (object) or
 * SEVERITY_STYLES_FLAT[severity] (string for className directly).
 */
export const SEVERITY_STYLES = {
  high: {
    border: 'border-red-200',
    bg: 'bg-red-50',
    text: 'text-red-800',
    icon: 'text-red-600',
    badge: 'bg-red-100 text-red-700 border-red-200',
    label: 'High',
  },
  medium: {
    border: 'border-warning/20',
    bg: 'bg-warning/5',
    text: 'text-warning',
    icon: 'text-warning',
    badge: 'bg-warning/10 text-warning border-warning/20',
    label: 'Medium',
  },
  low: {
    border: 'border-slate-200',
    bg: 'bg-slate-50',
    text: 'text-slate-700',
    icon: 'text-slate-500',
    badge: 'bg-slate-100 text-slate-600 border-slate-200',
    label: 'Low',
  },
};

// Flat string form for components that use className strings directly
// (e.g. <span className={SEVERITY_STYLES_FLAT[severity]}>
export const SEVERITY_STYLES_FLAT = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-warning/10 text-warning border-warning/20',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
};