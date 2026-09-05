import { useState, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import { fetchWithAuth } from '@/utils/api';
import { uploadWithProgress } from '@/utils/uploadWithProgress';
import { validateVaultFile } from '@/utils/uploadValidation';
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
  const [uploadError, setUploadError] = useState(null); // persistent inline error display
  const [uploadFile, setUploadFile] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const fileInputRef = useRef(null);

  const resetForm = useCallback(() => {
    setShowAdd(false);
    setUploadFile(null);
    setAddMode('upload');
    setUploadProgress('');
    setUploadError(null);
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
    setUploadProgress('Uploading 0%');

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
      const API_BASE = (process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app') + '/api';

      const res = await uploadWithProgress({
        url: `${API_BASE}/trusts/${selectedTrust.trust_id}/vault/upload`,
        token,
        formData,
        onProgress: ({ percent }) => {
          // Transfer caps around 95% — the final stretch is server-side
          // compression, tracked by the separate "Processing" message below.
          if (percent < 100) {
            setUploadProgress(`Uploading ${percent}%`);
          } else {
            setUploadProgress('Almost done — processing document…');
          }
        },
      });

      if (!res.ok) throw new Error(res.data.detail || `Upload failed (${res.status})`);

      setUploadProgress('Upload complete!');
      toast.success('File uploaded to vault');
      resetForm();
      loadData();
    } catch (e) {
      setUploadProgress('');
      let errorMsg = e.message || 'Upload failed';
      if (errorMsg.includes('timed out')) {
        errorMsg = `This upload timed out after 8 minutes — the file may be too large for your connection speed. ${uploadFile?.name ? `${uploadFile.name} is ${(uploadFile.size / (1024 * 1024)).toFixed(1)}MB. ` : ''}Please try again on a faster connection, or use "Link External" to store a link instead.`;
      }
      console.error('Vault upload error:', e);
      setUploadError(errorMsg);
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

    // Shared validation (size + type) with exact guidance — same messages on
    // every upload surface.
    const validationError = validateVaultFile(file);
    if (validationError) {
      setUploadError(validationError);
      toast.error(validationError.split('. ')[0]);
      return;
    }

    setUploadFile(file);
    setUploadError(null); // clear any previous error when a fresh file is chosen
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
    uploadError,
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
