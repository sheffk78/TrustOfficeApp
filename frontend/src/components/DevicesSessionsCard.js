// DevicesSessionsCard - the "Devices & sessions" card on the Settings
// Privacy & Security tab (FEATURE 5 item 2).
//
// Lists the user's active sessions (device label, IP, last-active relative
// time, "This device" badge), with a per-row "Sign out" button (hidden for the
// current device) and a "Sign out everywhere else" button guarded by a confirm
// dialog. Loads on mount, polls nothing (reloads on demand), and handles the
// empty state and API errors gracefully.
//
// Backend contract (pinned):
//   GET  /auth/sessions  -> { sessions: [{ jti, device_label, ip,
//                                          created_at, last_seen_at, is_current }] }
//   DELETE /auth/sessions/<jti> -> 200 (400 if jti is the current session)
//   POST /auth/sessions/revoke-all -> { revoked_count: number }

import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription, DialogTrigger } from '@/components/ui/dialog';
import { fetchWithAuth } from '@/utils/api';
import { getErrorMessage } from '@/utils/api';
import { showError } from '@/utils/errors';
import { toast } from 'sonner';
import { Monitor, Smartphone, LogOut, ShieldCheck } from 'lucide-react';

// ASCII-only relative-time formatter (no Intl.RelativeTimeFormat to keep deps
// light and strings ASCII). Parses ISO timestamps and renders "just now",
// "N minutes/hours/days ago", or a date for older entries.
function relativeTime(iso) {
  if (!iso) return 'unknown';
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return 'unknown';
  const diffMs = Date.now() - then.getTime();
  const sec = Math.floor(diffMs / 1000);
  if (sec < 60) return 'just now';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} minute${min === 1 ? '' : 's'} ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} hour${hr === 1 ? '' : 's'} ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} day${day === 1 ? '' : 's'} ago`;
  const mo = Math.floor(day / 30);
  if (mo < 12) return `${mo} month${mo === 1 ? '' : 's'} ago`;
  const yr = Math.floor(mo / 12);
  return `${yr} year${yr === 1 ? '' : 's'} ago`;
}

function deviceIcon(label) {
  if (/iOS|Android|iPhone|iPad/.test(label || '')) return Smartphone;
  return Monitor;
}

export default function DevicesSessionsCard() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyJti, setBusyJti] = useState(null); // jti currently being revoked
  const [revokingAll, setRevokingAll] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth('/auth/sessions');
      if (!res.ok) throw new Error(await getErrorMessage(res));
      const data = await res.json();
      setSessions(Array.isArray(data.sessions) ? data.sessions : []);
    } catch (err) {
      setError(err.message || 'Failed to load devices');
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const signOut = async (jti) => {
    setBusyJti(jti);
    try {
      const res = await fetchWithAuth(`/auth/sessions/${encodeURIComponent(jti)}`, { method: 'DELETE' });
      if (!res.ok) {
        throw new Error(await getErrorMessage(res));
      }
      toast.success('Signed out of that device');
      await load();
    } catch (err) {
      showError(toast, err, { operation: 'sign-out-device', page: 'Settings' });
    } finally {
      setBusyJti(null);
    }
  };

  const signOutEverywhereElse = async () => {
    setRevokingAll(true);
    setConfirmOpen(false);
    try {
      const res = await fetchWithAuth('/auth/sessions/revoke-all', { method: 'POST' });
      if (!res.ok) throw new Error(await getErrorMessage(res));
      const data = await res.json();
      const n = data.revoked_count || 0;
      toast.success(n > 0 ? `Signed out of ${n} other device${n === 1 ? '' : 's'}` : 'No other devices to sign out');
      await load();
    } catch (err) {
      showError(toast, err, { operation: 'sign-out-everywhere', page: 'Settings' });
    } finally {
      setRevokingAll(false);
    }
  };

  const otherCount = sessions.filter((s) => !s.is_current).length;

  return (
    <div className="flex items-center justify-between p-4 border border-navy/10" data-testid="devices-sessions-card">
      <div className="w-full">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-navy" />
            <p className="font-medium text-navy">Devices &amp; sessions</p>
          </div>
          {otherCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmOpen(true)}
              disabled={revokingAll}
              data-testid="sign-out-everywhere-btn"
            >
              <LogOut className="w-4 h-4 mr-2" />
              {revokingAll ? 'Signing out...' : 'Sign out everywhere else'}
            </Button>
          )}
        </div>

        {error && (
          <div
            className="mb-3 p-3 border border-red-300 bg-red-50 text-sm text-red-700"
            data-testid="sessions-error"
            role="alert"
          >
            {error}
            <button
              type="button"
              className="ml-2 underline"
              onClick={load}
              data-testid="sessions-retry"
            >
              Retry
            </button>
          </div>
        )}

        {loading && (
          <p className="text-sm text-muted-foreground" data-testid="sessions-loading">
            Loading your devices...
          </p>
        )}

        {!loading && !error && sessions.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="sessions-empty">
            No active sessions found.
          </p>
        )}

        {!loading && !error && sessions.length > 0 && (
          <ul className="space-y-2" data-testid="sessions-list">
            {sessions.map((s) => {
              const Icon = deviceIcon(s.device_label);
              return (
                <li
                  key={s.jti}
                  className="flex items-center justify-between p-3 border border-navy/10"
                  data-testid="session-row"
                >
                  <div className="flex items-start gap-3">
                    <Icon className="w-5 h-5 text-muted-foreground mt-0.5 flex-shrink-0" />
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-navy">{s.device_label}</p>
                        {s.is_current && (
                          <span
                            className="text-[10px] uppercase tracking-widest bg-success/10 text-success px-2 py-0.5 rounded"
                            data-testid="this-device-badge"
                          >
                            This device
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {s.ip ? `IP ${s.ip} - ` : ''}Active {relativeTime(s.last_seen_at)}
                      </p>
                    </div>
                  </div>
                  {!s.is_current && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => signOut(s.jti)}
                      disabled={busyJti === s.jti}
                      data-testid="sign-out-btn"
                      aria-label={`Sign out of ${s.device_label}`}
                    >
                      {busyJti === s.jti ? 'Signing out...' : 'Sign out'}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {/* Confirm dialog for "Sign out everywhere else" */}
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Sign out everywhere else?</DialogTitle>
              <DialogDescription>
                This will end all other active sessions except the one you are using right now.
                You will stay signed in on this device.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setConfirmOpen(false)}
                data-testid="confirm-cancel"
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={signOutEverywhereElse}
                disabled={revokingAll}
                data-testid="confirm-revoke-all"
              >
                {revokingAll ? 'Signing out...' : 'Sign out everywhere else'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
