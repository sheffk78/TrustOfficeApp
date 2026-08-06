import {
  FileText,
  ArrowUpDown,
  Clock,
  User,
  Users,
  Shield,
  DollarSign,
  Building2,
  AlertTriangle,
} from 'lucide-react';

export const EVENT_ICONS = {
  minutes_created: FileText,
  minutes_updated: FileText,
  distribution_created: DollarSign,
  distribution_updated: DollarSign,
  compensation_created: DollarSign,
  entity_created: Building2,
  entity_updated: Building2,
  relationship_created: ArrowUpDown,
  beneficiary_created: Users,
  schedule_a_created: DollarSign,
  communication_logged: FileText,
  alert_created: AlertTriangle,
  alert_resolved: Shield,
  transaction_created: DollarSign,
  transaction_updated: DollarSign,
  trust_updated: Shield,
  user_action: User,
};

export const EVENT_COLORS = {
  minutes_created: 'bg-navy/5 text-navy border-navy/20',
  minutes_updated: 'bg-navy/5 text-navy border-navy/20',
  distribution_created: 'bg-success/5 text-success border-success/20',
  distribution_updated: 'bg-success/5 text-success border-success/20',
  compensation_created: 'bg-success/5 text-success border-success/20',
  entity_created: 'bg-navy/5 text-navy border-navy/20',
  entity_updated: 'bg-navy/5 text-navy border-navy/20',
  relationship_created: 'bg-navy/5 text-navy border-navy/20',
  beneficiary_created: 'bg-success/5 text-success border-success/20',
  schedule_a_created: 'bg-warning/5 text-warning border-warning/20',
  communication_logged: 'bg-navy/5 text-navy border-navy/20',
  alert_created: 'bg-warning/5 text-warning border-warning/20',
  alert_resolved: 'bg-success/5 text-success border-success/20',
  transaction_created: 'bg-navy/5 text-navy border-navy/20',
  transaction_updated: 'bg-navy/5 text-navy border-navy/20',
  trust_updated: 'bg-navy/5 text-navy border-navy/20',
  user_action: 'bg-subtle-bg text-foreground border-border',
};

export const DEFAULT_COLOR = 'bg-subtle-bg text-foreground border-border';
export const DEFAULT_ICON = Clock;

export const FILTER_OPTIONS = [
  { value: 'all', label: 'All Events' },
  { value: 'minutes', label: 'Minutes' },
  { value: 'distribution', label: 'Distributions' },
  { value: 'compensation', label: 'Compensation' },
  { value: 'entity', label: 'Entities' },
  { value: 'relationship', label: 'Relationships' },
  { value: 'beneficiary', label: 'Beneficiaries' },
  { value: 'schedule_a', label: 'Schedule A' },
  { value: 'communication', label: 'Communications' },
  { value: 'alert', label: 'Alerts' },
  { value: 'transaction', label: 'Transactions' },
  { value: 'investment', label: 'Investments' },
  { value: 'vault', label: 'Vault' },
];

export const SECURITY_ACTIONS = [
  'login',
  'login_failed',
  'password_reset',
  'trust_updated',
  'vault_upload',
  'vault_download',
  'vault_delete',
];

export const AUDIT_ACTION_LABELS = {
  login: 'Login',
  login_failed: 'Failed Login',
  password_reset: 'Password Reset',
  trust_updated: 'Trust Profile Updated',
  vault_upload: 'Document Uploaded',
  vault_download: 'Document Downloaded',
  vault_delete: 'Document Deleted',
};

export const PAGE_SIZE = 25;