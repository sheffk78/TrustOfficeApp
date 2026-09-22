/**
 * Per-connection credential store passed to the bridge from the Python
 * backend. Secrets are stored encrypted (Fernet) in TrustOffice's MongoDB —
 * this store just carries the decrypted in-memory values per request.
 */
export class MemoryCredentialsStore {
  constructor(initial = {}) {
    this.data = { ...initial };
  }

  async load() {
    return Object.keys(this.data).length ? this.data : null;
  }

  async save(data) {
    this.data = { ...data };
  }

  async remove() {
    this.data = {};
  }
}

export class Credentials {
  constructor(store) {
    this.store = store;
    this.cachePassword = undefined;
    this.userKeyPassword = undefined;
    this.sessionInfo = undefined;
    this.sessionInfoChangedCallbacks = new Set();
  }

  on(_event, callback) {
    this.sessionInfoChangedCallbacks.add(callback);
  }

  isLoggedIn() {
    return !!this.userKeyPassword && !!this.sessionInfo;
  }

  getUserKeyPassword() {
    return this.userKeyPassword;
  }

  get uid() {
    return this.sessionInfo?.uid;
  }

  get accessToken() {
    return this.sessionInfo?.accessToken;
  }

  get refreshToken() {
    return this.sessionInfo?.refreshToken;
  }

  async load() {
    const raw = await this.store.load();
    if (!raw) return;
    this.cachePassword = raw.cachePassword;
    this.userKeyPassword = raw.userKeyPassword;
    this.sessionInfo = raw.session;
    this.notifySessionInfoChanged();
  }

  async setUserKeyPassword(userKeyPassword) {
    this.userKeyPassword = userKeyPassword;
    await this.persistCredentials();
    this.notifySessionInfoChanged();
  }

  async setSessionInfo(info) {
    this.sessionInfo = info;
    await this.persistCredentials();
    this.notifySessionInfoChanged();
  }

  async signOut() {
    this.userKeyPassword = undefined;
    this.sessionInfo = undefined;
    await this.store.remove();
    this.notifySessionInfoChanged();
  }

  /** Snapshot of everything the Python side must persist (it encrypts at rest). */
  snapshot() {
    return {
      cachePassword: this.cachePassword,
      userKeyPassword: this.userKeyPassword,
      session: this.sessionInfo,
    };
  }

  async persistCredentials() {
    if (!this.userKeyPassword || !this.sessionInfo) return;
    await this.store.save(this.snapshot());
  }

  notifySessionInfoChanged() {
    for (const callback of this.sessionInfoChangedCallbacks) callback();
  }
}