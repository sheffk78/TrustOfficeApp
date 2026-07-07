import { useState, useEffect, useRef, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import { showError } from '@/utils/errors';
import {
  CheckCircle2, Loader2, AlertTriangle, XCircle, Link2, Pencil, Link as LinkIcon
} from 'lucide-react';

const STATUS_CONFIG = {
  pending: {
    icon: Loader2,
    cls: 'bg-gold/10 text-gold',
    label: 'Extracting',
    spin: true,
  },
  completed: {
    icon: CheckCircle2,
    cls: 'bg-success/10 text-success',
    label: 'Verified',
    spin: false,
  },
  needs_review: {
    icon: AlertTriangle,
    cls: 'bg-warning/10 text-warning',
    label: 'Needs Review',
    spin: false,
  },
  failed: {
    icon: XCircle,
    cls: 'bg-error/10 text-error',
    label: 'Failed',
    spin: false,
  },
};

const fmtMoney = (n) => {
  if (n == null || isNaN(n)) return '';
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

/**
 * Badge + actions shown on Vault document cards when category=bank_statement.
 * Polls while extraction_status is pending. Shows Review modal for needs_review
 * and Link-to-Account dropdown when the statement isn't yet linked to a bank account.
 *
 * Props:
 *  - trustId
 *  - vaultDocId
 */
export default function BankStatementBadge({ trustId, vaultDocId }) {
  const [statement, setStatement] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [linkAccountId, setLinkAccountId] = useState('');
  const [linking, setLinking] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewForm, setReviewForm] = useState({});
  const [saving, setSaving] = useState(false);
  const pollRef = useRef(null);

  const loadStatement = useCallback(async () => {
    if (!trustId || !vaultDocId) return;
    try {
      // Backend exposes a lookup by vault_document_id via the trust's bank-statements list endpoint
      const res = await fetchWithAuth(
        `/trusts/${trustId}/bank-statements?vault_document_id=${vaultDocId}`
      );
      if (res.ok) {
        const data = await res.json();
        // Endpoint returns { statements: [...], count: N } — take first match
        const stmt = Array.isArray(data.statements) ? data.statements[0] : data;
        if (stmt) {
          setStatement(stmt);
          if (stmt.extraction_status === 'pending') {
            pollRef.current = setTimeout(loadStatement, 5000);
          }
        }
      } else if (res.status === 404) {
        // No statement record yet — backend may still be creating it after upload
        pollRef.current = setTimeout(loadStatement, 3000);
      }
    } catch (e) {
      // Silent — vault page shouldn't error if statement endpoint is unavailable
    }
  }, [trustId, vaultDocId]);

  const loadAccounts = useCallback(async () => {
    if (!trustId) return;
    try {
      const res = await fetchWithAuth(`/trusts/${trustId}/bank-accounts?include_archived=true`);
      if (res.ok) {
        const data = await res.json();
        setAccounts(data || []);
      }
    } catch {
      // Silent
    }
  }, [trustId]);

  useEffect(() => {
    loadStatement();
    loadAccounts();
    return () => {
      if (pollRef.current) {
        clearTimeout(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [loadStatement, loadAccounts]);

  const handleLink = async () => {
    if (!statement || !linkAccountId) {
      toast.error('Select an account to link');
      return;
    }
    setLinking(true);
    try {
      const res = await fetchWithAuth(`/trusts/${trustId}/bank-statements/${statement.statement_id}/link`, {
        method: 'PUT',
        body: JSON.stringify({ bank_account_id: linkAccountId }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to link statement');
      }
      toast.success('Statement linked to account');
      setLinkAccountId('');
      loadStatement();
    } catch (e) {
      showError(toast, e, { operation: 'link_statement', page: 'Vault' });
    } finally {
      setLinking(false);
    }
  };

  const openReview = () => {
    if (!statement) return;
    setReviewForm({
      bank_name: statement.bank_name || '',
      account_last_four: statement.account_last_four || '',
      statement_period_start: statement.statement_period_start || '',
      statement_period_end: statement.statement_period_end || '',
      beginning_balance: statement.beginning_balance ?? '',
      ending_balance: statement.ending_balance ?? '',
      total_deposits: statement.total_deposits ?? '',
      total_withdrawals: statement.total_withdrawals ?? '',
    });
    setReviewOpen(true);
  };

  const handleSaveReview = async () => {
    setSaving(true);
    try {
      const payload = {
        ...reviewForm,
        beginning_balance: reviewForm.beginning_balance === '' ? null : Number(reviewForm.beginning_balance),
        ending_balance: reviewForm.ending_balance === '' ? null : Number(reviewForm.ending_balance),
        total_deposits: reviewForm.total_deposits === '' ? null : Number(reviewForm.total_deposits),
        total_withdrawals: reviewForm.total_withdrawals === '' ? null : Number(reviewForm.total_withdrawals),
        extraction_status: 'completed',
      };
      const res = await fetchWithAuth(`/trusts/${trustId}/bank-statements/${statement.statement_id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to update statement');
      }
      toast.success('Statement data corrected');
      setReviewOpen(false);
      loadStatement();
    } catch (e) {
      showError(toast, e, { operation: 'correct_statement', page: 'Vault' });
    } finally {
      setSaving(false);
    }
  };

  if (!statement) {
    // Silently render nothing if there's no statement record yet.
    // Backend triggers extraction on upload, so the record may appear shortly.
    return null;
  }

  const cfg = STATUS_CONFIG[statement.extraction_status] || STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  const isLinked = !!statement.bank_account_id;
  const unlinkableAccounts = accounts.filter(a => !a.archived);

  return (
    <div className="mb-2" data-testid={`bank-statement-badge-${vaultDocId}`}>
      {/* Status badge + extracted data */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded ${cfg.cls}`}>
          <Icon className={`w-3 h-3 ${cfg.spin ? 'animate-spin' : ''}`} />
          {cfg.label}
        </span>
        {statement.bank_name && (
          <span className="text-[10px] text-muted-foreground">{statement.bank_name}</span>
        )}
        {statement.account_last_four && (
          <span className="text-[10px] text-muted-foreground font-mono">••••{statement.account_last_four}</span>
        )}
        {statement.statement_period_start && statement.statement_period_end && (
          <span className="text-[10px] text-muted-foreground">
            {statement.statement_period_start.slice(0, 7)} to {statement.statement_period_end.slice(0, 7)}
          </span>
        )}
      </div>

      {/* Extracted balances */}
      {(statement.ending_balance != null || statement.beginning_balance != null) && (
        <div className="flex items-center gap-3 mt-1 text-[10px] text-muted-foreground font-mono">
          {statement.beginning_balance != null && (
            <span>Start: ${fmtMoney(statement.beginning_balance)}</span>
          )}
          {statement.ending_balance != null && (
            <span className="text-navy">End: ${fmtMoney(statement.ending_balance)}</span>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {statement.extraction_status === 'needs_review' && (
          <Button size="sm" variant="outline" onClick={openReview} data-testid={`review-statement-${vaultDocId}`}>
            <Pencil className="w-3 h-3 mr-1" /> Review
          </Button>
        )}
        {!isLinked && unlinkableAccounts.length > 0 && (
          <div className="flex items-center gap-1">
            <Link2 className="w-3 h-3 text-muted-foreground" />
            <Select value={linkAccountId} onValueChange={setLinkAccountId}>
              <SelectTrigger className="h-7 w-[140px] text-xs" data-testid={`link-account-select-${vaultDocId}`}>
                <SelectValue placeholder="Link to account" />
              </SelectTrigger>
              <SelectContent>
                {unlinkableAccounts.map(a => (
                  <SelectItem key={a.account_id} value={a.account_id}>
                    {a.nickname} (••••{a.last_four})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button size="sm" variant="ghost" onClick={handleLink} disabled={linking || !linkAccountId}
              data-testid={`link-account-btn-${vaultDocId}`}>
              {linking ? <Loader2 className="w-3 h-3 animate-spin" /> : <LinkIcon className="w-3 h-3" />}
            </Button>
          </div>
        )}
        {isLinked && (
          <span className="inline-flex items-center gap-1 text-[10px] text-success">
            <Link2 className="w-3 h-3" /> Linked
          </span>
        )}
      </div>

      {/* Review Modal */}
      <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Review Extracted Statement Data</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div>
              <Label>Bank Name</Label>
              <Input
                value={reviewForm.bank_name || ''}
                onChange={e => setReviewForm(f => ({ ...f, bank_name: e.target.value }))}
                className="mt-1"
                data-testid="review-bank-name"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Account Last 4</Label>
                <Input
                  value={reviewForm.account_last_four || ''}
                  onChange={e => setReviewForm(f => ({ ...f, account_last_four: e.target.value.replace(/\D/g, '').slice(0, 4) }))}
                  maxLength={4}
                  className="mt-1"
                  data-testid="review-last-four"
                />
              </div>
              <div>
                <Label>Statement Period Start</Label>
                <Input
                  type="date"
                  value={reviewForm.statement_period_start || ''}
                  onChange={e => setReviewForm(f => ({ ...f, statement_period_start: e.target.value }))}
                  className="mt-1"
                  data-testid="review-period-start"
                />
              </div>
            </div>
            <div>
              <Label>Statement Period End</Label>
              <Input
                type="date"
                value={reviewForm.statement_period_end || ''}
                onChange={e => setReviewForm(f => ({ ...f, statement_period_end: e.target.value }))}
                className="mt-1"
                data-testid="review-period-end"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Beginning Balance</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={reviewForm.beginning_balance ?? ''}
                  onChange={e => setReviewForm(f => ({ ...f, beginning_balance: e.target.value }))}
                  className="mt-1"
                  data-testid="review-beginning-balance"
                />
              </div>
              <div>
                <Label>Ending Balance</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={reviewForm.ending_balance ?? ''}
                  onChange={e => setReviewForm(f => ({ ...f, ending_balance: e.target.value }))}
                  className="mt-1"
                  data-testid="review-ending-balance"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Total Deposits</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={reviewForm.total_deposits ?? ''}
                  onChange={e => setReviewForm(f => ({ ...f, total_deposits: e.target.value }))}
                  className="mt-1"
                  data-testid="review-total-deposits"
                />
              </div>
              <div>
                <Label>Total Withdrawals</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={reviewForm.total_withdrawals ?? ''}
                  onChange={e => setReviewForm(f => ({ ...f, total_withdrawals: e.target.value }))}
                  className="mt-1"
                  data-testid="review-total-withdrawals"
                />
              </div>
            </div>
            <Button className="w-full" onClick={handleSaveReview} disabled={saving} data-testid="review-save-btn">
              {saving ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving...</> : 'Save Corrections'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}