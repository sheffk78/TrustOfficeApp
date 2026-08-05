import { format, parseISO } from 'date-fns';

// Format an ISO date string as "MMM d, yyyy"; falls back to the raw string
// when parseISO throws (bad/missing dates).
export const formatDate = (dateString) => {
  try {
    return format(parseISO(dateString), 'MMM d, yyyy');
  } catch {
    return dateString;
  }
};

// Pretty-print an event's title: prefers title, then deadline_type for tax,
// then humanizes task_type / event_type by replacing underscores with spaces
// and title-casing.
export const eventTitle = (event) => {
  if (event.event_type === 'tax_deadline') {
    return event.title || event.deadline_type;
  }
  if (event.event_type === 'governance_task') {
    return event.title || humanizeKey(event.task_type);
  }
  return event.title || humanizeKey(event.event_type);
};

// "quarterly_review" → "Quarterly Review"
export const humanizeKey = (key) =>
  (key || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

// Resolve the initial type-filter value from a ?type= query param.
// (kept here as a pure helper; the component passes searchParams in)
export const typeFilterFromQuery = (qp) => {
  if (qp === 'tax') return 'tax_deadline';
  if (qp === 'tasks') return 'governance_task';
  if (qp === 'money') return 'money';
  if (qp === 'structure') return 'structure';
  return 'all';
};