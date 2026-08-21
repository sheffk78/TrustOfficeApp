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
  allow_fractional: false,
  allocation_mode: 'percentage',
  authorized_units_ceiling: 100,
  unlimited_units: false,
  class_distribution_convention: 'per_capita'
};

export const DEFAULT_CLASS_BENEFICIARY_FORM = {
  class_type: 'children',
  description: '',
  percentage: '',
  notes: '',
  distribution_convention: 'per_capita'
};

export const DEFAULT_PERSON_FORM = {
  name: '',
  relationship: '',
  sharePercentage: '',
  shareUnits: '',
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

// ========== EDUCATION & DISCLAIMER COPY ==========

export const ALLOCATION_MODE_HELP = {
  percentage: {
    title: 'Percentage Allocation Mode',
    description: 'In Percentage mode, you assign beneficiaries a share of the trust as a percentage. The TrustOffice calculates the equivalent raw units based on total authorized units.',
    example: 'Example: 25% of a 100-unit trust = 25 units',
    note: 'One percentage point does NOT necessarily equal one unit — it depends on the total authorized units.',
  },
  units: {
    title: 'Unit Allocation Mode',
    description: 'In Unit mode, you assign beneficiaries a specific number of raw units directly. The percentage is calculated from the total authorized units.',
    example: 'Example: 25 units in a 100-unit trust = 25%',
    note: 'Units are the canonical measure. Percentage is always derived (units ÷ total authorized × 100).',
  },
};

export const DISCLAIMER_TEXT = {
  noLegalAdvice: 'This interface shows allocation choices for planning purposes only. Unit and percentage values do not constitute legal advice. Consult qualified legal counsel before making trust distribution decisions.',
  unitsVsPercent: 'Units and percentages are two views of the same allocation. Changing the total authorized units changes the percentage each beneficiary receives for a fixed unit amount. One unit does not equal one percent unless total authorized units equal 100.',
  classDisclaimer: 'Class beneficiary designations define a pool and distribution convention (per capita or per stirpes). Actual distribution among class members is determined when members are confirmed. Recording members divides the reserved pool proportionally.',
};

export const EDUCATION_SECTIONS = {
  whatAreUnits: {
    title: 'What are Trust Units?',
    content: 'Units represent divisible portions of your trust\'s distributable value. You decide how many total units exist and who receives them. Think of units like slices of a pie — the pie size (total units) and slice count (per beneficiary) are your choices.',
  },
  allocationModes: {
    title: 'Allocation Modes',
    content: 'TrustOffice supports two allocation approaches:\n\n• Percentage mode — assign by percentage, units calculated automatically\n• Unit mode — assign by raw unit count, percentage calculated automatically\n\nThe canonical measurement is always units. Percentage is a convenient reference view.',
  },
  classBeneficiaries: {
    title: 'Class Beneficiaries',
    content: 'A class beneficiary is a group defined by relationship (e.g., "all children") rather than named individuals. You set a pool allocation and distribution convention:\n\n• Per Capita: equal shares per confirmed member\n• Per Stirpes: shares divided by family branch\n\nMembers are recorded separately and each reduces the available pool.',
  },
  beneficiaryTypes: {
    title: 'Beneficiary Types',
    content: 'TrustOffice supports three beneficiary types:\n\n• Individual — A named person (spouse, child, friend) who receives a direct allocation of units or percentage.\n• Organization — A legal entity (charity, LLC, corporation) that holds a direct allocation. Treated identically to an individual for allocation purposes.\n• Class — A group defined by relationship rather than name (e.g., "all descendants"). The class receives a reserved pool, distributed among confirmed members per capita or per stirpes.\n\nAll three types contribute to the total allocation. The combined percentage of individuals, organizations, and class pools should not exceed 100%.',
  },
  unitsVsPercentage: {
    title: 'Units vs. Percentage',
    content: 'Units and percentages are two views of the same allocation. The canonical value is always raw units. Percentage is derived: (units ÷ total authorized) × 100.\n\nChanging the total authorized units changes the percentage each beneficiary receives for a fixed unit amount. One unit does not equal one percent unless total authorized units equal 100.\n\nExample: 50 units in a 100-unit trust = 50%. But 50 units in a 200-unit trust = 25%.',
  },
  distributionConventions: {
    title: 'Distribution Conventions',
    content: 'When a class beneficiary pool is distributed among confirmed members, you choose the convention:\n\n• Per Capita — Equal shares per person. If a class has 4 confirmed members, each receives 25% of the pool.\n• Per Stirpes — Shares divided by family branch. If a beneficiary in the class is deceased, their share passes to their descendants rather than being redistributed.\n\nThe convention is set when creating a class beneficiary and can be changed in the Class Beneficiaries tab.',
  },
};