import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertTriangle, Sparkles, Undo2, Loader2 } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';

/**
 * AI Draft Panel — generates a draft from context, supports undo.
 *
 * Props:
 *   selectedTrust  — trust object from AuthContext
 *   minutesType    — string template type key
 *   meetingDate     — Date
 *   participants    — string[]
 *   agendaItems     — string[] (for quick minutes)
 *   keyDecisions    — string[] (for quick minutes)
 *   templateFields  — object (for template-based minutes)
 *   additionalContext — string
 *   onDraftGenerated — (draftBody, suggestedTitle) => void
 *   value           — current draft text (controlled)
 *   onChange        — (newText) => void
 */
export default function AiDraftPanel({
  selectedTrust,
  minutesType,
  meetingDate,
  participants,
  agendaItems,
  keyDecisions,
  templateFields,
  additionalContext,
  onDraftGenerated,
  value,
  onChange
}) {
  const [drafting, setDrafting] = useState(false);
  const [undoStack, setUndoStack] = useState([]); // stack of previous values

  const handleDraft = useCallback(async () => {
    if (!selectedTrust?.trust_id) {
      toast.error('Please select a trust first');
      return;
    }

    // Save current value for undo before generating
    setUndoStack(prev => [...prev, value || '']);
    setDrafting(true);

    try {
      const decisionsOutline = keyDecisions
        ? keyDecisions.filter(d => d?.trim())
        : [];

      if (decisionsOutline.length === 0 && (!value || !value.trim())) {
        decisionsOutline.push(`Review and document ${minutesType || 'meeting'} proceedings`);
      }

      let extraContext = additionalContext || '';
      if (value?.trim()) {
        extraContext = `USER'S EXISTING DRAFT:\n${value.trim()}\n\n${extraContext}`;
      }
      if (templateFields && Object.keys(templateFields).length > 0) {
        extraContext += `\n\nTEMPLATE FIELD VALUES:\n${JSON.stringify(templateFields, null, 2)}`;
      }

      const res = await fetchWithAuth('/ai/minutes-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          minutes_type: minutesType || 'general',
          meeting_date: meetingDate ? meetingDate.toISOString().split('T')[0] : new Date().toISOString().split('T')[0],
          participants: participants || [],
          decisions_outline: decisionsOutline,
          trust_name: selectedTrust.name,
          jurisdiction: selectedTrust.jurisdiction || null,
          beneficiary_standard: selectedTrust.beneficiary_standard || null,
          additional_context: extraContext || null
        })
      });

      if (res.ok) {
        const data = await res.json();
        if (onDraftGenerated) onDraftGenerated(data.draft_body, data.suggested_title);
        onChange(data.draft_body || '');
        toast.success('AI draft generated');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'AI assistant is currently unavailable.');
      }
    } catch {
      toast.error('Unable to connect to AI service. You can still draft manually.');
    } finally {
      setDrafting(false);
    }
  }, [selectedTrust, minutesType, meetingDate, participants, keyDecisions, additionalContext, templateFields, value, onChange, onDraftGenerated]);

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0) return;
    const prev = undoStack[undoStack.length - 1];
    setUndoStack(stack => stack.slice(0, -1));
    onChange(prev);
    toast.info('AI draft reverted');
  }, [undoStack, onChange]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
          <Sparkles className="w-4 h-4" />
          AI Draft
        </span>
        <div className="flex gap-2">
          {undoStack.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleUndo}
              className="text-xs flex items-center gap-1.5"
            >
              <Undo2 className="w-3 h-3" />
              Undo
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleDraft}
            disabled={drafting || !selectedTrust}
            className="text-xs flex items-center gap-1.5 border-gold/50 text-gold hover:bg-gold/10 hover:text-gold disabled:opacity-50"
          >
            {drafting ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="w-3 h-3" />
                {value?.trim() ? 'Improve with AI' : 'Draft with AI'}
              </>
            )}
          </Button>
        </div>
      </div>

      {drafting && (
        <div className="space-y-2">
          <Skeleton className="h-6 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      )}

      <Textarea
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Write your notes here... AI will help formalize them."
        className="min-h-[180px]"
        disabled={drafting}
      />

      <div className="flex items-start gap-2 p-2.5 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-md">
        <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
        <span className="text-xs text-amber-700 dark:text-amber-300">
          AI-generated — review carefully before saving. You are responsible for the accuracy of all content.
        </span>
      </div>
    </div>
  );
}