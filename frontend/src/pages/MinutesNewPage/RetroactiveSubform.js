import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { AlertTriangle, Clock } from 'lucide-react';
import { format } from 'date-fns';

/**
 * Retroactive Subform — 3 required questions when retroactive mode is enabled.
 *
 * Props:
 *   retroactive     — boolean, is retroactive mode on
 *   onToggle        — (val: boolean) => void
 *   retroactiveData — { reason, participantsConfirmation, bestInterest }
 *   onChange        — (field: string, value: string) => void
 */
export default function RetroactiveSubform({ retroactive, onToggle, retroactiveData, onChange }) {
  return (
    <div className="space-y-4">
      {/* Toggle */}
      <div className="flex items-center justify-between p-3 border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20 rounded-lg">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          <Label className="text-sm font-medium cursor-pointer">
            This is a retroactive minutes entry
          </Label>
        </div>
        <Switch
          checked={retroactive}
          onCheckedChange={onToggle}
        />
      </div>

      {/* Required questions when retroactive */}
      {retroactive && (
        <div className="space-y-4 p-4 border border-amber-300 dark:border-amber-700 bg-amber-50/30 dark:bg-amber-950/10 rounded-lg">
          <div className="flex items-start gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-amber-700 dark:text-amber-300">
              Retroactive minutes document decisions made on a prior date. All three fields below are required.
            </p>
          </div>

          {/* Q1: Reason for delay */}
          <div>
            <Label className="text-sm font-medium mb-1.5 block">
              Why was this not documented at the time? <span className="text-red-500">*</span>
            </Label>
            <Textarea
              value={retroactiveData?.reason || ''}
              onChange={(e) => onChange('reason', e.target.value)}
              placeholder="Explain why these minutes are being created after the fact..."
              className="min-h-[80px]"
            />
          </div>

          {/* Q2: Participants confirmation */}
          <div>
            <Label className="text-sm font-medium mb-1.5 block">
              How do you confirm the participants listed were actually present? <span className="text-red-500">*</span>
            </Label>
            <Textarea
              value={retroactiveData?.participantsConfirmation || ''}
              onChange={(e) => onChange('participantsConfirmation', e.target.value)}
              placeholder="E.g., mutual recollection, email records, signed attendance sheet..."
              className="min-h-[80px]"
            />
          </div>

          {/* Q3: Best interest */}
          <div>
            <Label className="text-sm font-medium mb-1.5 block">
              Why is documenting this now in the best interest of the trust? <span className="text-red-500">*</span>
            </Label>
            <Textarea
              value={retroactiveData?.bestInterest || ''}
              onChange={(e) => onChange('bestInterest', e.target.value)}
              placeholder="Explain how late documentation benefits the trust and beneficiaries..."
              className="min-h-[80px]"
            />
          </div>
        </div>
      )}
    </div>
  );
}