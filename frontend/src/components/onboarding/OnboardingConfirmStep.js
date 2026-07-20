import { useState, useEffect, useRef, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ArrowRight, ArrowLeft, Users, ChevronDown, Plus, X, Loader2, Sparkles } from 'lucide-react';
import PageAgentAssistant from '@/components/PageAgentAssistant';
import PageAgentErrorBoundary from '@/components/PageAgentErrorBoundary';

// Feature flag: only render the Page Agent pilot when explicitly enabled.
const PAGE_AGENT_ENABLED = process.env.REACT_APP_ENABLE_PAGE_AGENT === 'true';

// PII masking — must match PageAgentAssistant's internal maskPII so the
// system instructions embed masked extracted fields identically.
function maskPII(content) {
  if (!content || typeof content !== 'string') return content;
  let masked = content;
  masked = masked.replace(/\b\d{3}-\d{2}-\d{4}\b/g, 'XXX-XX-XXXX');
  masked = masked.replace(/\b\d{2}-\d{7}\b/g, 'XX-XXXXXXX');
  masked = masked.replace(/\b(?:\d[ -]*){13,19}\d\b/g, (m) => {
    const digits = m.replace(/\D/g, '');
    if (digits.length >= 13 && digits.length <= 19) return '[CARD REDACTED]';
    return m;
  });
  return masked;
}

// Valid trust type keys - used to validate extracted fields before pre-filling
const VALID_TRUST_TYPES = [
  'revocable_living',
  'irrevocable_family',
  'family',
  'charitable',
  'charitable_remainder',
  'business',
  'ecclesiastical',
  'special_needs',
  'spendthrift',
  'testamentary',
  'life_insurance',
  'land',
  'institutional',
  'other',
];

// All US states and DC - native <select> options for jurisdiction
const US_STATES = [
  { code: 'AL', name: 'Alabama' },
  { code: 'AK', name: 'Alaska' },
  { code: 'AZ', name: 'Arizona' },
  { code: 'AR', name: 'Arkansas' },
  { code: 'CA', name: 'California' },
  { code: 'CO', name: 'Colorado' },
  { code: 'CT', name: 'Connecticut' },
  { code: 'DE', name: 'Delaware' },
  { code: 'DC', name: 'District of Columbia' },
  { code: 'FL', name: 'Florida' },
  { code: 'GA', name: 'Georgia' },
  { code: 'HI', name: 'Hawaii' },
  { code: 'ID', name: 'Idaho' },
  { code: 'IL', name: 'Illinois' },
  { code: 'IN', name: 'Indiana' },
  { code: 'IA', name: 'Iowa' },
  { code: 'KS', name: 'Kansas' },
  { code: 'KY', name: 'Kentucky' },
  { code: 'LA', name: 'Louisiana' },
  { code: 'ME', name: 'Maine' },
  { code: 'MD', name: 'Maryland' },
  { code: 'MA', name: 'Massachusetts' },
  { code: 'MI', name: 'Michigan' },
  { code: 'MN', name: 'Minnesota' },
  { code: 'MS', name: 'Mississippi' },
  { code: 'MO', name: 'Missouri' },
  { code: 'MT', name: 'Montana' },
  { code: 'NE', name: 'Nebraska' },
  { code: 'NV', name: 'Nevada' },
  { code: 'NH', name: 'New Hampshire' },
  { code: 'NJ', name: 'New Jersey' },
  { code: 'NM', name: 'New Mexico' },
  { code: 'NY', name: 'New York' },
  { code: 'NC', name: 'North Carolina' },
  { code: 'ND', name: 'North Dakota' },
  { code: 'OH', name: 'Ohio' },
  { code: 'OK', name: 'Oklahoma' },
  { code: 'OR', name: 'Oregon' },
  { code: 'PA', name: 'Pennsylvania' },
  { code: 'RI', name: 'Rhode Island' },
  { code: 'SC', name: 'South Carolina' },
  { code: 'SD', name: 'South Dakota' },
  { code: 'TN', name: 'Tennessee' },
  { code: 'TX', name: 'Texas' },
  { code: 'UT', name: 'Utah' },
  { code: 'VT', name: 'Vermont' },
  { code: 'VA', name: 'Virginia' },
  { code: 'WA', name: 'Washington' },
  { code: 'WV', name: 'West Virginia' },
  { code: 'WI', name: 'Wisconsin' },
  { code: 'WY', name: 'Wyoming' },
];

export default function OnboardingConfirmStep({
  extractedFields,  // AI-extracted fields from backend
  trustData,        // current trust data state from parent
  setTrustData,     // setter for trust data
  trusteeNames,     // array of trustee name strings
  setTrusteeNames,  // setter for trustee names array
  onBack,           // go back to previous step
  onConfirm,        // save and continue (async)
  loading,          // bool, when saving
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const prefilledRef = useRef(false);

  // Ref for the form container — passed to PageAgentAssistant so the agent
  // is restricted to interacting only with elements inside this form.
  const formContainerRef = useRef(null);

  // ---------------- Page Agent system instructions ----------------
  // Onboarding-specific instructions are defined here and passed as a prop to
  // the shared PageAgentAssistant component. The extractedFields are masked
  // and embedded so the agent can read them without leaking PII.
  const systemInstructions = useMemo(() => {
    return `
You are the TrustOffice Onboarding Page Agent, embedded in the "Review Your
Trust Details" form on step 3 of trust onboarding. Your ONLY job is to help
the user fill in draft values for the form fields and explain what each
field means.

ABSOLUTE RULES:
1. NEVER submit the form. Do not click, tap, or otherwise activate the
   "Confirm and Create Trust" button (data-testid="confirm-create-trust-btn").
   That button finalizes the trust and is reserved for the user.
2. NEVER click the "Back" button (data-testid="confirm-back-btn").
3. You may ONLY interact with elements inside the onboarding confirm form
   container. Do not navigate away, open menus, or touch anything outside
   that container.
4. Never run arbitrary JavaScript. The execute_javascript tool is disabled.
5. Never ask for or reveal sensitive PII that is not already visible on the
   page. If the user asks you to fill an SSN, EIN, or credit card number,
   fill it ONLY from the provided extracted fields — never invent values.
6. Do not modify the trust once the user clicks "Confirm and Create Trust".
   If the form has been submitted, stop and tell the user.

WHAT YOU CAN DO:
- Fill form fields from the extracted data the user provides in their
  instruction, or from the \`extractedFields\` JSON I will pass you.
- Explain what a field means (e.g. "What trust type should I select?").
- Suggest a value for a field based on the trust document data.
- Clear a field the user asks to clear.

HOW TO FILL:
- Trust Name input: data-testid="confirm-trust-name-input"
- Trust Type (Radix Select): use the select_radix_option tool with
  testid="confirm-trust-type-select" and optionText = the visible label
  (e.g. "Revocable Living Trust", "Irrevocable Family Trust"). Do NOT try
  to use selectOption on this — it is not a native <select>.
- State/Jurisdiction (native select): data-testid="confirm-jurisdiction-input"
  — use the normal selectOption action.
- Trustee Name inputs: data-testid="confirm-trustee-name-0",
  data-testid="confirm-trustee-name-1", etc. (one per trustee)
- Grantor Name: data-testid="confirm-grantor-name-input"
- Formation Date: data-testid="confirm-formation-date-input"
- EIN: data-testid="confirm-ein-input" (under "Advanced settings" — click
  the "Advanced settings" toggle button first to reveal it)
- Tax Year End Month (Radix Select): use select_radix_option with
  testid="confirm-tax-month-select" and optionText like "DEC (Calendar)".
- Tax Year End Day: data-testid="confirm-tax-day-input"
- Description: data-testid="confirm-description-input"

When you fill a field, briefly tell the user what you set and why. If a
requested value is missing from the extracted data, say so — do not guess.

Available extracted fields from the user's trust document:
${maskPII(JSON.stringify(extractedFields || {}, null, 2))}
`.trim();
  }, [extractedFields]);

  // Pre-fill the form once when extractedFields arrive from the backend.
  // Uses a ref flag so we never overwrite user edits on subsequent renders.
  useEffect(() => {
    if (!extractedFields || prefilledRef.current) return;

    const updates = {};

    // Trust name - only set if the field is currently empty
    if (extractedFields.trust_name && !trustData.name) {
      updates.name = extractedFields.trust_name;
    }

    // Trust type - validate against known types before setting
    if (extractedFields.trust_type && VALID_TRUST_TYPES.includes(extractedFields.trust_type)) {
      updates.trust_type = extractedFields.trust_type;
    }

    // Jurisdiction / state - accept if it looks like a 2-letter US state code
    if (extractedFields.jurisdiction || extractedFields.state) {
      const rawState = (extractedFields.jurisdiction || extractedFields.state || '').toUpperCase();
      const stateCodes = US_STATES.map((s) => s.code);
      if (stateCodes.includes(rawState) && !trustData.jurisdiction) {
        updates.jurisdiction = rawState;
      }
    }

    // Grantor name - optional, only set if present
    if (extractedFields.grantor_name && !trustData.grantor_name) {
      updates.grantor_name = extractedFields.grantor_name;
    }

    // Formation date - maps to trustData.start_date
    if (extractedFields.formation_date && !trustData.start_date) {
      updates.start_date = extractedFields.formation_date;
    }

    // EIN
    if (extractedFields.ein && !trustData.ein) {
      updates.ein = extractedFields.ein;
    }

    // Description
    if (extractedFields.description && !trustData.description) {
      updates.description = extractedFields.description;
    }

    if (Object.keys(updates).length > 0) {
      setTrustData({ ...trustData, ...updates });
    }

    // Trustee names - replace the array if backend gave us a non-empty list,
    // but preserve the user's own name if it was already set on the first slot.
    if (Array.isArray(extractedFields.trustee_names) && extractedFields.trustee_names.length > 0) {
      const currentFirstName = trusteeNames[0] || '';
      const extractedClean = extractedFields.trustee_names.filter((n) => n && n.trim());
      if (extractedClean.length > 0) {
        // If the user already has their own name as the first trustee, keep it
        // and append the extracted names (deduped). Otherwise use extracted names.
        if (currentFirstName.trim() && !extractedClean.includes(currentFirstName.trim())) {
          setTrusteeNames([currentFirstName.trim(), ...extractedClean]);
        } else {
          setTrusteeNames(extractedClean);
        }
      }
    }

    prefilledRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extractedFields]);

  // Handlers for trustee name array editing
  const handleTrusteeChange = (idx, value) => {
    const updated = [...trusteeNames];
    updated[idx] = value;
    setTrusteeNames(updated);
  };

  const addTrustee = () => {
    setTrusteeNames([...trusteeNames, '']);
  };

  const removeTrustee = (idx) => {
    setTrusteeNames(trusteeNames.filter((_, i) => i !== idx));
  };

  // Local field updaters for trustData
  const updateField = (field, value) => {
    setTrustData({ ...trustData, [field]: value });
  };

  return (
    <div className="mt-8">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-muted-foreground hover:text-navy mb-6 transition-colors"
        type="button"
        data-testid="confirm-back-btn"
      >
        <ArrowLeft className="w-4 h-4" />
        <span className="font-mono text-xs uppercase tracking-widest">Back</span>
      </button>

      <div className="card-trust corner-mark mb-8" ref={formContainerRef}>
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="w-6 h-6 text-navy" />
            <h1 className="font-serif text-3xl text-navy">
              Review Your Trust Details
            </h1>
          </div>
          <p className="text-muted-foreground">
            We extracted these from your document. Please review and correct anything.
          </p>
        </div>

        {/* Form fields */}
        <div className="space-y-5">
          {/* Trust Name */}
          <div>
            <Label className="label-trust text-sm" htmlFor="confirm-trust-name">Trust Name <span className="text-warning">*</span></Label>
            <Input
              id="confirm-trust-name"
              type="text"
              value={trustData.name || ''}
              onChange={(e) => updateField('name', e.target.value)}
              className="mt-1.5 input-trust h-11 text-base"
              placeholder="e.g., Smith Family Trust"
              data-testid="confirm-trust-name-input"
            />
            <p className="text-xs text-muted-foreground mt-1.5">
              Enter the name exactly as it appears on your trust document.
            </p>
          </div>

          {/* Trust Type + Jurisdiction grid */}
          <div className="grid grid-cols-2 gap-4">
            {/* Trust Type */}
            <div>
              <Label className="label-trust text-sm" htmlFor="confirm-trust-type">Trust Type</Label>
              <Select
                value={trustData.trust_type || 'revocable_living'}
                onValueChange={(v) => updateField('trust_type', v)}
              >
                <SelectTrigger id="confirm-trust-type" className="mt-1.5 input-trust h-11 text-sm" data-testid="confirm-trust-type-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="revocable_living">Revocable Living Trust</SelectItem>
                  <SelectItem value="irrevocable_family">Irrevocable Family Trust</SelectItem>
                  <SelectItem value="family">Family Trust (Legacy)</SelectItem>
                  <SelectItem value="charitable">Charitable Trust</SelectItem>
                  <SelectItem value="charitable_remainder">Charitable Remainder Trust</SelectItem>
                  <SelectItem value="business">Business Trust</SelectItem>
                  <SelectItem value="ecclesiastical">Religious/Charitable Trust</SelectItem>
                  <SelectItem value="special_needs">Special Needs Trust</SelectItem>
                  <SelectItem value="spendthrift">Spendthrift Trust</SelectItem>
                  <SelectItem value="testamentary">Testamentary Trust</SelectItem>
                  <SelectItem value="life_insurance">Life Insurance Trust</SelectItem>
                  <SelectItem value="land">Land Trust</SelectItem>
                  <SelectItem value="institutional">Institutional Trust</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* State / Jurisdiction - native select for reliability */}
            <div>
              <Label className="label-trust text-sm" htmlFor="confirm-jurisdiction">State <span className="text-warning">*</span></Label>
              <select
                id="confirm-jurisdiction"
                value={trustData.jurisdiction || ''}
                onChange={(e) => updateField('jurisdiction', e.target.value)}
                className="mt-1.5 input-trust h-11 text-sm w-full rounded border border-input bg-background px-3 py-2 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
                data-testid="confirm-jurisdiction-input"
              >
                <option value="" disabled>Select state</option>
                {US_STATES.map((s) => (
                  <option key={s.code} value={s.code}>{s.name}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Trustee Names section */}
          <div className="p-4 border-2 border-navy/20 bg-navy/5">
            <div className="flex items-center gap-2 mb-3">
              <Users className="w-4 h-4 text-navy" />
              <Label className="label-trust text-sm" htmlFor="confirm-trustee-0">Trustee Name(s)</Label>
            </div>
            <div className="space-y-2">
              {trusteeNames.map((name, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    id={idx === 0 ? 'confirm-trustee-0' : undefined}
                    type="text"
                    value={name}
                    onChange={(e) => handleTrusteeChange(idx, e.target.value)}
                    className="input-trust h-11 text-base"
                    placeholder={idx === 0 ? 'Your name (as trustee)' : 'Co-trustee name'}
                    aria-label={idx === 0 ? 'Your name (as trustee)' : `Co-trustee ${idx}`}
                    data-testid={`confirm-trustee-name-${idx}`}
                  />
                  {trusteeNames.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeTrustee(idx)}
                      className="flex-shrink-0 w-9 h-9 flex items-center justify-center text-neutral-400 hover:text-red-500 transition-colors"
                      aria-label="Remove trustee"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addTrustee}
              className="flex items-center gap-1.5 text-sm text-navy hover:text-navy/80 mt-3 transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span>Add co-trustee</span>
            </button>
          </div>

          {/* Grantor Name - optional */}
          <div>
            <Label className="label-trust text-sm" htmlFor="confirm-grantor-name">Grantor Name (optional)</Label>
            <Input
              id="confirm-grantor-name"
              type="text"
              value={trustData.grantor_name || ''}
              onChange={(e) => updateField('grantor_name', e.target.value)}
              className="mt-1.5 input-trust h-11 text-base"
              placeholder="e.g., John Smith"
              data-testid="confirm-grantor-name-input"
            />
            <p className="text-xs text-muted-foreground mt-1.5">
              The person who created and funded the trust. Leave blank if not applicable.
            </p>
          </div>

          {/* Formation Date */}
          <div>
            <Label className="label-trust text-sm" htmlFor="confirm-formation-date">Formation Date</Label>
            <Input
              id="confirm-formation-date"
              type="date"
              value={trustData.start_date || ''}
              onChange={(e) => updateField('start_date', e.target.value)}
              className="mt-1.5 input-trust h-11 text-base"
              data-testid="confirm-formation-date-input"
            />
          </div>

          {/* Advanced settings - collapsible */}
          <div>
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-navy transition-colors"
              type="button"
            >
              <ChevronDown className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
              <span>Advanced settings (EIN, tax year end, description)</span>
            </button>

            {showAdvanced && (
              <div className="mt-4 space-y-4 p-4 bg-navy/5 border border-navy/10">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="label-trust text-xs" htmlFor="confirm-ein">EIN (optional)</Label>
                    <Input
                      id="confirm-ein"
                      type="text"
                      value={trustData.ein || ''}
                      onChange={(e) => updateField('ein', e.target.value)}
                      className="mt-1 input-trust h-9 text-sm"
                      placeholder="XX-XXXXXXX"
                      data-testid="confirm-ein-input"
                    />
                  </div>
                  <div>
                    <Label className="label-trust text-xs" htmlFor="confirm-tax-month">Tax Year End - Month</Label>
                    <Select
                      value={trustData.tax_year_end_month || '12'}
                      onValueChange={(v) => updateField('tax_year_end_month', v)}
                    >
                      <SelectTrigger id="confirm-tax-month" className="mt-1 input-trust h-9 text-sm" data-testid="confirm-tax-month-select">
                        <SelectValue placeholder="Month" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="12">DEC (Calendar)</SelectItem>
                        <SelectItem value="1">JAN</SelectItem>
                        <SelectItem value="2">FEB</SelectItem>
                        <SelectItem value="3">MAR</SelectItem>
                        <SelectItem value="4">APR</SelectItem>
                        <SelectItem value="5">MAY</SelectItem>
                        <SelectItem value="6">JUN</SelectItem>
                        <SelectItem value="7">JUL</SelectItem>
                        <SelectItem value="8">AUG</SelectItem>
                        <SelectItem value="9">SEP</SelectItem>
                        <SelectItem value="10">OCT</SelectItem>
                        <SelectItem value="11">NOV</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="label-trust text-xs" htmlFor="confirm-tax-day">Tax Year End - Day</Label>
                    <Input
                      id="confirm-tax-day"
                      type="number"
                      min={1}
                      max={31}
                      value={trustData.tax_year_end_day || ''}
                      onChange={(e) => updateField('tax_year_end_day', e.target.value)}
                      className="mt-1 input-trust h-9 text-sm"
                      placeholder="31"
                      data-testid="confirm-tax-day-input"
                    />
                  </div>
                </div>
                {trustData.tax_year_end_month && trustData.tax_year_end_day &&
                 !(Number(trustData.tax_year_end_month) === 12 && Number(trustData.tax_year_end_day) === 31) && (
                  <p className="text-xs text-muted-foreground">
                    Fiscal year - tax deadlines will be calculated from this date.
                  </p>
                )}
                <div>
                  <Label className="label-trust text-xs" htmlFor="confirm-description">Description (optional)</Label>
                  <Input
                    id="confirm-description"
                    type="text"
                    value={trustData.description || ''}
                    onChange={(e) => updateField('description', e.target.value)}
                    className="mt-1 input-trust h-9 text-sm"
                    placeholder="Brief description of your trust purpose"
                    data-testid="confirm-description-input"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Confirm and Create Trust button */}
          <Button
            onClick={onConfirm}
            className="w-full btn-primary h-12 text-base"
            disabled={loading || !trustData.name?.trim() || !trustData.jurisdiction}
            data-testid="confirm-create-trust-btn"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                Creating...
              </>
            ) : (
              <>
                Confirm and Create Trust
                <ArrowRight className="w-5 h-5 ml-2" />
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Page Agent pilot — only renders when REACT_APP_ENABLE_PAGE_AGENT === 'true' */}
      {PAGE_AGENT_ENABLED && (
        <PageAgentErrorBoundary>
          <PageAgentAssistant
            containerRef={formContainerRef}
            systemInstructions={systemInstructions}
            pageName="Onboarding"
            trustData={trustData}
            setTrustData={setTrustData}
            trusteeNames={trusteeNames}
            setTrusteeNames={setTrusteeNames}
            extractedFields={extractedFields}
            placeholder='e.g. "Fill in the trust name from my document"'
            idleMessage='Ready. Type an instruction like "Fill in the trust name from my document".'
            helpText='The agent can fill draft values from your document and explain fields. It will never submit the form — you review and confirm yourself.'
          />
        </PageAgentErrorBoundary>
      )}
    </div>
  );
}