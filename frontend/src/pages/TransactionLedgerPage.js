import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { fetchWithAuth } from '@/utils/api';
import { SeparationAlertsPanel } from '@/components/SeparationAlertsPanel';
import PageHelpButton from '@/components/PageHelpButton';
import {
  Plus, Search, Tag, Filter, X, Upload,
  ArrowUpDown,
} from 'lucide-react';

import { CLASSIFICATIONS, EMPTY_FORM } from './transaction-ledger/constants';
import {
  filterTransactions,
  computeFlowTotals,
  parseCsvText,
  autoDetectCsvMapping,
  buildImportRows,
  buildThresholdAlertByTxn,
} from './transaction-ledger/helpers';
import TransactionTable from './transaction-ledger/TransactionTable';
import TransactionDialog from './transaction-ledger/TransactionDialog';
import CsvImportDialog from './transaction-ledger/CsvImportDialog';
import BulkClassifyDialog from './transaction-ledger/BulkClassifyDialog';
import LinkMinutesDialog from './transaction-ledger/LinkMinutesDialog';

export default function TransactionLedgerPage() {
  const navigate = useNavigate();
  const { selectedTrust, isReadOnly } = useAuth();
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
  const [form, setForm] = useState(EMPTY_FORM);

  // CSV import
  const [showImport, setShowImport] = useState(false);
  const [csvData, setCsvData] = useState([]);
  const [csvHeaders, setCsvHeaders] = useState([]);
  const [csvMapping, setCsvMapping] = useState({ date: '', amount: '', description: '' });
  const [importEntity, setImportEntity] = useState('');
  const [importStep, setImportStep] = useState(1); // 1=upload, 2=map
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
  const [linkMinutesTxn, setLinkMinutesTxn] = useState(null);
  const [selectedMinutesId, setSelectedMinutesId] = useState('');
  const [linking, setLinking] = useState(false);

  // Edit transaction
  const [showEdit, setShowEdit] = useState(false);
  const [editingTxn, setEditingTxn] = useState(null);
  const [editForm, setEditForm] = useState(EMPTY_FORM);
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
        setThresholdAlerts(allAlerts.filter((a) => a.alert_type === 'spending_threshold_exceeded' && a.status === 'active'));
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
      setForm((f) => ({ ...f, entity_id: entities[0].entity_id }));
    }
  }, [entities]);

  // Derived: filtered transactions + totals
  const filtered = filterTransactions(transactions, {
    entity: filterEntity,
    classification: filterClassification,
    direction: filterDirection,
    search,
  });
  const { totalInflows, totalOutflows, netFlow } = computeFlowTotals(filtered);
  const thresholdAlertByTxn = buildThresholdAlertByTxn(thresholdAlerts);

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
          other_note: form.other_note,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
      toast.success('Transaction recorded');
      setShowCreate(false);
      setForm({ ...EMPTY_FORM, entity_id: entities[0]?.entity_id || '' });
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
    if (isReadOnly) {
      showUpgradeModal('delete transactions', 'button_click', 'transaction_ledger_page');
      return;
    }
    if (!window.confirm('Delete this transaction? The audit trail will be preserved.')) return;
    try {
      const res = await fetchWithAuth(`/transactions/${id}`, { method: 'DELETE' });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        showError(toast, errBody || { detail: 'Failed to delete transaction' }, { operation: 'delete', page: 'TransactionLedger' });
        return;
      }
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
      const parsed = parseCsvText(evt.target.result);
      if (!parsed) { toast.error('CSV must have a header row and at least one data row'); return; }
      setCsvHeaders(parsed.headers);
      setCsvData(parsed.rows);
      setCsvMapping(autoDetectCsvMapping(parsed.headers));
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
      const rows = buildImportRows(csvData, csvMapping);
      const res = await fetchWithAuth('/transactions/import', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          entity_id: importEntity,
          rows,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Import failed');
      const imported = await res.json();
      toast.success(`${imported.length} transactions imported — classify them now`);
      setShowImport(false);
      setCsvData([]);
      setImportStep(1);
      loadData();
    } catch (e) {
      showError(toast, e, { operation: 'import_csv', page: 'TransactionLedger', silent: true });
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
          other_note: bulkOtherNote,
        }),
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
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filtered.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(filtered.map((t) => t.transaction_id)));
  };

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
      loadData();
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
              <p className={`text-xl font-semibold ${netFlow >= 0 ? 'text-success' : 'text-error'}`} data-testid="net-flow">
                ${netFlow.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
            </div>
          </div>

          {/* Separation Alerts Panel */}
          <div className="mb-6 border border-border bg-card p-4">
            <SeparationAlertsPanel
              onLinkMinutes={(alert) => {
                const txn = transactions.find((t) => t.transaction_id === alert.transaction_id);
                if (txn) openLinkMinutes(txn);
              }}
            />
          </div>

          {/* Filters & Search */}
          <div className="flex flex-col md:flex-row gap-3 mb-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input placeholder="Search memo, accounts..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" data-testid="search-input" />
            </div>
            <Select value={filterEntity} onValueChange={setFilterEntity}>
              <SelectTrigger className="w-full md:w-[180px]" data-testid="filter-entity">
                <Filter className="w-4 h-4 mr-2" /><SelectValue placeholder="Entity" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Entities</SelectItem>
                {entities.map((e) => <SelectItem key={e.entity_id} value={e.entity_id}>{e.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={filterClassification} onValueChange={setFilterClassification}>
              <SelectTrigger className="w-full md:w-[180px]" data-testid="filter-classification">
                <Tag className="w-4 h-4 mr-2" /><SelectValue placeholder="Classification" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                {CLASSIFICATIONS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
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
          <TransactionTable
            loading={loading}
            entities={entities}
            filtered={filtered}
            total={transactions.length}
            selectedIds={selectedIds}
            thresholdAlertByTxn={thresholdAlertByTxn}
            onToggleSelect={toggleSelect}
            onToggleSelectAll={toggleSelectAll}
            onEdit={openEdit}
            onDelete={handleDelete}
            onLinkMinutes={openLinkMinutes}
            onNavigateToEntities={() => navigate('/structures')}
          />

          <p className="text-xs text-muted-foreground mt-3">
            Showing {filtered.length} of {transactions.length} transactions
          </p>
        </div>
      </main>
      <MobileBottomNav />

      {/* ==================== CREATE DIALOG ==================== */}
      <TransactionDialog
        open={showCreate}
        onOpenChange={setShowCreate}
        mode="create"
        form={form}
        onFormChange={(partial) => setForm((f) => ({ ...f, ...partial }))}
        entities={entities}
        submitting={creating}
        onSubmit={handleCreate}
      />

      {/* ==================== EDIT TRANSACTION DIALOG ==================== */}
      <TransactionDialog
        open={showEdit}
        onOpenChange={(v) => { setShowEdit(v); if (!v) setEditingTxn(null); }}
        mode="edit"
        form={editForm}
        onFormChange={(partial) => setEditForm((f) => ({ ...f, ...partial }))}
        entities={entities}
        submitting={savingEdit}
        onSubmit={handleEditSave}
      />

      {/* ==================== CSV IMPORT DIALOG ==================== */}
      <CsvImportDialog
        open={showImport}
        onOpenChange={(v) => { setShowImport(v); if (!v) { setImportStep(1); setCsvData([]); } }}
        step={importStep}
        entities={entities}
        importEntity={importEntity}
        onImportEntityChange={setImportEntity}
        csvData={csvData}
        csvHeaders={csvHeaders}
        csvMapping={csvMapping}
        onCsvMappingChange={(partial) => setCsvMapping((m) => ({ ...m, ...partial }))}
        importing={importing}
        fileInputRef={fileInputRef}
        onFileUpload={handleFileUpload}
        onImport={handleImport}
        onBack={() => { setImportStep(1); setCsvData([]); }}
      />

      {/* ==================== BULK CLASSIFY DIALOG ==================== */}
      <BulkClassifyDialog
        open={showBulkClassify}
        onOpenChange={setShowBulkClassify}
        selectedCount={selectedIds.size}
        classification={bulkClassification}
        onClassificationChange={setBulkClassification}
        otherNote={bulkOtherNote}
        onOtherNoteChange={setBulkOtherNote}
        memo={bulkMemo}
        onMemoChange={setBulkMemo}
        onSubmit={handleBulkClassify}
      />

      {/* ==================== LINK MINUTES DIALOG ==================== */}
      <LinkMinutesDialog
        open={!!linkMinutesTxn}
        onOpenChange={(v) => { if (!v) { setLinkMinutesTxn(null); setSelectedMinutesId(''); } }}
        transaction={linkMinutesTxn}
        minutesList={minutesList}
        selectedMinutesId={selectedMinutesId}
        onSelectedMinutesChange={setSelectedMinutesId}
        linking={linking}
        onSubmit={handleLinkMinutes}
      />
    </div>
  );
}