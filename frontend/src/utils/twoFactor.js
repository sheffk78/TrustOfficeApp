// TrustOffice 2FA client helpers (TOTP two-factor authentication).
//
// API contract (see backend routers/auth_2fa.py -- do not invent endpoints):
//   POST /auth/2fa/enroll {password}  -> { secret, provisioning_uri }
//   POST /auth/2fa/verify {code}     -> { recovery_codes: [10] }
//   POST /auth/2fa/disable {totp_code, password} -> 200
//   GET  /auth/2fa/status            -> { enabled, recovery_codes_remaining, enforced }
//   POST /auth/login                 -> session OR 401 {detail:'2fa_required', challenge_token}
//   POST /auth/2fa/login {challenge_token, code} -> session response
//   Vault download / successor grant with 2FA enabled require header
//   X-2FA-Code, else 403 {detail:'2fa_stepup_required'}
//
// All requests go through fetchWithAuth (credentials + Bearer headers).
// The step-up header X-2FA-Code is attached by callers that already hold a
// code (after the user re-enters it in the step-up modal).

import { fetchWithAuth } from './api';

// Named predicate: did the API reject this login with a 2FA challenge?
export const is2faChallenge = (payload) =>
  Boolean(payload && payload.detail === '2fa_required' && payload.challenge_token);

// Named predicate: did the API reject this request with a step-up requirement?
// detail may be the bare string '2fa_stepup_required' or a FastAPI-style
// object { msg: '2fa_stepup_required' } depending on the error path.
export const isStepUpRequired = (detail) => {
  if (!detail) return false;
  if (typeof detail === 'string') return detail === '2fa_stepup_required';
  if (typeof detail === 'object') return detail.msg === '2fa_stepup_required' || detail.detail === '2fa_stepup_required';
  return false;
};

// GET /auth/2fa/status -> { enabled, recovery_codes_remaining, enforced }
export const get2faStatus = async () => {
  const response = await fetchWithAuth('/auth/2fa/status');
  if (!response.ok) {
    throw new Error(`Failed to load two-factor status (${response.status})`);
  }
  return response.json();
};

// POST /auth/2fa/enroll {password} -> { secret, provisioning_uri }
// The password re-authenticates the account before enrollment starts.
export const enroll2fa = async (password) => {
  const response = await fetchWithAuth('/auth/2fa/enroll', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to start two-factor enrollment (${response.status})`);
  }
  return response.json();
};

// POST /auth/2fa/verify {code} -> { recovery_codes: [...] }
export const verify2fa = async (code) => {
  const response = await fetchWithAuth('/auth/2fa/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Verification failed (${response.status})`);
  }
  return response.json();
};

// POST /auth/2fa/disable {totp_code, password} -> 200
export const disable2fa = async (totpCode, password) => {
  const response = await fetchWithAuth('/auth/2fa/disable', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ totp_code: totpCode, password }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to disable two-factor authentication (${response.status})`);
  }
  return true;
};

// POST /auth/2fa/login {challenge_token, code} -> normal session response
export const login2fa = async (challengeToken, code) => {
  const response = await fetch(`${process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app'}/api/auth/2fa/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ challenge_token: challengeToken, code }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `Verification failed (${response.status})`);
  }
  return body;
};

// The step-up retry path (403 2fa_stepup_required) retries the ORIGINAL
// request with the X-2FA-Code header set by the caller.
export const with2faHeader = (headers, code) => ({
  ...(headers || {}),
  'X-2FA-Code': code,
});