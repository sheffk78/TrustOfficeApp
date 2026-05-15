import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import {
  ArrowLeft,
  ArrowRight,
  Calendar as CalendarIcon,
  ListChecks,
  FileText,
  CheckCircle,
  Loader2
} from 'lucide-react';
import { format } from 'date-fns';

import Step1TemplatePicker from './Step1TemplatePicker';
import Step2FormBuilder from './Step2FormBuilder';
import Step3ReviewAndSave from './Step3ReviewAndSave';
import { useMinutesAutosave } from './useMinutesAutosave';

const STEPS = [
  { id: 1, label: 'Template', icon: CalendarIcon },
  { id: 2, label: 'Details', icon: ListChecks },
  { id: 3, label: 'Review & Save', icon: CheckCircle }
];

// Quick Minutes types use the AI-first form
const QUICK_TYPES = new Set(['annual_review', 'quarterly_review', 'general_meeting']);

// Template display titles (for section names, review, etc.)
const TEMPLATE_TITLES = {
  'initial_trustee_meeting': 'Initial Trustee Meeting',
  'general_meeting': 'General Meeting',
  'distribution_to_beneficiaries': 'Distribution to Beneficiaries',
  'acceptance_of_property': 'Accept Property into Trust',
  'disposition_of_asset': 'Dispose / Sell Asset',
  'appointment_additional_trustee': 'Appoint Additional Trustee',
  'appointment_successor_trustee': 'Appoint Successor Trustee',
  'designation_of_beneficiaries': 'Designate Beneficiaries',
  'bank_account_authorization': 'Open Bank Account',
  'change_of_situs': 'Change Trust Situs',
  'benevolence_approval': 'Benevolence Approval',
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
  'trust_amendment': 'Trust Amendment',
  'power_of_attorney': 'Power of Attorney Authorization',
  'trust_termination': 'Trust Termination',
  'real_estate_purchase': 'Real Estate Purchase Authorization',
  'business_interest_acquisition': 'Business Interest Acquisition',
  'real_estate_lease': 'Real Estate Lease Authorization',
  'fiscal_year_election': 'Fiscal Year Election',
  'tax_filing_authorization': 'Tax Filing Authorization',
  'emergency_ratification': 'Emergency Action Ratification',
  'conflict_of_interest': 'Conflict of Interest Disclosure'
};

let sectionIdCounter = 1;

export default function MinutesNewPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { selectedTrust, isReadOnly } = useAuth();

  // Wizard state
  const [currentStep, setCurrentStep] = useState(1);
  const [saving, setSaving] = useState(false);

  // Loading states
  const [contextLoading, setContextLoading] = useState(true);
  const [templateOptionsLoading, setTemplateOptionsLoading] = useState(false);

  // Trust context (trustees list, etc.)
  const [trustContext, setTrustContext] = useState(null);
  const [trusteeOptions, setTrusteeOptions] = useState([]);

  // Template options from API
  const [templateOptions, setTemplateOptions] = useState([]);

  // Has existing minutes? (prop for "First Meeting" card)
  const [hasExistingMinutes, setHasExistingMinutes] = useState(true);

  // Common fields
  const [commonFields, setCommonFields] = useState({
    meetingDate: new Date(),
    selectedTrustees: [],
    otherAttendees: [],
    meetingLocation: ''
  });

  // Custom participant input
  const [customParticipant, setCustomParticipant] = useState('');

  // Sections (multi-section support)
  const [sections, setSections] = useState([]);

  // Retroactive
  const [retroactive, setRetroactive] = useState(false);
  const [retroactiveData, setRetroactiveData] = useState({
    reason: '',
    participantsConfirmation: '',
    bestInterest: ''
  });

  // Full draft text for review
  const [fullDraftText, setFullDraftText] = useState('');

  // Redirect read-only users
  useEffect(() => {
    if (isReadOnly) {
      toast.error('Your free access has ended. Subscribe to create new minutes.');
      navigate('/minutes');
    }
  }, [isReadOnly, navigate]);

  // Load trust context and template options on mount
  const loadData = useCallback(async () => {
    if (!selectedTrust?.trust_id) return;

    setContextLoading(true);
    setTemplateOptionsLoading(true);

    try {
      // Load trust context (trustees)
      const ctxRes = await fetchWithAuth(`/guided-minutes/context?trust_id=${selectedTrust.trust_id}`);
      if (ctxRes.ok) {
        const ctx = await ctxRes.json();
        setTrustContext(ctx);
        const trustees = ctx.trustees || [];
        setTrusteeOptions(trustees);
        // Auto-select all known trustees
        setCommonFields(prev => ({ ...prev, selectedTrustees: [...trustees] }));
      } else {
        toast.error('Failed to load trust information');
      }

      // Load existing minutes count to determine hasExistingMinutes
      const minRes = await fetchWithAuth(`/minutes?trust_id=${selectedTrust.trust_id}&limit=1`);
      if (minRes.ok) {
        const minData = await minRes.json();
        const total = Array.isArray(minData) ? minData.length : (minData.total || minData.items?.length || 0);
        setHasExistingMinutes(total > 0);
      }

      // Load template options
      const tplRes = await fetchWithAuth(`/template-options?trust_id=${selectedTrust.trust_id}`);
      if (tplRes.ok) {
        const tplData = await tplRes.json();
        setTemplateOptions(Array.isArray(tplData) ? tplData : tplData.templates || []);
      }
    } catch (error) {
      console.error('Error loading data:', error);
      toast.error('Failed to load trust information');
    } finally {
      setContextLoading(false);
      setTemplateOptionsLoading(false);
    }
  }, [selectedTrust?.trust_id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle URL params: ?type=initial_trustee_meeting, ?retroactive=1
  useEffect(() => {
    const typeParam = searchParams.get('type');
    const retroParam = searchParams.get('retroactive');

    if (retroParam === '1') {
      setRetroactive(true);
    }

    if (typeParam) {
      // Auto-select the template and add a section
      const templateName = TEMPLATE_TITLES[typeParam] || typeParam.replace(/_/g, ' ');
      setSections([{
        id: sectionIdCounter++,
        templateType: typeParam,
        templateName,
        formData: {},
        templateDef: { fields: [] },
        aiDraftText: ''
      }]);
      // If type param is provided, skip to step 2
      setCurrentStep(2);
    }
  }, [searchParams]);

  // Autosave
  useMinutesAutosave({
    selectedTrust,
    formData: { ...commonFields, retroactive, retroactiveData },
    sections,
    enabled: currentStep >= 2
  });

  // --- Step 1 handlers ---
  const handleTemplateSelect = (templateValue) => {
    // If there's a single section and it hasn't been configured yet, update it
    if (sections.length === 0) {
      const templateName = TEMPLATE_TITLES[templateValue] || templateValue.replace(/_/g, ' ');
      // Look for template definition in API options
      const apiTemplate = templateOptions.find(t => (t.value || t.type) === templateValue);
      setSections([{
        id: sectionIdCounter++,
        templateType: templateValue,
        templateName,
        formData: {},
        templateDef: apiTemplate ? { fields: apiTemplate.fields || [] } : { fields: [] },
        aiDraftText: ''
      }]);
    } else if (sections.length === 1 && !sections[0].templateType) {
      // Update the empty first section
      const templateName = TEMPLATE_TITLES[templateValue] || templateValue.replace(/_/g, ' ');
      const apiTemplate = templateOptions.find(t => (t.value || t.type) === templateValue);
      setSections(prev => prev.map((s, i) => i === 0 ? {
        ...s,
        templateType: templateValue,
        templateName,
        templateDef: apiTemplate ? { fields: apiTemplate.fields || [] } : { fields: [] }
      } : s));
    }
  };

  // Get the currently selected template from step 1 (first section's type)
  const selectedTemplate = sections.length > 0 ? sections[0].templateType : '';

  // --- Step 2 handlers ---
  const handleCommonFieldChange = (field, value) => {
    setCommonFields(prev => ({ ...prev, [field]: value }));
  };

  const handleSectionFieldChange = (sectionIndex, field, value) => {
    setSections(prev => prev.map((s, i) => {
      if (i !== sectionIndex) return s;
      return {
        ...s,
        formData: { ...s.formData, [field]: value },
        // Also track aiDraftText separately if that's the field
        ...(field === 'aiDraftText' ? { aiDraftText: value } : {})
      };
    }));
  };

  const handleAddSection = () => {
    setSections(prev => [...prev, {
      id: sectionIdCounter++,
      templateType: '',
      templateName: '',
      formData: {},
      templateDef: { fields: [] },
      aiDraftText: ''
    }]);
  };

  const handleRemoveSection = (index) => {
    setSections(prev => prev.filter((_, i) => i !== index));
  };

  const handleAiDraftGenerated = (sectionIndex, draftBody, suggestedTitle) => {
    setSections(prev => prev.map((s, i) => {
      if (i !== sectionIndex) return s;
      return { ...s, aiDraftText: draftBody };
    }));
  };

  const handleAddCustomParticipant = () => {
    if (customParticipant.trim()) {
      const name = customParticipant.trim();
      // Add as trustee if not in the known list, else as attendee
      if (!trusteeOptions.includes(name) && !(commonFields.selectedTrustees || []).includes(name)) {
        setCommonFields(prev => ({
          ...prev,
          selectedTrustees: [...(prev.selectedTrustees || []), name]
        }));
      }
      setCustomParticipant('');
    }
  };

  const handleRetroactiveToggle = (val) => {
    setRetroactive(val);
  };

  const handleRetroactiveChange = (field, value) => {
    setRetroactiveData(prev => ({ ...prev, [field]: value }));
  };

  // --- Step 3: Build the full draft text for preview ---
  const buildFullDraftText = useCallback(() => {
    if (sections.length === 0) return '';

    const dateStr = commonFields.meetingDate
      ? format(commonFields.meetingDate, 'MMMM d, yyyy')
      : '[Date TBD]';
    const trusteesStr = (commonFields.selectedTrustees || []).join(', ') || '[No trustees selected]';
    const attendeesStr = (commonFields.otherAttendees || []).join(', ');
    const locationStr = commonFields.meetingLocation || '[Location TBD]';

    let text = `MINUTES OF ${selectedTrust?.name || 'THE TRUST'}\n`;
    text += `Date: ${dateStr}\n`;
    text += `Trustees Present: ${trusteesStr}\n`;
    if (attendeesStr) text += `Other Attendees: ${attendeesStr}\n`;
    text += `Location: ${locationStr}\n`;
    text += '\n---\n\n';

    sections.forEach((section, idx) => {
      text += `${section.templateName || `Section ${idx + 1}`}\n\n`;

      if (section.aiDraftText) {
        text += section.aiDraftText;
      } else {
        const fd = section.formData || {};
        if (fd.keyDecisions) text += `Key Decisions:\n${fd.keyDecisions}\n\n`;
        if (fd.agendaItems) text += `Agenda:\n${fd.agendaItems}\n\n`;
        if (fd.notes) text += `Notes:\n${fd.notes}\n\n`;
        // Template field values
        Object.entries(fd).forEach(([key, val]) => {
          if (!['keyDecisions', 'agendaItems', 'notes', 'aiDraftText'].includes(key) && val) {
            text += `${key.replace(/_/g, ' ')}: ${val}\n`;
          }
        });
      }

      if (idx < sections.length - 1) text += '\n---\n\n';
    });

    if (retroactive) {
      text += '\n---\n\nRETROACTIVE DOCUMENTATION\n';
      text += `Reason for delay: ${retroactiveData.reason || '[Required]'}\n`;
      text += `Participants confirmation: ${retroactiveData.participantsConfirmation || '[Required]'}\n`;
      text += `Best interest justification: ${retroactiveData.bestInterest || '[Required]'}\n`;
    }

    return text;
  }, [sections, commonFields, retroactive, retroactiveData, selectedTrust?.name]);

  // Update full draft text when data changes
  useEffect(() => {
    setFullDraftText(buildFullDraftText());
  }, [buildFullDraftText]);

  // Check if any section has AI content
  const hasAiContent = sections.some(s => s.aiDraftText && s.aiDraftText.trim().length > 0);

  // --- Save handler ---
  const handleSave = async (status) => {
    if (!selectedTrust?.trust_id) {
      toast.error('Please select a trust first');
      return;
    }

    // Validate retroactive required fields
    if (retroactive) {
      if (!retroactiveData.reason || !retroactiveData.participantsConfirmation || !retroactiveData.bestInterest) {
        toast.error('Please complete all retroactive justification fields before saving.');
        setCurrentStep(2); // Go back to form
        return;
      }
    }

    // Validate at least 1 trustee
    if ((commonFields.selectedTrustees || []).length === 0) {
      toast.error('Please select at least one trustee present.');
      setCurrentStep(2);
      return;
    }

    setSaving(true);
    try {
      // Build the request body
      const requestBody = {
        trust_id: selectedTrust.trust_id,
        entry_type: sections.length === 1 ? sections[0].templateType : 'multi_section',
        date: commonFields.meetingDate ? commonFields.meetingDate.toISOString() : new Date().toISOString(),
        participants: commonFields.selectedTrustees,
        other_attendees: commonFields.otherAttendees,
        meeting_location: commonFields.meetingLocation || null,
        summary: sections.map(s => s.templateName || s.templateType).join(' + '),
        details: fullDraftText,
        best_interest_rationale: retroactive ? retroactiveData.bestInterest : null,
        status,
        retroactive: retroactive,
        retroactive_reason: retroactive ? retroactiveData.reason : null,
        retroactive_participants_confirmation: retroactive ? retroactiveData.participantsConfirmation : null,
        sections: sections.map(s => ({
          template_type: s.templateType,
          form_data: s.formData,
          ai_draft_text: s.aiDraftText || null
        }))
      };

      const res = await fetchWithAuth('/minutes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });

      if (res.ok) {
        toast.success(status === 'draft' ? 'Draft saved successfully' : 'Minutes saved successfully');
        navigate('/minutes');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to save minutes');
      }
    } catch (error) {
      console.error('Error saving minutes:', error);
      toast.error('Failed to save minutes. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // --- Navigation validation ---
  const canProceedToStep2 = sections.length > 0 && sections[0].templateType;
  const canProceedToStep3 = (commonFields.selectedTrustees || []).length > 0 && commonFields.meetingDate;

  // --- Render stepper ---
  const renderStepper = () => (
    <div className="flex items-center justify-center mb-8" data-testid="minutes-new-stepper">
      {STEPS.map((s, index) => (
        <div key={s.id} className="flex items-center">
          <div
            className={`flex items-center justify-center w-10 h-10 border-2 transition-colors ${
              currentStep >= s.id
                ? 'bg-navy dark:bg-gold border-navy dark:border-gold text-white dark:text-navy'
                : 'border-navy/20 dark:border-white/20 text-navy/40 dark:text-white/40'
            }`}
          >
            <s.icon className="w-5 h-5" />
          </div>
          <span className={`hidden sm:block ml-2 font-mono text-xs uppercase tracking-widest ${
            currentStep >= s.id ? 'text-navy dark:text-gold' : 'text-navy/40 dark:text-white/40'
          }`}>
            {s.label}
          </span>
          {index < STEPS.length - 1 && (
            <div className={`w-8 sm:w-16 h-0.5 mx-2 ${
              currentStep > s.id ? 'bg-navy dark:bg-gold' : 'bg-navy/20 dark:bg-white/20'
            }`} />
          )}
        </div>
      ))}
    </div>
  );

  // --- No trust selected ---
  if (!selectedTrust) {
    return (
      <div className="main-layout" data-testid="minutes-new-page">
        <Sidebar />
        <main className="main-content">
          <div className="page-container">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Select a trust to create minutes</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="main-layout" data-testid="minutes-new-page">
      <Sidebar />
      <main className="main-content">
        <div className="page-container max-w-3xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <Button
              variant="ghost"
              onClick={() => navigate('/minutes')}
              className="mb-4 text-muted-foreground hover:text-navy"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Minutes
            </Button>
            <h1 className="font-serif text-3xl text-navy dark:text-gold">Create Minutes</h1>
            <p className="text-sm text-muted-foreground mt-1">{selectedTrust?.name}</p>
          </div>

          {/* Stepper */}
          {renderStepper()}

          {/* Step Content */}
          <div className="card-trust corner-mark">
            {/* Loading state */}
            {contextLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-navy/50" />
                <span className="ml-2 text-muted-foreground">Loading trust context...</span>
              </div>
            )}

            {!contextLoading && (
              <>
                {/* Step 1: Template Picker */}
                {currentStep === 1 && (
                  <div data-testid="step-1-content">
                    <p className="label-trust mb-2">Step 1 of 3</p>
                    <h2 className="font-serif text-2xl text-navy dark:text-gold mb-6">What type of minutes?</h2>
                    <Step1TemplatePicker
                      selectedTemplate={selectedTemplate}
                      onSelect={handleTemplateSelect}
                      hasExistingMinutes={hasExistingMinutes}
                      templateOptions={templateOptions}
                    />
                  </div>
                )}

                {/* Step 2: Form Builder */}
                {currentStep === 2 && (
                  <div data-testid="step-2-content">
                    <p className="label-trust mb-2">Step 2 of 3</p>
                    <h2 className="font-serif text-2xl text-navy dark:text-gold mb-6">Fill in the details</h2>
                    <Step2FormBuilder
                      sections={sections}
                      onSectionFieldChange={handleSectionFieldChange}
                      onAddSection={handleAddSection}
                      onRemoveSection={handleRemoveSection}
                      onAiDraftGenerated={handleAiDraftGenerated}
                      commonFields={commonFields}
                      onCommonFieldChange={handleCommonFieldChange}
                      trusteeOptions={trusteeOptions}
                      retroactive={retroactive}
                      onRetroactiveToggle={handleRetroactiveToggle}
                      retroactiveData={retroactiveData}
                      onRetroactiveChange={handleRetroactiveChange}
                      selectedTrust={selectedTrust}
                      customParticipant={customParticipant}
                      onCustomParticipantChange={setCustomParticipant}
                      onAddCustomParticipant={handleAddCustomParticipant}
                    />
                  </div>
                )}

                {/* Step 3: Review & Save */}
                {currentStep === 3 && (
                  <div data-testid="step-3-content">
                    <p className="label-trust mb-2">Step 3 of 3</p>
                    <h2 className="font-serif text-2xl text-navy dark:text-gold mb-6">Review & Save</h2>
                    <Step3ReviewAndSave
                      sections={sections}
                      commonFields={commonFields}
                      retroactive={retroactive}
                      retroactiveData={retroactiveData}
                      onSave={handleSave}
                      saving={saving}
                      fullDraftText={fullDraftText}
                      onFullDraftTextChange={setFullDraftText}
                      hasAiContent={hasAiContent}
                    />
                  </div>
                )}
              </>
            )}

            {/* Navigation (only for steps 1-2; step 3 has its own buttons) */}
            {currentStep < 3 && !contextLoading && (
              <div className="flex items-center justify-between mt-8 pt-6 border-t border-navy/10">
                {currentStep > 1 ? (
                  <Button
                    variant="ghost"
                    onClick={() => setCurrentStep(currentStep - 1)}
                    className="text-muted-foreground hover:text-navy"
                  >
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back
                  </Button>
                ) : (
                  <div />
                )}

                <Button
                  onClick={() => setCurrentStep(currentStep + 1)}
                  disabled={
                    (currentStep === 1 && !canProceedToStep2) ||
                    (currentStep === 2 && !canProceedToStep3)
                  }
                  className="bg-navy dark:bg-gold text-white dark:text-navy hover:bg-navy/90 dark:hover:bg-gold/90"
                >
                  Next
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </div>
            )}
          </div>
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}