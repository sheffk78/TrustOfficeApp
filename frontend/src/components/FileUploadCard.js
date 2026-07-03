import React, { useState, useRef, useCallback } from 'react';
import { Upload, File as FileIcon, X, Check, Loader2, FolderOpen } from 'lucide-react';

const VAULT_CATEGORIES = [
  { value: 'trust_instrument', label: 'Trust Instrument / Governing Document' },
  { value: 'amendment', label: 'Trust Amendment / Restatement' },
  { value: 'schedule_a', label: 'Schedule A (Assets)' },
  { value: 'minutes', label: 'Minutes of Meetings' },
  { value: 'tax_return', label: 'Tax Return (Form 1041)' },
  { value: 'k1', label: 'Schedule K-1' },
  { value: 'ein_letter', label: 'EIN Confirmation Letter (CP575)' },
  { value: 'financial_statement', label: 'Financial Statement / Accounting' },
  { value: 'appraisal', label: 'Asset Appraisal / Valuation' },
  { value: 'notice', label: 'Beneficiary Notice / Communication' },
  { value: 'insurance', label: 'Insurance Policy / Rider' },
  { value: 'deed', label: 'Deed / Property Document' },
  { value: 'bank_statement', label: 'Bank / Investment Statement' },
  { value: 'legal_opinion', label: 'Legal Opinion / Attorney Letter' },
  { value: 'court_order', label: 'Court Order / Judgment' },
  { value: 'other', label: 'Other' },
];

const formatFileSize = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const FileUploadCard = ({ trustId, onUploadComplete, onCancel }) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('trust_instrument');
  const [description, setDescription] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null); // { success, docId, error }
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileSelect = useCallback((file) => {
    if (!file) return;
    if (file.size > 16 * 1024 * 1024) {
      setUploadResult({ success: false, error: 'File too large. Maximum size is 16MB.' });
      return;
    }
    setSelectedFile(file);
    // Auto-fill title from filename if empty
    if (!title) {
      const nameWithoutExt = file.name.replace(/\.[^/.]+$/, '');
      setTitle(nameWithoutExt.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()));
    }
    setUploadResult(null);
  }, [title]);

  const handleFileInputChange = (e) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileSelect(file);
  }, [handleFileSelect]);

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    if (!title.trim()) return;

    setUploading(true);
    setUploadResult(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('title', title.trim());
      formData.append('category', category);
      if (description) formData.append('description', description);
      formData.append('tags', '');
      formData.append('needs_renewal', 'false');

      const token = localStorage.getItem('auth_token');
      const backendUrl = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app/api';
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);

      const res = await fetch(`${backendUrl}/trusts/${trustId}/vault/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!res.ok) {
        let errorMsg = 'Upload failed';
        try {
          const errData = await res.json();
          errorMsg = errData.detail || errorMsg;
        } catch {
          errorMsg = `Upload failed (${res.status})`;
        }
        throw new Error(errorMsg);
      }

      let data;
      try {
        data = await res.json();
      } catch {
        data = {};
      }

      setUploadResult({ success: true, docId: data.doc_id, title: title.trim(), category });
      if (onUploadComplete) {
        onUploadComplete({ success: true, docId: data.doc_id, title: title.trim(), category, fileName: selectedFile.name });
      }
    } catch (err) {
      const errorMsg = err.name === 'AbortError'
        ? 'Upload timed out. The file may be too large or your connection is slow.'
        : err.message || 'Upload failed';
      setUploadResult({ success: false, error: errorMsg });
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setTitle('');
    setDescription('');
    setUploadResult(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const isComplete = uploadResult?.success;

  return (
    <div className="file-upload-card card-trust">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider border bg-navy/10 text-navy">
          <FolderOpen className="w-3 h-3" />
          Upload to Vault
        </span>
        {!isComplete && (
          <button
            onClick={onCancel}
            className="ml-auto p-1 text-muted-foreground hover:text-rust transition-colors"
            title="Cancel"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {isComplete ? (
        /* Success state */
        <div className="py-2">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-full bg-gold/10 flex items-center justify-center">
              <Check className="w-4 h-4 text-gold" />
            </div>
            <div>
              <p className="font-serif font-semibold text-sm text-foreground">
                Uploaded to Vault
              </p>
              <p className="font-mono text-xs text-muted-foreground">
                {uploadResult.title} saved to {VAULT_CATEGORIES.find(c => c.value === uploadResult.category)?.label || 'documents'}
              </p>
            </div>
          </div>
          <button
            onClick={handleReset}
            className="text-[10px] font-mono uppercase tracking-wider text-navy hover:text-navy/70 transition-colors mt-2"
          >
            Upload Another
          </button>
        </div>
      ) : (
        <>
          {/* File drop zone / selection */}
          {!selectedFile ? (
            <label
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              className={`file-drop-zone ${dragOver ? 'file-drop-zone-active' : ''}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileInputChange}
                accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.jpg,.jpeg,.png,.gif,.webp,.tiff"
                className="hidden"
              />
              <div className="flex flex-col items-center gap-2 py-4 cursor-pointer">
                <Upload className="w-6 h-6 text-muted-foreground/50" />
                <p className="text-sm font-medium text-foreground">
                  {dragOver ? 'Drop file here' : 'Click to upload or drag and drop'}
                </p>
                <p className="font-mono text-[10px] text-muted-foreground/60">
                  PDF, images, Word, Excel, text — max 16MB
                </p>
              </div>
            </label>
          ) : (
            /* Selected file preview */
            <div className="file-selected-preview">
              <div className="flex items-center gap-2 p-3 border border-navy/10 bg-navy/5">
                <FileIcon className="w-5 h-5 text-navy flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{selectedFile.name}</p>
                  <p className="font-mono text-[10px] text-muted-foreground">{formatFileSize(selectedFile.size)}</p>
                </div>
                <button
                  onClick={handleReset}
                  className="p-1 text-muted-foreground hover:text-rust transition-colors"
                  title="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Metadata fields */}
              <div className="mt-3 space-y-3">
                {/* Title */}
                <div>
                  <label className="block text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">
                    Title
                  </label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Document title"
                    className="w-full px-3 py-2 text-sm border border-navy/10 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-gold/40"
                  />
                </div>

                {/* Category */}
                <div>
                  <label className="block text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">
                    Category
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-navy/10 bg-background text-foreground focus:outline-none focus:border-gold/40"
                  >
                    {VAULT_CATEGORIES.map(cat => (
                      <option key={cat.value} value={cat.value}>{cat.label}</option>
                    ))}
                  </select>
                </div>

                {/* Description (optional) */}
                <div>
                  <label className="block text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">
                    Description <span className="text-muted-foreground/40">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Brief description of the document"
                    className="w-full px-3 py-2 text-sm border border-navy/10 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-gold/40"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Error feedback */}
          {uploadResult && !uploadResult.success && (
            <div className="mt-3 p-2 border border-rust/20 bg-rust/5 flex items-start gap-2">
              <X className="w-3.5 h-3.5 text-rust flex-shrink-0 mt-0.5" />
              <p className="font-mono text-xs text-rust">{uploadResult.error}</p>
            </div>
          )}

          {/* Upload button */}
          {selectedFile && !uploading && !uploadResult?.success && (
            <div className="flex items-center gap-2 pt-3 mt-3 border-t border-navy/10">
              <button
                onClick={handleUpload}
                disabled={!title.trim()}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider bg-gold/10 text-gold border border-gold/30 hover:bg-gold hover:text-navy transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Upload className="w-3.5 h-3.5" />
                Upload to Vault
              </button>
              <button
                onClick={handleReset}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider bg-navy/5 text-navy border border-navy/20 hover:bg-navy/10 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
                Cancel
              </button>
            </div>
          )}

          {/* Uploading state */}
          {uploading && (
            <div className="flex items-center gap-2 pt-3 mt-3 border-t border-navy/10">
              <Loader2 className="w-4 h-4 animate-spin text-gold" />
              <span className="font-mono text-xs text-muted-foreground">Uploading to vault...</span>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default FileUploadCard;