import {
  FileText,
  Calendar,
  Wallet,
  DollarSign,
  Receipt,
  CheckCircle2,
  TrendingUp,
  Package,
  PlusCircle,
  Landmark,
  UserPlus,
  Building2,
} from 'lucide-react';

// Quick action config for the dashboard sidebar
export const QUICK_ACTIONS = [
  {
    title: 'Record Distribution',
    description: 'Document a distribution to beneficiaries',
    icon: DollarSign,
    path: '/minutes/template/distribution_to_beneficiaries',
    color: 'bg-success/10 text-success'
  },
  {
    title: 'Add Asset to Trust',
    description: 'Accept property and update Trust Assets',
    icon: PlusCircle,
    path: '/minutes/template/acceptance_of_property',
    color: 'bg-navy/10 text-navy'
  },
  {
    title: 'Open Bank Account',
    description: 'Authorize a new trust bank account',
    icon: Landmark,
    path: '/minutes/template/bank_account_authorization',
    color: 'bg-gold/10 text-gold'
  },
  {
    title: 'Appoint Trustee',
    description: 'Add or replace a trustee',
    icon: UserPlus,
    path: '/minutes/template/appointment_additional_trustee',
    color: 'bg-warning/10 text-warning'
  },
  {
    title: 'View Trust Assets',
    description: 'Manage trust assets and corpus',
    icon: Package,
    path: '/schedule-a',
    color: 'bg-navy/10 text-navy'
  },
  {
    title: 'General Meeting',
    description: 'Record a trustee meeting',
    icon: FileText,
    path: '/minutes/template/general_meeting',
    color: 'bg-gold/20 text-gold'
  },
  {
    title: 'View Structures',
    description: 'Manage trust entities and relationships',
    icon: Building2,
    path: '/structures',
    color: 'bg-navy/10 text-navy'
  }
];

// Map insight types to icons
export const INSIGHT_ICONS = {
  'Quarterly Minutes': FileText,
  'Task Compliance': Calendar,
  'Compensation Alignment': Wallet,
  'Distribution Documentation': DollarSign,
  'Annual Review': TrendingUp,
  'Asset Valuation Freshness': Package
};

// Activity icon mapping
export const ACTIVITY_ICONS = {
  minutes: <FileText className="w-4 h-4" />,
  distribution: <DollarSign className="w-4 h-4" />,
  expense: <Receipt className="w-4 h-4" />,
  compensation: <Wallet className="w-4 h-4" />,
  task: <CheckCircle2 className="w-4 h-4" />,
};

export function getActivityIcon(type) {
  return ACTIVITY_ICONS[type] || <FileText className="w-4 h-4" />;
}

export function getScoreColor(score) {
  if (score >= 96) return 'score-good';
  if (score >= 72) return 'score-warning';
  return 'score-critical';
}

export function getStatusBadgeClass(status) {
  switch (status) {
    case 'approved': return 'badge-success';
    case 'review': return 'badge-warning';
    case 'declined': return 'badge-error';
    default: return '';
  }
}

// Build onboarding steps config from onboarding state + selectedTrust.
// Field names must match backend OnboardingState model (backend/models.py L1045).
export function getOnboardingProgress(onboarding, selectedTrust) {
  if (!onboarding) return { nextStep: null, completed: 0, total: 9, allSteps: [] };

  const steps = [
    { id: 'trust_doc', label: 'Add your trust document', done: onboarding.trust_doc_uploaded, action: '/vault', priority: 1, field: 'trust_doc_uploaded' },
    { id: 'beneficiaries', label: 'Add beneficiaries', done: onboarding.beneficiaries_added, action: '/beneficiaries', priority: 2, field: 'beneficiaries_added' },
    // Trust protector is optional and can be explicitly deferred. The
    // canonical setup step is complete once successor-trustee setup is done.
    { id: 'trustee_roles', label: 'Update trustee roles', done: onboarding.successor_trustee_added, action: '/trust-roles', priority: 3, field: 'trustee_roles' },
    { id: 'assets', label: 'Add your trust assets', done: onboarding.assets_added, action: '/schedule-a', priority: 4, field: 'assets_added' },
    { id: 'minutes', label: 'Hold your first trustee meeting', done: onboarding.minutes_generated, action: '/minutes/create?type=initial_trustee_meeting', priority: 5, field: 'minutes_generated' },
    { id: 'ein_doc', label: 'Add EIN letter to vault', done: onboarding.ein_doc_uploaded, action: '/vault', priority: 6, field: 'ein_doc_uploaded' },
    { id: 'formation_date', label: 'Add formation date', done: onboarding.formation_date_added, action: '/settings#formation-date', priority: 7, field: 'formation_date_added' },
    { id: 'ein', label: 'Enter your EIN', done: onboarding.ein_entered, action: '/settings#ein', priority: 8, field: 'ein_entered' },
    { id: 'calendar', label: 'Review your tax calendar', done: onboarding.calendar_set || selectedTrust?.benevolence_enabled, action: '/calendar', priority: 9, field: 'calendar_set' },
  ];

  const completed = steps.filter(s => s.done).length;
  const nextStep = steps.find(s => !s.done);
  return { nextStep, completed, total: steps.length, allSteps: steps };
}

// Compute the single highest-priority "do this next" action.
// Priority 1: Overdue tax deadline > Priority 2: first incomplete onboarding step
// > Priority 3: highest-point governance insight
export function computeNextAction(taxDeadlines, onboardingProgress, insights) {
  // Priority 1: Overdue tax deadline
  // NOTE: backend field is `days_remaining` (not `days_until`). TO-003a fix.
  const overdueDeadline = taxDeadlines?.find(
    d => (typeof d.days_remaining === 'number' && d.days_remaining < 0) || (d.is_overdue && d.filing_status === 'pending')
  );
  if (overdueDeadline) return {
    title: `${overdueDeadline.description || 'Tax deadline'} is overdue`,
    action: '/calendar',
    cta: 'Review deadline',
    context: `${Math.abs(overdueDeadline.days_remaining ?? 0)} days overdue`,
    variant: 'urgent'
  };

  // Priority 2: First incomplete onboarding step
  if (onboardingProgress.nextStep) return {
    title: onboardingProgress.nextStep.label,
    action: onboardingProgress.nextStep.action,
    cta: 'Start now',
    context: `${onboardingProgress.completed}/${onboardingProgress.total} setup steps done`,
    variant: 'onboarding'
  };

  // Priority 3: Highest-point governance insight
  const topInsight = [...insights].sort((a, b) => (b.points || 0) - (a.points || 0))[0];
  if (topInsight) return {
    title: topInsight.title || topInsight.description,
    action: topInsight.action_path || '/governance',
    cta: 'Fix this',
    context: `+${topInsight.points || 0} health points`,
    variant: 'insight'
  };

  return null; // All caught up
}

// Variant styling for the "Do This Next" hero card
export function getNextActionVariantClass(variant) {
  switch (variant) {
    case 'urgent':
      return 'bg-gradient-to-r from-error/10 to-error/5 border-l-4 border-l-error';
    case 'onboarding':
      return 'bg-gradient-to-r from-gold/10 to-navy/5 border-l-4 border-l-gold';
    default:
      return 'bg-gradient-to-r from-navy/10 to-navy/5 border-l-4 border-l-navy';
  }
}

// Severity color mapping for weekly briefing items
export const WEEKLY_BRIEFING_SEVERITY_COLORS = {
  high: 'border-error/30 bg-error/5 text-error',
  medium: 'border-warning/30 bg-warning/5 text-warning',
  low: 'border-navy/20 bg-navy/5 text-navy/70',
};

export function getSeverityClass(severity) {
  return WEEKLY_BRIEFING_SEVERITY_COLORS[severity] || WEEKLY_BRIEFING_SEVERITY_COLORS.low;
}