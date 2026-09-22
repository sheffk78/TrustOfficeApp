import { MemoryCache, ProtonDriveClient } from '@protontech/drive-sdk';

import { ApiClient } from './api-client.js';
import { AccountApi } from './account-api.js';
import { Addresses } from './addresses.js';
import { Auth } from './auth.js';
import { HTTPClient } from './http-client.js';
import { Srp } from './srp.js';
import { initProtonCrypto } from './crypto.js';
import { Credentials } from './credentials.js';
import { BRIDGE_VERSION, APP_VERSION, AUTH_CLIENT_ID, BASE_URL, BACKUP_ROOT_FOLDER, FORK_POLL_INTERVAL_MS } from './constants.js';

export { BRIDGE_VERSION, APP_VERSION, AUTH_CLIENT_ID, BASE_URL, BACKUP_ROOT_FOLDER };

/**
 * One DriveService instance per connected member (per request scope).
 * credentialsStore: MemoryCredentialsStore seeded from the Python backend's
 * decrypted connection record.
 */
export class DriveService {
  constructor(credentialsStore, { baseUrl = BASE_URL } = {}) {
    this.credentials = new Credentials(credentialsStore);
    this.baseUrl = baseUrl;
    this.apiClient = undefined;
    this.auth = undefined;
    this.addresses = undefined;
    this.client = undefined;
  }

  async initialize() {
    await this.credentials.load();
    if (this.credentials.isLoggedIn()) {
      await this.ensureClient();
    }
  }

  isLoggedIn() {
    return this.credentials.isLoggedIn();
  }

  getAuth() {
    this.ensureApiLayer();
    return this.auth;
  }

  async getClient() {
    if (!this.credentials.isLoggedIn()) {
      throw new BridgeError('not_signed_in', 'Proton session missing or expired');
    }
    await this.ensureClient();
    return this.client;
  }

  async logout() {
    this.client = undefined;
    await this.credentials.signOut();
  }

  /** What the Python backend must persist after any auth change. */
  credentialsSnapshot() {
    return this.credentials.snapshot();
  }

  ensureApiLayer() {
    if (this.apiClient && this.auth && this.addresses) return;
    this.apiClient = new ApiClient(this.credentials, this.baseUrl);
    const accountApi = new AccountApi(this.apiClient);
    this.auth = new Auth(accountApi, this.credentials);
    this.addresses = new Addresses(accountApi, this.credentials);
  }

  async ensureClient() {
    if (this.client) return;
    this.ensureApiLayer();

    const openPGPCryptoModule = initProtonCrypto();
    const httpClient = new HTTPClient(this.apiClient);
    const srpModule = new Srp(new AccountApi(this.apiClient));

    this.client = new ProtonDriveClient({
      httpClient,
      entitiesCache: new MemoryCache(),
      cryptoCache: new MemoryCache(),
      account: this.addresses,
      openPGPCryptoModule,
      srpModule,
      config: {
        clientUid: `trustoffice-bridge-${BRIDGE_VERSION}`,
      },
    });
  }
}

export class BridgeError extends Error {
  constructor(code, message, { httpStatus = 400 } = {}) {
    super(message);
    this.name = 'BridgeError';
    this.code = code;
    this.httpStatus = httpStatus;
  }
}