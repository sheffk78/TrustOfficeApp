import { ApiClient } from './api-client.js';

/**
 * Typed wrappers around the Proton core/v4 + auth/v4 endpoints the bridge needs.
 * Mirrors the reference integration's AccountApi.
 */
export class AccountApi {
  constructor(apiClient) {
    this.apiClient = apiClient;
  }

  /** Step 1 of the session-fork flow: create a fork attempt. */
  async sessionForksInit() {
    try {
      const response = await this.apiClient.unauthenticatedRequest(
        `${this.apiClient.baseUrlWithProtocol}/auth/v4/sessions/forks`,
      );
      if (!isOk(response)) throw await makeApiError(response);
      return parseJson(response);
    } catch (error) {
      throw await makeApiError(error);
    }
  }

  /** Step 3: poll until the user completes sign-in on account.proton.me. */
  async sessionForksStatus(selector) {
    try {
      const response = await this.apiClient.unauthenticatedRequest(
        `${this.apiClient.baseUrlWithProtocol}/auth/v4/sessions/forks/${encodeURIComponent(selector)}`,
      );
      if (!isOk(response)) throw await makeApiError(response);
      return parseJson(response);
    } catch (error) {
      throw await makeApiError(error);
    }
  }

  /** Fetch the logged-in user's keys (used to decrypt address keys). */
  async users() {
    try {
      const response = await this.apiClient.authenticatedRequest(
        `${this.apiClient.baseUrlWithProtocol}/core/v4/users`,
      );
      if (!isOk(response)) throw await makeApiError(response);
      return parseJson(response);
    } catch (error) {
      throw await makeApiError(error);
    }
  }

  async addresses() {
    try {
      const response = await this.apiClient.authenticatedRequest(
        `${this.apiClient.baseUrlWithProtocol}/core/v4/addresses`,
        { searchParams: { Page: 0, PageSize: 50 } },
      );
      if (!isOk(response)) throw await makeApiError(response);
      return parseJson(response);
    } catch (error) {
      throw await makeApiError(error);
    }
  }

  /** Public keys for another Proton user (SDK account interface requirement). */
  async keys(email) {
    try {
      const response = await this.apiClient.authenticatedRequest(
        `${this.apiClient.baseUrlWithProtocol}/core/v4/keys/all`,
        { searchParams: { Email: email, InternalOnly: 1 } },
      );
      if (!isOk(response)) throw await makeApiError(response);
      return parseJson(response);
    } catch (error) {
      throw await makeApiError(error);
    }
  }
}

export class AccountApiError extends Error {
  constructor(message, { httpCode, debug } = {}) {
    super(message);
    this.name = 'AccountApiError';
    this.httpCode = httpCode;
    this.debug = debug;
  }
}

function isOk(response) {
  return response.status >= 200 && response.status < 300;
}

function parseJson(response) {
  const text = new TextDecoder().decode(response.arrayBuffer);
  try {
    return JSON.parse(text);
  } catch {
    throw new AccountApiError('Invalid JSON response from Proton API', {
      httpCode: response.status,
    });
  }
}

async function makeApiError(responseOrError) {
  // Preserve the original error (esp. httpCode) when re-thrown through
  // multiple layers — the fork poller relies on httpCode === 422 to keep
  // waiting for the member to finish signing in.
  if (responseOrError instanceof AccountApiError) {
    return responseOrError;
  }
  if (responseOrError instanceof Error && !(responseOrError.arrayBuffer !== undefined)) {
    return new AccountApiError(responseOrError.message, {});
  }
  const response = responseOrError;
  let detail = '';
  let code;
  try {
    const body = parseJson(response);
    detail = body.Error || body.error || '';
    code = body.Code;
  } catch {
    detail = '';
  }
  return new AccountApiError(
    `Proton API error (HTTP ${response.status}${code ? `, Code ${code}` : ''})${detail ? `: ${detail}` : ''}`,
    { httpCode: response.status, debug: { code } },
  );
}