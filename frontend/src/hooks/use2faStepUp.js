// use2faStepUp -- wraps protected fetch calls with the 2FA step-up flow.
//
// Usage:
//   const { stepUpOpen, runWithStepUp, handleStepUpSubmit, closeStepUp } = use2faStepUp();
//   const res = await runWithStepUp((headers) => fetchWithAuth('/vault/documents/x/download', { headers }));
//
// When the request comes back 403 {detail:'2fa_stepup_required'}, the modal
// opens; on submit the ORIGINAL request is replayed once with the X-2FA-Code
// header set to the entered code. Users without 2FA never trigger this (the
// backend only sends 2fa_stepup_required to 2FA-enabled accounts).

import { useCallback, useState } from 'react';
import { isStepUpRequired } from '@/utils/twoFactor';
import TwoFactorStepUpModal from '@/components/TwoFactorStepUpModal';

export default function use2faStepUp() {
  const [stepUpOpen, setStepUpOpen] = useState(false);
  const [pendingRequest, setPendingRequest] = useState(null);
  const [resolveStepUp, setResolveStepUp] = useState(null);

  const runWithStepUp = useCallback((doRequest) => {
    let settled = false;
    return new Promise((resolve, reject) => {
      const attempt = async (extraCode) => {
        try {
          const headers = extraCode ? { 'X-2FA-Code': extraCode } : undefined;
          const response = await doRequest(headers);
          if (response && response.status === 403) {
            const body = await response.clone().json().catch(() => ({}));
            if (isStepUpRequired(body.detail)) {
              // Park the request; the modal collects a fresh code and replays it.
              setPendingRequest(() => attempt);
              setResolveStepUp(() => ({ resolve, reject }));
              setStepUpOpen(true);
              return;
            }
          }
          if (!settled) { settled = true; resolve(response); }
        } catch (err) {
          if (!settled) { settled = true; reject(err); }
        }
      };
      attempt(null);
    });
  }, []);

  const handleStepUpSubmit = useCallback(async (code) => {
    if (!pendingRequest) return;
    const replay = pendingRequest;
    const resolvers = resolveStepUp;
    // Close the modal UI state first; the replay decides the outcome.
    setStepUpOpen(false);
    setPendingRequest(null);
    setResolveStepUp(null);
    const response = await replay(code);
    if (resolvers) resolvers.resolve(response);
  }, [pendingRequest, resolveStepUp]);

  const closeStepUp = useCallback(() => {
    setStepUpOpen(false);
    setPendingRequest(null);
    setResolveStepUp(null);
  }, []);

  return { stepUpOpen, runWithStepUp, handleStepUpSubmit, closeStepUp, TwoFactorStepUpModal };
}