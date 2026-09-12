// use2faEnrollmentNag -- drives the dismissible "enable 2FA" banner shown to
// EVERY non-enrolled user (not just admins), per Jeff's directive.
//
// Rules (enforced by the pure shouldShowEnrollmentNag below so they can be
// unit-tested without React):
//   - Never show to users whose 2FA status reports enabled.
//   - Admin enforcement nag keeps priority (caller passes adminNagShown).
//   - After dismissal, hide for 7 days (localStorage timestamp), then
//     resurface once.
//   - Never show twice in the same session after dismissal (ref guard).
//
// 2FA status is fetched the same way the existing admin nag does (get2faStatus
// from @/utils/twoFactor).

import { useEffect, useRef, useState } from 'react';
import { get2faStatus } from '@/utils/twoFactor';

export const TWOFA_NAG_DISMISSED_KEY = 'twofa_nag_dismissed_at';
const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

export function shouldShowEnrollmentNag({
  enabled,
  enforced,
  dismissedAt,
  now,
  sessionDismissed,
  adminNagShown,
}) {
  if (enabled) return false; // never to enrolled users
  if (adminNagShown) return false; // admin enforcement nag wins
  if (sessionDismissed) return false; // never twice in one session
  if (dismissedAt == null) return true; // first time: show
  return now - dismissedAt >= SEVEN_DAYS_MS; // resurface once after 7 days
}

export function useTwoFactorEnrollmentNag(adminNagShown = false) {
  const [visible, setVisible] = useState(false);
  const sessionDismissedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    get2faStatus()
      .then((status) => {
        if (cancelled) return;
        const enabled = Boolean(status?.enabled);
        const enforced = Boolean(status?.enforced);
        const raw = localStorage.getItem(TWOFA_NAG_DISMISSED_KEY);
        const dismissedAt = raw != null ? Number(raw) : null;
        setVisible(
          shouldShowEnrollmentNag({
            enabled,
            enforced,
            dismissedAt,
            now: Date.now(),
            sessionDismissed: sessionDismissedRef.current,
            adminNagShown,
          })
        );
      })
      .catch(() => {
        // No 2FA status available (or not logged in): never show the nag.
      });
    return () => {
      cancelled = true;
    };
  }, [adminNagShown]);

  const dismiss = () => {
    localStorage.setItem(TWOFA_NAG_DISMISSED_KEY, String(Date.now()));
    sessionDismissedRef.current = true;
    setVisible(false);
  };

  return { visible, dismiss };
}
