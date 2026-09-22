import { AccountApi } from './account-api.js';
import { Srp } from './srp.js';
import { generateSignInUrl, completeFork } from './auth-fork.js';

/**
 * Sign-in orchestration over the session-fork flow.
 * The member completes sign-in on account.proton.me; the bridge only
 * receives session tokens + the (never-stored-in-plaintext) key password
 * via the encrypted fork payload.
 */
export class Auth {
  constructor(accountApi, credentials) {
    this.accountApi = accountApi;
    this.credentials = credentials;
    this.srpModule = new Srp(accountApi);
  }

  isLoggedIn() {
    return this.credentials.isLoggedIn();
  }

  async loadSession() {
    await this.credentials.load();
  }

  async logout() {
    await this.credentials.signOut();
  }

  /**
   * Runs the full fork flow. Returns the sign-in URL immediately (callback)
   * and resolves when the member finishes signing in on Proton's page.
   */
  async authViaFork(onSignInUrl, signal) {
    const forkResponse = await this.accountApi.sessionForksInit();
    const { encryptionKey, signInUrl } = generateSignInUrl(forkResponse.UserCode);

    await onSignInUrl(signInUrl);

    const { session, userKeyPassword } = await completeFork(
      this.accountApi,
      forkResponse.Selector,
      encryptionKey,
      signal,
    );

    await this.credentials.setUserKeyPassword(userKeyPassword);
    await this.credentials.setSessionInfo(session);

    return { uid: session.uid };
  }
}