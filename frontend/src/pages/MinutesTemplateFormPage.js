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
import { showError } from '../utils/errors';
import {
  ArrowLeft,
  Plus,
  Trash2,
  FileText,
  Download,
  Save,
  Eye,
  Landmark
} from 'lucide-react';
import { format } from 'date-fns';

// Extracted sub-components
import {
  formatCurrency,
  parseCurrencyInput,
  TEMPLATE_TITLES,
} from './minutesTemplateForm/constants';
import { MeetingInfoFields } from './minutesTemplateForm/MeetingInfoFields';
import {
  DistributionFields,
  PropertyFields,
  DispositionFields,
  TrusteeAppointmentFields,
  BeneficiaryDesignationFields,
  BankAccountFields,
  SitusFields,
  BenevolenceFields,
} from './minutesTemplateForm/FormSections1';
import {
  InvestmentPolicyFields,
  LoanAuthFields,
  InsuranceFields,
  AnnualReviewFields,
  QuarterlyReviewFields,
  TrusteeCompensationFields,
  TrusteeResignationFields,
  DenialFields,
  HemsFields,
  DistributionNoticeFields,
  BeneficiaryLoanFields,
} from './minutesTemplateForm/FormSections2';
import { buildTemplateData } from './minutesTemplateForm/templateDataBuilders';
import { useTrustEntityData } from './minutesTemplateForm/useTrustEntityData';

export default function MinutesTemplateFormPage() {
  const navigate = useNavigate();
  const { templateType } = useParams();
  const [searchParams] = useSearchParams();
  const { selectedTrust, isReadOnly } = useAuth();

  // ----- Read-only guard -----
  // Redirect read-only (inactive subscription) users to the minutes list
  // instead of letting them hit the generate form and get a 403 error.
  useEffect(() => {
    if (isReadOnly) {
      toast.error('Your subscription is inactive. Subscribe to generate minutes.');
      navigate('/minutes', { replace: true });
    }
  }, [isReadOnly, navigate]);

  const [loading, setLoading] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [generatedDoc, setGeneratedDoc] = useState('');
  const [minutesId, setMinutesId] = useState(null);

  // Common fields
  const [formData, setFormData] = useState({
    minute_number: `${new Date().getFullYear()}-001`,
    meeting_date: format(new Date(), 'yyyy-MM-dd'),
    meeting_time: '10:00',
    meeting_type: 'unanimous_written_consent',
    meeting_location: '',
    trustees_present: [],
    trust_formation_date: '',
    adjournment_time: '10:30'
  });

  // Distribution fields
  const [distributionData, setDistributionData] = useState({
    distribution_total: '',
    distribution_items: [{ beneficiary_name: '', amount: '', percentage: '' }],
    distribution_date: format(new Date(), 'yyyy-MM-dd'),
    distribution_characterization: 'income'
  });

  // Property acceptance fields
  const [propertyData, setPropertyData] = useState({
    grantor_name: '',
    property_description: '',
    property_value: '',
    property_identifier: '',
    property_location: '',
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

  // Beneficiary distribution notice fields
  const [distributionNoticeData, setDistributionNoticeData] = useState({
    beneficiary_name: '',
    distribution_amount: '',
    distribution_purpose: '',
    distribution_date: format(new Date(), 'yyyy-MM-dd'),
    trustee_name: ''
  });

  // Distribution evaluation fields
  const [evalData, setEvalData] = useState({
    beneficiary_name: '',
    requested_amount: '',
    request_purpose: '',
    hems_category: 'education',
    beneficiary_financial_situation: '',
    beneficiary_other_resources: '',
    past_distributions_note: ''
  });
  const [evalResult, setEvalResult] = useState(null);
  const [evalLoading, setEvalLoading] = useState(false);

  // Spending authorization fields
  const [spendingAuthData, setSpendingAuthData] = useState({
    expenditure_amount: '',
    expenditure_date: format(new Date(), 'yyyy-MM-dd'),
    expenditure_purpose: '',
    expenditure_vendor: '',
    expenditure_source_account: ''
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

  // Trust entity data + Schedule A assets via extracted hook
  const {
    trustEntity,
    trustEntityLoading,
    scheduleAAssets,
    loadingAssets,
    preFillTrusteeNames,
  } = useTrustEntityData({
    selectedTrust,
    templateType,
    searchParams,
    setFormData,
    setBankData,
    setPropertyData,
    setDispositionData,
    setTrusteeCompData,
    setTrusteeResignData,
    setConflictData,
    setEmergencyData,
    setDistributionNoticeData,
  });

  // Pre-fill trustee names in all minutes template forms when trustees_present is populated
  useEffect(() => {
    const trustees = formData.trustees_present.filter(t => t.trim());
    if (trustees.length === 0) return;
    preFillTrusteeNames(trustees);
  }, [formData.trustees_present]);

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

  const handleEvaluateDistribution = async () => {
    if (!selectedTrust) {
      toast.error('Please select a trust');
      return;
    }
    if (!evalData.beneficiary_name || !evalData.requested_amount) {
      toast.error('Beneficiary name and requested amount are required');
      return;
    }

    setEvalLoading(true);
    setEvalResult(null);
    try {
      const message = `I need to evaluate a distribution request. Beneficiary: ${evalData.beneficiary_name}. Requested amount: $${evalData.requested_amount}. Purpose: ${evalData.request_purpose || 'Not specified'}. HEMS category: ${evalData.hems_category}. Beneficiary's financial situation: ${evalData.beneficiary_financial_situation || 'Not specified'}. Beneficiary's other resources: ${evalData.beneficiary_other_resources || 'Not specified'}. Note on past distributions: ${evalData.past_distributions_note || 'None'}. Should I approve this distribution?`;

      const response = await fetchWithAuth('/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          trust_id: selectedTrust.trust_id
        })
      });

      if (response.ok) {
        const result = await response.json();
        setEvalResult(result);
        toast.success('Evaluation complete');
      } else {
        const error = await response.json();
        showError(toast, new Error(error.detail || 'Failed to evaluate distribution'), { operation: 'evaluate', page: 'MinutesTemplateForm' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'evaluate', page: 'MinutesTemplateForm' });
    } finally {
      setEvalLoading(false);
    }
  };

  const handleGeneratePreview = async () => {
    if (!selectedTrust) {
      toast.error('Please select a trust');
      return;
    }

    setLoading(true);
    try {
      const templateData = buildTemplateData(templateType, {
        formData,
        trustEntity,
        distributionData,
        propertyData,
        dispositionData,
        trusteeData,
        beneficiaryData,
        bankData,
        situsData,
        benevolenceData,
        investmentPolicyData,
        loanAuthData,
        insuranceData,
        annualReviewData,
        quarterlyReviewData,
        trusteeCompData,
        trusteeResignData,
        denialData,
        hemsData,
        distributionNoticeData,
        beneficiaryLoanData,
        spendingAuthData,
        evalData,
        amendmentData,
        poaData,
        terminationData,
        realEstatePurchaseData,
        businessInterestData,
        realEstateLeaseData,
        fiscalYearData,
        taxFilingData,
        emergencyData,
        conflictData,
        resolutions,
      });

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
        showError(toast, new Error(error.detail || 'Failed to generate minutes'), { operation: 'generate', page: 'MinutesTemplateForm' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'generate', page: 'MinutesTemplateForm' });
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
        const fromOnboarding = searchParams.get('source') === 'onboarding';
        navigate(fromOnboarding ? '/dashboard' : '/minutes');
      } else {
        showError(toast, new Error('Failed to save minutes. Please try again. If the problem continues, contact support@trustoffice.app.'), { operation: 'save', page: 'MinutesTemplateForm' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'save', page: 'MinutesTemplateForm' });
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
      showError(toast, error, { operation: 'download', page: 'MinutesTemplateForm' });
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content dot-grid">
          <div className="page-container">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Select a trust to create minutes</p>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Header */}
          <div className="mb-8">
            <Button
              variant="ghost"
              className="mb-4 text-muted-foreground hover:text-navy font-mono text-xs uppercase tracking-widest"
              onClick={() => previewMode ? setPreviewMode(false) : navigate(searchParams.get('source') === 'onboarding' ? '/dashboard' : searchParams.get('from') === 'create' ? '/minutes/create' : '/minutes/templates')}
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
              {previewMode ? 'Back to Form' : searchParams.get('source') === 'onboarding' ? 'Back to Dashboard' : searchParams.get('from') === 'create' ? 'Back to Create' : 'Back to Templates'}
            </Button>
            <h1 className="font-serif text-3xl lg:text-4xl text-navy mb-2">
              {TEMPLATE_TITLES[templateType] || 'Create Minutes'}
            </h1>
            <p className="inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-widest text-navy/40 dark:text-gold/40 mt-1">
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
              {/* Common Fields — Meeting Information */}
              <MeetingInfoFields
                formData={formData}
                setFormData={setFormData}
                templateType={templateType}
                trusteesPresent={formData.trustees_present}
                onAddTrustee={handleAddTrustee}
                onRemoveTrustee={handleRemoveTrustee}
                onTrusteeChange={handleTrusteeChange}
              />

              {/* Template-specific fields */}
              {templateType === 'distribution_to_beneficiaries' && (
                <DistributionFields
                  data={distributionData}
                  setData={setDistributionData}
                  onAddItem={handleAddDistributionItem}
                  onRemoveItem={handleRemoveDistributionItem}
                  onItemChange={handleDistributionItemChange}
                />
              )}

              {(templateType === 'acceptance_of_property' || templateType === 'bill_of_sale' || templateType === 'assignment_of_personal_property' || templateType === 'general_assignment') && (
                <PropertyFields
                  data={propertyData}
                  setData={setPropertyData}
                  templateType={templateType}
                />
              )}

              {templateType === 'disposition_of_asset' && (
                <DispositionFields
                  data={dispositionData}
                  setData={setDispositionData}
                  scheduleAAssets={scheduleAAssets}
                  loadingAssets={loadingAssets}
                />
              )}

              {(templateType === 'appointment_additional_trustee' || templateType === 'appointment_successor_trustee') && (
                <TrusteeAppointmentFields
                  data={trusteeData}
                  setData={setTrusteeData}
                  templateType={templateType}
                />
              )}

              {templateType === 'designation_of_beneficiaries' && (
                <BeneficiaryDesignationFields
                  data={beneficiaryData}
                  setData={setBeneficiaryData}
                />
              )}

              {templateType === 'bank_account_authorization' && (
                <BankAccountFields
                  data={bankData}
                  setData={setBankData}
                />
              )}

              {templateType === 'change_of_situs' && (
                <SitusFields
                  data={situsData}
                  setData={setSitusData}
                />
              )}

              {templateType === 'benevolence_approval' && (
                <BenevolenceFields
                  data={benevolenceData}
                  setData={setBenevolenceData}
                />
              )}

              {/* INVESTMENT POLICY TEMPLATE */}
              {templateType === 'investment_policy' && (
                <InvestmentPolicyFields
                  data={investmentPolicyData}
                  setData={setInvestmentPolicyData}
                />
              )}

              {/* LOAN AUTHORIZATION TEMPLATE */}
              {templateType === 'loan_authorization' && (
                <LoanAuthFields
                  data={loanAuthData}
                  setData={setLoanAuthData}
                />
              )}

              {/* INSURANCE AUTHORIZATION TEMPLATE */}
              {templateType === 'insurance_authorization' && (
                <InsuranceFields
                  data={insuranceData}
                  setData={setInsuranceData}
                />
              )}

              {/* ANNUAL REVIEW TEMPLATE */}
              {templateType === 'annual_review' && (
                <AnnualReviewFields
                  data={annualReviewData}
                  setData={setAnnualReviewData}
                />
              )}

              {/* QUARTERLY REVIEW TEMPLATE */}
              {templateType === 'quarterly_review' && (
                <QuarterlyReviewFields
                  data={quarterlyReviewData}
                  setData={setQuarterlyReviewData}
                />
              )}

              {/* TRUSTEE COMPENSATION TEMPLATE */}
              {templateType === 'trustee_compensation' && (
                <TrusteeCompensationFields
                  data={trusteeCompData}
                  setData={setTrusteeCompData}
                />
              )}

              {/* TRUSTEE RESIGNATION TEMPLATE */}
              {templateType === 'trustee_resignation' && (
                <TrusteeResignationFields
                  data={trusteeResignData}
                  setData={setTrusteeResignData}
                  trusteesPresent={formData.trustees_present}
                />
              )}

              {/* BENEFICIARY REQUEST DENIAL TEMPLATE */}
              {templateType === 'beneficiary_request_denial' && (
                <DenialFields
                  data={denialData}
                  setData={setDenialData}
                />
              )}

              {/* HEMS DISTRIBUTION TEMPLATE */}
              {templateType === 'hems_distribution' && (
                <HemsFields
                  data={hemsData}
                  setData={setHemsData}
                />
              )}

              {/* BENEFICIARY DISTRIBUTION NOTICE TEMPLATE */}
              {templateType === 'beneficiary_distribution_notice' && (
                <DistributionNoticeFields
                  data={distributionNoticeData}
                  setData={setDistributionNoticeData}
                />
              )}

              {/* BENEFICIARY LOAN TEMPLATE */}
              {templateType === 'beneficiary_loan' && (
                <BeneficiaryLoanFields
                  data={beneficiaryLoanData}
                  setData={setBeneficiaryLoanData}
                />
              )}

              {/* ========== UNEXTRACTED SECTIONS (kept inline) ========== */}

              {templateType === 'evaluate_distribution' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Distribution Request Details</h2>
                  <p className="text-sm text-muted-foreground mb-4">
                    Enter the details of a beneficiary's distribution request. The AI assistant will evaluate it against your trust document and trust law, then provide a recommendation.
                  </p>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Beneficiary Name</Label>
                      <Input value={evalData.beneficiary_name} onChange={(e) => setEvalData({ ...evalData, beneficiary_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith Jr." />
                    </div>
                    <div>
                      <Label className="label-trust">Requested Amount ($)</Label>
                      <Input type="text" inputMode="numeric" value={formatCurrency(evalData.requested_amount)} onChange={(e) => setEvalData({ ...evalData, requested_amount: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$50,000" />
                    </div>
                    <div>
                      <Label className="label-trust">HEMS Category</Label>
                      <Select value={evalData.hems_category} onValueChange={(v) => setEvalData({ ...evalData, hems_category: v })}>
                        <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="health">Health (Medical)</SelectItem>
                          <SelectItem value="education">Education</SelectItem>
                          <SelectItem value="maintenance">Maintenance</SelectItem>
                          <SelectItem value="support">Support</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Purpose of Request</Label>
                      <Textarea value={evalData.request_purpose} onChange={(e) => setEvalData({ ...evalData, request_purpose: e.target.value })} className="mt-1" rows={2} placeholder="Fall semester tuition at State University" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Beneficiary's Financial Situation (optional)</Label>
                      <Textarea value={evalData.beneficiary_financial_situation} onChange={(e) => setEvalData({ ...evalData, beneficiary_financial_situation: e.target.value })} className="mt-1" rows={2} placeholder="Annual income, savings, other assets, dependents" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Other Resources Available to Beneficiary (optional)</Label>
                      <Input value={evalData.beneficiary_other_resources} onChange={(e) => setEvalData({ ...evalData, beneficiary_other_resources: e.target.value })} className="mt-1 input-trust" placeholder="Scholarships, parental support, personal savings" />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Notes on Past Distributions (optional)</Label>
                      <Textarea value={evalData.past_distributions_note} onChange={(e) => setEvalData({ ...evalData, past_distributions_note: e.target.value })} className="mt-1" rows={2} placeholder="Previous distributions to this beneficiary or others for equity reference" />
                    </div>
                  </div>

                  <div className="mt-6">
                    <Button className="btn-gold" onClick={handleEvaluateDistribution} disabled={evalLoading}>
                      {evalLoading ? 'Evaluating...' : 'Evaluate Request'}
                    </Button>
                  </div>

                  {evalResult && (
                    <div className="mt-6 border border-navy/10 p-4">
                      <h3 className="font-serif text-lg text-navy mb-3 pb-2 border-b border-navy/10">AI Evaluation Result</h3>
                      {evalResult.message && (
                        <div className="text-sm text-navy whitespace-pre-wrap mb-4">
                          {typeof evalResult.message === 'string' 
                            ? evalResult.message 
                            : evalResult.message.content || JSON.stringify(evalResult.message)}
                        </div>
                      )}
                      {evalResult.message?.citation_note && (
                        <div className="text-xs text-muted-foreground border-t border-navy/10 pt-3 mt-3">
                          <span className="font-semibold">Basis: </span>{evalResult.message.citation_note}
                        </div>
                      )}
                      {evalResult.message?.unknown_note && (
                        <div className="text-xs text-muted-foreground pt-2">
                          <span className="font-semibold">Unknowns: </span>{evalResult.message.unknown_note}
                        </div>
                      )}
                      {evalResult.message?.caveat && (
                        <div className="text-xs text-gold pt-2">
                          <span className="font-semibold">Caveat: </span>{evalResult.message.caveat}
                        </div>
                      )}
                      {evalResult.citation_note && !evalResult.message?.citation_note && (
                        <div className="text-xs text-muted-foreground border-t border-navy/10 pt-3 mt-3">
                          <span className="font-semibold">Basis: </span>{evalResult.citation_note}
                        </div>
                      )}
                      {evalResult.unknown_note && !evalResult.message?.unknown_note && (
                        <div className="text-xs text-muted-foreground pt-2">
                          <span className="font-semibold">Unknowns: </span>{evalResult.unknown_note}
                        </div>
                      )}
                      {evalResult.caveat && !evalResult.message?.caveat && (
                        <div className="text-xs text-gold pt-2">
                          <span className="font-semibold">Caveat: </span>{evalResult.caveat}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {templateType === 'spending_authorization' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Expenditure Details</h2>
                  <p className="text-sm text-muted-foreground mb-4">
                    Document trustee approval of an expenditure that exceeds the spending threshold established in the trust's governance policy.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Expenditure Amount *</Label>
                      <Input
                        type="text"
                        inputMode="numeric"
                        value={formatCurrency(spendingAuthData.expenditure_amount)}
                        onChange={(e) => setSpendingAuthData({ ...spendingAuthData, expenditure_amount: parseCurrencyInput(e.target.value) })}
                        className="mt-1 input-trust"
                        placeholder="$5,000"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Expenditure Date *</Label>
                      <Input
                        type="date"
                        value={spendingAuthData.expenditure_date}
                        onChange={(e) => setSpendingAuthData({ ...spendingAuthData, expenditure_date: e.target.value })}
                        className="mt-1 input-trust"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Purpose of Expenditure *</Label>
                      <Textarea
                        value={spendingAuthData.expenditure_purpose}
                        onChange={(e) => setSpendingAuthData({ ...spendingAuthData, expenditure_purpose: e.target.value })}
                        className="mt-1"
                        placeholder="Describe the purpose and necessity of this expenditure"
                        rows={3}
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Vendor/Payee</Label>
                      <Input
                        value={spendingAuthData.expenditure_vendor}
                        onChange={(e) => setSpendingAuthData({ ...spendingAuthData, expenditure_vendor: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., ABC Contractors, LLC"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Source Account</Label>
                      <Input
                        value={spendingAuthData.expenditure_source_account}
                        onChange={(e) => setSpendingAuthData({ ...spendingAuthData, expenditure_source_account: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., Trust Checking ****1234"
                      />
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'trust_amendment' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Trust Amendment Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Amendment Type</Label>
                      <Select value={amendmentData.amendment_type} onValueChange={(v) => setAmendmentData({ ...amendmentData, amendment_type: v })}>
                        <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
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
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Power of Attorney Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Agent Name *</Label>
                      <Input value={poaData.agent_name} onChange={(e) => setPoaData({ ...poaData, agent_name: e.target.value })} className="mt-1 input-trust" placeholder="Full legal name of agent" />
                    </div>
                    <div>
                      <Label className="label-trust">Scope of Authority</Label>
                      <Select value={poaData.scope} onValueChange={(v) => setPoaData({ ...poaData, scope: v })}>
                        <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
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
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Trust Termination Details</h2>
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
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Real Estate Purchase Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <Label className="label-trust">Property Address *</Label>
                      <Input value={realEstatePurchaseData.property_address} onChange={(e) => setRealEstatePurchaseData({ ...realEstatePurchaseData, property_address: e.target.value })} className="mt-1 input-trust" placeholder="123 Main Street, City, State ZIP" />
                    </div>
                    <div>
                      <Label className="label-trust">Property Type</Label>
                      <Select value={realEstatePurchaseData.property_type} onValueChange={(v) => setRealEstatePurchaseData({ ...realEstatePurchaseData, property_type: v })}>
                        <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
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
                        <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
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
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Business Interest Acquisition Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Entity Name *</Label>
                      <Input value={businessInterestData.entity_name} onChange={(e) => setBusinessInterestData({ ...businessInterestData, entity_name: e.target.value })} className="mt-1 input-trust" placeholder="ABC Holdings, LLC" />
                    </div>
                    <div>
                      <Label className="label-trust">Entity Type</Label>
                      <Select value={businessInterestData.entity_type} onValueChange={(v) => setBusinessInterestData({ ...businessInterestData, entity_type: v })}>
                        <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
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
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Real Estate Lease Details</h2>
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
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Fiscal Year Election Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Fiscal Year End *</Label>
                      <Select value={fiscalYearData.fiscal_year_end} onValueChange={(v) => setFiscalYearData({ ...fiscalYearData, fiscal_year_end: v })}>
                        <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
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
                        <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
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
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Tax Filing Authorization Details</h2>
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
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Emergency Action Ratification Details</h2>
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
                  <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Conflict of Interest Disclosure Details</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Trustee with Conflict *</Label>
                      <Input value={conflictData.trustee_name} onChange={(e) => setConflictData({ ...conflictData, trustee_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith" />
                    </div>
                    <div>
                      <Label className="label-trust">Type of Conflict</Label>
                      <Select value={conflictData.conflict_type} onValueChange={(v) => setConflictData({ ...conflictData, conflict_type: v })}>
                        <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
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
                    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Meeting Details</h2>
                    <p className="text-sm text-muted-foreground mb-6">
                      This is your trust's first organizational meeting. It covers one-time actions, accepting trusteeship, confirming your EIN, and establishing the trust's foundation.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                          type="time"
                          value={formData.meeting_time || ''}
                          onChange={(e) => setFormData({ ...formData, meeting_time: e.target.value })}
                          className="mt-1 input-trust"
                        />
                      </div>
                      <div className="md:col-span-2">
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
                    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Bank Information</h2>
                    <p className="text-sm text-muted-foreground mb-6">
                      The trust will open its bank account and accept the initial deposit at this meeting.
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
                    </div>
                  </div>

                  <div className="card-trust corner-mark p-6">
                    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Fiscal Year</h2>
                    <div>
                      <Label className="label-trust">Fiscal Year End</Label>
                      <select
                        value={formData.fiscal_year_end || 'December 31'}
                        onChange={(e) => setFormData({ ...formData, fiscal_year_end: e.target.value })}
                        className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm input-trust"
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
                    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Trustee Compensation</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label className="label-trust">Compensation Type</Label>
                        <select
                          value={formData.compensation_type || 'none'}
                          onChange={(e) => setFormData({ ...formData, compensation_type: e.target.value })}
                          className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm input-trust"
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
                    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Include Resolutions</h2>
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
                    <div key={index} className="mb-6 p-4 border border-border rounded">
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
                <Button variant="outline" onClick={() => navigate(searchParams.get('source') === 'onboarding' ? '/dashboard' : searchParams.get('from') === 'create' ? '/minutes/create' : '/minutes/templates')}>
                  Cancel
                </Button>
                {templateType !== 'evaluate_distribution' && (
                  <Button className="btn-primary" onClick={handleGeneratePreview} disabled={loading || trustEntityLoading}>
                    <Eye className="w-4 h-4 mr-2" />
                    {loading ? 'Generating...' : 'Generate Preview'}
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
