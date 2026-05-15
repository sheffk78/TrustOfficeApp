import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import { 
  ArrowLeft, 
  ArrowRight,
  Calendar as CalendarIcon,
  Users,
  FileText,
  CheckCircle,
  X,
  Sparkles,
  Loader2,
  AlertTriangle,
  Copy
} from 'lucide-react';
import { format } from 'date-fns';

export default function NewMinutesPage() {
  const navigate = useNavigate();
  const { selectedTrust, isReadOnly } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  
  // Redirect /minutes/new to /minutes/create (preserves deep links)
  useEffect(() => {
    navigate('/minutes/create', { replace: true });
  }, [navigate]);
  
  // AI Drafting state
  const [aiDrafting, setAiDrafting] = useState(false);
  const [aiDraftModalOpen, setAiDraftModalOpen] = useState(false);
  const [aiDraft, setAiDraft] = useState(null);
  const [aiError, setAiError] = useState(null); // Inline error state for AI
  
  const [formData, setFormData] = useState({
    entry_type: '',
    date: new Date(),
    participants: [''],
    summary: '',
    details: '',
    best_interest_rationale: ''
  });

  // Redirect read-only users to minutes list with message
  useEffect(() => {
    if (isReadOnly) {
      navigate('/minutes');
    }
  }, [isReadOnly, navigate]);

  const handleAddParticipant = () => {
    setFormData({
      ...formData,
      participants: [...formData.participants, '']
    });
  };

  const handleRemoveParticipant = (index) => {
    if (formData.participants.length > 1) {
      setFormData({
        ...formData,
        participants: formData.participants.filter((_, i) => i !== index)
      });
    }
  };

  const handleParticipantChange = (index, value) => {
    const newParticipants = [...formData.participants];
    newParticipants[index] = value;
    setFormData({ ...formData, participants: newParticipants });
  };

  const canProceed = () => {
    switch (step) {
      case 1:
        return !!formData.entry_type;
      case 2:
        return !!formData.date;
      case 3:
        return formData.participants.some(p => p.trim() !== '');
      case 4:
        return formData.summary.trim() !== '' && formData.details.trim() !== '';
      default:
        return true;
    }
  };

  // AI Draft function - enhances user's existing draft or creates new one
  const handleDraftWithAI = async () => {
    if (!selectedTrust) {
      toast.error('Please select a trust first');
      return;
    }

    // Clear previous error
    setAiError(null);

    // Combine summary and details for better context
    // The user's existing details are the PRIMARY content to enhance
    const userDraft = formData.details?.trim() || '';
    const summaryNotes = formData.summary?.trim() || '';
    
    // Extract decision points from summary (split by newlines or periods)
    const decisionsOutline = summaryNotes
      ? summaryNotes.split(/[.\n]+/).map(s => s.trim()).filter(s => s.length > 0)
      : [];
    
    // If no summary yet, use entry type as a placeholder
    if (decisionsOutline.length === 0 && !userDraft) {
      decisionsOutline.push(`Review and document ${formData.entry_type || 'meeting'} proceedings`);
    }

    // Build additional context that includes the user's draft prominently
    let additionalContext = '';
    if (userDraft) {
      additionalContext = `USER'S DRAFT TO IMPROVE AND EXPAND:\n${userDraft}`;
      if (formData.best_interest_rationale) {
        additionalContext += `\n\nBEST INTEREST RATIONALE:\n${formData.best_interest_rationale}`;
      }
    } else if (formData.best_interest_rationale) {
      additionalContext = formData.best_interest_rationale;
    }

    setAiDrafting(true);
    try {
      const response = await fetchWithAuth('/ai/minutes-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          minutes_type: formData.entry_type || 'general',
          meeting_date: formData.date.toISOString().split('T')[0],
          participants: formData.participants.filter(p => p.trim() !== ''),
          decisions_outline: decisionsOutline,
          trust_name: selectedTrust.name,
          jurisdiction: selectedTrust.jurisdiction || null,
          beneficiary_standard: selectedTrust.beneficiary_standard || null,
          additional_context: additionalContext || null
        })
      });

      if (response.ok) {
        const data = await response.json();
        setAiDraft(data);
        setAiDraftModalOpen(true);
        setAiError(null);
      } else {
        const error = await response.json().catch(() => ({}));
        const errorMessage = error.detail || 'AI assistant is currently unavailable.';
        setAiError(errorMessage);
        // Don't use toast - show inline error instead
        console.error('AI draft error:', errorMessage);
      }
    } catch (error) {
      console.error('AI draft error:', error);
      setAiError('Unable to connect to AI service. You can still draft manually.');
    } finally {
      setAiDrafting(false);
    }
  };

  // Insert AI draft into form
  const handleInsertDraft = () => {
    if (aiDraft) {
      setFormData(prev => ({
        ...prev,
        summary: aiDraft.suggested_title || prev.summary,
        details: aiDraft.draft_body || prev.details
      }));
      setAiDraftModalOpen(false);
      toast.success('AI draft inserted. Please review and edit as needed.');
    }
  };

  const handleSubmit = async () => {
    if (!selectedTrust) {
      toast.error('Please select a trust first');
      return;
    }

    setLoading(true);
    try {
      const response = await fetchWithAuth('/minutes', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          entry_type: formData.entry_type,
          date: formData.date.toISOString(),
          participants: formData.participants.filter(p => p.trim() !== ''),
          summary: formData.summary,
          details: formData.details,
          best_interest_rationale: formData.best_interest_rationale || null
        })
      });

      if (!response.ok) {
        throw new Error('Failed to create minutes');
      }

      toast.success('Minutes created successfully');
      navigate('/minutes');
    } catch (error) {
      console.error('Failed to create minutes:', error);
      toast.error('Failed to create minutes');
    } finally {
      setLoading(false);
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout" data-testid="new-minutes-page">
        <Sidebar />
        <main className="main-content">
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
    <div className="main-layout" data-testid="new-minutes-page">
      <Sidebar />
      <main className="main-content">
        <div className="page-container max-w-2xl mx-auto">
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
            <h1 className="font-serif text-3xl text-navy">Create Minutes</h1>
            <p className="text-sm text-muted-foreground mt-1">{selectedTrust?.name}</p>
          </div>

          {/* Progress Steps */}
          <div className="mb-8">
            <div className="flex items-center justify-between">
              {[1, 2, 3, 4, 5].map((s) => (
                <div 
                  key={s}
                  className={`flex items-center justify-center w-8 h-8 text-sm font-mono transition-colors ${
                    s === step ? 'bg-navy text-white' : 
                    s < step ? 'bg-success text-white' : 
                    'bg-navy/10 text-muted-foreground'
                  }`}
                >
                  {s < step ? '✓' : s}
                </div>
              ))}
            </div>
          </div>

          {/* Form Steps */}
          <div className="card-trust corner-mark">
            {/* Step 1: Entry Type */}
            {step === 1 && (
              <div>
                <p className="label-trust mb-2">Step 1 of 5</p>
                <h2 className="font-serif text-2xl text-navy mb-6">What type of entry?</h2>
                
                <div className="grid grid-cols-2 gap-4">
                  {['annual', 'quarterly', 'distribution', 'compensation', 'solvency', 'special'].map((type) => (
                    <button
                      key={type}
                      onClick={() => setFormData({ ...formData, entry_type: type })}
                      className={`p-4 border text-left transition-all ${
                        formData.entry_type === type 
                          ? 'border-gold bg-gold/10' 
                          : 'border-navy/20 hover:border-navy/40'
                      }`}
                      data-testid={`entry-type-${type}`}
                    >
                      <span className="font-serif text-navy capitalize">{type}</span>
                      <p className="text-xs text-muted-foreground mt-1">
                        {type === 'annual' && 'Annual trust review'}
                        {type === 'quarterly' && 'Quarterly governance meeting'}
                        {type === 'distribution' && 'Distribution decision'}
                        {type === 'compensation' && 'Trustee compensation review'}
                        {type === 'solvency' && 'Solvency confirmation'}
                        {type === 'special' && 'Special resolution'}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Step 2: Date */}
            {step === 2 && (
              <div>
                <p className="label-trust mb-2">Step 2 of 5</p>
                <h2 className="font-serif text-2xl text-navy mb-6">When did this occur?</h2>
                
                <Popover>
                  <PopoverTrigger asChild>
                    <Button 
                      variant="outline" 
                      className="w-full justify-start btn-secondary"
                      data-testid="date-picker-btn"
                    >
                      <CalendarIcon className="mr-2 h-4 w-4" />
                      {formData.date ? format(formData.date, 'MMMM d, yyyy') : 'Select date'}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      mode="single"
                      selected={formData.date}
                      onSelect={(date) => setFormData({ ...formData, date: date || new Date() })}
                      initialFocus
                    />
                  </PopoverContent>
                </Popover>
              </div>
            )}

            {/* Step 3: Participants */}
            {step === 3 && (
              <div>
                <p className="label-trust mb-2">Step 3 of 5</p>
                <h2 className="font-serif text-2xl text-navy mb-6">Who was involved?</h2>
                
                <div className="space-y-3">
                  {formData.participants.map((participant, index) => (
                    <div key={index} className="flex gap-2">
                      <div className="relative flex-1">
                        <Users className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <Input
                          value={participant}
                          onChange={(e) => handleParticipantChange(index, e.target.value)}
                          placeholder="Participant name"
                          className="pl-10 input-trust"
                          data-testid={`participant-${index}`}
                        />
                      </div>
                      {formData.participants.length > 1 && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleRemoveParticipant(index)}
                          className="text-muted-foreground hover:text-error"
                        >
                          <X className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>

                <Button
                  variant="outline"
                  onClick={handleAddParticipant}
                  className="mt-4 btn-secondary"
                  data-testid="add-participant-btn"
                >
                  + Add Participant
                </Button>
              </div>
            )}

            {/* Step 4: Details with AI Draft Button */}
            {step === 4 && (
              <div>
                <p className="label-trust mb-2">Step 4 of 5</p>
                <h2 className="font-serif text-2xl text-navy mb-6">What was decided?</h2>
                
                <div className="space-y-6">
                  <div>
                    <Label className="label-trust">Summary *</Label>
                    <Input
                      value={formData.summary}
                      onChange={(e) => setFormData({ ...formData, summary: e.target.value })}
                      placeholder="Brief summary of the entry"
                      className="mt-1 input-trust"
                      data-testid="summary-input"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <Label className="label-trust">Details *</Label>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleDraftWithAI}
                        disabled={aiDrafting || !selectedTrust}
                        className="text-xs flex items-center gap-1.5 border-gold/50 text-gold hover:bg-gold/10 hover:text-gold disabled:opacity-50 disabled:cursor-not-allowed"
                        data-testid="draft-with-ai-btn"
                        title="AI will improve and formalize your notes below"
                      >
                        {aiDrafting ? (
                          <>
                            <Loader2 className="w-3 h-3 animate-spin" />
                            Improving...
                          </>
                        ) : (
                          <>
                            <Sparkles className="w-3 h-3" />
                            {formData.details?.trim() ? 'Improve with AI' : 'Draft with AI'}
                          </>
                        )}
                      </Button>
                    </div>
                    
                    {/* Inline AI error - does not block manual drafting */}
                    {aiError && (
                      <div className="mb-2 p-2 bg-warning/10 border border-warning/30 text-xs text-warning flex items-start gap-2" data-testid="ai-error-inline">
                        <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                        <span>{aiError}</span>
                      </div>
                    )}
                    
                    <Textarea
                      value={formData.details}
                      onChange={(e) => setFormData({ ...formData, details: e.target.value })}
                      placeholder="Write your notes here... AI will improve and formalize them when you click the button above."
                      className="mt-1 input-trust min-h-[150px]"
                      data-testid="details-input"
                    />
                    <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1 font-mono">
                      <Sparkles className="w-3 h-3" />
                      Write your notes, then click "{formData.details?.trim() ? 'Improve with AI' : 'Draft with AI'}" to formalize them. You remain responsible for accuracy.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Step 5: Best Interest Rationale */}
            {step === 5 && (
              <div>
                <p className="label-trust mb-2">Step 5 of 5</p>
                <h2 className="font-serif text-2xl text-navy mb-6">Why is this in the best interest?</h2>
                <p className="text-sm text-muted-foreground mb-6">
                  Document the reasoning behind this decision to demonstrate prudent trust management.
                </p>
                
                <div>
                  <Label className="label-trust">Best Interest Rationale (Optional)</Label>
                  <Textarea
                    value={formData.best_interest_rationale}
                    onChange={(e) => setFormData({ ...formData, best_interest_rationale: e.target.value })}
                    placeholder="Explain why this action is in the best interest of the trust and beneficiaries..."
                    className="mt-1 input-trust min-h-[150px]"
                    data-testid="rationale-input"
                  />
                </div>
              </div>
            )}

            {/* Navigation */}
            <div className="flex items-center justify-between mt-8 pt-6 border-t border-navy/10">
              {step > 1 ? (
                <Button
                  variant="ghost"
                  onClick={() => setStep(step - 1)}
                  className="btn-secondary"
                >
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Back
                </Button>
              ) : (
                <div></div>
              )}

              {step < 5 ? (
                <Button
                  onClick={() => setStep(step + 1)}
                  disabled={!canProceed()}
                  className="btn-primary"
                  data-testid="next-step-btn"
                >
                  Continue
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              ) : (
                <Button
                  onClick={handleSubmit}
                  disabled={loading || !canProceed()}
                  className="btn-gold"
                  data-testid="submit-minutes-btn"
                >
                  {loading ? 'Saving...' : 'Save Minutes'}
                  <CheckCircle className="w-4 h-4 ml-2" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </main>
      <MobileBottomNav />

      {/* AI Draft Modal */}
      <Dialog open={aiDraftModalOpen} onOpenChange={setAiDraftModalOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col" data-testid="ai-draft-modal">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-navy flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-gold" />
              AI Draft
            </DialogTitle>
            <DialogDescription>
              Review the AI-generated minutes below. Edit as needed after inserting.
            </DialogDescription>
          </DialogHeader>
          
          {aiDraft && (
            <div className="flex-1 overflow-auto space-y-4">
              {/* Cautions */}
              {aiDraft.cautions && aiDraft.cautions.length > 0 && (
                <div className="p-3 bg-warning/10 border border-warning/30">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-warning flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="font-mono text-xs uppercase tracking-widest text-warning mb-1">Review Before Use</p>
                      <ul className="text-xs text-warning/80 space-y-1">
                        {aiDraft.cautions.map((caution, i) => (
                          <li key={i}>• {caution}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}
              
              {/* Suggested Title */}
              <div>
                <Label className="label-trust">Suggested Title</Label>
                <p className="mt-1 p-3 bg-navy/5 border border-navy/10 font-medium text-navy">
                  {aiDraft.suggested_title}
                </p>
              </div>
              
              {/* Draft Body */}
              <div>
                <Label className="label-trust">Draft Content</Label>
                <div className="mt-1 p-4 bg-navy/5 border border-navy/10 max-h-[300px] overflow-auto">
                  <pre className="whitespace-pre-wrap font-serif text-sm text-navy leading-relaxed">
                    {aiDraft.draft_body}
                  </pre>
                </div>
              </div>
            </div>
          )}
          
          <DialogFooter className="border-t pt-4 mt-4">
            <p className="text-xs text-muted-foreground mr-auto flex items-center gap-1">
              <Sparkles className="w-3 h-3" />
              AI-generated. Review before signing.
            </p>
            <Button variant="outline" onClick={() => setAiDraftModalOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleInsertDraft}
              className="btn-gold flex items-center gap-2"
              data-testid="insert-draft-btn"
            >
              <Copy className="w-4 h-4" />
              Insert Draft
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
