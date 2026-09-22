import { CryptoProxy } from '@protontech/crypto';
import { Api as CryptoApi } from '@protontech/crypto/proxy/endpoint/api.ts';
import { OpenPGPCryptoWithCryptoProxy } from '@protontech/drive-sdk';

let initialized = false;

/**
 * Proton's crypto stack runs as a "proxy" — an endpoint object that the
 * SDK calls into. Initialize it once per process; it is stateless across
 * requests (keys are handed in per client instance).
 */
export function initProtonCrypto() {
  if (!initialized) {
    CryptoApi.init({});
    CryptoProxy.setEndpoint(
      new CryptoApi(),
      (endpoint) => endpoint.clearKeyStore(),
    );
    initialized = true;
  }
  return new OpenPGPCryptoWithCryptoProxy(CryptoProxy);
}