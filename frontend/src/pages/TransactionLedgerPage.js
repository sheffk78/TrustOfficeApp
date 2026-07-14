import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
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
import { showError } from '../utils/errors';
import { fetchWithAuth } from '@/utils/api';
import { SeparationAlertsPanel } from '@/components/SeparationAlertsPanel';
import PageHelpButton from '@/components/PageHelpButton';
import {
  Plus, Search, Calendar as CalendarIcon, ArrowUpRight, ArrowDownLeft,
  FileSpreadsheet, Tag, Trash2, Filter, X, Upload, ChevronDown,
  ArrowUpDown, CheckSquare, Loader2,
  AlertTriangle, Link2, FileText, Building2, Edit2
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const CLASSIFICATIONS = [
  'Distribution', 'Compensation', 'Inter-Entity Transfer',
  'Operational Expense', 'Capital Contribution', 'Tax Payment', 'Other'
];

const DIRECTION_OPTIONS = [
  { value: 'inflow', label: 'Inflow', icon: ArrowDownLeft, color: 'text-success' },
  { value: 'outflow', label: 'Outflow', icon: ArrowUpRight, color: 'text-error' },
];

const classificationColors = {
  'Distribution': 'bg-gold/10 text-gold dark:bg-gold/20 dark:text-gold',
  'Compensation': 'bg-navy/10 text-navy dark:bg-navy/20 dark:text-navy',
  'Inter-Entity Transfer': 'bg-warning/10 text-warning dark:bg-warning/20 dark:text-warning',
  'Operational Expense': 'bg-muted text-muted-foreground dark:bg-muted/30 dark:text-muted-foreground',
  'Capital Contribution': 'bg-success/10 text-success dark:bg-success/20 dark:text-success',
  'Tax Payment': 'bg-error/10 text-error dark:bg-error/20 dark:text-error',
  'Other': 'bg-navy/5 text-navy/70 dark:bg-navy/20 dark:text-navy/70',
};

export default function TransactionLedgerPage() {
  const navigate = useNavigate();
  const { selectedTrust, trusts, isReadOnly } = useAuth();
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

  // Threshold alerts + Link Minutes
  const [thresholdAlerts, setThresholdAlerts] = useState([]);
  const [minutesList, setMinutesList] = useState([]);
  const [linkMinutesTxn, setLinkMinutesTxn] = useState(null); // transaction being linked
  const [selectedMinutesId, setSelectedMinutesId] = useState('');
  const [linking, setLinking] = useState(false);

  // Edit transaction
  const [showEdit, setShowEdit] = useState(false);
  const [editingTxn, setEditingTxn] = useState(null);
  const [editForm, setEditForm] = useState({
    entity_id: '', date: '', amount: '', direction: 'outflow',
    source_account: '', destination_account: '',
    governance_classification: '', purpose_memo: '', other_note: ''
  });
  const [editDatePickerOpen, setEditDatePickerOpen] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);

  const loadData = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const [txnRes, entRes, alertsRes, minutesRes] = await Promise.all([
        fetchWithAuth(`/transactions?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/entities?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/alerts?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/minutes?trust_id=${selectedTrust.trust_id}`),
      ]);
      if (txnRes.ok) setTransactions(await txnRes.json());
      if (entRes.ok) {
        const entData = await entRes.json();
        setEntities(entData.items || entData);
      }
      if (alertsRes.ok) {
        const allAlerts = await alertsRes.json();
        setThresholdAlerts(allAlerts.filter(a => a.alert_type === 'spending_threshold_exceeded' && a.status === 'active'));
      }
      if (minutesRes.ok) setMinutesList(await minutesRes.json());
    } catch (e) {
      showError(toast, e, { operation: 'load', page: 'TransactionLedger' });
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
      showError(toast, e, { operation: 'create_transaction', page: 'TransactionLedger' });
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
    } catch (e) {
      showError(toast, e, { operation: 'delete', page: 'TransactionLedger' });
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
      showError(toast, e, { operation: 'import_csv', page: 'TransactionLedger' });
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
    } catch (error) {
      showError(toast, error, { operation: 'bulk_classify', page: 'TransactionLedger' });
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

  // Map transaction_id → active threshold alert
  const thresholdAlertByTxn = new Map(thresholdAlerts.map(a => [a.transaction_id, a]));

  // ==================== LINK MINUTES ====================
  const openLinkMinutes = (txn) => {
    setLinkMinutesTxn(txn);
    setSelectedMinutesId(txn.linked_minutes_id || '');
  };

  const handleLinkMinutes = async () => {
    if (!linkMinutesTxn || !selectedMinutesId) {
      toast.error('Please select a minutes document');
      return;
    }
    setLinking(true);
    try {
      const res = await fetchWithAuth(`/transactions/${linkMinutesTxn.transaction_id}`, {
        method: 'PATCH',
        body: JSON.stringify({ linked_minutes_id: selectedMinutesId }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to link minutes');
      }
      toast.success('Minutes linked — threshold alert will auto-resolve');
      setLinkMinutesTxn(null);
      setSelectedMinutesId('');
      loadData(); // refresh transactions + alerts
    } catch (e) {
      showError(toast, e, { operation: 'link_minutes', page: 'TransactionLedger' });
    } finally {
      setLinking(false);
    }
  };

  // ==================== EDIT TRANSACTION ====================
  const openEdit = (txn) => {
    if (isReadOnly) {
      showUpgradeModal('edit transactions', 'button_click', 'transaction_ledger');
      return;
    }
    setEditingTxn(txn);
    setEditForm({
      entity_id: txn.entity_id || '',
      date: txn.date || '',
      amount: String(txn.amount ?? ''),
      direction: txn.direction || 'outflow',
      source_account: txn.source_account || '',
      destination_account: txn.destination_account || '',
      governance_classification: txn.governance_classification || '',
      purpose_memo: txn.purpose_memo || '',
      other_note: txn.other_note || '',
    });
    setShowEdit(true);
  };

  const handleEditSave = async () => {
    if (!editingTxn) return;
    if (!editForm.entity_id || !editForm.date || !editForm.amount || !editForm.governance_classification) {
      toast.error('Please fill in all required fields');
      return;
    }
    if (editForm.governance_classification === 'Other' && !editForm.other_note.trim()) {
      toast.error('A note is required for "Other" classification');
      return;
    }
    setSavingEdit(true);
    try {
      const res = await fetchWithAuth(`/transactions/${editingTxn.transaction_id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          entity_id: editForm.entity_id,
          date: editForm.date,
          amount: parseFloat(editForm.amount),
          direction: editForm.direction,
          source_account: editForm.source_account,
          destination_account: editForm.destination_account,
          governance_classification: editForm.governance_classification,
          purpose_memo: editForm.purpose_memo,
          other_note: editForm.other_note,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to update transaction');
      }
      toast.success('Transaction updated');
      setShowEdit(false);
      setEditingTxn(null);
      loadData();
    } catch (e) {
      if (e.message?.includes('subscription') || e.message?.includes('402')) showUpgradeModal();
      showError(toast, e, { operation: 'update_transaction', page: 'TransactionLedger' });
    } finally {
      setSavingEdit(false);
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content dot-grid">
          <div className="page-container">
            <p className="text-muted-foreground">Select a trust to view its transaction ledger.</p>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content dot-grid" data-testid="transaction-ledger-page">
        <div className="page-container">
        {/* Header */}
        <div className="page-header flex items-center justify-between">
          <div>
            <h1 className="page-title">Transaction Ledger</h1>
            <p className="page-subtitle">View and manage all trust financial transactions — track income, expenses, and transfers across accounts</p>
          </div>
          <div className="flex items-center gap-2">
            <PageHelpButton
              items={[
                { text: 'View and manage all trust financial transactions in one ledger' },
                { text: 'Track income, expenses, and transfers across accounts' },
                { text: 'Import CSV files and reconcile with bank statements' },
              ]}
              taPrompt="Help me understand the Transaction Ledger and how to add a transaction"
            />
            <Button variant="outline" size="sm" className="btn-secondary" onClick={() => { setShowImport(true); setImportStep(1); }} data-testid="import-csv-btn">
              <Upload className="w-4 h-4 mr-2" /> Import CSV
            </Button>
            <Button size="sm" className="btn-primary" onClick={() => setShowCreate(true)} data-testid="add-transaction-btn">
              <Plus className="w-4 h-4 mr-2" /> Add Transaction
            </Button>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Total Inflows</p>
            <p className="text-xl font-semibold text-success" data-testid="total-inflows">
              ${totalInflows.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </p>
          </div>
          <div className="border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Total Outflows</p>
            <p className="text-xl font-semibold text-error" data-testid="total-outflows">
              ${totalOutflows.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </p>
          </div>
          <div className="border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Net Flow</p>
            <p className={`text-xl font-semibold ${totalInflows - totalOutflows >= 0 ? 'text-success' : 'text-error'}`} data-testid="net-flow">
              ${(totalInflows - totalOutflows).toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </p>
          </div>
        </div>

        {/* Separation Alerts Panel */}
        <div className="mb-6 border border-border bg-card p-4">
          <SeparationAlertsPanel onLinkMinutes={(alert) => {
            const txn = transactions.find(t => t.transaction_id === alert.transaction_id);
            if (txn) openLinkMinutes(txn);
          }} />
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
          <div className="flex items-center gap-3 mb-4 p-3 bg-navy/5 dark:bg-navy/20 border border-navy/20" data-testid="bulk-action-bar">
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
        <div className="border border-border overflow-hidden bg-card">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : entities.length === 0 ? (
            <div className="card-trust p-12 flex flex-col items-center justify-center text-center">
              <Building2 className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" />
              <p className="text-muted-foreground font-medium">No entities yet</p>
              <p className="text-sm text-muted-foreground/70 mt-1 mb-4">Add a trust entity to start recording transactions.</p>
              <Button onClick={() => navigate('/structures')} className="btn-primary">
                <Building2 className="w-4 h-4 mr-2" /> Add Entity
              </Button>
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
                    <th className="p-3 text-center font-medium text-muted-foreground w-32">Threshold</th>
                    <th className="p-3 text-center font-medium text-muted-foreground w-24">Actions</th>
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
                        <span className={t.direction === 'inflow' ? 'text-success' : 'text-error'}>
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
                        <span className={`inline-block px-2 py-0.5 text-xs font-medium ${classificationColors[t.governance_classification] || 'bg-muted text-muted-foreground'}`}>
                          {t.governance_classification}
                        </span>
                      </td>
                      <td className="p-3 text-muted-foreground text-xs max-w-[200px] truncate">{t.purpose_memo}</td>
                      <td className="p-3 text-center">
                        {(() => {
                          const alert = thresholdAlertByTxn.get(t.transaction_id);
                          if (t.linked_minutes_id) {
                            return (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-success/10 text-success" title="Linked to minutes">
                                <FileText className="w-3 h-3" /> Linked
                              </span>
                            );
                          }
                          if (alert) {
                            return (
                              <div className="flex flex-col items-center gap-1">
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-warning/10 text-warning" title={alert.description}>
                                  <AlertTriangle className="w-3 h-3" /> Exceeded
                                </span>
                                <Button variant="ghost" size="sm" className="h-6 px-1.5 text-xs text-navy hover:text-navy/70"
                                  onClick={() => openLinkMinutes(t)}
                                  data-testid={`link-minutes-${t.transaction_id}`}>
                                  <Link2 className="w-3 h-3 mr-1" /> Link Minutes
                                </Button>
                              </div>
                            );
                          }
                          return null;
                        })()}
                      </td>
                      <td className="p-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <Button variant="ghost" size="sm" onClick={() => openEdit(t)}
                            data-testid={`edit-txn-${t.transaction_id}`}>
                            <Edit2 className="w-4 h-4 text-muted-foreground hover:text-navy" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => handleDelete(t.transaction_id)}
                            data-testid={`delete-txn-${t.transaction_id}`}>
                            <Trash2 className="w-4 h-4 text-muted-foreground hover:text-error" />
                          </Button>
                        </div>
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
        </div>
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
              <Label className="label-trust">Entity *</Label>
              <Select value={form.entity_id} onValueChange={v => setForm(f => ({ ...f, entity_id: v }))}>
                <SelectTrigger data-testid="create-entity-select"><SelectValue placeholder="Select entity" /></SelectTrigger>
                <SelectContent>
                  {entities.map(e => <SelectItem key={e.entity_id} value={e.entity_id}>{e.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="label-trust">Date *</Label>
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
                <Label className="label-trust">Amount *</Label>
                <Input type="number" step="0.01" min="0" placeholder="0.00" className="input-trust"
                  value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
                  data-testid="create-amount-input" />
              </div>
            </div>

            <div>
              <Label className="label-trust">Direction *</Label>
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
                <Label className="label-trust">Source Account</Label>
                <Input placeholder="e.g. Trust Checking" className="input-trust" value={form.source_account}
                  onChange={e => setForm(f => ({ ...f, source_account: e.target.value }))}
                  data-testid="create-source-input" />
              </div>
              <div>
                <Label className="label-trust">Destination Account</Label>
                <Input placeholder="e.g. Personal Account" className="input-trust" value={form.destination_account}
                  onChange={e => setForm(f => ({ ...f, destination_account: e.target.value }))}
                  data-testid="create-dest-input" />
              </div>
            </div>

            <div>
              <Label className="label-trust">Governance Classification *</Label>
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
                <Label className="label-trust">Note (required for "Other") *</Label>
                <Input className="input-trust" value={form.other_note} onChange={e => setForm(f => ({ ...f, other_note: e.target.value }))}
                  placeholder="Explain the nature of this transaction" data-testid="create-other-note" />
              </div>
            )}

            <div>
              <Label className="label-trust">Purpose / Memo</Label>
              <Textarea className="input-trust" placeholder="Describe the purpose of this transaction"
                value={form.purpose_memo} onChange={e => setForm(f => ({ ...f, purpose_memo: e.target.value }))}
                rows={2} data-testid="create-memo-input" />
            </div>

            <Button className="w-full btn-primary" onClick={handleCreate} disabled={creating} data-testid="create-submit-btn">
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
                <Label className="label-trust">Entity *</Label>
                <Select value={importEntity} onValueChange={setImportEntity}>
                  <SelectTrigger data-testid="import-entity-select"><SelectValue placeholder="Select entity" /></SelectTrigger>
                  <SelectContent>
                    {entities.map(e => <SelectItem key={e.entity_id} value={e.entity_id}>{e.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="border-2 border-dashed border-border p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
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
                    <Label className="capitalize label-trust">{field} Column *</Label>
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
                <div className="border border-border overflow-hidden">
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
                <Button className="flex-1 btn-primary" onClick={handleImport} disabled={importing} data-testid="import-submit-btn">
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
              <Label className="label-trust">Governance Classification *</Label>
              <Select value={bulkClassification} onValueChange={setBulkClassification}>
                <SelectTrigger data-testid="bulk-classification-select"><SelectValue placeholder="Select classification" /></SelectTrigger>
                <SelectContent>
                  {CLASSIFICATIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {bulkClassification === 'Other' && (
              <div>
                <Label className="label-trust">Note (required) *</Label>
                <Input className="input-trust" value={bulkOtherNote} onChange={e => setBulkOtherNote(e.target.value)} placeholder="Explain classification" />
              </div>
            )}
            <div>
              <Label className="label-trust">Purpose / Memo (optional)</Label>
              <Textarea className="input-trust" value={bulkMemo} onChange={e => setBulkMemo(e.target.value)} rows={2} placeholder="Shared memo for selected transactions" />
            </div>
            <Button className="w-full btn-primary" onClick={handleBulkClassify} data-testid="bulk-classify-submit-btn">
              Apply Classification
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ==================== LINK MINUTES DIALOG ==================== */}
      <Dialog open={!!linkMinutesTxn} onOpenChange={v => { if (!v) { setLinkMinutesTxn(null); setSelectedMinutesId(''); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Link Minutes to Transaction</DialogTitle>
          </DialogHeader>
          {linkMinutesTxn && (
            <div className="space-y-4 mt-2">
              <div className="p-3 bg-warning/10 border border-warning/20">
                <p className="text-sm font-medium text-foreground">
                  {linkMinutesTxn.direction === 'inflow' ? '+' : '-'}${linkMinutesTxn.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">{linkMinutesTxn.purpose_memo || 'No memo'}</p>
                <p className="text-xs text-warning mt-1">This transaction exceeded the spending threshold. Linking minutes documents the trustee approval.</p>
              </div>

              <div>
                <Label className="label-trust">Select Minutes Document *</Label>
                {minutesList.length === 0 ? (
                  <p className="text-sm text-muted-foreground mt-2">
                    No minutes found. Create minutes first from the Minutes page.
                  </p>
                ) : (
                  <Select value={selectedMinutesId} onValueChange={setSelectedMinutesId}>
                    <SelectTrigger data-testid="link-minutes-select">
                      <SelectValue placeholder="Choose a minutes document" />
                    </SelectTrigger>
                    <SelectContent>
                      {minutesList.map(m => (
                        <SelectItem key={m.minutes_id} value={m.minutes_id}>
                          {m.meeting_date ? format(parseISO(m.meeting_date), 'MMM d, yyyy') : 'No date'} — {m.minutes_type || 'Minutes'}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>

              <Button className="w-full btn-primary" onClick={handleLinkMinutes} disabled={linking || !selectedMinutesId} data-testid="link-minutes-submit-btn">
                {linking ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Linking...</> : <><Link2 className="w-4 h-4 mr-2" /> Link Minutes</>}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ==================== EDIT TRANSACTION DIALOG ==================== */}
      <Dialog open={showEdit} onOpenChange={v => { setShowEdit(v); if (!v) setEditingTxn(null); }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Transaction</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <Label className="label-trust">Entity *</Label>
              <Select value={editForm.entity_id} onValueChange={v => setEditForm(f => ({ ...f, entity_id: v }))}>
                <SelectTrigger data-testid="edit-entity-select"><SelectValue placeholder="Select entity" /></SelectTrigger>
                <SelectContent>
                  {entities.map(e => <SelectItem key={e.entity_id} value={e.entity_id}>{e.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="label-trust">Date *</Label>
                <Popover open={editDatePickerOpen} onOpenChange={setEditDatePickerOpen}>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="w-full justify-start font-normal" data-testid="edit-date-btn">
                      <CalendarIcon className="w-4 h-4 mr-2" />
                      {editForm.date ? format(parseISO(editForm.date), 'MMM d, yyyy') : 'Pick date'}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar mode="single" selected={editForm.date ? parseISO(editForm.date) : undefined}
                      onSelect={d => { if (d) { setEditForm(f => ({ ...f, date: format(d, 'yyyy-MM-dd') })); setEditDatePickerOpen(false); } }} />
                  </PopoverContent>
                </Popover>
              </div>
              <div>
                <Label className="label-trust">Amount *</Label>
                <Input type="number" step="0.01" min="0" placeholder="0.00" className="input-trust"
                  value={editForm.amount} onChange={e => setEditForm(f => ({ ...f, amount: e.target.value }))}
                  data-testid="edit-amount-input" />
              </div>
            </div>

            <div>
              <Label className="label-trust">Direction *</Label>
              <Select value={editForm.direction} onValueChange={v => setEditForm(f => ({ ...f, direction: v }))}>
                <SelectTrigger data-testid="edit-direction-select"><SelectValue /></SelectTrigger>
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
                <Label className="label-trust">Source Account</Label>
                <Input placeholder="e.g. Trust Checking" className="input-trust" value={editForm.source_account}
                  onChange={e => setEditForm(f => ({ ...f, source_account: e.target.value }))}
                  data-testid="edit-source-input" />
              </div>
              <div>
                <Label className="label-trust">Destination Account</Label>
                <Input placeholder="e.g. Personal Account" className="input-trust" value={editForm.destination_account}
                  onChange={e => setEditForm(f => ({ ...f, destination_account: e.target.value }))}
                  data-testid="edit-dest-input" />
              </div>
            </div>

            <div>
              <Label className="label-trust">Governance Classification *</Label>
              <Select value={editForm.governance_classification}
                onValueChange={v => setEditForm(f => ({ ...f, governance_classification: v }))}>
                <SelectTrigger data-testid="edit-classification-select"><SelectValue placeholder="Select classification" /></SelectTrigger>
                <SelectContent>
                  {CLASSIFICATIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            {editForm.governance_classification === 'Other' && (
              <div>
                <Label className="label-trust">Note (required for "Other") *</Label>
                <Input className="input-trust" value={editForm.other_note} onChange={e => setEditForm(f => ({ ...f, other_note: e.target.value }))}
                  placeholder="Explain the nature of this transaction" data-testid="edit-other-note" />
              </div>
            )}

            <div>
              <Label className="label-trust">Purpose / Memo</Label>
              <Textarea className="input-trust" placeholder="Describe the purpose of this transaction"
                value={editForm.purpose_memo} onChange={e => setEditForm(f => ({ ...f, purpose_memo: e.target.value }))}
                rows={2} data-testid="edit-memo-input" />
            </div>

            <Button className="w-full btn-primary" onClick={handleEditSave} disabled={savingEdit} data-testid="edit-submit-btn">
              {savingEdit ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving...</> : 'Save Changes'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
