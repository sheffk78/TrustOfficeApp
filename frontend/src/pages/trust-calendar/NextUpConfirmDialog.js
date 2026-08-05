import { Button } from '@/components/ui/button';

// Confirmation dialog for the Next Up widget's Mark Filed / Extend actions.
// Enter confirms, Escape cancels.
//
// Props:
//   confirm        – { action: 'filed'|'extended', entryId, label, taxYear } | null
//   onClose        – () => void
//   onConfirm      – (entryId) => void  (calls markFiled or markExtended)
export default function NextUpConfirmDialog({ confirm, onClose, onConfirm }) {
  if (!confirm) return null;

  const isFiled = confirm.action === 'filed';

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white p-6 w-full max-w-sm corner-mark"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onClose();
          if (e.key === 'Enter') { onConfirm(confirm.entryId); onClose(); }
        }}
        role="dialog"
        aria-modal="true"
        aria-label={isFiled ? 'Confirm mark as filed' : 'Confirm mark as extended'}
        data-testid="nextup-confirm"
      >
        <h3 className="font-serif text-lg text-navy mb-2">
          {isFiled ? 'Confirm: Mark as Filed' : 'Confirm: Mark as Extended'}
        </h3>
        <p className="text-sm text-muted-foreground mb-4">
          {isFiled
            ? `Mark "${confirm.label}" as filed for tax year ${confirm.taxYear}?`
            : `Mark "${confirm.label}" as extended?`}
        </p>
        <div className="flex gap-3">
          <Button variant="outline" className="flex-1 btn-secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            className="flex-1 btn-primary"
            onClick={() => { onConfirm(confirm.entryId); onClose(); }}
          >
            Confirm
          </Button>
        </div>
      </div>
    </div>
  );
}