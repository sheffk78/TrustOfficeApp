import { useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Download } from 'lucide-react';
import { API, getAuthHeaders } from '@/utils/api';

/**
 * VaultPreviewModal — in-app first-page preview of an uploaded vault document.
 *
 * The backend download endpoint requires authentication (Bearer token), which
 * native <embed>/<img> tags cannot send. So we fetch the file with auth
 * headers, create a blob URL, and use that as the embed/img src instead.
 */
export default function VaultPreviewModal({ doc, open, onOpenChange }) {
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [blobUrl, setBlobUrl] = useState(null);

  const isPdf = (doc?.file_content_type || '').includes('pdf') ||
    (doc?.file_name || '').toLowerCase().endsWith('.pdf');
  const isImage = (doc?.file_content_type || '').startsWith('image/') ||
    /\.(png|jpe?g|gif|webp)$/i.test(doc?.file_name || '');
  const previewable = Boolean(doc && doc.storage_provider === 'trustoffice' && (isPdf || isImage));
  const downloadUrl = `${API}/vault/documents/${doc?.doc_id}/download`;

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
        const token = localStorage.getItem('auth_token');
        const response = await fetch(`${API}/vault/documents/${doc.doc_id}/download?inline=true`, {
          credentials: 'include',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
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

  if (!doc) return null;

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
              <a
                href={downloadUrl}
                download={doc.file_name}
                onClick={(e) => {
                  // Native anchor can't carry the Bearer header — do an
                  // authenticated fetch and trigger a client-side download.
                  e.preventDefault();
                  const token = localStorage.getItem('auth_token');
                  fetch(downloadUrl, {
                    credentials: 'include',
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                  })
                    .then((r) => { if (!r.ok) throw new Error(r.status); return r.blob(); })
                    .then((b) => {
                      const url = URL.createObjectURL(b);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = doc.file_name || 'document';
                      document.body.appendChild(a);
                      a.click();
                      a.remove();
                      setTimeout(() => URL.revokeObjectURL(url), 5000);
                    })
                    .catch((err) => console.error('Download failed:', err));
                }}
                className="text-xs text-navy hover:text-navy/70 flex items-center gap-1"
              >
                <Download className="w-3.5 h-3.5" /> Download
              </a>
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
                <a href={downloadUrl} download={doc.file_name} onClick={(e) => {
                  e.preventDefault();
                  const token = localStorage.getItem('auth_token');
                  fetch(downloadUrl, {
                    credentials: 'include',
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                  })
                    .then((r) => { if (!r.ok) throw new Error(r.status); return r.blob(); })
                    .then((b) => {
                      const url = URL.createObjectURL(b);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = doc.file_name || 'document';
                      document.body.appendChild(a);
                      a.click();
                      a.remove();
                      setTimeout(() => URL.revokeObjectURL(url), 5000);
                    })
                    .catch((err) => console.error('Download failed:', err));
                }} className="btn btn-primary btn-sm">
                  <Download className="w-3.5 h-3.5 mr-1" /> Download to view
                </a>
              </div>
            ) : loading ? (
              <div className="h-full flex items-center justify-center">
                <p className="text-sm text-muted-foreground">Loading preview…</p>
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
                <p className="text-sm text-muted-foreground">Loading preview…</p>
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
