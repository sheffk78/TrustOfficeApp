// OrgViewBanner.js — persistent "you're inside a client's workspace" banner.
// Modeled on ImpersonationBanner (approved Option B, 2026-10-01): the org
// console's workspace entry rides the same state machinery admin
// impersonation uses — explicit audited ENTER (POST /api/orgs/enter-trust)
// and EXIT (POST /api/orgs/enter-trust/{id}/log-exit), a fixed top banner
// that is impossible to miss, and one-tap return to the Org Console.
// Server-side scoping is unchanged: every trust data endpoint keeps
// enforcing require_org_grant (level, expiry, revocation).
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, X, UserCog } from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';

const BACKEND = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

const fmtExpiry = (iso) => {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch { return ''; }
};

export const OrgViewBanner = () => {
  const navigate = useNavigate();
  const [exiting, setExiting] = useState(false);
  const [viewTick, setViewTick] = useState(0);
  let view = null;
  try { view = JSON.parse(sessionStorage.getItem('org_view_data') || 'null'); } catch { view = null; }

  // Keep the banner reactive + push page content down while viewing
  // (same body-class contract ImpersonationBanner uses).
  useEffect(() => {
    if (view) {
      document.body.classList.add('impersonating');
      setViewTick((t) => t + 1);
    } else {
      document.body.classList.remove('impersonating');
    }
    const onStorage = () => setViewTick((t) => t + 1);
    window.addEventListener('org_view_changed', onStorage);
    return () => {
      document.body.classList.remove('impersonating');
      window.removeEventListener('org_view_changed', onStorage);
    };
  }, []);  // mount/unmount scope — view re-read on tick render
  if (!view) return null;

  const handleExit = async () => {
    setExiting(true);
    try {
      // Best-effort audit; the exit itself must always succeed.
      try {
        await fetchWithAuth(`${BACKEND}/api/orgs/enter-trust/${view.trust_id}/log-exit`, {
          method: 'POST',
        });
      } catch (e) {
        console.error('Failed to log org workspace exit:', e);
      }
      sessionStorage.removeItem('org_view_data');
      window.dispatchEvent(new Event('org_view_changed'));
      toast.success('Returned to Org Console');
      navigate('/org-console');
    } finally {
      setExiting(false);
    }
  };

  const expiry = view.expires_at ? ` · access ends ${fmtExpiry(view.expires_at)}` : '';

  return (
    <div
      className="fixed top-0 left-0 right-0 z-[100] bg-violet-700 text-white px-4 py-2 shadow-lg"
      data-testid="org-view-banner"
      role="status"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center gap-2 bg-violet-800 rounded-full px-3 py-1 shrink-0">
            <Eye className="w-4 h-4" />
            <span className="text-sm font-medium">VIEWING</span>
          </div>
          <div className="flex items-center gap-2 min-w-0">
            <UserCog className="w-5 h-5 shrink-0" />
            <span className="font-semibold truncate">
              {view.trust_name || 'Client Trust'}
            </span>
            {view.client_name && (
              <span className="text-violet-200 truncate hidden sm:inline">
                ({view.client_name}) · {view.view_level}{expiry}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={handleExit}
          disabled={exiting}
          data-testid="org-view-exit"
          className="flex items-center gap-2 bg-white text-violet-800 rounded-full px-4 py-1.5 text-sm font-semibold hover:bg-violet-50 transition-colors shrink-0 focus:outline-none focus:ring-2 focus:ring-white"
        >
          <X className="w-4 h-4" />
          {exiting ? 'Returning…' : 'Back to Org Console'}
        </button>
      </div>
    </div>
  );
};

export default OrgViewBanner;