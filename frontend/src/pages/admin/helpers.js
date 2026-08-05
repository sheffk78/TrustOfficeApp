// Shared helpers for AdminPage sub-components

export function formatLastActive(lastLogin) {
  if (!lastLogin) return '—';
  const now = new Date();
  const date = new Date(lastLogin);
  const diffMs = now - date;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours === 0) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60));
      if (diffMinutes === 0) return 'Just now';
      return `${diffMinutes} min ago`;
    }
    if (diffHours === 1) return '1 hour ago';
    return `${diffHours} hours ago`;
  }
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 30) return `${diffDays} days ago`;
  return date.toLocaleDateString();
}

const STATUS_STYLES = {
  active: 'bg-success/10 text-success',
  trialing: 'bg-gold/20 text-gold dark:bg-gold/30 dark:text-gold',
  expired: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  canceled: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
  none: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
};

export function getStatusBadgeClass(status) {
  return STATUS_STYLES[status] || STATUS_STYLES.none;
}

export function getLeadStageBadgeClass(stage) {
  switch (stage) {
    case 'new': return 'bg-blue-100 text-blue-800';
    case 'engaged': return 'bg-purple-100 text-purple-800';
    case 'warm': return 'bg-warning/10 text-warning';
    case 'converted': return 'bg-success/10 text-success';
    default: return 'bg-gray-100 text-gray-800';
  }
}

export function getScoreColorClass(score) {
  if (score >= 70) return 'bg-success';
  if (score >= 40) return 'bg-warning';
  return 'bg-rust';
}

export function getRatioColorClass(ratio) {
  if (ratio >= 0.7) return 'bg-success';
  if (ratio >= 0.4) return 'bg-warning';
  return 'bg-rust';
}

export function formatStageLabel(stage) {
  return stage.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
}

export const REVENUE_PRESETS = [
  { key: 'today', label: 'Today' },
  { key: 'this_week', label: 'This Week' },
  { key: 'this_month', label: 'This Month' },
  { key: 'last_30_days', label: 'Last 30 Days' },
  { key: 'last_90_days', label: 'Last 90 Days' },
  { key: 'all_time', label: 'All Time' },
];

export const LEAD_STAGE_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'booked_call', label: '📞 Booked Call' },
  { key: 'new', label: 'New' },
  { key: 'engaged', label: 'Engaged' },
  { key: 'warm', label: 'Warm' },
  { key: 'converted', label: 'Converted' },
  { key: 'lost', label: 'Lost' },
];

export const LEAD_STAGES = ['new', 'engaged', 'warm', 'converted', 'lost'];

export const FUNNEL_STAGES = [
  { key: 'new', label: 'New', color: 'bg-blue-500' },
  { key: 'engaged', label: 'Engaged', color: 'bg-purple-500' },
  { key: 'warm', label: 'Warm', color: 'bg-warning' },
  { key: 'converted', label: 'Converted', color: 'bg-success' },
  { key: 'lost', label: 'Lost', color: 'bg-error' },
];
