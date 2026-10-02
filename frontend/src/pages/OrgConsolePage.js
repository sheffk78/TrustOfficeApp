// OrgConsolePage.js — org owner console (v2 redesign, council-synthesized 2026-10-01)
// Structure (workflow order, not data-model order):
//   header (freshness) → org switcher → needs-attention rail → client trusts
//   (search + filter + incremental rendering) → activity → team (collapsible,
//   real member actions) → org settings row.
// Scales to many trusts/orgs: search + filters + "Show more" (24-card batch),
// derived rail always computed over ALL loaded trusts, switcher dropdown >3 orgs.
// Calls GET /api/orgs, /api/orgs/{org_id}/members, /api/orgs/{org_id}/trusts,
// /api/orgs/{org_id}/activity; PATCH /orgs/{id}/members/{member_id};
// POST /orgs/enter-trust/{trust_id} (audited workspace entry).
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useNavigate } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { fetchWithAuth } from '@/utils/api';
import { showError } from '@/utils/errors';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import {
  Building2, RefreshCw, UserPlus, FileText, Users, ArrowUpRight,
  Activity, CalendarClock, FileSignature, Search, ChevronDown, Settings,
  MoreHorizontal, PauseCircle, PlayCircle, Copy, AlertTriangle,
} from 'lucide-react';

const fmtDate = (iso) => {
  try { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
  catch { return iso; }
};
const fmtRelative = (iso) => {
  try {
    const d = new Date(iso); const diff = Date.now() - d.getTime();
    if (diff < 0) return fmtDate(iso);
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`;
    const days = Math.floor(h / 24);
    if (days < 7) return days === 1 ? 'yesterday' : `${days}d ago`;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch { return iso; }
};

// Activity feed verbs → readable labels
const ACTION_LABELS = {
  minutes_finalized: 'Finalized minutes',
  minutes_autosaved: 'Autosaved a minutes draft',
  distribution_created: 'Recorded a distribution',
  distribution_approved: 'Approved a distribution',
  distribution_status_changed: 'Updated a distribution status',
  distribution_minutes_attached: 'Attached minutes to a distribution',
  distribution_notice_sent: 'Sent a distribution notice',
  admin_kit_generated: 'Generated the admin kit',
  successor_packet_sent: 'Sent a successor packet',
  trust_protector_appointment_sent: 'Sent a trust protector appointment',
  schedule_a_item_created: 'Added a Schedule A asset',
  schedule_a_item_updated: 'Updated a Schedule A asset',
  schedule_a_item_confirmed: 'Confirmed a Schedule A asset',
  schedule_a_item_disposed: 'Disposed of a Schedule A asset',
  schedule_a_pdf_exported: 'Exported the Schedule A PDF',
  grant_expiring_7d: 'Grant expiry notice sent',
};

const TRUST_PAGE_SIZE = 24;

export default function OrgConsolePage() {
  const navigate = useNavigate();
  const { setSelectedTrust } = useAuth();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);            // page-level load failure (distinct from empty)
  const [lastUpdated, setLastUpdated] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [members, setMembers] = useState({});
  const [trustsByOrg, setTrustsByOrg] = useState({});
  const [activity, setActivity] = useState({});
  const [failedOrgs, setFailedOrgs] = useState({});  // per-org section failures
  const [focusOrg, setFocusOrg] = useState(null);    // active org in switcher
  const [switcherOpen, setSwitcherOpen] = useState(false);
  // trusts browser
  const [trustQuery, setTrustQuery] = useState('');
  const [trustLevel, setTrustLevel] = useState('all'); // all | preparer | viewer
  const [trustShown, setTrustShown] = useState(TRUST_PAGE_SIZE);
  // — Phase 0: server-backed search for orgs beyond client-aggregation scale (>24) —
  const SERVER_MODE_THRESHOLD = 48;
  const [searchParams, setSearchParams] = useSearchParams();
  const [serverTrusts, setServerTrusts] = useState(null);   // null = client mode
  const [serverTotal, setServerTotal] = useState(0);
  const [serverPage, setServerPage] = useState(1);
  const [trustStatus, setTrustStatus] = useState('all');
  const [trustDeadline, setTrustDeadline] = useState('all');
  const [trustSort, setTrustSort] = useState('pending_desc');
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef(null);
  // team
  const [teamOpen, setTeamOpen] = useState(false);   // collapsed by default (>8 shows collapsed)
  const [teamQuery, setTeamQuery] = useState('');
  const [menuMember, setMenuMember] = useState(null); // open row menu member_id
  // invite dialog
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteOrg, setInviteOrg] = useState(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviting, setInviting] = useState(false);
  const [inviteErr, setInviteErr] = useState('');
  const [isOwner, setIsOwner] = useState(false);
  const [confirmMember, setConfirmMember] = useState(null); // {member, action}
  const refreshBtn = useRef(null);

  const load = useCallback(async () => {
    setLoading(true); setErr(null); setFailedOrgs({});
    try {
      const res = await fetchWithAuth('/orgs');
      if (!res.ok) { setErr(new Error(`orgs ${res.status}`)); setOrgs([]); return; }
      const list = await res.json();
      setOrgs(list);
      setFocusOrg(prev => (list.find(o => o.org_id === prev?.org_id) || list[0] || null));
      const mem = {}; const trs = {}; const acts = {}; const failed = {};
      await Promise.all(list.map(async o => {
        try {
          const [mRes, tRes, aRes] = await Promise.all([
            fetchWithAuth(`/orgs/${o.org_id}/members`),
            fetchWithAuth(`/orgs/${o.org_id}/trusts`),
            fetchWithAuth(`/orgs/${o.org_id}/activity?limit=50`),
          ]);
          if (mRes.ok) mem[o.org_id] = await mRes.json();
          if (tRes.ok) trs[o.org_id] = (await tRes.json()).trusts || [];
          if (aRes.ok) acts[o.org_id] = (await aRes.json()).events || [];
          if (!mRes.ok || !tRes.ok || !aRes.ok) failed[o.org_id] = true;
        } catch { failed[o.org_id] = true; }
      }));
      setMembers(mem); setTrustsByOrg(trs); setActivity(acts); setFailedOrgs(failed);
      setLastUpdated(new Date());
    } catch (e) {
      setErr(e);
      showError(toast, e, { page: 'OrgConsole' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ——— Phase 0: server-side search (fires when the focused org is big enough) ———
  const trustCount = (trustsByOrg[focusOrg?.org_id] || []).filter(Boolean).length;
  const serverMode = trustCount > SERVER_MODE_THRESHOLD;
  useEffect(() => {
    if (!serverMode || !focusOrg) { setServerTrusts(null); return; }
    const params = {
      q: trustQuery, level: trustLevel, status: trustStatus,
      deadline: trustDeadline, sort: trustSort,
      page: String(serverPage), page_size: String(TRUST_PAGE_SIZE),
    };
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const qs = new URLSearchParams(params).toString();
        const res = await fetchWithAuth(`/orgs/${focusOrg.org_id}/trusts/search?${qs}`);
        if (res.ok) {
          const body = await res.json();
          setServerTrusts(body.trusts || []);
          setServerTotal(body.total || 0);
        }
      } finally { setSearching(false); }
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [serverMode, focusOrg?.org_id, trustQuery, trustLevel, trustStatus, trustDeadline, trustSort, serverPage]);

  // URL sync — shareable/stable filtered views (?q=&level=&status=...)
  useEffect(() => {
    const sp = new URLSearchParams();
    if (trustQuery) sp.set('q', trustQuery);
    if (trustLevel !== 'all') sp.set('level', trustLevel);
    if (trustStatus !== 'all') sp.set('status', trustStatus);
    if (trustDeadline !== 'all') sp.set('deadline', trustDeadline);
    if (trustSort !== 'pending_desc') sp.set('sort', trustSort);
    setSearchParams(sp, { replace: true });
  }, [trustQuery, trustLevel, trustStatus, trustDeadline, trustSort, setSearchParams]);

  // my role in the focused org (owner vs member — gates admin actions)
  useEffect(() => {
    let alive = true;
    (async () => {
      if (!focusOrg) { if (alive) setIsOwner(false); return; }
      try {
        const me = await fetchWithAuth('/auth/me');
        if (!me.ok) return;
        const profile = await me.json();
        if (!alive) return;
        const roster = members[focusOrg.org_id] || [];
        const mine = roster.find(m => (m.email || '').toLowerCase() === (profile.email || '').toLowerCase());
        setIsOwner(mine?.role === 'owner');
      } catch { /* role probe optional */ }
    })();
    return () => { alive = false; };
  }, [focusOrg, members]);

  // Deep-link (Option B, 2026-10-01): workspace entry is an explicit, audited
  // "viewing" session — same machinery as admin impersonation. The ENTER
  // endpoint validates the grant server-side (level/expiry/revocation) and
  // writes the audit row; org_view_data drives OrgViewBanner + Exit.
  const goToTrustSection = async (trust, route) => {
    try {
      const res = await fetchWithAuth(
        `/orgs/enter-trust/${trust.trust_id}`,
        { method: 'POST' },
      );
      if (!res.ok) throw new Error(`enter-trust ${res.status}`);
      const data = await res.json();
      setSelectedTrust({ trust_id: trust.trust_id, name: trust.name });
      sessionStorage.setItem('org_view_data', JSON.stringify({
        trust_id: data.trust.trust_id,
        trust_name: data.trust.name,
        client_name: data.client.name || data.client.email,
        org_id: data.org.org_id,
        view_level: data.view_level,
        expires_at: data.expires_at,
        entered_at: data.entered_at,
        return_path: data.return_path,
      }));
      window.dispatchEvent(new Event('org_view_changed'));
      navigate(route);
    } catch (e) {
      if (e && e.status === 403) {
        toast.error('Your access to this trust is not active — ask the client to re-grant or check the expiry.');
      } else {
        showError(toast, e, { page: 'OrgConsole' });
      }
    }
  };

  // ——— derived: needs-attention rail (computed over ALL trusts of focus org) ———
  const rail = useMemo(() => {
    const ts = (trustsByOrg[focusOrg?.org_id] || []).filter(Boolean);
    const pending = ts.reduce((n, t) => n + (t.pending_minutes || 0), 0);
    const week = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);
    const deadlines = ts.filter(t => t.next_deadline && t.next_deadline.slice(0, 10) <= week).length;
    return { pending, deadlineTrs: deadlines, trusts: ts.length };
  }, [trustsByOrg, focusOrg]);

  // ——— derived: searchable/filtered + paged trusts ———
  const filteredTrusts = useMemo(() => {
    const ts = (trustsByOrg[focusOrg?.org_id] || []).filter(Boolean);
    const q = trustQuery.trim().toLowerCase();
    let out = ts.filter(t => {
      if (trustLevel !== 'all' && (t.grant_level || 'viewer') !== trustLevel) return false;
      if (!q) return true;
      return [t.name, t.owner_name, t.owner_email, t.grantor_name, t.trustee_name]
        .some(v => (v || '').toLowerCase().includes(q));
    });
    // pending-first so the work surfaces even in a long list
    out = [...out].sort((a, b) => (b.pending_minutes || 0) - (a.pending_minutes || 0));
    return out;
  }, [trustsByOrg, focusOrg, trustQuery, trustLevel]);
  const visibleTrusts = filteredTrusts.slice(0, trustShown);

  // ——— derived: member list (search, sorted owner→active→invited) ———
  const roster = useMemo(() => {
    const all = members[focusOrg?.org_id] || [];
    const q = teamQuery.trim().toLowerCase();
    const rank = { owner: 0, admin: 1, member: 2 };
    return all.filter(m => !q || `${m.name || ''} ${m.email || ''}`.toLowerCase().includes(q))
      .sort((a, b) => (rank[a.role] ?? 3) - (rank[b.role] ?? 3));
  }, [members, focusOrg, teamQuery]);

  const countsByStatus = useMemo(() => {
    const all = members[focusOrg?.org_id] || [];
    return {
      active: all.filter(m => m.status === 'active').length,
      invited: all.filter(m => m.status === 'invited').length,
      suspended: all.filter(m => m.status === 'suspended').length,
    };
  }, [members, focusOrg]);

  // ——— member actions (real backend: PATCH status/role) ———
  const patchMember = async (member, body, confirmLabel) => {
    if (confirmLabel && !window.confirm(confirmLabel)) return;
    try {
      const res = await fetchWithAuth(
        `/orgs/${focusOrg.org_id}/members/${member.member_id}`,
        { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
      );
      if (!res.ok) {
        const det = await res.json().catch(() => ({}));
        toast.error(det?.detail?.code === 'owner_role_transfer_not_supported'
          ? 'Ownership transfer is not supported here yet.'
          : 'Could not update that member.');
        return;
      }
      toast.success('Member updated.');
      await load();
    } catch (e) { showError(toast, e, { page: 'OrgConsole' }); }
  };

  // ——— invite ———
  const sendInvite = async () => {
    if (!inviteOrg || !inviteEmail.trim()) return;
    setInviting(true); setInviteErr('');
    try {
      const res = await fetchWithAuth(`/orgs/${inviteOrg.org_id}/invites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole }),
      });
      if (res.ok) {
        toast.success(`Invite sent to ${inviteEmail.trim()}.`);
        setInviteOpen(false); setInviteEmail(''); setInviteRole('member');
        await load();
      } else {
        const body = await res.json().catch(() => ({}));
        const code = body?.detail?.code || body?.detail;
        setInviteErr(typeof code === 'string' ? code.replace(/_/g, ' ') : 'Invite failed. Check the email and try again.');
      }
    } catch (e) {
      setInviteErr('Network error — try again.');
      showError(toast, e, { page: 'OrgConsole' });
    } finally { setInviting(false); }
  };

  const OrgRouteEmptyState = ({ onRetry }) => (
    <div className="card-trust text-center py-12">
      <Building2 className="w-12 h-12 text-navy/30 mx-auto mb-4" />
      <h2 className="font-serif text-xl text-navy mb-2">No organization yet</h2>
      <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">
        If someone invited you to their organization, accept the email invitation first — that's the
        fastest path in. Or, if you run your own practice, create your organization here.
      </p>
      <Button
        variant="outline" className="btn-secondary"
        onClick={async () => {
          const name = window.prompt('Name your organization (e.g., "Barlow Fiduciary Group")');
          if (!name || !name.trim()) return;
          try {
            const res = await fetchWithAuth('/orgs', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: name.trim() }),
            });
            if (res.ok) { toast.success('Organization created.'); await onRetry(); }
            else toast.error('Could not create org — it may already exist.');
          } catch (e2) { showError(toast, e2, { page: 'OrgConsole' }); }
        }}
        data-testid="create-org-btn"
      >
        <Building2 className="w-4 h-4 mr-2" /> Create Organization
      </Button>
    </div>
  );

  // Member-side view: an org member with no granted trusts sees what happened,
  // who can fix it, and what happens next — instead of an empty list.
  const GrantedTrustsEmptyState = () => (
    <div className="card-trust text-center py-10 mb-4" data-testid="no-granted-trusts">
      <FileText className="w-10 h-10 text-navy/30 mx-auto mb-3" />
      <h3 className="font-serif text-md text-navy mb-1">Nothing shared with you yet</h3>
      <p className="text-sm text-muted-foreground max-w-md mx-auto">
        The organization owner hasn't granted you access to any client trusts yet. Once they do, those trusts appear
        here and you'll see exactly what you can work on. Until then, nothing is needed from you.
      </p>
    </div>
  );

  const grantLevelBadge = (level) => (
    <Badge
      data-testid="trust-card-level"
      variant={level === 'preparer' ? 'default' : 'secondary'}
      className={`capitalize text-xs ${level === 'preparer' ? 'bg-navy text-white hover:opacity-90' : 'text-navy'}`}
    >
      {level}
    </Badge>
  );

  const trustCard = (t) => {
    const pending = t.pending_minutes || 0;
    return (
      <Card key={t.trust_id} className="card-trust" data-testid="trust-card">
        <CardContent className="pt-6">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="min-w-0">
              <h3 className="font-serif text-base text-navy truncate" title={t.name || 'Untitled trust'}>{t.name || 'Untitled trust'}</h3>
              <p className="text-sm text-muted-foreground truncate" title={t.owner_email || ''} data-testid="trust-card-client">
                {t.owner_name || 'Client'}
                {t.owner_email ? <span className="text-xs"> · {t.owner_email}</span> : null}
              </p>
            </div>
            {grantLevelBadge(t.grant_level)}
          </div>

          {pending > 0 ? (
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center gap-1 text-xs font-medium text-navy bg-gold/20 border border-gold/40 rounded-full px-2.5 py-0.5" data-testid="trust-card-pending">
                <FileSignature className="w-3.5 h-3.5 text-gold" />
                {pending} {pending === 1 ? 'minute' : 'minutes'} pending review
              </span>
            </div>
          ) : null}

          <div className="text-xs text-muted-foreground mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="inline-flex items-center gap-1">
              <FileSignature className="w-3.5 h-3.5 text-gold/60" />
              {pending > 0 ? `${pending} pending` : 'No minutes pending'}
            </span>
            <span>Grantor {t.grantor_name || <span>—</span>} · Trustee {t.trustee_name || <span>—</span>}</span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground mb-4">
            <span className="inline-flex items-center gap-1">
              <CalendarClock className="w-3.5 h-3.5 text-gold" />
              {t.next_deadline ? `Next deadline ${fmtDate(t.next_deadline)}` : 'No upcoming deadline'}
            </span>
          </div>

          <div className="flex flex-col gap-2">
            <Button
              className="btn-primary w-full"
              data-testid="go-to-minutes"
              onClick={() => goToTrustSection(t, '/minutes')}
            >
              <FileText className="w-4 h-4 mr-2" />
              {pending > 0 ? `Review ${pending} pending ${pending === 1 ? 'minute' : 'minutes'}` : 'Go to Minutes'}
              <ArrowUpRight className="w-4 h-4 ml-auto" />
            </Button>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline" className="btn-secondary"
                data-testid={`go-to-meetings-${t.trust_id}`}
                onClick={() => goToTrustSection(t, `/governance/history/${t.trust_id}`)}
              >
                Meetings <ArrowUpRight className="w-4 h-4 ml-2" />
              </Button>
              <Button
                variant="outline" className="btn-secondary"
                data-testid={`go-to-distributions-${t.trust_id}`}
                onClick={() => goToTrustSection(t, '/distributions')}
              >
                Distributions <ArrowUpRight className="w-4 h-4 ml-2" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  const SectionHeader = ({ icon: Ic, title, count, right, testid }) => (
    <div className="flex items-center justify-between mb-3" data-testid={testid}>
      <div className="flex items-center gap-2">
        <Ic className="w-4 h-4 text-navy" />
        <h3 className="font-medium text-navy">{title}{count != null ? ` (${count})` : ''}</h3>
      </div>
      {right}
    </div>
  );

  const activityFeed = (o) => {
    const events = (activity[o.org_id] || []).filter(Boolean);
    return (
      <Card className="card-trust" data-testid="activity-feed">
        <CardContent className="pt-6">
          <SectionHeader
            icon={Activity} title="Activity"
            right={<span className="text-xs text-muted-foreground">{events.length ? `${events.length} recent` : ''}</span>}
          />
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No activity yet. Actions org members take on the left appear here — who did what, on whose behalf.
            </p>
          ) : (
            <>
            <ul className="space-y-2 md:max-h-64 md:overflow-y-auto md:pr-1">
              {events.slice(0, 12).map(ev => (
                <li key={ev.event_id || ev.created_at} className="text-sm border-b last:border-0 border-border/50 pb-2 last:pb-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="text-navy min-w-0 truncate">{ACTION_LABELS[ev.action] || ev.action}</p>
                    <span className="text-xs text-muted-foreground shrink-0">{fmtRelative(ev.created_at)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {ev.member_name || 'Org member'} · {fmtRelative(ev.created_at)}
                  </p>
                  {ev.attribution ? (
                    <p className="text-xs text-muted-foreground/80 italic mt-0.5">{ev.attribution}</p>
                  ) : null}
                </li>
              ))}
            </ul>
            {events.length > 12 ? (
              <p className="text-xs text-muted-foreground mt-3">Showing the 12 most recent of {events.length}.</p>
            ) : null}
            </>
          )}
        </CardContent>
      </Card>
    );
  };

  const memberRow = (m) => (
    <div key={m.member_id} className="flex items-center justify-between gap-3 py-2 border-b last:border-0 border-border/50 text-sm min-h-[36px]">
      <span className="min-w-0 truncate text-muted-foreground flex-1" title={m.email || m.name}>
        {m.name || m.email}
        {m.name && m.email ? <span className="text-xs text-muted-foreground/70"> · {m.email}</span> : null}
      </span>
      <span className="flex items-center gap-2 shrink-0">
        <span className={`text-xs ${m.status === 'active' ? 'text-muted-foreground' : 'text-gold'}`}>
          {m.status === 'active' ? 'Active' : m.status === 'suspended' ? 'Suspended' : 'Invited'}
        </span>
        <Badge variant={m.role === 'owner' ? 'default' : 'secondary'} className="capitalize text-xs pointer-events-none opacity-90">{m.role}</Badge>
        {m.role !== 'owner' && isOwner ? (
          <Button
            variant="ghost" size="sm" className="h-8 w-8 p-0"
            aria-label={`Member actions for ${m.name || m.email}`}
            data-testid={`member-menu-${m.member_id}`}
            onClick={() => setMenuMember(menuMember === m.member_id ? null : m.member_id)}
          >
            <MoreHorizontal className="w-4 h-4" />
          </Button>
        ) : null}
      </span>
    </div>
  );

  const memberMenu = (m) => (
    <div className="flex flex-wrap gap-2 py-2 pl-2 bg-cream/40 rounded" data-testid={`member-menu-open-${m.member_id}`}>
      {m.status === 'invited' ? (
        <Button variant="outline" size="sm" className="btn-secondary" onClick={() => patchMember(m, { status: 'active' }, `Mark ${m.email} as accepted (they can sign in)?`)}>
          <PlayCircle className="w-4 h-4 mr-1" /> Mark accepted
        </Button>
      ) : m.status === 'active' ? (
        <Button variant="outline" size="sm" className="btn-secondary" onClick={() => patchMember(m, { status: 'suspended' }, `Suspend ${m.name || m.email}? They lose org access until reinstated.`)}>
          <PauseCircle className="w-4 h-4 mr-1" /> Suspend
        </Button>
      ) : (
        <Button variant="outline" size="sm" className="btn-secondary" onClick={() => patchMember(m, { status: 'active' }, `Reinstate ${m.name || m.email}?`)}>
          <PlayCircle className="w-4 h-4 mr-1" /> Reinstate
        </Button>
      )}
      {isOwner && m.role !== 'owner' && m.role !== 'admin' ? (
        <Button variant="outline" size="sm" className="btn-secondary" onClick={() => patchMember(m, { role: 'admin' }, `Make ${m.name || m.email} an org admin?`)}>
          Make admin
        </Button>
      ) : null}
      {isOwner && m.role === 'admin' ? (
        <Button variant="outline" size="sm" className="btn-secondary" onClick={() => patchMember(m, { role: 'member' }, `Set ${m.name || m.email} back to member?`)}>
          Set to member
        </Button>
      ) : null}
    </div>
  );

  const teamSection = (o) => {
    const all = members[o.org_id] || [];
    const shown = teamOpen ? roster : roster.slice(0, 5);
    return (
      <Card className="card-trust mb-4" data-testid="team-card">
        <CardContent className="pt-6">
          <SectionHeader
            icon={Users} title="Team" count={all.length}
            right={
              <div className="flex items-center gap-2">
                {roster.length > 8 || all.length > 8 ? (
                  <Button variant="ghost" size="sm" className="h-8" data-testid="team-toggle" onClick={() => setTeamOpen(v => !v)}>
                    {teamOpen ? 'Show less' : `Show all ${all.length}`}
                    <ChevronDown className={`w-4 h-4 ml-1 transition-transform ${teamOpen ? 'rotate-180' : ''}`} />
                  </Button>
                ) : null}
                <Button variant="outline" size="sm" className="btn-secondary"
                  onClick={() => { setInviteOrg(o); setInviteOpen(true); }}
                  data-testid={`invite-${o.org_id}`}
                >
                  <UserPlus className="w-4 h-4 mr-2" /> Invite
                </Button>
              </div>
            }
          />
          {all.length > 8 ? (
            <Input
              value={teamQuery} onChange={e => setTeamQuery(e.target.value)}
              placeholder="Search team…" className="mb-3 text-sm" data-testid="team-search"
            />
          ) : null}
          <div className="text-xs text-muted-foreground mb-2">
            {countsByStatus.active} active{countsByStatus.invited ? ` · ${countsByStatus.invited} invited` : ''}{countsByStatus.suspended ? ` · ${countsByStatus.suspended} suspended` : ''}
          </div>
          {shown.map(m => (
            <div key={`row-${m.member_id}`}>
              {memberRow(m)}
              {menuMember === m.member_id ? memberMenu(m) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    );
  };

  const orgSwitcher = () => {
    if (orgs.length === 0) return null;
    const f = focusOrg || orgs[0];
    const orgStats = (o) => {
      const ts = (trustsByOrg[o.org_id] || []).filter(Boolean);
      const pend = ts.reduce((n, t) => n + (t.pending_minutes || 0), 0);
      const mm = (members[o.org_id] || []).length;
      return `${mm} member${mm === 1 ? '' : 's'} · ${ts.length} trust${ts.length === 1 ? '' : 's'}${pend ? ` · ${pend} pending` : ''}`;
    };
    if (orgs.length <= 3) {
      return (
        <div className="flex flex-wrap items-center gap-2 mb-4" data-testid="org-switcher">
          {orgs.map(o => (
            <button
              key={o.org_id}
              onClick={() => { setFocusOrg(o); setTrustQuery(''); setTrustLevel('all'); setTrustShown(TRUST_PAGE_SIZE); setTeamOpen(false); setTeamQuery(''); }}
              className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${o.org_id === f.org_id
                ? 'bg-navy text-white border-navy'
                : 'bg-transparent text-navy border-border hover:border-navy/50'}`}
              data-testid={`org-chip-${o.org_id}`}
            >
              {o.name}
              <span className={`ml-2 text-xs ${o.org_id === f.org_id ? 'text-white/70' : 'text-muted-foreground'}`}>
                {orgStats(o)}
              </span>
            </button>
          ))}
        </div>
      );
    }
    // many orgs → dropdown
    return (
      <div className="relative mb-4" data-testid="org-switcher">
        <Button variant="outline" className="btn-secondary" data-testid="org-switcher-toggle" onClick={() => setSwitcherOpen(v => !v)}>
          <Building2 className="w-4 h-4 mr-2" /> {f.name} <span className="text-xs text-muted-foreground ml-2">{orgStats(f)}</span>
          <ChevronDown className={`w-4 h-4 ml-2 transition-transform ${switcherOpen ? 'rotate-180' : ''}`} />
        </Button>
        {switcherOpen ? (
          <div className="absolute z-20 mt-2 w-full max-w-sm card-trust p-2" data-testid="org-switcher-menu">
            {orgs.map(o => (
              <button key={o.org_id}
                onClick={() => { setFocusOrg(o); setSwitcherOpen(false); setTrustQuery(''); setTrustLevel('all'); setTrustShown(TRUST_PAGE_SIZE); setTeamOpen(false); setTeamQuery(''); }}
                className="w-full text-left px-3 py-2 rounded hover:bg-cream/60 text-sm"
              >
                <span className="text-navy">{o.name}</span>
                <span className="text-xs text-muted-foreground ml-2">{orgStats(o)}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div className="main-layout" data-testid="org-console-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          <div className="page-header flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h1 className="page-title">Org Console</h1>
              <p className="page-subtitle">
                Your practice's account: the client trusts shared with your organization, the team that works them, and what the team does.
              </p>
              {lastUpdated ? (
                <p className="text-xs text-muted-foreground mt-1" data-testid="last-updated">
                  Updated {lastUpdated.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                </p>
              ) : null}
            </div>
            <Button variant="outline" className="btn-secondary" onClick={load} disabled={loading} data-testid="refresh-btn" ref={refreshBtn}>
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
          </div>

          {loading && !orgs.length ? (
            <div className="card-trust skeleton h-40 w-full" />
          ) : err ? (
            <div className="card-trust text-center py-10" data-testid="org-console-error">
              <AlertTriangle className="w-10 h-10 text-gold mx-auto mb-3" />
              <h2 className="font-serif text-xl text-navy mb-2">Couldn't load your organizations</h2>
              <p className="text-sm text-muted-foreground mb-4">Check your connection and try again — your data is safe.</p>
              <Button className="btn-primary" onClick={load} data-testid="org-console-retry">Try again</Button>
            </div>
          ) : orgs.length === 0 ? (
            <OrgRouteEmptyState onRetry={load} />
          ) : (
            <>
              {orgSwitcher()}
              {failedOrgs[focusOrg?.org_id] ? (
                <div className="card-trust mb-4 flex items-center justify-between" data-testid="org-section-failed">
                  <span className="text-sm text-navy">Some sections for {focusOrg.name} didn't load.</span>
                  <Button variant="outline" size="sm" className="btn-secondary" onClick={load}>Retry</Button>
                </div>
              ) : null}
              {focusOrg ? (
                <div data-testid={`org-card-${focusOrg.org_id}`}>
                  {/* needs-attention rail */}
                  {(rail.pending > 0 || rail.deadlineTrs > 0) ? (
                    <div className="flex flex-wrap items-center gap-2 mb-4" data-testid="attention-rail">
                      {rail.pending > 0 ? (
                        <button
                          onClick={() => { setTrustQuery(''); setTrustLevel('all'); }}
                          className="inline-flex items-center gap-1.5 text-xs font-medium text-navy bg-gold/20 border border-gold/40 rounded-full px-3 py-1.5"
                          data-testid="rail-pending"
                        >
                          <FileSignature className="w-3.5 h-3.5 text-gold" />
                          {rail.pending} pending {rail.pending === 1 ? 'minute' : 'minutes'} across your trusts
                        </button>
                      ) : null}
                      {rail.deadlineTrs > 0 ? (
                        <span className="inline-flex items-center gap-1.5 text-xs text-navy border border-gold/40 rounded-full px-3 py-1.5" data-testid="rail-deadlines">
                          <CalendarClock className="w-3.5 h-3.5 text-gold" />
                          {rail.deadlineTrs} {rail.deadlineTrs === 1 ? 'deadline' : 'deadlines'} within 7 days
                        </span>
                      ) : null}
                      <span className="text-xs text-muted-foreground">sorted pending-first below</span>
                    </div>
                  ) : null}

                  {/* trusts */}
                  <div className="mb-2 flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-navy" />
                      <h3 className="font-medium text-navy" data-testid="trusts-heading">
                        Client trusts ({(trustsByOrg[focusOrg.org_id] || []).filter(Boolean).length})
                      </h3>
                      {serverMode && serverTrusts ? (
                        <span className="text-xs text-muted-foreground" data-testid="trust-result-count">
                          {serverTotal === 0 ? 'no matches' : `showing ${serverTrusts.length} of ${serverTotal}`}
                        </span>
                      ) : null}
                    </div>
                    {trustCount > 6 ? (
                      <div className="flex items-center gap-2 flex-wrap">
                        <div className="relative">
                          <Search className="w-4 h-4 text-muted-foreground absolute left-2.5 top-2.5" />
                          <Input
                            value={trustQuery} onChange={e => { setTrustQuery(e.target.value); setServerPage(1); }}
                            placeholder="Search trust, client, or email…" className="pl-8 text-sm w-64"
                            data-testid="trust-search"
                          />
                        </div>
                        <div className="flex gap-1">
                          {['all', 'preparer', 'viewer'].map(lv => (
                            <button key={lv}
                              onClick={() => { setTrustLevel(lv); setServerPage(1); }}
                              className={`px-2.5 py-1 rounded-full text-xs border ${trustLevel === lv ? 'bg-navy text-white border-navy' : 'text-navy border-border hover:border-navy/50'}`}
                              data-testid={`trust-level-${lv}`}
                            >
                              {lv === 'all' ? 'All levels' : lv}
                            </button>
                          ))}
                        </div>
                        {serverMode ? (
                          <div className="flex gap-1" data-testid="advanced-filters">
                            <select
                              value={trustStatus} onChange={e => { setTrustStatus(e.target.value); setServerPage(1); }}
                              className="text-xs border border-border rounded-md bg-background px-2 py-1.5 text-navy"
                              data-testid="trust-status-filter"
                              aria-label="Status filter"
                            >
                              <option value="all">All status</option>
                              <option value="attention">Needs attention</option>
                              <option value="healthy">Healthy</option>
                            </select>
                            <select
                              value={trustDeadline} onChange={e => { setTrustDeadline(e.target.value); setServerPage(1); }}
                              className="text-xs border border-border rounded-md bg-background px-2 py-1.5 text-navy"
                              data-testid="trust-deadline-filter"
                              aria-label="Deadline filter"
                            >
                              <option value="all">Any deadline</option>
                              <option value="overdue">Overdue</option>
                              <option value="7d">Next 7 days</option>
                              <option value="30d">Next 30 days</option>
                              <option value="quarter">This quarter</option>
                              <option value="none">No deadline</option>
                            </select>
                            <select
                              value={trustSort} onChange={e => { setTrustSort(e.target.value); setServerPage(1); }}
                              className="text-xs border border-border rounded-md bg-background px-2 py-1.5 text-navy"
                              data-testid="trust-sort"
                              aria-label="Sort"
                            >
                              <option value="pending_desc">Most pending first</option>
                              <option value="deadline_asc">Deadline soonest</option>
                              <option value="health_asc">Lowest score</option>
                              <option value="name_asc">Name A–Z</option>
                            </select>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground mb-3">Scoped, time-limited, revocable by the client.</p>
                  {(trustsByOrg[focusOrg.org_id] || []).length === 0 ? (
                    <GrantedTrustsEmptyState />
                  ) : serverMode && (serverTrusts || []).length === 0 ? (
                    <div className="card-trust text-center py-8 mb-4" data-testid="trust-filter-empty">
                      <p className="text-sm text-muted-foreground mb-2">
                        No trusts match {trustQuery ? `"${trustQuery}"` : 'these filters'}
                        {trustStatus !== 'all' || trustDeadline !== 'all' ? ' + filter selections' : ''}.
                      </p>
                      <Button variant="outline" size="sm" className="btn-secondary" onClick={() => { setTrustQuery(''); setTrustLevel('all'); setTrustStatus('all'); setTrustDeadline('all'); setServerPage(1); }}>Clear</Button>
                    </div>
                  ) : !serverMode && filteredTrusts.length === 0 ? (
                    <div className="card-trust text-center py-8 mb-4" data-testid="trust-filter-empty">
                      <p className="text-sm text-muted-foreground mb-2">No trusts match “{trustQuery || trustLevel}”.</p>
                      <Button variant="outline" size="sm" className="btn-secondary" onClick={() => { setTrustQuery(''); setTrustLevel('all'); }}>Clear</Button>
                    </div>
                  ) : (
                    <>
                      {serverMode ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-4" data-testid="server-trust-grid">
                          {(serverTrusts || []).filter(Boolean).map(t => trustCard(t))}
                          {searching ? <p className="text-xs text-muted-foreground">Searching…</p> : null}
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-4">
                          {visibleTrusts.map(t => trustCard(t))}
                        </div>
                      )}
                      {serverMode && serverTotal > serverPage * TRUST_PAGE_SIZE ? (
                        <Button variant="outline" className="btn-secondary w-full mb-4" onClick={() => setServerPage(n => n + 1)} data-testid="trust-show-more">
                          Load page {serverPage + 1} of {Math.ceil(serverTotal / TRUST_PAGE_SIZE)}
                        </Button>
                      ) : null}
                      {!serverMode && filteredTrusts.length > trustShown ? (
                        <Button variant="outline" className="btn-secondary w-full mb-4" onClick={() => setTrustShown(n => n + TRUST_PAGE_SIZE)} data-testid="trust-show-more">
                          Show {Math.min(TRUST_PAGE_SIZE, filteredTrusts.length - trustShown)} more of {filteredTrusts.length}
                        </Button>
                      ) : null}
                    </>
                  )}

                  {/* two-column zone on xl: trusts already full-width above; activity + team side by side on wide screens */}
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                    {activityFeed(focusOrg)}
                    {teamSection(focusOrg)}
                  </div>

                  {/* org settings row */}
                  <div className="card-trust mt-4 mb-8" data-testid="org-settings">
                    <CardContent className="pt-6 flex items-center justify-between gap-3 flex-wrap">
                      <div className="flex items-center gap-2 text-sm text-navy">
                        <Settings className="w-4 h-4 text-navy" />
                        <span className="font-medium">{focusOrg.name}</span>
                        <button
                          className="text-xs text-muted-foreground hover:text-navy inline-flex items-center gap-1"
                          title={focusOrg.org_id}
                          onClick={() => { try { navigator.clipboard?.writeText(focusOrg.org_id); toast.success('Org ID copied.'); } catch {} }}
                          data-testid="org-id-copy"
                        >
                          <span>{focusOrg.org_id.slice(0, 10)}⋯{focusOrg.org_id.slice(-4)}</span>
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <span className="text-xs text-muted-foreground">Renaming and org-level policy are coming — contact support for changes.</span>
                    </CardContent>
                  </div>
                </div>
              ) : null}
            </>
          )}
        </div>
      </main>

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent data-testid="invite-dialog">
          <DialogHeader>
            <DialogTitle>Invite a team member to {inviteOrg?.name}</DialogTitle>
            <DialogDescription>
              They'll get an email invite. Once they accept, they can open every trust this org has been
              granted — you can suspend or remove them anytime.
            </DialogDescription>
          </DialogHeader>
          <div>
            <Label htmlFor="invite-email">Email</Label>
            <Input
              id="invite-email" type="email" inputMode="email" autoCapitalize="none"
              placeholder="colleague@example.com" className="mt-1"
              value={inviteEmail} onChange={e => setInviteEmail(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !inviting && inviteEmail.trim()) sendInvite(); }}
              data-testid="invite-email-input"
            />
            <Label htmlFor="invite-role" className="mt-3">Role</Label>
            <select
              id="invite-role" value={inviteRole} onChange={e => setInviteRole(e.target.value)}
              className="mt-1 w-full text-sm border border-border rounded-md bg-background px-3 py-2"
              data-testid="invite-role-select"
            >
              <option value="member">Member</option>
              {isOwner ? <option value="admin">Admin</option> : null}
            </select>
            {inviteErr ? <p className="text-xs text-red-700 mt-2" data-testid="invite-error">{inviteErr}</p> : null}
          </div>
          <Button className="btn-primary w-full" onClick={sendInvite} disabled={inviting || !inviteEmail.trim()} data-testid="send-invite-btn">
            {inviting ? 'Sending…' : 'Send Invite'}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
