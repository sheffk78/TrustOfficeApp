import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import AiDraftPanel from './AiDraftPanel';

/**
 * TemplateFieldsForm — Dynamic fields from template definition for specific action types.
 * Renders fields defined in template.fields array.
 *
 * Props:
 *   section           — current section object { templateType, templateName, formData, templateDef, aiDraftText }
 *   sectionIndex      — number
 *   onFieldChange     — (sectionIndex, field, value) => void
 *   selectedTrust     — from AuthContext
 *   meetingDate        — Date
 *   participants       — string[]
 *   onAiDraftGenerated — (sectionIndex, draftBody, suggestedTitle) => void
 */
const FIELD_COMPONENTS = {
  text: 'text',
  textarea: 'textarea',
  select: 'select',
  number: 'number',
  date: 'date'
};

function FieldRenderer({ fieldDef, value, onChange }) {
  const { key, label, type, placeholder, required, options } = fieldDef;

  switch (type) {
    case FIELD_COMPONENTS.textarea:
      return (
        <div>
          <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-1.5 block">
            {label} {required && <span className="text-red-500">*</span>}
          </Label>
          <Textarea
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder || ''}
            className="min-h-[80px]"
          />
        </div>
      );

    case FIELD_COMPONENTS.select:
      return (
        <div>
          <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-1.5 block">
            {label} {required && <span className="text-red-500">*</span>}
          </Label>
          <Select value={value || ''} onValueChange={onChange}>
            <SelectTrigger>
              <SelectValue placeholder={placeholder || 'Select...'} />
            </SelectTrigger>
            <SelectContent>
              {(options || []).map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      );

    case FIELD_COMPONENTS.number:
      return (
        <div>
          <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-1.5 block">
            {label} {required && <span className="text-red-500">*</span>}
          </Label>
          <Input
            type="number"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder || ''}
          />
        </div>
      );

    case FIELD_COMPONENTS.date:
      return (
        <div>
          <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-1.5 block">
            {label} {required && <span className="text-red-500">*</span>}
          </Label>
          <Input
            type="date"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );

    // Default: text input
    case FIELD_COMPONENTS.text:
    default:
      return (
        <div>
          <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-1.5 block">
            {label} {required && <span className="text-red-500">*</span>}
          </Label>
          <Input
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder || ''}
          />
        </div>
      );
  }
}

export default function TemplateFieldsForm({
  section,
  sectionIndex,
  onFieldChange,
  selectedTrust,
  meetingDate,
  participants,
  onAiDraftGenerated
}) {
  const fd = section.formData || {};
  const templateDef = section.templateDef || {};
  const fields = templateDef.fields || [];

  const handleAiDraftGenerated = (draftBody, suggestedTitle) => {
    if (onAiDraftGenerated) onAiDraftGenerated(sectionIndex, draftBody, suggestedTitle);
  };

  // Build template field values for AI context
  const templateFieldValues = {};
  fields.forEach(f => {
    if (fd[f.key]) templateFieldValues[f.key] = fd[f.key];
  });

  return (
    <div className="space-y-5">
      {/* Render each field from template definition */}
      {fields.map((fieldDef) => (
        <FieldRenderer
          key={fieldDef.key}
          fieldDef={fieldDef}
          value={fd[fieldDef.key]}
          onChange={(val) => onFieldChange(sectionIndex, fieldDef.key, val)}
        />
      ))}

      {fields.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No template-specific fields defined. You can use AI to generate a draft from context.
        </p>
      )}

      {/* AI Draft Panel */}
      <AiDraftPanel
        selectedTrust={selectedTrust}
        minutesType={section.templateType}
        meetingDate={meetingDate}
        participants={participants}
        additionalContext={fd.notes || ''}
        templateFields={templateFieldValues}
        onDraftGenerated={handleAiDraftGenerated}
        value={section.aiDraftText || ''}
        onChange={(val) => onFieldChange(sectionIndex, 'aiDraftText', val)}
      />
    </div>
  );
}