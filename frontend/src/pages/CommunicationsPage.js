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
import PageHelpButton from '@/components/PageHelpButton';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  MessageSquare, Phone, Mail, Video, FileText, Bell,
  TrendingUp, Plus, CheckCircle2, Clock, AlertTriangle,
  ChevronDown, Search, Filter, X
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const COMM_TYPE_ICONS = {
  email: Mail,
  phone: Phone,
  meeting: Video,
  notice: Bell,
  financial_report: FileText,
  k1_distribution: TrendingUp,
  other: MessageSquare,
};

const COMM_TYPE_LABELS = {
  email: 'Email',
  phone: 'Phone',
  meeting: 'Meeting',
  notice: 'Notice',
  financial_report: 'Financial Report',
  k1_distribution: 'K-1 / Distribution',
  other: 'Other',
};

const formatDate = (dateStr) => {
  if (!dateStr) return '';
  try {
    const parsed = parseISO(dateStr);
    if (isNaN(parsed.getTime())) return dateStr;
    return format(parsed, 'MMM d, yyyy');
  } catch {
    return dateStr || 'Invalid date';
  }
};

export default function CommunicationsPage() {
  const { selectedTrust } = useAuth();
  const [communications, setCommunications] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [commTotal, setCommTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const PAGE_SIZE = 50;
  const [form, setForm] = useState({
    comm_type: 'email',
    subject: '',
    content: '',
    direction: 'outbound',
    action_required: false,
    action_due: '',
    parties_text: '',
    parties: [{ role: 'trustee', name: '' }],
  });

  useEffect(() => {
    if (selectedTrust) loadData();
  }, [selectedTrust, filterType]);

  const loadData = async (append = false) => {
    if (!selectedTrust) return;
    if (!append) setLoading(true);
    else setLoadingMore(true);
    try {
      const params = new URLSearchParams();
      const skip = append ? communications.length : 0;
      params.append('skip', skip);
      params.append('limit', PAGE_SIZE);
      if (filterType) params.append('comm_type', filterType);
      if (search) params.append('search', search);

      const [commRes, sumRes] = await Promise.all([
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/communications?${params.toString()}`),
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/communications/summary`),
      ]);
      const cData = await commRes.json();
      if (commRes.ok) {
        const items = cData.items || [];
        setCommTotal(cData.total || 0);
        if (append) {
          setCommunications(prev => [...prev, ...items]);
        } else {
          setCommunications(items);
        }
      }

      const sData = await sumRes.json();
      if (sumRes.ok) setSummary(sData);
    } catch (e) {
      showError(toast, e, { operation: 'load_communications', page: 'Communications' });
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  const handleLoadMore = () => {
    loadData(true);
  };

  const createCommunication = async () => {
    try {
      const payload = { ...form };
      // Convert parties_text to parties array for backend
      if (form.parties_text && form.parties_text.trim()) {
        payload.parties = [{ role: 'trustee', name: form.parties_text.trim() }];
      }
      delete payload.parties_text;
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/communications`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed');
      toast.success('Communication logged');
      setShowAdd(false);
      setForm({ comm_type: 'email', subject: '', content: '', direction: 'outbound', action_required: false, action_due: '', parties_text: '', parties: [{ role: 'trustee', name: '' }] });
      loadData();
    } catch (e) {
      showError(toast, e, { operation: 'create_communication', page: 'Communications' });
    }
  };

  const completeAction = async (id) => {
    try {
      const res = await fetchWithAuth(`/communications/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_completed: true }),
      });
      if (!res.ok) throw new Error('Failed to mark action complete');
      toast.success('Action marked complete');
      loadData();
    } catch (e) {
      showError(toast, e, { operation: 'complete_action', page: 'Communications' });
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <div className="main-content dot-grid">
          <div className="page-container">
            <div className="card-trust p-12 flex flex-col items-center justify-center">
              <MessageSquare className="w-12 h-12 text-muted-foreground/40 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to view communications log.</p>
            </div>
          </div>
        </div>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="main-layout">
      <Sidebar />
      <div className="main-content dot-grid mobile-layout-offset">
        <div className="page-container">

          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Communication Log</h1>
              <p className="page-subtitle">Record and track all beneficiary communications — document calls, emails, and notices to satisfy UTC § 813</p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Record and track all beneficiary communications in one place' },
                  { text: 'Document calls, emails, and notices to satisfy UTC § 813 requirements' },
                  { text: 'Maintain a complete history of beneficiary contact' },
                ]}
                taPrompt="Walk me through the Communication Log and how to log a beneficiary contact"
              />
              <Button className="btn-primary" onClick={() => setShowAdd(!showAdd)}>
                <Plus className="w-4 h-4 mr-2"/>
                Log Communication
              </Button>
            </div>
          </div>

          {/* Summary + Filters */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            <Card><CardContent className="p-4">
              <div className="text-2xl font-bold text-navy">{summary?.total_communications || 0}</div>
              <div className="text-xs text-muted-foreground">Total Recorded</div>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <div className="text-2xl font-bold text-warning">{summary?.pending_actions || 0}</div>
              <div className="text-xs text-muted-foreground">Pending Actions</div>
            </CardContent></Card>
            <Card className="col-span-2 card-trust">
              <CardContent className="p-3 flex gap-2 items-center">
                <Search className="w-4 h-4 text-muted-foreground"/>
                <Input
                  placeholder="Search communications..."
                  value={search}
                  onChange={e => { setSearch(e.target.value); if (!e.target.value) loadData(); }}
                  onKeyDown={e => e.key === 'Enter' && loadData()}
                  className="flex-1"
                />
                <select
                  value={filterType}
                  onChange={e => { setFilterType(e.target.value); loadData(); }}
                  className="input-trust px-2 py-1.5 text-sm"
                >
                  <option value="">All Types</option>
                  {Object.entries(COMM_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </CardContent>
            </Card>
          </div>

          {/* Add Form */}
          {showAdd && (
            <Card className="mb-6 card-trust">
              <CardContent className="p-4">
                <h3 className="font-semibold text-navy mb-3">Log Communication</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                  <select value={form.comm_type} onChange={e => setForm({ ...form, comm_type: e.target.value })} className="input-trust px-3 py-2 text-sm">
                    {Object.entries(COMM_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <select value={form.direction} onChange={e => setForm({ ...form, direction: e.target.value })} className="input-trust px-3 py-2 text-sm">
                    <option value="outbound">Outbound (Trustee → Beneficiary)</option>
                    <option value="inbound">Inbound (Beneficiary → Trustee)</option>
                    <option value="internal">Internal (Trustee to Trustee)</option>
                  </select>
                  <Input type="date" placeholder="Action due date" value={form.action_due} onChange={e => setForm({ ...form, action_due: e.target.value })} />
                </div>
                <Input placeholder="Subject / Topic" value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })} className="mb-3" />
                <div className="mb-3">
                  <label className="label-trust block mb-1 text-sm">Parties (optional)</label>
                  <Input
                    placeholder="e.g., Trustee: John Smith; Beneficiary: Jane Smith"
                    value={form.parties_text || ''}
                    onChange={e => setForm({ ...form, parties_text: e.target.value })}
                    className="input-trust"
                  />
                </div>
                <textarea placeholder="Content / Summary of communication..." value={form.content} onChange={e => setForm({ ...form, content: e.target.value })} className="input-trust w-full px-3 py-2 text-sm mb-3" rows={4} />
                <div className="flex items-center gap-2 mb-3">
                  <input
                    type="checkbox"
                    checked={form.action_required}
                    onChange={e => setForm({ ...form, action_required: e.target.checked })}
                    id="action_req"
                  />
                  <label htmlFor="action_req" className="text-sm text-muted-foreground">This communication requires follow-up action</label>
                </div>
                <div className="flex gap-2">
                  <Button className="btn-primary" onClick={createCommunication}>Log Communication</Button>
                  <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* List */}
          {loading ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="card-trust h-20 animate-pulse"/>)}
            </div>
          ) : communications.length === 0 ? (
            <div className="card-trust p-12 flex flex-col items-center justify-center">
              <MessageSquare className="w-12 h-12 text-muted-foreground/30 mb-3"/>
              <h2 className="text-lg font-semibold text-navy mb-1">No communications logged</h2>
              <p className="text-sm text-muted-foreground mb-4">Every trustee-beneficiary interaction should be documented. Start logging emails, calls, and notices.</p>
              <Button className="btn-primary" onClick={() => setShowAdd(true)}>Log First Communication</Button>
            </div>
          ) : (
            <div className="space-y-3">
              {communications.map((comm) => {
                const Icon = COMM_TYPE_ICONS[comm.comm_type] || MessageSquare;
                const needsAction = comm.action_required && !comm.action_completed;
                return (
                  <div key={comm.comm_id} className={`card-trust ${needsAction ? 'border-warning/30' : ''} p-4`}>
                    <div className="flex items-start gap-3">
                      <div className={`w-9 h-9 flex items-center justify-center flex-shrink-0 rounded ${needsAction ? 'bg-warning/10 text-warning' : 'bg-navy/5 text-navy'}`}>
                        <Icon className="w-4 h-4"/>
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-mono text-muted-foreground uppercase">{COMM_TYPE_LABELS[comm.comm_type] || comm.comm_type}</span>
                          {needsAction && (
                            <Badge className="bg-warning/10 text-warning">Action Required</Badge>
                          )}
                          <span className="text-xs text-muted-foreground ml-auto">{formatDate(comm.created_at)}</span>
                        </div>
                        <h3 className="font-semibold text-navy text-sm">{comm.subject}</h3>
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{comm.content}</p>
                        {needsAction && comm.action_due && (
                          <p className="text-xs text-warning mt-2 flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5"/>
                            Action due {formatDate(comm.action_due)}
                          </p>
                        )}
                      </div>
                      {needsAction && (
                        <Button size="sm" variant="outline" onClick={() => completeAction(comm.comm_id)}>
                          <CheckCircle2 className="w-3.5 h-3.5 mr-1"/>
                          Complete
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {communications.length < commTotal && (
            <div className="mt-4 text-center">
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="btn-secondary"
              >
                {loadingMore ? 'Loading...' : 'Load More'}
              </button>
            </div>
          )}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}
