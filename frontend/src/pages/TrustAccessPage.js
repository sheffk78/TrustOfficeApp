// TrustAccessPage.js — client-facing grant-access screen (institution M4)
// Lets a trust owner grant "WingPoint Trust Group" (their fiduciary org) scoped,
// revocable access to their trust. Calls POST /api/trusts/{trust_id}/org-grants.
// Rendered only when the org feature is on; gracefully empty otherwise.
import { useState, useEffect, useCallback } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { fetchWithAuth } from '@/utils/api';
import { useAuth } from '@/context/AuthContext';
import { showError } from '@/utils/errors';
import { toast } from 'sonner';
import { Shield, KeyRound, Trash2, RefreshCw, Calendar } from 'lucide-react';

const LEVELS = [
  { id: 'viewer', label: 'View only', desc: 'Your fiduciary can see trust records and minutes, but cannot change anything.' },
  { id: 'preparer', label: 'Prepare minutes', desc: 'Your fiduciary can draft minutes and manage records. You approve before anything is final.' },
];

const fmtDate = (iso) => {
  try { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
  catch { return iso; }
};

export default function TrustAccessPage() {
  const { selectedTrust, trusts } = useAuth();
  const [loading, setLoading] = useState(true);
  const [orgs, setOrgs] = useState([]);
  const [grants, setGrants] = useState([]);
  const [grantOpen, setGrantOpen] = useState(false);
  const [orgIdInput, setOrgIdInput] = useState('');
  const [level, setLevel] = useState('viewer');
  const [months, setMonths] = useState('12');
  const [attested, setAttested] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [revoking, setRevoking] = useState(null);

  const trustId = selectedTrust?.trust_id;
  const isOwner = Boolean(selectedTrust);

  const load = useCallback(async () => {
    if (!trustId) { setLoading(false); return; }
    setLoading(true);
    try {
      const [orgsRes, grantsRes] = await Promise.all([
        fetchWithAuth('/orgs'),
        fetchWithAuth(`/trusts/${trustId}/org-grants`),
      ]);
      if (orgsRes.ok) setOrgs(await orgsRes.json());
      if (grantsRes.ok) setGrants(await grantsRes.json());
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
    }
  }, [trustId]);

  useEffect(() => { load(); }, [load]);

  const activeGrants = grants.filter(g => g.status === 'active');
  const pastGrants = grants.filter(g => g.status !== 'active');

  const submitGrant = async () => {
    if (!attested) { toast.error('Please confirm the attestation before granting.'); return; }
    setSubmitting(true);
    try {
      const expires = new Date();
      expires.setMonth(expires.getMonth() + Number(months || 12));
      const memberRes = await fetchWithAuth(`/orgs/${orgIdInput.trim()}/members`);
      let memberId = `mem_${orgIdInput.trim().replace('org_', '')}`;
      if (memberRes.ok) {
        const members = await memberRes.json();
        const owner = members.find(m => m.role === 'owner');
        if (owner) memberId = owner.member_id;
      }
      const res = await fetchWithAuth(`/trusts/${trustId}/org-grants`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org_id: orgIdInput.trim(),
          member_id: memberId,
          level,
          expires_at: expires.toISOString(),
          attested_delegation: true,
          attestation_ref: `ui-${Date.now()}`,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const code = body?.detail?.code;
        if (code === 'expiry_exceeds_365_days') toast.error('Grant window cannot exceed 12 months.');
        else if (res.status === 404) toast.error('Feature not available or org not found — check the org ID.');
        else if (res.status === 403) toast.error('Only the trust owner can grant access.');
        else toast.error(body?.detail || 'Grant failed.');
        return;
      }
      toast.success('Access granted. A notice email has been sent.');
      setGrantOpen(false); setAttested(false); setOrgIdInput(''); setLevel('viewer');
      await load();
    } catch (e) {
      showError(e);
    } finally {
      setSubmitting(false);
    }
  };

  const revoke = async (grantId) => {
    setRevoking(grantId);
    try {
      const res = await fetchWithAuth(`/trusts/${trustId}/org-grants/${grantId}`, { method: 'DELETE' });
      if (res.ok) { toast.success('Access revoked.'); await load(); }
      else toast.error('Revoke failed — try again or contact support.');
    } catch (e) {
      showError(e);
    } finally {
      setRevoking(null);
    }
  };

  if (!trustId) {
    return (
      <div className="main-layout" data-testid="trust-access-page">
        <Sidebar />
        <main className="main-content dot-grid">
          <div className="page-container">
            <h1 className="page-title">Trust Access</h1>
            <p className="text-sm text-muted-foreground">Select a trust to manage who has access to it.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="main-layout" data-testid="trust-access-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Trust Access</h1>
              <p className="page-subtitle">
                Control which fiduciaries can act on <strong>{selectedTrust?.name || selectedTrust?.trust_name || 'this trust'}</strong> — and take access back any time.
              </p>
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="btn-secondary" onClick={load} data-testid="refresh-btn">
                <RefreshCw className="w-4 h-4 mr-2" /> Refresh
              </Button>
              <Button className="btn-primary" onClick={() => setGrantOpen(true)} data-testid="grant-access-btn">
                <KeyRound className="w-4 h-4 mr-2" /> Grant Access
              </Button>
            </div>
          </div>

          <Card className="card-trust mb-6">
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <Shield className="w-5 h-5 text-navy mt-0.5" />
                <div className="text-sm text-muted-foreground">
                  Granting access gives a fiduciary organization a scoped key to this trust — nothing more.
                  Every grant is logged, notices you by email, expires within 12 months, and can be revoked by you instantly.
                </div>
              </div>
            </CardContent>
          </Card>

          <h2 className="font-serif text-lg text-navy mb-3">Active access</h2>
          {loading ? (
            <div className="card-trust skeleton h-24 w-full mb-4" />
          ) : activeGrants.length === 0 ? (
            <div className="card-trust text-center py-10 mb-6">
              <KeyRound className="w-10 h-10 text-navy/30 mx-auto mb-3" />
              <h3 className="font-serif text-md text-navy mb-1">No outside access right now</h3>
              <p className="text-sm text-muted-foreground max-w-md mx-auto">
                Only you can work on this trust. To let your fiduciary help with minutes and records, grant them access above.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              {activeGrants.map(g => (
                <Card className="card-trust" key={g.grant_id} data-testid={`grant-card-${g.grant_id}`}>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between mb-2">
                      <Badge variant="secondary" className="capitalize">{g.level === 'preparer' ? 'Prepare minutes' : 'View only'}</Badge>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => revoke(g.grant_id)} disabled={revoking === g.grant_id} data-testid={`revoke-${g.grant_id}`}>
                        <Trash2 className="w-4 h-4 mr-1" /> {revoking === g.grant_id ? 'Revoking…' : 'Revoke'}
                      </Button>
                    </div>
                    <div className="text-sm text-navy">Org: <code className="text-xs">{g.org_id}</code></div>
                    <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                      <Calendar className="w-3.5 h-3.5" /> Expires {fmtDate(g.expires_at)}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {pastGrants.length > 0 && (
            <>
              <h2 className="font-serif text-lg text-navy mb-3">Past access</h2>
              <div className="card-trust mb-6">
                {pastGrants.map(g => (
                  <div key={g.grant_id} className="flex items-center justify-between py-2 px-4 border-b last:border-0 border-border/50 text-sm">
                    <span className="text-muted-foreground"><code className="text-xs">{g.org_id}</code> · {g.level}</span>
                    <span className="text-xs text-muted-foreground capitalize">{g.status}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </main>

      <Dialog open={grantOpen} onOpenChange={setGrantOpen}>
        <DialogContent data-testid="grant-dialog">
          <DialogHeader>
            <DialogTitle>Grant access to your fiduciary</DialogTitle>
            <DialogDescription>
              Granting is logged and a notice email is sent. You can revoke at any time from this page.
            </DialogDescription>
          </DialogHeader>
          {orgs.length > 0 && (
            <div className="mb-3">
              <Label className="text-sm text-navy">Organizations you belong to</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {orgs.map(o => (
                  <Badge
                    key={o.org_id}
                    variant={orgIdInput === o.org_id ? 'default' : 'secondary'}
                    className="cursor-pointer"
                    onClick={() => setOrgIdInput(o.org_id)}
                  >
                    {o.name}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          <div className="space-y-4">
            <div>
              <Label htmlFor="org-id">Organization ID</Label>
              <Input
                id="org-id"
                placeholder="org_..."
                value={orgIdInput}
                onChange={e => setOrgIdInput(e.target.value)}
                data-testid="org-id-input"
              />
            </div>
            <div>
              <Label className="text-sm text-navy">Access level</Label>
              <div className="grid grid-cols-1 gap-2 mt-2">
                {LEVELS.map(l => (
                  <label key={l.id} className={`flex items-start gap-2 p-3 rounded-md border cursor-pointer ${level === l.id ? 'border-primary bg-accent/40' : 'border-border'}`}>
                    <input type="radio" name="level" value={l.id} checked={level === l.id} onChange={() => setLevel(l.id)} className="mt-1" data-testid={`level-${l.id}`} />
                    <span>
                      <span className="text-sm font-medium text-navy">{l.label}</span>
                      <span className="block text-xs text-muted-foreground">{l.desc}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <div>
              <Label className="text-sm text-navy">Expires after</Label>
              <select
                className="w-full mt-2 p-2 rounded-md border border-border bg-background text-sm"
                value={months} onChange={e => setMonths(e.target.value)} data-testid="expiry-select"
              >
                <option value="1">1 month</option>
                <option value="3">3 months</option>
                <option value="6">6 months</option>
                <option value="12">12 months (maximum)</option>
              </select>
            </div>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={attested} onChange={e => setAttested(e.target.checked)} data-testid="attest-checkbox" />
              <span className="text-muted-foreground">
                I confirm I am the trustee of this trust and I am delegating this access knowingly.
              </span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGrantOpen(false)}>Cancel</Button>
            <Button className="btn-primary" onClick={submitGrant} disabled={submitting || !attested || !orgIdInput.trim()} data-testid="confirm-grant-btn">
              {submitting ? 'Granting…' : 'Grant Access'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}