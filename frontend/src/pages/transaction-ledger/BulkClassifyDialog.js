/**
 * Bulk classify dialog — applies a single classification (and optional memo) to
 * a set of selected transactions. Parent owns the form state; this is purely
 * presentational with callbacks.
 */
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { CLASSIFICATIONS } from './constants';

export default function BulkClassifyDialog({
  open,
  onOpenChange,
  selectedCount,
  classification,
  onClassificationChange,
  otherNote,
  onOtherNoteChange,
  memo,
  onMemoChange,
  onSubmit,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Classify {selectedCount} Transactions</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div>
            <Label className="label-trust">Governance Classification *</Label>
            <Select value={classification} onValueChange={onClassificationChange}>
              <SelectTrigger data-testid="bulk-classification-select"><SelectValue placeholder="Select classification" /></SelectTrigger>
              <SelectContent>
                {CLASSIFICATIONS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {classification === 'Other' && (
            <div>
              <Label className="label-trust">Note (required) *</Label>
              <Input
                className="input-trust"
                value={otherNote}
                onChange={(e) => onOtherNoteChange(e.target.value)}
                placeholder="Explain classification"
              />
            </div>
          )}
          <div>
            <Label className="label-trust">Purpose / Memo (optional)</Label>
            <Textarea
              className="input-trust"
              value={memo}
              onChange={(e) => onMemoChange(e.target.value)}
              rows={2}
              placeholder="Shared memo for selected transactions"
            />
          </div>
          <Button className="w-full btn-primary" onClick={onSubmit} data-testid="bulk-classify-submit-btn">
            Apply Classification
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}