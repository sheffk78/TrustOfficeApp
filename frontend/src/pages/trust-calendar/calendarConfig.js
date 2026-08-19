import { format, parseISO } from 'date-fns';

// Task types for the create-task modal (minus tax_filing_1041 and tax_filing_k1,
// which are now handled by the tax calendar)
export const TASK_TYPES = [
  { value: 'annual_review', label: 'Annual Review' },
  { value: 'quarterly_review', label: 'Quarterly Review' },
  { value: 'compensation_review', label: 'Compensation Review' },
  { value: 'distribution_review', label: 'Distribution Review' },
  { value: 'insurance_compliance', label: 'Insurance Compliance' },
  { value: 'transaction_review', label: 'Transaction Review' },
  { value: 'custom', label: 'Custom Task' },
];

export const STATUS_TABS = [
  { key: 'upcoming', label: 'Upcoming' },
  { key: 'overdue', label: 'Overdue' },
  { key: 'completed', label: 'Completed' },
  { key: 'all', label: 'All' },
];

export const TYPE_FILTERS = [
  { key: 'all', label: 'All Types' },
  { key: 'governance_task', label: 'Trust Tasks' },
  { key: 'tax_deadline', label: 'Tax Filings' },
  { key: 'money', label: 'Money Events' },
  { key: 'structure', label: 'Structure Events' },
];

// Initial type-filter value derived from the ?type= query param.
export const initialTypeFilter = (searchParams) => {
  const qp = searchParams.get('type');
  if (qp === 'tax') return 'tax_deadline';
  if (qp === 'tasks') return 'governance_task';
  if (qp === 'money') return 'money';
  if (qp === 'structure') return 'structure';
  return 'all';
};

// Default new-task form state used by the create-task modal and reset on submit.
export const defaultNewTask = (addDays, format) => ({
  task_type: 'quarterly_review',
  due_date: format(addDays(new Date(), 30), 'yyyy-MM-dd'),
  description: '',
});

// Calculate the next annual review date from a trust's formation date.
// Returns 'yyyy-MM-dd' string or null if formationDateStr is invalid.
// The first annual review is 1 year after formation. If that date has
// already passed, advance to the next anniversary that's still upcoming.
export const annualReviewDate = (formationDateStr) => {
  if (!formationDateStr) return null;
  try {
    const formation = parseISO(formationDateStr);
    const now = new Date();
    // First annual review = formation date + 1 year
    let reviewDate = new Date(formation.getFullYear() + 1, formation.getMonth(), formation.getDate());
    // If that anniversary has already passed, keep advancing by 1 year
    // until we reach an upcoming date.
    while (reviewDate < now) {
      reviewDate = new Date(reviewDate.getFullYear() + 1, formation.getMonth(), formation.getDate());
    }
    return format(reviewDate, 'yyyy-MM-dd');
  } catch { return null; }
};