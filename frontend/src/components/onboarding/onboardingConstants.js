import {
  ArrowRight, ArrowLeft, CheckCircle2,
  Upload, Sparkles, Lock, CreditCard, Clock, Loader2, FileCheck,
  X, FileSearch,
} from 'lucide-react';

export const API_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

/** Step names for the progress indicator. */
export const STEP_NAMES = ['Upload Document', 'Analyzing', 'Review Details', 'Welcome'];
export const TOTAL_STEPS = 4;

/** Progress hints cycled during the AI analysis screen. */
export const PROGRESS_HINTS = [
  'Reading document...',
  'Extracting trustee names...',
  'Identifying trust type...',
  'Finding distribution rules...',
];

/** Initial trustData form state. */
export const INITIAL_TRUST_DATA = {
  name: '',
  trust_type: 'revocable_living',
  jurisdiction: '',
  role: 'Trustee',
  review_cadence: 'quarterly',
  description: '',
  ein: '',
  state_code: '',
  start_date: '',
  tax_year_end_month: '12',
  tax_year_end_day: '31',
  is_fiscal_year: false,
  successor_trustee_name: '',
  secondary_successor_trustee_name: '',
};

/** Allowed MIME types and file extensions for trust document upload. */
export const ALLOWED_DOC_TYPES = [
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'image/png',
  'image/jpeg',
  'image/jpg',
];

export const ALLOWED_DOC_EXTENSIONS = /\.(pdf|doc|docx|txt|png|jpg|jpeg)$/i;

/** Max upload size (16 MB). */
// Uploads up to 100MB accepted — server deep-compresses PDFs before storing (16MB vault cap).
export const MAX_DOC_SIZE = 100 * 1024 * 1024;

// Re-export icons used by step components
export {
  ArrowRight, ArrowLeft, CheckCircle2,
  Upload, Sparkles, Lock, CreditCard, Clock, Loader2, FileCheck,
  X, FileSearch,
};
