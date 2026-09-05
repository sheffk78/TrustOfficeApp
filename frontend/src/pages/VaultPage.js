import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { FolderOpen, Plus, Search } from 'lucide-react';
import PageHelpButton from '@/components/PageHelpButton';

import {
  CATEGORY_ICONS,
  DOC_CATEGORIES,
} from '@/components/vault/vaultConstants';
import { useVaultUpload } from '@/components/vault/useVaultUpload';
import VaultAddForm from '@/components/vault/VaultAddForm';
import VaultCategorySection from '@/components/vault/VaultCategorySection';
import CriticalDocumentsAlert from '@/components/vault/CriticalDocumentsAlert';
import CloudBackupSection from '@/components/vault/CloudBackupSection';
import { deleteDocument, downloadDocument } from '@/components/vault/vaultOperations';

export default function VaultPage() {
  const { selectedTrust } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [byCategory, setByCategory] = useState({});
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('');
  const [copiedLinkId, setCopiedLinkId] = useState(null);
  const [criticalDismissed, setCriticalDismissed] = useState(false);
  const copyTimeoutRef = useRef(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (activeCategory) params.append('category', activeCategory);
      if (search) params.append('search', search);

      const [docRes, sumRes] = await Promise.all([
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/vault/documents?${params.toString()}`),
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/vault/summary`),
      ]);

      if (docRes.ok) {
        const dData = await docRes.json();
        setDocuments(dData.documents || []);
        setByCategory(dData.by_category || {});
      } else {
        setDocuments([]);
        setByCategory({});
      }

      if (sumRes.ok) {
        const sData = await sumRes.json();
        setSummary(sData);
      }
    } catch (e) {
      console.error('Failed to reload vault data:', e);
    } finally {
      setLoading(false);
    }
  }, [selectedTrust, activeCategory, search]);

  useEffect(() => {
    if (selectedTrust) {
      setCriticalDismissed(false);
      loadData();
    }
  }, [selectedTrust, activeCategory]); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = useVaultUpload(selectedTrust, loadData);

  /** Copy a doc's external storage URL to the clipboard. */
  const handleCopyLink = useCallback((doc) => {
    if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    navigator.clipboard.writeText(doc.storage_url).then(() => {
      setCopiedLinkId(doc.doc_id);
      toast.success('Link copied to clipboard');
      copyTimeoutRef.current = setTimeout(() => setCopiedLinkId(null), 2000);
    }).catch(() => {
      toast.error('Could not copy link to clipboard. Please try copying it manually.');
    });
  }, []);

  const handleDelete = useCallback((id) => deleteDocument(id, loadData), [loadData]);
  const handleDownload = useCallback((docId, fileName) => downloadDocument(docId, fileName), []);

  if (!selectedTrust) {
    return (
      <div className="card-trust p-12 flex flex-col items-center justify-center">
        <FolderOpen className="w-12 h-12 text-muted-foreground/40 mb-3" />
        <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
        <p className="text-sm text-muted-foreground">Choose a trust to view document vault.</p>
      </div>
    );
  }

  const categories = summary?.categories || DOC_CATEGORIES;
  const hasDocuments = Object.keys(byCategory).length > 0;

  return (
    <>
      <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Trust Document Vault</h1>
              <p className="page-subtitle">Store, organize, and access trust documents — upload files, manage categories, and share with beneficiaries</p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'Store, organize, and access all trust documents in one place' },
                  { text: 'Upload files, manage categories, and control access' },
                  { text: 'Share documents with beneficiaries and advisors securely' },
                ]}
                taPrompt="Help me understand the Document Vault and how to upload files"
              />
              <Button className="btn-primary" onClick={() => { upload.setShowAdd(!upload.showAdd); upload.setAddMode('upload'); }}>
                <Plus className="w-4 h-4 mr-2" />
                Add Document
              </Button>
            </div>
          </div>

          {/* Missing Critical Alert */}
          <CriticalDocumentsAlert
            missingCritical={!criticalDismissed ? summary?.missing_critical : null}
            onDismiss={() => setCriticalDismissed(true)}
          />

          {/* Cloud Backup */}
          <CloudBackupSection selectedTrust={selectedTrust} />

          {/* Search + Category Filter */}
          <div className="flex gap-2 mb-6">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search documents..."
                value={search}
                onChange={e => { setSearch(e.target.value); if (!e.target.value) loadData(); }}
                onKeyDown={e => e.key === 'Enter' && loadData()}
                className="pl-9"
              />
            </div>
            <select
              value={activeCategory}
              onChange={e => { setActiveCategory(e.target.value); }}
              className="input-trust text-sm"
            >
              <option value="">All Categories</option>
              {Object.entries(categories).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>

          {/* Add Form */}
          {upload.showAdd && (
            <VaultAddForm
              addMode={upload.addMode}
              setAddMode={upload.setAddMode}
              form={upload.form}
              setForm={upload.setForm}
              uploadFile={upload.uploadFile}
              handleFileSelect={upload.handleFileSelect}
              clearUploadFile={upload.clearUploadFile}
              handleUpload={upload.handleUpload}
              addDocument={upload.addDocument}
              uploading={upload.uploading}
              uploadProgress={upload.uploadProgress}
              uploadError={upload.uploadError}
              resetForm={upload.resetForm}
              fileInputRef={upload.fileInputRef}
              categories={categories}
            />
          )}

          {/* Document Grid by Category */}
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map(i => <div key={i} className="h-20 card-trust animate-pulse" />)}
            </div>
          ) : !hasDocuments ? (
            <div className="card-trust p-12 flex flex-col items-center justify-center">
              <FolderOpen className="w-12 h-12 text-muted-foreground/30 mb-3" />
              <h2 className="text-lg font-semibold text-navy mb-1">Vault is empty</h2>
              <p className="text-sm text-muted-foreground mb-4">Upload your trust documents or link to files stored externally.</p>
              <Button className="btn-primary" onClick={() => { upload.setShowAdd(true); upload.setAddMode('upload'); }}>Upload First Document</Button>
            </div>
          ) : (
            <div className="space-y-8">
              {Object.entries(byCategory).map(([cat, data]) => (
                <VaultCategorySection
                  key={cat}
                  categoryKey={cat}
                  categoryData={data}
                  selectedTrustId={selectedTrust?.trust_id}
                  copiedLinkId={copiedLinkId}
                  onCopyLink={handleCopyLink}
                  onDelete={handleDelete}
                  onDownload={handleDownload}
                  categoryIcons={CATEGORY_ICONS}
                />
              ))}
            </div>
          )}
        </>
  );
}
