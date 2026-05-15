import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { AlertTriangle, CheckCircle, Save, FileText, Calendar, Users, Clock } from 'lucide-react';
import { format } from 'date-fns';

/**
 * Step 3: Review & Save
 *
 * Props:
 *   sections           — array of section objects
 *   commonFields        — { meetingDate, selectedTrustees, otherAttendees, meetingLocation }
 *   retroactive         — boolean
 *   retroactiveData      — { reason, participantsConfirmation, bestInterest }
 *   onSave              — (status: 'finalized' | 'draft') => void
 *   saving              — boolean
 *   fullDraftText        — string, combined minutes text
 *   onFullDraftTextChange — (newText) => void
 *   hasAiContent        — boolean
 */
export default function Step3ReviewAndSave({
  sections,
  commonFields,
  retroactive,
  retroactiveData,
  onSave,
  saving,
  fullDraftText,
  onFullDraftTextChange,
  hasAiContent
}) {
  const trusteeCount = (commonFields.selectedTrustees || []).length;
  const meetingDateStr = commonFields.meetingDate
    ? format(commonFields.meetingDate, 'MMMM d, yyyy')
    : 'Not set';

  return (
    <div className="space-y-6" data-testid="step3-review">
      {/* Review Checklist */}
      <div className="p-5 border border-navy/10 dark:border-white/10 rounded-lg">
        <h3 className="font-mono text-xs uppercase tracking-widest text-navy/50 dark:text-white/50 mb-4">
          Review Checklist
        </h3>
        <div className="space-y-3">
          {/* Meeting Date */}
          <div className="flex items-center gap-3 text-sm">
            <Calendar className="w-4 h-4 text-navy/50 dark:text-white/50 flex-shrink-0" />
            <span className="text-muted-foreground">Meeting Date:</span>
            <span className="font-medium text-navy dark:text-gold">{meetingDateStr}</span>
          </div>

          {/* Trustees */}
          <div className="flex items-center gap-3 text-sm">
            <Users className="w-4 h-4 text-navy/50 dark:text-white/50 flex-shrink-0" />
            <span className="text-muted-foreground">Trustees Present:</span>
            <span className="font-medium text-navy dark:text-gold">{trusteeCount} trustee{trusteeCount !== 1 ? 's' : ''}</span>
          </div>

          {/* Other Attendees */}
          {(commonFields.otherAttendees || []).length > 0 && (
            <div className="flex items-center gap-3 text-sm">
              <Users className="w-4 h-4 text-navy/50 dark:text-white/50 flex-shrink-0" />
              <span className="text-muted-foreground">Other Attendees:</span>
              <span className="font-medium text-navy dark:text-gold">{commonFields.otherAttendees.join(', ')}</span>
            </div>
          )}

          {/* Location */}
          {commonFields.meetingLocation && (
            <div className="flex items-center gap-3 text-sm">
              <FileText className="w-4 h-4 text-navy/50 dark:text-white/50 flex-shrink-0" />
              <span className="text-muted-foreground">Location:</span>
              <span className="font-medium text-navy dark:text-gold">{commonFields.meetingLocation}</span>
            </div>
          )}

          {/* Section types */}
          {sections.map((section, idx) => (
            <div key={section.id} className="flex items-center gap-3 text-sm">
              <CheckCircle className={`w-4 h-4 flex-shrink-0 ${section.aiDraftText ? 'text-amber-500' : 'text-green-600'}`} />
              <span className="text-muted-foreground">Section {idx + 1}:</span>
              <span className="font-medium text-navy dark:text-gold">{section.templateName || section.templateType}</span>
              {section.aiDraftText && (
                <span className="text-xs text-amber-600 font-mono">(AI draft)</span>
              )}
            </div>
          ))}

          {/* Retroactive indicator */}
          {retroactive && (
            <div className="flex items-center gap-3 text-sm">
              <Clock className="w-4 h-4 text-amber-500 flex-shrink-0" />
              <span className="text-amber-600 font-medium">Retroactive entry</span>
            </div>
          )}
        </div>
      </div>

      {/* AI Content Warning */}
      {hasAiContent && (
        <div className="flex items-start gap-2 p-3 bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-800 rounded-lg">
          <AlertTriangle className="w-4 h-4 text-orange-600 dark:text-orange-400 flex-shrink-0 mt-0.5" />
          <span className="text-sm text-orange-700 dark:text-orange-300">
            This minutes entry contains AI-generated content. Please review all sections carefully before finalizing.
          </span>
        </div>
      )}

      {/* Retroactive Warning */}
      {retroactive && commonFields.meetingDate && (
        <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg">
          <Clock className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <span className="text-sm text-amber-700 dark:text-amber-300">
            <strong>Retroactive entry:</strong> Meeting date ({meetingDateStr}) precedes the creation date ({format(new Date(), 'MMMM d, yyyy')}). Ensure all retroactive justification fields are complete.
          </span>
        </div>
      )}

      {/* Full Minutes Text Preview */}
      <div>
        <Label className="font-mono text-xs uppercase tracking-widest text-navy/50 dark:text-white/50 mb-2 block">
          Full Minutes Text
        </Label>
        <Textarea
          value={fullDraftText || ''}
          onChange={(e) => onFullDraftTextChange(e.target.value)}
          className="min-h-[200px] font-mono text-sm"
        />
        <p className="text-xs text-muted-foreground mt-1 italic">
          We recommend editing form fields in Step 2 instead of directly modifying this text.
        </p>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row gap-3 pt-4 border-t border-navy/10 dark:border-white/10">
        <Button
          onClick={() => onSave('finalized')}
          disabled={saving}
          className="flex-1 bg-navy dark:bg-gold text-white dark:text-navy hover:bg-navy/90 dark:hover:bg-gold/90"
        >
          <CheckCircle className="w-4 h-4 mr-2" />
          {saving ? 'Saving...' : 'Save Minutes'}
        </Button>
        <Button
          variant="outline"
          onClick={() => onSave('draft')}
          disabled={saving}
          className="flex-1 border-navy/20 dark:border-white/20"
        >
          <Save className="w-4 h-4 mr-2" />
          {saving ? 'Saving...' : 'Save as Draft'}
        </Button>
      </div>
    </div>
  );
}