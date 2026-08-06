import { useState, useEffect, useCallback } from 'react';
import { fetchWithAuth } from '@/utils/api';
import { PAGE_SIZE, AUDIT_ACTION_LABELS } from './constants';

/**
 * Generic helper: fetch a URL, parse JSON, extract an array, and map items to events.
 * Replaces the 11 nearly-identical try/fetch/parse/forEach/catch blocks.
 *
 * @param {string} url — API endpoint URL
 * @param {function} extractArray — (data) => array of items from the parsed JSON
 * @param {function} mapItem — (item) => event object
 * @returns {Promise<array>} — mapped events (empty on any failure)
 */
async function fetchSource(url, extractArray, mapItem) {
  try {
    const res = await fetchWithAuth(url);
    if (!res.ok) return [];
    const data = await res.json();
    const items = extractArray(data);
    if (!Array.isArray(items)) return [];
    return items.map(mapItem);
  } catch {
    return [];
  }
}

/** Safely coerce a possibly-non-array response field into an array. */
const toArray = (val) => (Array.isArray(val) ? val : []);

/**
 * Build the full URL for a trust-scoped endpoint.
 */
const trustUrl = (path, trustId) => `${path}?trust_id=${trustId}`;

// ── Source mappers ──────────────────────────────────────────────────────────

const minutesMapper = (m) => ({
  id: m.minutes_id || m.id,
  type: m.is_retroactive ? 'minutes_created' : 'minutes_updated',
  title: m.title || 'Minutes Created',
  description: m.is_retroactive ? 'Retroactive minutes' : 'Meeting minutes documented',
  date: m.created_at || m.meeting_date,
  source: 'minutes',
  is_retroactive: m.is_retroactive || false,
});

const entitiesMapper = (e) => ({
  id: `entity-${e.entity_id}`,
  type: 'entity_created',
  title: `${e.name} Created`,
  description: `${e.entity_type} entity added to trust structure`,
  date: e.created_at || e.formation_date,
  source: 'entities',
});

const relationshipsMapper = (r) => ({
  id: `rel-${r.relationship_id || r.id}`,
  type: 'relationship_created',
  title: 'Relationship Added',
  description: `${r.relationship_type || 'relationship'} between entities`,
  date: r.created_at,
  source: 'relationships',
});

const beneficiariesMapper = (b) => ({
  id: `ben-${b.beneficiary_id || b.id}`,
  type: 'beneficiary_created',
  title: `Beneficiary Added: ${b.name || 'Unknown'}`,
  description: b.relationship || 'Beneficiary added to trust',
  date: b.created_at || b.date_added,
  source: 'beneficiaries',
});

const scheduleAMapper = (s) => ({
  id: `sched-${s.item_id || s.id}`,
  type: 'schedule_a_created',
  title: `Asset Added: ${s.description || 'Unknown'}`,
  description: `${s.category || 'Asset'}${s.approximate_value ? ` — $${s.approximate_value.toLocaleString()}` : ''}`,
  date: s.created_at || s.date_conveyed,
  source: 'schedule_a',
});

const communicationsMapper = (c) => ({
  id: `comm-${c.comm_id}`,
  type: 'communication_logged',
  title: `Communication: ${c.subject || c.comm_type_label || 'Logged'}`,
  description: c.content ? c.content.substring(0, 100) : '',
  date: c.created_at,
  source: 'communications',
});

const distributionsMapper = (d) => ({
  id: d.distribution_id || d.id,
  type: 'distribution_created',
  title: `Distribution: $${d.amount?.toLocaleString() || 'N/A'}`,
  description: `Distribution to ${d.recipient_name || d.recipient || 'beneficiary'}`,
  date: d.created_at || d.distribution_date,
  source: 'distributions',
});

const compensationPlansMapper = (c) => ({
  id: `plan-${c.plan_id || c.id}`,
  type: 'compensation_created',
  title: `Compensation Plan: $${c.amount?.toLocaleString() || 'N/A'}`,
  description: `Compensation plan for ${c.recipient_name || c.trustee_name || 'trustee'}`,
  date: c.created_at || c.effective_date,
  source: 'compensation',
});

const compensationPaymentsMapper = (c) => ({
  id: `payment-${c.payment_id || c.id}`,
  type: 'compensation_created',
  title: `Compensation Payment: $${c.amount?.toLocaleString() || 'N/A'}`,
  description: `Compensation payment for ${c.recipient_name || c.trustee_name || 'trustee'}`,
  date: c.created_at || c.payment_date,
  source: 'compensation',
});

const investmentsMapper = (inv) => ({
  id: `inv-${inv.investment_id || inv.id}`,
  type: 'investment_created',
  title: `Investment: $${inv.amount?.toLocaleString() || 'N/A'}`,
  description: inv.description || inv.asset_name || 'Investment created',
  date: inv.created_at || inv.date,
  source: 'investments',
});

const alertsMapper = (a) => ({
  id: a.alert_id || a.id,
  type: a.resolved ? 'alert_resolved' : 'alert_created',
  title: a.resolved
    ? `Alert Resolved: ${a.alert_type || 'Alert'}`
    : `Alert: ${a.alert_type || 'Alert'}`,
  description: a.message || a.description || '',
  date: a.resolved_at || a.created_at,
  source: 'alerts',
});

const transactionsMapper = (t) => ({
  id: t.transaction_id || t.id,
  type: 'transaction_created',
  title: `Transaction: $${t.amount?.toLocaleString() || 'N/A'}`,
  description: t.description || t.memo || '',
  date: t.created_at || t.date,
  source: 'transactions',
});

const auditLogsMapper = (a) => {
  const label = AUDIT_ACTION_LABELS[a.action] || a.action;
  return {
    id: a.audit_id,
    type: a.action,
    title: label,
    description: a.details
      ? Object.entries(a.details).map(([k, v]) => `${k}: ${v}`).join(', ')
      : '',
    date: a.timestamp,
    source: 'audit_logs',
  };
};

// ── Source definitions ─────────────────────────────────────────────────────
// Each entry: { fetch: () => Promise<events[]> }
// Grouped so compensation plans/payments run in parallel (preserving original behavior).

function buildSources(trustId) {
  return [
    () => fetchSource(
      trustUrl('/minutes', trustId),
      (d) => toArray(d.minutes || d),
      minutesMapper,
    ),
    () => fetchSource(
      trustUrl('/entities', trustId),
      (d) => d.items || d.entities || [],
      entitiesMapper,
    ),
    () => fetchSource(
      trustUrl('/entity-relationships', trustId),
      (d) => d.items || d.relationships || [],
      relationshipsMapper,
    ),
    () => fetchSource(
      trustUrl('/beneficiaries', trustId),
      (d) => toArray(d.beneficiaries || d),
      beneficiariesMapper,
    ),
    () => fetchSource(
      `${trustUrl('/schedule-a', trustId)}&status=all`,
      (d) => toArray(d.items || d),
      scheduleAMapper,
    ),
    () => fetchSource(
      `/trusts/${trustId}/communications?limit=100`,
      (d) => d.items || d.communications || [],
      communicationsMapper,
    ),
    () => fetchSource(
      trustUrl('/distributions', trustId),
      (d) => toArray(d.items || d.distributions || d),
      distributionsMapper,
    ),
    // Compensation plans + payments — fetched in parallel as in original
    async () => {
      const [plans, payments] = await Promise.all([
        fetchSource(
          trustUrl('/compensation-plans', trustId),
          (d) => toArray(d.items || d.compensation_plans || d),
          compensationPlansMapper,
        ),
        fetchSource(
          trustUrl('/compensation-payments', trustId),
          (d) => toArray(d.items || d.compensation_payments || d),
          compensationPaymentsMapper,
        ),
      ]);
      return [...plans, ...payments];
    },
    () => fetchSource(
      `/trusts/${trustId}/investments`,
      (d) => toArray(d.investments || d),
      investmentsMapper,
    ),
    () => fetchSource(
      trustUrl('/alerts', trustId),
      (d) => toArray(d.alerts || d),
      alertsMapper,
    ),
    () => fetchSource(
      trustUrl('/transactions', trustId),
      (d) => toArray(d.transactions || d),
      transactionsMapper,
    ),
    () => fetchSource(
      '/audit-logs?limit=100',
      (d) => d.audit_logs || [],
      auditLogsMapper,
    ),
  ];
}

function sortByDateDesc(events) {
  return events.sort((a, b) => {
    const dateA = a.date ? new Date(a.date) : new Date(0);
    const dateB = b.date ? new Date(b.date) : new Date(0);
    return dateB - dateA;
  });
}

function applyFilter(events, filter) {
  if (filter === 'all') return events;
  return events.filter((e) => e.type.startsWith(filter));
}

// ── Hook ────────────────────────────────────────────────────────────────────

export function useAuditTrail(selectedTrust) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const loadAuditTrail = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const trustId = selectedTrust.trust_id;
      const sources = buildSources(trustId);

      // Run all source fetchers; each is resilient (returns [] on failure)
      const results = await Promise.allSettled(sources.map((s) => s()));
      const allEvents = results.flatMap((r) =>
        r.status === 'fulfilled' ? r.value : [],
      );

      sortByDateDesc(allEvents);
      const filtered = applyFilter(allEvents, filter);

      setEvents(filtered);
      setTotalPages(Math.max(1, Math.ceil(filtered.length / PAGE_SIZE)));
    } catch (error) {
      console.error('Failed to load audit trail:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedTrust, filter]);

  useEffect(() => {
    if (selectedTrust) loadAuditTrail();
  }, [selectedTrust, page, filter, loadAuditTrail]);

  return {
    events,
    loading,
    filter,
    setFilter,
    page,
    setPage,
    totalPages,
    loadAuditTrail,
  };
}