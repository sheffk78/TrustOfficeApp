import { createHash } from 'node:crypto';
import { BACKUP_ROOT_FOLDER, BRIDGE_VERSION } from './constants.js';

/**
 * Backup operations against one member's Proton Drive.
 * Folder layout mirrors the existing Google/Dropbox backup layout:
 *   TrustOffice-Backup/
 *     manifest.json
 *     <trust-name>/<document files...>
 */
export class DriveOps {
  constructor(driveService) {
    this.driveService = driveService;
  }

  async client() {
    return this.driveService.getClient();
  }

  /**
   * Ensure the TrustOffice-Backup root folder exists; return its node.
   * Idempotent — checks "My files" children for an exact-name folder first.
   */
  async ensureRootFolder() {
    const client = await this.client();
    const root = await client.getMyFilesRootFolder();

    let backupFolder;
    for await (const child of client.iterateFolderChildren(root)) {
      if (child.isFolder && nameOf(child) === BACKUP_ROOT_FOLDER) {
        backupFolder = child;
        break;
      }
    }
    if (backupFolder) return backupFolder;
    return client.createFolder(root.uid, BACKUP_ROOT_FOLDER);
  }

  /**
   * Ensure a subfolder exists under the given parent with the exact name.
   * Returns { node, created }.
   */
  async ensureSubfolder(parentNode, name) {
    const client = await this.client();
    for await (const child of client.iterateFolderChildren(parentNode)) {
      if (child.isFolder && nameOf(child) === name) {
        return { node: child, created: false };
      }
    }
    const node = await client.createFolder(parentNode.uid, name);
    return { node, created: true };
  }

  /**
   * Upload (or add a new revision of) one file.
   * data: Uint8Array; returns { nodeUid, nodeRevisionUid, revised }.
   */
  async uploadFile(parentFolder, name, mediaType, data) {
    const client = await this.client();
    const expectedSize = data.byteLength;
    const expectedSha1 = sha1Hex(data);
    const modTime = new Date();

    // Revise the existing file with the same name instead of duplicating.
    let existing;
    for await (const child of client.iterateFolderChildren(parentFolder)) {
      if (!child.isFolder && nameOf(child) === name) {
        existing = child;
        break;
      }
    }

    if (existing?.activeRevision?.uid) {
      const uploader = await client.getFileRevisionUploader(existing.uid, {
        mediaType,
        expectedSize,
        expectedSha1,
        modificationTime: modTime,
        additionalMetadata: { 'Uploaded-By': `trustoffice-bridge/${BRIDGE_VERSION}` },
      });
      const controller = await uploader.uploadFromFile(
        new File([data], name, { type: mediaType }),
        [],
      );
      const result = await controller.completion();
      return { ...result, revised: true };
    }

    const uploader = await client.getFileUploader(parentFolder.uid, name, {
      mediaType,
      expectedSize,
      expectedSha1,
      modificationTime: modTime,
      additionalMetadata: { 'Uploaded-By': `trustoffice-bridge/${BRIDGE_VERSION}` },
    });
    const controller = await uploader.uploadFromFile(
      new File([data], name, { type: mediaType }),
      [],
    );
    const result = await controller.completion();
    return { ...result, revised: false };
  }

  /** Download a file's decrypted bytes. */
  async downloadFile(nodeUid) {
    const client = await this.client();
    const downloader = await client.getFileDownloader(nodeUid);
    const stream = downloader.downloadLocally();
    const chunks = [];
    const reader = stream.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    return concat(chunks);
  }

  /** List children of a node (names + sizes) for status/debug endpoints. */
  async listChildren(parentNode) {
    const client = await this.client();
    const out = [];
    for await (const child of client.iterateFolderChildren(parentNode)) {
      out.push({
        uid: child.uid,
        name: nameOf(child),
        isFolder: !!child.isFolder,
        size: child.activeRevision?.size ?? null,
      });
    }
    return out;
  }
}

/** Node name is a Result type — nameOf handles both ok/err shapes safely. */
function nameOf(node) {
  const nameResult = node?.name;
  if (typeof nameResult === 'string') return nameResult;
  if (nameResult && typeof nameResult === 'object') {
    if (typeof nameResult.value === 'string') return nameResult.value;
    if (typeof nameResult.ok === 'string') return nameResult.ok;
  }
  return '';
}

function sha1Hex(data) {
  // Computed on plaintext bytes; SDK verifies integrity server-side.
  try {
    return createHash('sha1').update(data).digest('hex');
  } catch {
    return undefined;
  }
}

function concat(chunks) {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}