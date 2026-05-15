import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { CheckCircle, Calendar as CalendarIcon, Plus, X, Users } from 'lucide-react';
import { format } from 'date-fns';
import RetroactiveSubform from './RetroactiveSubform';
import SectionCard from './SectionCard';
import QuickMinutesForm from './QuickMinutesForm';
import TemplateFieldsForm from './TemplateFieldsForm';

// Template types that use QuickMinutesForm (AI-first)
const QUICK_TYPES = new Set(['annual_review', 'quarterly_review', 'general_meeting']);

/**
 * Step 2: Form Builder
 *
 * Props:
 *   sections           — array of section objects
 *   onSectionFieldChange — (sectionIndex, field, value) => void
 *   onAddSection       — () => void
 *   onRemoveSection    — (sectionIndex) => void
 *   onAiDraftGenerated — (sectionIndex, draftBody, suggestedTitle) => void
 *   commonFields       — { meetingDate, selectedTrustees, otherAttendees, meetingLocation }
 *   onCommonFieldChange — (field, value) => void
 *   trusteeOptions     — string[] from trust context
 *   retroactive        — boolean
 *   onRetroactiveToggle — (val) => void
 *   retroactiveData    — { reason, participantsConfirmation, bestInterest }
 *   onRetroactiveChange — (field, value) => void
 *   selectedTrust      — from AuthContext
 *   customParticipant  — string
 *   onCustomParticipantChange — (value) => void
 *   onAddCustomParticipant — () => void
 *   addAnotherVisible  — boolean
 */
export default function Step2FormBuilder({
  sections,
  onSectionFieldChange,
  onAddSection,
  onRemoveSection,
  onAiDraftGenerated,
  commonFields,
  onCommonFieldChange,
  trusteeOptions,
  retroactive,
  onRetroactiveToggle,
  retroactiveData,
  onRetroactiveChange,
  selectedTrust,
  customParticipant,
  onCustomParticipantChange,
  onAddCustomParticipant
}) {
  const handleTrusteeToggle = (name) => {
    const current = commonFields.selectedTrustees || [];
    const next = current.includes(name)
      ? current.filter(n => n !== name)
      : [...current, name];
    onCommonFieldChange('selectedTrustees', next);
  };

  const handleRemoveAttendee = (name) => {
    const current = commonFields.otherAttendees || [];
    onCommonFieldChange('otherAttendees', current.filter(n => n !== name));
  };

  return (
    <div className="space-y-6" data-testid="step2-form-builder">
      {/* Retroactive Toggle */}
      <RetroactiveSubform
        retroactive={retroactive}
        onToggle={onRetroactiveToggle}
        retroactiveData={retroactiveData}
        onChange={onRetroactiveChange}
      />

      {/* Common Header Fields */}
      <div className="space-y-5 p-5 border border-navy/10 dark:border-white/10 rounded-lg bg-navy/2 dark:bg-white/2">
        <h3 className="font-mono text-xs uppercase tracking-widest text-navy/50 dark:text-white/50 mb-2">
          Meeting Details
        </h3>

        {/* Meeting Date */}
        <div>
          <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-1.5 block">
            Meeting Date <span className="text-red-500">*</span>
          </Label>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                className="w-full justify-start text-left font-normal border-navy/20 dark:border-white/20"
              >
                <CalendarIcon className="mr-2 h-4 w-4" />
                {commonFields.meetingDate ? format(commonFields.meetingDate, 'PPP') : 'Select date'}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="single"
                selected={commonFields.meetingDate}
                onSelect={(date) => date && onCommonFieldChange('meetingDate', date)}
                initialFocus
              />
            </PopoverContent>
          </Popover>
        </div>

        {/* Trustees Present */}
        <div>
          <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-2 block">
            Trustees Present <span className="text-red-500">*</span>
          </Label>
          {trusteeOptions.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {trusteeOptions.map((trustee) => {
                const isSelected = (commonFields.selectedTrustees || []).includes(trustee);
                return (
                  <button
                    key={trustee}
                    onClick={() => handleTrusteeToggle(trustee)}
                    className={`flex items-center gap-2 px-3 py-2 border transition-all text-sm ${
                      isSelected
                        ? 'border-navy dark:border-gold bg-navy/5 dark:bg-gold/5'
                        : 'border-navy/20 dark:border-white/20 hover:border-navy/40'
                    }`}
                  >
                    <div className={`w-4 h-4 border flex items-center justify-center ${
                      isSelected
                        ? 'border-navy dark:border-gold bg-navy dark:bg-gold'
                        : 'border-navy/30 dark:border-white/30'
                    }`}>
                      {isSelected && <CheckCircle className="w-3 h-3 text-white dark:text-navy" />}
                    </div>
                    {trustee}
                  </button>
                );
              })}
            </div>
          )}

          {/* Selected trustees summary */}
          {(commonFields.selectedTrustees || []).length > 0 && (
            <p className="text-xs text-muted-foreground mb-2">
              {commonFields.selectedTrustees.length} trustee{commonFields.selectedTrustees.length > 1 ? 's' : ''} selected
            </p>
          )}

          {/* Add custom trustee/participant */}
          <div className="flex gap-2 mt-2">
            <div className="relative flex-1">
              <Users className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                value={customParticipant || ''}
                onChange={(e) => onCustomParticipantChange(e.target.value)}
                placeholder="Add a participant name..."
                className="pl-10"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    onAddCustomParticipant();
                  }
                }}
              />
            </div>
            <Button variant="outline" size="sm" onClick={onAddCustomParticipant}>
              <Plus className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Other Attendees */}
        {(commonFields.otherAttendees || []).length > 0 && (
          <div>
            <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-2 block">
              Other Attendees
            </Label>
            <div className="flex flex-wrap gap-2">
              {commonFields.otherAttendees.map((name) => (
                <span
                  key={name}
                  className="flex items-center gap-1 px-2 py-1 bg-navy/5 dark:bg-gold/5 border border-navy/10 dark:border-gold/10 text-xs"
                >
                  {name}
                  <button
                    onClick={() => handleRemoveAttendee(name)}
                    className="text-muted-foreground hover:text-red-500"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Meeting Location */}
        <div>
          <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-1.5 block">
            Meeting Location
          </Label>
          <Input
            value={commonFields.meetingLocation || ''}
            onChange={(e) => onCommonFieldChange('meetingLocation', e.target.value)}
            placeholder="City, State or virtual meeting platform"
          />
        </div>
      </div>

      {/* Multi-section cards */}
      <div className="space-y-4">
        {sections.map((section, idx) => (
          <SectionCard
            key={section.id}
            section={section}
            sectionIndex={idx}
            onRemove={() => onRemoveSection(idx)}
            canRemove={sections.length > 1}
          >
            {QUICK_TYPES.has(section.templateType) ? (
              <QuickMinutesForm
                section={section}
                sectionIndex={idx}
                onFieldChange={onSectionFieldChange}
                selectedTrust={selectedTrust}
                meetingDate={commonFields.meetingDate}
                participants={commonFields.selectedTrustees}
                onAiDraftGenerated={onAiDraftGenerated}
              />
            ) : (
              <TemplateFieldsForm
                section={section}
                sectionIndex={idx}
                onFieldChange={onSectionFieldChange}
                selectedTrust={selectedTrust}
                meetingDate={commonFields.meetingDate}
                participants={commonFields.selectedTrustees}
                onAiDraftGenerated={onAiDraftGenerated}
              />
            )}
          </SectionCard>
        ))}
      </div>

      {/* Add Section button */}
      <Button
        variant="outline"
        onClick={onAddSection}
        className="w-full border-dashed border-navy/30 dark:border-white/30 text-navy dark:text-gold hover:bg-navy/5 dark:hover:bg-gold/5"
      >
        <Plus className="w-4 h-4 mr-2" />
        Add Another Section
      </Button>
    </div>
  );
}