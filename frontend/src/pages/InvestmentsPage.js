import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import PageHelpButton from '@/components/PageHelpButton';
import {
  TrendingUp, Plus, Wallet, Building2, Landmark,
  ArrowUpRight, Coins, Home, Activity, ChevronRight,
  Trash2, Pencil, Loader2
} from 'lucide-react';

const ASSET_TYPE_ICONS = {
  stock: TrendingUp,
  bond: Landmark,
  reit: Building2,
  crypto: Coins,
  real_estate: Home,
  other: Activity,
};

const ASSET_TYPE_LABELS = {
  stock: 'Stock / Equity',
  bond: 'Bond / Fixed Income',
  reit: 'REIT',
  crypto: 'Cryptocurrency',
  real_estate: 'Real Estate',
  other: 'Other',
};

export default function InvestmentsPage() {
  const { selectedTrust, isReadOnly } = useAuth();
  const { showUpgradeModal } = useUpgradeModal();
  const [investments, setInvestments] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    asset_name: '',
    asset_type: 'stock',
    cost_basis: '',
    current_value: '',
    quantity: '1',
    unit: 'shares',
    custodian: '',
    notes: '',
  });

  // Edit investment state
  const [showEdit, setShowEdit] = useState(false);
  const [editingInv, setEditingInv] = useState(null);
  const [editForm, setEditForm] = useState({
    asset_name: '',
    asset_type: 'stock',
    current_value: '',
    quantity: '1',
    unit: 'shares',
    custodian: '',
    notes: '',
    is_active: true,
  });
  const [savingEdit, setSavingEdit] = useState(false);

  useEffect(() => {
    if (selectedTrust) {
      loadData();
    }
  }, [selectedTrust]);

  const loadData = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const [invRes, sumRes] = await Promise.all([
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/investments`),
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/investments/summary`),
      ]);
      const invData = await invRes.json();
      if (invRes.ok) {
        setInvestments(invData.investments || []);
        setSummary({
          total_cost_basis: invData.total_cost_basis,
          total_current_value: invData.total_current_value,
          total_return: invData.total_return,
          total_return_pct: invData.total_return_pct,
        });
      }
      const sumData = await sumRes.json();
      if (sumRes.ok) {
        setSummary(prev => ({ ...prev, by_type: sumData.by_type }));
      }
    } catch (e) {
      showError(toast, e, { operation: 'load_investments', page: 'Investments' });
    } finally {
      setLoading(false);
    }
  };

  const createInvestment = async () => {
    try {
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/investments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          cost_basis: parseFloat(form.cost_basis) || 0,
          current_value: parseFloat(form.current_value) || 0,
          quantity: parseFloat(form.quantity) || 1,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create');
      toast.success('Investment recorded');
      setShowAdd(false);
      setForm({ asset_name: '', asset_type: 'stock', cost_basis: '', current_value: '', quantity: '1', unit: 'shares', custodian: '', notes: '' });
      loadData();
    } catch (e) {
      showError(toast, e, { operation: 'create_investment', page: 'Investments' });
    }
  };

  const deleteInvestment = async (id) => {
    if (!window.confirm('Remove this investment from the trust? This can be reversed later if needed.')) return;
    try {
      const res = await fetchWithAuth(`/investments/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: false }),
      });
      if (res.ok) {
        toast.success('Investment removed');
        loadData();
      }
    } catch (e) {
      showError(toast, e, { operation: 'remove', page: 'Investments' });
    }
  };

  // ==================== EDIT INVESTMENT ====================
  const openEdit = (inv) => {
    if (isReadOnly) {
      showUpgradeModal('edit investments', 'button_click', 'investments_page');
      return;
    }
    setEditingInv(inv);
    setEditForm({
      asset_name: inv.asset_name || '',
      asset_type: inv.asset_type || 'stock',
      current_value: String(inv.current_value ?? ''),
      quantity: String(inv.quantity ?? '1'),
      unit: inv.unit || 'shares',
      custodian: inv.custodian || '',
      notes: inv.notes || '',
      is_active: inv.is_active !== false,
    });
    setShowEdit(true);
  };

  const handleEditSave = async () => {
    if (!editingInv) return;
    if (!editForm.asset_name.trim()) {
      toast.error('Asset name is required');
      return;
    }
    setSavingEdit(true);
    try {
      const res = await fetchWithAuth(`/investments/${editingInv.investment_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          asset_name: editForm.asset_name,
          asset_type: editForm.asset_type,
          current_value: parseFloat(editForm.current_value) || 0,
          quantity: parseFloat(editForm.quantity) || 1,
          unit: editForm.unit,
          custodian: editForm.custodian,
          notes: editForm.notes,
          is_active: editForm.is_active,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Failed to update investment');
      toast.success('Investment updated');
      setShowEdit(false);
      setEditingInv(null);
      loadData();
    } catch (e) {
      if (e.message?.includes('subscription') || e.message?.includes('402')) showUpgradeModal();
      showError(toast, e, { operation: 'update_investment', page: 'Investments' });
    } finally {
      setSavingEdit(false);
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <div className="main-content dot-grid">
          <div className="page-container">
            <div className="card-trust p-12 flex flex-col items-center justify-center">
              <Wallet className="w-12 h-12 text-navy/30 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to manage investments.</p>
            </div>
          </div>
        </div>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="main-layout">
      <Sidebar />
      <div className="main-content dot-grid">
        <div className="page-container">

          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Investment Holdings</h1>
              <p className="page-subtitle">Manage trust investments, track performance, and document investment decisions for fiduciary compliance</p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Manage trust investments and track portfolio performance' },
                  { text: 'Document investment decisions for fiduciary compliance' },
                  { text: 'View holdings, returns, and allocation at a glance' },
                ]}
                taPrompt="Help me understand the Investment Holdings page and how to add an investment"
              />
              <Button onClick={() => setShowAdd(!showAdd)} className="btn-primary">
                <Plus className="w-4 h-4 mr-2"/>
                Add Investment
              </Button>
            </div>
          </div>

          {/* Summary Cards */}
          {summary && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
              <Card className="card-trust"><CardContent className="p-4">
                <div className="text-2xl font-bold text-navy">
                  ${(summary.total_current_value || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}
                </div>
                <div className="text-xs text-muted-foreground">Current Value</div>
              </CardContent></Card>
              <Card className="card-trust"><CardContent className="p-4">
                <div className="text-2xl font-bold text-navy">
                  ${(summary.total_cost_basis || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}
                </div>
                <div className="text-xs text-muted-foreground">Cost Basis</div>
              </CardContent></Card>
              <Card className="card-trust"><CardContent className="p-4">
                <div className={`text-2xl font-bold ${(summary.total_return || 0) >= 0 ? 'text-success' : 'text-error'}`}>
                  {summary.total_return >= 0 ? '+' : ''}${(summary.total_return || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}
                </div>
                <div className="text-xs text-muted-foreground">Total Return</div>
              </CardContent></Card>
              <Card className="card-trust"><CardContent className="p-4">
                <div className={`text-2xl font-bold ${(summary.total_return_pct || 0) >= 0 ? 'text-success' : 'text-error'}`}>
                  {summary.total_return_pct >= 0 ? '+' : ''}{summary.total_return_pct || 0}%
                </div>
                <div className="text-xs text-muted-foreground">Return %</div>
              </CardContent></Card>
            </div>
          )}

          {/* Asset Allocation */}
          {summary?.by_type && summary.by_type.length > 0 && (
            <Card className="mb-6 card-trust">
              <div className="corner-mark" />
              <CardHeader><CardTitle className="font-serif text-lg text-navy">Asset Allocation</CardTitle></CardHeader>
              <CardContent className="p-6 pt-0">
                <div className="space-y-3">
                  {summary.by_type.map((t) => (
                    <div key={t.asset_type}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-muted-foreground capitalize">{ASSET_TYPE_LABELS[t.asset_type] || t.asset_type}</span>
                        <span className="text-sm font-semibold text-navy">{t.pct}%</span>
                      </div>
                      <div className="w-full h-2 bg-navy/10">
                        <div className="h-full bg-navy" style={{ width: `${t.pct}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Add Form */}
          {showAdd && (
            <Card className="mb-6 card-trust">
              <CardContent className="p-4">
                <h3 className="font-semibold text-navy mb-3">Record New Investment</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                  <Input placeholder="Asset name (e.g. Apple, S&P 500 ETF)" value={form.asset_name} onChange={e => setForm({ ...form, asset_name: e.target.value })} />
                  <select value={form.asset_type} onChange={e => setForm({ ...form, asset_type: e.target.value })} className="input-trust">
                    {Object.entries(ASSET_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <Input type="number" placeholder="Cost basis ($)" value={form.cost_basis} onChange={e => setForm({ ...form, cost_basis: e.target.value })} />
                  <Input type="number" placeholder="Current value ($)" value={form.current_value} onChange={e => setForm({ ...form, current_value: e.target.value })} />
                  <Input placeholder="Quantity" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} />
                  <select value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })} className="input-trust">
                    <option value="shares">Shares</option>
                    <option value="units">Units</option>
                    <option value="coins">Coins</option>
                    <option value="sqft">Sq Ft</option>
                  </select>
                </div>
                <Input placeholder="Custodian (e.g. Fidelity, Schwab, Coinbase)" value={form.custodian} onChange={e => setForm({ ...form, custodian: e.target.value })} className="mb-3" />
                <textarea placeholder="Notes..." value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className="w-full input-trust mb-3" rows={3} />
                <div className="flex gap-2">
                  <Button onClick={createInvestment} className="btn-primary">Record Investment</Button>
                  <Button variant="outline" onClick={() => setShowAdd(false)} className="btn-secondary">Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Investments Table */}
          {loading ? (
            <div className="space-y-3">
              {[1,2].map(i => <div key={i} className="h-16 card-trust animate-pulse"/>)}
            </div>
          ) : investments.length === 0 ? (
            <div className="card-trust p-12 flex flex-col items-center justify-center">
              <TrendingUp className="w-12 h-12 text-navy/20 mb-3"/>
              <h2 className="text-lg font-semibold text-navy mb-1">No investments recorded</h2>
              <p className="text-sm text-muted-foreground mb-4">Track holdings, cost basis, and performance for this trust.</p>
              <Button onClick={() => setShowAdd(true)} className="btn-primary">Record First Investment</Button>
            </div>
          ) : (
            <div className="space-y-3">
              {investments.map((inv) => {
                const ret = inv.current_value - inv.cost_basis;
                const retPct = inv.cost_basis > 0 ? (ret / inv.cost_basis * 100).toFixed(1) : 0;
                const Icon = ASSET_TYPE_ICONS[inv.asset_type] || Activity;
                return (
                  <div key={inv.investment_id} className="card-trust p-4 flex items-start gap-4 hover:shadow-sm transition-shadow">
                    <div className="w-10 h-10 bg-navy/5 flex items-center justify-center rounded-full flex-shrink-0">
                      <Icon className="w-5 h-5 text-navy" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <h3 className="font-semibold text-navy text-sm">{inv.asset_name}</h3>
                        <Badge variant="outline" className="text-[10px]">{ASSET_TYPE_LABELS[inv.asset_type] || inv.asset_type}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {inv.quantity.toLocaleString()} {inv.unit} · ${inv.current_value.toLocaleString()} current
                        {inv.custodian && ` · ${inv.custodian}`}
                      </p>
                      {inv.notes && <p className="text-xs text-muted-foreground/70 mt-1 italic">{inv.notes}</p>}
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className={`text-sm font-semibold ${ret >= 0 ? 'text-success' : 'text-error'}`}>
                        {ret >= 0 ? '+' : ''}${ret.toLocaleString('en-US', {maximumFractionDigits: 0})}
                      </p>
                      <p className={`text-xs ${ret >= 0 ? 'text-success' : 'text-error'}`}>{retPct}%</p>
                    </div>
                    <div className="flex flex-col gap-1 flex-shrink-0">
                      <Button size="sm" variant="ghost" onClick={() => openEdit(inv)} data-testid={`edit-investment-${inv.investment_id}`}>
                        <Pencil className="w-4 h-4 text-muted-foreground hover:text-navy" />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => deleteInvestment(inv.investment_id)} data-testid={`delete-investment-${inv.investment_id}`}>
                        <Trash2 className="w-4 h-4 text-muted-foreground hover:text-error" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      <MobileBottomNav />

      {/* ==================== EDIT INVESTMENT DIALOG ==================== */}
      <Dialog open={showEdit} onOpenChange={v => { setShowEdit(v); if (!v) setEditingInv(null); }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Investment</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <label className="block text-sm font-medium text-navy mb-1">Asset Name *</label>
              <Input placeholder="Asset name" value={editForm.asset_name}
                onChange={e => setEditForm({ ...editForm, asset_name: e.target.value })}
                className="input-trust" data-testid="edit-inv-name" />
            </div>
            <div>
              <label className="block text-sm font-medium text-navy mb-1">Asset Type</label>
              <select value={editForm.asset_type} onChange={e => setEditForm({ ...editForm, asset_type: e.target.value })} className="input-trust w-full">
                {Object.entries(ASSET_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-navy mb-1">Current Value ($)</label>
                <Input type="number" placeholder="0.00" value={editForm.current_value}
                  onChange={e => setEditForm({ ...editForm, current_value: e.target.value })}
                  className="input-trust" data-testid="edit-inv-value" />
              </div>
              <div>
                <label className="block text-sm font-medium text-navy mb-1">Quantity</label>
                <Input placeholder="Quantity" value={editForm.quantity}
                  onChange={e => setEditForm({ ...editForm, quantity: e.target.value })}
                  className="input-trust" data-testid="edit-inv-quantity" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-navy mb-1">Unit</label>
              <select value={editForm.unit} onChange={e => setEditForm({ ...editForm, unit: e.target.value })} className="input-trust w-full">
                <option value="shares">Shares</option>
                <option value="units">Units</option>
                <option value="coins">Coins</option>
                <option value="sqft">Sq Ft</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-navy mb-1">Custodian</label>
              <Input placeholder="e.g. Fidelity, Schwab, Coinbase" value={editForm.custodian}
                onChange={e => setEditForm({ ...editForm, custodian: e.target.value })}
                className="input-trust" data-testid="edit-inv-custodian" />
            </div>
            <div>
              <label className="block text-sm font-medium text-navy mb-1">Notes</label>
              <textarea placeholder="Notes..." value={editForm.notes}
                onChange={e => setEditForm({ ...editForm, notes: e.target.value })}
                className="w-full input-trust" rows={3} data-testid="edit-inv-notes" />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox checked={editForm.is_active} onCheckedChange={v => setEditForm({ ...editForm, is_active: v })} data-testid="edit-inv-active" />
              <label className="text-sm text-muted-foreground cursor-pointer" onClick={() => setEditForm({ ...editForm, is_active: !editForm.is_active })}>Active holding</label>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowEdit(false)} className="btn-secondary flex-1">Cancel</Button>
              <Button onClick={handleEditSave} disabled={savingEdit} className="btn-primary flex-1" data-testid="edit-inv-submit">
                {savingEdit ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving...</> : 'Save Changes'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
