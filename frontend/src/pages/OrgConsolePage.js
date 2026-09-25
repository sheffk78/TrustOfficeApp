// OrgConsolePage.js — org owner console (institution M4)
// Shows orgs you own, members, and the trusts clients have granted you.
// Calls GET /api/orgs, /api/orgs/{org_id}/members, /api/orgs/{org_id}/trusts.
import { useState, useEffect, useCallback } from 'react';
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
import { toast } from 'sonner';
import { Building2, RefreshCw, UserPlus, FileText, Users } from 'lucide-react';

const fmtDate = (iso) => {
  try { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
  catch { return iso; }
};

export default function OrgConsolePage() {
  const [loading, setLoading] = useState(true);
  const [orgs, setOrgs] = useState([]);
  const [members, setMembers] = useState({});
  const [trustsByOrg, setTrustsByOrg] = useState({});
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
      const mem = {}; const trs = {};
      await Promise.all(list.map(async o => {
        try {
          const [mRes, tRes] = await Promise.all([
            fetchWithAuth(`/orgs/${o.org_id}/members`),
            fetchWithAuth(`/orgs/${o.org_id}/trusts`),
          ]);
          if (mRes.ok) mem[o.org_id] = await mRes.json();
          if (tRes.ok) trs[o.org_id] = (await tRes.json()).trusts || [];
        } catch { /* per-org failure tolerated */ }
      }));
      setMembers(mem); setTrustsByOrg(trs);
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

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
      showError(e);
    } finally {
      setInviting(false);
    }
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
            <div className="card-trust text-center py-12">
              <Building2 className="w-12 h-12 text-navy/30 mx-auto mb-4" />
              <h2 className="font-serif text-xl text-navy mb-2">No organization yet</h2>
              <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">
                An org represents your fiduciary practice. Create one to receive delegated access from your clients.
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
                    if (res.ok) { toast.success('Organization created.'); await load(); }
                    else toast.error('Could not create org — it may already exist.');
                  } catch (e) { showError(e); }
                }}
                data-testid="create-org-btn"
              >
                <Building2 className="w-4 h-4 mr-2" /> Create Organization
              </Button>
            </div>
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

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card className="card-trust">
                    <CardContent className="pt-6">
                      <div className="flex items-center gap-2 mb-3">
                        <Users className="w-4 h-4 text-navy" />
                        <h3 className="font-medium text-navy">Members ({(members[o.org_id] || []).length})</h3>
                      </div>
                      {(members[o.org_id] || []).map(m => (
                        <div key={m.member_id} className="flex items-center justify-between py-1.5 border-b last:border-0 border-border/50 text-sm">
                          <span className="text-muted-foreground">{m.name || m.email}</span>
                          <Badge variant={m.role === 'owner' ? 'default' : 'secondary'} className="capitalize text-xs">{m.role}</Badge>
                        </div>
                      ))}
                    </CardContent>
                  </Card>

                  <Card className="card-trust">
                    <CardContent className="pt-6">
                      <div className="flex items-center gap-2 mb-3">
                        <FileText className="w-4 h-4 text-navy" />
                        <h3 className="font-medium text-navy">Granted trusts ({(trustsByOrg[o.org_id] || []).length})</h3>
                      </div>
                      {(trustsByOrg[o.org_id] || []).length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          None yet. When a client grants your org access to their trust, it appears here.
                        </p>
                      ) : (
                        (trustsByOrg[o.org_id] || []).map(t => (
                          <div key={t.trust_id} className="py-1.5 border-b last:border-0 border-border/50 text-sm">
                            <span className="text-navy">{t.name || 'Untitled trust'}</span>
                          </div>
                        ))
                      )}
                    </CardContent>
                  </Card>
                </div>
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