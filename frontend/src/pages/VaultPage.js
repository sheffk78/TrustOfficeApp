import { useState, useEffect } from 'react';
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
import {
  FolderOpen, Plus, FileText, Calendar, Link as LinkIcon,
  Search, AlertTriangle, CheckCircle2, ExternalLink,
  Trash2, Tag, Shield, FileCheck
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

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
  court_order: Gavel,
  other: FileText,
};

function Gavel(props) { return <svg {...props} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 13l6-6"/><circle cx="8" cy="8" r="6"/><path d="M4 20l6-6"/></svg>; }

export default function VaultPage() {
  const { selectedTrust } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [byCategory, setByCategory] = useState({});
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('');
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

  useEffect(() => {
    if (selectedTrust) loadData();
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
      const dData = await docRes.json();
      if (docRes.ok) {
        setDocuments(dData.documents || []);
        setByCategory(dData.by_category || {});
      }
      const sData = await sumRes.json();
      if (sumRes.ok) setSummary(sData);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const addDocument = async () => {
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
      setShowAdd(false);
      setForm({ title: '', category: 'trust_instrument', date: '', description: '', storage_provider: 'google_drive', storage_url: '', storage_path: '', file_name: '', tags: '', expiration_date: '', needs_renewal: false });
      loadData();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const deleteDocument = async (id) => {
    try {
      const res = await fetchWithAuth(`/vault/documents/${id}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success('Document removed');
        loadData();
      }
    } catch (e) {
      toast.error('Failed');
    }
  };

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <div className="md:pl-64 pb-20 md:pb-0">
          <div className="pt-16 md:pt-8 ml-4 mr-4">
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded-lg">
              <FolderOpen className="w-12 h-12 text-slate-400 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-neutral-600">Choose a trust to view document vault.</p>
            </div>
          </div>
        </div>
        <MobileBottomNav />
      </div>
    );
  }

  const categories = summary?.categories || {};

  return (
    <div className="min-h-screen bg-subtle-bg">
      <Sidebar />
      <div className="md:pl-64 pb-20 md:pb-0">
        <div className="pt-16 md:pt-8 ml-4 mr-4">

          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6 gap-4">
            <div>
              <h1 className="text-2xl font-bold text-navy flex items-center gap-2">
                <FolderOpen className="w-6 h-6 text-navy"/>
                Trust Document Vault
              </h1>
              <p className="text-sm text-neutral-600 mt-1">Organize references to your trust documents for <span className="font-semibold">{selectedTrust.name}</span></p>
              <p className="text-xs text-neutral-400 mt-1">Link to files stored on Google Drive, Dropbox, OneDrive, or your local server.</p>
            </div>
            <Button onClick={() => setShowAdd(!showAdd)}>
              <Plus className="w-4 h-4 mr-2"/>
              Add Document
            </Button>
          </div>

          {/* Missing Critical Alert */}
          {summary?.missing_critical && summary.missing_critical.length > 0 && (
            <Card className="mb-6 border-red-200 bg-red-50">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="w-5 h-5 text-red-600"/>
                  <h3 className="font-semibold text-red-800">Critical Documents Missing</h3>
                </div>
                <ul className="text-sm text-red-700 space-y-1">
                  {summary.missing_critical.map((m, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-red-600 rounded-full"/>
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
              className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
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
                <h3 className="font-semibold text-navy mb-3">Add Document Reference</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                  <Input placeholder="Document title" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
                  <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} className="border border-neutral-300 rounded-md px-3 py-2 text-sm">
                    {Object.entries(categories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <Input type="date" placeholder="Document date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} />
                  <Input placeholder="Tags (comma-separated)" value={form.tags} onChange={e => setForm({ ...form, tags: e.target.value })} />
                  <select value={form.storage_provider} onChange={e => setForm({ ...form, storage_provider: e.target.value })} className="border border-neutral-300 rounded-md px-3 py-2 text-sm">
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
                <textarea placeholder="Description..." value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="w-full border border-neutral-300 rounded-md px-3 py-2 text-sm mb-3" rows={3} />
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <Input type="date" placeholder="Expires on" value={form.expiration_date} onChange={e => setForm({ ...form, expiration_date: e.target.value })} />
                  <div className="flex items-center gap-2">
                    <input type="checkbox" checked={form.needs_renewal} onChange={e => setForm({ ...form, needs_renewal: e.target.checked })} id="renew" />
                    <label htmlFor="renew" className="text-sm text-neutral-600">Requires periodic renewal / update</label>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button onClick={addDocument}>Save to Vault</Button>
                  <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Document Grid by Category */}
          {loading ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-20 bg-white border border-neutral-200 rounded-lg animate-pulse"/>)}
            </div>
          ) : Object.keys(byCategory).length === 0 ? (
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded-lg">
              <FolderOpen className="w-12 h-12 text-slate-300 mb-3"/>
              <h2 className="text-lg font-semibold text-navy mb-1">Vault is empty</h2>
              <p className="text-sm text-neutral-600 mb-4">Your trust documents should be organized here. Link to files stored externally.</p>
              <Button onClick={() => setShowAdd(true)}>Add First Document</Button>
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
                        <div key={doc.doc_id} className="bg-white border border-neutral-200 rounded-lg p-4 hover:shadow-sm transition-shadow">
                          <div className="flex items-start justify-between mb-2">
                            <p className="font-semibold text-navy text-sm line-clamp-2">{doc.title}</p>
                            <button onClick={() => deleteDocument(doc.doc_id)} className="text-neutral-400 hover:text-red-500">
                              <Trash2 className="w-3.5 h-3.5"/>
                            </button>
                          </div>
                          <p className="text-xs text-neutral-500 mb-2">{doc.file_name}</p>
                          {doc.description && <p className="text-xs text-neutral-600 mb-2 line-clamp-2">{doc.description}</p>}
                          <div className="flex flex-wrap gap-1 mb-3">
                            {doc.tags?.map((tag, i) => (
                              <span key={i} className="text-[10px] font-mono bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">{tag}</span>
                            ))}
                          </div>
                          <div className="flex items-center justify-between">
                            {doc.storage_url ? (
                              <a href={doc.storage_url} target="_blank" rel="noopener noreferrer" className="text-xs text-navy hover:text-gold flex items-center gap-1">
                                <ExternalLink className="w-3 h-3"/> Open
                              </a>
                            ) : (
                              <span className="text-xs text-neutral-400">No link</span>
                            )}
                            <span className="text-[10px] text-neutral-400">
                              {doc.date ? format(parseISO(doc.date), 'MMM d, yyyy') : ''}
                            </span>
                          </div>
                          {doc.needs_renewal && doc.expiration_date && (
                            <div className="mt-2 text-[10px] text-amber-600 bg-amber-50 border border-amber-100 rounded px-2 py-1">
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
