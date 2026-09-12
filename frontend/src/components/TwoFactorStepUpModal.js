// TrustOffice 2FA step-up modal.
//
// Shown when a protected action (vault document download, successor-grant
// creation) is rejected with 403 {detail:'2fa_stepup_required'}. Asks for the
// current 6-digit code, retries the ORIGINAL request with the X-2FA-Code
// header. Users without 2FA never see this (only 2FA-enabled accounts get the
// step-up 403 from the backend).
//
// Lockout UX: when onSubmit rejects with 429 {detail:'2fa_rate_limited',
// retry_after, message}, the backend's message is shown verbatim and a visible
// countdown disables the submit button until it reaches zero. When an
// invalid-code reject carries attempts_remaining, that count is shown under
// the input. The backend's message field is the source of truth for copy.

import { useState, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Shield, AlertCircle, Loader2 } from 'lucide-react';
import { get2faRateLimitMessage, get2faAttemptsRemaining } from '@/utils/twoFactor';
import { use2faLockout, formatLockout } from '@/hooks/use2faLockout';

export default function TwoFactorStepUpModal({ open, onSubmit, onCancel }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [attemptsLeft, setAttemptsLeft] = useState(null);
  const lockout = use2faLockout();

  // Reset transient state whenever the modal (re)opens.
  useEffect(() => {
    if (open) {
      setError('');
      setAttemptsLeft(null);
      lockout.clear();
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting || lockout.active) return;
    const trimmed = code.trim();
    if (!trimmed) {
      setError('Enter the 6-digit code from your authenticator app.');
      return;
    }
    setError('');
    setAttemptsLeft(null);
    setSubmitting(true);
    try {
      await onSubmit(trimmed);
      // Success: parent closes the modal; clear local state for next time.
      setCode('');
      setError('');
    } catch (err) {
      const rateMsg = get2faRateLimitMessage(err);
      const remaining = get2faAttemptsRemaining(err);
      if (rateMsg) {
        const retryAfter = Number(err?.body?.retry_after || err?.payload?.retry_after || 0);
        lockout.trigger(retryAfter);
        setError(rateMsg);
      } else {
        setError(err?.message || 'That code did not work. Please try again.');
      }
      setAttemptsLeft(remaining);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy/60"
      data-testid="twofa-stepup-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Two-factor verification required"
    >
      <div className="bg-white w-[92vw] max-w-md p-6 rounded-lg shadow-xl">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="w-5 h-5 text-navy" />
          <h2 className="font-serif text-xl text-navy">Two-factor verification required</h2>
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          This action is protected by two-factor authentication.
          Open your authenticator app and enter the 6-digit code it shows to continue.
        </p>
        <form onSubmit={handleSubmit}>
          <Input
            autoFocus
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="123456"
            maxLength={9}
            value={code}
            onChange={(e) => { setCode(e.target.value); if (error) setError(''); }}
            aria-label="6-digit authentication code"
            data-testid="stepup-code-input"
            disabled={lockout.active}
          />
          {error && (
            <p className="text-xs text-error mt-2 flex items-center gap-1" data-testid="stepup-error" role="alert">
              <AlertCircle className="w-3 h-3" />
              {error}
            </p>
          )}
          {lockout.active && (
            <p className="text-xs text-navy mt-2 flex items-center gap-1" data-testid="stepup-countdown" role="status">
              <AlertCircle className="w-3 h-3" />
              You can try again in {formatLockout(lockout.secondsLeft)}
            </p>
          )}
          {attemptsLeft != null && (
            <p className="text-xs text-muted-foreground mt-2" data-testid="stepup-attempts-left">
              {attemptsLeft} attempts left before a short cooldown
            </p>
          )}
          <div className="flex justify-end gap-2 mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => { setCode(''); setError(''); onCancel(); }}
              disabled={submitting || lockout.active}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || lockout.active} data-testid="stepup-submit-btn">
              {submitting ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" /> Verifying...
                </span>
              ) : 'Verify'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
