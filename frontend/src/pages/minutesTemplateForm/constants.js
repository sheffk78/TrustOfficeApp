/**
 * Config arrays and constants extracted from MinutesTemplateFormPage.
 * Kept in one place so the main page component and form-section sub-components
 * can import them without circular dependencies.
 */

/** Format a number as currency for display (e.g., 500000 → "$500,000") */
export const formatCurrency = (value) => {
  if (!value && value !== 0) return '';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return value;
  return '$' + num.toLocaleString('en-US');
};

/** Parse a formatted currency string back to a number string (e.g., "$500,000" → "500000") */
export const parseCurrencyInput = (value) => {
  return value.replace(/[$,\s]/g, '');
};

export const TEMPLATE_TITLES = {
  'initial_trustee_meeting': 'Initial Trustee Resolution',
  'general_meeting': 'General Meeting Resolution',
  'distribution_to_beneficiaries': 'Resolution to Distribute to Beneficiaries',
  'acceptance_of_property': 'Resolution to Accept Property into Trust',
  'disposition_of_asset': 'Resolution to Dispose / Sell Asset',
  'appointment_additional_trustee': 'Resolution to Appoint Additional Trustee',
  'appointment_successor_trustee': 'Resolution to Appoint Successor Trustee',
  'designation_of_beneficiaries': 'Resolution to Designate Beneficiaries',
  'bank_account_authorization': 'Resolution to Open Bank Account',
  'change_of_situs': 'Resolution to Change Trust Situs',
  'benevolence_approval': 'Resolution to Approve Benevolence Assistance',
  // Batch 1 templates
  'investment_policy': 'Resolution to Approve Investment Policy',
  'loan_authorization': 'Resolution to Authorize Loan',
  'insurance_authorization': 'Resolution to Authorize Insurance',
  'annual_review': 'Annual Review Resolution',
  'quarterly_review': 'Quarterly Review Resolution',
  'trustee_compensation': 'Resolution to Approve Trustee Compensation',
  'trustee_resignation': 'Resolution for Trustee Resignation/Removal',
  'beneficiary_request_denial': 'Resolution to Deny Beneficiary Request',
  'hems_distribution': 'Resolution for HEMS Distribution',
  'beneficiary_distribution_notice': 'Resolution for Beneficiary Distribution Notice',
  'beneficiary_loan': 'Resolution to Authorize Loan to Beneficiary',
  'evaluate_distribution': 'Resolution to Evaluate Distribution Request',
  // Batch 2 templates
  'trust_amendment': 'Resolution to Amend Trust',
  'power_of_attorney': 'Resolution to Authorize Power of Attorney',
  'trust_termination': 'Resolution to Terminate/Dissolve Trust',
  'real_estate_purchase': 'Resolution to Purchase Real Estate',
  'business_interest_acquisition': 'Resolution to Acquire Business Interest',
  'real_estate_lease': 'Resolution to Lease Real Estate',
  'fiscal_year_election': 'Resolution for Fiscal Year Election',
  'tax_filing_authorization': 'Resolution to Authorize Tax Filing',
  'emergency_ratification': 'Resolution to Ratify Emergency Action',
  'conflict_of_interest': 'Resolution to Disclose Conflict of Interest',
  'bill_of_sale': 'Resolution & Bill of Sale',
  'assignment_of_personal_property': 'Resolution to Assign Personal Property',
  'general_assignment': 'Resolution for General Assignment',
};

export const ASSET_CATEGORIES = [
  { value: 'real_property', label: 'Real Property' },
  { value: 'personal_property', label: 'Personal Property' },
  { value: 'financial_accounts', label: 'Financial Accounts' },
  { value: 'business_interests', label: 'Business Interests' },
  { value: 'digital_assets', label: 'Digital Assets' },
  { value: 'intellectual_property', label: 'Intellectual Property' },
  { value: 'notes_receivable', label: 'Notes Receivable' },
  { value: 'other_property', label: 'Other Property' },
];

/** Resolutions included in the initial trustee meeting template. */
export const INITIAL_MEETING_RESOLUTIONS = [
  { key: 'accept_trusteeship', label: 'Adoption of Trust & Accept Trusteeship', desc: 'Acknowledge the Declaration of Trust and accept your role as Trustee' },
  { key: 'acknowledge_fiduciary_duties', label: 'Fiduciary Duties Acknowledgment', desc: 'Formally acknowledge duties of Loyalty, Prudence, Impartiality, Obedience, Recordkeeping, and Confidentiality' },
  { key: 'authorize_ein', label: 'EIN Confirmation / Authorization', desc: 'Confirm your EIN or authorize obtaining one' },
  { key: 'accept_initial_property', label: 'Accept Initial Trust Property', desc: 'Acknowledge authority to accept the initial corpus from the Settlor' },
  { key: 'authorize_insurance', label: 'Insurance Authorization', desc: 'Authorize trustee liability and property insurance' },
  { key: 'authorize_professional_services', label: 'Professional Services Authorization', desc: 'Authorize retaining attorneys, accountants, and tax advisors' },
  { key: 'designate_record_keeper', label: 'Designate Record Keeper', desc: 'Assign responsibility for maintaining trust records' },
  { key: 'adopt_governance_standards', label: 'Governance Standards', desc: 'Adopt regular meetings, minutes requirements, resolution standards, annual review' },
  { key: 'ratify_prior_actions', label: 'Ratification of Prior Actions', desc: 'Ratify all actions taken during trust formation' },
];

/** Shared input className for currency inputs — keeps the JSX sections DRY. */
export const currencyInputClass = 'mt-1 input-trust';