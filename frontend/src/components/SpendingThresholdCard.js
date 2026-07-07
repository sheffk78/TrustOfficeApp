import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';
import { Shield, AlertTriangle, ArrowRight, Loader2 } from 'lucide-react';

const fmtMoney = (n) => {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

/**
 * Spending Threshold status card for the Trust Dashboard.
 * Reads threshold from the selected trust's governance_settings and
 * fetches active alert count from /api/alerts/count?trust_id=X.
 */
export default function SpendingThresholdCard() {
  const { selectedTrust } = useAuth();
  const navigate = useNavigate();
  const [alertCount, setAlertCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const threshold = selectedTrust?.governance_settings?.spending_threshold;
  const thresholdAmount = threshold?.amount ?? null;
  const requiresMinutes = threshold?.requires_minutes ?? false;

  useEffect(() => {
    if (!selectedTrust) return;
    let active = true;
    setLoading(true);
    fetchWithAuth(`/alerts/count?trust_id=${selectedTrust.trust_id}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (active && data) {
          // Count active alerts of type spending_threshold_exceeded (if categorized)
          // Falls back to total_active if the type breakdown isn't available
          const count = data.threshold_active ?? data.spending_threshold_count ?? 0;
          setAlertCount(count);
        }
      })
      .catch(() => { if (active) setAlertCount(0); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedTrust?.trust_id]);

  if (!selectedTrust) return null;

  const hasThreshold = thresholdAmount != null && thresholdAmount > 0;

  return (
    <div className="card-trust corner-mark" data-testid="spending-threshold-card">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-navy/20 to-navy/10 flex items-center justify-center">
            <Shield className="w-5 h-5 text-navy" />
          </div>
          <div>
            <p className="label-trust mb-1">Governance</p>
            <h3 className="font-serif text-lg text-navy">Spending Threshold</h3>
          </div>
        </div>
        <button
          onClick={() => navigate('/settings#governance')}
          className="text-navy hover:text-navy/70 font-mono text-xs uppercase tracking-widest flex items-center gap-1"
          title="Configure spending threshold"
        >
          Configure <ArrowRight className="w-3 h-3" />
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
        </div>
      ) : !hasThreshold ? (
        <div className="p-4 bg-navy/5 border border-navy/10 rounded text-center">
          <p className="text-sm text-muted-foreground mb-2">No spending threshold set</p>
          <button
            onClick={() => navigate('/settings#governance')}
            className="inline-flex items-center gap-1 text-sm text-navy hover:text-navy/70 font-medium"
          >
            Set a threshold
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="font-mono text-2xl text-navy">${fmtMoney(thresholdAmount)}</p>
              <p className="label-trust">Threshold</p>
            </div>
            <div>
              <p className={`font-mono text-2xl ${alertCount > 0 ? 'text-error' : 'text-success'}`}>
                {alertCount}
              </p>
              <p className="label-trust">Active Alerts</p>
            </div>
          </div>
          {requiresMinutes && (
            <p className="text-xs text-muted-foreground">
              Requires meeting minutes for transactions above threshold.
            </p>
          )}
          {alertCount > 0 && (
            <div className="flex items-center gap-2 p-2 bg-error/5 border border-error/20 rounded">
              <AlertTriangle className="w-4 h-4 text-error flex-shrink-0" />
              <p className="text-xs text-error">
                {alertCount} transaction{alertCount !== 1 ? 's' : ''} exceeded the threshold.
              </p>
              <button
                onClick={() => navigate('/transactions')}
                className="ml-auto text-xs text-error font-medium hover:underline"
              >
                Review
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}