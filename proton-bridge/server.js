import express from 'express';
import { randomUUID } from 'node:crypto';
import { MemoryCredentialsStore } from './lib/credentials.js';
import { DriveService, BridgeError } from './lib/drive-service.js';
import { DriveOps } from './lib/drive-ops.js';
import { BRIDGE_VERSION } from './lib/constants.js';

/**
 * TrustOffice Proton Bridge — internal HTTP API.
 *
 * Called ONLY by the TrustOffice Python backend over the internal network.
 * AUTH: every request carries X-Bridge-Key which must equal BRIDGE_KEY env.
 * Secrets arrive per-request (already decrypted by the Python side) and are
 * never written to disk by this process.
 */

const PORT = process.env.PORT || 8081;
const BRIDGE_KEY = process.env.BRIDGE_KEY;

if (!BRIDGE_KEY) {
  console.error('BRIDGE_KEY env var is required');
  process.exit(1);
}

const app = express();
app.use(express.json({ limit: '60mb' }));

/** connectionRecord: { credentials: {cachePassword?, userKeyPassword?, session?} } */
function buildService(connectionRecord) {
  const store = new MemoryCredentialsStore(connectionRecord?.credentials || {});
  const service = new DriveService(store);
  return { store, service };
}

function requireAuth(req, res, next) {
  const key = req.header('X-Bridge-Key');
  if (!key || key !== BRIDGE_KEY) {
    return res.status(401).json({ error: 'unauthorized', message: 'Invalid bridge key' });
  }
  next();
}

function handleError(res, error) {
  if (error instanceof BridgeError) {
    return res.status(error.httpStatus).json({ error: error.code, message: error.message });
  }
  const message = error?.message || 'Internal bridge error';
  console.error('[bridge]', message);
  return res.status(500).json({ error: 'internal', message });
}

app.get('/health', (_req, res) => {
  res.json({ ok: true, version: BRIDGE_VERSION });
});

/**
 * POST /connect/start
 * { } → { connect_id, sign_in_url }
 * Member opens sign_in_url and signs in on account.proton.me.
 */
app.post('/connect/start', requireAuth, async (req, res) => {
  try {
    const { store, service } = buildService({});
    const auth = service.getAuth();
    const connectId = randomUUID();

    // Fire the fork flow; poll resolves when the member completes sign-in.
    const completion = auth.authViaFork(async (signInUrl) => {
      pendingConnects.set(connectId, { signInUrl, service, store, startedAt: Date.now() });
      console.log(`[bridge] connect ${connectId}: sign-in URL ready`);
    });

    completion.catch((error) => {
      console.error(`[bridge] connect ${connectId} failed:`, error.message);
      pendingConnects.set(connectId, {
        ...(pendingConnects.get(connectId) || {}),
        error: error.message,
        failedAt: Date.now(),
      });
    });

    // The URL is produced inside authViaFork before polling starts; wait briefly.
    const deadline = Date.now() + 10_000;
    while (!pendingConnects.get(connectId)?.signInUrl && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 100));
    }
    const entry = pendingConnects.get(connectId);
    if (!entry?.signInUrl) {
      throw new Error('Failed to initialize Proton sign-in flow');
    }

    res.json({ connect_id: connectId, sign_in_url: entry.signInUrl });
  } catch (error) {
    handleError(res, error);
  }
});

/**
 * POST /connect/status
 * { connect_id } → { status: pending|completed|failed, credentials? }
 * Python polls this; on completed it stores the encrypted credentials.
 */
app.post('/connect/status', requireAuth, async (req, res) => {
  try {
    const { connect_id: connectId } = req.body || {};
    const entry = pendingConnects.get(connectId);
    if (!entry) {
      return res.status(404).json({ error: 'not_found', message: 'Unknown connect_id' });
    }
    if (entry.error) {
      return res.json({ status: 'failed', message: entry.error });
    }
    if (entry.completed) {
      const snapshot = entry.service.credentialsSnapshot();
      return res.json({ status: 'completed', credentials: snapshot, email: entry.email || null });
    }
    return res.json({ status: 'pending' });
  } catch (error) {
    handleError(res, error);
  }
});

/**
 * POST /verify — validate stored credentials, return account email.
 * { connection: { credentials } } → { ok, email }
 */
app.post('/verify', requireAuth, async (req, res) => {
  try {
    const { store, service } = buildService(req.body?.connection);
    await service.initialize();
    if (!service.isLoggedIn()) {
      return res.status(401).json({ ok: false, error: 'not_signed_in' });
    }
    const client = await service.getClient();
    const root = await client.getMyFilesRootFolder();
    const addresses = service.addresses;
    const primary = await addresses.getOwnPrimaryAddress();
    res.json({ ok: true, email: primary.email, root_folder_uid: root.uid });
  } catch (error) {
    handleError(res, error);
  }
});

/**
 * POST /backup/upload — upload one file (creates folders as needed).
 * {
 *   connection: { credentials },
 *   trust_name: string,
 *   file_name: string,
 *   media_type: string,
 *   content_base64: string
 * } → { ok, node_uid, revised }
 */
app.post('/backup/upload', requireAuth, async (req, res) => {
  try {
    const { connection, trust_name: trustName, file_name: fileName, media_type: mediaType, content_base64: contentB64 } = req.body || {};
    if (!connection || !trustName || !fileName || !contentB64) {
      return res.status(400).json({ error: 'bad_request', message: 'Missing fields' });
    }

    const { store, service } = buildService(connection);
    await service.initialize();
    const ops = new DriveOps(service);

    const root = await ops.ensureRootFolder();
    const { node: trustFolder } = await ops.ensureSubfolder(root, trustName);

    const data = Uint8Array.from(Buffer.from(contentB64, 'base64'));
    const result = await ops.uploadFile(trustFolder, fileName, mediaType || 'application/octet-stream', data);

    res.json({ ok: true, node_uid: result.nodeUid, revision_uid: result.nodeRevisionUid, revised: result.revised });
  } catch (error) {
    handleError(res, error);
  }
});

/**
 * POST /backup/list — list a folder (root or trust subfolder).
 * { connection, trust_name? } → { ok, items: [{name, isFolder, size}] }
 */
app.post('/backup/list', requireAuth, async (req, res) => {
  try {
    const { connection, trust_name: trustName } = req.body || {};
    const { service } = buildService(connection);
    await service.initialize();
    const ops = new DriveOps(service);

    const root = await ops.ensureRootFolder();
    let target = root;
    if (trustName) {
      target = (await ops.ensureSubfolder(root, trustName)).node;
    }
    const items = await ops.listChildren(target);
    res.json({ ok: true, items });
  } catch (error) {
    handleError(res, error);
  }
});

/**
 * POST /backup/download — fetch a file's decrypted bytes.
 * { connection, node_uid } → { ok, content_base64 }
 */
app.post('/backup/download', requireAuth, async (req, res) => {
  try {
    const { connection, node_uid: nodeUid } = req.body || {};
    if (!connection || !nodeUid) {
      return res.status(400).json({ error: 'bad_request', message: 'Missing fields' });
    }
    const { service } = buildService(connection);
    await service.initialize();
    const ops = new DriveOps(service);
    const data = await ops.downloadFile(nodeUid);
    res.json({ ok: true, content_base64: Buffer.from(data).toString('base64') });
  } catch (error) {
    handleError(res, error);
  }
});

/**
 * POST /disconnect — revoke the local session snapshot (idempotent).
 */
app.post('/disconnect', requireAuth, async (req, res) => {
  try {
    const { store, service } = buildService(req.body?.connection);
    await service.initialize();
    await service.logout();
    res.json({ ok: true });
  } catch (error) {
    handleError(res, error);
  }
});

const pendingConnects = new Map();

// Periodic cleanup of stale connect attempts (10 min fork TTL + buffer).
setInterval(() => {
  const now = Date.now();
  for (const [id, entry] of pendingConnects) {
    if (entry.failedAt || (entry.startedAt && now - entry.startedAt > 12 * 60 * 1000)) {
      pendingConnects.delete(id);
    }
  }
}, 60_000).unref();

app.listen(PORT, () => {
  console.log(`[bridge] TrustOffice Proton Bridge v${BRIDGE_VERSION} listening on :${PORT}`);
});