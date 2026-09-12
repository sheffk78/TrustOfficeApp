import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import { fetchWithAuth } from '@/utils/api';
import use2faStepUp from '@/hooks/use2faStepUp';

// Shared 2FA step-up hook state lives at the VaultPage level (the hook must
// not be re-created per call). This module receives the wrapped runner via
// configure2faStepUp so downloads can replay through the step-up modal.
// Simpler approach: keep a module-level reference to a React-safe wrapper
// set by VaultPage's use2faStepUp instance.

let stepUpRunner = null;

/** VaultPage registers its use2faStepUp runner here on mount. */
export function register2faStepUpRunner(runner) {
  stepUpRunner = runner;
}

const API_BASE = () => (process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app') + '/api';

/** Delete a vault document by id. */
export async function deleteDocument(id, loadData) {
  try {
    const res = await fetchWithAuth(`/vault/documents/${id}`, { method: 'DELETE' });
    if (res.ok) {
      toast.success('Document removed');
      loadData();
    } else {
      const errData = await res.json().catch(() => ({}));
      showError(toast, new Error(errData.detail || 'Could not delete document. Please try again or contact support@trustoffice.app.'), { operation: 'delete_vault_doc', page: 'Vault' });
    }
  } catch (e) {
    showError(toast, e, { operation: 'delete_vault_doc', page: 'Vault' });
  }
}

/**
 * Download a vault document as a blob and trigger a browser save.
 * When 2FA is enabled the backend may answer 403 2fa_stepup_required; the
 * request is then replayed with the X-2FA-Code header after the user enters
 * a fresh code in the step-up modal (via the registered runner).
 */
export async function downloadDocument(docId, fileName) {
  const doDownload = async (extraHeaders) => {
    const token = localStorage.getItem('auth_token');
    const headers = { ...(extraHeaders || {}) };
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(`${API_BASE()}/vault/documents/${docId}/download`, { headers });
  };

  try {
    const res = stepUpRunner
      ? await stepUpRunner(doDownload)
      : await doDownload(null);
    if (!res.ok) throw new Error('Download failed');

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName || 'document';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  } catch (e) {
    showError(toast, e, { operation: 'download_vault_doc', page: 'Vault' });
  }
}