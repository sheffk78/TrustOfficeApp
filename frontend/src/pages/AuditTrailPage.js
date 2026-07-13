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
  Users,
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
  beneficiary_created: Users,
  schedule_a_created: DollarSign,
  communication_logged: FileText,
  alert_created: AlertTriangle,
  alert_resolved: Shield,
  transaction_created: DollarSign,
  transaction_updated: DollarSign,
  trust_updated: Shield,
  user_action: User,
};

const EVENT_COLORS = {
  minutes_created: 'bg-navy/5 text-navy border-navy/20',
  minutes_updated: 'bg-navy/5 text-navy border-navy/20',
  distribution_created: 'bg-success/5 text-success border-success/20',
  distribution_updated: 'bg-success/5 text-success border-success/20',
  compensation_created: 'bg-success/5 text-success border-success/20',
  entity_created: 'bg-navy/5 text-navy border-navy/20',
  entity_updated: 'bg-navy/5 text-navy border-navy/20',
  relationship_created: 'bg-navy/5 text-navy border-navy/20',
  beneficiary_created: 'bg-success/5 text-success border-success/20',
  schedule_a_created: 'bg-warning/5 text-warning border-warning/20',
  communication_logged: 'bg-navy/5 text-navy border-navy/20',
  alert_created: 'bg-warning/5 text-warning border-warning/20',
  alert_resolved: 'bg-success/5 text-success border-success/20',
  transaction_created: 'bg-navy/5 text-navy border-navy/20',
  transaction_updated: 'bg-navy/5 text-navy border-navy/20',
  trust_updated: 'bg-navy/5 text-navy border-navy/20',
  user_action: 'bg-subtle-bg text-foreground border-border',
};

const DEFAULT_COLOR = 'bg-subtle-bg text-foreground border-border';

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
        const relsRes = await fetchWithAuth(`/entity-relationships?trust_id=${trustId}`);
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

      // Fetch beneficiaries
      try {
        const benRes = await fetchWithAuth(`/beneficiaries?trust_id=${trustId}`);
        if (benRes.ok) {
          const data = await benRes.json();
          const beneficiaries = data.beneficiaries || data || [];
          (Array.isArray(beneficiaries) ? beneficiaries : []).forEach(b => {
            allEvents.push({
              id: `ben-${b.beneficiary_id || b.id}`,
              type: 'beneficiary_created',
              title: `Beneficiary Added: ${b.name || 'Unknown'}`,
              description: b.relationship || 'Beneficiary added to trust',
              date: b.created_at || b.date_added,
              source: 'beneficiaries',
            });
          });
        }
      } catch (e) { /* skip */ }

      // Fetch Schedule A items
      try {
        const schedRes = await fetchWithAuth(`/schedule-a?trust_id=${trustId}&status=all`);
        if (schedRes.ok) {
          const data = await schedRes.json();
          const scheduleItems = data.items || data || [];
          (Array.isArray(scheduleItems) ? scheduleItems : []).forEach(s => {
            allEvents.push({
              id: `sched-${s.item_id || s.id}`,
              type: 'schedule_a_created',
              title: `Asset Added: ${s.description || 'Unknown'}`,
              description: `${s.category || 'Asset'}${s.approximate_value ? ` — $${s.approximate_value.toLocaleString()}` : ''}`,
              date: s.created_at || s.date_conveyed,
              source: 'schedule_a',
            });
          });
        }
      } catch (e) { /* skip */ }

      // Fetch communications
      try {
        const commRes = await fetchWithAuth(`/trusts/${trustId}/communications?limit=100`);
        if (commRes.ok) {
          const data = await commRes.json();
          const comms = data.communications || [];
          comms.forEach(c => {
            allEvents.push({
              id: `comm-${c.comm_id}`,
              type: 'communication_logged',
              title: `Communication: ${c.subject || c.comm_type_label || 'Logged'}`,
              description: c.content ? c.content.substring(0, 100) : '',
              date: c.created_at,
              source: 'communications',
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

      // Fetch compensation plans and payments in parallel
      try {
        const [plansRes, paymentsRes] = await Promise.all([
          fetchWithAuth(`/compensation-plans?trust_id=${trustId}`),
          fetchWithAuth(`/compensation-payments?trust_id=${trustId}`),
        ]);

        if (plansRes.ok) {
          const data = await plansRes.json();
          const plans = data.compensation_plans || data || [];
          (Array.isArray(plans) ? plans : []).forEach(c => {
            allEvents.push({
              id: `plan-${c.plan_id || c.id}`,
              type: 'compensation_created',
              title: `Compensation Plan: $${c.amount?.toLocaleString() || 'N/A'}`,
              description: `Compensation plan for ${c.recipient_name || c.trustee_name || 'trustee'}`,
              date: c.created_at || c.effective_date,
              source: 'compensation',
            });
          });
        }

        if (paymentsRes.ok) {
          const data = await paymentsRes.json();
          const payments = data.compensation_payments || data || [];
          (Array.isArray(payments) ? payments : []).forEach(c => {
            allEvents.push({
              id: `payment-${c.payment_id || c.id}`,
              type: 'compensation_created',
              title: `Compensation Payment: $${c.amount?.toLocaleString() || 'N/A'}`,
              description: `Compensation payment for ${c.recipient_name || c.trustee_name || 'trustee'}`,
              date: c.created_at || c.payment_date,
              source: 'compensation',
            });
          });
        }
      } catch (e) { /* skip if endpoint fails */ }

      // Fetch investments
      try {
        const investRes = await fetchWithAuth(`/trusts/${trustId}/investments`);
        if (investRes.ok) {
          const data = await investRes.json();
          const investments = data.investments || data || [];
          (Array.isArray(investments) ? investments : []).forEach(inv => {
            allEvents.push({
              id: `inv-${inv.investment_id || inv.id}`,
              type: 'investment_created',
              title: `Investment: $${inv.amount?.toLocaleString() || 'N/A'}`,
              description: inv.description || inv.asset_name || 'Investment created',
              date: inv.created_at || inv.date,
              source: 'investments',
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
    { value: 'beneficiary', label: 'Beneficiaries' },
    { value: 'schedule_a', label: 'Schedule A' },
    { value: 'communication', label: 'Communications' },
    { value: 'alert', label: 'Alerts' },
    { value: 'transaction', label: 'Transactions' },
    { value: 'investment', label: 'Investments' },
    { value: 'vault', label: 'Vault' },
  ];

  const getEventColor = (type) => EVENT_COLORS[type] || DEFAULT_COLOR;
  const getEventIcon = (type) => EVENT_ICONS[type] || Clock;

  if (loading) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content mobile-layout-offset">
          <div className="page-container flex items-center justify-center py-20">
            <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content mobile-layout-offset">
          <div className="page-container">
            <div className="card-trust p-12 flex flex-col items-center justify-center">
              <FileText className="w-12 h-12 text-muted-foreground/60 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to view the audit trail.</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content mobile-layout-offset">
        <div className="page-container max-w-4xl mx-auto space-y-6">
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
              { label: 'Minutes', value: events.filter(e => e.type.includes('minutes')).length, color: 'text-navy' },
              { label: 'Financial', value: events.filter(e => e.type.includes('distribution') || e.type.includes('compensation') || e.type.includes('transaction')).length, color: 'text-success' },
              { label: 'Alerts', value: events.filter(e => e.type.includes('alert')).length, color: 'text-warning' },
              { label: 'Security', value: events.filter(e => ['login', 'login_failed', 'password_reset', 'trust_updated', 'vault_upload', 'vault_download', 'vault_delete'].includes(e.type)).length, color: 'text-navy' },
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
                    : 'card-trust text-muted-foreground border-border hover:border-navy/30'
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