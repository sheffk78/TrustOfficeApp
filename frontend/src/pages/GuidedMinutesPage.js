import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import { 
  ArrowLeft, 
  ArrowRight,
  Calendar as CalendarIcon,
  Users,
  FileText,
  CheckCircle,
  Plus,
  X,
  Sparkles,
  Loader2,
  AlertTriangle,
  Save,
  ListChecks,
  MessageSquare,
  RefreshCw,
  DollarSign,
  Wallet,
  HeartHandshake,
  Trash2
} from 'lucide-react';
import { format } from 'date-fns';

const MEETING_TYPES = [
  { value: 'annual', label: 'Annual Meeting', description: 'Year-end review and planning' },
  { value: 'quarterly', label: 'Quarterly Meeting', description: 'Regular quarterly review' },
  { value: 'general', label: 'General Meeting', description: 'Ad-hoc or special meeting' }
];

const STEPS = [
  { id: 1, label: 'Meeting Type', icon: CalendarIcon },
  { id: 2, label: 'Topics & Decisions', icon: ListChecks },
  { id: 3, label: 'Review Draft', icon: FileText },
  { id: 4, label: 'Save', icon: CheckCircle }
];

const DISTRIBUTION_PURPOSES = [
  { value: 'hems_health', label: 'Health' },
  { value: 'hems_education', label: 'Education' },
  { value: 'hems_maintenance', label: 'Maintenance' },
  { value: 'hems_support', label: 'Support' },
  { value: 'discretionary', label: 'Discretionary' }
];

export default function GuidedMinutesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { selectedTrust } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [contextLoading, setContextLoading] = useState(true);
  
  // Trust context from backend
  const [trustContext, setTrustContext] = useState(null);
  
  // Step 1: Meeting type and basic info
  const [meetingType, setMeetingType] = useState('');
  const [meetingDate, setMeetingDate] = useState(new Date());
  const [selectedParticipants, setSelectedParticipants] = useState([]);
  const [customParticipant, setCustomParticipant] = useState('');
  
  // Step 2: Agenda and decisions
  const [agendaItems, setAgendaItems] = useState(['']);
  const [keyDecisions, setKeyDecisions] = useState(['']);
  const [additionalContext, setAdditionalContext] = useState('');
  
  // Step 3: AI Draft
  const [aiDrafting, setAiDrafting] = useState(false);
  const [draftResponse, setDraftResponse] = useState(null);
  const [editedDraft, setEditedDraft] = useState('');
  const [editedTitle, setEditedTitle] = useState('');
  
  // Step 3: Record creation toggles (Minutes → Money flow)
  const [createCompensationRecords, setCreateCompensationRecords] = useState(false);
  const [createDistributionRecords, setCreateDistributionRecords] = useState(false);
  const [createBenevolenceRecords, setCreateBenevolenceRecords] = useState(false);
  const [recordsToCreate, setRecordsToCreate] = useState([]);
  
  // Step 4: Save
  const [saving, setSaving] = useState(false);
  const [createdRecordsCounts, setCreatedRecordsCounts] = useState(null);

  // Handle URL params for prefill (Money → Minutes flow)
  useEffect(() => {
    const prefillType = searchParams.get('prefill_type');
    const prefillAmount = searchParams.get('prefill_amount');
    const prefillRecipient = searchParams.get('prefill_recipient');
    const prefillDescription = searchParams.get('prefill_description');
    
    if (prefillType && prefillAmount) {
      // Prefill from money record
      const decision = `${prefillType === 'compensation' ? 'Approved compensation' : prefillType === 'distribution' ? 'Approved distribution' : 'Approved benevolence'} of $${parseFloat(prefillAmount).toLocaleString()} to ${prefillRecipient || 'recipient'}${prefillDescription ? ` for ${prefillDescription}` : ''}`;
      setKeyDecisions([decision]);
      
      // Auto-enable the corresponding record type
      if (prefillType === 'compensation') setCreateCompensationRecords(true);
      if (prefillType === 'distribution') setCreateDistributionRecords(true);
      if (prefillType === 'benevolence') setCreateBenevolenceRecords(true);
      
      // Pre-populate record to create
      setRecordsToCreate([{
        record_type: prefillType,
        amount: parseFloat(prefillAmount),
        recipient: prefillRecipient || '',
        date: format(new Date(), 'yyyy-MM-dd'),
        description: prefillDescription || ''
      }]);
    }
  }, [searchParams]);

  // Load trust context on mount
  const loadContext = useCallback(async () => {
    if (!selectedTrust?.trust_id) return;
    
    setContextLoading(true);
    try {
      const response = await fetchWithAuth(`/guided-minutes/context?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        const data = await response.json();
        setTrustContext(data);
      } else {
        toast.error('Failed to load trust information');
      }
    } catch (error) {
      console.error('Error loading context:', error);
      toast.error('Failed to load trust information');
    } finally {
      setContextLoading(false);
    }
  }, [selectedTrust?.trust_id]);

  useEffect(() => {
    loadContext();
  }, [loadContext]);

  // Handle participant selection
  const handleParticipantToggle = (name) => {
    setSelectedParticipants(prev => 
      prev.includes(name) 
        ? prev.filter(p => p !== name)
        : [...prev, name]
    );
  };

  const handleAddCustomParticipant = () => {
    if (customParticipant.trim() && !selectedParticipants.includes(customParticipant.trim())) {
      setSelectedParticipants(prev => [...prev, customParticipant.trim()]);
      setCustomParticipant('');
    }
  };

  // Handle agenda items
  const handleAgendaChange = (index, value) => {
    const newItems = [...agendaItems];
    newItems[index] = value;
    setAgendaItems(newItems);
  };

  const handleAddAgendaItem = () => {
    setAgendaItems([...agendaItems, '']);
  };

  const handleRemoveAgendaItem = (index) => {
    if (agendaItems.length > 1) {
      setAgendaItems(agendaItems.filter((_, i) => i !== index));
    }
  };

  // Handle key decisions
  const handleDecisionChange = (index, value) => {
    const newDecisions = [...keyDecisions];
    newDecisions[index] = value;
    setKeyDecisions(newDecisions);
  };

  const handleAddDecision = () => {
    setKeyDecisions([...keyDecisions, '']);
  };

  const handleRemoveDecision = (index) => {
    if (keyDecisions.length > 1) {
      setKeyDecisions(keyDecisions.filter((_, i) => i !== index));
    }
  };

  // Generate AI draft
  const handleGenerateDraft = async () => {
    if (!selectedTrust?.trust_id) {
      toast.error('Please select a trust first');
      return;
    }

    setAiDrafting(true);
    try {
      const response = await fetchWithAuth('/guided-minutes/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          minutes_type: meetingType,
          meeting_date: format(meetingDate, 'yyyy-MM-dd'),
          participants: selectedParticipants,
          agenda_items: agendaItems.filter(a => a.trim()),
          key_decisions: keyDecisions.filter(d => d.trim()),
          additional_context: additionalContext.trim() || null
        })
      });

      if (response.ok) {
        const data = await response.json();
        setDraftResponse(data);
        setEditedDraft(data.draft_body);
        setEditedTitle(data.suggested_title);
        setStep(3);
        toast.success('Draft generated successfully');
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to generate draft');
      }
    } catch (error) {
      console.error('Error generating draft:', error);
      toast.error('Failed to generate draft. Please try again.');
    } finally {
      setAiDrafting(false);
    }
  };

  // Save the minutes
  const handleSave = async () => {
    if (!selectedTrust?.trust_id) {
      toast.error('Please select a trust first');
      return;
    }

    setSaving(true);
    try {
      // Determine if we need to create linked records
      const hasRecordsToCreate = recordsToCreate.length > 0 && 
        (createCompensationRecords || createDistributionRecords || createBenevolenceRecords);
      
      const endpoint = hasRecordsToCreate ? '/guided-minutes/save-with-records' : '/guided-minutes/save';
      
      const requestBody = {
        trust_id: selectedTrust.trust_id,
        minutes_type: meetingType,
        meeting_date: format(meetingDate, 'yyyy-MM-dd'),
        participants_text: selectedParticipants.join(', '),
        decisions_text: editedDraft
      };
      
      if (hasRecordsToCreate) {
        // Filter records by enabled toggles
        const filteredRecords = recordsToCreate.filter(r => {
          if (r.record_type === 'compensation' && !createCompensationRecords) return false;
          if (r.record_type === 'distribution' && !createDistributionRecords) return false;
          if (r.record_type === 'benevolence' && !createBenevolenceRecords) return false;
          return r.amount > 0 && r.recipient;
        });
        requestBody.records_to_create = filteredRecords;
      }
      
      const response = await fetchWithAuth(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });

      if (response.ok) {
        const data = await response.json();
        if (hasRecordsToCreate && data.created_records) {
          setCreatedRecordsCounts(data.created_records);
        }
        toast.success('Minutes saved successfully');
        setStep(4);
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to save minutes');
      }
    } catch (error) {
      console.error('Error saving minutes:', error);
      toast.error('Failed to save minutes. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Add a new record to create
  const handleAddRecord = (type) => {
    setRecordsToCreate([...recordsToCreate, {
      record_type: type,
      amount: 0,
      recipient: '',
      date: format(meetingDate, 'yyyy-MM-dd'),
      description: '',
      purpose_classification: type === 'distribution' ? 'hems_support' : undefined
    }]);
  };

  // Update a record
  const handleUpdateRecord = (index, field, value) => {
    const updated = [...recordsToCreate];
    updated[index] = { ...updated[index], [field]: value };
    setRecordsToCreate(updated);
  };

  // Remove a record
  const handleRemoveRecord = (index) => {
    setRecordsToCreate(recordsToCreate.filter((_, i) => i !== index));
  };

  // Navigation validation
  const canProceedToStep2 = meetingType && meetingDate && selectedParticipants.length > 0;
  const canProceedToStep3 = agendaItems.some(a => a.trim()) || keyDecisions.some(d => d.trim());
  const canSave = editedDraft.trim().length > 0;

  // Render stepper
  const renderStepper = () => (
    <div className="flex items-center justify-center mb-8" data-testid="guided-minutes-stepper">
      {STEPS.map((s, index) => (
        <div key={s.id} className="flex items-center">
          <div 
            className={`flex items-center justify-center w-10 h-10 border-2 ${
              step >= s.id 
                ? 'bg-navy dark:bg-gold border-navy dark:border-gold text-white dark:text-navy' 
                : 'border-navy/20 dark:border-white/20 text-navy/40 dark:text-white/40'
            }`}
            data-testid={`step-${s.id}-indicator`}
          >
            <s.icon className="w-5 h-5" />
          </div>
          <span className={`hidden sm:block ml-2 font-mono text-xs uppercase tracking-widest ${
            step >= s.id ? 'text-navy dark:text-gold' : 'text-navy/40 dark:text-white/40'
          }`}>
            {s.label}
          </span>
          {index < STEPS.length - 1 && (
            <div className={`w-8 sm:w-16 h-0.5 mx-2 ${
              step > s.id ? 'bg-navy dark:bg-gold' : 'bg-navy/20 dark:bg-white/20'
            }`} />
          )}
        </div>
      ))}
    </div>
  );

  // Render Step 1: Meeting Type & Date
  const renderStep1 = () => (
    <div className="space-y-6" data-testid="step-1-content">
      {/* Meeting Type */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-3 block">
          Meeting Type
        </Label>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {MEETING_TYPES.map(type => (
            <button
              key={type.value}
              onClick={() => setMeetingType(type.value)}
              className={`p-4 border text-left transition-all ${
                meetingType === type.value
                  ? 'border-navy dark:border-gold bg-navy/5 dark:bg-gold/5'
                  : 'border-navy/20 dark:border-white/20 hover:border-navy/40 dark:hover:border-white/40'
              }`}
              data-testid={`meeting-type-${type.value}`}
            >
              <div className="font-serif text-lg text-navy dark:text-gold">{type.label}</div>
              <div className="text-sm text-muted-foreground mt-1">{type.description}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Meeting Date */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-3 block">
          Meeting Date
        </Label>
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className="w-full justify-start text-left font-normal border-navy/20 dark:border-white/20"
              data-testid="meeting-date-picker"
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {meetingDate ? format(meetingDate, 'PPP') : 'Select date'}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="single"
              selected={meetingDate}
              onSelect={(date) => date && setMeetingDate(date)}
              initialFocus
            />
          </PopoverContent>
        </Popover>
      </div>

      {/* Participants */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-3 block">
          Participants
        </Label>
        
        {/* Known trustees from context */}
        {trustContext?.trustees?.length > 0 && (
          <div className="space-y-2 mb-4">
            <p className="text-sm text-muted-foreground">Select from known trustees:</p>
            <div className="flex flex-wrap gap-2">
              {trustContext.trustees.map(trustee => (
                <button
                  key={trustee}
                  onClick={() => handleParticipantToggle(trustee)}
                  className={`flex items-center gap-2 px-3 py-2 border transition-all ${
                    selectedParticipants.includes(trustee)
                      ? 'border-navy dark:border-gold bg-navy/5 dark:bg-gold/5'
                      : 'border-navy/20 dark:border-white/20 hover:border-navy/40'
                  }`}
                  data-testid={`participant-${trustee.replace(/\s+/g, '-').toLowerCase()}`}
                >
                  <div className={`w-4 h-4 border flex items-center justify-center ${
                    selectedParticipants.includes(trustee)
                      ? 'border-navy dark:border-gold bg-navy dark:bg-gold'
                      : 'border-navy/30 dark:border-white/30'
                  }`}>
                    {selectedParticipants.includes(trustee) && (
                      <CheckCircle className="w-3 h-3 text-white dark:text-navy" />
                    )}
                  </div>
                  <span className="text-sm">{trustee}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        
        {/* Add custom participant */}
        <div className="flex gap-2">
          <Input
            value={customParticipant}
            onChange={(e) => setCustomParticipant(e.target.value)}
            placeholder="Add another participant..."
            className="flex-1"
            onKeyDown={(e) => e.key === 'Enter' && handleAddCustomParticipant()}
            data-testid="custom-participant-input"
          />
          <Button
            variant="outline"
            onClick={handleAddCustomParticipant}
            disabled={!customParticipant.trim()}
            data-testid="add-participant-btn"
          >
            <Plus className="w-4 h-4" />
          </Button>
        </div>
        
        {/* Selected participants display */}
        {selectedParticipants.length > 0 && (
          <div className="mt-4 p-3 bg-subtle-bg dark:bg-slate-800 border border-navy/10 dark:border-white/10">
            <p className="text-xs font-mono uppercase tracking-widest text-navy/50 dark:text-white/50 mb-2">
              Selected ({selectedParticipants.length})
            </p>
            <div className="flex flex-wrap gap-2">
              {selectedParticipants.map(p => (
                <span 
                  key={p} 
                  className="inline-flex items-center gap-1 px-2 py-1 bg-navy/10 dark:bg-gold/10 text-sm"
                >
                  {p}
                  <button onClick={() => handleParticipantToggle(p)} className="text-navy/50 hover:text-navy dark:text-white/50 dark:hover:text-white">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  // Render Step 2: Agenda & Decisions
  const renderStep2 = () => (
    <div className="space-y-6" data-testid="step-2-content">
      <div className="p-4 bg-gold/10 dark:bg-gold/5 border border-gold/30">
        <div className="flex items-start gap-3">
          <Sparkles className="w-5 h-5 text-gold flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-navy dark:text-gold">Keep it simple</p>
            <p className="text-sm text-muted-foreground">
              Short bullet points are enough. AI will draft the formal language.
            </p>
          </div>
        </div>
      </div>

      {/* Agenda Items */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-3 block">
          <ListChecks className="w-4 h-4 inline mr-2" />
          Agenda Items (What was discussed?)
        </Label>
        <div className="space-y-2">
          {agendaItems.map((item, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={item}
                onChange={(e) => handleAgendaChange(index, e.target.value)}
                placeholder={`Agenda item ${index + 1}...`}
                className="flex-1"
                data-testid={`agenda-item-${index}`}
              />
              {agendaItems.length > 1 && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRemoveAgendaItem(index)}
                  className="text-red-500 hover:text-red-700"
                >
                  <X className="w-4 h-4" />
                </Button>
              )}
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={handleAddAgendaItem}
            className="mt-2"
            data-testid="add-agenda-btn"
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Agenda Item
          </Button>
        </div>
      </div>

      {/* Key Decisions */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-3 block">
          <CheckCircle className="w-4 h-4 inline mr-2" />
          Key Decisions (What was decided?)
        </Label>
        <div className="space-y-2">
          {keyDecisions.map((decision, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={decision}
                onChange={(e) => handleDecisionChange(index, e.target.value)}
                placeholder={`Decision ${index + 1}...`}
                className="flex-1"
                data-testid={`decision-item-${index}`}
              />
              {keyDecisions.length > 1 && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRemoveDecision(index)}
                  className="text-red-500 hover:text-red-700"
                >
                  <X className="w-4 h-4" />
                </Button>
              )}
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={handleAddDecision}
            className="mt-2"
            data-testid="add-decision-btn"
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Decision
          </Button>
        </div>
      </div>

      {/* Additional Context */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-3 block">
          <MessageSquare className="w-4 h-4 inline mr-2" />
          Additional Notes (Optional)
        </Label>
        <Textarea
          value={additionalContext}
          onChange={(e) => setAdditionalContext(e.target.value)}
          placeholder="Any other context or notes for the AI to consider..."
          rows={3}
          data-testid="additional-context"
        />
      </div>
    </div>
  );

  // Render Step 3: Review Draft
  const renderStep3 = () => (
    <div className="space-y-6" data-testid="step-3-content">
      {/* Cautions */}
      {draftResponse?.cautions?.length > 0 && (
        <div className="p-4 bg-gold/10 dark:bg-gold/5 border border-gold/30">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-gold flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-navy dark:text-gold mb-2">Review Notes</p>
              <ul className="text-sm text-muted-foreground space-y-1">
                {draftResponse.cautions.map((caution, i) => (
                  <li key={i}>• {caution}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Title */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-3 block">
          Title
        </Label>
        <Input
          value={editedTitle}
          onChange={(e) => setEditedTitle(e.target.value)}
          className="font-serif text-lg"
          data-testid="draft-title"
        />
      </div>

      {/* Draft Body */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70">
            Minutes Draft
          </Label>
          <Button
            variant="outline"
            size="sm"
            onClick={handleGenerateDraft}
            disabled={aiDrafting}
            data-testid="regenerate-draft-btn"
          >
            {aiDrafting ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-2" />
            )}
            Regenerate
          </Button>
        </div>
        <Textarea
          value={editedDraft}
          onChange={(e) => setEditedDraft(e.target.value)}
          rows={12}
          className="font-mono text-sm"
          data-testid="draft-body"
        />
      </div>

      {/* Create Tracking Records Section */}
      <div className="border border-navy/20 dark:border-white/20 p-4">
        <div className="flex items-center gap-2 mb-4">
          <DollarSign className="w-5 h-5 text-navy dark:text-gold" />
          <h3 className="font-mono text-sm uppercase tracking-widest text-navy dark:text-gold">
            Create Tracking Records from This Approved Decision
          </h3>
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          Optionally create compensation, distribution, or benevolence records that will be automatically linked to these minutes.
        </p>
        
        {/* Toggle switches */}
        <div className="space-y-3 mb-4">
          <div className="flex items-center justify-between p-3 bg-subtle-bg dark:bg-slate-800">
            <div className="flex items-center gap-3">
              <Wallet className="w-4 h-4 text-navy/60 dark:text-white/60" />
              <span className="text-sm">Compensation payment records</span>
            </div>
            <Switch
              checked={createCompensationRecords}
              onCheckedChange={setCreateCompensationRecords}
              data-testid="toggle-compensation"
            />
          </div>
          <div className="flex items-center justify-between p-3 bg-subtle-bg dark:bg-slate-800">
            <div className="flex items-center gap-3">
              <DollarSign className="w-4 h-4 text-navy/60 dark:text-white/60" />
              <span className="text-sm">Distribution records</span>
            </div>
            <Switch
              checked={createDistributionRecords}
              onCheckedChange={setCreateDistributionRecords}
              data-testid="toggle-distributions"
            />
          </div>
          {selectedTrust?.benevolence_enabled && (
            <div className="flex items-center justify-between p-3 bg-subtle-bg dark:bg-slate-800">
              <div className="flex items-center gap-3">
                <HeartHandshake className="w-4 h-4 text-navy/60 dark:text-white/60" />
                <span className="text-sm">Benevolence records</span>
              </div>
              <Switch
                checked={createBenevolenceRecords}
                onCheckedChange={setCreateBenevolenceRecords}
                data-testid="toggle-benevolence"
              />
            </div>
          )}
        </div>

        {/* Records to create */}
        {(createCompensationRecords || createDistributionRecords || createBenevolenceRecords) && (
          <div className="space-y-4">
            <div className="flex gap-2">
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

            {recordsToCreate.length > 0 && (
              <div className="space-y-3">
                {recordsToCreate.map((record, index) => (
                  <div 
                    key={index} 
                    className="p-3 border border-navy/10 dark:border-white/10 bg-white dark:bg-slate-900"
                    data-testid={`record-${index}`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-mono text-xs uppercase tracking-widest text-navy dark:text-gold flex items-center gap-2">
                        {record.record_type === 'compensation' && <Wallet className="w-3 h-3" />}
                        {record.record_type === 'distribution' && <DollarSign className="w-3 h-3" />}
                        {record.record_type === 'benevolence' && <HeartHandshake className="w-3 h-3" />}
                        {record.record_type}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveRecord(index)}
                        className="text-red-500 hover:text-red-700 h-6 w-6 p-0"
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div>
                        <Label className="text-xs text-muted-foreground">Amount ($)</Label>
                        <Input
                          type="number"
                          value={record.amount || ''}
                          onChange={(e) => handleUpdateRecord(index, 'amount', parseFloat(e.target.value) || 0)}
                          placeholder="0.00"
                          className="mt-1"
                          data-testid={`record-${index}-amount`}
                        />
                      </div>
                      <div>
                        <Label className="text-xs text-muted-foreground">Recipient</Label>
                        <Input
                          value={record.recipient || ''}
                          onChange={(e) => handleUpdateRecord(index, 'recipient', e.target.value)}
                          placeholder="Name"
                          className="mt-1"
                          data-testid={`record-${index}-recipient`}
                        />
                      </div>
                      <div>
                        <Label className="text-xs text-muted-foreground">Date</Label>
                        <Input
                          type="date"
                          value={record.date || format(meetingDate, 'yyyy-MM-dd')}
                          onChange={(e) => handleUpdateRecord(index, 'date', e.target.value)}
                          className="mt-1"
                          data-testid={`record-${index}-date`}
                        />
                      </div>
                    </div>
                    {record.record_type === 'distribution' && (
                      <div className="mt-3">
                        <Label className="text-xs text-muted-foreground">Purpose</Label>
                        <Select 
                          value={record.purpose_classification || 'hems_support'}
                          onValueChange={(val) => handleUpdateRecord(index, 'purpose_classification', val)}
                        >
                          <SelectTrigger className="mt-1" data-testid={`record-${index}-purpose`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {DISTRIBUTION_PURPOSES.map(p => (
                              <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                    <div className="mt-3">
                      <Label className="text-xs text-muted-foreground">Description (optional)</Label>
                      <Input
                        value={record.description || ''}
                        onChange={(e) => handleUpdateRecord(index, 'description', e.target.value)}
                        placeholder="Brief description..."
                        className="mt-1"
                        data-testid={`record-${index}-description`}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Disclaimer */}
      <div className="text-center">
        <p className="font-mono text-xs uppercase tracking-widest text-navy/40 dark:text-white/40">
          AI helps draft language; you are responsible for accuracy and legal sufficiency.
        </p>
      </div>
    </div>
  );

  // Render Step 4: Success
  const renderStep4 = () => (
    <div className="text-center py-12" data-testid="step-4-content">
      <div className="w-20 h-20 mx-auto mb-6 bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
        <CheckCircle className="w-10 h-10 text-green-600 dark:text-green-400" />
      </div>
      <h2 className="font-serif text-2xl text-navy dark:text-gold mb-4">Minutes Saved</h2>
      <p className="text-muted-foreground mb-4">
        Your meeting minutes have been saved successfully and are now available in your Minutes list.
      </p>
      
      {/* Show created records summary */}
      {createdRecordsCounts && (createdRecordsCounts.compensation > 0 || createdRecordsCounts.distribution > 0 || createdRecordsCounts.benevolence > 0) && (
        <div className="inline-flex flex-wrap justify-center gap-3 mb-8 p-4 bg-navy/5 dark:bg-gold/5 border border-navy/10 dark:border-gold/10">
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
        >
          <FileText className="w-4 h-4 mr-2" />
          View All Minutes
        </Button>
        <Button
          onClick={() => {
            setStep(1);
            setMeetingType('');
            setSelectedParticipants([]);
            setAgendaItems(['']);
            setKeyDecisions(['']);
            setAdditionalContext('');
            setDraftResponse(null);
            setEditedDraft('');
            setEditedTitle('');
            setCreateCompensationRecords(false);
            setCreateDistributionRecords(false);
            setCreateBenevolenceRecords(false);
            setRecordsToCreate([]);
            setCreatedRecordsCounts(null);
          }}
          className="btn-primary"
          data-testid="create-another-btn"
        >
          <Plus className="w-4 h-4 mr-2" />
          Create Another
        </Button>
      </div>
    </div>
  );

  // Loading state
  if (contextLoading) {
    return (
      <>
        <Sidebar />
        <main className="flex-1 ml-0 md:ml-64 min-h-screen bg-background">
          <div className="flex items-center justify-center min-h-screen">
            <Loader2 className="w-8 h-8 animate-spin text-navy dark:text-gold" />
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-64 min-h-screen bg-background">
        <div className="container mx-auto px-4 py-8 max-w-4xl">
          {/* Header */}
          <div className="mb-8">
            <button
              onClick={() => navigate('/minutes')}
              className="flex items-center gap-2 text-navy/60 dark:text-white/60 hover:text-navy dark:hover:text-white mb-4 font-mono text-xs uppercase tracking-widest"
              data-testid="back-to-minutes"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Minutes
            </button>
            <h1 className="font-serif text-3xl text-navy dark:text-gold">Guided Minutes</h1>
            <p className="text-muted-foreground mt-2">
              Answer a few questions and let AI draft your meeting minutes.
            </p>
            {trustContext && (
              <p className="text-sm text-navy/50 dark:text-white/50 mt-1">
                {trustContext.trust_name} • {trustContext.jurisdiction || 'No jurisdiction set'}
              </p>
            )}
          </div>

          {/* Stepper */}
          {renderStepper()}

          {/* Main Card */}
          <div className="border border-navy/20 dark:border-white/20 bg-white dark:bg-slate-900 p-6 md:p-8">
            {step === 1 && renderStep1()}
            {step === 2 && renderStep2()}
            {step === 3 && renderStep3()}
            {step === 4 && renderStep4()}
          </div>

          {/* Navigation Buttons */}
          {step < 4 && (
            <div className="flex justify-between mt-6">
              <Button
                variant="outline"
                onClick={() => setStep(Math.max(1, step - 1))}
                disabled={step === 1}
                data-testid="prev-step-btn"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back
              </Button>
              
              {step === 1 && (
                <Button
                  onClick={() => setStep(2)}
                  disabled={!canProceedToStep2}
                  className="btn-primary"
                  data-testid="next-step-btn"
                >
                  Next
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              )}
              
              {step === 2 && (
                <Button
                  onClick={handleGenerateDraft}
                  disabled={!canProceedToStep3 || aiDrafting}
                  className="btn-primary"
                  data-testid="generate-draft-btn"
                >
                  {aiDrafting ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4 mr-2" />
                      Generate Draft with AI
                    </>
                  )}
                </Button>
              )}
              
              {step === 3 && (
                <Button
                  onClick={handleSave}
                  disabled={!canSave || saving}
                  className="btn-primary"
                  data-testid="save-minutes-btn"
                >
                  {saving ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4 mr-2" />
                      Save Minutes
                    </>
                  )}
                </Button>
              )}
            </div>
          )}
        </div>
      </main>
    </>
  );
}
