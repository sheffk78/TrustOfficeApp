import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import {
  Clock,
  FileText,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Calendar,
  DollarSign,
  Users,
  Sparkles,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

const EVENT_TYPES = [
  { value: 'distribution', label: 'Distribution', icon: DollarSign, description: 'A distribution was made but not formally documented' },
  { value: 'compensation', label: 'Compensation', icon: Users, description: 'Trustee or manager compensation was paid without minutes' },
  { value: 'decision', label: 'Trustee Decision', icon: FileText, description: 'A trustee decision was made without formal minutes' },
  { value: 'governance_review', label: 'Governance Review', icon: CheckCircle2, description: 'An annual or quarterly review was conducted but not documented' },
  { value: 'entity_action', label: 'Entity Action', icon: Clock, description: 'An LLC or corporate action was taken without documentation' },
];

export default function RetroactiveMinutesPage() {
  const { selectedTrust } = useAuth();
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [success, setSuccess] = useState(null);
  const [error, setError] = useState(null);

  // Form state
  const [eventType, setEventType] = useState('');
  const [eventDate, setEventDate] = useState('');
  const [description, setDescription] = useState('');
  const [participants, setParticipants] = useState('');
  const [amount, setAmount] = useState('');
  const [recipient, setRecipient] = useState('');
  const [selectedEntityId, setSelectedEntityId] = useState('');

  useEffect(() => {
    if (selectedTrust) loadEntities();
  }, [selectedTrust]);

  const loadEntities = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/entities?trust_id=${selectedTrust.trust_id}`);
      if (res.ok) {
        const data = await res.json();
        setEntities(data.entities || []);
      }
    } catch (err) {
      console.error('Failed to load entities:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedTrust || !eventType || !eventDate || !description) {
      setError('Please fill in the event type, date, and description.');
      return;
    }

    setGenerating(true);
    setError(null);
    setSuccess(null);

    try {
      // Use the guided minutes API to generate retroactive minutes
      const contextRes = await fetchWithAuth(`/guided-minutes/context?trust_id=${selectedTrust.trust_id}`);
      const context = contextRes.ok ? await contextRes.json() : {};

      // Build the minutes request with retroactive date
      const payload = {
        trust_id: selectedTrust.trust_id,
        minutes_type: eventType,
        meeting_date: eventDate,
        is_retroactive: true,
        decisions: [description],
        attendees: participants ? participants.split(',').map(p => p.trim()) : (context.trustees || []),
        amount: amount ? parseFloat(amount) : null,
        recipient: recipient || null,
        entity_id: selectedEntityId || null,
        notes: `Retroactive minutes created on ${new Date().toISOString().split('T')[0]} for an event that occurred on ${eventDate}.`,
      };

      const res = await fetchWithAuth('/guided-minutes/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to generate retroactive minutes');
      }

      const draft = await res.json();

      // Now save the minutes
      const saveRes = await fetchWithAuth('/guided-minutes/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          minutes_type: eventType,
          meeting_date: eventDate,
          title: `Retroactive Minutes — ${EVENT_TYPES.find(t => t.value === eventType)?.label || eventType} — ${eventDate}`,
          decisions: [description],
          attendees: participants ? participants.split(',').map(p => p.trim()) : (context.trustees || []),
          content: draft.draft || draft.content || description,
          is_retroactive: true,
        }),
      });

      if (!saveRes.ok) {
        const errData = await saveRes.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to save retroactive minutes');
      }

      setSuccess('Retroactive minutes generated and saved successfully.');
      // Reset form
      setEventType('');
      setEventDate('');
      setDescription('');
      setParticipants('');
      setAmount('');
      setRecipient('');
      setSelectedEntityId('');
    } catch (err) {
      setError(err.message || 'Failed to generate retroactive minutes');
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!selectedTrust) {
    return (
      <div className="flex items-center justify-center min-h-screen text-muted-foreground">
        Select a trust to create retroactive minutes
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 p-4 md:p-8 overflow-y-auto">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Header */}
          <div>
            <h1 className="font-serif text-2xl md:text-3xl text-navy flex items-center gap-3">
              <Clock className="w-8 h-8" />
              Retroactive Minutes
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Document past trust actions that should have been formally recorded
            </p>
          </div>

          {/* Warning */}
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium text-amber-800">Why Retroactive Minutes Matter</p>
              <p className="text-amber-700 mt-1">
                If a trust action (distribution, compensation, decision) occurred without formal documentation, retroactive minutes create the record. 
                They show the action was ratified and properly documented — critical for audit defense and compliance.
              </p>
            </div>
          </div>

          {success && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-green-700">{success}</p>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex gap-3">
              <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {/* Event Type Selection */}
          <div className="card-trust">
            <h2 className="font-serif text-lg text-navy mb-4 flex items-center gap-2">
              <FileText className="w-5 h-5" /> What type of event needs documenting?
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {EVENT_TYPES.map(type => {
                const Icon = type.icon;
                const isSelected = eventType === type.value;
                return (
                  <button
                    key={type.value}
                    onClick={() => setEventType(type.value)}
                    className={`text-left p-4 rounded-lg border-2 transition-all ${
                      isSelected
                        ? 'border-navy bg-navy/5'
                        : 'border-slate-200 hover:border-slate-300 bg-white'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Icon className={`w-4 h-4 ${isSelected ? 'text-navy' : 'text-muted-foreground'}`} />
                      <span className={`font-medium text-sm ${isSelected ? 'text-navy' : 'text-slate-700'}`}>
                        {type.label}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">{type.description}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Event Details */}
          <div className="card-trust space-y-4">
            <h2 className="font-serif text-lg text-navy flex items-center gap-2">
              <Calendar className="w-5 h-5" /> When did this happen?
            </h2>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Date of Event</label>
              <input
                type="date"
                value={eventDate}
                onChange={e => setEventDate(e.target.value)}
                max={new Date().toISOString().split('T')[0]}
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-navy/20"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Related Entity (optional)</label>
              <select
                value={selectedEntityId}
                onChange={e => setSelectedEntityId(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-navy/20"
              >
                <option value="">Trust level (no specific entity)</option>
                {entities.map(entity => (
                  <option key={entity.entity_id} value={entity.entity_id}>
                    {entity.name} ({entity.entity_type})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">What happened?</label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Describe the action or decision that was made. e.g., 'Trustee approved a distribution of $5,000 to beneficiary John Smith for educational expenses'"
                rows={4}
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-navy/20 resize-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Who was present? (comma-separated)</label>
              <input
                type="text"
                value={participants}
                onChange={e => setParticipants(e.target.value)}
                placeholder="John Smith, Jane Doe"
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-navy/20"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Leave blank to auto-fill trustees from the trust
              </p>
            </div>
          </div>

          {/* Financial Details (for distribution/compensation) */}
          {(eventType === 'distribution' || eventType === 'compensation') && (
            <div className="card-trust space-y-4">
              <h2 className="font-serif text-lg text-navy flex items-center gap-2">
                <DollarSign className="w-5 h-5" /> Financial Details
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Amount ($)</label>
                  <input
                    type="number"
                    value={amount}
                    onChange={e => setAmount(e.target.value)}
                    placeholder="5000"
                    min="0"
                    step="0.01"
                    className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-navy/20"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Recipient</label>
                  <input
                    type="text"
                    value={recipient}
                    onChange={e => setRecipient(e.target.value)}
                    placeholder="John Smith"
                    className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-navy/20"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Submit */}
          <div className="flex justify-end">
            <Button
              onClick={handleGenerate}
              disabled={generating || !eventType || !eventDate || !description}
              className="bg-navy hover:bg-navy/90 text-white px-6"
            >
              {generating ? (
                <><RefreshCw className="w-4 h-4 mr-2 animate-spin" /> Generating...</>
              ) : (
                <><Sparkles className="w-4 h-4 mr-2" /> Generate Retroactive Minutes</>
              )}
            </Button>
          </div>
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}