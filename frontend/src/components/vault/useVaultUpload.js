import { useState, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import { fetchWithAuth } from '@/utils/api';
import { INITIAL_FORM } from './vaultConstants';

/**
 * Custom hook that encapsulates vault document upload and link logic.
 *
 * @param {object} selectedTrust - The currently selected trust object.
 * @param {function} loadData - Callback to reload vault data after mutations.
 * @returns {object} State and handlers for the Add Document form.
 */
export function useVaultUpload(selectedTrust, loadData) {
  const [showAdd, setShowAdd] = useState(false);
  const [addMode, setAddMode] = useState('upload'); // 'upload' or 'link'
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [uploadFile, setUploadFile] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const fileInputRef = useRef(null);

  const resetForm = useCallback(() => {
    setShowAdd(false);
    setUploadFile(null);
    setAddMode('upload');
    setUploadProgress('');
    setForm(INITIAL_FORM);
  }, []);

  /** Validate the link-form before submission. */
  const isLinkUrlValid = useCallback(() => {
    if (addMode !== 'link') return true;
    if (!form.storage_url) return true;
    return form.storage_url.startsWith('https://');
  }, [addMode, form.storage_url]);

  const addDocument = useCallback(async () => {
    if (!isLinkUrlValid()) {
      toast.error('Storage URL must start with https://');
      return;
    }
    try {
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/vault/documents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed');
      toast.success('Document added to vault');
      resetForm();
      loadData();
    } catch (e) {
      showError(toast, e, { operation: 'add_external_link', page: 'Vault' });
    }
  }, [form, isLinkUrlValid, resetForm, selectedTrust, loadData]);

  /** Read the JSON body of an upload response, falling back to a status-based message. */
  const readUploadErrorMessage = async (res) => {
    let errorMsg = 'Upload failed';
    try {
      const errData = await res.json();
      errorMsg = errData.detail || errorMsg;
    } catch {
      errorMsg = `Upload failed (${res.status})`;
    }
    return errorMsg;
  };

  const handleUpload = useCallback(async () => {
    if (!uploadFile) {
      toast.error('Please select a file to upload first.');
      return;
    }
    if (!form.title.trim()) {
      toast.error('Please enter a document title so you can identify it later.');
      return;
    }

    setUploading(true);
    setUploadProgress('Uploading...');

    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('title', form.title);
      formData.append('category', form.category);
      if (form.date) formData.append('date', form.date);
      if (form.description) formData.append('description', form.description);
      formData.append('tags', form.tags);
      if (form.expiration_date) formData.append('expiration_date', form.expiration_date);
      formData.append('needs_renewal', form.needs_renewal ? 'true' : 'false');

      const token = localStorage.getItem('auth_token');
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);

      let res;
      try {
        const API_BASE = (process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app') + '/api';
        res = await fetch(`${API_BASE}/trusts/${selectedTrust.trust_id}/vault/upload`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
          signal: controller.signal,
        });
      } catch (fetchError) {
        clearTimeout(timeoutId);
        if (fetchError.name === 'AbortError') {
          throw new Error('Upload timed out — the file may be too large or your connection is slow. Please try again.');
        }
        throw new Error('Could not reach the server. Please check your internet connection and try again.');
      }
      clearTimeout(timeoutId);

      if (!res.ok) throw new Error(await readUploadErrorMessage(res));

      let data;
      try {
        data = await res.json();
      } catch {
        data = {};
      }

      setUploadProgress('Upload complete!');
      toast.success('File uploaded to vault');
      resetForm();
      loadData();
    } catch (e) {
      setUploadProgress('');
      let errorMsg = e.message || 'Upload failed';
      if (errorMsg === 'Failed to fetch' || errorMsg.includes('Could not reach the server')) {
        errorMsg = 'Could not reach the server. The file may be too large or your connection timed out. Please try again, or use "Link External" to store a link to the file instead.';
      }
      console.error('Vault upload error:', e);
      toast.error(errorMsg);
      loadData();
    } finally {
      setUploading(false);
    }
  }, [uploadFile, form, selectedTrust, resetForm, loadData]);

  /** Check whether a file's name suggests it's an EIN confirmation letter. */
  const isEinLetterName = (name) => {
    const lower = name.toLowerCase();
    const hasEin = lower.includes('cp575') || lower.includes('ein') || lower.includes('ein_letter') || lower.includes('ein-confirmation');
    const hasIrs = lower.includes('irs') && lower.includes('letter');
    return hasEin || hasIrs;
  };

  const handleFileSelect = useCallback((e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (file.size > 50 * 1024 * 1024) {
      toast.error(`File too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Maximum is 50MB. PDFs are automatically compressed.`);
      return;
    }

    setUploadFile(file);
    const baseName = file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
    setForm(f => ({
      ...f,
      title: f.title || baseName,
      file_name: file.name,
      category: isEinLetterName(file.name) ? 'ein_letter' : f.category,
    }));
  }, []);

  /** Clear the selected upload file. */
  const clearUploadFile = useCallback(() => {
    setUploadFile(null);
    setForm(f => ({ ...f, file_name: '' }));
  }, []);

  return {
    showAdd, setShowAdd,
    addMode, setAddMode,
    uploading, uploadProgress,
    uploadFile,
    form, setForm,
    fileInputRef,
    addDocument,
    handleUpload,
    handleFileSelect,
    clearUploadFile,
    resetForm,
  };
}
