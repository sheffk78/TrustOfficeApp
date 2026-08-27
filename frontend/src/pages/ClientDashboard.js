import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import TrustCard from '@/components/TrustCard';
import QuickActionsBar from '@/components/QuickActionsBar';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { format, parseISO } from 'date-fns';
import {
  Users,
  Mail,
  Phone,
  MapPin,
  Shield,
  CalendarDays,
  FileText,
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  ArrowLeft,
  ChevronRight,
  Save,
} from 'lucide-react';

const getScoreColor = (score) => {
  if (score >= 96) return 'text-success';
  if (score >= 72) return 'text-warning';
  return 'text-error';
};

const getScoreBadgeStyle = (score) => {
  if (score >= 96) return 'bg-success/10 text-success border-success/20';
  if (score >= 72) return 'bg-warning/10 text-warning border-warning/20';
  return 'bg-error/10 text-error border-error/20';
};

export default function ClientDashboard() {
  const { clientId } = useParams();
  const { user } = useAuth();
  const [client, setClient] = useState(null);
  const [health, setHealth] = useState(null);
  const [deadlines, setDeadlines] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [addTrustOpen, setAddTrustOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  // Edit form state
  const [editForm, setEditForm] = useState({
    name: '',
    email: '',
    phone: '',
    address: '',
    notes: '',
  });

  // Add trust form state
  const [availableTrusts, setAvailableTrusts] = useState([]);
  const [selectedTrustId, setSelectedTrustId] = useState('');

  useEffect(() => {
    if (clientId) {
      loadClientData();
    }
  }, [clientId]);

  const loadClientData = async () => {
    setLoading(true);
    try {
      const [clientRes, healthRes, deadlinesRes, meetingsRes] = await Promise.all([
        fetchWithAuth(`/clients/${clientId}`),
        fetchWithAuth(`/clients/${clientId}/health`),
        fetchWithAuth(`/clients/${clientId}/deadlines`),
        fetchWithAuth(`/clients/${clientId}/meetings`),
      ]);

      if (clientRes.ok) {
        const clientData = await clientRes.json();
        setClient(clientData);
        setEditForm({
          name: clientData.name || '',
          email: clientData.email || '',
          phone: clientData.phone || '',
          address: clientData.address || '',
          notes: clientData.notes || '',
        });
      } else {
        const err = await clientRes.json().catch(() => ({}));
        showError(toast, new Error(err.detail || 'Failed to load client'), {
          operation: 'load_client',
          page: 'ClientDashboard',
        });
      }

      if (healthRes.ok) {
        setHealth(await healthRes.json());
      }

      if (deadlinesRes.ok) {
        const data = await deadlinesRes.json();
        setDeadlines(Array.isArray(data) ? data : data.deadlines || []);
      }

      if (meetingsRes.ok) {
        const data = await meetingsRes.json();
        setMeetings(Array.isArray(data) ? data : data.meetings || []);
      }
    } catch (error) {
      console.error('Failed to load client data:', error);
      showError(toast, error, { operation: 'load_client_data', page: 'ClientDashboard' });
    } finally {
      setLoading(false);
    }
  };

  const handleEditSave = async () => {
    setSaving(true);
    try {
      const res = await fetchWithAuth(`/clients/${clientId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });

      if (res.ok) {
        toast.success('Client updated successfully');
        setEditOpen(false);
        loadClientData();
      } else {
        const err = await res.json().catch(() => ({}));
        showError(toast, new Error(err.detail || 'Failed to update client'), {
          operation: 'update_client',
          page: 'ClientDashboard',
        });
      }
    } catch (error) {
      showError(toast, error, { operation: 'update_client', page: 'ClientDashboard' });
    } finally {
      setSaving(false);
    }
  };

  const openAddTrustDialog = async () => {
    try {
      // Fetch all trusts to let the user pick one to link
      const res = await fetchWithAuth('/trusts');
      if (res.ok) {
        const data = await res.json();
        const allTrusts = Array.isArray(data) ? data : data.trusts || [];
        // Filter out trusts already linked to this client
        const linkedIds = new Set((client?.trusts || []).map((t) => t.trust_id));
        setAvailableTrusts(allTrusts.filter((t) => !linkedIds.has(t.trust_id)));
      }
    } catch (error) {
      console.error('Failed to load trusts:', error);
    }
    setSelectedTrustId('');
    setAddTrustOpen(true);
  };

  const handleLinkTrust = async () => {
    if (!selectedTrustId) return;
    setSaving(true);
    try {
      const res = await fetchWithAuth(`/clients/${clientId}/trusts/${selectedTrustId}`, {
        method: 'POST',
      });

      if (res.ok) {
        toast.success('Trust linked to client');
        setAddTrustOpen(false);
        loadClientData();
      } else {
        const err = await res.json().catch(() => ({}));
        showError(toast, new Error(err.detail || 'Failed to link trust'), {
          operation: 'link_trust',
          page: 'ClientDashboard',
        });
      }
    } catch (error) {
      showError(toast, error, { operation: 'link_trust', page: 'ClientDashboard' });
    } finally {
      setSaving(false);
    }
  };

  const formatDate = (dateString) => {
    try {
      return format(parseISO(dateString), 'MMM d, yyyy');
    } catch {
      return dateString;
    }
  };

  const trusts = client?.trusts || [];
  const trustCount = trusts.length;
  const avgScore =
    trustCount > 0
      ? Math.round(
          trusts.reduce((sum, t) => sum + (t.governance_score || 0), 0) / trustCount
        )
      : null;
  const greenCount = trusts.filter((t) => (t.governance_score || 0) >= 96).length;
  const yellowCount = trusts.filter(
    (t) => (t.governance_score || 0) >= 72 && (t.governance_score || 0) < 96
  ).length;
  const redCount = trusts.filter((t) => (t.governance_score || 0) < 72).length;

  const upcomingDeadlines = deadlines
    .filter((d) => {
      try {
        return new Date(d.due_date || d.date) >= new Date();
      } catch {
        return false;
      }
    })
    .sort((a, b) => new Date(a.due_date || a.date) - new Date(b.due_date || b.date))
    .slice(0, 5);

  const recentMeetings = meetings
    .sort((a, b) => new Date(b.meeting_date || b.date) - new Date(a.meeting_date || a.date))
    .slice(0, 5);

  return (
    <div className="main-layout" data-testid="client-dashboard-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link to="/clients">
                <Button variant="ghost" size="sm" className="text-muted-foreground">
                  <ArrowLeft className="w-4 h-4 mr-1" />
                  Clients
                </Button>
              </Link>
              <div>
                <h1 className="page-title">
                  {loading ? 'Loading…' : client?.name || 'Client Dashboard'}
                </h1>
                <p className="page-subtitle">
                  Multi-trust client overview — health, deadlines, and meetings across all linked trusts
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'View all trusts linked to this client in one place' },
                  { text: 'Track health scores and compliance across trusts' },
                  { text: 'See upcoming deadlines and recent meetings cross-trust' },
                ]}
                taPrompt="Walk me through the Client Dashboard and how to manage multi-trust clients"
              />
              <Button
                onClick={loadClientData}
                variant="outline"
                className="btn-secondary"
                data-testid="refresh-btn"
              >
                <RefreshCw className="w-4 h-4 mr-2" />
                Refresh
              </Button>
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 card-trust">
                <div className="skeleton h-48 w-full"></div>
              </div>
              <div className="card-trust">
                <div className="skeleton h-48 w-full"></div>
              </div>
            </div>
          ) : !client ? (
            <div className="card-trust text-center py-12">
              <Users className="w-12 h-12 text-navy/30 mx-auto mb-4" />
              <h2 className="font-serif text-xl text-navy mb-2">Client not found</h2>
              <p className="text-sm text-muted-foreground mb-6">
                This client may have been removed or the link is invalid.
              </p>
              <Link to="/clients">
                <Button variant="outline" className="btn-secondary">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Back to Clients
                </Button>
              </Link>
            </div>
          ) : (
            <>
              {/* Quick Actions */}
              <QuickActionsBar
                clientId={clientId}
                onEdit={() => setEditOpen(true)}
                onAddTrust={openAddTrustDialog}
              />

              {/* Client Profile + Health Summary */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* Client Profile Card */}
                <div className="lg:col-span-2 card-trust corner-mark">
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-lg bg-navy/5 flex items-center justify-center shrink-0">
                      <Users className="w-6 h-6 text-navy" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h2 className="font-serif text-xl text-navy mb-1">{client.name}</h2>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                        {client.email && (
                          <span className="inline-flex items-center">
                            <Mail className="w-3.5 h-3.5 mr-1" />
                            {client.email}
                          </span>
                        )}
                        {client.phone && (
                          <span className="inline-flex items-center">
                            <Phone className="w-3.5 h-3.5 mr-1" />
                            {client.phone}
                          </span>
                        )}
                        {client.address && (
                          <span className="inline-flex items-center">
                            <MapPin className="w-3.5 h-3.5 mr-1" />
                            {client.address}
                          </span>
                        )}
                      </div>
                      {client.notes && (
                        <p className="text-sm text-muted-foreground mt-3 border-t border-border pt-3">
                          {client.notes}
                        </p>
                      )}
                    </div>
                    <Badge variant="outline" className="bg-navy/5 text-navy border-navy/20 shrink-0">
                      {trustCount} trust{trustCount === 1 ? '' : 's'}
                    </Badge>
                  </div>
                </div>

                {/* Health Summary Card */}
                <div className="card-trust">
                  <h3 className="font-serif text-lg text-navy mb-4">Health Summary</h3>
                  {avgScore !== null ? (
                    <>
                      <div className="text-center mb-4">
                        <div className="score-circle">
                          <span className={`score-indicator ${getScoreColor(avgScore)}`}>
                            {avgScore}
                          </span>
                          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
                            avg score
                          </span>
                        </div>
                      </div>
                      <div className="flex justify-center gap-4">
                        <div className="text-center">
                          <div className="flex items-center gap-1 justify-center">
                            <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                            <span className="font-mono text-lg text-success">{greenCount}</span>
                          </div>
                          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                            Healthy
                          </p>
                        </div>
                        <div className="text-center">
                          <div className="flex items-center gap-1 justify-center">
                            <AlertTriangle className="w-3.5 h-3.5 text-warning" />
                            <span className="font-mono text-lg text-warning">{yellowCount}</span>
                          </div>
                          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                            Attention
                          </p>
                        </div>
                        <div className="text-center">
                          <div className="flex items-center gap-1 justify-center">
                            <Shield className="w-3.5 h-3.5 text-error" />
                            <span className="font-mono text-lg text-error">{redCount}</span>
                          </div>
                          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                            At Risk
                          </p>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="text-center py-6">
                      <Shield className="w-8 h-8 text-navy/30 mx-auto mb-2" />
                      <p className="text-sm text-muted-foreground">No trusts linked yet</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Link a trust to see health scores
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Trust Cards Grid */}
              <div className="mb-8">
                <h2 className="font-serif text-lg text-navy mb-4">Linked Trusts</h2>
                {trustCount === 0 ? (
                  <div className="card-trust text-center py-8">
                    <Shield className="w-10 h-10 text-navy/30 mx-auto mb-3" />
                    <p className="text-sm text-muted-foreground mb-4">
                      No trusts linked to this client yet
                    </p>
                    <Button onClick={openAddTrustDialog} className="btn-primary" size="sm">
                      Link a Trust
                    </Button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {trusts.map((trust) => (
                      <TrustCard key={trust.trust_id} trust={trust} />
                    ))}
                  </div>
                )}
              </div>

              {/* Bottom Row: Meetings + Deadlines */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Recent Meetings */}
                <div className="card-trust">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-serif text-lg text-navy">Recent Meetings</h3>
                    <Badge variant="outline" className="bg-navy/5 text-navy border-navy/20">
                      {meetings.length}
                    </Badge>
                  </div>
                  {recentMeetings.length === 0 ? (
                    <div className="text-center py-6">
                      <FileText className="w-8 h-8 text-navy/30 mx-auto mb-2" />
                      <p className="text-sm text-muted-foreground">No meetings recorded</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {recentMeetings.map((meeting, idx) => (
                        <div
                          key={meeting.meeting_id || idx}
                          className="flex items-center justify-between p-3 border border-border rounded-lg hover:border-navy/30 transition-colors"
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <FileText className="w-4 h-4 text-navy shrink-0" />
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-navy truncate">
                                {meeting.title || meeting.meeting_type || 'Trustee Meeting'}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                {meeting.trust_name && `${meeting.trust_name} · `}
                                {formatDate(meeting.meeting_date || meeting.date)}
                              </p>
                            </div>
                          </div>
                          <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Upcoming Deadlines */}
                <div className="card-trust">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-serif text-lg text-navy">Upcoming Deadlines</h3>
                    <Badge variant="outline" className="bg-navy/5 text-navy border-navy/20">
                      {upcomingDeadlines.length}
                    </Badge>
                  </div>
                  {upcomingDeadlines.length === 0 ? (
                    <div className="text-center py-6">
                      <CalendarDays className="w-8 h-8 text-navy/30 mx-auto mb-2" />
                      <p className="text-sm text-muted-foreground">No upcoming deadlines</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {upcomingDeadlines.map((deadline, idx) => {
                        const dueDate = deadline.due_date || deadline.date;
                        const isOverdue = (() => {
                          try {
                            return new Date(dueDate) < new Date();
                          } catch {
                            return false;
                          }
                        })();

                        return (
                          <div
                            key={deadline.deadline_id || idx}
                            className={`flex items-center justify-between p-3 border rounded-lg transition-colors ${
                              isOverdue
                                ? 'border-error/30 bg-error/5'
                                : 'border-border hover:border-navy/30'
                            }`}
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <Clock
                                className={`w-4 h-4 shrink-0 ${
                                  isOverdue ? 'text-error' : 'text-navy'
                                }`}
                              />
                              <div className="min-w-0">
                                <p
                                  className={`text-sm font-medium truncate ${
                                    isOverdue ? 'text-error' : 'text-navy'
                                  }`}
                                >
                                  {deadline.title || deadline.description || 'Deadline'}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  {deadline.trust_name && `${deadline.trust_name} · `}
                                  Due {formatDate(dueDate)}
                                </p>
                              </div>
                            </div>
                            {isOverdue && (
                              <Badge
                                variant="outline"
                                className="bg-error/10 text-error border-error/20 shrink-0"
                              >
                                Overdue
                              </Badge>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* Edit Client Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>Edit Client</DialogTitle>
            <DialogDescription>
              Update client contact information and notes.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                placeholder="Client name"
              />
            </div>
            <div>
              <Label htmlFor="edit-email">Email</Label>
              <Input
                id="edit-email"
                type="email"
                value={editForm.email}
                onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                placeholder="client@example.com"
              />
            </div>
            <div>
              <Label htmlFor="edit-phone">Phone</Label>
              <Input
                id="edit-phone"
                value={editForm.phone}
                onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                placeholder="(555) 123-4567"
              />
            </div>
            <div>
              <Label htmlFor="edit-address">Address</Label>
              <Input
                id="edit-address"
                value={editForm.address}
                onChange={(e) => setEditForm({ ...editForm, address: e.target.value })}
                placeholder="123 Main St, City, State ZIP"
              />
            </div>
            <div>
              <Label htmlFor="edit-notes">Notes</Label>
              <Textarea
                id="edit-notes"
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                placeholder="Internal notes about this client"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleEditSave} disabled={saving} className="btn-primary">
              <Save className="w-4 h-4 mr-1.5" />
              {saving ? 'Saving…' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Trust Dialog */}
      <Dialog open={addTrustOpen} onOpenChange={setAddTrustOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>Link Trust to Client</DialogTitle>
            <DialogDescription>
              Select a trust to link to {client?.name || 'this client'}.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {availableTrusts.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                All trusts are already linked to this client.
              </p>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="select-trust">Select Trust</Label>
                <select
                  id="select-trust"
                  className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background text-navy focus:outline-none focus:ring-1 focus:ring-navy"
                  value={selectedTrustId}
                  onChange={(e) => setSelectedTrustId(e.target.value)}
                >
                  <option value="">Choose a trust…</option>
                  {availableTrusts.map((t) => (
                    <option key={t.trust_id} value={t.trust_id}>
                      {t.trust_name || t.name || 'Unnamed Trust'}
                      {t.trust_type ? ` (${t.trust_type})` : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddTrustOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleLinkTrust}
              disabled={saving || !selectedTrustId}
              className="btn-primary"
            >
              {saving ? 'Linking…' : 'Link Trust'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
