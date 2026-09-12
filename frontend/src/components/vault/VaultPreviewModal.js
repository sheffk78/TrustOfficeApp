import { useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Download } from 'lucide-react';
import { API, getAuthHeaders } from '@/utils/api';
import { isStepUpRequired } from '@/utils/twoFactor';

/**
 * VaultPreviewModal — in-app first-page preview of an uploaded vault document.
 *
 * The backend download endpoint requires authentication (Bearer token), which
 * native <embed>/<img> tags cannot send. So we fetch the file with auth
 * headers, create a blob URL, and use that as the embed/img src instead.
 *
 * 2FA step-up: with 2FA enabled the download can answer 403
 * {detail:'2fa_stepup_required'}. onStepUpRequired lets the parent VaultPage
 * open the step-up modal and replay the download with the X-2FA-Code header.
 */
export default function VaultPreviewModal({ doc, open, onOpenChange, onStepUpRequired }) {
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [blobUrl, setBlobUrl] = useState(null);

  const isPdf = (doc?.file_content_type || '').includes('pdf') ||
    (doc?.file_name || '').toLowerCase().endsWith('.pdf');
  const isImage = (doc?.file_content_type || '').startsWith('image/') ||
    /\.(png|jpe?g|gif|webp)$/i.test(doc?.file_name || '');
  const previewable = Boolean(doc && doc.storage_provider === 'trustoffice' && (isPdf || isImage));
  const downloadUrl = `${API}/vault/documents/${doc?.doc_id}/download`;

  // Shared download implementation (preview + save both use it).
  // Returns the raw fetch Response so callers can inspect the status.
  const doDownload = (inline) => {
    const token = localStorage.getItem('auth_token');
    return fetch(`${downloadUrl}${inline ? '?inline=true' : ''}`, {
      credentials: 'include',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  };

  const isStepUp403 = async (response) => {
    if (!response || response.status !== 403) return false;
    try {
      const body = await response.clone().json();
      return isStepUpRequired(body.detail);
    } catch {
      return false;
    }
  };

  // Fetch the file with auth and create an object URL for the embed/img.
  useEffect(() => {
    if (!open || !previewable) return undefined;

    let cancelled = false;
    let objectUrl = null;

    async function loadPreview() {
      setLoading(true);
      setFailed(false);
      try {
        // fetchWithAuth forces JSON content-type; use raw fetch with auth headers.
        const response = await doDownload(true);
        if (await isStepUp403(response)) {
          // Protected action needs a fresh code; the parent's step-up modal
          // handles the retry, so skip the preview rather than erroring.
          if (!cancelled) setFailed(true);
          return;
        }
        if (!response.ok) throw new Error(`Preview request failed (${response.status})`);
        const blob = await response.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      } catch (err) {
        console.error('Vault preview failed to load:', err);
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadPreview();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [open, previewable, doc?.doc_id]);

  // Revoke any lingering blob URL when the modal closes.
  useEffect(() => () => {
    setBlobUrl((url) => {
      if (url) URL.revokeObjectURL(url);
      return null;
    });
  }, []);

  // Client-side download with 2FA step-up support: on 403 2fa_stepup_required
  // hand the original request to the parent (step-up modal) via onStepUpRequired.
  const handleDownloadClick = async (e) => {
    e.preventDefault();
    try {
      const response = await doDownload(false);
      if (await isStepUp403(response)) {
        if (onStepUpRequired) onStepUpRequired(() => doDownload(false), doc);
        return;
      }
      if (!response.ok) throw new Error(response.status);
      const b = await response.blob();
      const url = URL.createObjectURL(b);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.file_name || 'document';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  if (!doc) return null;

  const downloadLink = (label, testid, className) => (
    <a
      href={downloadUrl}
      download={doc.file_name}
      onClick={handleDownloadClick}
      data-testid={testid}
      className={className}
    >
      <Download className="w-3.5 h-3.5" /> {label}
    </a>
  );

  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!o) { setFailed(false); setBlobUrl((u) => { if (u) URL.revokeObjectURL(u); return null; }); } onOpenChange(o); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-navy/60 z-50" />
        <Dialog.Content
          className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[92vw] max-w-3xl h-[85vh] bg-white rounded-lg shadow-xl z-50 flex flex-col overflow-hidden"
          data-testid="vault-preview-modal"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <Dialog.Title className="font-serif text-navy text-base truncate pr-4">{doc.title}</Dialog.Title>
            <div className="flex items-center gap-3 flex-shrink-0">
              {downloadLink('Download', 'vault-preview-download-btn', 'text-xs text-navy hover:text-navy/70 flex items-center gap-1')}
              <Dialog.Close asChild>
                <button aria-label="Close preview" className="text-muted-foreground hover:text-navy">
                  <X className="w-4 h-4" />
                </button>
              </Dialog.Close>
            </div>
          </div>

          <div className="flex-1 bg-subtle-bg overflow-auto">
            {!previewable || failed ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 gap-3">
                <p className="text-sm text-muted-foreground">
                  No inline preview available for this file type{failed ? ' (preview failed to load)' : ''}.
                </p>
                {downloadLink('Download to view', 'vault-preview-download-alt-btn', 'btn btn-primary btn-sm')}
              </div>
            ) : loading ? (
              <div className="h-full flex items-center justify-center">
                <p className="text-sm text-muted-foreground">Loading preview...</p>
              </div>
            ) : isPdf && blobUrl ? (
              <embed
                src={blobUrl}
                type="application/pdf"
                className="w-full h-full"
                title={`Preview of ${doc.title}`}
              />
            ) : isImage && blobUrl ? (
              <img src={blobUrl} alt={`Preview of ${doc.title}`} className="max-w-full max-h-full mx-auto" />
            ) : (
              <div className="h-full flex items-center justify-center">
                <p className="text-sm text-muted-foreground">Loading preview...</p>
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}