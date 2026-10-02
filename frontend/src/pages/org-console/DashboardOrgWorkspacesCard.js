import { useEffect, useState } from 'react';
import { Building2, ArrowRight, X } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';

/**
 * Org-workspaces nudge (org console workspace entry, 2026-10-01): a member
 * with active client trust grants lands on /dashboard after login with no
 * signal that client workspaces exist. This card counts the granted trusts
 * across the member's orgs and offers one-tap entry. Owner accounts with no
 * org memberships never see it; dismissal persists.
 */
export default function DashboardOrgWorkspacesCard() {
  const [grants, setGrants] = useState([]);
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem('org_ws_nudge_dismissed') === '1'
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchWithAuth('/orgs');
        if (!res.ok) return;
        const orgs = await res.json();
        const list = Array.isArray(orgs) ? orgs : orgs?.orgs || [];
        const perOrg = await Promise.all(
          list.map(async (o) => {
            const r2 = await fetchWithAuth(`/orgs/${o.org_id}/trusts`);
            if (!r2.ok) return [];
            const t = await r2.json();
            return Array.isArray(t) ? t : t?.trusts || [];
          })
        );
        if (!cancelled) setGrants(perOrg.flat());
      } catch {
        /* silent: nudge is best-effort */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const dismiss = () => {
    localStorage.setItem('org_ws_nudge_dismissed', '1');
    setDismissed(true);
  };

  if (dismissed || grants.length === 0) return null;

  return (
    <div
      className="card-trust mb-8 border-[#7C6BB8]/40 relative"
      data-testid="org-workspaces-nudge"
    >
      <button
        onClick={dismiss}
        className="absolute top-3 right-3 text-muted-foreground hover:text-navy"
        data-testid="org-workspaces-nudge-dismiss"
        aria-label="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 rounded-lg bg-[#7C6BB8]/10 border border-[#7C6BB8]/30 flex items-center justify-center shrink-0">
          <Building2 className="w-5 h-5 text-[#7C6BB8]" />
        </div>
        <div className="min-w-0">
          <h3 className="font-serif text-base text-navy">
            {grants.length} client {grants.length === 1 ? 'trust workspace' : 'trust workspaces'} available
          </h3>
          <p className="text-sm text-muted-foreground mt-1 mb-3">
            {grants.length === 1
              ? 'You have granted access through your organization. Open the Org Console to work inside it.'
              : 'You have granted access through your organizations. Open the Org Console to work inside them.'}
          </p>
          <a
            href="/org-console"
            data-testid="org-workspaces-nudge-open"
            className="inline-flex items-center gap-2 font-mono text-sm text-navy border border-navy/30 px-3 py-1.5 hover:bg-navy/5 transition-colors"
          >
            Open Org Console <ArrowRight className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}
