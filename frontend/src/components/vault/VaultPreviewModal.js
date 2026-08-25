import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Download } from 'lucide-react';

/**
 * VaultPreviewModal — in-app first-page preview of an uploaded vault document.
 * PDFs render via the browser's native <embed>; other types show a fallback
 * with a download option.
 */
export default function VaultPreviewModal({ doc, open, onOpenChange }) {
  const [failed, setFailed] = useState(false);

  if (!doc) return null;
  const isPdf = (doc.file_content_type || '').includes('pdf') ||
    (doc.file_name || '').toLowerCase().endsWith('.pdf');
  const isImage = (doc.file_content_type || '').startsWith('image/') ||
    /\.(png|jpe?g|gif|webp)$/i.test(doc.file_name || '');
  const src = `${process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app'}/api/vault/documents/${doc.doc_id}/download?inline=true`;

  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!o) setFailed(false); onOpenChange(o); }}>
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
                href={src}
                download={doc.file_name}
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
            {isPdf && !failed ? (
              <embed
                src={src}
                type="application/pdf"
                className="w-full h-full"
                title={`Preview of ${doc.title}`}
                onError={() => setFailed(true)}
              />
            ) : isImage && !failed ? (
              <img src={src} alt={`Preview of ${doc.title}`} className="max-w-full max-h-full mx-auto" onError={() => setFailed(true)} />
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 gap-3">
                <p className="text-sm text-muted-foreground">
                  No inline preview available for this file type{failed ? ' (preview failed to load)' : ''}.
                </p>
                <a href={src} download={doc.file_name} className="btn btn-primary btn-sm">
                  <Download className="w-3.5 h-3.5 mr-1" /> Download to view
                </a>
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
