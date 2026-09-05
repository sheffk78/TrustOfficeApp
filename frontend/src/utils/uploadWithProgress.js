/**
 * Upload with real progress reporting. fetch() can't report upload progress,
 * so this uses XMLHttpRequest with the same auth/timeout semantics as the
 * fetch-based paths it replaces.
 *
 * @param {object} opts
 * @param {string} opts.url - Full upload endpoint URL.
 * @param {string} opts.token - Bearer token.
 * @param {FormData} opts.formData - Request body.
 * @param {number} [opts.timeoutMs=480000] - Abort timeout (8 min default).
 * @param {function} [opts.onProgress] - ({ percent, loaded, total }) => void, throttled to ~5/s.
 * @returns {Promise<{ok: boolean, status: number, data: object}>}
 *   data is the parsed JSON body ({} on parse failure).
 */
export function uploadWithProgress({ url, token, formData, timeoutMs = 480000, onProgress }) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);

    const timeoutId = setTimeout(() => {
      xhr.abort();
      const err = new Error('Upload timed out after 8 minutes — the file may be too large for your connection speed. Please try again, use a faster connection, or use "Link External" to store a link to the file instead.');
      err.name = 'AbortError';
      reject(err);
    }, timeoutMs);

    let lastTick = 0;
    xhr.upload.onprogress = (e) => {
      if (!onProgress || !e.lengthComputable) return;
      const now = Date.now();
      if (now - lastTick < 200 && e.loaded < e.total) return; // throttle to ~5/s, always fire final
      lastTick = now;
      onProgress({
        percent: Math.round((e.loaded / e.total) * 100),
        loaded: e.loaded,
        total: e.total,
      });
    };

    xhr.onload = () => {
      clearTimeout(timeoutId);
      let data = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON body */
      }
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data });
    };

    xhr.onerror = () => {
      clearTimeout(timeoutId);
      reject(new Error('Could not reach the server. Please check your internet connection and try again.'));
    };

    xhr.onabort = () => clearTimeout(timeoutId);

    xhr.send(formData);
  });
}