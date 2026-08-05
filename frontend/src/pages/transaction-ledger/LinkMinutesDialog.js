/**
 * Link Minutes dialog — links a threshold-exceeded transaction to a minutes
 * document so the alert can auto-resolve.
 */
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, Link2 } from 'lucide-react';
import { format, parseISO } from 'date-fns';

export default function LinkMinutesDialog({
  open,
  onOpenChange,
  transaction,            // the transaction being linked, or null
  minutesList,
  selectedMinutesId,
  onSelectedMinutesChange,
  linking,
  onSubmit,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Link Minutes to Transaction</DialogTitle>
        </DialogHeader>
        {transaction && (
          <div className="space-y-4 mt-2">
            <div className="p-3 bg-warning/10 border border-warning/20">
              <p className="text-sm font-medium text-foreground">
                {transaction.direction === 'inflow' ? '+' : '-'}$
                {transaction.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">{transaction.purpose_memo || 'No memo'}</p>
              <p className="text-xs text-warning mt-1">
                This transaction exceeded the spending threshold. Linking minutes documents the trustee approval.
              </p>
            </div>

            <div>
              <Label className="label-trust">Select Minutes Document *</Label>
              {minutesList.length === 0 ? (
                <p className="text-sm text-muted-foreground mt-2">
                  No minutes found. Create minutes first from the Minutes page.
                </p>
              ) : (
                <Select value={selectedMinutesId} onValueChange={onSelectedMinutesChange}>
                  <SelectTrigger data-testid="link-minutes-select">
                    <SelectValue placeholder="Choose a minutes document" />
                  </SelectTrigger>
                  <SelectContent>
                    {minutesList.map((m) => (
                      <SelectItem key={m.minutes_id} value={m.minutes_id}>
                        {m.meeting_date ? format(parseISO(m.meeting_date), 'MMM d, yyyy') : 'No date'} — {m.minutes_type || 'Minutes'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            <Button
              className="w-full btn-primary"
              onClick={onSubmit}
              disabled={linking || !selectedMinutesId}
              data-testid="link-minutes-submit-btn"
            >
              {linking ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Linking...</>
              ) : (
                <><Link2 className="w-4 h-4 mr-2" /> Link Minutes</>
              )}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}