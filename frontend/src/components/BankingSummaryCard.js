import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';
import { Landmark, Loader2, Plus, ArrowRight } from 'lucide-react';

const fmtMoney = (n) => {
  if (n == null || isNaN(n)) return '0.00';
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

/**
 * Banking summary card for the Trust Dashboard.
 * Fetches GET /api/trusts/{trust_id}/bank-accounts/summary and renders
 * account count, latest total balance, and link to add an account.
 */
export default function BankingSummaryCard() {
  const { selectedTrust } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!selectedTrust) return;
    let active = true;
    setLoading(true);
    fetchWithAuth(`/trusts/${selectedTrust.trust_id}/bank-accounts/summary`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (active) setSummary(data); })
      .catch(() => { if (active) setSummary(null); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedTrust?.trust_id]);

  if (!selectedTrust) return null;

  const accountCount = summary?.account_count ?? 0;
  const totalBalance = summary?.total_latest_balance ?? null;

  return (
    <div className="card-trust corner-mark" data-testid="banking-summary-card">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-navy/20 to-navy/10 flex items-center justify-center">
            <Landmark className="w-5 h-5 text-navy" />
          </div>
          <div>
            <p className="label-trust mb-1">Banking</p>
            <h3 className="font-serif text-lg text-navy">Accounts Overview</h3>
          </div>
        </div>
        <button
          onClick={() => navigate('/structures')}
          className="text-navy hover:text-navy/70 font-mono text-xs uppercase tracking-widest flex items-center gap-1"
          title="Manage bank accounts"
        >
          Manage <ArrowRight className="w-3 h-3" />
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
        </div>
      ) : accountCount === 0 ? (
        <div className="p-4 bg-navy/5 border border-navy/10 rounded text-center">
          <p className="text-sm text-muted-foreground mb-2">No bank accounts linked yet</p>
          <button
            onClick={() => navigate('/structures')}
            className="inline-flex items-center gap-1 text-sm text-navy hover:text-navy/70 font-medium"
          >
            <Plus className="w-4 h-4" /> Add your first account
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="font-mono text-2xl text-navy">{accountCount}</p>
            <p className="label-trust">Bank Accounts</p>
          </div>
          <div>
            <p className="font-mono text-2xl text-navy">${fmtMoney(totalBalance)}</p>
            <p className="label-trust">Latest Total Balance</p>
          </div>
        </div>
      )}
    </div>
  );
}