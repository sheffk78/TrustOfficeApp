import {
  computeKeyPassword,
  generateKeySalt,
  getSrp,
  getRandomSrpVerifier,
} from '@protontech/crypto/srp';

/**
 * SRP helpers (thin wrapper over @protontech/crypto/srp).
 * The bridge itself authenticates only via session forks (auth-fork.js),
 * so SRP is used by the SDK internals (e.g. password re-derivation paths).
 */
export class Srp {
  constructor(accountApi) {
    this.accountApi = accountApi;
  }

  async getSrp(version, modulus, serverEphemeral, salt, password) {
    return getSrp(
      {
        Version: version,
        Modulus: modulus,
        ServerEphemeral: serverEphemeral,
        Salt: salt,
      },
      { password },
    );
  }

  async getSrpVerifier(password) {
    const result = await this.accountApi.modulus();
    if (!result.Modulus || !result.ModulusID) {
      throw new Error('Missing modulus');
    }
    const { version, salt, verifier } = await getRandomSrpVerifier(
      { Modulus: result.Modulus },
      { password },
    );
    return { modulusId: result.ModulusID, version, salt, verifier };
  }

  async computeKeyPassword(password, salt) {
    return computeKeyPassword(password, salt);
  }

  generateKeySalt() {
    return generateKeySalt();
  }
}