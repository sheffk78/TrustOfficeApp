// OrgConsolePage.js — org owner console (institution M4 + frontend upgrade)
// Shows orgs you own, members, full client-context trust cards, deep-links
// into the client workspace (global selectedTrust), and the org activity feed.
// Calls GET /api/orgs, /api/orgs/{org_id}/members, /api/orgs/{org_id}/trusts,
// /api/orgs/{org_id}/activity.
import { useState, useEffect, useCallback } from 'react';
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
  Activity, CalendarClock, FileSignature,
} from 'lucide-react';

const fmtDate = (iso) => {
  try { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
  catch { return iso; }
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

export default function OrgConsolePage() {
  const navigate = useNavigate();
  const { setSelectedTrust } = useAuth();
  const [loading, setLoading] = useState(true);
  const [orgs, setOrgs] = useState([]);
  const [members, setMembers] = useState({});
  const [trustsByOrg, setTrustsByOrg] = useState({});
  const [activity, setActivity] = useState({});
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteOrg, setInviteOrg] = useState(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth('/orgs');
      if (!res.ok) { setOrgs([]); return; }
      const list = await res.json();
      setOrgs(list);
      const mem = {}; const trs = {}; const acts = {};
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
        } catch { /* per-org failure tolerated */ }
      }));
      setMembers(mem); setTrustsByOrg(trs); setActivity(acts);
    } catch (e) {
      showError(toast, e, { page: 'OrgConsole' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Deep-link: set the global selected trust (AuthContext persists
  // selected_trust_id), then navigate into the workspace view for it.
  const goToTrustSection = (trust, route) => {
    setSelectedTrust({ trust_id: trust.trust_id, name: trust.name });
    navigate(route);
  };

  const OrgRouteEmptyState = ({ onRetry }) => (
    <div className="main-layout" data-testid="org-console-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          <div className="page-header">
            <h1 className="page-title">Org Console</h1>
            <p className="page-subtitle">
              Trusts your clients have authorized you to work on — scoped, time-limited, revocable by them.
            </p>
          </div>
          <div className="card-trust text-center py-12">
            <Building2 className="w-12 h-12 text-navy/30 mx-auto mb-4" />
            <h2 className="font-serif text-xl text-navy mb-2">No organization yet</h2>
            <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">
              You're not a member of an organization yet. If someone invited you, accept their email invitation first —
              or if you run your own practice, you can create your organization here.
            </p>
            <Button
              className="btn-primary"
              onClick={async () => {
                try {
                  const res = await fetchWithAuth('/orgs', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: 'My Fiduciary Group' }),
                  });
                  if (res.ok) { toast.success('Organization created.'); await onRetry(); }
                  else toast.error('Could not create org — it may already exist.');
                } catch (e) { showError(toast, e, { page: 'OrgConsole' }); }
              }}
              data-testid="create-org-btn"
            >
              <Building2 className="w-4 h-4 mr-2" /> Create Organization
            </Button>
          </div>
        </div>
      </main>
    </div>
  );

  // Member-side view: an org member with no granted trusts sees what happened,
  // who can fix it, and what happens next — instead of an empty list.
  const GrantedTrustsEmptyState = (o) => (
    <div className="card-trust text-center py-10 mb-4" data-testid="no-granted-trusts">
      <FileText className="w-10 h-10 text-navy/30 mx-auto mb-3" />
      <h3 className="font-serif text-md text-navy mb-1">Nothing shared with you yet</h3>
      <p className="text-sm text-muted-foreground max-w-md mx-auto">
        The organization owner hasn't granted you access to any client trusts yet. Once they do, those trusts appear
        here and you'll see exactly what you can work on. Until then, nothing is needed from you.
      </p>
    </div>
  );

  const sendInvite = async () => {
    if (!inviteOrg || !inviteEmail.trim()) return;
    setInviting(true);
    try {
      const res = await fetchWithAuth(`/orgs/${inviteOrg.org_id}/invites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: inviteEmail.trim(), role: 'member' }),
      });
      if (res.ok) {
        toast.success(`Invite sent to ${inviteEmail.trim()}.`);
        setInviteOpen(false); setInviteEmail('');
        await load();
      } else {
        const body = await res.json().catch(() => ({}));
        toast.error(body?.detail?.code || body?.detail || 'Invite failed.');
      }
    } catch (e) {
      showError(toast, e, { page: 'OrgConsole' });
    } finally {
      setInviting(false);
    }
  };

  const grantLevelBadge = (level) => (
    <Badge
      data-testid="trust-card-level"
      variant={level === 'preparer' ? 'default' : 'secondary'}
      className={`capitalize text-xs ${level === 'preparer' ? 'bg-navy text-white hover:opacity-90' : 'text-navy'}`}
    >
      {level}
    </Badge>
  );

  const trustCard = (t) => (
    <Card key={t.trust_id} className="card-trust" data-testid="trust-card">
      <CardContent className="pt-6">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="min-w-0">
            <h3 className="font-serif text-base text-navy truncate">{t.name || 'Untitled trust'}</h3>
            <p className="text-sm text-muted-foreground" data-testid="trust-card-client">
              {t.owner_name || 'Client'}
              {t.owner_email ? <span className="text-xs"> · {t.owner_email}</span> : null}
            </p>
          </div>
          {grantLevelBadge(t.grant_level)}
        </div>

        <dl className="text-sm space-y-1.5 mb-3">
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground shrink-0">Grantor</dt>
            <dd className="text-navy text-right truncate">{t.grantor_name || '—'}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground shrink-0">Trustee</dt>
            <dd className="text-navy text-right truncate">{t.trustee_name || '—'}</dd>
          </div>
        </dl>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground mb-4">
          <span className="inline-flex items-center gap-1">
            <FileSignature className="w-3.5 h-3.5 text-gold" />
            {t.pending_minutes > 0
              ? <span className="text-navy font-medium">{t.pending_minutes} minutes pending review</span>
              : 'No minutes pending'}
          </span>
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
            <FileText className="w-4 h-4 mr-2" /> Go to Minutes <ArrowUpRight className="w-4 h-4 ml-auto" />
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

  const activityFeed = (o) => {
    const events = activity[o.org_id] || [];
    return (
      <Card className="card-trust" data-testid="activity-feed">
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-4 h-4 text-gold" />
            <h3 className="font-medium text-navy">Activity</h3>
          </div>
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No activity yet. Actions org members take on the left appear here — who did what, on whose behalf.
            </p>
          ) : (
            <ul className="space-y-2 max-h-64 overflow-y-auto pr-1">
              {events.filter(Boolean).map(ev => (
                <li key={ev.event_id || ev.created_at} className="text-sm border-b last:border-0 border-border/50 pb-2 last:pb-0">
                  <p className="text-navy">
                    {ACTION_LABELS[ev.action] || ev.action}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {ev.member_name || 'Org member'} · {fmtDate(ev.created_at)}
                  </p>
                  {ev.attribution ? (
                    <p className="text-xs text-muted-foreground/80 italic mt-0.5">{ev.attribution}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="main-layout" data-testid="org-console-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Org Console</h1>
              <p className="page-subtitle">
                Trusts your clients have authorized you to work on — scoped, time-limited, revocable by them.
              </p>
            </div>
            <Button variant="outline" className="btn-secondary" onClick={load} data-testid="refresh-btn">
              <RefreshCw className="w-4 h-4 mr-2" /> Refresh
            </Button>
          </div>

          {loading ? (
            <div className="card-trust skeleton h-40 w-full" />
          ) : orgs.length === 0 ? (
            <OrgRouteEmptyState onRetry={load} />
          ) : (
            orgs.map(o => (
              <div key={o.org_id} className="mb-8" data-testid={`org-card-${o.org_id}`}>
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h2 className="font-serif text-lg text-navy">{o.name}</h2>
                    <code className="text-xs text-muted-foreground">{o.org_id}</code>
                  </div>
                  <Button
                    variant="outline" size="sm"
                    onClick={() => { setInviteOrg(o); setInviteOpen(true); }}
                    data-testid={`invite-${o.org_id}`}
                  >
                    <UserPlus className="w-4 h-4 mr-2" /> Invite team member
                  </Button>
                </div>

                <Card className="card-trust mb-4">
                  <CardContent className="pt-6">
                    <div className="flex items-center gap-2 mb-3">
                      <Users className="w-4 h-4 text-navy" />
                      <h3 className="font-medium text-navy">Members ({(members[o.org_id] || []).length})</h3>
                    </div>
                    {(members[o.org_id] || []).map(m => (
                      <div key={m.member_id} className="flex items-center justify-between py-1.5 border-b last:border-0 border-border/50 text-sm">
                        <span className="text-muted-foreground">{m.name || m.email}</span>
                        <span className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">{m.status === 'active' ? 'Active' : 'Invited'}</span>
                          <Badge variant={m.role === 'owner' ? 'default' : 'secondary'} className="capitalize text-xs">{m.role}</Badge>
                        </span>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <div className="mb-2 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-navy" />
                  <h3 className="font-medium text-navy">
                    Client trusts ({(trustsByOrg[o.org_id] || []).length})
                  </h3>
                </div>
                {(trustsByOrg[o.org_id] || []).length === 0 ? (
                  <GrantedTrustsEmptyState org={o} />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-4">
                    {(trustsByOrg[o.org_id] || []).filter(Boolean).map(t => trustCard(t))}
                  </div>
                )}

                {activityFeed(o)}
              </div>
            ))
          )}
        </div>
      </main>

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent data-testid="invite-dialog">
          <DialogHeader>
            <DialogTitle>Invite a team member to {inviteOrg?.name}</DialogTitle>
            <DialogDescription>
              They'll receive an email invite to join as a member. Clients grant to the org.
            </DialogDescription>
          </DialogHeader>
          <div>
            <Label htmlFor="invite-email">Email</Label>
            <Input
              id="invite-email" type="email" placeholder="colleague@example.com"
              value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} data-testid="invite-email-input"
            />
          </div>
          <Button className="btn-primary mt-2" onClick={sendInvite} disabled={inviting || !inviteEmail.trim()} data-testid="send-invite-btn">
            {inviting ? 'Sending…' : 'Send Invite'}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}