/**
 * CreateMinutesPage.js
 *
 * Unified entry point for creating minutes — a clean 3-step experience:
 *   Step 1: Template picker grid ("What are you documenting?")
 *   Step 2: Guided input (only for "Draft with AI")
 *   Step 3: AI draft review & save (only for "Draft with AI")
 *
 * When a template IS selected in Step 1, the user is immediately navigated
 * to /minutes/template/{type}?from=create instead of entering Steps 2–3.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import {
  ArrowLeft,
  ArrowRight,
  CalendarIcon,
  Check,
  CheckCircle,
  ChevronRight,
  FileText,
  Gavel,
  Sparkles,
  Users,
  DollarSign,
  PlusCircle,
  MinusCircle,
  UserPlus,
  UserCheck,
  UsersRound,
  Landmark,
  MapPin,
  HeartHandshake,
  TrendingUp,
  Banknote,
  ShieldCheck,
  CalendarCheck,
  CalendarDays,
  Wallet,
  FileEdit,
  Stamp,
  FileX,
  Home,
  Building2,
  Key,
  CalendarRange,
  Receipt,
  AlertTriangle,
  Scale,
  XCircle,
  HandCoins,
  UserMinus,
  Loader2,
  X,
  Plus,
  Save,
  ClipboardList,
  Trash2,
  RefreshCw,
} from 'lucide-react';
import { Switch } from '@/components/ui/switch';

// ---------------------------------------------------------------------------
// Constants & Mappings
// ---------------------------------------------------------------------------

/** Distribution purpose classification options */
const DISTRIBUTION_PURPOSES = [
  { value: 'hems_health', label: 'Health' },
  { value: 'hems_education', label: 'Education' },
  { value: 'hems_maintenance', label: 'Maintenance' },
  { value: 'hems_support', label: 'Support' },
  { value: 'hems_discretionary', label: 'Discretionary' },
];
import { format } from 'date-fns';

// ---------------------------------------------------------------------------
// Constants & Mappings
// ---------------------------------------------------------------------------

/** Map backend icon names to lucide-react components */
const ICONS = {
  'file-text': FileText,
  'users': Users,
  'dollar-sign': DollarSign,
  'plus-circle': PlusCircle,
  'minus-circle': MinusCircle,
  'user-plus': UserPlus,
  'user-check': UserCheck,
  'users-round': UsersRound,
  'landmark': Landmark,
  'map-pin': MapPin,
  'heart-handshake': HeartHandshake,
  'gavel': Gavel,
  'heart-pulse': HeartHandshake,
  'trending-up': TrendingUp,
  'banknote': Banknote,
  'shield-check': ShieldCheck,
  'calendar-check': CalendarCheck,
  'calendar-days': CalendarDays,
  'wallet': Wallet,
  'file-edit': FileEdit,
  'stamp': Stamp,
  'file-x': FileX,
  'home': Home,
  'building-2': Building2,
  'key': Key,
  'calendar-range': CalendarRange,
  'receipt': Receipt,
  'alert-triangle': AlertTriangle,
  'scale': Scale,
  'x-circle': XCircle,
  'hand-coins': HandCoins,
  'user-minus': UserMinus,
};

/** Human-readable labels for meeting types */
const MEETING_TYPE_LABELS = {
  annual: 'Annual Meeting',
  quarterly: 'Quarterly Meeting',
  general: 'General / Special Meeting',
};

/** Category display order and labels for the template grid */
const CATEGORY_ORDER = [
  { key: 'recommended', label: 'Recommended' },
  { key: 'governance', label: 'Governance' },
  { key: 'financial', label: 'Financial' },
  { key: 'assets', label: 'Assets' },
  { key: 'beneficiaries', label: 'Beneficiaries' },
  { key: 'reviews', label: 'Reviews' },
  { key: 'administrative', label: 'Administrative' },
  { key: 'legal', label: 'Legal' },
];

/** Template types that belong to the "Recommended" section */
const RECOMMENDED_TYPES = new Set([
  'initial_trustee_meeting',
  'quarterly_review',
  'annual_review',
  'distribution_to_beneficiaries',
]);

/** Mapping from backend category key → our display categories */
const CATEGORY_MAP = {
  governance: 'governance',
  financial: 'financial',
  assets: 'assets',
  beneficiaries: 'beneficiaries',
  reviews: 'reviews',
  administrative: 'administrative',
  legal: 'legal',
  // These backend categories go into "Recommended" when applicable;
  // otherwise they map based on their actual category.
  priority: 'recommended',
  basic: 'recommended',
  distributions: 'recommended',
  benevolence: 'beneficiaries',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CreateMinutesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { selectedTrust, isReadOnly } = useAuth();

  // ----- Read-only guard -----
  useEffect(() => {
    if (isReadOnly) {
      toast.error('Read-only users cannot create minutes');
      navigate('/minutes', { replace: true });
    }
  }, [isReadOnly, navigate]);

  // ----- URL prefill support (Money → Minutes onboarding flow) -----
  const fromOnboarding = searchParams.get('from') === 'onboarding';

  useEffect(() => {
    const prefillType = searchParams.get('prefill_type');
    const prefillAmount = searchParams.get('prefill_amount');
    const prefillRecipient = searchParams.get('prefill_recipient');
    const prefillDescription = searchParams.get('prefill_description');

    const hasPrefill = prefillType && prefillAmount;

    // Guard: don't proceed if prefill params exist but selectedTrust isn't loaded yet
    if (hasPrefill && !selectedTrust?.trust_id) {
      return;
    }

    if (hasPrefill) {
      // Auto-select "Draft with AI" flow and jump to Step 2
      const decision = `${prefillType === 'compensation' ? 'Approved compensation' : prefillType === 'distribution' ? 'Approved distribution' : 'Approved benevolence'} of $${parseFloat(prefillAmount).toLocaleString()} to ${prefillRecipient || 'recipient'}${prefillDescription ? ` for ${prefillDescription}` : ''}`;
      setKeyDecisions([decision]);

      // Auto-enable the corresponding record type
      if (prefillType === 'compensation') setCreateCompensationRecords(true);
      if (prefillType === 'distribution') setCreateDistributionRecords(true);
      if (prefillType === 'benevolence') setCreateBenevolenceRecords(true);
      setCreateLinkedRecords(true);

      // Pre-populate record
      setRecordsToCreate([{
        record_type: prefillType,
        amount: parseFloat(prefillAmount),
        recipient: prefillRecipient || '',
        date: format(new Date(), 'yyyy-MM-dd'),
        description: prefillDescription || '',
        purpose_classification: prefillType === 'distribution' ? 'hems_support' : undefined,
      }]);

      // Jump to Step 2 (load trust context first)
      loadTrustContext();
      setStep(2);
    }
  }, [searchParams, selectedTrust?.trust_id]);

  // ----- Step state (1 = template picker, 2 = guided input, 3 = AI draft review) -----
  const [step, setStep] = useState(1);

  // ----- Step 1: template options loaded from backend -----
  const [templateOptions, setTemplateOptions] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);

  // ----- Step 2: guided minutes input -----
  const [meetingType, setMeetingType] = useState('general');
  const [meetingDate, setMeetingDate] = useState(new Date());
  const [datePopoverOpen, setDatePopoverOpen] = useState(false);
  const [trustContext, setTrustContext] = useState(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [selectedTrustees, setSelectedTrustees] = useState([]);
  const [otherAttendees, setOtherAttendees] = useState([]);
  const [agendaItems, setAgendaItems] = useState(['']);
  const [keyDecisions, setKeyDecisions] = useState(['']);
  const [additionalContext, setAdditionalContext] = useState('');

  // ----- Step 2: custom trustees -----
  const [customTrustees, setCustomTrustees] = useState([]);
  const [customTrusteeInput, setCustomTrusteeInput] = useState('');

  // ----- Step 3: AI draft -----
  const [aiDrafting, setAiDrafting] = useState(false);
  const [draftResponse, setDraftResponse] = useState(null);
  const [editedDraft, setEditedDraft] = useState('');
  const [editedTitle, setEditedTitle] = useState('');

  // ----- Step 3: per-type record toggles -----
  const [createCompensationRecords, setCreateCompensationRecords] = useState(false);
  const [createDistributionRecords, setCreateDistributionRecords] = useState(false);
  const [createBenevolenceRecords, setCreateBenevolenceRecords] = useState(false);

  const [createLinkedRecords, setCreateLinkedRecords] = useState(false);
  const [recordsToCreate, setRecordsToCreate] = useState([]);
  const [createdRecordsCounts, setCreatedRecordsCounts] = useState(null);
  const [saving, setSaving] = useState(false);

  const [showDraftExample, setShowDraftExample] = useState(false);
  const [templateFetchKey, setTemplateFetchKey] = useState(0);

  // =========================================================================
  // Step 1 — Load template options
  // =========================================================================

  useEffect(() => {
    if (!selectedTrust?.trust_id) return;
    let cancelled = false;
    setTemplatesLoading(true);
    fetchWithAuth(`/template-options?trust_id=${selectedTrust.trust_id}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load templates');
        return res.json();
      })
      .then((data) => {
        if (!cancelled) {
          setTemplateOptions(data.templates || data || []);
        }
      })
      .catch((err) => {
        console.error('Error loading template options:', err);
        if (!cancelled) toast.error('Failed to load templates');
      })
      .finally(() => {
        if (!cancelled) setTemplatesLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedTrust?.trust_id, templateFetchKey]);

  // =========================================================================
  // Step 2 — Load trust context for guided flow
  // =========================================================================

  const loadTrustContext = useCallback(async () => {
    if (!selectedTrust?.trust_id) return;
    setContextLoading(true);
    try {
      const res = await fetchWithAuth(
        `/guided-minutes/context?trust_id=${selectedTrust.trust_id}`
      );
      if (!res.ok) throw new Error('Failed to load trust context');
      const data = await res.json();
      setTrustContext(data);
      // Auto-populate trustees from trust context
      if (data.trustees && data.trustees.length > 0) {
        setSelectedTrustees(data.trustees.map((t) => t.name || t));
      }
    } catch (err) {
      console.error('Error loading trust context:', err);
      toast.error('Failed to load trust context');
    } finally {
      setContextLoading(false);
    }
  }, [selectedTrust?.trust_id]);

  // =========================================================================
  // Template selection handler (Step 1)
  // =========================================================================

  const handleTemplateSelect = (templateType) => {
    if (templateType === 'blank') {
      handleWriteFromScratch();
    } else {
      navigate(`/minutes/template/${templateType}?from=create`);
    }
  };

  const handleWriteFromScratch = () => {
    loadTrustContext();
    setStep(2);
  };

  // =========================================================================
  // Step 2 → Step 3: Generate AI draft
  // =========================================================================

  const canProceedToStep3 =
    meetingType &&
    meetingDate &&
    selectedTrustees.length > 0 &&
    agendaItems.concat(keyDecisions).some((s) => s.trim());

  const handleGenerateDraft = async () => {
    if (aiDrafting) return;
    if (!selectedTrust?.trust_id) {
      toast.error('Please select a trust first');
      return;
    }
    if (!canProceedToStep3) {
      toast.error('Please fill in meeting type, date, and at least one topic or decision.');
      return;
    }
    setAiDrafting(true);
    try {
      const res = await fetchWithAuth('/guided-minutes/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          minutes_type: meetingType,
          meeting_date: format(meetingDate, 'yyyy-MM-dd'),
          participants: selectedTrustees,
          other_attendees: otherAttendees.filter((a) => a.trim()),
          agenda_items: agendaItems.filter((i) => i.trim()),
          key_decisions: keyDecisions.filter((d) => d.trim()),
          additional_context: additionalContext.trim() || null,
        }),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to generate draft');
      }
      const data = await res.json();
      setDraftResponse(data);
      const draftBody = data.draft_body || '';
      const draftTitle = data.suggested_title || '';
      if (!draftBody.trim()) {
        toast.error('AI returned an empty draft. Please try again or write from scratch.');
        return;
      }
      setEditedDraft(draftBody);
      setEditedTitle(draftTitle);
      if (data.cautions && data.cautions.length > 0) {
        data.cautions.forEach((c) => toast.warning(c));
      }
      setStep(3);
    } catch (err) {
      console.error('Error generating draft:', err);
      toast.error(err.message || 'Failed to generate minutes draft. Please try again.');
    } finally {
      setAiDrafting(false);
    }
  };

  // =========================================================================
  // Step 3: Save minutes
  // =========================================================================

  const canSave = editedDraft.trim().length > 0 && (() => {
    if (!createLinkedRecords) return true;
    // Validate linked records when enabled
    const enabledRecords = recordsToCreate.filter((r) => {
      if (r.record_type === 'compensation' && !createCompensationRecords) return false;
      if (r.record_type === 'distribution' && !createDistributionRecords) return false;
      if (r.record_type === 'benevolence' && !createBenevolenceRecords) return false;
      return true;
    });
    if (enabledRecords.length === 0) return true;
    return enabledRecords.every((r) => r.amount > 0 && r.recipient && r.recipient.trim());
  })();

  const handleSave = async (withRecords = false) => {
    if (!selectedTrust?.trust_id) {
      toast.error('Please select a trust first');
      return;
    }
    if (!canSave) {
      toast.error('Draft content cannot be empty.');
      return;
    }
    setSaving(true);
    try {
      // Determine if we need to create linked records
      const enabledRecordTypes = (createCompensationRecords ? ['compensation'] : [])
        .concat(createDistributionRecords ? ['distribution'] : [])
        .concat((createBenevolenceRecords && selectedTrust?.benevolence_enabled) ? ['benevolence'] : []);
      const filteredRecords = withRecords
        ? recordsToCreate.filter((r) =>
            enabledRecordTypes.includes(r.record_type) && r.amount > 0 && r.recipient && r.recipient.trim()
          )
        : [];
      const hasRecordsToCreate = withRecords && filteredRecords.length > 0;

      const endpoint = hasRecordsToCreate
        ? '/guided-minutes/save-with-records'
        : '/guided-minutes/save';
      const body = {
        trust_id: selectedTrust.trust_id,
        minutes_type: meetingType,
        meeting_date: format(meetingDate, 'yyyy-MM-dd'),
        participants_text: selectedTrustees.join(', '),
        other_attendees_text: otherAttendees.filter((a) => a.trim()).join(', '),
        decisions_text: editedDraft,
        suggested_title: editedTitle,
      };
      if (hasRecordsToCreate) {
        body.records_to_create = filteredRecords;
      }
      const res = await fetchWithAuth(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to save minutes');
      }
      const data = await res.json();
      if (hasRecordsToCreate && data.created_records) {
        setCreatedRecordsCounts(data.created_records);
      }
      toast.success('Minutes saved successfully');
      setStep(4);
    } catch (err) {
      console.error('Error saving minutes:', err);
      toast.error(err.message || 'Failed to save minutes. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // =========================================================================
  // Helper: toggle trustee from list
  // =========================================================================

  const toggleTrustee = (name) => {
    setSelectedTrustees((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    );
  };

  /** Add a custom trustee name */
  const addCustomTrustee = () => {
    const name = customTrusteeInput.trim();
    if (!name) return;
    if (!selectedTrustees.includes(name)) {
      setSelectedTrustees((prev) => [...prev, name]);
      setCustomTrustees((prev) => [...prev, name]);
    }
    setCustomTrusteeInput('');
  };

  /** Remove a custom trustee */
  const removeCustomTrustee = (name) => {
    setSelectedTrustees((prev) => prev.filter((n) => n !== name));
    setCustomTrustees((prev) => prev.filter((n) => n !== name));
  };

  /** Add a new record of the given type */
  const handleAddRecord = (type) => {
    setRecordsToCreate((prev) => [
      ...prev,
      {
        record_type: type,
        amount: 0,
        recipient: '',
        date: format(meetingDate, 'yyyy-MM-dd'),
        description: '',
        purpose_classification: type === 'distribution' ? 'hems_support' : undefined,
      },
    ]);
  };

  /** Update a single field on a record */
  const handleUpdateRecord = (index, field, value) => {
    setRecordsToCreate((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  /** Remove a record */
  const handleRemoveRecord = (index) => {
    setRecordsToCreate((prev) => prev.filter((_, i) => i !== index));
  };

  /** Reset all state back to initial values (for "Create Another") */
  const resetAllState = () => {
    setStep(1);
    setTemplateOptions([]);
    setTemplatesLoading(true);
    setMeetingType('general');
    setMeetingDate(new Date());
    setDatePopoverOpen(false);
    setTrustContext(null);
    setContextLoading(false);
    setSelectedTrustees([]);
    setOtherAttendees([]);
    setCustomTrustees([]);
    setCustomTrusteeInput('');
    setAgendaItems(['']);
    setKeyDecisions(['']);
    setAdditionalContext('');
    setAiDrafting(false);
    setDraftResponse(null);
    setEditedDraft('');
    setEditedTitle('');
    setCreateCompensationRecords(false);
    setCreateDistributionRecords(false);
    setCreateBenevolenceRecords(false);
    setCreateLinkedRecords(false);
    setRecordsToCreate([]);
    setCreatedRecordsCounts(null);
    setSaving(false);
    setTemplateFetchKey(k => k + 1);
  };

  // =========================================================================
  // Render helpers
  // =========================================================================

  /** Build a map of templates grouped by display category */
  const buildCategorizedTemplates = () => {
    const categorized = {};
    CATEGORY_ORDER.forEach((cat) => {
      categorized[cat.key] = [];
    });

    templateOptions.forEach((t) => {
      const backendCat = t.category || 'basic';
      const displayCat = CATEGORY_MAP[backendCat] || 'other';

      if (RECOMMENDED_TYPES.has(t.type)) {
        categorized.recommended.push(t);
      } else if (categorized[displayCat]) {
        categorized[displayCat].push(t);
      } else {
        // Fallback: put into a reasonable category
        if (!categorized.other) categorized.other = [];
        categorized.other.push(t);
      }
    });

    return categorized;
  };

  /** Render a single template card */
  const renderTemplateCard = (t, idx) => {
    const IconComp = ICONS[t.icon] || FileText;
    const isPriority = t.priority || t.type === 'initial_trustee_meeting';

    return (
      <button
        key={t.type}
        data-testid={`template-${t.type}`}
        onClick={() => handleTemplateSelect(t.type)}
        className="card-trust corner-mark overflow-visible group relative flex flex-col items-start gap-2 p-5 text-left transition-all hover:border-gold/50 hover:shadow-md"
      >
        {/* Priority/Start Here badge */}
        {isPriority && (
          <span className={`badge-trust absolute -top-2 -right-2 bg-gold text-navy text-sm font-bold px-3 py-1 rounded-full shadow-sm${fromOnboarding ? ' animate-pulse' : ''}`}>
            Start Here
          </span>
        )}
        <div className="flex items-center gap-3 w-full">
          <div className={`flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-lg ${isPriority ? 'bg-gold/10 text-gold' : 'bg-navy/5 text-navy'}`}>
            <IconComp className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-serif text-sm font-semibold text-navy truncate">
              {t.name}
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
              {t.description}
            </p>
          </div>
          <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
        </div>
      </button>
    );
  };

  // =========================================================================
  // Render: Step 1 — Template Picker
  // =========================================================================

  const renderStep1 = () => {
    // No trust selected
    if (!selectedTrust?.trust_id) {
      return (
        <div className="flex flex-col items-center justify-center py-20">
          <ClipboardList className="h-12 w-12 text-muted-foreground mb-4" />
          <h2 className="font-serif text-xl text-navy">Select a Trust</h2>
          <p className="text-muted-foreground mt-2">
            Choose a trust from the sidebar to create minutes.
          </p>
        </div>
      );
    }

    const categorized = buildCategorizedTemplates();

    return (
      <div className="space-y-10">
        {/* Page header */}
        <div>
          <h1 className="font-serif text-2xl text-navy">What are you documenting?</h1>
          <p className="text-muted-foreground mt-1">
            Choose a template to get started, or draft with AI assistance.
          </p>
        </div>

        {/* Onboarding welcome message */}
        {fromOnboarding && (
          <div className="rounded-lg border border-gold/30 bg-gold/10 p-4 text-sm text-navy flex items-start gap-2">
            <Sparkles className="h-5 w-5 text-gold flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Welcome!</span>{' '}
              Let's create your first meeting minutes. Choose a template below or draft with AI.
            </div>
          </div>
        )}

        {/* Template grid sections */}
        {CATEGORY_ORDER.map((cat) => {
          const templates = categorized[cat.key];
          if (!templates || templates.length === 0) return null;

          return (
            <section key={cat.key} className="space-y-3">
              <h2 className="font-serif text-lg text-navy border-b border-gold/20 pb-1">
                {cat.label}
                {cat.key === 'recommended' && (
                  <span className="ml-2 text-xs font-mono text-gold normal-case">
                    — most common for your trust
                  </span>
                )}
              </h2>
              {templatesLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {Array.from({ length: templates.length || 4 }).map((_, i) => (
                    <div key={i} className="card-trust animate-pulse p-5 h-24" />
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {templates.map((t, i) => renderTemplateCard(t, i))}
                </div>
              )}
            </section>
          );
        })}

        {/* Write from scratch card */}
        {!templatesLoading && (
          <section className="space-y-3">
            <h2 className="font-serif text-lg text-navy border-b border-gold/20 pb-1">
              AI-Assisted
            </h2>
            <button
              onClick={handleWriteFromScratch}
              className="card-trust group relative flex flex-col items-start gap-2 p-5 text-left transition-all hover:border-gold/50 hover:shadow-md w-full md:w-2/3 lg:w-1/2"
            >
              <div className="flex items-center gap-3 w-full">
                <div className="flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-lg bg-gold/10 text-gold">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-serif text-sm font-semibold text-navy">
                    Draft with AI
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Describe your meeting in plain English. AI transforms your notes into formal, compliant minutes — no legal jargon needed.
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
              </div>
            </button>
            <button
              type="button"
              onClick={() => setShowDraftExample(!showDraftExample)}
              className="text-xs text-gold hover:text-gold/80 font-mono uppercase tracking-wider mt-1"
            >
              {showDraftExample ? 'Hide example' : 'See example'} →
            </button>
            {showDraftExample && (
              <div className="rounded-lg border border-gold/20 bg-gold/5 p-3 text-xs text-muted-foreground font-mono mt-2">
                <p className="font-semibold text-navy mb-1">Your input:</p>
                <p className="italic">&ldquo;Discussed selling the rental property on Oak St. Agreed to list at $340K. Trustee Jane will contact the realtor.&rdquo;</p>
                <p className="font-semibold text-navy mb-1 mt-2">AI produces:</p>
                <p className="italic">A formal resolution authorizing the sale, documenting trustee consensus, naming the realtor, and recording the price decision — ready to save.</p>
              </div>
            )}
          </section>
        )}

        {/* Info box */}
        <div className="rounded-lg border border-gold/20 bg-gold/5 p-4 text-sm text-muted-foreground">
          <p className="flex items-start gap-2">
            <FileText className="h-4 w-4 mt-0.5 text-gold flex-shrink-0" />
            <span>
              Templates guide you through common trustee decisions. New here?
              Start with &ldquo;Initial Trustee Meeting&rdquo; — it walks you through everything.
              Or choose &ldquo;Draft with AI&rdquo; and describe your meeting in plain language.
            </span>
          </p>
        </div>
      </div>
    );
  };

  // =========================================================================
  // Render: Step 2 — Meeting Details
  // =========================================================================

  const renderStep2 = () => {
    const trustName = selectedTrust?.name || trustContext?.trust_name || 'your trust';

    return (
      <div className="card-trust corner-mark p-6 md:p-8">
        <div className="space-y-8">
        {/* Header */}
        <div>
          <button
            onClick={() => setStep(1)}
            className="text-sm text-muted-foreground hover:text-navy flex items-center gap-1 mb-4 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" /> Back to templates
          </button>
          <h1 className="font-serif text-2xl text-navy">Meeting Details</h1>
          <p className="text-muted-foreground mt-1">
            Provide the basics for {trustName} and we'll draft formal minutes for you.
          </p>
        </div>

        {trustContext === null && !contextLoading ? (
          <div className="text-center py-8">
            <p className="text-muted-foreground mb-4">Failed to load trust context.</p>
            <Button onClick={loadTrustContext} className="btn-secondary">Retry</Button>
          </div>
        ) : contextLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-gold" />
          </div>
        ) : (
          <div className="space-y-8 max-w-2xl">
            {/* Meeting Type */}
            <div className="space-y-2">
              <Label className="label-trust" htmlFor="meeting-type">Meeting Type</Label>
              <Select value={meetingType} onValueChange={setMeetingType}>
                <SelectTrigger className="input-trust" id="meeting-type">
                  <SelectValue placeholder="Select meeting type" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(MEETING_TYPE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Meeting Date */}
            <div className="space-y-2">
              <Label className="label-trust" htmlFor="meeting-date">Meeting Date</Label>
              <Popover open={datePopoverOpen} onOpenChange={setDatePopoverOpen}>
                <PopoverTrigger asChild>
                  <Button
                    id="meeting-date"
                    variant="outline"
                    className="input-trust w-full justify-start text-left font-normal"
                  >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {meetingDate ? format(meetingDate, 'PPP') : 'Pick a date'}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={meetingDate}
                    onSelect={(date) => {
                      if (date) {
                        setMeetingDate(date);
                        setDatePopoverOpen(false);
                      }
                    }}
                    initialFocus
                  />
                </PopoverContent>
              </Popover>
            </div>

            {/* Trustees Present */}
            <div className="space-y-2">
              <Label className="label-trust">Trustees Present</Label>
              <div className="space-y-2">
                {(trustContext?.trustees || []).map((trustee) => {
                  const name = trustee.name || trustee;
                  const isChecked = selectedTrustees.includes(name);
                  return (
                    <div key={name} className="flex items-center space-x-2">
                      <Checkbox
                        checked={isChecked}
                        onCheckedChange={() => toggleTrustee(name)}
                        id={`trustee-${name}`}
                      />
                      <Label
                        htmlFor={`trustee-${name}`}
                        className="text-sm font-normal cursor-pointer"
                      >
                        {name}
                      </Label>
                    </div>
                  );
                })}
                {/* Custom trustees from earlier additions */}
                {customTrustees.map((name) => (
                  <div key={name} className="flex items-center space-x-2">
                    <Checkbox
                      checked={selectedTrustees.includes(name)}
                      onCheckedChange={() => toggleTrustee(name)}
                      id={`trustee-custom-${name}`}
                    />
                    <Label
                      htmlFor={`trustee-custom-${name}`}
                      className="text-sm font-normal cursor-pointer"
                    >
                      {name}
                    </Label>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeCustomTrustee(name)}
                      className="ml-auto flex-shrink-0 text-muted-foreground hover:text-destructive h-6 w-6"
                      aria-label="Remove trustee"
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
              {/* Add custom trustee */}
              <div className="flex items-center gap-2 mt-2">
                <Input
                  value={customTrusteeInput}
                  onChange={(e) => setCustomTrusteeInput(e.target.value)}
                  placeholder="Add trustee name"
                  className="input-trust"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addCustomTrustee();
                    }
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={addCustomTrustee}
                  disabled={!customTrusteeInput.trim()}
                  className="text-muted-foreground"
                >
                  <Plus className="h-3 w-3 mr-1" /> Add Trustee
                </Button>
              </div>
            </div>

            {/* Other Attendees */}
            <div className="space-y-2">
              <Label className="label-trust">Other Attendees</Label>
              {otherAttendees.map((attendee, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    value={attendee}
                    onChange={(e) => {
                      const updated = [...otherAttendees];
                      updated[idx] = e.target.value;
                      setOtherAttendees(updated);
                    }}
                    placeholder="Attendee name"
                    className="input-trust"
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() =>
                      setOtherAttendees((prev) => prev.filter((_, i) => i !== idx))
                    }
                    className="flex-shrink-0 text-muted-foreground hover:text-destructive"
                    aria-label="Remove attendee"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOtherAttendees((prev) => [...prev, ''])}
                className="text-muted-foreground"
              >
                <Plus className="h-3 w-3 mr-1" /> Add attendee
              </Button>
            </div>

            {/* Keep it simple callout */}
            <div className="rounded-lg border border-gold/20 bg-gold/5 p-3 text-sm text-navy flex items-start gap-2">
              <Sparkles className="h-4 w-4 text-gold flex-shrink-0 mt-0.5" />
              <span>
                <strong>Keep it simple</strong> — Short bullet points are enough. AI will draft the formal language.
              </span>
            </div>

            {/* Agenda Items */}
            <div className="space-y-2">
              <Label className="label-trust">Agenda Items</Label>
              <p className="text-xs text-muted-foreground">
                What topics were discussed?
              </p>
              {agendaItems.map((item, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    value={item}
                    onChange={(e) => {
                      const updated = [...agendaItems];
                      updated[idx] = e.target.value;
                      setAgendaItems(updated);
                    }}
                    placeholder="Agenda item"
                    className="input-trust"
                  />
                  {agendaItems.length > 1 && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        setAgendaItems((prev) => prev.filter((_, i) => i !== idx))
                      }
                      className="flex-shrink-0 text-muted-foreground hover:text-destructive"
                      aria-label="Remove agenda item"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAgendaItems((prev) => [...prev, ''])}
                className="text-muted-foreground"
              >
                <Plus className="h-3 w-3 mr-1" /> Add item
              </Button>
            </div>

            {/* Key Decisions */}
            <div className="space-y-2">
              <Label className="label-trust">Key Decisions</Label>
              <p className="text-xs text-muted-foreground">
                What was decided or resolved?
              </p>
              {keyDecisions.map((decision, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    value={decision}
                    onChange={(e) => {
                      const updated = [...keyDecisions];
                      updated[idx] = e.target.value;
                      setKeyDecisions(updated);
                    }}
                    placeholder="Key decision"
                    className="input-trust"
                  />
                  {keyDecisions.length > 1 && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        setKeyDecisions((prev) => prev.filter((_, i) => i !== idx))
                      }
                      className="flex-shrink-0 text-muted-foreground hover:text-destructive"
                      aria-label="Remove decision"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setKeyDecisions((prev) => [...prev, ''])}
                className="text-muted-foreground"
              >
                <Plus className="h-3 w-3 mr-1" /> Add decision
              </Button>
            </div>

            {/* Additional Context */}
            <div className="space-y-2">
              <Label className="label-trust" htmlFor="additional-context">Additional Context (Optional)</Label>
              <Textarea
                id="additional-context"
                value={additionalContext}
                onChange={(e) => setAdditionalContext(e.target.value)}
                placeholder="Any additional notes or context for the AI drafter..."
                className="input-trust min-h-[80px]"
              />
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-3 pt-4">
              <Button
                variant="outline"
                onClick={() => setStep(1)}
                className="btn-secondary"
              >
                Back
              </Button>
              <Button
                onClick={handleGenerateDraft}
                disabled={!canProceedToStep3 || aiDrafting}
                className="btn-primary"
              >
                {aiDrafting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Drafting…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" /> Generate Draft
                  </>
                )}
              </Button>
            </div>
          </div>
        )}
        </div>
      </div>
    );
  };

  // =========================================================================
  // Render: Step 3 — Review & Edit AI Draft
  // =========================================================================

  const renderStep3 = () => {
    if (!draftResponse) {
      return (
        <div className="card-trust corner-mark p-6 md:p-8">
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">No draft to review. Please go back and generate one.</p>
            <Button onClick={() => setStep(2)} className="btn-secondary">Back to Meeting Details</Button>
          </div>
        </div>
      );
    }
    return (
    <div className="card-trust corner-mark p-6 md:p-8">
      <div className="space-y-8">
      {/* Header */}
      <div>
        <button
          onClick={() => setStep(2)}
          className="text-sm text-muted-foreground hover:text-navy flex items-center gap-1 mb-4 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to meeting details
        </button>
        <h1 className="font-serif text-2xl text-navy">Review & Edit Draft</h1>
        <p className="text-muted-foreground mt-1">
          Review the AI-generated draft below. Edit as needed, then save.
        </p>
      </div>

      <div className="space-y-6 max-w-3xl">
        {/* Title */}
        <div className="space-y-2">
          <Label className="label-trust" htmlFor="minutes-title">Minutes Title</Label>
          <Input
            id="minutes-title"
            value={editedTitle}
            onChange={(e) => setEditedTitle(e.target.value)}
            className="input-trust"
          />
        </div>

        {/* Cautions */}
        {draftResponse?.cautions?.length > 0 && (
          <div className="rounded-lg border border-gold/30 bg-gold/10 p-4 space-y-1">
            {draftResponse.cautions.map((caution, i) => (
              <p key={i} className="text-sm text-navy flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0 text-gold" />
                {caution}
              </p>
            ))}
          </div>
        )}

        {/* Draft body */}
        <div className="space-y-2">
          <Label className="label-trust" htmlFor="minutes-content">Minutes Content</Label>
          <Textarea
            id="minutes-content"
            value={editedDraft}
            onChange={(e) => setEditedDraft(e.target.value)}
            className="input-trust font-mono min-h-[400px] text-sm leading-relaxed"
            placeholder="Minutes content will appear here…"
          />
        </div>

        {/* Linked records — per-type toggles */}
        <div className="space-y-3">
          <div className="flex items-center space-x-2">
            <Checkbox
              id="create-linked-records"
              checked={createLinkedRecords}
              onCheckedChange={(checked) => {
                setCreateLinkedRecords(checked);
                if (!checked) {
                  setCreateCompensationRecords(false);
                  setCreateDistributionRecords(false);
                  setCreateBenevolenceRecords(false);
                }
              }}
            />
            <Label htmlFor="create-linked-records" className="text-sm cursor-pointer">
              Create linked money records (distributions, compensation, etc.)
            </Label>
          </div>

          {createLinkedRecords && (
            <div className="rounded-lg border border-gold/20 bg-gold/5 p-4 space-y-4">
              {/* Per-type toggles */}
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-white dark:bg-slate-900 rounded-md">
                  <div className="flex items-center gap-3">
                    <Wallet className="w-4 h-4 text-navy/60" />
                    <span className="text-sm font-medium">Compensation payment records</span>
                  </div>
                  <Switch
                    checked={createCompensationRecords}
                    onCheckedChange={setCreateCompensationRecords}
                    data-testid="toggle-compensation"
                  />
                </div>
                <div className="flex items-center justify-between p-3 bg-white dark:bg-slate-900 rounded-md">
                  <div className="flex items-center gap-3">
                    <DollarSign className="w-4 h-4 text-navy/60" />
                    <span className="text-sm font-medium">Distribution records</span>
                  </div>
                  <Switch
                    checked={createDistributionRecords}
                    onCheckedChange={setCreateDistributionRecords}
                    data-testid="toggle-distributions"
                  />
                </div>
                {selectedTrust?.benevolence_enabled && (
                  <div className="flex items-center justify-between p-3 bg-white dark:bg-slate-900 rounded-md">
                    <div className="flex items-center gap-3">
                      <HeartHandshake className="w-4 h-4 text-navy/60" />
                      <span className="text-sm font-medium">Benevolence records</span>
                    </div>
                    <Switch
                      checked={createBenevolenceRecords}
                      onCheckedChange={setCreateBenevolenceRecords}
                      data-testid="toggle-benevolence"
                    />
                  </div>
                )}
              </div>

              {/* Add record buttons */}
              {(createCompensationRecords || createDistributionRecords || (createBenevolenceRecords && selectedTrust?.benevolence_enabled)) && (
                <div className="flex flex-wrap gap-2">
                  {createCompensationRecords && (
                    <Button variant="outline" size="sm" onClick={() => handleAddRecord('compensation')} data-testid="add-compensation-record">
                      <Plus className="w-3 h-3 mr-1" /> Compensation
                    </Button>
                  )}
                  {createDistributionRecords && (
                    <Button variant="outline" size="sm" onClick={() => handleAddRecord('distribution')} data-testid="add-distribution-record">
                      <Plus className="w-3 h-3 mr-1" /> Distribution
                    </Button>
                  )}
                  {createBenevolenceRecords && selectedTrust?.benevolence_enabled && (
                    <Button variant="outline" size="sm" onClick={() => handleAddRecord('benevolence')} data-testid="add-benevolence-record">
                      <Plus className="w-3 h-3 mr-1" /> Benevolence
                    </Button>
                  )}
                </div>
              )}

              {/* Records list */}
              {recordsToCreate.length > 0 && (
                <div className="space-y-3">
                  {recordsToCreate.map((record, idx) => {
                    // Only show records whose type toggle is enabled
                    if (record.record_type === 'compensation' && !createCompensationRecords) return null;
                    if (record.record_type === 'distribution' && !createDistributionRecords) return null;
                    if (record.record_type === 'benevolence' && !createBenevolenceRecords) return null;

                    return (
                      <div
                        key={idx}
                        className="space-y-3 p-3 border rounded-md bg-white"
                        data-testid={`record-${idx}`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs uppercase tracking-widest text-navy/70 flex items-center gap-2">
                            {record.record_type === 'compensation' && <Wallet className="w-3 h-3" />}
                            {record.record_type === 'distribution' && <DollarSign className="w-3 h-3" />}
                            {record.record_type === 'benevolence' && <HeartHandshake className="w-3 h-3" />}
                            {record.record_type}
                          </span>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRemoveRecord(idx)}
                            className="text-destructive hover:text-destructive h-6 w-6 p-0"
                            aria-label="Remove record"
                          >
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                          <div className="space-y-1">
                            <Label className="text-xs text-muted-foreground">Amount ($)</Label>
                            <Input
                              type="number"
                              value={record.amount || ''}
                              onChange={(e) => handleUpdateRecord(idx, 'amount', parseFloat(e.target.value) || 0)}
                              placeholder="0.00"
                              className="input-trust text-sm"
                              data-testid={`record-${idx}-amount`}
                            />
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs text-muted-foreground">Recipient</Label>
                            <Input
                              value={record.recipient || ''}
                              onChange={(e) => handleUpdateRecord(idx, 'recipient', e.target.value)}
                              placeholder="Name"
                              className="input-trust text-sm"
                              data-testid={`record-${idx}-recipient`}
                            />
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs text-muted-foreground">Date</Label>
                            <Input
                              type="date"
                              value={record.date || format(meetingDate, 'yyyy-MM-dd')}
                              onChange={(e) => handleUpdateRecord(idx, 'date', e.target.value)}
                              className="input-trust text-sm"
                              data-testid={`record-${idx}-date`}
                            />
                          </div>
                        </div>
                        {record.record_type === 'distribution' && (
                          <div className="space-y-1">
                            <Label className="text-xs text-muted-foreground">Purpose</Label>
                            <Select
                              value={record.purpose_classification || 'hems_support'}
                              onValueChange={(val) => handleUpdateRecord(idx, 'purpose_classification', val)}
                            >
                              <SelectTrigger className="input-trust text-sm" data-testid={`record-${idx}-purpose`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {DISTRIBUTION_PURPOSES.map((p) => (
                                  <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <p className="text-xs text-muted-foreground mt-1">
                              HEMS = Health, Education, Maintenance, or Support — standard trust distribution categories that help document the purpose of each payment.
                            </p>
                          </div>
                        )}
                        <div className="space-y-1">
                          <Label className="text-xs text-muted-foreground">Description (optional)</Label>
                          <Input
                            value={record.description || ''}
                            onChange={(e) => handleUpdateRecord(idx, 'description', e.target.value)}
                            placeholder="Brief description..."
                            className="input-trust text-sm"
                            data-testid={`record-${idx}-description`}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-3 pt-4">
          <Button
            variant="outline"
            onClick={() => setStep(2)}
            className="btn-secondary"
          >
            Back
          </Button>
          <Button
            onClick={() => handleSave(false)}
            disabled={!canSave || saving}
            className="btn-primary"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
          {createLinkedRecords && recordsToCreate.length > 0 ? 'Save Minutes Only' : 'Save Minutes'}
          </Button>
          {createLinkedRecords && recordsToCreate.length > 0 && (
            <p className="text-xs text-muted-foreground mt-1">Linked records won't be saved. Use the gold button to save everything.</p>
          )}
          {(createLinkedRecords && (createCompensationRecords || createDistributionRecords || createBenevolenceRecords)) && (
            <Button
              onClick={() => handleSave(true)}
              disabled={!canSave || saving}
              className="btn-gold"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Check className="h-4 w-4 mr-2" />
              )}
              Save & Create Linked Records
            </Button>
          )}
        </div>

        </div>
      </div>
    </div>
    );
  };

  // =========================================================================
  // Render: Step 4 — Success
  // =========================================================================

  const renderStep4 = () => (
    <div className="card-trust corner-mark p-6 md:p-8">
      <div className="text-center py-12" data-testid="step-4-content">
        <div className="w-20 h-20 mx-auto mb-6 bg-gold/10 dark:bg-gold/20 flex items-center justify-center rounded-full">
          <CheckCircle className="w-10 h-10 text-gold" />
        </div>
        <h2 className="font-serif text-2xl text-navy mb-4">Minutes Saved</h2>
        <p className="text-muted-foreground mb-4">
          Your meeting minutes have been saved successfully and are now available in your Minutes list.
        </p>

        {/* Show created records summary */}
        {createdRecordsCounts && (createdRecordsCounts.compensation > 0 || createdRecordsCounts.distribution > 0 || createdRecordsCounts.benevolence > 0) && (
          <div className="inline-flex flex-wrap justify-center gap-3 mb-8 p-4 bg-navy/5 dark:bg-gold/5 border border-navy/10 dark:border-gold/10 rounded-lg">
            <span className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70">
              Linked Records Created:
            </span>
            {createdRecordsCounts.compensation > 0 && (
              <span className="flex items-center gap-1 text-sm">
                <Wallet className="w-4 h-4 text-navy dark:text-gold" />
                {createdRecordsCounts.compensation} Compensation
              </span>
            )}
            {createdRecordsCounts.distribution > 0 && (
              <span className="flex items-center gap-1 text-sm">
                <DollarSign className="w-4 h-4 text-navy dark:text-gold" />
                {createdRecordsCounts.distribution} Distribution
              </span>
            )}
            {createdRecordsCounts.benevolence > 0 && (
              <span className="flex items-center gap-1 text-sm">
                <HeartHandshake className="w-4 h-4 text-navy dark:text-gold" />
                {createdRecordsCounts.benevolence} Benevolence
              </span>
            )}
          </div>
        )}

        <div className="flex justify-center gap-4">
          <Button
            variant="outline"
            onClick={() => navigate('/minutes')}
            data-testid="view-minutes-btn"
            className="btn-secondary"
          >
            <FileText className="h-4 w-4 mr-2" />
            View All Minutes
          </Button>
          <Button
            onClick={resetAllState}
            className="btn-primary"
            data-testid="create-another-btn"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Create Another
          </Button>
        </div>
      </div>
    </div>
  );

  // =========================================================================
  // Step indicator
  // =========================================================================

  const renderStepIndicator = () => {
    const steps = [
      { num: 1, label: 'Choose Template' },
      { num: 2, label: 'Meeting Details' },
      { num: 3, label: 'Review Draft' },
      { num: 4, label: 'Done' },
    ];

    return (
      <div className="flex items-center gap-2 mb-8" role="navigation" aria-label="Progress">
        {steps.map((s, idx) => (
          <React.Fragment key={s.num}>
            <div
              aria-label={s.label}
              aria-current={step === s.num ? 'step' : undefined}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                step === s.num
                  ? 'bg-gold/10 text-gold border border-gold/50'
                  : step > s.num
                  ? 'bg-gold/10 text-navy border border-gold/30'
                  : 'bg-muted text-muted-foreground border border-transparent'
              }`}
            >
              {step > s.num ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <span className="h-5 w-5 flex items-center justify-center rounded-full bg-white/80 text-xs font-semibold">
                  {s.num}
                </span>
              )}
              <span className={`hidden sm:inline ${step > s.num ? 'text-navy' : ''}`}>{s.label}</span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={`h-px flex-1 ${
                  step > s.num ? 'bg-gold' : 'bg-muted'
                }`}
              />
            )}
          </React.Fragment>
        ))}
      </div>
    );
  };

  // =========================================================================
  // Main render
  // =========================================================================

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className="lg:ml-64 min-h-screen dot-grid">
        <div className="p-4 md:p-8 pb-24 md:pb-8 max-w-5xl mx-auto">
          {/* Back to minutes list */}
          <button
            onClick={() => navigate('/minutes')}
            className="text-sm text-muted-foreground hover:text-navy flex items-center gap-1 mb-6 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" /> Minutes
          </button>

          {/* Step indicator (only shows for write-from-scratch flow) */}
          {step > 1 && renderStepIndicator()}

          {/* Step content */}
          {step === 1 && renderStep1()}
          {step === 2 && renderStep2()}
          {step === 3 && renderStep3()}
          {step === 4 && renderStep4()}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}