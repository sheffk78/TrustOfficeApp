import {
  CryptoProxy,
  VERIFICATION_STATUS,
} from '@protontech/crypto';

/**
 * Implements the SDK's `account` interface (ProtonDriveAccount) — mirrors
 * the reference integration's Addresses class: user primary keys are
 * imported with the (fork-delivered) key password, address keys are
 * resolved via signed tokens, and public keys for other users come from
 * core/v4/keys/all. Per-request instance, so a simple userData cache is
 * enough (invalidated on error).
 */
export class Addresses {
  constructor(accountApi, credentials) {
    this.accountApi = accountApi;
    this.credentials = credentials;
    this.userDataPromise = undefined;
    this.otherUsersPublicKeysByEmailPromises = new Map();
  }

  async getOwnPrimaryAddress() {
    const { primaryAddress } = await this.getUserData();
    return this.getOwnAddress(primaryAddress.addressId);
  }

  async getOwnAddresses() {
    const userData = await this.getUserData();
    const addresses = [];
    for (const address of userData.addresses) {
      if (!address.ID) continue;
      addresses.push(await this.getOwnAddress(address.ID));
    }
    return addresses;
  }

  async getOwnAddress(emailOrAddressId) {
    const userData = await this.getUserData();
    const address = userData.addresses.find(
      (a) => a.ID === emailOrAddressId || a.Email === emailOrAddressId,
    );
    if (!address?.ID || !address.Email) {
      throw new Error(`Address ${emailOrAddressId} not found`);
    }

    const keys = [];
    const errors = [];

    for (const key of address.Keys ?? []) {
      try {
        const { id, privateKey } = await this.getAddressKey(
          userData.userPrimaryPrivateKeys,
          userData.userPrimaryPublicKeys,
          key,
          address.Email,
        );
        keys.push({ id, key: privateKey });
      } catch (error) {
        errors.push(error);
      }
    }

    if (keys.length === 0) {
      throw new Error(`No private key found: ${errors.map(String).join('; ')}`);
    }

    return {
      email: address.Email,
      addressId: address.ID,
      primaryKeyIndex: 0,
      keys,
    };
  }

  async hasProtonAccount(email) {
    const keys = await this.getPublicKeys(email);
    return keys.length > 0;
  }

  async getPublicKeys(email, _forceRefresh = false) {
    if (!this.credentials.isLoggedIn()) {
      return [];
    }

    const userData = await this.getUserData();
    const address = userData.addresses.find((a) => a.Email === email);
    if (address) {
      return this.getOwnPublicKeys(address);
    }
    return this.getOtherPublicKeys(email);
  }

  async getOwnPublicKeys(address) {
    const { userPrimaryPrivateKeys, userPrimaryPublicKeys } =
      await this.getUserData();

    const keys = [];
    const errors = [];

    for (const key of address.Keys ?? []) {
      try {
        const { publicKey } = await this.getAddressKey(
          userPrimaryPrivateKeys,
          userPrimaryPublicKeys,
          key,
          address.Email,
        );
        keys.push(publicKey);
      } catch (error) {
        errors.push(error);
      }
    }

    if (keys.length === 0 && errors.length > 0) {
      throw new Error(
        `Failed to load public keys: ${errors.map(String).join('; ')}`,
      );
    }

    return keys;
  }

  async getOtherPublicKeys(email) {
    const existing = this.otherUsersPublicKeysByEmailPromises.get(email);
    if (existing) {
      return existing;
    }

    const promise = this.loadOtherPublicKeys(email);
    this.otherUsersPublicKeysByEmailPromises.set(email, promise);
    return promise;
  }

  async loadOtherPublicKeys(email) {
    try {
      const response = await this.accountApi.keys(email);
      return await Promise.all(
        (response.Address?.Keys ?? []).map((key) =>
          CryptoProxy.importPublicKey({ armoredKey: key.PublicKey }),
        ),
      );
    } catch (error) {
      this.otherUsersPublicKeysByEmailPromises.delete(email);
      throw error;
    }
  }

  async getUserData() {
    if (this.userDataPromise) {
      return this.userDataPromise;
    }

    this.userDataPromise = this.loadUserData();
    return this.userDataPromise;
  }

  async loadUserData() {
    const userKeyPassword = this.credentials.getUserKeyPassword();
    if (!userKeyPassword) {
      throw new Error('Password is not set');
    }

    try {
      const users = await this.accountApi.users();
      const userKeys = users.User?.Keys ?? [];

      const userPrimaryPrivateKeys = [];
      const userPrimaryPublicKeys = [];

      for (const userKey of userKeys) {
        if (!userKey.PrivateKey) {
          continue;
        }

        const userPrimaryPrivateKey = await CryptoProxy.importPrivateKey({
          armoredKey: userKey.PrivateKey,
          passphrase: userKeyPassword,
        });

        const userPrimaryPublicKey = await CryptoProxy.importPublicKey({
          binaryKey: await CryptoProxy.exportPublicKey({
            key: userPrimaryPrivateKey,
            format: 'binary',
          }),
        });

        userPrimaryPrivateKeys.push(userPrimaryPrivateKey);
        userPrimaryPublicKeys.push(userPrimaryPublicKey);
      }

      const addresses = await this.accountApi.addresses();
      const primaryAddress = addresses.Addresses?.[0];
      const primaryAddressPrimaryKey = primaryAddress?.Keys?.[0];

      if (
        !primaryAddress?.Email ||
        !primaryAddress.ID ||
        !primaryAddressPrimaryKey?.ID
      ) {
        throw new Error('Missing primary address');
      }

      if (
        userPrimaryPrivateKeys.length === 0 ||
        userPrimaryPublicKeys.length === 0
      ) {
        throw new Error('Missing user primary keys');
      }

      return {
        userPrimaryPrivateKeys,
        userPrimaryPublicKeys,
        primaryAddress: {
          email: primaryAddress.Email,
          addressId: primaryAddress.ID,
          addressKeyId: primaryAddressPrimaryKey.ID,
        },
        addresses: addresses.Addresses ?? [],
      };
    } catch (error) {
      this.userDataPromise = undefined;
      throw error;
    }
  }

  async getAddressKey(
    userPrimaryPrivateKeys,
    userPrimaryPublicKeys,
    key,
    email,
  ) {
    const keyId = key.ID;
    if (!keyId) {
      throw new Error('Missing key ID');
    }
    return this.loadAddressKey(
      userPrimaryPrivateKeys,
      userPrimaryPublicKeys,
      key,
      keyId,
      email,
    );
  }

  async loadAddressKey(
    userPrimaryPrivateKeys,
    userPrimaryPublicKeys,
    key,
    keyId,
    email,
  ) {
    try {
      if (!key.Token && key.PrivateKey) {
        const userKeyPassword = this.credentials.getUserKeyPassword();
        if (!userKeyPassword) {
          throw new Error('User key password is not set');
        }

        const privateKey = await CryptoProxy.importPrivateKey({
          armoredKey: key.PrivateKey,
          passphrase: userKeyPassword,
        });

        return {
          id: keyId,
          privateKey,
          publicKey: await CryptoProxy.importPublicKey({
            binaryKey: await CryptoProxy.exportPublicKey({
              key: privateKey,
              format: 'binary',
            }),
          }),
        };
      }

      const { verificationStatus } = await CryptoProxy.decryptMessage({
        armoredMessage: key.Token ?? '',
        armoredSignature: key.Signature ?? '',
        decryptionKeys: userPrimaryPrivateKeys,
        verificationKeys: userPrimaryPublicKeys,
      });

      if (verificationStatus !== VERIFICATION_STATUS.SIGNED_AND_VALID) {
        throw new Error('Failed to verify address key');
      }

      const { data: decryptedToken } = await CryptoProxy.decryptMessage({
        armoredMessage: key.Token ?? '',
        armoredSignature: key.Signature ?? '',
        decryptionKeys: userPrimaryPrivateKeys,
        verificationKeys: userPrimaryPublicKeys,
      });

      const privateKey = await CryptoProxy.importPrivateKey({
        armoredKey: key.PrivateKey ?? '',
        passphrase: decryptedToken.toString(),
      });

      return {
        id: keyId,
        privateKey,
        publicKey: await CryptoProxy.importPublicKey({
          binaryKey: await CryptoProxy.exportPublicKey({
            key: privateKey,
            format: 'binary',
          }),
        }),
      };
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      throw new Error(
        `Error loading address key ${keyId} for ${email ?? 'unknown'}: ${detail}`,
      );
    }
  }
}