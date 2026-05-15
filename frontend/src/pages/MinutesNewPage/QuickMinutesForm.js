import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import AiDraftPanel from './AiDraftPanel';

/**
 * QuickMinutesForm — Bullet-point + AI draft for simple meeting types
 * (Annual Review, Quarterly Review, General Meeting).
 *
 * Props:
 *   section           — current section object
 *   sectionIndex       — number
 *   onFieldChange     — (sectionIndex, field, value) => void
 *   selectedTrust     — from AuthContext
 *   meetingDate        — Date
 *   participants       — string[]
 *   onAiDraftGenerated — (sectionIndex, draftBody, suggestedTitle) => void
 */
export default function QuickMinutesForm({
  section,
  sectionIndex,
  onFieldChange,
  selectedTrust,
  meetingDate,
  participants,
  onAiDraftGenerated
}) {
  const fd = section.formData || {};

  const handleAiDraftGenerated = (draftBody, suggestedTitle) => {
    if (onAiDraftGenerated) onAiDraftGenerated(sectionIndex, draftBody, suggestedTitle);
  };

  return (
    <div className="space-y-5">
      {/* Agenda Items */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-2 block">
          Agenda Items
        </Label>
        <Textarea
          value={fd.agendaItems || ''}
          onChange={(e) => onFieldChange(sectionIndex, 'agendaItems', e.target.value)}
          placeholder="• Review previous meeting minutes&#10;• Financial update&#10;• Upcoming decisions"
          className="min-h-[100px]"
        />
        <p className="text-xs text-muted-foreground mt-1">One item per line. Use bullet points for clarity.</p>
      </div>

      {/* Key Decisions */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-2 block">
          Key Decisions
        </Label>
        <Textarea
          value={fd.keyDecisions || ''}
          onChange={(e) => onFieldChange(sectionIndex, 'keyDecisions', e.target.value)}
          placeholder="• Approved distribution of $X to beneficiary&#10;• Adopted new investment policy"
          className="min-h-[100px]"
        />
        <p className="text-xs text-muted-foreground mt-1">One decision per line.</p>
      </div>

      {/* Notes / Additional Context */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-2 block">
          Notes & Additional Context
        </Label>
        <Textarea
          value={fd.notes || ''}
          onChange={(e) => onFieldChange(sectionIndex, 'notes', e.target.value)}
          placeholder="Any additional context, rationale, or background information..."
          className="min-h-[80px]"
        />
      </div>

      {/* AI Draft Panel */}
      <AiDraftPanel
        selectedTrust={selectedTrust}
        minutesType={section.templateType}
        meetingDate={meetingDate}
        participants={participants}
        agendaItems={(fd.agendaItems || '').split('\n').filter(s => s.trim())}
        keyDecisions={(fd.keyDecisions || '').split('\n').filter(s => s.trim())}
        additionalContext={fd.notes || ''}
        onDraftGenerated={handleAiDraftGenerated}
        value={section.aiDraftText || ''}
        onChange={(val) => onFieldChange(sectionIndex, 'aiDraftText', val)}
      />
    </div>
  );
}