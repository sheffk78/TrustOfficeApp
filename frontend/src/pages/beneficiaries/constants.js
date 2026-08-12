// Configuration arrays, options, and constants for BeneficiariesPage

export const CHART_COLORS = [
  '#010079', '#D5AD36', '#2563eb', '#16a34a', '#dc2626',
  '#9333ea', '#ea580c', '#0891b2', '#4f46e5', '#be185d',
];

export const CLASS_BENEFICIARY_OPTIONS = [
  { value: 'children', label: 'Children (including after-born)' },
  { value: 'descendants', label: 'Descendants' },
  { value: 'issue', label: 'Issue (lineal descendants)' },
  { value: 'heirs', label: 'Heirs' },
  { value: 'heirs_at_law', label: 'Heirs at Law' },
  { value: 'blood_relatives', label: 'Blood Relatives' },
  { value: 'per_stirpes', label: 'Per Stirpes (by branch)' },
  { value: 'per_capita', label: 'Per Capita (by head)' },
  { value: 'custom', label: 'Custom Class' },
];

export const RELATIONSHIP_OPTIONS = [
  { value: 'Spouse', label: 'Spouse' },
  { value: 'Child', label: 'Child' },
  { value: 'Daughter', label: 'Daughter' },
  { value: 'Son', label: 'Son' },
  { value: 'Parent', label: 'Parent' },
  { value: 'Sibling', label: 'Sibling' },
  { value: 'Grandchild', label: 'Grandchild' },
  { value: 'Other relative', label: 'Other relative' },
  { value: 'Friend', label: 'Friend' },
  { value: 'Charity', label: 'Charity / Organization' },
  { value: 'Other', label: 'Other' },
];

export const HOLDER_TYPE_OPTIONS = [
  { value: 'individual', label: 'Individual' },
  { value: 'trust', label: 'Trust' },
  { value: 'llc', label: 'LLC' },
  { value: 'corporation', label: 'Corporation' },
  { value: 'charity', label: 'Charity / Nonprofit' },
  { value: 'estate', label: 'Estate' },
  { value: 'other', label: 'Other Entity' },
];

export const STATUS_FILTER_OPTIONS = [
  { value: 'active', label: 'Active Only' },
  { value: 'all', label: 'All Certificates' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'replaced', label: 'Replaced' },
];

export const DEFAULT_CERTIFICATE_FORM = {
  holder_name: '',
  holder_identifier: '',
  holder_type: 'individual',
  holder_trust_id: '',
  email: '',
  phone: '',
  units: '',
  issue_date: '', // set at runtime via new Date()
  notes: ''
};

export const DEFAULT_TRANSFER_FORM = {
  from_certificate_id: '',
  to_certificate_id: '',
  to_holder_name: '',
  to_holder_identifier: '',
  units: '',
  reason: ''
};

export const DEFAULT_SETTINGS_FORM = {
  total_authorized_units: 100,
  unit_label: 'Unit',
  allow_fractional: false
};

export const DEFAULT_CLASS_BENEFICIARY_FORM = {
  class_type: 'children',
  description: '',
  percentage: '',
  notes: ''
};

export const DEFAULT_PERSON_FORM = {
  name: '',
  relationship: '',
  sharePercentage: '',
};

// Build a fresh certificate form with today's issue_date
export function makeCertificateForm() {
  const today = new Date();
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  return { ...DEFAULT_CERTIFICATE_FORM, issue_date: iso };
}

// Format an ISO date string for display; returns em-dash for null/undefined
export function formatDate(dateStr) {
  if (!dateStr) return '—';
  try {
    return format(parseISO(dateStr), 'MMM d, yyyy');
  } catch {
    return dateStr;
  }
}

import { format, parseISO } from 'date-fns';

// Coerce optional string fields to null when empty (for API payloads)
export function sanitizeOptional(val) {
  return val === null || val === undefined || val.trim() === '' ? null : val;
}

// Build a certificate form object from an existing certificate for editing
export function certificateFormFromEdit(editing) {
  const today = new Date();
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  return {
    holder_name: editing.holder_name,
    holder_identifier: editing.holder_identifier || '',
    holder_type: editing.holder_type || 'individual',
    holder_trust_id: editing.holder_trust_id || '',
    email: editing.email || '',
    phone: editing.phone || '',
    units: editing.units.toString(),
    issue_date: editing.issue_date?.split('T')[0] || iso,
    notes: editing.notes || ''
  };
}

// Named predicates (complex_conditional mitigation)

export const isTrustHolder = (form) => form.holder_type === 'trust';

export const hasMultipleTrustsAvailable = (trusts, selectedTrust) =>
  Boolean(trusts && trusts.length > 1 && selectedTrust);

export const canSelectTrustHolder = (trusts, selectedTrust) =>
  isTrustHolder({ holder_type: 'trust' }) && trusts && trusts.length > 0 && Boolean(selectedTrust);

export const isFullyAllocated = (summary) =>
  Boolean(summary && summary.remaining_units === 0);

export const hasActiveCertificates = (summary) =>
  Boolean(summary?.certificates?.filter(c => c.status === 'active').length);

export const isValidSharePercentage = (pct) =>
  Boolean(pct) && pct > 0 && pct <= 100;

export const exceedsRemainingUnits = (units, summary) =>
  Boolean(summary) && units > summary.remaining_units;

export const filterCertificatesByStatus = (certificates, statusFilter) =>
  (certificates || []).filter(cert =>
    statusFilter === 'all' ? true : cert.status === statusFilter
  );

// Build the gradient stops for the ownership pie chart
export function buildPieGradient(beneficiaries) {
  const gradientStops = [];
  let currentAngle = 0;
  beneficiaries.forEach((ben, index) => {
    const angle = (ben.percentage / 100) * 360;
    const color = CHART_COLORS[index % CHART_COLORS.length];
    gradientStops.push(`${color} ${currentAngle}deg ${currentAngle + angle}deg`);
    currentAngle += angle;
  });
  const totalIssued = beneficiaries.reduce((sum, b) => sum + b.percentage, 0);
  if (totalIssued < 100) {
    gradientStops.push(`#e5e7eb ${currentAngle}deg 360deg`);
  }
  return `conic-gradient(${gradientStops.join(', ')})`;
}

// Extract the relationship stored in certificate notes for a beneficiary
export function extractRelationship(ben) {
  const relationshipNote = ben.certificates?.find(c => c.notes?.startsWith('Relationship to grantor:'))?.notes;
  return relationshipNote ? relationshipNote.replace('Relationship to grantor: ', '') : null;
}

// Stable key for a beneficiary row
export function beneficiaryKey(ben) {
  return `${ben.holder_name}-${ben.holder_identifier || ''}-${ben.holder_type || 'individual'}`;
}

// Status badge className for a certificate
export function statusBadgeClass(status) {
  if (status === 'active') return 'bg-success/10 text-success dark:bg-success/20 dark:text-success';
  if (status === 'cancelled') return 'bg-error/10 text-error dark:bg-error/20 dark:text-error';
  return 'bg-muted text-muted-foreground';
}