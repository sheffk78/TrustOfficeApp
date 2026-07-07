import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import {
  AlertTriangle, ShieldAlert, CheckCircle2, Loader2, ScanSearch,
  Filter, History, ChevronDown, FileText
} from 'lucide-react';

const severityConfig = {
  red: {
    icon: ShieldAlert,
    bg: 'bg-red-50 dark:bg-red-950/30',
    border: 'border-red-200 dark:border-red-800',
    badge: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    label: 'Immediate Risk',
    dot: 'bg-red-500'
  },
  yellow: {
    icon: AlertTriangle,
    bg: 'bg-warning/10 dark:bg-warning/20',
    border: 'border-warning/20 dark:border-warning/30',
    badge: 'bg-warning/10 text-warning dark:bg-warning/20 dark:text-warning',
    label: 'Needs Attention',
    dot: 'bg-warning'
  }
};

const RESOLUTION_TYPES = [
  { value: 'classified', label: 'Reclassified the transaction' },
  { value: 'linked', label: 'Linked to governance action' },
  { value: 'documented', label: 'Uploaded supporting documentation' },
  { value: 'reviewed_no_issue', label: 'Reviewed — No Issue' },
];

export function SeparationAlertsPanel({ entityId = null, compact = false, onLinkMinutes = null }) {
  const { selectedTrust } = useAuth();
  const [alerts, setAlerts] = useState([]);
  const [counts, setCounts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Resolve dialog
  const [resolveAlert, setResolveAlert] = useState(null);
  const [resolveType, setResolveType] = useState('');
  const [resolveNote, setResolveNote] = useState('');
  const [resolving, setResolving] = useState(false);

  const loadAlerts = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ trust_id: selectedTrust.trust_id });
      if (entityId) params.set('entity_id', entityId);

      const [alertsRes, countsRes] = await Promise.all([
        fetchWithAuth(`/alerts?${params}`),
        fetchWithAuth(`/alerts/count?trust_id=${selectedTrust.trust_id}`)
      ]);

      if (alertsRes.ok) setAlerts(await alertsRes.json());
      if (countsRes.ok) setCounts(await countsRes.json());
    } catch {
      toast.error('Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }, [selectedTrust, entityId]);

  useEffect(() => { loadAlerts(); }, [loadAlerts]);

  const handleScan = async () => {
    if (!selectedTrust) return;
    setScanning(true);
    try {
      const res = await fetchWithAuth(`/alerts/scan?trust_id=${selectedTrust.trust_id}`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Scan complete — ${data.active_alerts} active alerts`);
        loadAlerts();
      }
    } catch {
      toast.error('Scan failed');
    } finally {
      setScanning(false);
    }
  };

  const handleResolve = async () => {
    if (!resolveType || !resolveNote.trim()) {
      toast.error('Both resolution type and note are required');
      return;
    }
    setResolving(true);
    try {
      const res = await fetchWithAuth(`/alerts/${resolveAlert.alert_id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ resolution_type: resolveType, resolution_note: resolveNote })
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
      toast.success('Alert resolved');
      setResolveAlert(null);
      setResolveType('');
      setResolveNote('');
      loadAlerts();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setResolving(false);
    }
  };

  const loadHistory = async () => {
    if (!selectedTrust) return;
    setHistoryLoading(true);
    try {
      const res = await fetchWithAuth(`/alerts/history?trust_id=${selectedTrust.trust_id}`);
      if (res.ok) setHistory(await res.json());
    } catch {
      toast.error('Failed to load history');
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleGenerateMinutes = async (alertId) => {
    try {
      const res = await fetchWithAuth(`/alerts/${alertId}/generate-resolution`, { method: 'POST' });
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
      const data = await res.json();
      toast.success('Resolution minutes generated', { description: `Minutes ID: ${data.minutes_id}` });
    } catch (e) {
      toast.error(e.message);
    }
  };

  if (!selectedTrust) return null;

  const redAlerts = alerts.filter(a => a.severity === 'red');
  const yellowAlerts = alerts.filter(a => a.severity === 'yellow');

  return (
    <div data-testid="separation-alerts-panel">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className={`${compact ? 'text-base' : 'text-lg'} font-semibold text-foreground`}>
            Separation Alerts
          </h2>
          {counts && counts.total_active > 0 && (
            <div className="flex gap-1.5">
              {counts.red_count > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300" data-testid="red-alert-badge">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500" /> {counts.red_count}
                </span>
              )}
              {counts.yellow_count > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-warning/10 text-warning" data-testid="yellow-alert-badge">
                  <span className="w-1.5 h-1.5 rounded-full bg-warning" /> {counts.yellow_count}
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => { setShowHistory(true); loadHistory(); }} data-testid="alert-history-btn">
            <History className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={handleScan} disabled={scanning} data-testid="scan-alerts-btn">
            {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <ScanSearch className="w-4 h-4" />}
            <span className="ml-1.5 hidden sm:inline">Scan</span>
          </Button>
        </div>
      </div>

      {/* Alert List */}
      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-8 rounded border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/20" data-testid="no-alerts">
          <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
          <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">No Active Alerts</p>
          <p className="text-xs text-muted-foreground mt-1">All clear — no commingling risks detected</p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Red alerts first */}
          {redAlerts.map(alert => (
            <AlertCard key={alert.alert_id} alert={alert} onResolve={() => setResolveAlert(alert)} onLinkMinutes={onLinkMinutes} />
          ))}
          {/* Then yellow */}
          {yellowAlerts.map(alert => (
            <AlertCard key={alert.alert_id} alert={alert} onResolve={() => setResolveAlert(alert)} onLinkMinutes={onLinkMinutes} />
          ))}
        </div>
      )}

      {/* Resolve Dialog */}
      <Dialog open={!!resolveAlert} onOpenChange={v => { if (!v) setResolveAlert(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Resolve Alert</DialogTitle>
          </DialogHeader>
          {resolveAlert && (
            <div className="space-y-4 mt-2">
              <div className={`p-3 rounded ${severityConfig[resolveAlert.severity]?.bg} ${severityConfig[resolveAlert.severity]?.border} border`}>
                <p className="text-sm font-medium text-foreground">{resolveAlert.title}</p>
                <p className="text-xs text-muted-foreground mt-1">{resolveAlert.description}</p>
              </div>

              <div>
                <Label>How are you resolving this? *</Label>
                <Select value={resolveType} onValueChange={setResolveType}>
                  <SelectTrigger data-testid="resolve-type-select"><SelectValue placeholder="Select resolution type" /></SelectTrigger>
                  <SelectContent>
                    {RESOLUTION_TYPES.map(r => (
                      <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Resolution Note *</Label>
                <Textarea value={resolveNote} onChange={e => setResolveNote(e.target.value)}
                  placeholder="Explain why this is not a commingling risk, or what action was taken..."
                  rows={3} data-testid="resolve-note-input" />
                <p className="text-xs text-muted-foreground mt-1">This note becomes a permanent part of the audit trail.</p>
              </div>

              <Button className="w-full" onClick={handleResolve} disabled={resolving} data-testid="resolve-submit-btn">
                {resolving ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Resolving...</> : 'Resolve Alert'}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* History Dialog */}
      <Dialog open={showHistory} onOpenChange={setShowHistory}>
        <DialogContent className="max-w-xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Alert History (Audit Trail)</DialogTitle>
          </DialogHeader>
          {historyLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin" /></div>
          ) : history.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">No alert history yet</p>
          ) : (
            <div className="space-y-2 mt-2">
              {history.map(a => {
                const cfg = severityConfig[a.severity] || severityConfig.yellow;
                return (
                  <div key={a.alert_id} className={`p-3 rounded border ${a.status === 'resolved' ? 'border-border bg-muted/30 opacity-75' : `${cfg.border} ${cfg.bg}`}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${cfg.badge}`}>{a.severity.toUpperCase()}</span>
                          <span className="text-sm font-medium text-foreground truncate">{a.title}</span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{a.description}</p>
                        {a.entity_name && <p className="text-[10px] text-muted-foreground/70 mt-1">Entity: {a.entity_name}</p>}
                      </div>
                      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${a.status === 'resolved' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-orange-100 text-orange-700'}`}>
                        {a.status}
                      </span>
                    </div>
                    {a.status === 'resolved' && (
                      <div className="mt-2 pt-2 border-t border-border/50 text-xs text-muted-foreground flex items-center justify-between">
                        <span><span className="font-medium">Resolution:</span> {a.resolution_type?.replace(/_/g, ' ')} — {a.resolution_note}</span>
                        <Button variant="ghost" size="sm" className="text-[10px] h-6 px-2 ml-2 flex-shrink-0"
                          onClick={() => handleGenerateMinutes(a.alert_id)} data-testid={`gen-minutes-${a.alert_id}`}>
                          <FileText className="w-3 h-3 mr-1" /> Minutes
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AlertCard({ alert, onResolve, onLinkMinutes = null }) {
  const cfg = severityConfig[alert.severity] || severityConfig.yellow;
  const Icon = cfg.icon;
  const isThreshold = alert.alert_type === 'spending_threshold_exceeded';

  return (
    <div className={`p-3 rounded border ${cfg.border} ${cfg.bg} transition-colors`} data-testid={`alert-card-${alert.alert_id}`}>
      <div className="flex items-start gap-3">
        <Icon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${alert.severity === 'red' ? 'text-red-500' : 'text-warning'}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${cfg.badge}`}>{cfg.label}</span>
            {alert.entity_name && (
              <span className="text-[10px] text-muted-foreground">{alert.entity_name}</span>
            )}
            {isThreshold && (
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-warning/10 text-warning">
                Threshold
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-foreground">{alert.title}</p>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{alert.description}</p>
        </div>
        <div className="flex flex-col gap-1 flex-shrink-0">
          {isThreshold && onLinkMinutes && alert.transaction_id && (
            <Button size="sm" variant="outline" onClick={() => onLinkMinutes(alert)} className="text-xs" data-testid={`link-minutes-alert-${alert.alert_id}`}>
              Link Minutes
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onResolve}
            className="text-xs" data-testid={`resolve-btn-${alert.alert_id}`}>
            Resolve
          </Button>
        </div>
      </div>
    </div>
  );
}

// Compact badge for sidebar/dashboard showing alert counts
export function AlertCountBadge({ trustId }) {
  const [counts, setCounts] = useState(null);

  useEffect(() => {
    if (!trustId) return;
    fetchWithAuth(`/alerts/count?trust_id=${trustId}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setCounts(data); })
      .catch(() => {});
  }, [trustId]);

  if (!counts || counts.total_active === 0) return null;

  return (
    <span className="inline-flex items-center gap-1" data-testid="alert-count-badge">
      {counts.red_count > 0 && (
        <span className="w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
          {counts.red_count}
        </span>
      )}
      {counts.yellow_count > 0 && (
        <span className="w-5 h-5 rounded-full bg-warning text-white text-[10px] font-bold flex items-center justify-center">
          {counts.yellow_count}
        </span>
      )}
    </span>
  );
}
