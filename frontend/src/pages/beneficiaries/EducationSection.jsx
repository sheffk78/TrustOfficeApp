import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Info } from 'lucide-react';

// ========== EDUCATION SECTION COMPONENT ==========
// Reusable inline education section for trusts & allocation concepts.
export function EducationSection() {
  return (
    <div className="space-y-3 text-sm text-muted-foreground">
      <p>
        <Info className="w-3.5 h-3.5 inline mr-1 mb-0.5 text-muted-foreground" />
        <strong>Units</strong> represent divisible portions of your trust's distributable value.
        You decide how many total units exist and who receives them.
      </p>
      <p>
        <Info className="w-3.5 h-3.5 inline mr-1 mb-0.5 text-muted-foreground" />
        <strong>Allocation modes:</strong> You can assign shares by <em>percentage</em> (units calculated
        automatically) or by <em>raw unit count</em> (percentage calculated automatically). The canonical
        measurement is always units — one unit does not equal one percent unless your total equals 100.
      </p>
      <p>
        <Info className="w-3.5 h-3.5 inline mr-1 mb-0.5 text-muted-foreground" />
        <strong>Class beneficiaries</strong> define a pool by relationship (e.g. "all children"). Actual
        distribution among members uses the convention you choose — Per Capita (equal per head) or Per
        Stirpes (by family branch). Members are confirmed separately.
      </p>
      <p className="italic text-xs text-muted-foreground/70 border-l-2 border-muted pl-3 py-1">
        This interface shows allocation choices for planning purposes only. Values do not constitute
        legal advice. Consult qualified legal counsel before making trust distribution decisions.
      </p>
    </div>
  );
}

// ========== TOOLTIP HELPER ==========
export function InfoTooltip({ children, text }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Info className="w-3.5 h-3.5 text-muted-foreground cursor-help inline mb-0.5" />
        </TooltipTrigger>
        <TooltipContent className="max-w-xs text-sm">{text}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}