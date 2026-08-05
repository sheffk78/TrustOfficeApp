import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { format, parseISO } from 'date-fns';
import {
  File, ExternalLink, Download, Trash2, Copy, Check, Bot,
} from 'lucide-react';
import AnalysisStatusBadge from '@/components/AnalysisStatusBadge';
import BankStatementBadge from '@/components/BankStatementBadge';

/**
 * Renders a single vault document card with file/storage indicators,
 * analysis badges, copy/download/open actions, and AI summarise link.
 */
export default function VaultDocumentCard({
  doc,
  selectedTrustId,
  copiedLinkId,
  onCopyLink,
  onDelete,
  onDownload,
}) {
  const isUploadedFile = doc.storage_provider === 'trustoffice';

  return (
    <div className="card-trust p-4 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between mb-2">
        <p className="font-semibold text-navy text-sm line-clamp-2">{doc.title}</p>
        <button onClick={() => onDelete(doc.doc_id)} className="text-muted-foreground hover:text-rust ml-2 flex-shrink-0">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* File indicator */}
      {isUploadedFile ? (
        <div className="flex items-center gap-1.5 text-xs text-success bg-success/10 rounded px-2 py-1 mb-2 w-fit">
          <File className="w-3 h-3" />
          {doc.file_name} {doc.file_size && `(${doc.file_size})`}
        </div>
      ) : doc.file_name ? (
        <p className="text-xs text-muted-foreground mb-2">{doc.file_name}</p>
      ) : null}

      {doc.description && <p className="text-xs text-muted-foreground mb-2 line-clamp-2">{doc.description}</p>}
      <div className="flex flex-wrap gap-1 mb-3">
        {doc.tags?.map((tag, i) => (
          <span key={i} className="text-[10px] bg-navy/5 text-navy/60 px-1.5 py-0.5 rounded">{tag}</span>
        ))}
      </div>
      {/* Analysis status badge for trust instruments and amendments */}
      <div className="mb-2">
        <AnalysisStatusBadge trustId={selectedTrustId} docId={doc.doc_id} category={doc.category} />
      </div>
      {/* Bank statement extraction badge + link-to-account actions */}
      {doc.category === 'bank_statement' && (
        <div className="mb-2">
          <BankStatementBadge trustId={selectedTrustId} vaultDocId={doc.doc_id} />
        </div>
      )}
      <div className="flex items-center justify-between">
        {isUploadedFile ? (
          <button
            onClick={() => onDownload(doc.doc_id, doc.file_name)}
            className="text-xs text-navy hover:text-navy/70 flex items-center gap-1"
          >
            <Download className="w-3 h-3" /> Download
          </button>
        ) : doc.storage_url ? (
          <div className="flex items-center gap-3">
            <a href={doc.storage_url} target="_blank" rel="noopener noreferrer" className="text-xs text-navy hover:text-navy/70 flex items-center gap-1">
              <ExternalLink className="w-3 h-3" /> Open
            </a>
            <button
              onClick={() => onCopyLink(doc)}
              className="text-xs text-navy hover:text-navy/70 flex items-center gap-1"
              title="Copy external link"
              data-testid={`copy-link-${doc.doc_id}`}
            >
              {copiedLinkId === doc.doc_id ? (
                <><Check className="w-3 h-3" /> Copied</>
              ) : (
                <><Copy className="w-3 h-3" /> Copy Link</>
              )}
            </button>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">No link</span>
        )}
        <span className="text-[10px] text-muted-foreground">
          {doc.date ? format(parseISO(doc.date), 'MMM d, yyyy') : ''}
        </span>
      </div>
      {/* AI CTA — Summarize this document */}
      <div className="mt-2">
        <Link
          to={`/trust-assistant?prompt=${encodeURIComponent(`Summarize the document "${doc.title}" in the trust vault and explain its key provisions and relevance to the trust.`)}`}
          className="inline-flex items-center gap-1 px-2 py-1 text-xs text-gold hover:bg-gold/10 transition-colors"
          data-testid={`ta-summarize-${doc.doc_id}`}
        >
          <Bot className="w-3.5 h-3.5" />
          Summarize this document
        </Link>
      </div>
      {doc.needs_renewal && doc.expiration_date && (
        <div className="mt-2 text-[10px] text-warning bg-warning/5 border border-warning/10 rounded px-2 py-1">
          Renews {format(parseISO(doc.expiration_date), 'MMM d, yyyy')}
        </div>
      )}
    </div>
  );
}
