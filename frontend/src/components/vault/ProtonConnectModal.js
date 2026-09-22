import { useEffect, useRef, useState } from 'react';
import { X, ExternalLink, Loader2, ShieldCheck, CheckCircle2, AlertCircle } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';

/**
 * Proton Drive connect modal — session-fork flow.
 *
 * Member clicks "Connect Proton Drive" -> backend starts a fork session ->
 * we open Proton's own sign-in page in a new tab -> member signs in THERE
 * (password + 2FA never touch TrustOffice) -> this modal polls
 * /backup/proton/connect/status every 3s until complete/failed/expired.
 */
export default function ProtonConnectModal({ open, onClose, onConnected }) {
  const [phase, setPhase] = useState('idle'); // idle | ready | polling | complete | failed | expired
  const [signInUrl, setSignInUrl] = useState('');
  const pollRef = useRef(null);
  const tabRef = useRef(null);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  useEffect(() => () => stopPolling(), []); // cleanup on unmount

  if (!open) return null;

  const startConnect = async () => {
    try {
      const resp = await fetchWithAuth('/backup/proton/connect/start', { method: 'POST' });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        toast.error(data.detail || 'Could not start Proton connect.');
        return;
      }
      const { sign_in_url } = await resp.json();
      setSignInUrl(sign_in_url);
      setPhase('ready');
      tabRef.current = window.open(sign_in_url, '_blank', 'noopener');
      setTimeout(() => setPhase('polling'), 1000);
      startPolling();
    } catch {
      toast.error('Could not reach the backup service. Please try again.');
    }
  };

  const startPolling = () => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const resp = await fetchWithAuth('/backup/proton/connect/status', { method: 'POST' });
        if (resp.status === 404) { stopPolling(); setPhase('failed'); return; }
        if (!resp.ok) return; // transient — keep polling
        const { status } = await resp.json();
        if (status === 'complete') {
          stopPolling();
          setPhase('complete');
          toast.success('Proton Drive connected!');
          if (tabRef.current && !tabRef.current.closed) tabRef.current.close();
          setTimeout(() => { onConnected?.(); onClose?.(); }, 900);
        } else if (status === 'expired') {
          stopPolling();
          setPhase('expired');
        } else if (status === 'failed') {
          stopPolling();
          setPhase('failed');
        }
      } catch { /* transient network error — keep polling */ }
    }, 3000);
  };

  const close = () => { stopPolling(); onClose?.(); };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={close}>
      <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-navy" />
            <h3 className="text-lg font-semibold text-navy">Connect Proton Drive</h3>
          </div>
          <button onClick={close} className="text-gray-400 hover:text-gray-600" data-testid="proton-modal-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="text-sm text-gray-600 space-y-3 mb-5">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 mt-0.5 text-green-600 flex-shrink-0" />
            <span>You'll sign in on <strong>Proton's own page</strong> in a new tab. Your Proton password and 2FA code are never seen by TrustOffice.</span>
          </div>
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 mt-0.5 text-green-600 flex-shrink-0" />
            <span>TrustOffice receives a limited session that can <strong>only create files</strong> in a dedicated backup folder on your Proton Drive.</span>
          </div>
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 text-amber-500 flex-shrink-0" />
            <span>Files stored on Proton Drive are protected by Proton's end-to-end encryption. Weekly backups run automatically.</span>
          </div>
        </div>

        {phase === 'idle' && (
          <button onClick={startConnect} className="btn-primary w-full py-2.5" data-testid="proton-start-connect">
            Continue to Proton
          </button>
        )}

        {phase === 'ready' && (
          <div className="space-y-3">
            {!tabRef.current && (
              <a href={signInUrl} target="_blank" rel="noopener noreferrer" className="text-navy underline flex items-center gap-1 text-sm">
                Open Proton sign-in <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              Waiting for you to finish signing in at Proton...
            </div>
          </div>
        )}

        {phase === 'polling' && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            Waiting for you to finish signing in at Proton...
          </div>
        )}

        {phase === 'complete' && (
          <div className="flex items-center gap-2 text-sm text-green-600">
            <CheckCircle2 className="w-4 h-4" /> Connected! Setting things up...
          </div>
        )}

        {(phase === 'failed' || phase === 'expired') && (
          <div className="space-y-3">
            <div className="text-sm text-red-500">
              {phase === 'expired' ? 'Sign-in session expired.' : 'Proton sign-in did not complete.'}
            </div>
            <button onClick={() => { setPhase('idle'); startConnect(); }} className="btn-primary w-full py-2.5">
              Try again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
