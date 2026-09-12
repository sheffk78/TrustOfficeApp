// use2faLockout -- drives the rate-limit countdown shown on 2FA code-entry
// surfaces when the backend rejects a request with 429
// {detail:'2fa_rate_limited', retry_after, message}.
//
// The caller triggers the lockout with the backend's retry_after (seconds);
// the hook counts down once per second and reports whether the submit button
// should stay disabled. Fake timers in tests drive the same path.

import { useEffect, useState } from 'react';

// Format a remaining-seconds value for display. <= 60s shows plain seconds
// (e.g. "45s"); above that shows m:ss (e.g. "4:32") per the UX contract.
export function formatLockout(secondsLeft) {
  const s = Math.max(0, Math.floor(Number(secondsLeft) || 0));
  if (s <= 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, '0')}`;
}

export function use2faLockout() {
  const [lockoutUntil, setLockoutUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!lockoutUntil) return undefined;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [lockoutUntil]);

  // Start (or restart) the countdown from the backend's retry_after seconds.
  const trigger = (retryAfterSeconds) => {
    const secs = Number(retryAfterSeconds) || 0;
    setNow(Date.now());
    setLockoutUntil(Date.now() + secs * 1000);
  };

  const clear = () => setLockoutUntil(0);

  const active = lockoutUntil > now;
  const secondsLeft = Math.max(0, Math.ceil((lockoutUntil - now) / 1000));

  return { active, secondsLeft, trigger, clear, lockoutUntil };
}
