import { VERSION as SDK_VERSION } from '@protontech/drive-sdk';

export const BRIDGE_VERSION = '0.1.0';

/** Required x-pm-appversion format for third-party Drive clients. */
export const APP_VERSION = `external-drive-trustoffice@${BRIDGE_VERSION}-stable`;

/** OAuth client id used in the session-fork payload (Proton's generic third-party id). */
export const AUTH_CLIENT_ID = 'external-drive';

/** Proton Drive API base (also proxies core/v4 + auth/v4 account endpoints). */
export const BASE_URL = 'https://drive-api.proton.me';

/** Proton's account web app — the user signs in HERE, never on TrustOffice. */
export const PROTON_ACCOUNT_URL = 'https://account.proton.me';

export const SDK_VERSION_STRING = SDK_VERSION;

export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

/** Backup folder root created inside the member's Proton Drive. */
export const BACKUP_ROOT_FOLDER = 'TrustOffice-Backup';

/** Fork polling cadence (matches reference implementation). */
export const FORK_POLL_INTERVAL_MS = 5_000;
export const FORK_INITIAL_DELAY_MS = 5_000;
export const FORK_MAX_POLL_TIME_MS = 10 * 60 * 1000;