import { ApiClient } from './api-client.js';

/**
 * Bridges the SDK's HTTP client interface onto our ApiClient.
 * (No SDK type imports — those are types-only and break esbuild bundling.)
 */
export class HTTPClient {
  constructor(apiClient) {
    this.apiClient = apiClient;
  }

  async fetchJson(options) {
    const response = await this.apiClient.authenticatedRequest(options.url, {
      method: options.method,
      ...(options.json !== undefined ? { json: options.json } : {}),
      ...(options.body !== undefined && options.json === undefined ? { body: options.body } : {}),
      headers: options.headers,
      timeout: options.timeoutMs,
      signal: options.signal,
    });
    return toFetchResponse(response);
  }

  async fetchBlob(options) {
    const response = await this.apiClient.authenticatedRequest(options.url, {
      method: options.method,
      body: options.body,
      headers: options.headers,
      timeout: options.timeoutMs,
      signal: options.signal,
    });
    return toFetchResponse(response);
  }
}

function toFetchResponse(response) {
  const headers = new Headers();
  for (const [key, value] of Object.entries(response.headers)) {
    if (typeof value === 'string') headers.set(key, value);
  }

  const body =
    response.arrayBuffer instanceof ArrayBuffer ? response.arrayBuffer : undefined;

  return new Response(body, {
    status: response.status,
    headers,
  });
}