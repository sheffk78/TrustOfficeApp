import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import {
  Plus, Search, Calendar as CalendarIcon, ArrowUpRight, ArrowDownLeft,
  FileSpreadsheet, Tag, Trash2, Filter, X, Upload, ChevronDown,
  ArrowUpDown, CheckSquare, Loader2
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const CLASSIFICATIONS = [
  'Distribution', 'Compensation', 'Inter-Entity Transfer',
  'Operational Expense', 'Capital Contribution', 'Tax Payment', 'Other'
];

const DIRECTION_OPTIONS = [
  { value: 'inflow', label: 'Inflow', icon: ArrowDownLeft, color: 'text-emerald-600' },
  { value: 'outflow', label: 'Outflow', icon: ArrowUpRight, color: 'text-red-500' },
];

const classificationColors = {
  'Distribution': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  'Compensation': 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  'Inter-Entity Transfer': 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  'Operational Expense': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  'Capital Contribution': 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  'Tax Payment': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  'Other': 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
};

export default function TransactionLedgerPage() {
  const { selectedTrust, trusts } = useAuth();
  const { showUpgradeModal } = useUpgradeModal();

  // Core state
  const [transactions, setTransactions] = useState([]);
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // Filters
  const [filterEntity, setFilterEntity] = useState('all');
  const [filterClassification, setFilterClassification] = useState('all');
  const [filterDirection, setFilterDirection] = useState('all');

  // Create dialog
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    entity_id: '', date: '', amount: '', direction: 'outflow',
    source_account: '', destination_account: '',
    governance_classification: '', purpose_memo: '', other_note: ''
  });
  const [datePickerOpen, setDatePickerOpen] = useState(false);

  // CSV import
  const [showImport, setShowImport] = useState(false);
  const [csvData, setCsvData] = useState([]);
  const [csvHeaders, setCsvHeaders] = useState([]);
  const [csvMapping, setCsvMapping] = useState({ date: '', amount: '', description: '' });
  const [importEntity, setImportEntity] = useState('');
  const [importStep, setImportStep] = useState(1); // 1=upload, 2=map, 3=classify
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef(null);

  // Bulk selection
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [showBulkClassify, setShowBulkClassify] = useState(false);
  const [bulkClassification, setBulkClassification] = useState('');
  const [bulkMemo, setBulkMemo] = useState('');
  const [bulkOtherNote, setBulkOtherNote] = useState('');

  const loadData = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const [txnRes, entRes] = await Promise.all([
        fetchWithAuth(`/transactions?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/entities?trust_id=${selectedTrust.trust_id}`)
      ]);
      if (txnRes.ok) setTransactions(await txnRes.json());
      if (entRes.ok) setEntities(await entRes.json());
    } catch (e) {
      toast.error('Failed to load transaction data');
    } finally {
      setLoading(false);
    }
  }, [selectedTrust]);

  useEffect(() => { loadData(); }, [loadData]);

  // Reset entity filter when entities change
  useEffect(() => {
    if (entities.length > 0 && !form.entity_id) {
      setForm(f => ({ ...f, entity_id: entities[0].entity_id }));
    }
  }, [entities]);

  // Filtered transactions
  const filtered = transactions.filter(t => {
    if (filterEntity !== 'all' && t.entity_id !== filterEntity) return false;
    if (filterClassification !== 'all' && t.governance_classification !== filterClassification) return false;
    if (filterDirection !== 'all' && t.direction !== filterDirection) return false;
    if (search) {
      const s = search.toLowerCase();
      return (t.purpose_memo?.toLowerCase().includes(s) ||
              t.source_account?.toLowerCase().includes(s) ||
              t.destination_account?.toLowerCase().includes(s) ||
              t.entity_name?.toLowerCase().includes(s));
    }
    return true;
  });

  // Summary stats
  const totalInflows = filtered.filter(t => t.direction === 'inflow').reduce((s, t) => s + t.amount, 0);
  const totalOutflows = filtered.filter(t => t.direction === 'outflow').reduce((s, t) => s + t.amount, 0);

  // ==================== CREATE ====================
  const handleCreate = async () => {
    if (!form.entity_id || !form.date || !form.amount || !form.governance_classification) {
      toast.error('Please fill in all required fields');
      return;
    }
    if (form.governance_classification === 'Other' && !form.other_note.trim()) {
      toast.error('A note is required for "Other" classification');
      return;
    }
    setCreating(true);
    try {
      const res = await fetchWithAuth('/transactions', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          entity_id: form.entity_id,
          date: form.date,
          amount: parseFloat(form.amount),
          direction: form.direction,
          source_account: form.source_account,
          destination_account: form.destination_account,
          governance_classification: form.governance_classification,
          purpose_memo: form.purpose_memo,
          other_note: form.other_note
        })
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
      toast.success('Transaction recorded');
      setShowCreate(false);
      setForm({ entity_id: entities[0]?.entity_id || '', date: '', amount: '', direction: 'outflow', source_account: '', destination_account: '', governance_classification: '', purpose_memo: '', other_note: '' });
      loadData();
    } catch (e) {
      if (e.message?.includes('subscription') || e.message?.includes('402')) showUpgradeModal();
      else toast.error(e.message);
    } finally {
      setCreating(false);
    }
  };

  // ==================== DELETE ====================
  const handleDelete = async (id) => {
    if (!window.confirm('Delete this transaction? The audit trail will be preserved.')) return;
    try {
      const res = await fetchWithAuth(`/transactions/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed');
      toast.success('Transaction deleted');
      loadData();
    } catch {
      toast.error('Failed to delete');
    }
  };

  // ==================== CSV IMPORT ====================
  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target.result;
      const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
      if (lines.length < 2) { toast.error('CSV must have a header row and at least one data row'); return; }
      const headers = lines[0].split(',').map(h => h.replace(/"/g, '').trim());
      const rows = lines.slice(1).map(line => {
        const vals = line.split(',').map(v => v.replace(/"/g, '').trim());
        const obj = {};
        headers.forEach((h, i) => { obj[h] = vals[i] || ''; });
        return obj;
      });
      setCsvHeaders(headers);
      setCsvData(rows);
      // Auto-detect common mappings
      const lower = headers.map(h => h.toLowerCase());
      setCsvMapping({
        date: headers[lower.findIndex(h => h.includes('date'))] || '',
        amount: headers[lower.findIndex(h => h.includes('amount') || h.includes('debit') || h.includes('credit'))] || '',
        description: headers[lower.findIndex(h => h.includes('desc') || h.includes('memo') || h.includes('payee'))] || ''
      });
      setImportStep(2);
    };
    reader.readAsText(file);
  };

  const handleImport = async () => {
    if (!importEntity || !csvMapping.date || !csvMapping.amount) {
      toast.error('Please select entity and map date + amount columns');
      return;
    }
    setImporting(true);
    try {
      const rows = csvData.map(row => {
        const rawAmount = parseFloat(row[csvMapping.amount]?.replace(/[^0-9.\-]/g, '')) || 0;
        const direction = rawAmount < 0 ? 'outflow' : 'inflow';
        return {
          date: row[csvMapping.date] || new Date().toISOString().slice(0, 10),
          amount: Math.abs(rawAmount),
          direction,
          description: row[csvMapping.description] || '',
          purpose_memo: row[csvMapping.description] || ''
        };
      }).filter(r => r.amount > 0);

      const res = await fetchWithAuth('/transactions/import', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          entity_id: importEntity,
          rows
        })
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Import failed');
      const imported = await res.json();
      toast.success(`${imported.length} transactions imported — classify them now`);
      setShowImport(false);
      setCsvData([]);
      setImportStep(1);
      loadData();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setImporting(false);
    }
  };

  // ==================== BULK CLASSIFY ====================
  const handleBulkClassify = async () => {
    if (!bulkClassification) { toast.error('Select a classification'); return; }
    if (bulkClassification === 'Other' && !bulkOtherNote.trim()) {
      toast.error('A note is required for "Other"'); return;
    }
    try {
      const res = await fetchWithAuth('/transactions/bulk-classify', {
        method: 'POST',
        body: JSON.stringify({
          transaction_ids: [...selectedIds],
          governance_classification: bulkClassification,
          purpose_memo: bulkMemo,
          other_note: bulkOtherNote
        })
      });
      if (!res.ok) throw new Error('Failed');
      const data = await res.json();
      toast.success(`${data.modified} transactions classified`);
      setSelectedIds(new Set());
      setShowBulkClassify(false);
      setBulkClassification('');
      setBulkMemo('');
      setBulkOtherNote('');
      loadData();
    } catch {
      toast.error('Bulk classify failed');
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filtered.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(filtered.map(t => t.transaction_id)));
  };

  if (!selectedTrust) {
    return (
      <div className="flex min-h-screen bg-background">
        <Sidebar />
        <main className="flex-1 p-4 md:p-8">
          <p className="text-muted-foreground">Select a trust to view its transaction ledger.</p>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 p-4 md:p-8 pb-24 md:pb-8 overflow-x-hidden" data-testid="transaction-ledger-page">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl md:text-3xl font-serif text-foreground tracking-tight" data-testid="ledger-title">
              Transaction Ledger
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Log and classify all money movement for governance evidence
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => { setShowImport(true); setImportStep(1); }} data-testid="import-csv-btn">
              <Upload className="w-4 h-4 mr-2" /> Import CSV
            </Button>
            <Button size="sm" onClick={() => setShowCreate(true)} data-testid="add-transaction-btn">
              <Plus className="w-4 h-4 mr-2" /> Add Transaction
            </Button>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Total Inflows</p>
            <p className="text-xl font-semibold text-emerald-600" data-testid="total-inflows">
              ${totalInflows.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Total Outflows</p>
            <p className="text-xl font-semibold text-red-500" data-testid="total-outflows">
              ${totalOutflows.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Net Flow</p>
            <p className={`text-xl font-semibold ${totalInflows - totalOutflows >= 0 ? 'text-emerald-600' : 'text-red-500'}`} data-testid="net-flow">
              ${(totalInflows - totalOutflows).toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </p>
          </div>
        </div>

        {/* Filters & Search */}
        <div className="flex flex-col md:flex-row gap-3 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input placeholder="Search memo, accounts..." value={search} onChange={e => setSearch(e.target.value)}
              className="pl-9" data-testid="search-input" />
          </div>
          <Select value={filterEntity} onValueChange={setFilterEntity}>
            <SelectTrigger className="w-full md:w-[180px]" data-testid="filter-entity">
              <Filter className="w-4 h-4 mr-2" /><SelectValue placeholder="Entity" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Entities</SelectItem>
              {entities.map(e => <SelectItem key={e.entity_id} value={e.entity_id}>{e.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filterClassification} onValueChange={setFilterClassification}>
            <SelectTrigger className="w-full md:w-[180px]" data-testid="filter-classification">
              <Tag className="w-4 h-4 mr-2" /><SelectValue placeholder="Classification" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              {CLASSIFICATIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filterDirection} onValueChange={setFilterDirection}>
            <SelectTrigger className="w-full md:w-[140px]" data-testid="filter-direction">
              <ArrowUpDown className="w-4 h-4 mr-2" /><SelectValue placeholder="Direction" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="inflow">Inflows</SelectItem>
              <SelectItem value="outflow">Outflows</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Bulk action bar */}
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-3 mb-4 p-3 rounded-lg bg-navy/5 dark:bg-navy/20 border border-navy/20" data-testid="bulk-action-bar">
            <span className="text-sm font-medium">{selectedIds.size} selected</span>
            <Button size="sm" variant="outline" onClick={() => setShowBulkClassify(true)} data-testid="bulk-classify-btn">
              <Tag className="w-4 h-4 mr-2" /> Classify Selected
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
              <X className="w-4 h-4" />
            </Button>
          </div>
        )}

        {/* Transaction Table */}
        <div className="rounded-lg border border-border overflow-hidden bg-card">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16 px-4">
              <FileSpreadsheet className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" />
              <p className="text-muted-foreground font-medium">No transactions yet</p>
              <p className="text-sm text-muted-foreground/70 mt-1">Add transactions manually or import a bank statement CSV</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="p-3 text-left w-10">
                      <Checkbox checked={selectedIds.size === filtered.length && filtered.length > 0}
                        onCheckedChange={toggleSelectAll} data-testid="select-all-checkbox" />
                    </th>
                    <th className="p-3 text-left font-medium text-muted-foreground">Date</th>
                    <th className="p-3 text-left font-medium text-muted-foreground">Entity</th>
                    <th className="p-3 text-right font-medium text-muted-foreground">Amount</th>
                    <th className="p-3 text-left font-medium text-muted-foreground">From / To</th>
                    <th className="p-3 text-left font-medium text-muted-foreground">Classification</th>
                    <th className="p-3 text-left font-medium text-muted-foreground">Memo</th>
                    <th className="p-3 text-center font-medium text-muted-foreground w-16"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(t => (
                    <tr key={t.transaction_id} className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                      data-testid={`transaction-row-${t.transaction_id}`}>
                      <td className="p-3">
                        <Checkbox checked={selectedIds.has(t.transaction_id)}
                          onCheckedChange={() => toggleSelect(t.transaction_id)} />
                      </td>
                      <td className="p-3 whitespace-nowrap text-foreground">
                        {(() => { try { return format(parseISO(t.date), 'MMM d, yyyy'); } catch { return t.date; } })()}
                      </td>
                      <td className="p-3 text-foreground whitespace-nowrap">{t.entity_name}</td>
                      <td className="p-3 text-right whitespace-nowrap font-medium">
                        <span className={t.direction === 'inflow' ? 'text-emerald-600' : 'text-red-500'}>
                          {t.direction === 'inflow' ? '+' : '-'}${t.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                        </span>
                      </td>
                      <td className="p-3 text-muted-foreground text-xs max-w-[160px] truncate">
                        {t.direction === 'outflow'
                          ? <span>{t.source_account} <ArrowUpRight className="w-3 h-3 inline" /> {t.destination_account}</span>
                          : <span>{t.source_account} <ArrowDownLeft className="w-3 h-3 inline" /> {t.destination_account}</span>
                        }
                      </td>
                      <td className="p-3">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${classificationColors[t.governance_classification] || 'bg-gray-100 text-gray-700'}`}>
                          {t.governance_classification}
                        </span>
                      </td>
                      <td className="p-3 text-muted-foreground text-xs max-w-[200px] truncate">{t.purpose_memo}</td>
                      <td className="p-3 text-center">
                        <Button variant="ghost" size="sm" onClick={() => handleDelete(t.transaction_id)}
                          data-testid={`delete-txn-${t.transaction_id}`}>
                          <Trash2 className="w-4 h-4 text-muted-foreground hover:text-red-500" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <p className="text-xs text-muted-foreground mt-3">
          Showing {filtered.length} of {transactions.length} transactions
        </p>
      </main>
      <MobileBottomNav />

      {/* ==================== CREATE DIALOG ==================== */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Record Transaction</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <Label>Entity *</Label>
              <Select value={form.entity_id} onValueChange={v => setForm(f => ({ ...f, entity_id: v }))}>
                <SelectTrigger data-testid="create-entity-select"><SelectValue placeholder="Select entity" /></SelectTrigger>
                <SelectContent>
                  {entities.map(e => <SelectItem key={e.entity_id} value={e.entity_id}>{e.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Date *</Label>
                <Popover open={datePickerOpen} onOpenChange={setDatePickerOpen}>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="w-full justify-start font-normal" data-testid="create-date-btn">
                      <CalendarIcon className="w-4 h-4 mr-2" />
                      {form.date ? format(parseISO(form.date), 'MMM d, yyyy') : 'Pick date'}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar mode="single" selected={form.date ? parseISO(form.date) : undefined}
                      onSelect={d => { if (d) { setForm(f => ({ ...f, date: format(d, 'yyyy-MM-dd') })); setDatePickerOpen(false); } }} />
                  </PopoverContent>
                </Popover>
              </div>
              <div>
                <Label>Amount *</Label>
                <Input type="number" step="0.01" min="0" placeholder="0.00"
                  value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
                  data-testid="create-amount-input" />
              </div>
            </div>

            <div>
              <Label>Direction *</Label>
              <Select value={form.direction} onValueChange={v => setForm(f => ({ ...f, direction: v }))}>
                <SelectTrigger data-testid="create-direction-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {DIRECTION_OPTIONS.map(d => (
                    <SelectItem key={d.value} value={d.value}>
                      <span className="flex items-center gap-2"><d.icon className={`w-4 h-4 ${d.color}`} /> {d.label}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Source Account</Label>
                <Input placeholder="e.g. Trust Checking" value={form.source_account}
                  onChange={e => setForm(f => ({ ...f, source_account: e.target.value }))}
                  data-testid="create-source-input" />
              </div>
              <div>
                <Label>Destination Account</Label>
                <Input placeholder="e.g. Personal Account" value={form.destination_account}
                  onChange={e => setForm(f => ({ ...f, destination_account: e.target.value }))}
                  data-testid="create-dest-input" />
              </div>
            </div>

            <div>
              <Label>Governance Classification *</Label>
              <Select value={form.governance_classification}
                onValueChange={v => setForm(f => ({ ...f, governance_classification: v }))}>
                <SelectTrigger data-testid="create-classification-select"><SelectValue placeholder="Select classification" /></SelectTrigger>
                <SelectContent>
                  {CLASSIFICATIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            {form.governance_classification === 'Other' && (
              <div>
                <Label>Note (required for "Other") *</Label>
                <Input value={form.other_note} onChange={e => setForm(f => ({ ...f, other_note: e.target.value }))}
                  placeholder="Explain the nature of this transaction" data-testid="create-other-note" />
              </div>
            )}

            <div>
              <Label>Purpose / Memo</Label>
              <Textarea placeholder="Describe the purpose of this transaction"
                value={form.purpose_memo} onChange={e => setForm(f => ({ ...f, purpose_memo: e.target.value }))}
                rows={2} data-testid="create-memo-input" />
            </div>

            <Button className="w-full" onClick={handleCreate} disabled={creating} data-testid="create-submit-btn">
              {creating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving...</> : 'Record Transaction'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ==================== CSV IMPORT DIALOG ==================== */}
      <Dialog open={showImport} onOpenChange={v => { setShowImport(v); if (!v) { setImportStep(1); setCsvData([]); } }}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Import Bank Statement CSV</DialogTitle>
          </DialogHeader>

          {importStep === 1 && (
            <div className="space-y-4 mt-2">
              <div>
                <Label>Entity *</Label>
                <Select value={importEntity} onValueChange={setImportEntity}>
                  <SelectTrigger data-testid="import-entity-select"><SelectValue placeholder="Select entity" /></SelectTrigger>
                  <SelectContent>
                    {entities.map(e => <SelectItem key={e.entity_id} value={e.entity_id}>{e.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
                onClick={() => fileInputRef.current?.click()}>
                <Upload className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">Click to upload a CSV file</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Common bank statement format (date, description, amount)</p>
                <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={handleFileUpload} data-testid="csv-file-input" />
              </div>
            </div>
          )}

          {importStep === 2 && (
            <div className="space-y-4 mt-2">
              <p className="text-sm text-muted-foreground">
                Map your CSV columns to TrustOffice fields. Found <strong>{csvData.length}</strong> rows.
              </p>
              <div className="grid grid-cols-1 gap-3">
                {['date', 'amount', 'description'].map(field => (
                  <div key={field}>
                    <Label className="capitalize">{field} Column *</Label>
                    <Select value={csvMapping[field]} onValueChange={v => setCsvMapping(m => ({ ...m, [field]: v }))}>
                      <SelectTrigger data-testid={`map-${field}-select`}><SelectValue placeholder={`Select ${field} column`} /></SelectTrigger>
                      <SelectContent>
                        {csvHeaders.map(h => <SelectItem key={h} value={h}>{h}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>

              {/* Preview */}
              {csvData.length > 0 && csvMapping.date && csvMapping.amount && (
                <div className="rounded border border-border overflow-hidden">
                  <p className="text-xs font-medium p-2 bg-muted/50">Preview (first 5 rows)</p>
                  <table className="w-full text-xs">
                    <thead><tr className="border-b border-border bg-muted/30">
                      <th className="p-2 text-left">Date</th><th className="p-2 text-right">Amount</th><th className="p-2 text-left">Description</th>
                    </tr></thead>
                    <tbody>
                      {csvData.slice(0, 5).map((row, i) => (
                        <tr key={i} className="border-b border-border/30">
                          <td className="p-2">{row[csvMapping.date]}</td>
                          <td className="p-2 text-right">{row[csvMapping.amount]}</td>
                          <td className="p-2 truncate max-w-[200px]">{row[csvMapping.description]}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="flex gap-2">
                <Button variant="outline" onClick={() => { setImportStep(1); setCsvData([]); }}>Back</Button>
                <Button className="flex-1" onClick={handleImport} disabled={importing} data-testid="import-submit-btn">
                  {importing ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Importing...</> : `Import ${csvData.length} Transactions`}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Imported transactions default to "Other" classification. Use bulk-classify to tag them efficiently.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ==================== BULK CLASSIFY DIALOG ==================== */}
      <Dialog open={showBulkClassify} onOpenChange={setShowBulkClassify}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Classify {selectedIds.size} Transactions</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <Label>Governance Classification *</Label>
              <Select value={bulkClassification} onValueChange={setBulkClassification}>
                <SelectTrigger data-testid="bulk-classification-select"><SelectValue placeholder="Select classification" /></SelectTrigger>
                <SelectContent>
                  {CLASSIFICATIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {bulkClassification === 'Other' && (
              <div>
                <Label>Note (required) *</Label>
                <Input value={bulkOtherNote} onChange={e => setBulkOtherNote(e.target.value)} placeholder="Explain classification" />
              </div>
            )}
            <div>
              <Label>Purpose / Memo (optional)</Label>
              <Textarea value={bulkMemo} onChange={e => setBulkMemo(e.target.value)} rows={2} placeholder="Shared memo for selected transactions" />
            </div>
            <Button className="w-full" onClick={handleBulkClassify} data-testid="bulk-classify-submit-btn">
              Apply Classification
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
