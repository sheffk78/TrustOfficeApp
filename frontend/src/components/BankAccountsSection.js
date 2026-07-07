import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import { showError } from '@/utils/errors';
import {
  Landmark, Plus, ChevronDown, ChevronRight, Loader2, Trash2,
  Building2, CreditCard, FileText
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const ACCOUNT_TYPES = [
  'Checking',
  'Savings',
  'Money Market',
  'CD',
  'Investment / Brokerage',
  'Trust',
];

const EXTRACTION_BADGE = {
  pending: { label: 'Extracting', cls: 'bg-gold/10 text-gold' },
  completed: { label: 'Verified', cls: 'bg-success/10 text-success' },
  needs_review: { label: 'Needs Review', cls: 'bg-warning/10 text-warning' },
  failed: { label: 'Failed', cls: 'bg-error/10 text-error' },
};

const fmtMoney = (n) => {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

/**
 * Bank Accounts section for the Entity Detail page.
 * Lists accounts for a given trust + entity, supports creating new accounts,
 * and shows per-account statement history timeline.
 */
export default function BankAccountsSection({ entityId }) {
  const { selectedTrust } = useAuth();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    nickname: '',
    institution: '',
    last_four: '',
    account_type: 'Checking',
  });
  const [expanded, setExpanded] = useState({});
  const [statements, setStatements] = useState({});
  const [stmtLoading, setStmtLoading] = useState({});

  const loadAccounts = useCallback(async () => {
    if (!selectedTrust || !entityId) return;
    setLoading(true);
    try {
      const res = await fetchWithAuth(
        `/trusts/${selectedTrust.trust_id}/entities/${entityId}/bank-accounts`
      );
      if (res.ok) {
        setAccounts(await res.json());
      } else {
        setAccounts([]);
      }
    } catch (e) {
      console.error('Failed to load bank accounts:', e);
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, [selectedTrust, entityId]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  const handleCreate = async () => {
    if (!form.nickname.trim() || !form.institution.trim() || !form.last_four.trim()) {
      toast.error('Please fill in nickname, institution, and last 4 digits');
      return;
    }
    if (!/^\d{4}$/.test(form.last_four)) {
      toast.error('Last 4 must be exactly 4 digits');
      return;
    }
    setCreating(true);
    try {
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/bank-accounts`, {
        method: 'POST',
        body: JSON.stringify({
          entity_id: entityId,
          nickname: form.nickname.trim(),
          institution: form.institution.trim(),
          last_four: form.last_four,
          account_type: form.account_type,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to create bank account');
      }
      toast.success('Bank account added');
      setShowAdd(false);
      setForm({ nickname: '', institution: '', last_four: '', account_type: 'Checking' });
      loadAccounts();
    } catch (e) {
      showError(toast, e, { operation: 'create_bank_account', page: 'EntityDetail' });
    } finally {
      setCreating(false);
    }
  };

  const handleArchive = async (accountId) => {
    if (!confirm('Archive this bank account? You can still view its statement history.')) return;
    try {
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/bank-accounts/${accountId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to archive account');
      toast.success('Account archived');
      loadAccounts();
    } catch (e) {
      showError(toast, e, { operation: 'archive_bank_account', page: 'EntityDetail' });
    }
  };

  const loadStatements = async (accountId) => {
    setStmtLoading(prev => ({ ...prev, [accountId]: true }));
    try {
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/bank-accounts/${accountId}/statements`);
      if (res.ok) {
        const data = await res.json();
        setStatements(prev => ({ ...prev, [accountId]: data }));
      }
    } catch (e) {
      console.error('Failed to load statements:', e);
    } finally {
      setStmtLoading(prev => ({ ...prev, [accountId]: false }));
    }
  };

  const toggleExpand = (accountId) => {
    setExpanded(prev => {
      const next = { ...prev, [accountId]: !prev[accountId] };
      if (next[accountId] && !statements[accountId]) {
        loadStatements(accountId);
      }
      return next;
    });
  };

  const latestBalance = (account) => {
    if (account.latest_statement_ending_balance != null) {
      return account.latest_statement_ending_balance;
    }
    if (account.statements?.length) {
      const sorted = [...account.statements].sort(
        (a, b) => new Date(b.statement_period_end) - new Date(a.statement_period_end)
      );
      return sorted[0]?.ending_balance;
    }
    return null;
  };

  return (
    <div data-testid="bank-accounts-section" className="card-trust">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Landmark className="w-5 h-5 text-navy" />
          <h2 className="font-serif text-lg text-navy">Bank Accounts</h2>
        </div>
        <Button size="sm" variant="outline" onClick={() => setShowAdd(true)} data-testid="add-bank-account-btn">
          <Plus className="w-4 h-4 mr-1" /> Add Account
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-6">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : accounts.length === 0 ? (
        <div className="text-center py-8">
          <Landmark className="w-8 h-8 text-muted-foreground/40 mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No bank accounts linked to this entity yet</p>
          <Button variant="link" size="sm" onClick={() => setShowAdd(true)} className="mt-1">
            Add your first account
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {accounts.map(account => {
            const bal = latestBalance(account);
            const isExpanded = expanded[account.account_id];
            const acctStmts = statements[account.account_id] || [];
            const isLoadingStmts = stmtLoading[account.account_id];

            return (
              <div key={account.account_id} className="border border-navy/10 rounded" data-testid={`bank-account-${account.account_id}`}>
                {/* Account Card Header */}
                <div className="flex items-start gap-3 p-3">
                  <div className="w-9 h-9 bg-navy/10 flex items-center justify-center flex-shrink-0">
                    <CreditCard className="w-4 h-4 text-navy" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-medium text-navy text-sm">{account.nickname}</p>
                      <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-navy/5 text-navy/70">
                        {account.account_type}
                      </span>
                      {account.archived && (
                        <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">
                          Archived
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {account.institution} · ••••{account.last_four}
                    </p>
                    {bal != null && (
                      <p className="text-sm font-mono text-navy mt-1">
                        Latest balance: ${fmtMoney(bal)}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {!account.archived && (
                      <button
                        onClick={() => handleArchive(account.account_id)}
                        className="text-muted-foreground hover:text-red-500 p-1"
                        title="Archive account"
                        data-testid={`archive-account-${account.account_id}`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button
                      onClick={() => toggleExpand(account.account_id)}
                      className="text-muted-foreground hover:text-navy p-1"
                      data-testid={`toggle-statements-${account.account_id}`}
                    >
                      {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Statement History (collapsible) */}
                {isExpanded && (
                  <div className="border-t border-navy/10 bg-subtle-bg/50 p-3" data-testid={`statements-${account.account_id}`}>
                    {isLoadingStmts ? (
                      <div className="flex justify-center py-4">
                        <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                      </div>
                    ) : acctStmts.length === 0 ? (
                      <div className="text-center py-4">
                        <FileText className="w-6 h-6 text-muted-foreground/40 mx-auto mb-1" />
                        <p className="text-xs text-muted-foreground">No statements uploaded yet</p>
                        <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                          Upload a bank statement in the Vault to populate this timeline.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-navy mb-2">Statement History</p>
                        {acctStmts
                          .sort((a, b) => new Date(b.statement_period_end || b.created_at) - new Date(a.statement_period_end || a.created_at))
                          .map(stmt => {
                            const badge = EXTRACTION_BADGE[stmt.extraction_status] || EXTRACTION_BADGE.pending;
                            const periodLabel = stmt.statement_period_start && stmt.statement_period_end
                              ? `${format(parseISO(stmt.statement_period_start), 'MMM yyyy')} - ${format(parseISO(stmt.statement_period_end), 'MMM yyyy')}`
                              : 'Period unknown';
                            return (
                              <div key={stmt.statement_id} className="flex items-start gap-3 p-2 border border-navy/5 bg-white rounded">
                                <div className="w-6 h-6 bg-navy/5 flex items-center justify-center flex-shrink-0 mt-0.5">
                                  <FileText className="w-3 h-3 text-navy/60" />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="text-xs font-medium text-navy">{periodLabel}</p>
                                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                                    {stmt.beginning_balance != null && (
                                      <span className="text-[10px] text-muted-foreground font-mono">
                                        Start: ${fmtMoney(stmt.beginning_balance)}
                                      </span>
                                    )}
                                    {stmt.ending_balance != null && (
                                      <span className="text-[10px] text-navy font-mono">
                                        End: ${fmtMoney(stmt.ending_balance)}
                                      </span>
                                    )}
                                  </div>
                                </div>
                                <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${badge.cls} flex-shrink-0`}>
                                  {badge.label}
                                </span>
                              </div>
                            );
                          })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Add Bank Account Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add Bank Account</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <Label>Nickname *</Label>
              <Input
                value={form.nickname}
                onChange={e => setForm(f => ({ ...f, nickname: e.target.value }))}
                placeholder="e.g., Trust Operating Checking"
                className="mt-1"
                data-testid="ba-nickname"
              />
            </div>
            <div>
              <Label>Institution *</Label>
              <Input
                value={form.institution}
                onChange={e => setForm(f => ({ ...f, institution: e.target.value }))}
                placeholder="e.g., Chase, Wells Fargo"
                className="mt-1"
                data-testid="ba-institution"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Last 4 Digits *</Label>
                <Input
                  value={form.last_four}
                  onChange={e => setForm(f => ({ ...f, last_four: e.target.value.replace(/\D/g, '').slice(0, 4) }))}
                  placeholder="1234"
                  maxLength={4}
                  inputMode="numeric"
                  className="mt-1"
                  data-testid="ba-last-four"
                />
              </div>
              <div>
                <Label>Account Type</Label>
                <Select value={form.account_type} onValueChange={v => setForm(f => ({ ...f, account_type: v }))}>
                  <SelectTrigger className="mt-1" data-testid="ba-type-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ACCOUNT_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Button className="w-full" onClick={handleCreate} disabled={creating} data-testid="ba-create-btn">
              {creating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving...</> : 'Add Account'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}