import {
  ArrowUpRight,
  ArrowDownLeft,
} from 'lucide-react';

export const CLASSIFICATIONS = [
  'Distribution', 'Compensation', 'Inter-Entity Transfer',
  'Operational Expense', 'Capital Contribution', 'Tax Payment', 'Other'
];

export const DIRECTION_OPTIONS = [
  { value: 'inflow', label: 'Inflow', icon: ArrowDownLeft, color: 'text-success' },
  { value: 'outflow', label: 'Outflow', icon: ArrowUpRight, color: 'text-error' },
];

export const classificationColors = {
  'Distribution': 'bg-gold/10 text-gold dark:bg-gold/20 dark:text-gold',
  'Compensation': 'bg-navy/10 text-navy dark:bg-navy/20 dark:text-navy',
  'Inter-Entity Transfer': 'bg-warning/10 text-warning dark:bg-warning/20 dark:text-warning',
  'Operational Expense': 'bg-muted text-muted-foreground dark:bg-muted/30 dark:text-muted-foreground',
  'Capital Contribution': 'bg-success/10 text-success dark:bg-success/20 dark:text-success',
  'Tax Payment': 'bg-error/10 text-error dark:bg-error/20 dark:text-error',
  'Other': 'bg-navy/5 text-navy/70 dark:bg-navy/20 dark:text-navy/70',
};

export const EMPTY_FORM = {
  entity_id: '', date: '', amount: '', direction: 'outflow',
  source_account: '', destination_account: '',
  governance_classification: '', purpose_memo: '', other_note: ''
};

// Predicates for the "Other" classification requiring a note
export const isOtherClassification = (classification) => classification === 'Other';
export const isOtherWithoutNote = (classification, note) =>
  isOtherClassification(classification) && !note.trim();