import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import { fetchWithAuth } from '@/utils/api';

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

/** Download a vault document as a blob and trigger a browser save. */
export async function downloadDocument(docId, fileName) {
  try {
    const token = localStorage.getItem('auth_token');
    const res = await fetch(`${API_BASE()}/vault/documents/${docId}/download`, {
      headers: { Authorization: `Bearer ${token}` },
    });
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
