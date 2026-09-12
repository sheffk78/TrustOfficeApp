// TwoFactorCard -- the real 2FA management card on the Settings Account tab.
// Replaces the old "Not Enabled" placeholder.
//
// Audience note: our users skew 55+ and non-technical. Every step says
// exactly what to do in plain language, with manual-entry fallbacks.
//
// States:
//   disabled    -> Enable + password confirm starts enrollment
//                  (POST /auth/2fa/enroll {password}), 3-step plain-language
//                  guide + QR + manual setup key, 6-digit code entry,
//                  POST /auth/2fa/verify.
//   recovery    -> 10 single-use recovery codes shown ONCE with print/download
//                  and an "I have saved them" confirm.
//   enabled     -> status + remaining recovery count + Disable flow
//                  (authenticator code + account password -> /auth/2fa/disable).

import { useState, useEffect } from 'react';
import { QRCodeCanvas } from 'qrcode.react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import { get2faStatus, enroll2fa, verify2fa, disable2fa, get2faRateLimitMessage, get2faAttemptsRemaining } from '@/utils/twoFactor';
import { use2faLockout, formatLockout } from '@/hooks/use2faLockout';
import {
  Shield, Copy, Check, Loader2, AlertCircle, KeyRound, Printer, Download,
} from 'lucide-react';

// Exact copy from the council review delta -- do not paraphrase.
const ENROLLMENT_GUIDE_STEPS = [
  '1. Install an authenticator app (Google Authenticator, Microsoft Authenticator, or 1Password) on your phone.',
  '2. Open it and tap + to add an account.',
  '3. Point your phone camera at this code.',
];
const CANT_SCAN_LABEL = "Can't scan? Enter this code manually";
const RECOVERY_WARNING = 'Do not save these codes on the same device as your authenticator app. Print them or store them somewhere safe and separate.';

export default function TwoFactorCard() {
  // status: null = loading, otherwise { enabled, recovery_codes_remaining, enforced }
  const [status, setStatus] = useState(null);
  const [loadFailed, setLoadFailed] = useState(false);

  // Enrollment flow state
  const [stage, setStage] = useState('idle'); // idle | password | enrolling | verifying | recovery | disabling
  const [enrollPassword, setEnrollPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [secret, setSecret] = useState('');
  const [provisioningUri, setProvisioningUri] = useState('');
  const [code, setCode] = useState('');
  const [verifyError, setVerifyError] = useState('');
  const [verifyAttemptsLeft, setVerifyAttemptsLeft] = useState(null);
  const verifyLockout = use2faLockout();
  const [recoveryCodes, setRecoveryCodes] = useState([]);

  // Disable flow state
  const [disableCode, setDisableCode] = useState('');
  const [disablePassword, setDisablePassword] = useState('');
  const [disableError, setDisableError] = useState('');

  // Copy-button feedback
  const [copiedUri, setCopiedUri] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);
  const [copiedCodes, setCopiedCodes] = useState(false);

  const loadStatus = async () => {
    try {
      const data = await get2faStatus();
      setStatus(data);
      setLoadFailed(false);
    } catch (err) {
      setLoadFailed(true);
      console.error('Failed to load 2FA status:', err);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const copyText = async (text, which) => {
    try {
      await navigator.clipboard.writeText(text);
      if (which === 'uri') { setCopiedUri(true); setTimeout(() => setCopiedUri(false), 2500); }
      if (which === 'secret') { setCopiedSecret(true); setTimeout(() => setCopiedSecret(false), 2500); }
      if (which === 'codes') { setCopiedCodes(true); setTimeout(() => setCopiedCodes(false), 2500); }
      toast.success('Copied to clipboard');
    } catch (err) {
      showError(toast, err, { operation: 'copy', page: 'Settings' });
    }
  };

  const startEnrollment = async (e) => {
    e.preventDefault();
    if (stage !== 'password') return;
    if (!enrollPassword) {
      setPasswordError('Enter your account password to confirm it is you.');
      return;
    }
    setPasswordError('');
    setStage('enrolling');
    try {
      const data = await enroll2fa(enrollPassword);
      setSecret(data.secret || '');
      setProvisioningUri(data.provisioning_uri || '');
      setStage('verifying');
    } catch (err) {
      const msg = err?.message || '';
      if (msg.includes('401') || msg.toLowerCase().includes('password')) {
        // Wrong password: let the user retry without leaving the flow.
        setStage('password');
        setPasswordError('That password was not correct. Please try again.');
      } else {
        setStage('idle');
        showError(toast, err, { operation: '2fa_enroll', page: 'Settings' });
      }
    } finally {
      setEnrollPassword('');
    }
  };

  const handleVerify = async (e) => {
    e.preventDefault();
    if (stage !== 'verifying') return;
    const trimmed = code.trim();
    if (!trimmed) {
      setVerifyError('Enter the 6-digit code from your authenticator app.');
      return;
    }
    setVerifyError('');
    setVerifyAttemptsLeft(null);
    try {
      const data = await verify2fa(trimmed);
      setRecoveryCodes(data.recovery_codes || []);
      setStage('recovery');
    } catch (err) {
      // Wrong code or transient failure: keep the QR on screen, show inline
      // error, let the user retry with a fresh code.
      const rateMsg = get2faRateLimitMessage(err);
      const attemptsLeft = get2faAttemptsRemaining(err);
      if (rateMsg) {
        const retryAfter = Number(err?.body?.retry_after || err?.payload?.retry_after || 0);
        verifyLockout.trigger(retryAfter);
        setVerifyError(rateMsg);
      } else {
        setVerifyError(err?.message || 'That code was not valid. Please try again.');
      }
      setVerifyAttemptsLeft(attemptsLeft);
    }
  };

  // Print the recovery codes in a new window (plain, large-type list).
  const printRecoveryCodes = () => {
    const win = window.open('', '_blank', 'width=640,height=800');
    if (!win) {
      toast.error('Your browser blocked the print window. Use Download instead.');
      return;
    }
    const list = recoveryCodes.map((c) => `<li style="font-family:monospace;font-size:16pt;margin:8px 0;">${c}</li>`).join('');
    win.document.write(
      `<html><head><title>TrustOffice recovery codes</title></head>` +
      `<body style="font-family:Georgia,serif;padding:32px;">` +
      `<h1 style="font-size:20pt;">Your TrustOffice recovery codes</h1>` +
      `<p>Each code works once, if you lose your device.</p>` +
      `<p><strong>${RECOVERY_WARNING}</strong></p>` +
      `<ol>${list}</ol>` +
      `</body></html>`
    );
    win.document.close();
    win.focus();
    win.print();
  };

  // Download the recovery codes as a plain text file.
  const downloadRecoveryCodes = () => {
    const text = [
      'Your TrustOffice recovery codes',
      'Each code works once, if you lose your device.',
      RECOVERY_WARNING,
      '',
      ...recoveryCodes,
    ].join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'trustoffice-recovery-codes.txt';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };

  const handleConfirmSaved = async () => {
    setStage('idle');
    setRecoveryCodes([]);
    setSecret('');
    setProvisioningUri('');
    setCode('');
    await loadStatus();
    toast.success('Two-factor authentication is now enabled');
  };

  const handleDisable = async (e) => {
    e.preventDefault();
    if (stage !== 'disabling') return;
    const trimmedCode = disableCode.trim();
    if (!trimmedCode) {
      setDisableError('Enter the current 6-digit code from your authenticator app.');
      return;
    }
    if (!disablePassword) {
      setDisableError('Enter your account password to confirm.');
      return;
    }
    setDisableError('');
    try {
      await disable2fa(trimmedCode, disablePassword);
      setStage('idle');
      setDisableCode('');
      setDisablePassword('');
      await loadStatus();
      toast.success('Two-factor authentication has been disabled');
    } catch (err) {
      setDisableError(err?.message || 'Could not disable two-factor authentication. Please try again.');
    }
  };

  // ---------------------------------------------------------------- loading
  if (status === null && !loadFailed) {
    return (
      <div className="flex items-center justify-between p-4 border border-navy/10" data-testid="twofa-card">
        <div>
          <p className="font-medium text-navy">Two-Factor Authentication</p>
          <p className="text-sm text-muted-foreground">Checking status...</p>
        </div>
        <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // ---------------------------------------------------------------- error
  if (loadFailed) {
    return (
      <div className="p-4 border border-navy/10" data-testid="twofa-card">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-4 h-4 text-error mt-1 flex-shrink-0" />
          <div className="flex-1">
            <p className="font-medium text-navy">Two-Factor Authentication</p>
            <p className="text-sm text-muted-foreground mt-1">
              We could not load your two-factor status. Please refresh the page or try again later.
            </p>
            <Button variant="outline" size="sm" className="mt-3" onClick={loadStatus}>
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const enabled = Boolean(status?.enabled);
  const enforced = Boolean(status?.enforced);
  const remaining = typeof status?.recovery_codes_remaining === 'number' ? status.recovery_codes_remaining : null;

  // ---------------------------------------------------------------- disabled / enrolling / verifying / recovery
  if (!enabled) {
    return (
      <div className="p-4 border border-navy/10" data-testid="twofa-card">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-medium text-navy">Two-Factor Authentication</p>
            <p className="text-sm text-muted-foreground mt-1">
              Add an extra layer of security to your account with TOTP authentication.
              {enforced && ' Two-factor authentication is required for admin accounts.'}
            </p>
          </div>
          <span className="font-mono text-xs uppercase tracking-widest text-muted-foreground flex-shrink-0 mt-1">
            Not Enabled
          </span>
        </div>

        {(stage === 'idle') && (
          <div className="mt-4">
            <Button onClick={() => { setStage('password'); setPasswordError(''); }} data-testid="twofa-enable-btn">
              <Shield className="w-4 h-4 mr-2" />
              Enable
            </Button>
          </div>
        )}

        {stage === 'password' && (
          <form onSubmit={startEnrollment} className="mt-4 space-y-3" data-testid="twofa-password-step">
            <p className="text-sm text-muted-foreground">
              First, confirm it is you. Enter your account password to start setting up two-factor authentication.
            </p>
            <Input
              type="password"
              autoComplete="current-password"
              placeholder="Account password"
              className="max-w-[280px]"
              value={enrollPassword}
              onChange={(e) => { setEnrollPassword(e.target.value); if (passwordError) setPasswordError(''); }}
              aria-label="Account password"
              data-testid="twofa-enroll-password-input"
            />
            {passwordError && (
              <p className="text-xs text-error" data-testid="twofa-enroll-password-error" role="alert">{passwordError}</p>
            )}
            <div className="flex gap-2">
              <Button type="submit" data-testid="twofa-enroll-start-btn">Continue</Button>
              <Button type="button" variant="ghost" onClick={() => { setStage('idle'); setEnrollPassword(''); }}>
                Cancel
              </Button>
            </div>
          </form>
        )}

        {stage === 'enrolling' && (
          <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground" data-testid="twofa-enroll-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Starting enrollment...
          </div>
        )}

        {stage === 'verifying' && (
          <div className="mt-6" data-testid="twofa-qr-step">
            {/* Plain-language 3-step guide (55+ friendly, exact council copy) */}
            <ol className="space-y-1 mb-4 text-sm text-navy" data-testid="twofa-enroll-guide">
              {ENROLLMENT_GUIDE_STEPS.map((step) => (
                <li key={step} className="leading-relaxed">{step}</li>
              ))}
            </ol>

            <div className="flex flex-col sm:flex-row gap-6 items-start">
              <div className="p-3 bg-white border border-navy/10">
                <QRCodeCanvas value={provisioningUri} size={148} marginSize={1} data-testid="twofa-qr" />
              </div>
              <div className="flex-1 w-full space-y-3">
                <div>
                  <p className="text-sm font-medium text-navy" data-testid="twofa-cant-scan-label">{CANT_SCAN_LABEL}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <code className="text-sm text-navy bg-navy/5 px-2 py-1 break-all" data-testid="twofa-secret">{secret}</code>
                    <button
                      type="button"
                      onClick={() => copyText(secret, 'secret')}
                      className="text-muted-foreground hover:text-navy"
                      aria-label="Copy setup code"
                    >
                      {copiedSecret ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    In your authenticator app, choose "Enter a setup key" instead of scanning, then paste this code.
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Provisioning URI</p>
                  <div className="flex items-center gap-2 mt-1">
                    <code className="text-[10px] text-muted-foreground bg-navy/5 px-2 py-1 break-all max-w-full" data-testid="twofa-uri">{provisioningUri}</code>
                    <button
                      type="button"
                      onClick={() => copyText(provisioningUri, 'uri')}
                      className="text-muted-foreground hover:text-navy"
                      aria-label="Copy provisioning URI"
                    >
                      {copiedUri ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <p className="text-sm text-navy font-medium mt-6 mb-2">Next: enter the 6-digit code your app shows</p>
            <form onSubmit={handleVerify} className="space-y-3">
              <Input
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
                maxLength={9}
                className="max-w-[200px]"
                value={code}
                onChange={(e) => { setCode(e.target.value); if (verifyError) setVerifyError(''); }}
                aria-label="6-digit authentication code"
                data-testid="twofa-verify-code-input"
              />
              {verifyError && (
                <p className="text-xs text-error" data-testid="twofa-verify-error" role="alert">{verifyError}</p>
              )}
              {verifyLockout.active && (
                <p className="text-xs text-navy mt-2" data-testid="twofa-verify-countdown" role="status">
                  You can try again in {formatLockout(verifyLockout.secondsLeft)}
                </p>
              )}
              {verifyAttemptsLeft != null && (
                <p className="text-xs text-muted-foreground mt-2" data-testid="twofa-verify-attempts-left">
                  {verifyAttemptsLeft} attempts left before a short cooldown
                </p>
              )}
              <div>
                <Button type="submit" data-testid="twofa-verify-btn" disabled={verifyLockout.active}>Verify and Enable</Button>
              </div>
            </form>
          </div>
        )}

        {stage === 'recovery' && (
          <div className="mt-6" data-testid="twofa-recovery-step">
            <p className="text-sm text-navy font-medium flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-gold" />
              Save your recovery codes now. This is the only time they are shown.
            </p>
            <p className="text-xs text-muted-foreground mt-1 mb-3">
              Each code works once if you lose your device.
            </p>
            <div className="bg-navy/5 p-4 grid grid-cols-2 gap-2" data-testid="twofa-recovery-codes">
              {recoveryCodes.map((c) => (
                <code key={c} className="text-sm text-navy">{c}</code>
              ))}
            </div>
            <p className="text-sm text-error mt-3" data-testid="twofa-recovery-warning">
              {RECOVERY_WARNING}
            </p>
            <div className="flex flex-wrap items-center gap-3 mt-4">
              <Button variant="outline" size="sm" onClick={printRecoveryCodes} data-testid="twofa-print-codes-btn">
                <Printer className="w-4 h-4" /> Print
              </Button>
              <Button variant="outline" size="sm" onClick={downloadRecoveryCodes} data-testid="twofa-download-codes-btn">
                <Download className="w-4 h-4" /> Download
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => copyText(recoveryCodes.join('\n'), 'codes')}
                data-testid="twofa-copy-codes-btn"
              >
                {copiedCodes ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
                Copy codes
              </Button>
              <Button onClick={handleConfirmSaved} data-testid="twofa-saved-codes-btn">
                I have saved them
              </Button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------- enabled
  return (
    <div className="p-4 border border-navy/10" data-testid="twofa-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-medium text-navy">Two-Factor Authentication</p>
          <p className="text-sm text-muted-foreground mt-1">
            Your account is protected with TOTP two-factor authentication.
          </p>
          {remaining !== null && (
            <p className="text-sm text-navy mt-1" data-testid="twofa-recovery-remaining">
              Recovery codes remaining: {remaining}
            </p>
          )}
        </div>
        <span className="font-mono text-xs uppercase tracking-widest text-success flex-shrink-0 mt-1" data-testid="twofa-enabled-badge">
          Enabled
        </span>
      </div>

      {stage === 'idle' && (
        <div className="mt-4">
          <Button
            variant="outline"
            onClick={() => { setStage('disabling'); setDisableError(''); }}
            data-testid="twofa-disable-btn"
          >
            Disable
          </Button>
        </div>
      )}

      {stage === 'disabling' && (
        <form onSubmit={handleDisable} className="mt-4 space-y-3" data-testid="twofa-disable-form">
          <div>
            <label className="text-xs text-muted-foreground" htmlFor="twofa-disable-code">Current authenticator code</label>
            <Input
              id="twofa-disable-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="123456"
              maxLength={9}
              className="max-w-[200px]"
              value={disableCode}
              onChange={(e) => { setDisableCode(e.target.value); if (disableError) setDisableError(''); }}
              data-testid="twofa-disable-code-input"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground" htmlFor="twofa-disable-password">Account password</label>
            <Input
              id="twofa-disable-password"
              type="password"
              autoComplete="current-password"
              className="max-w-[280px]"
              value={disablePassword}
              onChange={(e) => { setDisablePassword(e.target.value); if (disableError) setDisableError(''); }}
              data-testid="twofa-disable-password-input"
            />
          </div>
          {disableError && (
            <p className="text-xs text-error" data-testid="twofa-disable-error" role="alert">{disableError}</p>
          )}
          <div className="flex gap-2">
            <Button type="submit" data-testid="twofa-disable-confirm-btn">Disable two-factor</Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => { setStage('idle'); setDisableCode(''); setDisablePassword(''); setDisableError(''); }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}