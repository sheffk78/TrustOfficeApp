import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import {
  TrendingUp, Plus, Wallet, Building2, Landmark,
  ArrowUpRight, Coins, Home, Activity, ChevronRight,
  Trash2
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
  const { selectedTrust } = useAuth();
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

  useEffect(() => {
    if (selectedTrust) {
      loadData();
    }
  }, [selectedTrust]);

  const loadData = async () => {
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
      toast.error(e.message);
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
      toast.error(e.message);
    }
  };

  const deleteInvestment = async (id) => {
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
      toast.error('Failed to remove');
    }
  };

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <div className="md:pl-64 pb-20 md:pb-0">
          <div className="pt-16 md:pt-8 ml-4 mr-4">
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded-lg">
              <Wallet className="w-12 h-12 text-slate-400 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-neutral-600">Choose a trust to manage investments.</p>
            </div>
          </div>
        </div>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-subtle-bg">
      <Sidebar />
      <div className="md:pl-64 pb-20 md:pb-0">
        <div className="pt-16 md:pt-8 ml-4 mr-4">

          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6 gap-4">
            <div>
              <h1 className="text-2xl font-bold text-navy flex items-center gap-2">
                <TrendingUp className="w-6 h-6 text-navy"/>
                Investment Holdings
              </h1>
              <p className="text-sm text-neutral-600 mt-1">Durable wealth tracking for <span className="font-semibold">{selectedTrust.name}</span></p>
            </div>
            <Button onClick={() => setShowAdd(!showAdd)}>
              <Plus className="w-4 h-4 mr-2"/>
              Add Investment
            </Button>
          </div>

          {/* Summary Cards */}
          {summary && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
              <Card><CardContent className="p-4">
                <div className="text-2xl font-bold text-navy">
                  ${(summary.total_current_value || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}
                </div>
                <div className="text-xs text-neutral-600">Current Value</div>
              </CardContent></Card>
              <Card><CardContent className="p-4">
                <div className="text-2xl font-bold text-navy">
                  ${(summary.total_cost_basis || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}
                </div>
                <div className="text-xs text-neutral-600">Cost Basis</div>
              </CardContent></Card>
              <Card><CardContent className="p-4">
                <div className={`text-2xl font-bold ${(summary.total_return || 0) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                  {summary.total_return >= 0 ? '+' : ''}${(summary.total_return || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}
                </div>
                <div className="text-xs text-neutral-600">Total Return</div>
              </CardContent></Card>
              <Card><CardContent className="p-4">
                <div className={`text-2xl font-bold ${(summary.total_return_pct || 0) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                  {summary.total_return_pct >= 0 ? '+' : ''}{summary.total_return_pct || 0}%
                </div>
                <div className="text-xs text-neutral-600">Return %</div>
              </CardContent></Card>
            </div>
          )}

          {/* Asset Allocation */}
          {summary?.by_type && summary.by_type.length > 0 && (
            <Card className="mb-6 border border-neutral-200">
              <CardHeader><CardTitle className="font-serif text-lg text-navy">Asset Allocation</CardTitle></CardHeader>
              <CardContent className="p-6 pt-0">
                <div className="space-y-3">
                  {summary.by_type.map((t) => (
                    <div key={t.asset_type}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-neutral-600 capitalize">{ASSET_TYPE_LABELS[t.asset_type] || t.asset_type}</span>
                        <span className="text-sm font-semibold text-navy">{t.pct}%</span>
                      </div>
                      <div className="w-full h-2 bg-neutral-100 rounded">
                        <div className="h-full bg-navy rounded" style={{ width: `${t.pct}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Add Form */}
          {showAdd && (
            <Card className="mb-6 border border-neutral-200">
              <CardContent className="p-4">
                <h3 className="font-semibold text-navy mb-3">Record New Investment</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                  <Input placeholder="Asset name (e.g. Apple, S&P 500 ETF)" value={form.asset_name} onChange={e => setForm({ ...form, asset_name: e.target.value })} />
                  <select value={form.asset_type} onChange={e => setForm({ ...form, asset_type: e.target.value })} className="border border-neutral-300 rounded-md px-3 py-2 text-sm">
                    {Object.entries(ASSET_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <Input type="number" placeholder="Cost basis ($)" value={form.cost_basis} onChange={e => setForm({ ...form, cost_basis: e.target.value })} />
                  <Input type="number" placeholder="Current value ($)" value={form.current_value} onChange={e => setForm({ ...form, current_value: e.target.value })} />
                  <Input placeholder="Quantity" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} />
                  <select value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })} className="border border-neutral-300 rounded-md px-3 py-2 text-sm">
                    <option value="shares">Shares</option>
                    <option value="units">Units</option>
                    <option value="coins">Coins</option>
                    <option value="sqft">Sq Ft</option>
                  </select>
                </div>
                <Input placeholder="Custodian (e.g. Fidelity, Schwab, Coinbase)" value={form.custodian} onChange={e => setForm({ ...form, custodian: e.target.value })} className="mb-3" />
                <textarea placeholder="Notes..." value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm mb-3" rows={3} />
                <div className="flex gap-2">
                  <Button onClick={createInvestment}>Record Investment</Button>
                  <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Investments Table */}
          {loading ? (
            <div className="space-y-3">
              {[1,2].map(i => <div key={i} className="h-16 bg-white border border-neutral-200 rounded-lg animate-pulse"/>)}
            </div>
          ) : investments.length === 0 ? (
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded-lg">
              <TrendingUp className="w-12 h-12 text-slate-300 mb-3"/>
              <h2 className="text-lg font-semibold text-navy mb-1">No investments recorded</h2>
              <p className="text-sm text-neutral-600 mb-4">Track holdings, cost basis, and performance for this trust.</p>
              <Button onClick={() => setShowAdd(true)}>Record First Investment</Button>
            </div>
          ) : (
            <div className="space-y-3">
              {investments.map((inv) => {
                const ret = inv.current_value - inv.cost_basis;
                const retPct = inv.cost_basis > 0 ? (ret / inv.cost_basis * 100).toFixed(1) : 0;
                const Icon = ASSET_TYPE_ICONS[inv.asset_type] || Activity;
                return (
                  <div key={inv.investment_id} className="bg-white border border-neutral-200 rounded-lg p-4 flex items-start gap-4 hover:shadow-sm transition-shadow">
                    <div className="w-10 h-10 bg-navy/5 flex items-center justify-center rounded flex-shrink-0">
                      <Icon className="w-5 h-5 text-navy" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <h3 className="font-semibold text-navy text-sm">{inv.asset_name}</h3>
                        <Badge variant="outline" className="text-[10px]">{ASSET_TYPE_LABELS[inv.asset_type] || inv.asset_type}</Badge>
                      </div>
                      <p className="text-xs text-neutral-600">
                        {inv.quantity.toLocaleString()} {inv.unit} · ${inv.current_value.toLocaleString()} current
                        {inv.custodian && ` · ${inv.custodian}`}
                      </p>
                      {inv.notes && <p className="text-xs text-neutral-500 mt-1 italic">{inv.notes}</p>}
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className={`text-sm font-semibold ${ret >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                        {ret >= 0 ? '+' : ''}${ret.toLocaleString('en-US', {maximumFractionDigits: 0})}
                      </p>
                      <p className={`text-xs ${ret >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>{retPct}%</p>
                    </div>
                    {/* <Button size="sm" variant="ghost" onClick={() => deleteInvestment(inv.investment_id)}>
                      <Trash2 className="w-4 h-4 text-neutral-400 hover:text-red-500" />
                    </Button> */}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}
