import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import InfoTooltip from '@/components/InfoTooltip';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  CheckCircle2, XCircle, Clock, FileText, User,
  CircleDot, ArrowRight, Shield, MessageSquare,
} from 'lucide-react';

const STATUS_CONFIG = {
  draft: { label: 'Draft', color: 'bg-slate-100 text-slate-600 border-slate-200', icon: FileText },
  pending_review: { label: 'Pending Review', color: 'bg-warning/10 text-warning border-warning/20', icon: Clock },
  in_review: { label: 'In Review', color: 'bg-blue-100 text-blue-700 border-blue-200', icon: CircleDot },
  changes_requested: { label: 'Changes Requested', color: 'bg-red-100 text-red-700 border-red-200', icon: MessageSquare },
  approved: { label: 'Approved', color: 'bg-success/10 text-success border-success/20', icon: CheckCircle2 },
  recorded: { label: 'Recorded', color: 'bg-navy/10 text-navy border-navy/20', icon: Shield },
};

const ACTION_ICONS = {
  created: FileText,
  updated: FileText,
  submitted: ArrowRight,
  approved: CheckCircle2,
  changes_requested: MessageSquare,
  recorded: Shield,
  finalized: CheckCircle2,
};

function TimelineEntry({ entry }) {
  const Icon = ACTION_ICONS[entry.action] || CircleDot;
  const ts = entry.timestamp || entry.created_at;
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className="w-8 h-8 rounded-full bg-navy/5 flex items-center justify-center shrink-0">
          <Icon className="w-3.5 h-3.5 text-navy" />
        </div>
        <div className="w-px flex-1 bg-border mt-1" />
      </div>
      <div className="pb-5 min-w-0">
        <p className="text-sm text-navy font-medium capitalize">
          {(entry.action || 'updated').replace(/_/g, ' ')}
        </p>
        {entry.actor_name && (
          <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
            <User className="w-3 h-3" /> {entry.actor_name}
          </p>
        )}
        {entry.notes && (
          <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">{entry.notes}</p>
        )}
        {ts && (
          <p className="text-[11px] text-muted-foreground/70 mt-1">
            {new Date(ts).toLocaleString(undefined, {
              month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
            })}
          </p>
        )}
      </div>
    </div>
  );
}

export default function ApprovalFlow() {
  const { trustId } = useParams();
  const { selectedTrust, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [workflow, setWorkflow] = useState(null);
  const [actionNotes, setActionNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showNotesBox, setShowNotesBox] = useState(false);

  const effectiveTrustId = trustId || selectedTrust?.trust_id;

  const loadWorkflow = useCallback(async () => {
    if (!effectiveTrustId) return;
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/meetings/${effectiveTrustId}/workflow-status`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load workflow status');
      setWorkflow(data);
    } catch (e) {
      showError(toast, e, { operation: 'load_workflow', page: 'ApprovalFlow' });
    } finally {
      setLoading(false);
    }
  }, [effectiveTrustId]);

  useEffect(() => {
    loadWorkflow();
  }, [loadWorkflow]);

  const current = workflow?.current_minutes || workflow?.minutes;
  const actionLog = workflow?.action_log || workflow?.history || [];
  const status = current?.status || 'draft';
  const statusCfg = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  const StatusIcon = statusCfg.icon;

  // Role-aware: trustees/admins can approve; preparers can only view once submitted
  const userRole = (workflow?.user_role || user?.role || 'trustee').toLowerCase();
  const canApprove = ['trustee', 'co_trustee', 'admin', 'approver'].includes(userRole)
    && ['pending_review', 'in_review', 'changes_requested'].includes(status);
  const canEdit = status === 'draft' || status === 'changes_requested';

  const doAction = async (action) => {
    if (!current?.minutes_id) return;
    if (action === 'request_changes' && !actionNotes.trim()) {
      toast.error('Please add a note describing the changes needed');
      setShowNotesBox(true);
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetchWithAuth(`/meetings/minutes/${current.minutes_id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          notes: actionNotes.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Failed to ${action === 'approve' ? 'approve' : 'request changes'}`);
      toast.success(action === 'approve' ? 'Minutes approved' : 'Changes requested');
      setActionNotes('');
      setShowNotesBox(false);
      loadWorkflow();
    } catch (e) {
      showError(toast, e, { operation: `${action}_minutes`, page: 'ApprovalFlow' });
    } finally {
      setSubmitting(false);
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content mobile-layout-offset">
          <div className="page-container">
            <div className="card-trust border border-border p-12 flex flex-col items-center justify-center rounded">
              <Shield className="w-12 h-12 text-muted-foreground/60 mb-3" />
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to view its approval workflow.</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content mobile-layout-offset">
        <div className="page-container">

          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Approval Workflow</h1>
              <p className="page-subtitle">
                Track minutes from draft through approval for {selectedTrust.trust_name || 'this trust'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'See where the current minutes stand in the approval process' },
                  { text: 'Approve minutes or request changes with notes for the preparer' },
                  { text: 'Review the action log for a full audit trail' },
                ]}
                taPrompt="Explain the minutes approval workflow"
                contextAlerts={status === 'pending_review' && canApprove ? [
                  { text: 'Minutes are waiting for your approval', prompt: 'What should I check before approving these minutes?' },
                ] : []}
              />
              <Link to={`/governance/history/${effectiveTrustId}`}>
                <Button variant="outline">Meeting History</Button>
              </Link>
            </div>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1, 2].map((i) => (
                <div key={i} className="h-40 card-trust border border-border rounded animate-pulse" />
              ))}
            </div>
          ) : !current ? (
            <div className="card-trust border border-border p-12 flex flex-col items-center justify-center rounded">
              <FileText className="w-12 h-12 text-muted-foreground/60 mb-3" />
              <h2 className="text-xl font-semibold text-navy mb-1">No active minutes</h2>
              <p className="text-sm text-muted-foreground mb-4">
                There are no minutes currently in the approval pipeline for this trust.
              </p>
              <Link to="/minutes/create">
                <Button>Create minutes</Button>
              </Link>
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-5">

              {/* Status + actions */}
              <div className="lg:col-span-3 space-y-4">
                <Card className="card-trust border border-border">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      Current Minutes
                      <InfoTooltip text="The most recent minutes for this trust and where they stand in the review cycle. Minutes move from draft → pending review → approved → recorded." />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div>
                        <p className="text-sm font-medium text-navy">
                          {current.title || 'Trustee meeting minutes'}
                        </p>
                        {current.meeting_date && (
                          <p className="text-xs text-muted-foreground">
                            Meeting: {new Date(current.meeting_date).toLocaleDateString()}
                          </p>
                        )}
                        {current.updated_at && (
                          <p className="text-xs text-muted-foreground">
                            Last edited: {new Date(current.updated_at).toLocaleString(undefined, {
                              month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                            })}
                          </p>
                        )}
                      </div>
                      <Badge variant="outline" className={statusCfg.color}>
                        <StatusIcon className="w-3 h-3 mr-1" />
                        {statusCfg.label}
                      </Badge>
                    </div>

                    {current.review_notes && status === 'changes_requested' && (
                      <div className="border border-red-200 bg-red-50 rounded-lg p-3">
                        <p className="text-xs font-medium text-red-800 mb-1">Requested changes</p>
                        <p className="text-sm text-red-700 whitespace-pre-wrap">{current.review_notes}</p>
                      </div>
                    )}

                    {current.approver_name && (
                      <p className="text-xs text-muted-foreground flex items-center gap-1">
                        <User className="w-3 h-3" /> Approver: {current.approver_name}
                      </p>
                    )}

                    {/* Action buttons */}
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      {canEdit && (
                        <Link to={`/governance/minutes/${current.minutes_id}`}>
                          <Button variant="outline" size="sm">
                            <FileText className="w-3.5 h-3.5 mr-1" /> Open Editor
                          </Button>
                        </Link>
                      )}
                      {canApprove && (
                        <>
                          <Button size="sm" onClick={() => doAction('approve')} disabled={submitting}>
                            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                            {submitting ? 'Working…' : 'Approve'}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => (showNotesBox ? doAction('request_changes') : setShowNotesBox(true))}
                            disabled={submitting}
                          >
                            <XCircle className="w-3.5 h-3.5 mr-1" /> Request Changes
                          </Button>
                        </>
                      )}
                      {!canApprove && ['pending_review', 'in_review'].includes(status) && (
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <Clock className="w-3 h-3" /> Waiting for trustee approval
                        </p>
                      )}
                    </div>

                    {showNotesBox && canApprove && (
                      <div className="space-y-2">
                        <textarea
                          className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background text-navy focus:outline-none focus:ring-1 focus:ring-navy min-h-[72px]"
                          value={actionNotes}
                          onChange={(e) => setActionNotes(e.target.value)}
                          placeholder="Describe what needs to change before you can approve…"
                        />
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => doAction('request_changes')} disabled={submitting}>
                            Send change request
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => { setShowNotesBox(false); setActionNotes(''); }}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* Action log */}
              <div className="lg:col-span-2">
                <Card className="card-trust border border-border">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Action Log</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {actionLog.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No workflow actions recorded yet.</p>
                    ) : (
                      <div>
                        {actionLog.map((entry, i) => (
                          <TimelineEntry key={entry.log_id || i} entry={entry} />
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
