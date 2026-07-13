import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import {
  FolderOpen, Plus, FileText, Calendar, Link as LinkIcon,
  Search, AlertTriangle, CheckCircle2, ExternalLink,
  Trash2, Tag, Shield, FileCheck, Upload, Download,
  File, X, CloudUpload, Link2, Copy, Check, Bot
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import PageHelpButton from '@/components/PageHelpButton';
import AnalysisStatusBadge from '@/components/AnalysisStatusBadge';
import BankStatementBadge from '@/components/BankStatementBadge';

const CATEGORY_ICONS = {
  trust_instrument: Shield,
  amendment: FileText,
  schedule_a: FolderOpen,
  minutes: FileText,
  tax_return: FileText,
  k1: FileText,
  ein_letter: FileCheck,
  financial_statement: FileText,
  appraisal: FileText,
  notice: AlertTriangle,
  insurance: Shield,
  deed: FileText,
  bank_statement: FileText,
  legal_opinion: Shield,
  court_order: FileText,
  other: FileText,
};

const DOC_CATEGORIES = {
  trust_instrument: "Trust Instrument / Governing Document",
  amendment: "Trust Amendment / Restatement",
  schedule_a: "Trust Assets",
  minutes: "Minutes of Meetings",
  tax_return: "Tax Return (Form 1041)",
  k1: "Schedule K-1",
  ein_letter: "EIN Confirmation Letter (CP575)",
  financial_statement: "Financial Statement / Accounting",
  appraisal: "Asset Appraisal / Valuation",
  notice: "Beneficiary Notice / Communication",
  insurance: "Insurance Policy / Rider",
  deed: "Deed / Property Document",
  bank_statement: "Bank / Investment Statement",
  legal_opinion: "Legal Opinion / Attorney Letter",
  court_order: "Court Order / Judgment",
  other: "Other",
};

function Gavel(props) { return <svg {...props} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 13l6-6"/><circle cx="8" cy="8" r="6"/><path d="M4 20l6-6"/></svg>; }

const ACCEPTED_TYPES = '.pdf,.jpg,.jpeg,.png,.gif,.webp,.tiff,.tif,.doc,.docx,.xls,.xlsx,.txt';

export default function VaultPage() {
  const { selectedTrust } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [byCategory, setByCategory] = useState({});
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [addMode, setAddMode] = useState('upload'); // 'upload' or 'link'
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [copiedLinkId, setCopiedLinkId] = useState(null);
  const [criticalDismissed, setCriticalDismissed] = useState(false);
  const fileInputRef = useRef(null);
  const copyTimeoutRef = useRef(null);

  const [form, setForm] = useState({
    title: '',
    category: 'trust_instrument',
    date: '',
    description: '',
    storage_provider: 'google_drive',
    storage_url: '',
    storage_path: '',
    file_name: '',
    tags: '',
    expiration_date: '',
    needs_renewal: false,
  });

  const [uploadFile, setUploadFile] = useState(null);

  useEffect(() => {
    if (selectedTrust) {
      setCriticalDismissed(false);
      loadData();
    }
  }, [selectedTrust, activeCategory]);

  const loadData = async () => {
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
      // Silently fail — loadData is a background refresh, not a user action
      console.error('Failed to reload vault data:', e);
    } finally {
      setLoading(false);
    }
  };

  const addDocument = async () => {
    if (addMode === 'link' && form.storage_url && !form.storage_url.startsWith('https://')) {
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
  };

  const handleUpload = async () => {
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
      const timeoutId = setTimeout(() => controller.abort(), 120000); // 2 min timeout for large files

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
        // Network-level error (CORS block, DNS, offline, etc.)
        throw new Error('Could not reach the server. Please check your internet connection and try again.');
      }
      clearTimeout(timeoutId);

      if (!res.ok) {
        let errorMsg = 'Upload failed';
        try {
          const errData = await res.json();
          errorMsg = errData.detail || errorMsg;
        } catch (e) {
          // Response wasn't JSON — use status text
          errorMsg = `Upload failed (${res.status})`;
        }
        throw new Error(errorMsg);
      }

      let data;
      try {
        data = await res.json();
      } catch (e) {
        // Response wasn't JSON but upload succeeded (status OK)
        data = {};
      }

      setUploadProgress('Upload complete!');
      toast.success('File uploaded to vault');
      resetForm();
      loadData();
    } catch (e) {
      setUploadProgress('');
      // Provide more specific error messages for common failure modes
      let errorMsg = e.message || 'Upload failed';
      if (errorMsg === 'Failed to fetch' || errorMsg.includes('Could not reach the server')) {
        errorMsg = 'Could not reach the server. The file may be too large or your connection timed out. Please try again, or use "Link External" to store a link to the file instead.';
      }
      console.error('Vault upload error:', e);
      toast.error(errorMsg);
      // The backend may have saved the file before hitting a serialization error.
      // Refresh the vault list so the user sees the uploaded file if it landed.
      loadData();
    } finally {
      setUploading(false);
    }
  };

  const resetForm = () => {
    setShowAdd(false);
    setUploadFile(null);
    setAddMode('upload');
    setUploadProgress('');
    setForm({
      title: '', category: 'trust_instrument', date: '', description: '',
      storage_provider: 'google_drive', storage_url: '', storage_path: '',
      file_name: '', tags: '', expiration_date: '', needs_renewal: false,
    });
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Client-side size check (50MB — backend compresses PDFs down to 16MB)
    if (file.size > 50 * 1024 * 1024) {
      toast.error(`File too large (${(file.size / (1024*1024)).toFixed(1)}MB). Maximum is 50MB. PDFs are automatically compressed.`);
      return;
    }

    setUploadFile(file);
    // Auto-fill title from filename if empty
    if (!form.title) {
      const name = file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
      setForm(f => ({ ...f, title: name, file_name: file.name }));
    } else {
      setForm(f => ({ ...f, file_name: file.name }));
    }

    // Auto-detect EIN Confirmation Letter (CP575) from filename
    const lowerName = file.name.toLowerCase();
    if (lowerName.includes('cp575') || lowerName.includes('ein') || lowerName.includes('ein_letter') || lowerName.includes('ein-confirmation') || lowerName.includes('irs') && lowerName.includes('letter')) {
      setForm(f => ({ ...f, category: 'ein_letter' }));
    }
  };

  const deleteDocument = async (id) => {
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
  };

  const downloadDocument = async (docId, fileName) => {
    try {
      const token = localStorage.getItem('auth_token');
      const API_BASE = (process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app') + '/api';
      const res = await fetch(`${API_BASE}/vault/documents/${docId}/download`, {
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
  };

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <div className="md:pl-64 pb-20 md:pb-0">
          <div className="pt-16 md:pt-8 ml-4 mr-4">
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded">
              <FolderOpen className="w-12 h-12 text-muted-foreground/40 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to view document vault.</p>
            </div>
          </div>
        </div>
        <MobileBottomNav />
      </div>
    );
  }

  const categories = summary?.categories || DOC_CATEGORIES;

  return (
    <div className="min-h-screen bg-subtle-bg">
      <Sidebar />
      <div className="md:pl-64 pb-20 md:pb-0 mobile-layout-offset">
        <div className="pt-16 md:pt-8 ml-4 mr-4">

          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Trust Document Vault</h1>
              <p className="page-subtitle">Store, organize, and access trust documents — upload files, manage categories, and share with beneficiaries</p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Store, organize, and access all trust documents in one place' },
                  { text: 'Upload files, manage categories, and control access' },
                  { text: 'Share documents with beneficiaries and advisors securely' },
                ]}
                taPrompt="Help me understand the Document Vault and how to upload files"
              />
              <Button onClick={() => { setShowAdd(!showAdd); setAddMode('upload'); }}>
                <Plus className="w-4 h-4 mr-2"/>
                Add Document
              </Button>
            </div>
          </div>

          {/* Missing Critical Alert */}
          {summary?.missing_critical && summary.missing_critical.length > 0 && !criticalDismissed && (
            <Card className="mb-6 border-warning/20 bg-warning/5">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="w-5 h-5 text-warning"/>
                  <h3 className="font-semibold text-warning">Critical Documents Missing</h3>
                  <button
                    onClick={() => setCriticalDismissed(true)}
                    className="ml-auto p-1 text-warning/40 hover:text-warning transition-colors"
                    title="Dismiss"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <ul className="text-sm text-warning space-y-1">
                  {summary.missing_critical.map((m, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-warning rounded-full"/>
                      {m.label} · {m.message}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {/* Search + Category Filter */}
          <div className="flex gap-2 mb-6">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-neutral-400"/>
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
          {showAdd && (
            <Card className="mb-6 border border-neutral-200">
              <CardContent className="p-4">
                {/* Mode Toggle - styled as tabs, not action buttons */}
                <div className="flex border-b border-neutral-200 mb-4">
                  <button
                    onClick={() => setAddMode('upload')}
                    className={`flex items-center gap-2 px-5 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                      addMode === 'upload'
                        ? 'border-navy text-navy'
                        : 'border-transparent text-neutral-500 hover:text-neutral-800'
                    }`}
                  >
                    <Upload className="w-4 h-4"/> Upload File
                  </button>
                  <button
                    onClick={() => setAddMode('link')}
                    className={`flex items-center gap-2 px-5 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                      addMode === 'link'
                        ? 'border-navy text-navy'
                        : 'border-transparent text-neutral-500 hover:text-neutral-800'
                    }`}
                  >
                    <Link2 className="w-4 h-4"/> Link External
                  </button>
                </div>

                <h3 className="font-semibold text-navy mb-3">
                  {addMode === 'upload' ? 'Upload a Document' : 'Add Document Reference'}
                </h3>

                {/* Upload Drop Zone */}
                {addMode === 'upload' && (
                  <div className="mb-4">
                    {!uploadFile ? (
                      <label
                        htmlFor="vault-file-upload"
                        className="flex flex-col items-center justify-center border-2 border-dashed border-navy/20 rounded p-8 cursor-pointer hover:border-navy hover:bg-subtle-bg transition-colors"
                      >
                        <CloudUpload className="w-10 h-10 text-muted-foreground/40 mb-2"/>
                        <p className="text-sm font-medium text-foreground">Click to upload or drag and drop</p>
                        <p className="text-xs text-muted-foreground mt-1">PDF, images, Word, Excel — up to 50MB (PDFs auto-compressed)</p>
                        <input
                          id="vault-file-upload"
                          ref={fileInputRef}
                          type="file"
                          accept={ACCEPTED_TYPES}
                          className="hidden"
                          onChange={handleFileSelect}
                        />
                      </label>
                    ) : (
                      <div className="flex items-center gap-3 bg-subtle-bg border border-navy/10 rounded p-3">
                        <File className="w-8 h-8 text-navy"/>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">{uploadFile.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {(uploadFile.size / 1024).toFixed(1)} KB
                            {uploadFile.size > 1024 * 1024 && ` (${(uploadFile.size / (1024*1024)).toFixed(1)} MB)`}
                          </p>
                        </div>
                        <button
                          onClick={() => { setUploadFile(null); setForm(f => ({...f, file_name: ''})); }}
                          className="text-muted-foreground hover:text-rust"
                        >
                          <X className="w-5 h-5"/>
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Common Fields */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                  <Input placeholder="Document title *" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
                  <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} className="input-trust text-sm">
                    {Object.entries(categories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <Input type="date" placeholder="Document date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} />
                  <Input placeholder="Tags (comma-separated)" value={form.tags} onChange={e => setForm({ ...form, tags: e.target.value })} />
                </div>

                {/* Link-specific fields */}
                {addMode === 'link' && (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                      <select value={form.storage_provider} onChange={e => setForm({ ...form, storage_provider: e.target.value })} className="input-trust text-sm">
                        <option value="google_drive">Google Drive</option>
                        <option value="dropbox">Dropbox</option>
                        <option value="onedrive">OneDrive</option>
                        <option value="local_server">Local Server</option>
                        <option value="cloud_url">Cloud URL</option>
                        <option value="physical">Physical / Paper</option>
                      </select>
                      <Input placeholder="File name" value={form.file_name} onChange={e => setForm({ ...form, file_name: e.target.value })} />
                    </div>
                    <div className="mb-3">
                      <Input placeholder="Storage URL or path (paste Google Drive link, Dropbox link, etc.)" value={form.storage_url} onChange={e => setForm({ ...form, storage_url: e.target.value })} />
                    </div>
                  </>
                )}

                <textarea placeholder="Description..." value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="input-trust w-full text-sm mb-3" rows={2} />
                {/* Expiration / Renewal - only relevant for documents that expire */}
                <div className="mb-3">
                  <label className="text-sm font-medium text-neutral-700 block mb-1.5">Expiration / Renewal Date (optional)</label>
                  <p className="text-xs text-neutral-500 mb-2">
                    For documents that have an expiration or renewal date, such as insurance policies, certifications, or licenses. Trust instruments and most legal documents do not expire, so you can skip this.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Input type="date" placeholder="Expires on" value={form.expiration_date} onChange={e => setForm({ ...form, expiration_date: e.target.value })} />
                    <div className="flex items-center gap-2">
                      <input type="checkbox" checked={form.needs_renewal} onChange={e => setForm({ ...form, needs_renewal: e.target.checked })} id="renew" />
                    <label htmlFor="renew" className="text-sm text-neutral-600">Remind me to renew before this date</label>
                  </div>
                </div>
                {form.needs_renewal && form.expiration_date && (
                  <p className="text-xs text-success bg-success/10 rounded px-2 py-1.5 mb-3">
                    You will receive a reminder email 30 days before this document expires.
                  </p>
                )}
                </div>

                {/* Upload progress */}
                {uploadProgress && (
                  <p className="text-sm text-warning mb-2">{uploadProgress}</p>
                )}

                <div className="flex gap-2">
                  <Button
                    onClick={addMode === 'upload' ? handleUpload : addDocument}
                    disabled={addMode === 'upload' ? uploading || !uploadFile : !form.title}
                  >
                    {addMode === 'upload' ? (
                      <>
                        <Upload className="w-4 h-4 mr-2"/>
                        {uploading ? 'Uploading...' : 'Upload to Vault'}
                      </>
                    ) : (
                      'Save to Vault'
                    )}
                  </Button>
                  <Button variant="outline" onClick={resetForm} className="btn-secondary">Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Document Grid by Category */}
          {loading ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-20 bg-white border border-neutral-200 rounded animate-pulse"/>)}
            </div>
          ) : Object.keys(byCategory).length === 0 ? (
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded">
              <FolderOpen className="w-12 h-12 text-muted-foreground/30 mb-3"/>
              <h2 className="text-lg font-semibold text-navy mb-1">Vault is empty</h2>
              <p className="text-sm text-neutral-600 mb-4">Upload your trust documents or link to files stored externally.</p>
              <Button onClick={() => { setShowAdd(true); setAddMode('upload'); }}>Upload First Document</Button>
            </div>
          ) : (
            <div className="space-y-8">
              {Object.entries(byCategory).map(([cat, data]) => {
                const Icon = CATEGORY_ICONS[cat] || FileText;
                return (
                  <div key={cat}>
                    <h3 className="text-sm font-semibold text-neutral-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                      <Icon className="w-4 h-4"/>
                      {data.label} ({data.documents.length})
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {data.documents.map((doc) => (
                        <div key={doc.doc_id} className="bg-white border border-neutral-200 rounded p-4 hover:shadow-sm transition-shadow">
                          <div className="flex items-start justify-between mb-2">
                            <p className="font-semibold text-navy text-sm line-clamp-2">{doc.title}</p>
                            <button onClick={() => deleteDocument(doc.doc_id)} className="text-muted-foreground hover:text-rust ml-2 flex-shrink-0">
                              <Trash2 className="w-3.5 h-3.5"/>
                            </button>
                          </div>

                          {/* File indicator */}
                          {doc.storage_provider === 'trustoffice' ? (
                            <div className="flex items-center gap-1.5 text-xs text-success bg-success/10 rounded px-2 py-1 mb-2 w-fit">
                              <File className="w-3 h-3"/>
                              {doc.file_name} {doc.file_size && `(${doc.file_size})`}
                            </div>
                          ) : doc.file_name ? (
                            <p className="text-xs text-neutral-500 mb-2">{doc.file_name}</p>
                          ) : null}

                          {doc.description && <p className="text-xs text-neutral-600 mb-2 line-clamp-2">{doc.description}</p>}
                          <div className="flex flex-wrap gap-1 mb-3">
                            {doc.tags?.map((tag, i) => (
                              <span key={i} className="text-[10px] bg-navy/5 text-navy/60 px-1.5 py-0.5 rounded">{tag}</span>
                            ))}
                          </div>
                          {/* Analysis status badge for trust instruments and amendments */}
                          <div className="mb-2">
                            <AnalysisStatusBadge
                              trustId={selectedTrust?.trust_id}
                              docId={doc.doc_id}
                              category={doc.category}
                            />
                          </div>
                          {/* Bank statement extraction badge + link-to-account actions */}
                          {doc.category === 'bank_statement' && (
                            <div className="mb-2">
                              <BankStatementBadge trustId={selectedTrust?.trust_id} vaultDocId={doc.doc_id} />
                            </div>
                          )}
                          <div className="flex items-center justify-between">
                            {doc.storage_provider === 'trustoffice' ? (
                              <button
                                onClick={() => downloadDocument(doc.doc_id, doc.file_name)}
                                className="text-xs text-navy hover:text-navy/70 flex items-center gap-1"
                              >
                                <Download className="w-3 h-3"/> Download
                              </button>
                            ) : doc.storage_url ? (
                              <div className="flex items-center gap-3">
                                <a href={doc.storage_url} target="_blank" rel="noopener noreferrer" className="text-xs text-navy hover:text-navy/70 flex items-center gap-1">
                                  <ExternalLink className="w-3 h-3"/> Open
                                </a>
                                <button
                                  onClick={() => {
                                    // Clear any previous timeout to prevent flicker
                                    if (copyTimeoutRef.current) {
                                      clearTimeout(copyTimeoutRef.current);
                                    }
                                    navigator.clipboard.writeText(doc.storage_url).then(() => {
                                      setCopiedLinkId(doc.doc_id);
                                      toast.success('Link copied to clipboard');
                                      copyTimeoutRef.current = setTimeout(() => setCopiedLinkId(null), 2000);
                                    }).catch(() => {
                                      toast.error('Could not copy link to clipboard. Please try copying it manually.');
                                    });
                                  }}
                                  className="text-xs text-navy hover:text-navy/70 flex items-center gap-1"
                                  title="Copy external link"
                                  data-testid={`copy-link-${doc.doc_id}`}
                                >
                                  {copiedLinkId === doc.doc_id ? (
                                    <><Check className="w-3 h-3"/> Copied</>
                                  ) : (
                                    <><Copy className="w-3 h-3"/> Copy Link</>
                                  )}
                                </button>
                              </div>
                            ) : (
                              <span className="text-xs text-neutral-400">No link</span>
                            )}
                            <span className="text-[10px] text-neutral-400">
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
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}