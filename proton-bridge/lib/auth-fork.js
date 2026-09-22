import { FORK_POLL_INTERVAL_MS, FORK_INITIAL_DELAY_MS, FORK_MAX_POLL_TIME_MS, AUTH_CLIENT_ID, PROTON_ACCOUNT_URL } from './constants.js';
import { AccountApiError } from './account-api.js';

/**
 * Session-fork authentication — the whole reason members never type their
 * Proton password on TrustOffice:
 *
 *   1. Bridge asks Proton for a fork attempt  → { Selector, UserCode }.
 *   2. Bridge builds a sign-in URL on account.proton.me carrying a random
 *      32-byte AES-GCM key. The MEMBER opens it and signs in on Proton's
 *      own page (password, 2FA, whatever Proton requires).
 *   3. Bridge polls the fork status; when Proton approves the fork it
 *      returns an encrypted payload containing { UID, AccessToken,
 *      RefreshToken, keyPassword }. We decrypt with the key we generated.
 *
 * The bridge never sees the Proton password or a TOTP code.
 */
export function generateSignInUrl(userCode) {
  const encryptionKey = crypto.getRandomValues(new Uint8Array(32));
  const base64EncodedKey = uint8ArrayToBase64(encryptionKey);
  const payload = `0:${userCode}:${base64EncodedKey}:${AUTH_CLIENT_ID}`;
  const signInUrl = `${PROTON_ACCOUNT_URL}/desktop/login?app=drive&pv=3#payload=${encodeURIComponent(payload)}`;
  return { encryptionKey, signInUrl };
}

export async function completeFork(accountApi, selector, encryptionKey, signal) {
  const startTime = Date.now();
  await sleep(FORK_INITIAL_DELAY_MS, signal);

  while (true) {
    if (Date.now() - startTime > FORK_MAX_POLL_TIME_MS) {
      throw new Error('Proton sign-in timed out (10 minutes). Please try again.');
    }

    let response;
    try {
      response = await accountApi.sessionForksStatus(selector);
    } catch (error) {
      if (error instanceof AccountApiError && error.httpCode === 422) {
        await sleep(FORK_POLL_INTERVAL_MS, signal);
        continue;
      }
      throw error;
    }

    const userKeyPassword = await parseUserKeyPassword(encryptionKey, response.Payload);
    const session = {
      uid: response.UID,
      accessToken: response.AccessToken,
      refreshToken: response.RefreshToken,
    };
    return { session, userKeyPassword };
  }
}

export async function parseUserKeyPassword(encryptionKey, encryptedPayload) {
  const decryptedPayload = await decryptForkPayload(encryptedPayload, encryptionKey);
  return parseForkUserKeyPassword(decryptedPayload);
}

const FORK_AAD = new TextEncoder().encode('fork');
const GCM_NONCE_LENGTH = 12;
const GCM_TAG_LENGTH = 16;

async function decryptForkPayload(encodedPayload, encryptionKey) {
  const blob = base64ToUint8Array(encodedPayload);
  if (blob.length < GCM_NONCE_LENGTH + GCM_TAG_LENGTH) {
    throw new Error('Invalid fork payload blob length');
  }

  const nonce = blob.subarray(0, GCM_NONCE_LENGTH);
  const tag = blob.subarray(blob.length - GCM_TAG_LENGTH);
  const ciphertext = blob.subarray(GCM_NONCE_LENGTH, blob.length - GCM_TAG_LENGTH);

  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    toArrayBuffer(encryptionKey),
    { name: 'AES-GCM' },
    false,
    ['decrypt'],
  );

  let plaintext;
  try {
    plaintext = await crypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: toArrayBuffer(nonce),
        additionalData: toArrayBuffer(FORK_AAD),
        tagLength: GCM_TAG_LENGTH * 8,
      },
      cryptoKey,
      toArrayBuffer(concatUint8Arrays(ciphertext, tag)),
    );
  } catch (error) {
    throw new Error(`Fork payload decryption failed: ${error.message}`);
  }

  return new TextDecoder().decode(plaintext);
}

function parseForkUserKeyPassword(decryptedPayloadJson) {
  const payload = JSON.parse(decryptedPayloadJson);
  const keyPassword = payload.keyPassword;
  if (typeof keyPassword !== 'string') {
    throw new Error('Failed to deserialize the fork payload');
  }
  return keyPassword;
}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    if (signal) {
      signal.addEventListener(
        'abort',
        () => {
          clearTimeout(t);
          reject(new Error('Aborted'));
        },
        { once: true },
      );
    }
  });
}

function uint8ArrayToBase64(bytes) {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToUint8Array(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function concatUint8Arrays(...arrays) {
  const totalLength = arrays.reduce((sum, array) => sum + array.length, 0);
  const result = new Uint8Array(totalLength);
  let offset = 0;
  for (const array of arrays) {
    result.set(array, offset);
    offset += array.length;
  }
  return result;
}

function toArrayBuffer(bytes) {
  const { buffer, byteOffset, byteLength } = bytes;
  if (buffer instanceof ArrayBuffer) {
    return buffer.slice(byteOffset, byteOffset + byteLength);
  }
  return bytes.slice().buffer;
}