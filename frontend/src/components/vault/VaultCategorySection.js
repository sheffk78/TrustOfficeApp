import { FileText } from 'lucide-react';
import VaultDocumentCard from './VaultDocumentCard';

/**
 * Renders a category group with its label, count, and grid of document cards.
 */
export default function VaultCategorySection({
  categoryKey,
  categoryData,
  selectedTrustId,
  copiedLinkId,
  onCopyLink,
  onDelete,
  onDownload,
  categoryIcons,
}) {
  const Icon = categoryIcons[categoryKey] || FileText;
  return (
    <div>
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
        <Icon className="w-4 h-4" />
        {categoryData.label} ({categoryData.documents.length})
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {categoryData.documents.map((doc) => (
          <VaultDocumentCard
            key={doc.doc_id}
            doc={doc}
            selectedTrustId={selectedTrustId}
            copiedLinkId={copiedLinkId}
            onCopyLink={onCopyLink}
            onDelete={onDelete}
            onDownload={onDownload}
          />
        ))}
      </div>
    </div>
  );
}
