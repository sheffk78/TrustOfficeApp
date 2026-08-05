/**
 * Transaction form dialog — used for both Create and Edit.
 *
 * The dialog is fully controlled: the parent owns the `form` state and supplies
 * an `onFormChange` callback that receives a partial update. All validation and
 * submission happens in the parent; this component only renders the fields.
 */
import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Loader2 } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { Calendar as CalendarIcon } from 'lucide-react';
import { CLASSIFICATIONS, DIRECTION_OPTIONS } from './constants';

/**
 * Shared field renderer for the direction select (Inflow / Outflow).
 */
function DirectionSelect({ value, onChange, testId }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger data-testid={testId}><SelectValue /></SelectTrigger>
      <SelectContent>
        {DIRECTION_OPTIONS.map((d) => (
          <SelectItem key={d.value} value={d.value}>
            <span className="flex items-center gap-2"><d.icon className={`w-4 h-4 ${d.color}`} /> {d.label}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/**
 * Date picker field. Parent controls `value` (yyyy-MM-dd) and gets back the
 * formatted yyyy-MM-dd string via `onChange`.
 */
function DateField({ value, onChange, testId, label = 'Date *' }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <Label className="label-trust">{label}</Label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" className="w-full justify-start font-normal" data-testid={testId}>
            <CalendarIcon className="w-4 h-4 mr-2" />
            {value ? format(parseISO(value), 'MMM d, yyyy') : 'Pick date'}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="single"
            selected={value ? parseISO(value) : undefined}
            onSelect={(d) => { if (d) { onChange(format(d, 'yyyy-MM-dd')); setOpen(false); } }}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}

/**
 * Classification select with conditional "Other" note field.
 */
function ClassificationFields({ classification, otherNote, onClassificationChange, onOtherNoteChange, testIdPrefix }) {
  return (
    <>
      <div>
        <Label className="label-trust">Governance Classification *</Label>
        <Select value={classification} onValueChange={onClassificationChange}>
          <SelectTrigger data-testid={`${testIdPrefix}-classification-select`}>
            <SelectValue placeholder="Select classification" />
          </SelectTrigger>
          <SelectContent>
            {CLASSIFICATIONS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {classification === 'Other' && (
        <div>
          <Label className="label-trust">Note (required for &quot;Other&quot;) *</Label>
          <Input
            className="input-trust"
            value={otherNote}
            onChange={(e) => onOtherNoteChange(e.target.value)}
            placeholder="Explain the nature of this transaction"
            data-testid={`${testIdPrefix}-other-note`}
          />
        </div>
      )}
    </>
  );
}

/**
 * Transaction dialog (Create or Edit). Pass `mode="create"` or `mode="edit"`.
 */
export default function TransactionDialog({
  open,
  onOpenChange,
  mode,            // 'create' | 'edit'
  form,            // { entity_id, date, amount, direction, source_account, destination_account, governance_classification, purpose_memo, other_note }
  onFormChange,    // (partial) => void  — merges partial into form
  entities,
  submitting,
  onSubmit,
}) {
  const isEdit = mode === 'edit';
  const testPrefix = isEdit ? 'edit' : 'create';
  const title = isEdit ? 'Edit Transaction' : 'Record Transaction';
  const submitLabel = isEdit ? 'Save Changes' : 'Record Transaction';
  const submittingLabel = 'Saving...';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div>
            <Label className="label-trust">Entity *</Label>
            <Select value={form.entity_id} onValueChange={(v) => onFormChange({ entity_id: v })}>
              <SelectTrigger data-testid={`${testPrefix}-entity-select`}><SelectValue placeholder="Select entity" /></SelectTrigger>
              <SelectContent>
                {entities.map((e) => <SelectItem key={e.entity_id} value={e.entity_id}>{e.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <DateField
              value={form.date}
              onChange={(d) => onFormChange({ date: d })}
              testId={`${testPrefix}-date-btn`}
            />
            <div>
              <Label className="label-trust">Amount *</Label>
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="0.00"
                className="input-trust"
                value={form.amount}
                onChange={(e) => onFormChange({ amount: e.target.value })}
                data-testid={`${testPrefix}-amount-input`}
              />
            </div>
          </div>

          <div>
            <Label className="label-trust">Direction *</Label>
            <DirectionSelect
              value={form.direction}
              onChange={(v) => onFormChange({ direction: v })}
              testId={`${testPrefix}-direction-select`}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="label-trust">Source Account</Label>
              <Input
                placeholder="e.g. Trust Checking"
                className="input-trust"
                value={form.source_account}
                onChange={(e) => onFormChange({ source_account: e.target.value })}
                data-testid={`${testPrefix}-source-input`}
              />
            </div>
            <div>
              <Label className="label-trust">Destination Account</Label>
              <Input
                placeholder="e.g. Personal Account"
                className="input-trust"
                value={form.destination_account}
                onChange={(e) => onFormChange({ destination_account: e.target.value })}
                data-testid={`${testPrefix}-dest-input`}
              />
            </div>
          </div>

          <ClassificationFields
            classification={form.governance_classification}
            otherNote={form.other_note}
            onClassificationChange={(v) => onFormChange({ governance_classification: v })}
            onOtherNoteChange={(v) => onFormChange({ other_note: v })}
            testIdPrefix={testPrefix}
          />

          <div>
            <Label className="label-trust">Purpose / Memo</Label>
            <Textarea
              className="input-trust"
              placeholder="Describe the purpose of this transaction"
              value={form.purpose_memo}
              onChange={(e) => onFormChange({ purpose_memo: e.target.value })}
              rows={2}
              data-testid={`${testPrefix}-memo-input`}
            />
          </div>

          <Button
            className="w-full btn-primary"
            onClick={onSubmit}
            disabled={submitting}
            data-testid={`${testPrefix}-submit-btn`}
          >
            {submitting ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> {submittingLabel}</>
            ) : (
              submitLabel
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}