import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import {
  FileText,
  RefreshCw,
  Filter,
  ArrowUpDown,
  Clock,
  User,
  Shield,
  DollarSign,
  Building2,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Download,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import PageHelpButton from '@/components/PageHelpButton';
import { toast } from 'sonner';

const EVENT_ICONS = {
  minutes_created: FileText,
  minutes_updated: FileText,
  distribution_created: DollarSign,
  distribution_updated: DollarSign,
  compensation_created: DollarSign,
  entity_created: Building2,
  entity_updated: Building2,
  relationship_created: ArrowUpDown,
  alert_created: AlertTriangle,
  alert_resolved: Shield,
  transaction_created: DollarSign,
  transaction_updated: DollarSign,
  trust_updated: Shield,
  user_action: User,
};

const EVENT_COLORS = {
  minutes_created: 'bg-blue-50 text-blue-700 border-blue-200',
  minutes_updated: 'bg-blue-50 text-blue-600 border-blue-200',
  distribution_created: 'bg-success/5 text-success border-success/20',
  distribution_updated: 'bg-success/5 text-success border-success/20',
  compensation_created: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  entity_created: 'bg-purple-50 text-purple-700 border-purple-200',
  entity_updated: 'bg-purple-50 text-purple-600 border-purple-200',
  relationship_created: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  alert_created: 'bg-warning/5 text-warning border-warning/20',
  alert_resolved: 'bg-success/5 text-success border-success/20',
  transaction_created: 'bg-teal-50 text-teal-700 border-teal-200',
  transaction_updated: 'bg-teal-50 text-teal-600 border-teal-200',
  trust_updated: 'bg-navy/5 text-navy border-navy/20',
  user_action: 'bg-slate-50 text-slate-700 border-slate-200',
};

const DEFAULT_COLOR = 'bg-slate-50 text-slate-700 border-slate-200';

export default function AuditTrailPage() {
  const { selectedTrust } = useAuth();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [downloading, setDownloading] = useState(false);
  const PAGE_SIZE = 25;

  useEffect(() => {
    if (selectedTrust) loadAuditTrail();
  }, [selectedTrust, page, filter]);

  const loadAuditTrail = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      // Aggregate audit events from multiple sources
      const allEvents = [];
      const trustId = selectedTrust.trust_id;

      // Fetch minutes
      try {
        const minutesRes = await fetchWithAuth(`/minutes?trust_id=${trustId}`);
        if (minutesRes.ok) {
          const data = await minutesRes.json();
          const minutes = data.minutes || data || [];
          (Array.isArray(minutes) ? minutes : []).forEach(m => {
            allEvents.push({
              id: m.minutes_id || m.id,
              type: m.is_retroactive ? 'minutes_created' : 'minutes_updated',
              title: m.title || 'Minutes Created',
              description: m.is_retroactive ? 'Retroactive minutes' : `Meeting minutes documented`,
              date: m.created_at || m.meeting_date,
              source: 'minutes',
              is_retroactive: m.is_retroactive || false,
            });
          });
        }
      } catch (e) { /* skip if endpoint fails */ }

      // Fetch entities
      try {
        const entitiesRes = await fetchWithAuth(`/entities?trust_id=${trustId}`);
        if (entitiesRes.ok) {
          const data = await entitiesRes.json();
          const entityList = data.entities || [];
          entityList.forEach(e => {
            allEvents.push({
              id: `entity-${e.entity_id}`,
              type: 'entity_created',
              title: `${e.name} Created`,
              description: `${e.entity_type} entity added to trust structure`,
              date: e.created_at || e.formation_date,
              source: 'entities',
            });
          });
        }
      } catch (e) { /* skip */ }

      // Fetch relationships
      try {
        const relsRes = await fetchWithAuth(`/relationships?trust_id=${trustId}`);
        if (relsRes.ok) {
          const data = await relsRes.json();
          const rels = data.relationships || [];
          rels.forEach(r => {
            allEvents.push({
              id: `rel-${r.relationship_id || r.id}`,
              type: 'relationship_created',
              title: `Relationship Added`,
              description: `${r.relationship_type || 'relationship'} between entities`,
              date: r.created_at,
              source: 'relationships',
            });
          });
        }
      } catch (e) { /* skip */ }

      // Fetch distributions
      try {
        const distRes = await fetchWithAuth(`/distributions?trust_id=${trustId}`);
        if (distRes.ok) {
          const data = await distRes.json();
          const dists = data.distributions || data || [];
          (Array.isArray(dists) ? dists : []).forEach(d => {
            allEvents.push({
              id: d.distribution_id || d.id,
              type: 'distribution_created',
              title: `Distribution: $${d.amount?.toLocaleString() || 'N/A'}`,
              description: `Distribution to ${d.recipient_name || d.recipient || 'beneficiary'}`,
              date: d.created_at || d.distribution_date,
              source: 'distributions',
            });
          });
        }
      } catch (e) { /* skip */ }

      // Fetch compensation
      try {
        const compRes = await fetchWithAuth(`/compensation?trust_id=${trustId}`);
        if (compRes.ok) {
          const data = await compRes.json();
          const comps = data.compensation_records || data || [];
          (Array.isArray(comps) ? comps : []).forEach(c => {
            allEvents.push({
              id: c.compensation_id || c.id,
              type: 'compensation_created',
              title: `Compensation: $${c.amount?.toLocaleString() || 'N/A'}`,
              description: `Compensation for ${c.recipient_name || c.trustee_name || 'trustee'}`,
              date: c.created_at || c.effective_date,
              source: 'compensation',
            });
          });
        }
      } catch (e) { /* skip */ }

      // Fetch alerts
      try {
        const alertRes = await fetchWithAuth(`/alerts?trust_id=${trustId}`);
        if (alertRes.ok) {
          const data = await alertRes.json();
          const alerts = data.alerts || data || [];
          (Array.isArray(alerts) ? alerts : []).forEach(a => {
            allEvents.push({
              id: a.alert_id || a.id,
              type: a.resolved ? 'alert_resolved' : 'alert_created',
              title: a.resolved ? `Alert Resolved: ${a.alert_type || 'Alert'}` : `Alert: ${a.alert_type || 'Alert'}`,
              description: a.message || a.description || '',
              date: a.resolved_at || a.created_at,
              source: 'alerts',
            });
          });
        }
      } catch (e) { /* skip */ }

      // Fetch transactions
      try {
        const txnRes = await fetchWithAuth(`/transactions?trust_id=${trustId}`);
        if (txnRes.ok) {
          const data = await txnRes.json();
          const txns = data.transactions || data || [];
          (Array.isArray(txns) ? txns : []).forEach(t => {
            allEvents.push({
              id: t.transaction_id || t.id,
              type: 'transaction_created',
              title: `Transaction: $${t.amount?.toLocaleString() || 'N/A'}`,
              description: t.description || t.memo || '',
              date: t.created_at || t.date,
              source: 'transactions',
            });
          });
        }
      } catch (e) { /* skip */ }

      // Fetch security audit logs (logins, password changes, vault actions, trust edits)
      try {
        const auditRes = await fetchWithAuth(`/audit-logs?limit=100`);
        if (auditRes.ok) {
          const data = await auditRes.json();
          const logs = data.audit_logs || [];
          logs.forEach(a => {
            // Map audit actions to display types
            const actionLabels = {
              'login': 'Login',
              'login_failed': 'Failed Login',
              'password_reset': 'Password Reset',
              'trust_updated': 'Trust Profile Updated',
              'vault_upload': 'Document Uploaded',
              'vault_download': 'Document Downloaded',
              'vault_delete': 'Document Deleted',
            };
            const label = actionLabels[a.action] || a.action;
            allEvents.push({
              id: a.audit_id,
              type: a.action,
              title: label,
              description: a.details ? Object.entries(a.details).map(([k, v]) => `${k}: ${v}`).join(', ') : '',
              date: a.timestamp,
              source: 'audit_logs',
            });
          });
        }
      } catch (e) { /* skip */ }

      // Sort by date descending
      allEvents.sort((a, b) => {
        const dateA = a.date ? new Date(a.date) : new Date(0);
        const dateB = b.date ? new Date(b.date) : new Date(0);
        return dateB - dateA;
      });

      // Apply filter
      const filtered = filter === 'all'
        ? allEvents
        : allEvents.filter(e => e.type.startsWith(filter));

      setEvents(filtered);
      setTotalPages(Math.max(1, Math.ceil(filtered.length / PAGE_SIZE)));
    } catch (error) {
      console.error('Failed to load audit trail:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    if (!selectedTrust) return;
    setDownloading(true);
    try {
      const res = await fetchWithAuth(`/exports/audit-defense/${selectedTrust.trust_id}?days=365`);
      if (!res.ok) throw new Error('Failed to generate report');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_defense_${selectedTrust.trust_id}_${new Date().toISOString().slice(0,10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('Audit Defense Report downloaded');
    } catch (e) {
      toast.error(e.message || 'Failed to generate report');
    } finally {
      setDownloading(false);
    }
  };

  const paginatedEvents = events.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const filterOptions = [
    { value: 'all', label: 'All Events' },
    { value: 'minutes', label: 'Minutes' },
    { value: 'distribution', label: 'Distributions' },
    { value: 'compensation', label: 'Compensation' },
    { value: 'entity', label: 'Entities' },
    { value: 'relationship', label: 'Relationships' },
    { value: 'alert', label: 'Alerts' },
    { value: 'transaction', label: 'Transactions' },
    { value: 'vault', label: 'Vault' },
  ];

  const getEventColor = (type) => EVENT_COLORS[type] || DEFAULT_COLOR;
  const getEventIcon = (type) => EVENT_ICONS[type] || Clock;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!selectedTrust) {
    return (
      <div className="flex items-center justify-center min-h-screen text-muted-foreground">
        Select a trust to view the audit trail
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 p-4 md:p-8 overflow-y-auto">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Audit Trail</h1>
              <p className="page-subtitle">View a complete log of all trust administration actions — track changes, access, and decisions for compliance</p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'View a complete log of all trust administration actions' },
                  { text: 'Track changes, access, and decisions for compliance and transparency' },
                  { text: 'Filter events by type to focus on minutes, distributions, or alerts' },
                  { text: 'Export a court-ready Audit Defense PDF with the Export button' },
                ]}
                taPrompt="Walk me through the Audit Trail and what gets logged"
                contextAlerts={events.length < 5 ? [
                  { text: 'Your audit trail is sparse. Regular activity (minutes, distributions) builds a stronger compliance record.', prompt: 'What should I be doing to build a strong audit trail for my trust?' }
                ] : []}
              />
              <Button variant="outline" size="sm" onClick={loadAuditTrail}>
                <RefreshCw className="w-4 h-4 mr-1" /> Refresh
              </Button>
              <Button variant="outline" size="sm" onClick={handleExport} disabled={downloading}>
                <Download className="w-4 h-4 mr-1" /> {downloading ? 'Generating...' : 'Export'}
              </Button>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: 'Total Events', value: events.length, color: 'text-navy' },
              { label: 'Minutes', value: events.filter(e => e.type.includes('minutes')).length, color: 'text-blue-600' },
              { label: 'Financial', value: events.filter(e => e.type.includes('distribution') || e.type.includes('compensation') || e.type.includes('transaction')).length, color: 'text-success' },
              { label: 'Alerts', value: events.filter(e => e.type.includes('alert')).length, color: 'text-warning' },
              { label: 'Security', value: events.filter(e => ['login', 'login_failed', 'password_reset', 'trust_updated', 'vault_upload', 'vault_download', 'vault_delete'].includes(e.type)).length, color: 'text-purple-600' },
            ].map(stat => (
              <div key={stat.label} className="card-trust text-center">
                <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
                <p className="text-xs text-muted-foreground">{stat.label}</p>
              </div>
            ))}
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-2">
            {filterOptions.map(opt => (
              <button
                key={opt.value}
                onClick={() => { setFilter(opt.value); setPage(1); }}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
                  filter === opt.value
                    ? 'bg-navy text-white border-navy'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* Timeline */}
          {paginatedEvents.length === 0 ? (
            <div className="card-trust text-center py-12">
              <Clock className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="font-serif text-lg text-navy mb-2">No Audit Events</h3>
              <p className="text-sm text-muted-foreground">
                Actions taken on this trust will appear here as a permanent record.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {paginatedEvents.map((event, idx) => {
                const Icon = getEventIcon(event.type);
                const colorClass = getEventColor(event.type);
                const dateStr = event.date
                  ? new Date(event.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                  : 'Unknown date';
                const timeStr = event.date
                  ? new Date(event.date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
                  : '';

                return (
                  <div key={event.id || idx} className={`card-trust flex items-start gap-3 border ${colorClass}`}>
                    <div className="flex-shrink-0 mt-0.5">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-sm truncate">{event.title}</p>
                        {event.is_retroactive && (
                          <span className="text-[10px] bg-warning/10 text-warning px-1.5 py-0.5 rounded font-medium">
                            RETROACTIVE
                          </span>
                        )}
                      </div>
                      {event.description && (
                        <p className="text-xs opacity-80 mt-0.5">{event.description}</p>
                      )}
                    </div>
                    <div className="flex-shrink-0 text-right">
                      <p className="text-xs font-medium">{dateStr}</p>
                      {timeStr && <p className="text-[10px] opacity-60">{timeStr}</p>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(p => p - 1)}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}