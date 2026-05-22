import { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { 
  ArrowLeft,
  Plus,
  Trash2,
  FileText,
  Download,
  Save,
  Eye
} from 'lucide-react';
import { format } from 'date-fns';

const TEMPLATE_TITLES = {
  'initial_trustee_meeting': 'Initial Trustee Meeting',
  'general_meeting': 'General Meeting Minutes',
  'distribution_to_beneficiaries': 'Distribution to Beneficiaries',
  'acceptance_of_property': 'Accept Property into Trust',
  'disposition_of_asset': 'Dispose / Sell Asset',
  'appointment_additional_trustee': 'Appoint Additional Trustee',
  'appointment_successor_trustee': 'Appoint Successor Trustee',
  'designation_of_beneficiaries': 'Designate Beneficiaries',
  'bank_account_authorization': 'Open Bank Account',
  'change_of_situs': 'Change Trust Situs',
  'benevolence_approval': 'Benevolence Assistance Approval',
  // Batch 1 templates
  'investment_policy': 'Investment Policy Approval',
  'loan_authorization': 'Loan Authorization',
  'insurance_authorization': 'Insurance Authorization',
  'annual_review': 'Annual Review Meeting',
  'quarterly_review': 'Quarterly Review Meeting',
  'trustee_compensation': 'Trustee Compensation Approval',
  'trustee_resignation': 'Trustee Resignation/Removal',
  'beneficiary_request_denial': 'Beneficiary Request Denial',
  'hems_distribution': 'HEMS Distribution',
  'beneficiary_loan': 'Loan to Beneficiary',
  // Batch 2 templates
  'trust_amendment': 'Trust Amendment',
  'power_of_attorney': 'Power of Attorney Authorization',
  'trust_termination': 'Trust Termination/Dissolution',
  'real_estate_purchase': 'Real Estate Purchase Authorization',
  'business_interest_acquisition': 'Business Interest Acquisition',
  'real_estate_lease': 'Real Estate Lease Authorization',
  'fiscal_year_election': 'Fiscal Year Election',
  'tax_filing_authorization': 'Tax Filing Authorization',
  'emergency_ratification': 'Emergency Action Ratification',
  'conflict_of_interest': 'Conflict of Interest Disclosure'
};

const ASSET_CATEGORIES = [
  { value: 'real_property', label: 'Real Property' },
  { value: 'personal_property', label: 'Personal Property' },
  { value: 'financial_accounts', label: 'Financial Accounts' },
  { value: 'business_interests', label: 'Business Interests' },
  { value: 'digital_assets', label: 'Digital Assets' },
  { value: 'intellectual_property', label: 'Intellectual Property' },
  { value: 'notes_receivable', label: 'Notes Receivable' },
  { value: 'other_property', label: 'Other Property' }
];

export default function MinutesTemplateFormPage() {
  const navigate = useNavigate();
  const { templateType } = useParams();
  const [searchParams] = useSearchParams();
  const { selectedTrust } = useAuth();
  
  const [loading, setLoading] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [generatedDoc, setGeneratedDoc] = useState('');
  const [minutesId, setMinutesId] = useState(null);
  
  // Common fields
  const [formData, setFormData] = useState({
    minute_number: `${new Date().getFullYear()}-001`,
    meeting_date: format(new Date(), 'MMMM d, yyyy'),
    meeting_time: '10:00 AM',
    meeting_type: 'unanimous_written_consent',
    meeting_location: '',
    trustees_present: [],
    trust_formation_date: '',
    adjournment_time: '10:30 AM'
  });

  // Distribution fields
  const [distributionData, setDistributionData] = useState({
    distribution_total: '',
    distribution_items: [{ beneficiary_name: '', amount: '', percentage: '' }],
    distribution_date: format(new Date(), 'MMMM d, yyyy'),
    distribution_characterization: 'income'
  });

  // Property acceptance fields
  const [propertyData, setPropertyData] = useState({
    grantor_name: '',
    property_description: '',
    property_value: '',
    property_identifier: '',  // VIN, account number, legal description
    property_location: '',    // Address, institution, platform
    conveyance_date: format(new Date(), 'MMMM d, yyyy'),
    add_to_schedule_a: true,
    schedule_a_category: 'real_property'
  });

  // Asset disposition fields
  const [dispositionData, setDispositionData] = useState({
    disposition_asset_id: '',
    disposition_asset_description: '',
    disposition_reason: 'sale',
    disposition_date: format(new Date(), 'MMMM d, yyyy'),
    disposition_value: '',
    disposition_recipient: '',
    disposition_notes: '',
    update_schedule_a: true
  });

  // Schedule A assets for disposition selection
  const [scheduleAAssets, setScheduleAAssets] = useState([]);
  const [loadingAssets, setLoadingAssets] = useState(false);

  // Trustee appointment fields
  const [trusteeData, setTrusteeData] = useState({
    new_trustee_name: '',
    new_trustee_gender: 'man',
    departing_trustee_name: '',
    departing_reason: 'resigned',
    signature_requirement: 'any_one',
    signature_threshold: '',
    banking_powers_granted: true,
    effective_date: format(new Date(), 'MMMM d, yyyy')
  });

  // Beneficiary designation fields
  const [beneficiaryData, setBeneficiaryData] = useState({
    designation_type: 'initial',
    total_units: 100,
    beneficiaries: [{ name: '', units: '', percentage: '', relationship: '' }]
  });

  // Bank account fields
  const [bankData, setBankData] = useState({
    bank_name: '',
    account_type: 'checking',
    purpose: 'general trust administration',
    authorized_signers: [],
    signature_requirement: 'any_one',
    signature_threshold: '',
    initial_deposit: ''
  });

  // Change of situs fields
  const [situsData, setSitusData] = useState({
    current_situs: '',
    new_situs: '',
    effective_date: format(new Date(), 'MMMM d, yyyy'),
    reasons: ['']
  });

  // Benevolence approval fields
  const [benevolenceData, setBenevolenceData] = useState({
    beneficiary_name: '',
    beneficiary_type: 'individual',
    benevolence_purpose: 'assistance',
    purpose_description: '',
    amount: '',
    disbursement_date: format(new Date(), 'MMMM d, yyyy'),
    add_to_benevolence_log: true
  });

  // Investment policy fields
  const [investmentPolicyData, setInvestmentPolicyData] = useState({
    policy_type: 'adopt',
    risk_tolerance: 'moderate',
    asset_allocation: [
      { asset_class: 'Fixed Income', percentage: 50 },
      { asset_class: 'Equities', percentage: 40 },
      { asset_class: 'Cash', percentage: 10 }
    ],
    investment_restrictions: ['No speculative trading', 'No margin accounts'],
    review_frequency: 'annually'
  });

  // Loan authorization fields
  const [loanAuthData, setLoanAuthData] = useState({
    loan_direction: 'making',
    borrower_name: '',
    lender_name: '',
    loan_amount: '',
    interest_rate: 'AFR (Applicable Federal Rate)',
    term_months: '60',
    loan_purpose: '',
    collateral_description: ''
  });

  // Insurance authorization fields
  const [insuranceData, setInsuranceData] = useState({
    insurance_type: 'property',
    policy_action: 'obtain',
    insurer_name: '',
    coverage_amount: '',
    premium_amount: '',
    coverage_description: '',
    policy_number: ''
  });

  // Annual review fields
  const [annualReviewData, setAnnualReviewData] = useState({
    fiscal_year: String(new Date().getFullYear() - 1),
    total_assets: '',
    total_income: '',
    total_expenses: '',
    total_distributions: '',
    investment_return: '',
    key_accomplishments: [''],
    upcoming_priorities: [''],
    governance_items: ['']
  });

  // Quarterly review fields
  const [quarterlyReviewData, setQuarterlyReviewData] = useState({
    quarter: 'Q1',
    year: String(new Date().getFullYear()),
    beginning_balance: '',
    ending_balance: '',
    income_received: '',
    expenses_paid: '',
    distributions_made: '',
    discussion_items: [''],
    action_items: ['']
  });

  // Trustee compensation fields
  const [trusteeCompData, setTrusteeCompData] = useState({
    trustee_name: '',
    compensation_type: 'annual',
    compensation_amount: '',
    effective_date: format(new Date(), 'MMMM d, yyyy'),
    compensation_basis: '',
    duties_description: '',
    all_trustees: false
  });

  // Trustee resignation fields
  const [trusteeResignData, setTrusteeResignData] = useState({
    departing_trustee_name: '',
    departure_type: 'resignation',
    departure_reason: '',
    effective_date: format(new Date(), 'MMMM d, yyyy'),
    remaining_trustees: [''],
    successor_appointed: false,
    successor_name: ''
  });

  // Beneficiary denial fields
  const [denialData, setDenialData] = useState({
    beneficiary_name: '',
    request_type: 'distribution',
    request_amount: '',
    request_purpose: '',
    request_date: format(new Date(), 'MMMM d, yyyy'),
    denial_reasons: [''],
    alternative_offered: ''
  });

  // HEMS distribution fields
  const [hemsData, setHemsData] = useState({
    beneficiary_name: '',
    hems_category: 'support',
    distribution_amount: '',
    specific_purpose: '',
    supporting_documentation: [''],
    recurring: false,
    recurring_frequency: 'monthly'
  });

  // Beneficiary loan fields
  const [beneficiaryLoanData, setBeneficiaryLoanData] = useState({
    beneficiary_name: '',
    loan_amount: '',
    interest_rate: 'AFR (Applicable Federal Rate)',
    term_months: '60',
    loan_purpose: '',
    collateral_description: '',
    repayment_terms: 'monthly installments'
  });

  // ========== BATCH 2 TEMPLATE STATES ==========

  // Trust amendment fields
  const [amendmentData, setAmendmentData] = useState({
    amendment_type: 'modification',
    article_section: '',
    current_provision: '',
    amended_provision: '',
    effective_date: 'immediately upon execution',
    reason: ''
  });

  // Power of attorney fields
  const [poaData, setPoaData] = useState({
    agent_name: '',
    scope: 'limited',
    powers_granted: [''],
    expiration: 'upon completion of specified purpose',
    purpose: ''
  });

  // Trust termination fields
  const [terminationData, setTerminationData] = useState({
    termination_reason: '',
    termination_date: format(new Date(), 'MMMM d, yyyy'),
    distribution_plan: '',
    final_accounting_date: 'within 60 days',
    outstanding_obligations: 'None known at this time'
  });

  // Real estate purchase fields
  const [realEstatePurchaseData, setRealEstatePurchaseData] = useState({
    property_address: '',
    property_type: 'residential',
    purchase_price: '',
    financing: 'all cash',
    purpose: 'investment and income production',
    inspection_period: 'standard due diligence period'
  });

  // Business interest acquisition fields
  const [businessInterestData, setBusinessInterestData] = useState({
    entity_name: '',
    entity_type: 'LLC',
    ownership_percentage: '',
    purchase_price: '',
    purpose: 'investment diversification',
    due_diligence: 'financial review completed'
  });

  // Real estate lease fields
  const [realEstateLeaseData, setRealEstateLeaseData] = useState({
    property_address: '',
    tenant_name: '',
    lease_term: '',
    monthly_rent: '',
    security_deposit: 'equivalent to one month\'s rent',
    permitted_use: 'residential occupancy'
  });

  // Fiscal year election fields
  const [fiscalYearData, setFiscalYearData] = useState({
    fiscal_year_end: 'December 31',
    election_type: 'initial',
    effective_year: String(new Date().getFullYear()),
    reason: 'administrative convenience and alignment with beneficiary tax years'
  });

  // Tax filing authorization fields
  const [taxFilingData, setTaxFilingData] = useState({
    tax_year: String(new Date().getFullYear() - 1),
    preparer_name: '',
    returns_to_file: ['Form 1041 - U.S. Income Tax Return for Estates and Trusts'],
    filing_deadline: 'April 15',
    extension_authorized: true
  });

  // Emergency ratification fields
  const [emergencyData, setEmergencyData] = useState({
    action_date: format(new Date(), 'MMMM d, yyyy'),
    emergency_type: '',
    actions_taken: [''],
    trustee_acting: '',
    cost_incurred: '',
    outcome: ''
  });

  // Conflict of interest fields
  const [conflictData, setConflictData] = useState({
    trustee_name: '',
    conflict_type: 'financial_interest',
    description: '',
    related_transaction: '',
    disclosure_date: format(new Date(), 'MMMM d, yyyy'),
    waiver_granted: true,
    conditions: 'None'
  });

  // General meeting resolutions
  const [resolutions, setResolutions] = useState([{
    title: '',
    whereas_clauses: [''],
    resolved_clauses: [''],
    vote: 'Unanimous approval',
    effective_date: 'Immediately upon adoption'
  }]);

  // Trust entity data for auto-population
  const [trustEntity, setTrustEntity] = useState(null);

  useEffect(() => {
    if (selectedTrust) {
      loadTrustEntityData();
    }
  }, [selectedTrust]);

  // Load Schedule A assets when disposition template is selected
  useEffect(() => {
    if (selectedTrust && templateType === 'disposition_of_asset') {
      loadScheduleAAssets();
      
      // Pre-fill disposition data from URL parameters (coming from Schedule A page)
      const assetId = searchParams.get('asset_id');
      const assetDescription = searchParams.get('asset_description');
      const dispositionDate = searchParams.get('disposition_date');
      const dispositionReason = searchParams.get('disposition_reason');
      const dispositionValue = searchParams.get('disposition_value');
      const dispositionRecipient = searchParams.get('disposition_recipient');
      const dispositionNotes = searchParams.get('disposition_notes');
      
      if (assetId || assetDescription) {
        setDispositionData(prev => ({
          ...prev,
          disposition_asset_id: assetId || '',
          disposition_asset_description: assetDescription || '',
          disposition_date: dispositionDate ? format(new Date(dispositionDate), 'MMMM d, yyyy') : prev.disposition_date,
          disposition_reason: dispositionReason || prev.disposition_reason,
          disposition_value: dispositionValue || '',
          disposition_recipient: dispositionRecipient || '',
          disposition_notes: dispositionNotes || '',
          update_schedule_a: true
        }));
      }
    }
  }, [selectedTrust, templateType, searchParams]);

  const loadScheduleAAssets = async () => {
    if (!selectedTrust) return;
    setLoadingAssets(true);
    try {
      // Only load active assets
      const response = await fetchWithAuth(`/schedule-a?trust_id=${selectedTrust.trust_id}&status=active`);
      if (response.ok) {
        const assets = await response.json();
        setScheduleAAssets(assets);
      }
    } catch (error) {
      console.error('Failed to load Schedule A assets:', error);
    } finally {
      setLoadingAssets(false);
    }
  };

  const loadTrustEntityData = async () => {
    try {
      const response = await fetchWithAuth(`/entities?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        const entities = await response.json();
        // Find the main trust entity (entity_type === 'Trust')
        const mainTrust = entities.find(e => e.entity_type === 'Trust');
        if (mainTrust) {
          setTrustEntity(mainTrust);
          
          // Auto-populate trust_formation_date from entity formation date or trust start_date
          if (mainTrust.formation_date) {
            const formattedDate = format(new Date(mainTrust.formation_date), 'MMMM d, yyyy');
            setFormData(prev => ({
              ...prev,
              trust_formation_date: formattedDate
            }));
          } else if (selectedTrust?.start_date) {
            const formattedDate = format(new Date(selectedTrust.start_date), 'MMMM d, yyyy');
            setFormData(prev => ({
              ...prev,
              trust_formation_date: formattedDate
            }));
          }
          
          // Auto-populate trustees from trustee_names field
          if (mainTrust.trustee_names) {
            const trustees = mainTrust.trustee_names.split(',').map(t => t.trim()).filter(t => t);
            if (trustees.length > 0) {
              setFormData(prev => ({
                ...prev,
                trustees_present: trustees
              }));
              setBankData(prev => ({
                ...prev,
                authorized_signers: trustees
              }));
            }
          }
        }
      }
    } catch (error) {
      console.error('Failed to load trust entity data:', error);
    }
  };

  const handleAddTrustee = () => {
    setFormData(prev => ({
      ...prev,
      trustees_present: [...prev.trustees_present, '']
    }));
  };

  const handleRemoveTrustee = (index) => {
    setFormData(prev => ({
      ...prev,
      trustees_present: prev.trustees_present.filter((_, i) => i !== index)
    }));
  };

  const handleTrusteeChange = (index, value) => {
    setFormData(prev => ({
      ...prev,
      trustees_present: prev.trustees_present.map((t, i) => i === index ? value : t)
    }));
  };

  const handleAddDistributionItem = () => {
    setDistributionData(prev => ({
      ...prev,
      distribution_items: [...prev.distribution_items, { beneficiary_name: '', amount: '', percentage: '' }]
    }));
  };

  const handleRemoveDistributionItem = (index) => {
    setDistributionData(prev => ({
      ...prev,
      distribution_items: prev.distribution_items.filter((_, i) => i !== index)
    }));
  };

  const handleDistributionItemChange = (index, field, value) => {
    setDistributionData(prev => ({
      ...prev,
      distribution_items: prev.distribution_items.map((item, i) => 
        i === index ? { ...item, [field]: value } : item
      )
    }));
  };

  const handleAddResolution = () => {
    setResolutions(prev => [...prev, {
      title: '',
      whereas_clauses: [''],
      resolved_clauses: [''],
      vote: 'Unanimous approval',
      effective_date: 'Immediately upon adoption'
    }]);
  };

  const handleRemoveResolution = (index) => {
    setResolutions(prev => prev.filter((_, i) => i !== index));
  };

  const buildTemplateData = () => {
    const baseData = {
      ...formData,
      trustees_present: formData.trustees_present.filter(t => t.trim()),
      // Include article references from trust entity
      article_ref_distribution: trustEntity?.article_ref_distribution || '',
      article_ref_compensation: trustEntity?.article_ref_compensation || '',
      article_ref_amendment: trustEntity?.article_ref_amendment || '',
      beneficiary_standard: trustEntity?.beneficiary_standard || ''
    };

    switch (templateType) {
      case 'initial_trustee_meeting':
        return {
          ...baseData,
          bank_name: formData.bank_name || '',
          initial_deposit: formData.initial_deposit || '',
          meeting_location: formData.meeting_location || '',
          meeting_time: formData.meeting_time || '',
          principal_place: formData.principal_place || formData.meeting_location || '',
          fiscal_year_end: formData.fiscal_year_end || 'December 31',
          compensation_type: formData.compensation_type || 'none',
          compensation_amount: formData.compensation_amount || '',
          accept_trusteeship: formData.accept_trusteeship !== false,
          acknowledge_fiduciary_duties: formData.acknowledge_fiduciary_duties !== false,
          authorize_ein: formData.authorize_ein !== false,
          accept_initial_property: formData.accept_initial_property !== false,
          authorize_insurance: formData.authorize_insurance !== false,
          authorize_professional_services: formData.authorize_professional_services !== false,
          designate_record_keeper: formData.designate_record_keeper !== false,
          adopt_governance_standards: formData.adopt_governance_standards !== false,
          ratify_prior_actions: formData.ratify_prior_actions !== false,
        };
      case 'distribution_to_beneficiaries':
        return {
          ...baseData,
          distribution_total: parseFloat(distributionData.distribution_total) || 0,
          distribution_items: distributionData.distribution_items
            .filter(item => item.beneficiary_name)
            .map(item => ({
              beneficiary_name: item.beneficiary_name,
              amount: parseFloat(item.amount) || 0,
              percentage: parseFloat(item.percentage) || 0
            })),
          distribution_date: distributionData.distribution_date,
          distribution_characterization: distributionData.distribution_characterization
        };
      
      case 'acceptance_of_property':
        return {
          ...baseData,
          grantor_name: propertyData.grantor_name,
          property_description: propertyData.property_description,
          property_value: parseFloat(propertyData.property_value) || null,
          property_identifier: propertyData.property_identifier,
          property_location: propertyData.property_location,
          conveyance_date: propertyData.conveyance_date,
          add_to_schedule_a: propertyData.add_to_schedule_a,
          schedule_a_category: propertyData.schedule_a_category
        };
      
      case 'disposition_of_asset':
        return {
          ...baseData,
          disposition_asset_id: dispositionData.disposition_asset_id,
          disposition_asset_description: dispositionData.disposition_asset_description,
          disposition_reason: dispositionData.disposition_reason,
          disposition_date: dispositionData.disposition_date,
          disposition_value: parseFloat(dispositionData.disposition_value) || null,
          disposition_recipient: dispositionData.disposition_recipient,
          disposition_notes: dispositionData.disposition_notes,
          update_schedule_a: dispositionData.update_schedule_a
        };
      
      case 'appointment_additional_trustee':
      case 'appointment_successor_trustee':
        return {
          ...baseData,
          appointment_type: templateType === 'appointment_successor_trustee' ? 'successor' : 'additional',
          new_trustee_name: trusteeData.new_trustee_name,
          new_trustee_gender: trusteeData.new_trustee_gender,
          departing_trustee_name: trusteeData.departing_trustee_name,
          departing_reason: trusteeData.departing_reason,
          signature_requirement: trusteeData.signature_requirement,
          signature_threshold: parseFloat(trusteeData.signature_threshold) || null,
          banking_powers_granted: trusteeData.banking_powers_granted,
          effective_date: trusteeData.effective_date
        };
      
      case 'designation_of_beneficiaries':
        return {
          ...baseData,
          designation_type: beneficiaryData.designation_type,
          total_units: parseInt(beneficiaryData.total_units) || 100,
          beneficiaries: beneficiaryData.beneficiaries
            .filter(b => b.name)
            .map(b => ({
              name: b.name,
              units: parseInt(b.units) || 0,
              percentage: parseFloat(b.percentage) || 0,
              relationship: b.relationship
            }))
        };
      
      case 'bank_account_authorization':
        return {
          ...baseData,
          bank_name: bankData.bank_name,
          account_type: bankData.account_type,
          purpose: bankData.purpose,
          authorized_signers: bankData.authorized_signers.filter(s => s.trim()),
          signature_requirement: bankData.signature_requirement,
          signature_threshold: parseFloat(bankData.signature_threshold) || null,
          initial_deposit: parseFloat(bankData.initial_deposit) || null
        };
      
      case 'change_of_situs':
        return {
          ...baseData,
          current_situs: situsData.current_situs,
          new_situs: situsData.new_situs,
          effective_date: situsData.effective_date,
          reasons: situsData.reasons.filter(r => r.trim())
        };
      
      case 'benevolence_approval':
        return {
          ...baseData,
          beneficiary_name: benevolenceData.beneficiary_name,
          beneficiary_type: benevolenceData.beneficiary_type,
          benevolence_purpose: benevolenceData.benevolence_purpose,
          purpose_description: benevolenceData.purpose_description,
          amount: parseFloat(benevolenceData.amount) || 0,
          disbursement_date: benevolenceData.disbursement_date,
          add_to_benevolence_log: benevolenceData.add_to_benevolence_log
        };
      
      // NEW TEMPLATES
      case 'investment_policy':
        return {
          ...baseData,
          policy_type: investmentPolicyData.policy_type,
          risk_tolerance: investmentPolicyData.risk_tolerance,
          asset_allocation: investmentPolicyData.asset_allocation,
          investment_restrictions: investmentPolicyData.investment_restrictions.filter(r => r.trim()),
          review_frequency: investmentPolicyData.review_frequency
        };
      
      case 'loan_authorization':
        return {
          ...baseData,
          loan_direction: loanAuthData.loan_direction,
          borrower_name: loanAuthData.borrower_name,
          lender_name: loanAuthData.lender_name,
          loan_amount: parseFloat(loanAuthData.loan_amount) || 0,
          interest_rate: loanAuthData.interest_rate,
          term_months: parseInt(loanAuthData.term_months) || 60,
          loan_purpose: loanAuthData.loan_purpose,
          collateral_description: loanAuthData.collateral_description
        };
      
      case 'insurance_authorization':
        return {
          ...baseData,
          insurance_type: insuranceData.insurance_type,
          policy_action: insuranceData.policy_action,
          insurer_name: insuranceData.insurer_name,
          coverage_amount: parseFloat(insuranceData.coverage_amount) || 0,
          premium_amount: parseFloat(insuranceData.premium_amount) || 0,
          coverage_description: insuranceData.coverage_description,
          policy_number: insuranceData.policy_number
        };
      
      case 'annual_review':
        return {
          ...baseData,
          fiscal_year: annualReviewData.fiscal_year,
          total_assets: parseFloat(annualReviewData.total_assets) || 0,
          total_income: parseFloat(annualReviewData.total_income) || 0,
          total_expenses: parseFloat(annualReviewData.total_expenses) || 0,
          total_distributions: parseFloat(annualReviewData.total_distributions) || 0,
          investment_return: annualReviewData.investment_return,
          key_accomplishments: annualReviewData.key_accomplishments.filter(a => a.trim()),
          upcoming_priorities: annualReviewData.upcoming_priorities.filter(p => p.trim()),
          governance_items: annualReviewData.governance_items.filter(g => g.trim())
        };
      
      case 'quarterly_review':
        return {
          ...baseData,
          quarter: quarterlyReviewData.quarter,
          year: quarterlyReviewData.year,
          beginning_balance: parseFloat(quarterlyReviewData.beginning_balance) || 0,
          ending_balance: parseFloat(quarterlyReviewData.ending_balance) || 0,
          income_received: parseFloat(quarterlyReviewData.income_received) || 0,
          expenses_paid: parseFloat(quarterlyReviewData.expenses_paid) || 0,
          distributions_made: parseFloat(quarterlyReviewData.distributions_made) || 0,
          discussion_items: quarterlyReviewData.discussion_items.filter(d => d.trim()),
          action_items: quarterlyReviewData.action_items.filter(a => a.trim())
        };
      
      case 'trustee_compensation':
        return {
          ...baseData,
          trustee_name: trusteeCompData.trustee_name,
          compensation_type: trusteeCompData.compensation_type,
          compensation_amount: parseFloat(trusteeCompData.compensation_amount) || 0,
          effective_date: trusteeCompData.effective_date,
          compensation_basis: trusteeCompData.compensation_basis,
          duties_description: trusteeCompData.duties_description,
          all_trustees: trusteeCompData.all_trustees
        };
      
      case 'trustee_resignation':
        return {
          ...baseData,
          departing_trustee_name: trusteeResignData.departing_trustee_name,
          departure_type: trusteeResignData.departure_type,
          departure_reason: trusteeResignData.departure_reason,
          effective_date: trusteeResignData.effective_date,
          remaining_trustees: trusteeResignData.remaining_trustees.filter(t => t.trim()),
          successor_appointed: trusteeResignData.successor_appointed,
          successor_name: trusteeResignData.successor_name
        };
      
      case 'beneficiary_request_denial':
        return {
          ...baseData,
          beneficiary_name: denialData.beneficiary_name,
          request_type: denialData.request_type,
          request_amount: parseFloat(denialData.request_amount) || 0,
          request_purpose: denialData.request_purpose,
          request_date: denialData.request_date,
          denial_reasons: denialData.denial_reasons.filter(r => r.trim()),
          alternative_offered: denialData.alternative_offered
        };
      
      case 'hems_distribution':
        return {
          ...baseData,
          beneficiary_name: hemsData.beneficiary_name,
          hems_category: hemsData.hems_category,
          distribution_amount: parseFloat(hemsData.distribution_amount) || 0,
          specific_purpose: hemsData.specific_purpose,
          supporting_documentation: hemsData.supporting_documentation.filter(d => d.trim()),
          recurring: hemsData.recurring,
          recurring_frequency: hemsData.recurring_frequency
        };
      
      case 'beneficiary_loan':
        return {
          ...baseData,
          beneficiary_name: beneficiaryLoanData.beneficiary_name,
          loan_amount: parseFloat(beneficiaryLoanData.loan_amount) || 0,
          interest_rate: beneficiaryLoanData.interest_rate,
          term_months: parseInt(beneficiaryLoanData.term_months) || 60,
          loan_purpose: beneficiaryLoanData.loan_purpose,
          collateral_description: beneficiaryLoanData.collateral_description,
          repayment_terms: beneficiaryLoanData.repayment_terms
        };
      
      // ========== BATCH 2 TEMPLATES ==========
      
      case 'trust_amendment':
        return {
          ...baseData,
          amendment_type: amendmentData.amendment_type,
          article_section: amendmentData.article_section,
          current_provision: amendmentData.current_provision,
          amended_provision: amendmentData.amended_provision,
          effective_date: amendmentData.effective_date,
          reason: amendmentData.reason
        };
      
      case 'power_of_attorney':
        return {
          ...baseData,
          agent_name: poaData.agent_name,
          scope: poaData.scope,
          powers_granted: poaData.powers_granted.filter(p => p.trim()),
          expiration: poaData.expiration,
          purpose: poaData.purpose
        };
      
      case 'trust_termination':
        return {
          ...baseData,
          termination_reason: terminationData.termination_reason,
          termination_date: terminationData.termination_date,
          distribution_plan: terminationData.distribution_plan,
          final_accounting_date: terminationData.final_accounting_date,
          outstanding_obligations: terminationData.outstanding_obligations
        };
      
      case 'real_estate_purchase':
        return {
          ...baseData,
          property_address: realEstatePurchaseData.property_address,
          property_type: realEstatePurchaseData.property_type,
          purchase_price: realEstatePurchaseData.purchase_price,
          financing: realEstatePurchaseData.financing,
          purpose: realEstatePurchaseData.purpose,
          inspection_period: realEstatePurchaseData.inspection_period
        };
      
      case 'business_interest_acquisition':
        return {
          ...baseData,
          entity_name: businessInterestData.entity_name,
          entity_type: businessInterestData.entity_type,
          ownership_percentage: businessInterestData.ownership_percentage,
          purchase_price: businessInterestData.purchase_price,
          purpose: businessInterestData.purpose,
          due_diligence: businessInterestData.due_diligence
        };
      
      case 'real_estate_lease':
        return {
          ...baseData,
          property_address: realEstateLeaseData.property_address,
          tenant_name: realEstateLeaseData.tenant_name,
          lease_term: realEstateLeaseData.lease_term,
          monthly_rent: realEstateLeaseData.monthly_rent,
          security_deposit: realEstateLeaseData.security_deposit,
          permitted_use: realEstateLeaseData.permitted_use
        };
      
      case 'fiscal_year_election':
        return {
          ...baseData,
          fiscal_year_end: fiscalYearData.fiscal_year_end,
          election_type: fiscalYearData.election_type,
          effective_year: fiscalYearData.effective_year,
          reason: fiscalYearData.reason
        };
      
      case 'tax_filing_authorization':
        return {
          ...baseData,
          tax_year: taxFilingData.tax_year,
          preparer_name: taxFilingData.preparer_name,
          returns_to_file: taxFilingData.returns_to_file.filter(r => r.trim()),
          filing_deadline: taxFilingData.filing_deadline,
          extension_authorized: taxFilingData.extension_authorized
        };
      
      case 'emergency_ratification':
        return {
          ...baseData,
          action_date: emergencyData.action_date,
          emergency_type: emergencyData.emergency_type,
          actions_taken: emergencyData.actions_taken.filter(a => a.trim()),
          trustee_acting: emergencyData.trustee_acting,
          cost_incurred: emergencyData.cost_incurred,
          outcome: emergencyData.outcome
        };
      
      case 'conflict_of_interest':
        return {
          ...baseData,
          trustee_name: conflictData.trustee_name,
          conflict_type: conflictData.conflict_type,
          description: conflictData.description,
          related_transaction: conflictData.related_transaction,
          disclosure_date: conflictData.disclosure_date,
          waiver_granted: conflictData.waiver_granted,
          conditions: conflictData.conditions
        };
      
      case 'general_meeting':
      default:
        return {
          ...baseData,
          resolutions: resolutions.filter(r => r.title).map(r => ({
            title: r.title,
            whereas_clauses: r.whereas_clauses.filter(c => c.trim()),
            resolved_clauses: r.resolved_clauses.filter(c => c.trim()),
            vote: r.vote,
            effective_date: r.effective_date
          }))
        };
    }
  };

  const handleGeneratePreview = async () => {
    if (!selectedTrust) {
      toast.error('Please select a trust');
      return;
    }

    setLoading(true);
    try {
      const templateData = buildTemplateData();
      
      const response = await fetchWithAuth('/minutes-templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          template_type: templateType,
          template_data: templateData
        })
      });

      if (response.ok) {
        const result = await response.json();
        setGeneratedDoc(result.generated_document);
        setMinutesId(result.minutes_id);
        setPreviewMode(true);
        toast.success('Minutes generated');
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to generate minutes');
      }
    } catch (error) {
      toast.error('Failed to generate minutes');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveMinutes = async () => {
    if (!minutesId) return;

    setLoading(true);
    try {
      const response = await fetchWithAuth(`/minutes-templates/${minutesId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          generated_document: generatedDoc,
          status: 'final'
        })
      });

      if (response.ok) {
        toast.success('Minutes saved');
        navigate('/minutes');
      } else {
        toast.error('Failed to save minutes');
      }
    } catch (error) {
      toast.error('Failed to save minutes');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    if (!minutesId) return;

    try {
      const response = await fetchWithAuth(`/minutes-templates/${minutesId}/pdf`);
      if (response.ok) {
        const data = await response.json();
        const link = document.createElement('a');
        link.href = `data:application/pdf;base64,${data.pdf_base64}`;
        link.download = data.filename;
        link.click();
        toast.success('PDF downloaded');
      }
    } catch (error) {
      toast.error('Failed to download PDF');
    }
  };

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Select a trust to create minutes</p>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <main className="lg:pl-64 pt-16 lg:pt-0">
        <div className="p-4 lg:p-8">
          {/* Header */}
          <div className="mb-8">
            <Button 
              variant="ghost" 
              className="mb-4"
              onClick={() => previewMode ? setPreviewMode(false) : navigate(searchParams.get('from') === 'create' ? '/minutes/create' : '/minutes/templates')}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              {previewMode ? 'Back to Form' : searchParams.get('from') === 'create' ? 'Back to Create' : 'Back to Templates'}
            </Button>
            <h1 className="font-serif text-3xl lg:text-4xl text-navy mb-2">
              {TEMPLATE_TITLES[templateType] || 'Create Minutes'}
            </h1>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              {selectedTrust.name}
            </p>
          </div>

          {previewMode ? (
            /* Preview Mode */
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <h2 className="font-serif text-xl text-navy">Document Preview</h2>
                <div className="flex gap-3">
                  <Button variant="outline" onClick={handleDownloadPDF}>
                    <Download className="w-4 h-4 mr-2" />
                    Download PDF
                  </Button>
                  <Button className="btn-primary" onClick={handleSaveMinutes} disabled={loading}>
                    <Save className="w-4 h-4 mr-2" />
                    {loading ? 'Saving...' : 'Save Minutes'}
                  </Button>
                </div>
              </div>
              
              <div className="card-trust p-6">
                <p className="text-xs text-muted-foreground mb-4">
                  You can edit the document below before saving. Changes are tracked for audit purposes.
                </p>
                <Textarea
                  value={generatedDoc}
                  onChange={(e) => setGeneratedDoc(e.target.value)}
                  className="font-mono text-sm min-h-[600px] whitespace-pre-wrap"
                  data-testid="generated-document"
                />
              </div>
            </div>
          ) : (
            /* Form Mode */
            <div className="space-y-8">
              {/* Common Fields */}
              <div className="card-trust corner-mark p-6">
                <h2 className="font-serif text-xl text-navy mb-4">Meeting Information</h2>
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <Label className="label-trust">Minute Number</Label>
                    <Input
                      value={formData.minute_number}
                      onChange={(e) => setFormData({ ...formData, minute_number: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="2024-001"
                    />
                  </div>
                  <div>
                    <Label className="label-trust">Meeting Date</Label>
                    <Input
                      value={formData.meeting_date}
                      onChange={(e) => setFormData({ ...formData, meeting_date: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="February 23, 2024"
                    />
                  </div>
                  <div>
                    <Label className="label-trust">Meeting Time</Label>
                    <Input
                      value={formData.meeting_time}
                      onChange={(e) => setFormData({ ...formData, meeting_time: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="10:00 AM"
                    />
                  </div>
                  <div>
                    <Label className="label-trust">Meeting Type</Label>
                    <Select value={formData.meeting_type} onValueChange={(v) => setFormData({ ...formData, meeting_type: v })}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="unanimous_written_consent">Unanimous Written Consent</SelectItem>
                        <SelectItem value="in_person">In Person</SelectItem>
                        <SelectItem value="video_conference">Video/Phone Conference</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {formData.meeting_type === 'in_person' && (
                    <div className="md:col-span-2">
                      <Label className="label-trust">Meeting Location</Label>
                      <Input
                        value={formData.meeting_location}
                        onChange={(e) => setFormData({ ...formData, meeting_location: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="123 Main Street, City, State"
                      />
                    </div>
                  )}
                  <div className="md:col-span-2">
                    <Label className="label-trust">Trust Formation Date</Label>
                    <Input
                      value={formData.trust_formation_date}
                      onChange={(e) => setFormData({ ...formData, trust_formation_date: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="January 1, 2020"
                    />
                  </div>
                </div>

                {/* Trustees Present */}
                <div className="mt-6">
                  <div className="flex items-center justify-between mb-2">
                    <Label className="label-trust">Trustees Present</Label>
                    <Button type="button" variant="ghost" size="sm" onClick={handleAddTrustee}>
                      <Plus className="w-4 h-4 mr-1" />
                      Add Trustee
                    </Button>
                  </div>
                  <div className="space-y-2">
                    {formData.trustees_present.map((trustee, index) => (
                      <div key={index} className="flex gap-2">
                        <Input
                          value={trustee}
                          onChange={(e) => handleTrusteeChange(index, e.target.value)}
                          className="input-trust"
                          placeholder="Trustee name"
                        />
                        {formData.trustees_present.length > 1 && (
                          <Button type="button" variant="ghost" size="icon" onClick={() => handleRemoveTrustee(index)}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Template-specific fields */}
              {templateType === 'distribution_to_beneficiaries' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Distribution Details</h2>
                  <div className="grid md:grid-cols-2 gap-4 mb-6">
                    <div>
                      <Label className="label-trust">Total Distribution Amount</Label>
                      <Input
                        type="number"
                        value={distributionData.distribution_total}
                        onChange={(e) => setDistributionData({ ...distributionData, distribution_total: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="50000"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Distribution Date</Label>
                      <Input
                        value={distributionData.distribution_date}
                        onChange={(e) => setDistributionData({ ...distributionData, distribution_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="March 1, 2024"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Characterization</Label>
                      <Select value={distributionData.distribution_characterization} onValueChange={(v) => setDistributionData({ ...distributionData, distribution_characterization: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="income">Income</SelectItem>
                          <SelectItem value="principal">Principal</SelectItem>
                          <SelectItem value="return_of_corpus">Return of Corpus</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mb-2">
                    <Label className="label-trust">Beneficiaries</Label>
                    <Button type="button" variant="ghost" size="sm" onClick={handleAddDistributionItem}>
                      <Plus className="w-4 h-4 mr-1" />
                      Add Beneficiary
                    </Button>
                  </div>
                  <div className="space-y-3">
                    {distributionData.distribution_items.map((item, index) => (
                      <div key={index} className="flex gap-2 items-end">
                        <div className="flex-1">
                          <Input
                            value={item.beneficiary_name}
                            onChange={(e) => handleDistributionItemChange(index, 'beneficiary_name', e.target.value)}
                            placeholder="Beneficiary name"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-32">
                          <Input
                            type="number"
                            value={item.amount}
                            onChange={(e) => handleDistributionItemChange(index, 'amount', e.target.value)}
                            placeholder="Amount"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-24">
                          <Input
                            type="number"
                            value={item.percentage}
                            onChange={(e) => handleDistributionItemChange(index, 'percentage', e.target.value)}
                            placeholder="%"
                            className="input-trust"
                          />
                        </div>
                        {distributionData.distribution_items.length > 1 && (
                          <Button type="button" variant="ghost" size="icon" onClick={() => handleRemoveDistributionItem(index)}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {templateType === 'acceptance_of_property' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Property Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <Label className="label-trust">Grantor/Creator Name</Label>
                      <Input
                        value={propertyData.grantor_name}
                        onChange={(e) => setPropertyData({ ...propertyData, grantor_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="John Smith"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Property Description</Label>
                      <Textarea
                        value={propertyData.property_description}
                        onChange={(e) => setPropertyData({ ...propertyData, property_description: e.target.value })}
                        className="mt-1"
                        placeholder="Single-family residence located at 123 Main Street, City, State 12345; Lot 4, Block 2, Subdivision XYZ"
                        rows={3}
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Identifier (VIN, Account #, Legal Description)</Label>
                      <Input
                        value={propertyData.property_identifier}
                        onChange={(e) => setPropertyData({ ...propertyData, property_identifier: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="VIN: 1HGBH41JXMN109186"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Location / Institution</Label>
                      <Input
                        value={propertyData.property_location}
                        onChange={(e) => setPropertyData({ ...propertyData, property_location: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="123 Main St, City, State 12345"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Approximate Value</Label>
                      <Input
                        type="number"
                        value={propertyData.property_value}
                        onChange={(e) => setPropertyData({ ...propertyData, property_value: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="250000"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Date of Conveyance</Label>
                      <Input
                        value={propertyData.conveyance_date}
                        onChange={(e) => setPropertyData({ ...propertyData, conveyance_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="February 23, 2024"
                      />
                    </div>
                    <div className="md:col-span-2 flex items-center gap-3 mt-2">
                      <Checkbox
                        checked={propertyData.add_to_schedule_a}
                        onCheckedChange={(checked) => setPropertyData({ ...propertyData, add_to_schedule_a: checked })}
                        id="add-schedule-a"
                      />
                      <Label htmlFor="add-schedule-a" className="cursor-pointer">
                        Automatically add to Schedule A
                      </Label>
                    </div>
                    {propertyData.add_to_schedule_a && (
                      <div className="md:col-span-2">
                        <Label className="label-trust">Asset Category (for Schedule A)</Label>
                        <Select value={propertyData.schedule_a_category} onValueChange={(v) => setPropertyData({ ...propertyData, schedule_a_category: v })}>
                          <SelectTrigger className="mt-1">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {ASSET_CATEGORIES.map(cat => (
                              <SelectItem key={cat.value} value={cat.value}>{cat.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {templateType === 'disposition_of_asset' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Asset Disposition Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <Label className="label-trust">Select Asset from Schedule A</Label>
                      {loadingAssets ? (
                        <div className="mt-2 text-muted-foreground">Loading assets...</div>
                      ) : scheduleAAssets.length === 0 ? (
                        <div className="mt-2 text-muted-foreground">No active assets found in Schedule A</div>
                      ) : (
                        <Select 
                          value={dispositionData.disposition_asset_id} 
                          onValueChange={(v) => {
                            const asset = scheduleAAssets.find(a => a.item_id === v);
                            setDispositionData({ 
                              ...dispositionData, 
                              disposition_asset_id: v,
                              disposition_asset_description: asset ? `${asset.description} (${asset.category.replace(/_/g, ' ')})` : ''
                            });
                          }}
                        >
                          <SelectTrigger className="mt-1">
                            <SelectValue placeholder="Select an asset to dispose" />
                          </SelectTrigger>
                          <SelectContent>
                            {scheduleAAssets.map(asset => (
                              <SelectItem key={asset.item_id} value={asset.item_id}>
                                {asset.description} - {asset.category.replace(/_/g, ' ')} 
                                {asset.approximate_value && ` ($${asset.approximate_value.toLocaleString()})`}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    </div>
                    
                    {dispositionData.disposition_asset_id && (
                      <>
                        <div className="md:col-span-2">
                          <Label className="label-trust">Asset Description (for minutes)</Label>
                          <Textarea
                            value={dispositionData.disposition_asset_description}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_asset_description: e.target.value })}
                            className="mt-1"
                            placeholder="2020 Toyota Camry, VIN: 1HGBH41JXMN109186"
                            rows={2}
                          />
                        </div>
                        
                        <div>
                          <Label className="label-trust">Reason for Disposition</Label>
                          <Select 
                            value={dispositionData.disposition_reason} 
                            onValueChange={(v) => setDispositionData({ ...dispositionData, disposition_reason: v })}
                          >
                            <SelectTrigger className="mt-1">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="sale">Sale</SelectItem>
                              <SelectItem value="transfer">Transfer</SelectItem>
                              <SelectItem value="donation">Donation</SelectItem>
                              <SelectItem value="destruction">Destruction / Total Loss</SelectItem>
                              <SelectItem value="other">Other</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        
                        <div>
                          <Label className="label-trust">Date of Disposition</Label>
                          <Input
                            value={dispositionData.disposition_date}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_date: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="February 23, 2024"
                          />
                        </div>
                        
                        <div>
                          <Label className="label-trust">
                            {dispositionData.disposition_reason === 'sale' ? 'Sale Price' : 'Fair Market Value'}
                          </Label>
                          <Input
                            type="number"
                            value={dispositionData.disposition_value}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_value: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="25000"
                          />
                        </div>
                        
                        <div>
                          <Label className="label-trust">
                            {dispositionData.disposition_reason === 'sale' ? 'Buyer' : 'Recipient'} (if applicable)
                          </Label>
                          <Input
                            value={dispositionData.disposition_recipient}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_recipient: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="ABC Motors LLC"
                          />
                        </div>
                        
                        <div className="md:col-span-2">
                          <Label className="label-trust">Additional Notes</Label>
                          <Textarea
                            value={dispositionData.disposition_notes}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_notes: e.target.value })}
                            className="mt-1"
                            placeholder="Any additional details about the disposition..."
                            rows={2}
                          />
                        </div>
                        
                        <div className="md:col-span-2 flex items-center gap-3 mt-2">
                          <Checkbox
                            checked={dispositionData.update_schedule_a}
                            onCheckedChange={(checked) => setDispositionData({ ...dispositionData, update_schedule_a: checked })}
                            id="update-schedule-a"
                          />
                          <Label htmlFor="update-schedule-a" className="cursor-pointer">
                            Mark asset as disposed in Schedule A (keeps historical record)
                          </Label>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}

              {(templateType === 'appointment_additional_trustee' || templateType === 'appointment_successor_trustee') && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">
                    {templateType === 'appointment_successor_trustee' ? 'Successor Trustee Details' : 'New Trustee Details'}
                  </h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">New Trustee Name</Label>
                      <Input
                        value={trusteeData.new_trustee_name}
                        onChange={(e) => setTrusteeData({ ...trusteeData, new_trustee_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Jane Doe"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Gender (for document language)</Label>
                      <Select value={trusteeData.new_trustee_gender} onValueChange={(v) => setTrusteeData({ ...trusteeData, new_trustee_gender: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="man">Man</SelectItem>
                          <SelectItem value="woman">Woman</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    {templateType === 'appointment_successor_trustee' && (
                      <>
                        <div>
                          <Label className="label-trust">Departing Trustee Name</Label>
                          <Input
                            value={trusteeData.departing_trustee_name}
                            onChange={(e) => setTrusteeData({ ...trusteeData, departing_trustee_name: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="John Smith"
                          />
                        </div>
                        <div>
                          <Label className="label-trust">Reason for Departure</Label>
                          <Select value={trusteeData.departing_reason} onValueChange={(v) => setTrusteeData({ ...trusteeData, departing_reason: v })}>
                            <SelectTrigger className="mt-1">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="resigned">Resigned</SelectItem>
                              <SelectItem value="died">Died</SelectItem>
                              <SelectItem value="incapacitated">Become Incapacitated</SelectItem>
                              <SelectItem value="removed">Been Removed</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </>
                    )}

                    <div>
                      <Label className="label-trust">Effective Date</Label>
                      <Input
                        value={trusteeData.effective_date}
                        onChange={(e) => setTrusteeData({ ...trusteeData, effective_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="February 23, 2024"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Signature Requirement</Label>
                      <Select value={trusteeData.signature_requirement} onValueChange={(v) => setTrusteeData({ ...trusteeData, signature_requirement: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="any_one">Any One Trustee (no limit)</SelectItem>
                          <SelectItem value="any_two">Any Two Trustees (all transactions)</SelectItem>
                          <SelectItem value="threshold">One up to threshold, Two above</SelectItem>
                          <SelectItem value="all_trustees">All Trustees (above threshold)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    {(trusteeData.signature_requirement === 'threshold' || trusteeData.signature_requirement === 'all_trustees') && (
                      <div>
                        <Label className="label-trust">Signature Threshold Amount</Label>
                        <Input
                          type="number"
                          value={trusteeData.signature_threshold}
                          onChange={(e) => setTrusteeData({ ...trusteeData, signature_threshold: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="10000"
                        />
                      </div>
                    )}

                    <div className="md:col-span-2 flex items-center gap-3 mt-2">
                      <Checkbox
                        checked={trusteeData.banking_powers_granted}
                        onCheckedChange={(checked) => setTrusteeData({ ...trusteeData, banking_powers_granted: checked })}
                        id="banking-powers"
                      />
                      <Label htmlFor="banking-powers" className="cursor-pointer">
                        Grant banking and signatory powers
                      </Label>
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'designation_of_beneficiaries' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Beneficiary Designation</h2>
                  <div className="grid md:grid-cols-2 gap-4 mb-6">
                    <div>
                      <Label className="label-trust">Designation Type</Label>
                      <Select value={beneficiaryData.designation_type} onValueChange={(v) => setBeneficiaryData({ ...beneficiaryData, designation_type: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="initial">Initial Designation</SelectItem>
                          <SelectItem value="amendment">Amendment to Existing</SelectItem>
                          <SelectItem value="restatement">Complete Restatement</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Total Units of Beneficial Interest</Label>
                      <Input
                        type="number"
                        value={beneficiaryData.total_units}
                        onChange={(e) => setBeneficiaryData({ ...beneficiaryData, total_units: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="100"
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-between mb-2">
                    <Label className="label-trust">Beneficiaries</Label>
                    <Button type="button" variant="ghost" size="sm" onClick={() => setBeneficiaryData(prev => ({
                      ...prev,
                      beneficiaries: [...prev.beneficiaries, { name: '', units: '', percentage: '', relationship: '' }]
                    }))}>
                      <Plus className="w-4 h-4 mr-1" />
                      Add Beneficiary
                    </Button>
                  </div>
                  <div className="space-y-3">
                    {beneficiaryData.beneficiaries.map((ben, index) => (
                      <div key={index} className="flex gap-2 items-end">
                        <div className="flex-1">
                          <Input
                            value={ben.name}
                            onChange={(e) => {
                              const newBens = [...beneficiaryData.beneficiaries];
                              newBens[index].name = e.target.value;
                              setBeneficiaryData({ ...beneficiaryData, beneficiaries: newBens });
                            }}
                            placeholder="Beneficiary name"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-24">
                          <Input
                            type="number"
                            value={ben.units}
                            onChange={(e) => {
                              const newBens = [...beneficiaryData.beneficiaries];
                              newBens[index].units = e.target.value;
                              setBeneficiaryData({ ...beneficiaryData, beneficiaries: newBens });
                            }}
                            placeholder="Units"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-20">
                          <Input
                            type="number"
                            value={ben.percentage}
                            onChange={(e) => {
                              const newBens = [...beneficiaryData.beneficiaries];
                              newBens[index].percentage = e.target.value;
                              setBeneficiaryData({ ...beneficiaryData, beneficiaries: newBens });
                            }}
                            placeholder="%"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-32">
                          <Input
                            value={ben.relationship}
                            onChange={(e) => {
                              const newBens = [...beneficiaryData.beneficiaries];
                              newBens[index].relationship = e.target.value;
                              setBeneficiaryData({ ...beneficiaryData, beneficiaries: newBens });
                            }}
                            placeholder="Relationship"
                            className="input-trust"
                          />
                        </div>
                        {beneficiaryData.beneficiaries.length > 1 && (
                          <Button type="button" variant="ghost" size="icon" onClick={() => {
                            setBeneficiaryData(prev => ({
                              ...prev,
                              beneficiaries: prev.beneficiaries.filter((_, i) => i !== index)
                            }));
                          }}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {templateType === 'bank_account_authorization' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Bank Account Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Bank/Institution Name</Label>
                      <Input
                        value={bankData.bank_name}
                        onChange={(e) => setBankData({ ...bankData, bank_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., Chase Bank, Charles Schwab"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Account Type</Label>
                      <Select value={bankData.account_type} onValueChange={(v) => setBankData({ ...bankData, account_type: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="checking">Checking Account</SelectItem>
                          <SelectItem value="savings">Savings Account</SelectItem>
                          <SelectItem value="brokerage">Brokerage/Investment Account</SelectItem>
                          <SelectItem value="money_market">Money Market Account</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Purpose</Label>
                      <Input
                        value={bankData.purpose}
                        onChange={(e) => setBankData({ ...bankData, purpose: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., general trust administration, investment holdings"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Signature Requirement</Label>
                      <Select value={bankData.signature_requirement} onValueChange={(v) => setBankData({ ...bankData, signature_requirement: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="any_one">Any One Trustee</SelectItem>
                          <SelectItem value="any_two">Any Two Trustees</SelectItem>
                          <SelectItem value="threshold">One up to threshold, Two above</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    {bankData.signature_requirement === 'threshold' && (
                      <div>
                        <Label className="label-trust">Signature Threshold</Label>
                        <Input
                          type="number"
                          value={bankData.signature_threshold}
                          onChange={(e) => setBankData({ ...bankData, signature_threshold: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="10000"
                        />
                      </div>
                    )}
                    <div>
                      <Label className="label-trust">Initial Deposit (optional)</Label>
                      <Input
                        type="number"
                        value={bankData.initial_deposit}
                        onChange={(e) => setBankData({ ...bankData, initial_deposit: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="0.00"
                      />
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="flex items-center justify-between mb-2">
                      <Label className="label-trust">Authorized Signers</Label>
                      <Button type="button" variant="ghost" size="sm" onClick={() => setBankData(prev => ({
                        ...prev,
                        authorized_signers: [...prev.authorized_signers, '']
                      }))}>
                        <Plus className="w-4 h-4 mr-1" />
                        Add Signer
                      </Button>
                    </div>
                    <div className="space-y-2">
                      {bankData.authorized_signers.map((signer, index) => (
                        <div key={index} className="flex gap-2">
                          <Input
                            value={signer}
                            onChange={(e) => {
                              const newSigners = [...bankData.authorized_signers];
                              newSigners[index] = e.target.value;
                              setBankData({ ...bankData, authorized_signers: newSigners });
                            }}
                            className="input-trust"
                            placeholder="Trustee name"
                          />
                          {bankData.authorized_signers.length > 1 && (
                            <Button type="button" variant="ghost" size="icon" onClick={() => {
                              setBankData(prev => ({
                                ...prev,
                                authorized_signers: prev.authorized_signers.filter((_, i) => i !== index)
                              }));
                            }}>
                              <Trash2 className="w-4 h-4 text-red-500" />
                            </Button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'change_of_situs' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Change of Situs Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Current Situs (State/Jurisdiction)</Label>
                      <Input
                        value={situsData.current_situs}
                        onChange={(e) => setSitusData({ ...situsData, current_situs: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., State of Texas"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">New Situs (State/Jurisdiction)</Label>
                      <Input
                        value={situsData.new_situs}
                        onChange={(e) => setSitusData({ ...situsData, new_situs: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., State of Nevada"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Effective Date</Label>
                      <Input
                        value={situsData.effective_date}
                        onChange={(e) => setSitusData({ ...situsData, effective_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="March 1, 2024"
                      />
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="flex items-center justify-between mb-2">
                      <Label className="label-trust">Reasons for Change (optional)</Label>
                      <Button type="button" variant="ghost" size="sm" onClick={() => setSitusData(prev => ({
                        ...prev,
                        reasons: [...prev.reasons, '']
                      }))}>
                        <Plus className="w-4 h-4 mr-1" />
                        Add Reason
                      </Button>
                    </div>
                    <div className="space-y-2">
                      {situsData.reasons.map((reason, index) => (
                        <div key={index} className="flex gap-2">
                          <Input
                            value={reason}
                            onChange={(e) => {
                              const newReasons = [...situsData.reasons];
                              newReasons[index] = e.target.value;
                              setSitusData({ ...situsData, reasons: newReasons });
                            }}
                            className="input-trust"
                            placeholder="e.g., Favorable trust laws, tax considerations"
                          />
                          {situsData.reasons.length > 1 && (
                            <Button type="button" variant="ghost" size="icon" onClick={() => {
                              setSitusData(prev => ({
                                ...prev,
                                reasons: prev.reasons.filter((_, i) => i !== index)
                              }));
                            }}>
                              <Trash2 className="w-4 h-4 text-red-500" />
                            </Button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'benevolence_approval' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Benevolence Grant Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <Label className="label-trust">Beneficiary Name *</Label>
                      <Input
                        value={benevolenceData.beneficiary_name}
                        onChange={(e) => setBenevolenceData({ ...benevolenceData, beneficiary_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Name of recipient"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Beneficiary Type</Label>
                      <Select value={benevolenceData.beneficiary_type} onValueChange={(v) => setBenevolenceData({ ...benevolenceData, beneficiary_type: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="individual">Individual</SelectItem>
                          <SelectItem value="family">Family</SelectItem>
                          <SelectItem value="organization">Organization</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Purpose Category</Label>
                      <Select value={benevolenceData.benevolence_purpose} onValueChange={(v) => setBenevolenceData({ ...benevolenceData, benevolence_purpose: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="medical">Medical Expenses</SelectItem>
                          <SelectItem value="housing">Housing Assistance</SelectItem>
                          <SelectItem value="education">Education</SelectItem>
                          <SelectItem value="food_necessities">Food & Necessities</SelectItem>
                          <SelectItem value="utilities">Utilities</SelectItem>
                          <SelectItem value="transportation">Transportation</SelectItem>
                          <SelectItem value="emergency">Emergency Relief</SelectItem>
                          <SelectItem value="spiritual">Spiritual/Ministry</SelectItem>
                          <SelectItem value="assistance">General Assistance</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Purpose Description *</Label>
                      <Textarea
                        value={benevolenceData.purpose_description}
                        onChange={(e) => setBenevolenceData({ ...benevolenceData, purpose_description: e.target.value })}
                        className="mt-1"
                        placeholder="Describe the need and how the assistance will help"
                        rows={3}
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Grant Amount *</Label>
                      <Input
                        type="number"
                        value={benevolenceData.amount}
                        onChange={(e) => setBenevolenceData({ ...benevolenceData, amount: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="500.00"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Disbursement Date</Label>
                      <Input
                        value={benevolenceData.disbursement_date}
                        onChange={(e) => setBenevolenceData({ ...benevolenceData, disbursement_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="March 1, 2024"
                      />
                    </div>
                    <div className="md:col-span-2 flex items-center gap-3 mt-2">
                      <Checkbox
                        checked={benevolenceData.add_to_benevolence_log}
                        onCheckedChange={(checked) => setBenevolenceData({ ...benevolenceData, add_to_benevolence_log: checked })}
                        id="add-benevolence-log"
                      />
                      <Label htmlFor="add-benevolence-log" className="cursor-pointer">
                        Automatically add to Benevolence Log
                      </Label>
                    </div>
                  </div>
                </div>
              )}

              {/* INVESTMENT POLICY TEMPLATE */}
              {templateType === 'investment_policy' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Investment Policy Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Policy Action</Label>
                      <Select value={investmentPolicyData.policy_type} onValueChange={(v) => setInvestmentPolicyData({ ...investmentPolicyData, policy_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="adopt">Adopt New Policy</SelectItem>
                          <SelectItem value="amend">Amend Existing Policy</SelectItem>
                          <SelectItem value="review">Review & Reaffirm</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Risk Tolerance</Label>
                      <Select value={investmentPolicyData.risk_tolerance} onValueChange={(v) => setInvestmentPolicyData({ ...investmentPolicyData, risk_tolerance: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="conservative">Conservative</SelectItem>
                          <SelectItem value="moderate">Moderate</SelectItem>
                          <SelectItem value="moderately_aggressive">Moderately Aggressive</SelectItem>
                          <SelectItem value="aggressive">Aggressive</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Review Frequency</Label>
                      <Select value={investmentPolicyData.review_frequency} onValueChange={(v) => setInvestmentPolicyData({ ...investmentPolicyData, review_frequency: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="quarterly">Quarterly</SelectItem>
                          <SelectItem value="semi-annually">Semi-Annually</SelectItem>
                          <SelectItem value="annually">Annually</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              )}

              {/* LOAN AUTHORIZATION TEMPLATE */}
              {templateType === 'loan_authorization' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Loan Authorization Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Loan Direction</Label>
                      <Select value={loanAuthData.loan_direction} onValueChange={(v) => setLoanAuthData({ ...loanAuthData, loan_direction: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="making">Trust Making Loan</SelectItem>
                          <SelectItem value="receiving">Trust Receiving Loan</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">{loanAuthData.loan_direction === 'making' ? 'Borrower Name' : 'Lender Name'}</Label>
                      <Input
                        value={loanAuthData.loan_direction === 'making' ? loanAuthData.borrower_name : loanAuthData.lender_name}
                        onChange={(e) => setLoanAuthData({ ...loanAuthData, [loanAuthData.loan_direction === 'making' ? 'borrower_name' : 'lender_name']: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Name"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Loan Amount ($)</Label>
                      <Input type="number" value={loanAuthData.loan_amount} onChange={(e) => setLoanAuthData({ ...loanAuthData, loan_amount: e.target.value })} className="mt-1 input-trust" placeholder="50000" />
                    </div>
                    <div>
                      <Label className="label-trust">Interest Rate</Label>
                      <Input value={loanAuthData.interest_rate} onChange={(e) => setLoanAuthData({ ...loanAuthData, interest_rate: e.target.value })} className="mt-1 input-trust" placeholder="AFR or 5%" />
                    </div>
                    <div>
                      <Label className="label-trust">Term (Months)</Label>
                      <Input type="number" value={loanAuthData.term_months} onChange={(e) => setLoanAuthData({ ...loanAuthData, term_months: e.target.value })} className="mt-1 input-trust" placeholder="60" />
                    </div>
                    <div>
                      <Label className="label-trust">Purpose</Label>
                      <Input value={loanAuthData.loan_purpose} onChange={(e) => setLoanAuthData({ ...loanAuthData, loan_purpose: e.target.value })} className="mt-1 input-trust" placeholder="Home purchase, business capital, etc." />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Collateral Description (if any)</Label>
                      <Input value={loanAuthData.collateral_description} onChange={(e) => setLoanAuthData({ ...loanAuthData, collateral_description: e.target.value })} className="mt-1 input-trust" placeholder="Real property, securities, etc." />
                    </div>
                  </div>
                </div>
              )}

              {/* INSURANCE AUTHORIZATION TEMPLATE */}
              {templateType === 'insurance_authorization' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Insurance Authorization Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Insurance Type</Label>
                      <Select value={insuranceData.insurance_type} onValueChange={(v) => setInsuranceData({ ...insuranceData, insurance_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="property">Property & Casualty</SelectItem>
                          <SelectItem value="liability">Liability</SelectItem>
                          <SelectItem value="life">Life Insurance</SelectItem>
                          <SelectItem value="health">Health Insurance</SelectItem>
                          <SelectItem value="umbrella">Umbrella/Excess</SelectItem>
                          <SelectItem value="professional">Professional Liability</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Action</Label>
                      <Select value={insuranceData.policy_action} onValueChange={(v) => setInsuranceData({ ...insuranceData, policy_action: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="obtain">Obtain New Policy</SelectItem>
                          <SelectItem value="renew">Renew Existing</SelectItem>
                          <SelectItem value="modify">Modify Coverage</SelectItem>
                          <SelectItem value="cancel">Cancel Policy</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Insurance Company</Label>
                      <Input value={insuranceData.insurer_name} onChange={(e) => setInsuranceData({ ...insuranceData, insurer_name: e.target.value })} className="mt-1 input-trust" placeholder="Company name" />
                    </div>
                    <div>
                      <Label className="label-trust">Coverage Amount ($)</Label>
                      <Input type="number" value={insuranceData.coverage_amount} onChange={(e) => setInsuranceData({ ...insuranceData, coverage_amount: e.target.value })} className="mt-1 input-trust" placeholder="1000000" />
                    </div>
                    <div>
                      <Label className="label-trust">Annual Premium ($)</Label>
                      <Input type="number" value={insuranceData.premium_amount} onChange={(e) => setInsuranceData({ ...insuranceData, premium_amount: e.target.value })} className="mt-1 input-trust" placeholder="5000" />
                    </div>
                    <div>
                      <Label className="label-trust">Policy Number (if existing)</Label>
                      <Input value={insuranceData.policy_number} onChange={(e) => setInsuranceData({ ...insuranceData, policy_number: e.target.value })} className="mt-1 input-trust" placeholder="POL-123456" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Coverage Description</Label>
                      <Textarea value={insuranceData.coverage_description} onChange={(e) => setInsuranceData({ ...insuranceData, coverage_description: e.target.value })} className="mt-1" rows={2} placeholder="Describe what is covered" />
                    </div>
                  </div>
                </div>
              )}

              {/* ANNUAL REVIEW TEMPLATE */}
              {templateType === 'annual_review' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Annual Review Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Fiscal Year</Label>
                      <Input value={annualReviewData.fiscal_year} onChange={(e) => setAnnualReviewData({ ...annualReviewData, fiscal_year: e.target.value })} className="mt-1 input-trust" placeholder="2025" />
                    </div>
                    <div>
                      <Label className="label-trust">Investment Return</Label>
                      <Input value={annualReviewData.investment_return} onChange={(e) => setAnnualReviewData({ ...annualReviewData, investment_return: e.target.value })} className="mt-1 input-trust" placeholder="7.5%" />
                    </div>
                    <div>
                      <Label className="label-trust">Total Assets (Year End)</Label>
                      <Input type="number" value={annualReviewData.total_assets} onChange={(e) => setAnnualReviewData({ ...annualReviewData, total_assets: e.target.value })} className="mt-1 input-trust" placeholder="1000000" />
                    </div>
                    <div>
                      <Label className="label-trust">Total Income</Label>
                      <Input type="number" value={annualReviewData.total_income} onChange={(e) => setAnnualReviewData({ ...annualReviewData, total_income: e.target.value })} className="mt-1 input-trust" placeholder="50000" />
                    </div>
                    <div>
                      <Label className="label-trust">Total Expenses</Label>
                      <Input type="number" value={annualReviewData.total_expenses} onChange={(e) => setAnnualReviewData({ ...annualReviewData, total_expenses: e.target.value })} className="mt-1 input-trust" placeholder="10000" />
                    </div>
                    <div>
                      <Label className="label-trust">Total Distributions</Label>
                      <Input type="number" value={annualReviewData.total_distributions} onChange={(e) => setAnnualReviewData({ ...annualReviewData, total_distributions: e.target.value })} className="mt-1 input-trust" placeholder="30000" />
                    </div>
                  </div>
                </div>
              )}

              {/* QUARTERLY REVIEW TEMPLATE */}
              {templateType === 'quarterly_review' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Quarterly Review Details</h2>
                  <div className="grid md:grid-cols-3 gap-4">
                    <div>
                      <Label className="label-trust">Quarter</Label>
                      <Select value={quarterlyReviewData.quarter} onValueChange={(v) => setQuarterlyReviewData({ ...quarterlyReviewData, quarter: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Q1">Q1 (Jan-Mar)</SelectItem>
                          <SelectItem value="Q2">Q2 (Apr-Jun)</SelectItem>
                          <SelectItem value="Q3">Q3 (Jul-Sep)</SelectItem>
                          <SelectItem value="Q4">Q4 (Oct-Dec)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Year</Label>
                      <Input value={quarterlyReviewData.year} onChange={(e) => setQuarterlyReviewData({ ...quarterlyReviewData, year: e.target.value })} className="mt-1 input-trust" placeholder="2026" />
                    </div>
                  </div>
                  <div className="grid md:grid-cols-2 gap-4 mt-4">
                    <div>
                      <Label className="label-trust">Beginning Balance</Label>
                      <Input type="number" value={quarterlyReviewData.beginning_balance} onChange={(e) => setQuarterlyReviewData({ ...quarterlyReviewData, beginning_balance: e.target.value })} className="mt-1 input-trust" placeholder="500000" />
                    </div>
                    <div>
                      <Label className="label-trust">Ending Balance</Label>
                      <Input type="number" value={quarterlyReviewData.ending_balance} onChange={(e) => setQuarterlyReviewData({ ...quarterlyReviewData, ending_balance: e.target.value })} className="mt-1 input-trust" placeholder="510000" />
                    </div>
                    <div>
                      <Label className="label-trust">Income Received</Label>
                      <Input type="number" value={quarterlyReviewData.income_received} onChange={(e) => setQuarterlyReviewData({ ...quarterlyReviewData, income_received: e.target.value })} className="mt-1 input-trust" placeholder="15000" />
                    </div>
                    <div>
                      <Label className="label-trust">Distributions Made</Label>
                      <Input type="number" value={quarterlyReviewData.distributions_made} onChange={(e) => setQuarterlyReviewData({ ...quarterlyReviewData, distributions_made: e.target.value })} className="mt-1 input-trust" placeholder="5000" />
                    </div>
                  </div>
                </div>
              )}

              {/* TRUSTEE COMPENSATION TEMPLATE */}
              {templateType === 'trustee_compensation' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Trustee Compensation Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="md:col-span-2 flex items-center gap-3">
                      <Checkbox checked={trusteeCompData.all_trustees} onCheckedChange={(c) => setTrusteeCompData({ ...trusteeCompData, all_trustees: c })} id="all-trustees" />
                      <Label htmlFor="all-trustees" className="cursor-pointer">Apply to all trustees</Label>
                    </div>
                    {!trusteeCompData.all_trustees && (
                      <div>
                        <Label className="label-trust">Trustee Name</Label>
                        <Input value={trusteeCompData.trustee_name} onChange={(e) => setTrusteeCompData({ ...trusteeCompData, trustee_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith" />
                      </div>
                    )}
                    <div>
                      <Label className="label-trust">Compensation Type</Label>
                      <Select value={trusteeCompData.compensation_type} onValueChange={(v) => setTrusteeCompData({ ...trusteeCompData, compensation_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="annual">Annual Fee</SelectItem>
                          <SelectItem value="hourly">Hourly Rate</SelectItem>
                          <SelectItem value="per_meeting">Per Meeting</SelectItem>
                          <SelectItem value="percentage">% of Assets</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Amount</Label>
                      <Input type="number" value={trusteeCompData.compensation_amount} onChange={(e) => setTrusteeCompData({ ...trusteeCompData, compensation_amount: e.target.value })} className="mt-1 input-trust" placeholder="5000" />
                    </div>
                    <div>
                      <Label className="label-trust">Effective Date</Label>
                      <Input value={trusteeCompData.effective_date} onChange={(e) => setTrusteeCompData({ ...trusteeCompData, effective_date: e.target.value })} className="mt-1 input-trust" placeholder="January 1, 2026" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Compensation Basis/Justification</Label>
                      <Textarea value={trusteeCompData.compensation_basis} onChange={(e) => setTrusteeCompData({ ...trusteeCompData, compensation_basis: e.target.value })} className="mt-1" rows={2} placeholder="Based on comparable trustee fees in the region..." />
                    </div>
                  </div>
                </div>
              )}

              {/* TRUSTEE RESIGNATION TEMPLATE */}
              {templateType === 'trustee_resignation' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Trustee Departure Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Departing Trustee Name</Label>
                      <Input value={trusteeResignData.departing_trustee_name} onChange={(e) => setTrusteeResignData({ ...trusteeResignData, departing_trustee_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith" />
                    </div>
                    <div>
                      <Label className="label-trust">Departure Type</Label>
                      <Select value={trusteeResignData.departure_type} onValueChange={(v) => setTrusteeResignData({ ...trusteeResignData, departure_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="resignation">Resignation</SelectItem>
                          <SelectItem value="removal">Removal</SelectItem>
                          <SelectItem value="death">Death</SelectItem>
                          <SelectItem value="incapacity">Incapacity</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Effective Date</Label>
                      <Input value={trusteeResignData.effective_date} onChange={(e) => setTrusteeResignData({ ...trusteeResignData, effective_date: e.target.value })} className="mt-1 input-trust" placeholder="March 1, 2026" />
                    </div>
                    <div>
                      <Label className="label-trust">Reason (optional)</Label>
                      <Input value={trusteeResignData.departure_reason} onChange={(e) => setTrusteeResignData({ ...trusteeResignData, departure_reason: e.target.value })} className="mt-1 input-trust" placeholder="Personal reasons, relocation, etc." />
                    </div>
                    <div className="md:col-span-2 flex items-center gap-3">
                      <Checkbox checked={trusteeResignData.successor_appointed} onCheckedChange={(c) => setTrusteeResignData({ ...trusteeResignData, successor_appointed: c })} id="successor-appointed" />
                      <Label htmlFor="successor-appointed" className="cursor-pointer">Successor trustee being appointed</Label>
                    </div>
                    {trusteeResignData.successor_appointed && (
                      <div className="md:col-span-2">
                        <Label className="label-trust">Successor Name</Label>
                        <Input value={trusteeResignData.successor_name} onChange={(e) => setTrusteeResignData({ ...trusteeResignData, successor_name: e.target.value })} className="mt-1 input-trust" placeholder="Jane Doe" />
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* BENEFICIARY REQUEST DENIAL TEMPLATE */}
              {templateType === 'beneficiary_request_denial' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Request Denial Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Beneficiary Name</Label>
                      <Input value={denialData.beneficiary_name} onChange={(e) => setDenialData({ ...denialData, beneficiary_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith Jr." />
                    </div>
                    <div>
                      <Label className="label-trust">Request Type</Label>
                      <Select value={denialData.request_type} onValueChange={(v) => setDenialData({ ...denialData, request_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="distribution">Distribution Request</SelectItem>
                          <SelectItem value="loan">Loan Request</SelectItem>
                          <SelectItem value="early_distribution">Early Distribution</SelectItem>
                          <SelectItem value="special_request">Special Request</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Request Amount ($)</Label>
                      <Input type="number" value={denialData.request_amount} onChange={(e) => setDenialData({ ...denialData, request_amount: e.target.value })} className="mt-1 input-trust" placeholder="25000" />
                    </div>
                    <div>
                      <Label className="label-trust">Request Date</Label>
                      <Input value={denialData.request_date} onChange={(e) => setDenialData({ ...denialData, request_date: e.target.value })} className="mt-1 input-trust" placeholder="February 15, 2026" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Request Purpose</Label>
                      <Input value={denialData.request_purpose} onChange={(e) => setDenialData({ ...denialData, request_purpose: e.target.value })} className="mt-1 input-trust" placeholder="Vacation, luxury purchase, etc." />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Reasons for Denial</Label>
                      <div className="space-y-2 mt-1">
                        {denialData.denial_reasons.map((reason, idx) => (
                          <div key={idx} className="flex gap-2">
                            <Input value={reason} onChange={(e) => {
                              const newReasons = [...denialData.denial_reasons];
                              newReasons[idx] = e.target.value;
                              setDenialData({ ...denialData, denial_reasons: newReasons });
                            }} className="input-trust" placeholder="Reason for denial" />
                            {denialData.denial_reasons.length > 1 && (
                              <Button variant="ghost" size="icon" onClick={() => setDenialData({ ...denialData, denial_reasons: denialData.denial_reasons.filter((_, i) => i !== idx) })}>
                                <Trash2 className="w-4 h-4 text-red-500" />
                              </Button>
                            )}
                          </div>
                        ))}
                        <Button variant="ghost" size="sm" onClick={() => setDenialData({ ...denialData, denial_reasons: [...denialData.denial_reasons, ''] })}>
                          <Plus className="w-4 h-4 mr-1" /> Add Reason
                        </Button>
                      </div>
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Alternative Offered (optional)</Label>
                      <Textarea value={denialData.alternative_offered} onChange={(e) => setDenialData({ ...denialData, alternative_offered: e.target.value })} className="mt-1" rows={2} placeholder="Smaller distribution, loan instead, etc." />
                    </div>
                  </div>
                </div>
              )}

              {/* HEMS DISTRIBUTION TEMPLATE */}
              {templateType === 'hems_distribution' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">HEMS Distribution Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Beneficiary Name</Label>
                      <Input value={hemsData.beneficiary_name} onChange={(e) => setHemsData({ ...hemsData, beneficiary_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith Jr." />
                    </div>
                    <div>
                      <Label className="label-trust">HEMS Category</Label>
                      <Select value={hemsData.hems_category} onValueChange={(v) => setHemsData({ ...hemsData, hems_category: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="health">Health (Medical)</SelectItem>
                          <SelectItem value="education">Education</SelectItem>
                          <SelectItem value="maintenance">Maintenance</SelectItem>
                          <SelectItem value="support">Support</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Distribution Amount ($)</Label>
                      <Input type="number" value={hemsData.distribution_amount} onChange={(e) => setHemsData({ ...hemsData, distribution_amount: e.target.value })} className="mt-1 input-trust" placeholder="10000" />
                    </div>
                    <div className="flex items-center gap-3">
                      <Checkbox checked={hemsData.recurring} onCheckedChange={(c) => setHemsData({ ...hemsData, recurring: c })} id="recurring-hems" />
                      <Label htmlFor="recurring-hems" className="cursor-pointer">Recurring Distribution</Label>
                    </div>
                    {hemsData.recurring && (
                      <div>
                        <Label className="label-trust">Frequency</Label>
                        <Select value={hemsData.recurring_frequency} onValueChange={(v) => setHemsData({ ...hemsData, recurring_frequency: v })}>
                          <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="monthly">Monthly</SelectItem>
                            <SelectItem value="quarterly">Quarterly</SelectItem>
                            <SelectItem value="semi-annually">Semi-Annually</SelectItem>
                            <SelectItem value="annually">Annually</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                    <div className="md:col-span-2">
                      <Label className="label-trust">Specific Purpose</Label>
                      <Textarea value={hemsData.specific_purpose} onChange={(e) => setHemsData({ ...hemsData, specific_purpose: e.target.value })} className="mt-1" rows={2} placeholder="Describe the specific HEMS need" />
                    </div>
                  </div>
                </div>
              )}

              {/* BENEFICIARY LOAN TEMPLATE */}
              {templateType === 'beneficiary_loan' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Beneficiary Loan Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Beneficiary Name</Label>
                      <Input value={beneficiaryLoanData.beneficiary_name} onChange={(e) => setBeneficiaryLoanData({ ...beneficiaryLoanData, beneficiary_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith Jr." />
                    </div>
                    <div>
                      <Label className="label-trust">Loan Amount ($)</Label>
                      <Input type="number" value={beneficiaryLoanData.loan_amount} onChange={(e) => setBeneficiaryLoanData({ ...beneficiaryLoanData, loan_amount: e.target.value })} className="mt-1 input-trust" placeholder="50000" />
                    </div>
                    <div>
                      <Label className="label-trust">Interest Rate</Label>
                      <Input value={beneficiaryLoanData.interest_rate} onChange={(e) => setBeneficiaryLoanData({ ...beneficiaryLoanData, interest_rate: e.target.value })} className="mt-1 input-trust" placeholder="AFR or 5%" />
                    </div>
                    <div>
                      <Label className="label-trust">Term (Months)</Label>
                      <Input type="number" value={beneficiaryLoanData.term_months} onChange={(e) => setBeneficiaryLoanData({ ...beneficiaryLoanData, term_months: e.target.value })} className="mt-1 input-trust" placeholder="60" />
                    </div>
                    <div>
                      <Label className="label-trust">Repayment Terms</Label>
                      <Select value={beneficiaryLoanData.repayment_terms} onValueChange={(v) => setBeneficiaryLoanData({ ...beneficiaryLoanData, repayment_terms: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="monthly installments">Monthly Installments</SelectItem>
                          <SelectItem value="quarterly installments">Quarterly Installments</SelectItem>
                          <SelectItem value="annual installments">Annual Installments</SelectItem>
                          <SelectItem value="balloon payment">Balloon at Maturity</SelectItem>
                          <SelectItem value="interest only">Interest Only</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Purpose</Label>
                      <Input value={beneficiaryLoanData.loan_purpose} onChange={(e) => setBeneficiaryLoanData({ ...beneficiaryLoanData, loan_purpose: e.target.value })} className="mt-1 input-trust" placeholder="Home purchase, education, etc." />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Collateral (if any)</Label>
                      <Input value={beneficiaryLoanData.collateral_description} onChange={(e) => setBeneficiaryLoanData({ ...beneficiaryLoanData, collateral_description: e.target.value })} className="mt-1 input-trust" placeholder="Real property, vehicle, etc." />
                    </div>
                  </div>
                </div>
              )}

              {/* ========== BATCH 2 TEMPLATES ========== */}

              {templateType === 'trust_amendment' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Trust Amendment Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Amendment Type</Label>
                      <Select value={amendmentData.amendment_type} onValueChange={(v) => setAmendmentData({ ...amendmentData, amendment_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="modification">Modification of Existing Provision</SelectItem>
                          <SelectItem value="addition">Addition of New Provision</SelectItem>
                          <SelectItem value="deletion">Deletion of Provision</SelectItem>
                          <SelectItem value="restatement">Full Article Restatement</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Article/Section Reference *</Label>
                      <Input value={amendmentData.article_section} onChange={(e) => setAmendmentData({ ...amendmentData, article_section: e.target.value })} className="mt-1 input-trust" placeholder="Article III, Section 2" />
                    </div>
                    <div>
                      <Label className="label-trust">Effective Date</Label>
                      <Input value={amendmentData.effective_date} onChange={(e) => setAmendmentData({ ...amendmentData, effective_date: e.target.value })} className="mt-1 input-trust" placeholder="immediately upon execution" />
                    </div>
                    <div>
                      <Label className="label-trust">Reason for Amendment</Label>
                      <Input value={amendmentData.reason} onChange={(e) => setAmendmentData({ ...amendmentData, reason: e.target.value })} className="mt-1 input-trust" placeholder="Changed family circumstances, tax law changes, etc." />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Current Provision Language *</Label>
                      <Textarea value={amendmentData.current_provision} onChange={(e) => setAmendmentData({ ...amendmentData, current_provision: e.target.value })} className="mt-1" placeholder="Quote the exact current language from the Trust Indenture" rows={4} />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Amended Provision Language *</Label>
                      <Textarea value={amendmentData.amended_provision} onChange={(e) => setAmendmentData({ ...amendmentData, amended_provision: e.target.value })} className="mt-1" placeholder="The new language that will replace the current provision" rows={4} />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'power_of_attorney' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Power of Attorney Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Agent Name *</Label>
                      <Input value={poaData.agent_name} onChange={(e) => setPoaData({ ...poaData, agent_name: e.target.value })} className="mt-1 input-trust" placeholder="Full legal name of agent" />
                    </div>
                    <div>
                      <Label className="label-trust">Scope of Authority</Label>
                      <Select value={poaData.scope} onValueChange={(v) => setPoaData({ ...poaData, scope: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="limited">Limited (Specific Tasks)</SelectItem>
                          <SelectItem value="special">Special (Defined Transactions)</SelectItem>
                          <SelectItem value="general">General (Broad Authority)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Purpose/Description *</Label>
                      <Input value={poaData.purpose} onChange={(e) => setPoaData({ ...poaData, purpose: e.target.value })} className="mt-1 input-trust" placeholder="e.g., execute real estate closing documents, manage bank account" />
                    </div>
                    <div>
                      <Label className="label-trust">Expiration</Label>
                      <Input value={poaData.expiration} onChange={(e) => setPoaData({ ...poaData, expiration: e.target.value })} className="mt-1 input-trust" placeholder="upon completion of transaction, 90 days, etc." />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Powers Granted (one per line)</Label>
                      <Textarea value={poaData.powers_granted.join('\n')} onChange={(e) => setPoaData({ ...poaData, powers_granted: e.target.value.split('\n') })} className="mt-1" placeholder="Execute documents on behalf of the Trust&#10;Access trust bank accounts&#10;Sign closing documents" rows={4} />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'trust_termination' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Trust Termination Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Termination Date *</Label>
                      <Input value={terminationData.termination_date} onChange={(e) => setTerminationData({ ...terminationData, termination_date: e.target.value })} className="mt-1 input-trust" />
                    </div>
                    <div>
                      <Label className="label-trust">Final Accounting Due</Label>
                      <Input value={terminationData.final_accounting_date} onChange={(e) => setTerminationData({ ...terminationData, final_accounting_date: e.target.value })} className="mt-1 input-trust" placeholder="within 60 days" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Reason for Termination *</Label>
                      <Textarea value={terminationData.termination_reason} onChange={(e) => setTerminationData({ ...terminationData, termination_reason: e.target.value })} className="mt-1" placeholder="Trust has accomplished its purposes, all beneficiaries have received distributions, etc." rows={2} />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Distribution Plan *</Label>
                      <Textarea value={terminationData.distribution_plan} onChange={(e) => setTerminationData({ ...terminationData, distribution_plan: e.target.value })} className="mt-1" placeholder="Describe how remaining assets will be distributed to beneficiaries" rows={3} />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Outstanding Obligations</Label>
                      <Textarea value={terminationData.outstanding_obligations} onChange={(e) => setTerminationData({ ...terminationData, outstanding_obligations: e.target.value })} className="mt-1" placeholder="List any debts, taxes, or obligations to be paid before distribution" rows={2} />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'real_estate_purchase' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Real Estate Purchase Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <Label className="label-trust">Property Address *</Label>
                      <Input value={realEstatePurchaseData.property_address} onChange={(e) => setRealEstatePurchaseData({ ...realEstatePurchaseData, property_address: e.target.value })} className="mt-1 input-trust" placeholder="123 Main Street, City, State ZIP" />
                    </div>
                    <div>
                      <Label className="label-trust">Property Type</Label>
                      <Select value={realEstatePurchaseData.property_type} onValueChange={(v) => setRealEstatePurchaseData({ ...realEstatePurchaseData, property_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="residential">Residential</SelectItem>
                          <SelectItem value="commercial">Commercial</SelectItem>
                          <SelectItem value="industrial">Industrial</SelectItem>
                          <SelectItem value="land">Vacant Land</SelectItem>
                          <SelectItem value="mixed_use">Mixed Use</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Purchase Price *</Label>
                      <Input value={realEstatePurchaseData.purchase_price} onChange={(e) => setRealEstatePurchaseData({ ...realEstatePurchaseData, purchase_price: e.target.value })} className="mt-1 input-trust" placeholder="$500,000" />
                    </div>
                    <div>
                      <Label className="label-trust">Financing Method</Label>
                      <Select value={realEstatePurchaseData.financing} onValueChange={(v) => setRealEstatePurchaseData({ ...realEstatePurchaseData, financing: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all cash">All Cash</SelectItem>
                          <SelectItem value="mortgage financing">Mortgage Financing</SelectItem>
                          <SelectItem value="seller financing">Seller Financing</SelectItem>
                          <SelectItem value="mixed">Cash + Financing</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Due Diligence Period</Label>
                      <Input value={realEstatePurchaseData.inspection_period} onChange={(e) => setRealEstatePurchaseData({ ...realEstatePurchaseData, inspection_period: e.target.value })} className="mt-1 input-trust" placeholder="30 days" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Purpose of Acquisition</Label>
                      <Input value={realEstatePurchaseData.purpose} onChange={(e) => setRealEstatePurchaseData({ ...realEstatePurchaseData, purpose: e.target.value })} className="mt-1 input-trust" placeholder="investment and rental income, beneficiary residence, etc." />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'business_interest_acquisition' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Business Interest Acquisition Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Entity Name *</Label>
                      <Input value={businessInterestData.entity_name} onChange={(e) => setBusinessInterestData({ ...businessInterestData, entity_name: e.target.value })} className="mt-1 input-trust" placeholder="ABC Holdings, LLC" />
                    </div>
                    <div>
                      <Label className="label-trust">Entity Type</Label>
                      <Select value={businessInterestData.entity_type} onValueChange={(v) => setBusinessInterestData({ ...businessInterestData, entity_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="LLC">LLC</SelectItem>
                          <SelectItem value="Corporation">Corporation</SelectItem>
                          <SelectItem value="Limited Partnership">Limited Partnership</SelectItem>
                          <SelectItem value="General Partnership">General Partnership</SelectItem>
                          <SelectItem value="S Corporation">S Corporation</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Ownership Percentage *</Label>
                      <Input value={businessInterestData.ownership_percentage} onChange={(e) => setBusinessInterestData({ ...businessInterestData, ownership_percentage: e.target.value })} className="mt-1 input-trust" placeholder="25%" />
                    </div>
                    <div>
                      <Label className="label-trust">Purchase Price *</Label>
                      <Input value={businessInterestData.purchase_price} onChange={(e) => setBusinessInterestData({ ...businessInterestData, purchase_price: e.target.value })} className="mt-1 input-trust" placeholder="$100,000" />
                    </div>
                    <div>
                      <Label className="label-trust">Investment Purpose</Label>
                      <Input value={businessInterestData.purpose} onChange={(e) => setBusinessInterestData({ ...businessInterestData, purpose: e.target.value })} className="mt-1 input-trust" placeholder="diversification, income generation, family business" />
                    </div>
                    <div>
                      <Label className="label-trust">Due Diligence Status</Label>
                      <Input value={businessInterestData.due_diligence} onChange={(e) => setBusinessInterestData({ ...businessInterestData, due_diligence: e.target.value })} className="mt-1 input-trust" placeholder="financial review completed, legal review pending" />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'real_estate_lease' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Real Estate Lease Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <Label className="label-trust">Property Address *</Label>
                      <Input value={realEstateLeaseData.property_address} onChange={(e) => setRealEstateLeaseData({ ...realEstateLeaseData, property_address: e.target.value })} className="mt-1 input-trust" placeholder="123 Main Street, City, State ZIP" />
                    </div>
                    <div>
                      <Label className="label-trust">Tenant Name *</Label>
                      <Input value={realEstateLeaseData.tenant_name} onChange={(e) => setRealEstateLeaseData({ ...realEstateLeaseData, tenant_name: e.target.value })} className="mt-1 input-trust" placeholder="John Doe or ABC Company" />
                    </div>
                    <div>
                      <Label className="label-trust">Lease Term *</Label>
                      <Input value={realEstateLeaseData.lease_term} onChange={(e) => setRealEstateLeaseData({ ...realEstateLeaseData, lease_term: e.target.value })} className="mt-1 input-trust" placeholder="1 year, 3 years, month-to-month" />
                    </div>
                    <div>
                      <Label className="label-trust">Monthly Rent *</Label>
                      <Input value={realEstateLeaseData.monthly_rent} onChange={(e) => setRealEstateLeaseData({ ...realEstateLeaseData, monthly_rent: e.target.value })} className="mt-1 input-trust" placeholder="$2,500" />
                    </div>
                    <div>
                      <Label className="label-trust">Security Deposit</Label>
                      <Input value={realEstateLeaseData.security_deposit} onChange={(e) => setRealEstateLeaseData({ ...realEstateLeaseData, security_deposit: e.target.value })} className="mt-1 input-trust" placeholder="$2,500 (one month's rent)" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Permitted Use</Label>
                      <Input value={realEstateLeaseData.permitted_use} onChange={(e) => setRealEstateLeaseData({ ...realEstateLeaseData, permitted_use: e.target.value })} className="mt-1 input-trust" placeholder="residential occupancy, retail business, office use" />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'fiscal_year_election' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Fiscal Year Election Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Fiscal Year End *</Label>
                      <Select value={fiscalYearData.fiscal_year_end} onValueChange={(v) => setFiscalYearData({ ...fiscalYearData, fiscal_year_end: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="December 31">December 31 (Calendar Year)</SelectItem>
                          <SelectItem value="January 31">January 31</SelectItem>
                          <SelectItem value="March 31">March 31</SelectItem>
                          <SelectItem value="June 30">June 30</SelectItem>
                          <SelectItem value="September 30">September 30</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Election Type</Label>
                      <Select value={fiscalYearData.election_type} onValueChange={(v) => setFiscalYearData({ ...fiscalYearData, election_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="initial">Initial Election</SelectItem>
                          <SelectItem value="change">Change from Prior Year</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Effective Tax Year *</Label>
                      <Input value={fiscalYearData.effective_year} onChange={(e) => setFiscalYearData({ ...fiscalYearData, effective_year: e.target.value })} className="mt-1 input-trust" placeholder="2024" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Reason for Election</Label>
                      <Input value={fiscalYearData.reason} onChange={(e) => setFiscalYearData({ ...fiscalYearData, reason: e.target.value })} className="mt-1 input-trust" placeholder="administrative convenience, alignment with beneficiary tax years, etc." />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'tax_filing_authorization' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Tax Filing Authorization Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Tax Year *</Label>
                      <Input value={taxFilingData.tax_year} onChange={(e) => setTaxFilingData({ ...taxFilingData, tax_year: e.target.value })} className="mt-1 input-trust" placeholder="2023" />
                    </div>
                    <div>
                      <Label className="label-trust">Tax Preparer/CPA *</Label>
                      <Input value={taxFilingData.preparer_name} onChange={(e) => setTaxFilingData({ ...taxFilingData, preparer_name: e.target.value })} className="mt-1 input-trust" placeholder="Smith & Associates CPA" />
                    </div>
                    <div>
                      <Label className="label-trust">Filing Deadline</Label>
                      <Input value={taxFilingData.filing_deadline} onChange={(e) => setTaxFilingData({ ...taxFilingData, filing_deadline: e.target.value })} className="mt-1 input-trust" placeholder="April 15" />
                    </div>
                    <div className="flex items-center gap-2 pt-6">
                      <Checkbox checked={taxFilingData.extension_authorized} onCheckedChange={(checked) => setTaxFilingData({ ...taxFilingData, extension_authorized: checked })} />
                      <Label className="label-trust cursor-pointer">Extension Authorized if Needed</Label>
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Returns to File (one per line)</Label>
                      <Textarea value={taxFilingData.returns_to_file.join('\n')} onChange={(e) => setTaxFilingData({ ...taxFilingData, returns_to_file: e.target.value.split('\n') })} className="mt-1" placeholder="Form 1041 - U.S. Income Tax Return for Estates and Trusts&#10;State fiduciary income tax return&#10;Schedule K-1s for beneficiaries" rows={4} />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'emergency_ratification' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Emergency Action Ratification Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Date of Emergency *</Label>
                      <Input value={emergencyData.action_date} onChange={(e) => setEmergencyData({ ...emergencyData, action_date: e.target.value })} className="mt-1 input-trust" />
                    </div>
                    <div>
                      <Label className="label-trust">Trustee Who Acted *</Label>
                      <Input value={emergencyData.trustee_acting} onChange={(e) => setEmergencyData({ ...emergencyData, trustee_acting: e.target.value })} className="mt-1 input-trust" placeholder="John Smith" />
                    </div>
                    <div>
                      <Label className="label-trust">Type of Emergency *</Label>
                      <Input value={emergencyData.emergency_type} onChange={(e) => setEmergencyData({ ...emergencyData, emergency_type: e.target.value })} className="mt-1 input-trust" placeholder="Property damage, medical emergency, market event, etc." />
                    </div>
                    <div>
                      <Label className="label-trust">Cost Incurred</Label>
                      <Input value={emergencyData.cost_incurred} onChange={(e) => setEmergencyData({ ...emergencyData, cost_incurred: e.target.value })} className="mt-1 input-trust" placeholder="$5,000" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Actions Taken (one per line) *</Label>
                      <Textarea value={emergencyData.actions_taken.join('\n')} onChange={(e) => setEmergencyData({ ...emergencyData, actions_taken: e.target.value.split('\n') })} className="mt-1" placeholder="Authorized emergency repairs&#10;Contacted insurance company&#10;Secured the property" rows={4} />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Outcome/Result</Label>
                      <Input value={emergencyData.outcome} onChange={(e) => setEmergencyData({ ...emergencyData, outcome: e.target.value })} className="mt-1 input-trust" placeholder="the emergency was successfully addressed with minimal Trust loss" />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'conflict_of_interest' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Conflict of Interest Disclosure Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Trustee with Conflict *</Label>
                      <Input value={conflictData.trustee_name} onChange={(e) => setConflictData({ ...conflictData, trustee_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith" />
                    </div>
                    <div>
                      <Label className="label-trust">Type of Conflict</Label>
                      <Select value={conflictData.conflict_type} onValueChange={(v) => setConflictData({ ...conflictData, conflict_type: v })}>
                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="financial_interest">Financial Interest</SelectItem>
                          <SelectItem value="family_relationship">Family Relationship</SelectItem>
                          <SelectItem value="business_relationship">Business Relationship</SelectItem>
                          <SelectItem value="self_dealing">Self-Dealing Transaction</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Disclosure Date</Label>
                      <Input value={conflictData.disclosure_date} onChange={(e) => setConflictData({ ...conflictData, disclosure_date: e.target.value })} className="mt-1 input-trust" />
                    </div>
                    <div className="flex items-center gap-2 pt-6">
                      <Checkbox checked={conflictData.waiver_granted} onCheckedChange={(checked) => setConflictData({ ...conflictData, waiver_granted: checked })} />
                      <Label className="label-trust cursor-pointer">Waiver Granted (Trustee may participate)</Label>
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Related Transaction/Matter *</Label>
                      <Input value={conflictData.related_transaction} onChange={(e) => setConflictData({ ...conflictData, related_transaction: e.target.value })} className="mt-1 input-trust" placeholder="Sale of property to trustee's family member" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Description of Conflict *</Label>
                      <Textarea value={conflictData.description} onChange={(e) => setConflictData({ ...conflictData, description: e.target.value })} className="mt-1" placeholder="Describe the nature of the conflict and how it relates to the transaction" rows={3} />
                    </div>
                    {conflictData.waiver_granted && (
                      <div className="md:col-span-2">
                        <Label className="label-trust">Conditions of Waiver</Label>
                        <Input value={conflictData.conditions} onChange={(e) => setConflictData({ ...conflictData, conditions: e.target.value })} className="mt-1 input-trust" placeholder="None, or specify conditions" />
                      </div>
                    )}
                  </div>
                </div>
              )}

              {templateType === 'initial_trustee_meeting' && (
                <div className="space-y-6">
                  <div className="card-trust corner-mark p-6">
                    <h2 className="font-serif text-xl text-navy mb-4">Initial Meeting Details</h2>
                    <p className="text-sm text-muted-foreground mb-6">
                      This is your trust's first organizational meeting. It covers one-time actions — accepting trusteeship, opening bank accounts, confirming your EIN, and establishing the trust's foundation.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label className="label-trust">Bank Name</Label>
                        <Input
                          value={formData.bank_name || ''}
                          onChange={(e) => setFormData({ ...formData, bank_name: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="e.g., Chase, Wells Fargo"
                        />
                      </div>
                      <div>
                        <Label className="label-trust">Initial Deposit Amount</Label>
                        <Input
                          value={formData.initial_deposit || ''}
                          onChange={(e) => setFormData({ ...formData, initial_deposit: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="e.g., $10,000"
                        />
                      </div>
                      <div>
                        <Label className="label-trust">Meeting Location</Label>
                        <Input
                          value={formData.meeting_location || ''}
                          onChange={(e) => setFormData({ ...formData, meeting_location: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="e.g., Portland, Oregon"
                        />
                      </div>
                      <div>
                        <Label className="label-trust">Meeting Time</Label>
                        <Input
                          value={formData.meeting_time || ''}
                          onChange={(e) => setFormData({ ...formData, meeting_time: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="e.g., 10:00 AM"
                        />
                      </div>
                      <div>
                        <Label className="label-trust">Principal Place of Administration</Label>
                        <Input
                          value={formData.principal_place || ''}
                          onChange={(e) => setFormData({ ...formData, principal_place: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="Defaults to meeting location if blank"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="card-trust corner-mark p-6">
                    <h2 className="font-serif text-xl text-navy mb-4">Fiscal Year</h2>
                    <div>
                      <Label className="label-trust">Fiscal Year End</Label>
                      <select
                        value={formData.fiscal_year_end || 'December 31'}
                        onChange={(e) => setFormData({ ...formData, fiscal_year_end: e.target.value })}
                        className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm input-trust"
                      >
                        <option value="December 31">December 31 (Calendar Year)</option>
                        <option value="March 31">March 31</option>
                        <option value="June 30">June 30</option>
                        <option value="September 30">September 30</option>
                      </select>
                      <p className="text-xs text-muted-foreground mt-1">Most trusts use a calendar year (Dec 31). Consult your tax advisor before choosing a different fiscal year.</p>
                    </div>
                  </div>

                  <div className="card-trust corner-mark p-6">
                    <h2 className="font-serif text-xl text-navy mb-4">Trustee Compensation</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label className="label-trust">Compensation Type</Label>
                        <select
                          value={formData.compensation_type || 'none'}
                          onChange={(e) => setFormData({ ...formData, compensation_type: e.target.value })}
                          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm input-trust"
                        >
                          <option value="none">No Compensation</option>
                          <option value="fixed">Fixed Annual Amount</option>
                          <option value="percentage">Percentage of Corpus</option>
                        </select>
                      </div>
                      {formData.compensation_type && formData.compensation_type !== 'none' && (
                        <div>
                          <Label className="label-trust">
                            {formData.compensation_type === 'fixed' ? 'Annual Amount' : 'Percentage (%)'}
                          </Label>
                          <Input
                            value={formData.compensation_amount || ''}
                            onChange={(e) => setFormData({ ...formData, compensation_amount: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder={formData.compensation_type === 'fixed' ? 'e.g., $5,000' : 'e.g., 1'}
                          />
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="card-trust corner-mark p-6">
                    <h2 className="font-serif text-xl text-navy mb-4">Include Resolutions</h2>
                    <p className="text-sm text-muted-foreground mb-4">
                      Select which resolutions to include. All are recommended for a new trust's first meeting.
                    </p>
                    <div className="space-y-3">
                      {[
                        { key: 'accept_trusteeship', label: 'Adoption of Trust & Accept Trusteeship', desc: 'Acknowledge the Declaration of Trust and accept your role as Trustee' },
                        { key: 'acknowledge_fiduciary_duties', label: 'Fiduciary Duties Acknowledgment', desc: 'Formally acknowledge duties of Loyalty, Prudence, Impartiality, Obedience, Recordkeeping, and Confidentiality' },
                        { key: 'authorize_ein', label: 'EIN Confirmation / Authorization', desc: 'Confirm your EIN or authorize obtaining one' },
                        { key: 'accept_initial_property', label: 'Accept Initial Trust Property', desc: 'Acknowledge authority to accept the initial corpus from the Settlor' },
                        { key: 'authorize_insurance', label: 'Insurance Authorization', desc: 'Authorize trustee liability and property insurance' },
                        { key: 'authorize_professional_services', label: 'Professional Services Authorization', desc: 'Authorize retaining attorneys, accountants, and tax advisors' },
                        { key: 'designate_record_keeper', label: 'Designate Record Keeper', desc: 'Assign responsibility for maintaining trust records' },
                        { key: 'adopt_governance_standards', label: 'Governance Standards', desc: 'Adopt regular meetings, minutes requirements, resolution standards, annual review' },
                        { key: 'ratify_prior_actions', label: 'Ratification of Prior Actions', desc: 'Ratify all actions taken during trust formation' },
                      ].map(item => (
                        <label key={item.key} className="flex items-start gap-3 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={formData[item.key] !== false}
                            onChange={(e) => setFormData({ ...formData, [item.key]: e.target.checked })}
                            className="mt-1 rounded border-border"
                          />
                          <div>
                            <div className="font-medium text-navy">{item.label}</div>
                            <div className="text-sm text-muted-foreground">{item.desc}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              )}
              {templateType === 'general_meeting' && (
                <div className="card-trust corner-mark p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="font-serif text-xl text-navy">Resolutions</h2>
                    <Button type="button" variant="outline" onClick={handleAddResolution}>
                      <Plus className="w-4 h-4 mr-2" />
                      Add Resolution
                    </Button>
                  </div>
                  
                  {resolutions.map((res, index) => (
                    <div key={index} className="mb-6 p-4 border border-border rounded-lg">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="font-medium">Resolution {index + 1}</h3>
                        {resolutions.length > 1 && (
                          <Button type="button" variant="ghost" size="sm" onClick={() => handleRemoveResolution(index)}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        )}
                      </div>
                      <div className="space-y-4">
                        <div>
                          <Label className="label-trust">Title/Subject</Label>
                          <Input
                            value={res.title}
                            onChange={(e) => {
                              const newRes = [...resolutions];
                              newRes[index].title = e.target.value;
                              setResolutions(newRes);
                            }}
                            className="mt-1 input-trust"
                            placeholder="e.g., Approval of Annual Report"
                          />
                        </div>
                        <div>
                          <Label className="label-trust">WHEREAS Clause(s)</Label>
                          <Textarea
                            value={res.whereas_clauses[0]}
                            onChange={(e) => {
                              const newRes = [...resolutions];
                              newRes[index].whereas_clauses = [e.target.value];
                              setResolutions(newRes);
                            }}
                            className="mt-1"
                            placeholder="State the background, circumstances, or reason for the resolution"
                            rows={2}
                          />
                        </div>
                        <div>
                          <Label className="label-trust">BE IT RESOLVED Clause(s)</Label>
                          <Textarea
                            value={res.resolved_clauses[0]}
                            onChange={(e) => {
                              const newRes = [...resolutions];
                              newRes[index].resolved_clauses = [e.target.value];
                              setResolutions(newRes);
                            }}
                            className="mt-1"
                            placeholder="State the specific action, decision, or authorization"
                            rows={2}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Generate Button */}
              <div className="flex justify-end gap-3">
                <Button variant="outline" onClick={() => navigate(searchParams.get('from') === 'create' ? '/minutes/create' : '/minutes/templates')}>
                  Cancel
                </Button>
                <Button className="btn-primary" onClick={handleGeneratePreview} disabled={loading}>
                  <Eye className="w-4 h-4 mr-2" />
                  {loading ? 'Generating...' : 'Generate Preview'}
                </Button>
              </div>
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
