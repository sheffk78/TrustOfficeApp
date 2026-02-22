import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import { 
  ArrowLeft, 
  ArrowRight,
  Calendar as CalendarIcon,
  Users,
  FileText,
  CheckCircle,
  X
} from 'lucide-react';
import { format } from 'date-fns';

export default function NewMinutesPage() {
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  
  const [formData, setFormData] = useState({
    entry_type: '',
    date: new Date(),
    participants: [''],
    summary: '',
    details: '',
    best_interest_rationale: ''
  });

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

      toast.success('Minutes recorded successfully');
      navigate('/minutes');
    } catch (error) {
      toast.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  const entryTypes = [
    { value: 'meeting', label: 'Meeting', description: 'Regular trust meeting or review session' },
    { value: 'decision', label: 'Decision', description: 'Specific decision or resolution' },
    { value: 'distribution_approval', label: 'Distribution Approval', description: 'Approval of a distribution request' }
  ];

  return (
    <div className="main-layout" data-testid="new-minutes-page">
      <Sidebar />
      <main className="main-content">
        <div className="page-container max-w-3xl">
          {/* Back button */}
          <button 
            onClick={() => navigate('/minutes')}
            className="flex items-center gap-2 text-muted-foreground hover:text-navy mb-6"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="font-mono text-xs uppercase tracking-widest">Back to Minutes</span>
          </button>

          {/* Page Header */}
          <div className="page-header">
            <h1 className="page-title">Record Minutes</h1>
            <p className="page-subtitle">
              {selectedTrust?.name || 'Select a trust'}
            </p>
          </div>

          {/* Progress */}
          <div className="wizard-steps mb-8">
            {[1, 2, 3, 4, 5].map((s) => (
              <div 
                key={s} 
                className={`wizard-step ${step >= s ? 'active' : ''} ${step > s ? 'completed' : ''}`}
              ></div>
            ))}
          </div>

          <div className="card-trust corner-mark">
            {/* Step 1: Entry Type */}
            {step === 1 && (
              <div>
                <p className="label-trust mb-2">Step 1 of 5</p>
                <h2 className="font-serif text-2xl text-navy mb-6">What type of entry is this?</h2>
                
                <div className="space-y-3">
                  {entryTypes.map((type) => (
                    <button
                      key={type.value}
                      onClick={() => setFormData({ ...formData, entry_type: type.value })}
                      className={`w-full p-4 border text-left hover-lift ${
                        formData.entry_type === type.value 
                          ? 'border-gold bg-gold/5' 
                          : 'border-navy/10 hover:border-navy/30'
                      }`}
                      data-testid={`entry-type-${type.value}`}
                    >
                      <div className="flex items-center gap-4">
                        <div className={`w-10 h-10 flex items-center justify-center ${
                          formData.entry_type === type.value ? 'bg-gold/20' : 'bg-navy/5'
                        }`}>
                          <FileText className={`w-5 h-5 ${
                            formData.entry_type === type.value ? 'text-gold' : 'text-navy'
                          }`} />
                        </div>
                        <div>
                          <p className="font-medium text-navy">{type.label}</p>
                          <p className="text-sm text-muted-foreground">{type.description}</p>
                        </div>
                      </div>
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
                      className="w-full justify-start text-left font-mono input-trust h-12"
                      data-testid="date-picker-trigger"
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

            {/* Step 4: Details */}
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
                    <Label className="label-trust">Details *</Label>
                    <Textarea
                      value={formData.details}
                      onChange={(e) => setFormData({ ...formData, details: e.target.value })}
                      placeholder="Full details of the meeting, decision, or approval..."
                      className="mt-1 input-trust min-h-[150px]"
                      data-testid="details-input"
                    />
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
    </div>
  );
}
