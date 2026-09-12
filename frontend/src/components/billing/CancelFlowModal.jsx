import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import {
  CheckCircle2,
  Cloud,
  Download,
  Archive,
  ShoppingCart,
  Trash2,
  ShieldCheck,
} from 'lucide-react';

// CancelFlowModal â replaces the bare window.confirm on subscription cancel.
// Flow:
//   step 'ask'     â "Is your trust complete?" Keep / Leave
//   step 'keep'    â Records Repository (one-time purchase) + archive-to-read-only
//   step 'leave'   â backup verification + export, bulk delete (typed confirm), final cancel
//
// Props:
//   open                          â boolean
//   onOpenChange(open)            â () => void
//   trustId                       â string (selected trust id for dissolve/export/bulk-delete)
//   userEmail                     â string (for reloading subscription state)
//   loadSubscriptionState         â fn(email) reload auth subscription
//   onComplete                    â optional fn called after successful final cancel
export default function CancelFlowModal({
  open,
  onOpenChange,
  trustId,
  userEmail,
  loadSubscriptionState,
  onComplete,
}) {
  const [step, setStep] = useState('ask'); // 'ask' | 'keep' | 'leave'
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Backup / export state (shared by both Keep and Leave paths â both verify backup first).
  const [exitSummary, setExitSummary] = useState(null); // { backup: {connected, last_backup_at}, ... }
  const [summaryLoaded, setSummaryLoaded] = useState(false);
  const [exported, setExported] = useState(false);

  // Keep-path state
  const [repoPlan, setRepoPlan] = useState(null); // 'annual' | 'lifetime'
  const [dissolved, setDissolved] = useState(false);

  // Leave-path typed-confirm bulk delete state
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleted, setDeleted] = useState(false);
  const DELETE_PHRASE = 'DELETE';

  // Reset everything whenever the modal is (re)opened.
  useEffect(() => {
    if (open) {
      setStep('ask');
      setLoading(false);
      setError(null);
      setExitSummary(null);
      setSummaryLoaded(false);
      setExported(false);
      setRepoPlan(null);
      setDissolved(false);
      setDeleteConfirmText('');
      setDeleted(false);
    }
  }, [open]);

  // Load the exit-summary (backup status + counts) as soon as either branch begins.
  const loadExitSummary = useCallback(async () => {
    if (summaryLoaded) return;
    setLoading(true);
    try {
      const res = await fetchWithAuth('/account/exit-summary');
      if (res.ok) {
        setExitSummary(await res.json());
      } else {
        setExitSummary({ backup: { connected: false, last_backup_at: null } });
      }
    } catch {
      setExitSummary({ backup: { connected: false, last_backup_at: null } });
    } finally {
      setSummaryLoaded(true);
      setLoading(false);
    }
  }, [summaryLoaded]);

  const enterKeep = () => {
    setStep('keep');
    loadExitSummary();
  };
  const enterLeave = () => {
    setStep('leave');
    loadExitSummary();
  };

  // ââ Archive export (GET /trusts/{id}/archive-export â zip stream) ââ
  const handleExport = async () => {
    if (!trustId) {
      toast.error('Select a trust before exporting.');
      return;
    }
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/trusts/${trustId}/archive-export`);
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trust-archive-${trustId}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      setExported(true);
      toast.success('Archive exported. Keep this copy safe.');
    } catch (e) {
      showError(toast, e, { operation: 'archive_export', page: 'CancelFlow' });
    } finally {
      setLoading(false);
    }
  };

  // ââ Keep path: Records Repository purchase (annual subscription OR lifetime one-time) ââ
  const handlePurchaseRepo = async (plan) => {
    setLoading(true);
    setRepoPlan(plan);
    try {
      const res = await fetchWithAuth('/repository/purchase', {
        method: 'POST',
        body: JSON.stringify({ plan }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.checkout_url) {
          window.location.href = data.checkout_url;
          return;
        }
      }
      showError(
        toast,
        new Error('Could not start the Records Repository checkout. Please contact support@trustoffice.app.'),
        { operation: 'repository_purchase', page: 'CancelFlow' }
      );
      setRepoPlan(null);
    } catch (e) {
      showError(toast, e, { operation: 'repository_purchase', page: 'CancelFlow' });
      setRepoPlan(null);
    } finally {
      setLoading(false);
    }
  };

  // ââ Keep path: archive trust read-only (free, no purchase) ââ
  const handleDissolve = async () => {
    if (!trustId) {
      toast.error('Select a trust before archiving.');
      return;
    }
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/trusts/${trustId}/dissolve`, {
        method: 'POST',
        body: JSON.stringify({ dissolved_on: new Date().toISOString() }),
      });
      if (res.ok) {
        setDissolved(true);
        toast.success('Your trust has been archived read-only. Records are preserved.');
      } else {
        showError(toast, new Error('Could not archive the trust. Please try again.'), {
          operation: 'dissolve_trust',
          page: 'CancelFlow',
        });
      }
    } catch (e) {
      showError(toast, e, { operation: 'dissolve_trust', page: 'CancelFlow' });
    } finally {
      setLoading(false);
    }
  };

  // ââ Leave path: bulk delete vault documents (typed confirmation) ââ
  const handleBulkDelete = async () => {
    if (deleteConfirmText !== DELETE_PHRASE) {
      setError(`Type "${DELETE_PHRASE}" to confirm deletion.`);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth('/vault/documents/bulk', {
        method: 'DELETE',
        body: JSON.stringify({ confirm: DELETE_PHRASE }),
      });
      if (res.ok) {
        setDeleted(true);
        toast.success('All vault documents deleted.');
      } else if (res.status === 400) {
        setError('Confirmation text did not match. Deletion was not performed.');
      } else {
        showError(toast, new Error('Could not delete documents. Please try again.'), {
          operation: 'bulk_delete',
          page: 'CancelFlow',
        });
      }
    } catch (e) {
      showError(toast, e, { operation: 'bulk_delete', page: 'CancelFlow' });
    } finally {
      setLoading(false);
    }
  };

  // ââ Final cancel (existing endpoint) ââ
  const handleFinalCancel = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth('/subscription/cancel', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || 'Subscription canceled.');
        if (userEmail && loadSubscriptionState) await loadSubscriptionState(userEmail);
        onComplete?.();
        onOpenChange(false);
      } else {
        const err = await res.json().catch(() => ({}));
        showError(
          toast,
          new Error(err.detail || 'Could not cancel subscription. Please contact support@trustoffice.app.'),
          { operation: 'cancel_subscription', page: 'CancelFlow' }
        );
      }
    } catch (e) {
      showError(toast, e, { operation: 'cancel_subscription', page: 'CancelFlow' });
    } finally {
      setLoading(false);
    }
  };

  const backupConnected = exitSummary?.backup?.connected === true;
  const lastBackup = exitSummary?.backup?.last_backup_at;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="cancel-flow-modal">
        {step === 'ask' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-serif text-2xl text-navy">
                Is your trust complete?
              </DialogTitle>
              <DialogDescription>
                Before you go, let&apos;s make sure your records are safe. Choose the option that fits.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3 py-2">
              <button
                type="button"
                onClick={enterKeep}
                className="w-full text-left p-4 border border-navy/20 rounded-lg hover:border-navy/40 transition-colors"
                data-testid="cancel-keep-btn"
              >
                <div className="flex items-center gap-2 mb-1">
                  <ShieldCheck className="w-4 h-4 text-navy" />
                  <span className="font-medium text-navy">Keep my records</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Preserve everything read-only in the Records Repository. Downloadable anytime â nothing is lost.
                </p>
              </button>

              <button
                type="button"
                onClick={enterLeave}
                className="w-full text-left p-4 border border-navy/20 rounded-lg hover:border-navy/40 transition-colors"
                data-testid="cancel-leave-btn"
              >
                <div className="flex items-center gap-2 mb-1">
                  <Trash2 className="w-4 h-4 text-error" />
                  <span className="font-medium text-navy">Leave & delete</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Export a full copy first, then delete your documents and cancel your subscription.
                </p>
              </button>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                Never mind
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'keep' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-serif text-2xl text-navy">Keep your records</DialogTitle>
              <DialogDescription>
                Your trust can be archived read-only. First, confirm your off-site backup is current.
              </DialogDescription>
            </DialogHeader>

            <BackupStatusBlock
              loading={loading && !summaryLoaded}
              connected={backupConnected}
              lastBackup={lastBackup}
              exported={exported}
              onExport={handleExport}
            />

            <div className="space-y-3 py-2">
              <div className="p-4 border border-gold/30 bg-gold/5 rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <ShoppingCart className="w-4 h-4 text-navy" />
                  <span className="font-medium text-navy">Records Repository Ã¢ÂÂ $49/year</span>
                </div>
                <p className="text-sm text-muted-foreground mb-3">
                  A read-only archive of all your trust records, preserved and downloadable anytime. Billed annually.
                </p>
                <Button
                  onClick={() => handlePurchaseRepo('annual')}
                  disabled={loading || repoPlan !== null}
                  className="btn-primary"
                  data-testid="purchase-repo-annual-btn"
                >
                  <ShoppingCart className="w-4 h-4 mr-2" />
                  {repoPlan === 'annual' ? 'Redirecting to checkoutÃ¢ÂÂ¦' : 'Buy Records Repository Ã¢ÂÂ $49/yr'}
                </Button>
              </div>

              <div className="p-4 border border-gold/30 bg-gold/5 rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <ShoppingCart className="w-4 h-4 text-navy" />
                  <span className="font-medium text-navy">Lifetime Ã¢ÂÂ $199 one-time</span>
                </div>
                <p className="text-sm text-muted-foreground mb-3">
                  The same read-only archive, yours forever with a single one-time purchase.
                </p>
                <Button
                  onClick={() => handlePurchaseRepo('lifetime')}
                  disabled={loading || repoPlan !== null}
                  className="btn-primary"
                  data-testid="purchase-repo-lifetime-btn"
                >
                  <ShoppingCart className="w-4 h-4 mr-2" />
                  {repoPlan === 'lifetime' ? 'Redirecting to checkoutÃ¢ÂÂ¦' : 'Buy Lifetime Ã¢ÂÂ $199'}
                </Button>
              </div>

              <div className="p-4 border border-navy/20 rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <Archive className="w-4 h-4 text-navy" />
                  <span className="font-medium text-navy">Or archive now (free)</span>
                </div>
                <p className="text-sm text-muted-foreground mb-3">
                  Dissolve this trust to a preserved, read-only archive. No purchase required.
                </p>
                <Button
                  onClick={handleDissolve}
                  disabled={loading || dissolved || !trustId}
                  variant="outline"
                  data-testid="dissolve-trust-btn"
                >
                  <Archive className="w-4 h-4 mr-2" />
                  {dissolved ? 'Archived read-only' : 'Archive trust read-only'}
                </Button>
              </div>
            </div>

            <DialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-between gap-2">
              <Button variant="ghost" onClick={() => setStep('ask')} disabled={loading}>
                Back
              </Button>
              <Button
                onClick={handleFinalCancel}
                disabled={loading || (!repoPlan && !dissolved)}
                variant="outline"
                className="text-muted-foreground"
                data-testid="keep-final-cancel-btn"
              >
                Cancel subscription anyway
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'leave' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-serif text-2xl text-navy">Export, then delete</DialogTitle>
              <DialogDescription>
                Take your information with you. Verify your backup, export a full archive, then delete and cancel.
              </DialogDescription>
            </DialogHeader>

            <BackupStatusBlock
              loading={loading && !summaryLoaded}
              connected={backupConnected}
              lastBackup={lastBackup}
              exported={exported}
              onExport={handleExport}
            />

            {!deleted ? (
              <div className="p-4 border border-error/30 bg-error/5 rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <Trash2 className="w-4 h-4 text-error" />
                  <span className="font-medium text-error">Delete all vault documents</span>
                </div>
                <p className="text-sm text-muted-foreground mb-3">
                  This permanently removes every document in your vault. Only proceed after you&apos;ve exported a copy.
                </p>
                <label className="block text-xs font-mono text-muted-foreground mb-1">
                  Type {DELETE_PHRASE} to confirm
                </label>
                <Input
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  placeholder={DELETE_PHRASE}
                  className="mb-2 font-mono"
                  data-testid="bulk-delete-confirm-input"
                />
                {error && <p className="text-sm text-error mb-2" data-testid="bulk-delete-error">{error}</p>}
                <Button
                  onClick={handleBulkDelete}
                  disabled={loading || deleteConfirmText !== DELETE_PHRASE}
                  className="bg-error hover:bg-error/90 text-white"
                  data-testid="bulk-delete-btn"
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete all documents
                </Button>
              </div>
            ) : (
              <div className="p-4 border border-success/30 bg-success/5 rounded-lg flex items-center gap-2" data-testid="deleted-confirmation">
                <CheckCircle2 className="w-4 h-4 text-success" />
                <span className="text-sm text-success">All vault documents deleted.</span>
              </div>
            )}

            <DialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-between gap-2">
              <Button variant="ghost" onClick={() => setStep('ask')} disabled={loading || deleted}>
                Back
              </Button>
              <Button
                onClick={handleFinalCancel}
                disabled={loading || !exported || !deleted}
                variant="outline"
                className="text-muted-foreground"
                data-testid="leave-final-cancel-btn"
              >
                Cancel subscription
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// Shared backup-status + export block for both Keep and Leave paths.
function BackupStatusBlock({ loading, connected, lastBackup, exported, onExport }) {
  const formatDate = (iso) => {
    if (!iso) return 'Never';
    try {
      return new Date(iso).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return 'Unknown';
    }
  };

  return (
    <div className="p-4 border border-navy/15 rounded-lg bg-navy/5">
      <div className="flex items-center gap-2 mb-2">
        <Cloud className="w-4 h-4 text-navy" />
        <span className="font-medium text-navy text-sm">Cloud backup status</span>
      </div>
      {loading ? (
        <p className="text-sm text-muted-foreground" data-testid="backup-status-loading">
          Checking backup statusâ¦
        </p>
      ) : (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground" data-testid="backup-status-text">
            {connected ? (
              <>
                Connected Â· last backup {formatDate(lastBackup)}
              </>
            ) : (
              <>Not connected â your export below is your only copy.</>
            )}
          </span>
          <Button
            onClick={onExport}
            size="sm"
            variant="outline"
            disabled={exported}
            data-testid="export-archive-btn"
          >
            <Download className="w-4 h-4 mr-2" />
            {exported ? 'Exported' : 'Export full archive'}
          </Button>
        </div>
      )}
    </div>
  );
}
