import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';
import { ChevronDown, ChevronRight, Trash2 } from 'lucide-react';

/**
 * SectionCard — Wraps a single template section in a collapsible card.
 *
 * Props:
 *   section       — { id, templateType, templateName, formData, aiDraftText }
 *   sectionIndex   — number
 *   children       — form content for this section
 *   onRemove       — () => void
 *   canRemove      — boolean (hide remove if only 1 section)
 */
export default function SectionCard({ section, sectionIndex, children, onRemove, canRemove }) {
  const isOpen = true; // default open

  return (
    <Collapsible defaultOpen={isOpen} className="border border-navy/10 dark:border-white/10 rounded-lg">
      <div className="flex items-center justify-between px-4 py-3 bg-navy/3 dark:bg-white/3">
        <CollapsibleTrigger className="flex items-center gap-2 flex-1 text-left">
          <ChevronDown className="w-4 h-4 text-navy/50 dark:text-white/50 ui-expanded:rotate-0 ui-not-expanded:rotate-[-90deg] transition-transform" />
          <span className="font-serif text-base text-navy dark:text-gold">
            {section.templateName || `Section ${sectionIndex + 1}`}
          </span>
          <span className="text-xs text-muted-foreground font-mono ml-2">
            Section {sectionIndex + 1}
          </span>
        </CollapsibleTrigger>

        {canRemove && (
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            className="text-muted-foreground hover:text-red-500 text-xs flex items-center gap-1"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Remove
          </Button>
        )}
      </div>

      <CollapsibleContent className="p-4 space-y-4">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}