import { DEFAULT_REQUEST_TIMEOUT_MS, APP_VERSION, SDK_VERSION_STRING, BASE_URL } from './constants.js';

/**
 * Node-native HTTP layer for the Proton core/account API.
 * Implements the same contract as the reference integration's ApiClient:
 * sets x-pm-appversion + x-pm-drive-sdk-version, attaches session tokens,
 * transparently refreshes access tokens on 401 (single-flight).
 * Uses global fetch (Node >= 18).
 */
export class ApiClient {
  constructor(credentials, baseUrl = BASE_URL) {
    this.credentials = credentials;
    this.baseUrlWithProtocol = /^https?:\/\//.test(baseUrl) ? baseUrl : `https://${baseUrl}`;
    this.activeRefreshPromise = null;
  }

  async authenticatedRequest(url, options = {}) {
    const response = await this._request(url, options, true);
    if (response.status !== 401 || shouldSkipAuthRefreshForUrl(url)) {
      return response;
    }
    const refreshed = await this.refreshSessionIfPossible();
    if (!refreshed) {
      return response;
    }
    return this._request(url, options, true);
  }

  async unauthenticatedRequest(url, options = {}) {
    return this._request(url, options, false);
  }

  async _request(url, options, authenticated) {
    const timeoutMs = options.timeout ?? DEFAULT_REQUEST_TIMEOUT_MS;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new Error('Request timed out')), timeoutMs);

    if (options.signal?.aborted) {
      clearTimeout(timer);
      throw options.signal.reason instanceof Error ? options.signal.reason : new Error('Aborted');
    }
    if (options.signal) {
      options.signal.addEventListener('abort', () => controller.abort(options.signal.reason), { once: true });
    }

    const headers = new Headers(options.headers || {});
    headers.set('x-pm-appversion', APP_VERSION);
    if (SDK_VERSION_STRING) {
      headers.set('x-pm-drive-sdk-version', SDK_VERSION_STRING);
    }
    headers.set('Accept', 'application/json');
    if (!headers.has('User-Agent')) {
      headers.set('User-Agent', 'TrustOffice-ProtonBridge/0.1.0');
    }

    if (authenticated) {
      if (this.credentials.uid) headers.set('x-pm-uid', this.credentials.uid);
      if (this.credentials.accessToken) headers.set('Authorization', `Bearer ${this.credentials.accessToken}`);
    }

    let body = options.body;
    if (options.json !== undefined) {
      headers.set('Content-Type', 'application/json');
      body = JSON.stringify(options.json);
    }

    const urlWithParams = appendSearchParams(url, options.searchParams);
    try {
      const response = await fetch(urlWithParams, {
        method: options.method || 'GET',
        headers,
        body,
        signal: controller.signal,
        redirect: 'error',
      });
      const headersOut = {};
      response.headers.forEach((v, k) => { headersOut[k] = v; });
      const arrayBuffer = await response.arrayBuffer();
      return { status: response.status, headers: headersOut, arrayBuffer, ok: response.ok };
    } finally {
      clearTimeout(timer);
    }
  }

  async refreshSessionIfPossible() {
    this.activeRefreshPromise ??= this._performTokenRefresh().finally(() => {
      this.activeRefreshPromise = null;
    });
    return this.activeRefreshPromise;
  }

  async _performTokenRefresh() {
    const refreshToken = this.credentials.refreshToken;
    if (!refreshToken) return false;

    const response = await this.unauthenticatedRequest(
      `${this.baseUrlWithProtocol}/auth/v4/refresh`,
      {
        method: 'POST',
        json: {
          ResponseType: 'token',
          GrantType: 'refresh_token',
          RefreshToken: refreshToken,
        },
      },
    );

    if (!isOkStatus(response.status)) {
      if (response.status >= 400 && response.status < 500 && response.status !== 429) {
        await this.credentials.signOut('refresh_rejected');
      }
      return false;
    }

    const data = parseJsonBody(response);
    const uid = data.UID ?? this.credentials.uid;
    const accessToken = data.AccessToken;
    if (!uid || !accessToken) return false;

    await this.credentials.setSessionInfo({
      uid,
      accessToken,
      refreshToken: data.RefreshToken ?? refreshToken,
    });
    return true;
  }
}

function shouldSkipAuthRefreshForUrl(url) {
  let pathname;
  try {
    pathname = new URL(url).pathname.toLowerCase();
  } catch {
    pathname = url.toLowerCase();
  }
  return (
    pathname.includes('/auth/v4/refresh') ||
    pathname.includes('/auth/v4/sessions') ||
    pathname.includes('/core/v4/auth')
  );
}

function isOkStatus(status) {
  return status >= 200 && status < 300;
}

function parseJsonBody(response) {
  const text = new TextDecoder().decode(response.arrayBuffer);
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

function appendSearchParams(url, searchParams) {
  if (!searchParams || Object.keys(searchParams).length === 0) return url;
  const u = new URL(url);
  for (const [k, v] of Object.entries(searchParams)) {
    u.searchParams.set(k, String(v));
  }
  return u.toString();
}