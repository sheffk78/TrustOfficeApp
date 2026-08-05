import { Shield, FileText, FolderOpen, FileCheck, AlertTriangle } from 'lucide-react';

/** Maps vault category keys to their Lucide icon component. */
export const CATEGORY_ICONS = {
  trust_instrument: Shield,
  amendment: FileText,
  schedule_a: FolderOpen,
  minutes: FileText,
  tax_return: FileText,
  k1: FileText,
  ein_letter: FileCheck,
  financial_statement: FileText,
  appraisal: FileText,
  notice: AlertTriangle,
  insurance: Shield,
  deed: FileText,
  bank_statement: FileText,
  legal_opinion: Shield,
  court_order: FileText,
  other: FileText,
};

/** Human-readable labels for each vault document category. */
export const DOC_CATEGORIES = {
  trust_instrument: "Trust Instrument / Governing Document",
  amendment: "Trust Amendment / Restatement",
  schedule_a: "Trust Assets",
  minutes: "Minutes of Meetings",
  tax_return: "Tax Return (Form 1041)",
  k1: "Schedule K-1",
  ein_letter: "EIN Confirmation Letter (CP575)",
  financial_statement: "Financial Statement / Accounting",
  appraisal: "Asset Appraisal / Valuation",
  notice: "Beneficiary Notice / Communication",
  insurance: "Insurance Policy / Rider",
  deed: "Deed / Property Document",
  bank_statement: "Bank / Investment Statement",
  legal_opinion: "Legal Opinion / Attorney Letter",
  court_order: "Court Order / Judgment",
  other: "Other",
};

/** Accepted file type extensions for vault uploads. */
export const ACCEPTED_TYPES = '.pdf,.jpg,.jpeg,.png,.gif,.webp,.tiff,.tif,.doc,.docx,.xls,.xlsx,.txt';

/** Initial empty form state for the Add Document form. */
export const INITIAL_FORM = {
  title: '',
  category: 'trust_instrument',
  date: '',
  description: '',
  storage_provider: 'google_drive',
  storage_url: '',
  storage_path: '',
  file_name: '',
  tags: '',
  expiration_date: '',
  needs_renewal: false,
};

/** Storage provider select options. */
export const STORAGE_PROVIDERS = [
  { value: 'google_drive', label: 'Google Drive' },
  { value: 'dropbox', label: 'Dropbox' },
  { value: 'onedrive', label: 'OneDrive' },
  { value: 'local_server', label: 'Local Server' },
  { value: 'cloud_url', label: 'Cloud URL' },
  { value: 'physical', label: 'Physical / Paper' },
];
