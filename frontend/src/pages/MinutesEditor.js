import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import InfoTooltip from '@/components/InfoTooltip';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  FileText, Save, Send, ArrowLeft, CheckCircle2,
  Users, CalendarDays, AlertTriangle,
} from 'lucide-react';

const STATUS_LABELS = {
  draft: 'Draft',
  pending_review: 'Pending Review',
  in_review: 'In Review',
  changes_requested: 'Changes Requested',
  approved: 'Approved',
  recorded: 'Recorded',
};

function AgendaMinutesSection({ item, index, value, onChange, readOnly }) {
  const entry = value || { discussion: '', decision: '', action_items: '' };
  return (
    <Card className="card-trust border border-border">
      <CardContent className="p-5">
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <span className="text-xs font-mono text-muted-foreground">{index + 1}.</span>
          <p className="text-sm font-semibold text-navy flex-1 min-w-0">{item.title}</p>
          {item.item_type && (
            <Badge variant="outline" className="bg-slate-100 text-slate-600 border-slate-200 capitalize">
              {item.item_type}
            </Badge>
          )}
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center">
              Discussion
              <InfoTooltip text="Summarize what was discussed for this agenda item — key points raised, documents reviewed, questions asked." />
            </label>
            <textarea
              className="mt-1 w-full text-sm border border-border rounded-md px-3 py-2 bg-background text-navy focus:outline-none focus:ring-1 focus:ring-navy min-h-[72px] disabled:opacity-60"
              value={entry.discussion}
              disabled={readOnly}
              onChange={(e) => onChange(index, { ...entry, discussion: e.target.value })}
              placeholder="What was discussed?"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center">
              Decision / Resolution
              <InfoTooltip text="Record the formal decision made. For resolutions, use clear 'RESOLVED, that…' language so the minutes stand on their own." />
            </label>
            <textarea
              className="mt-1 w-full text-sm border border-border rounded-md px-3 py-2 bg-background text-navy focus:outline-none focus:ring-1 focus:ring-navy min-h-[56px] disabled:opacity-60"
              value={entry.decision}
              disabled={readOnly}
              onChange={(e) => onChange(index, { ...entry, decision: e.target.value })}
              placeholder="RESOLVED, that…"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Action Items
            </label>
            <textarea
              className="mt-1 w-full text-sm border border-border rounded-md px-3 py-2 bg-background text-navy focus:outline-none focus:ring-1 focus:ring-navy min-h-[48px] disabled:opacity-60"
              value={entry.action_items}
              disabled={readOnly}
              onChange={(e) => onChange(index, { ...entry, action_items: e.target.value })}
              placeholder="Follow-ups, owners, due dates (one per line)"
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function MinutesEditor() {
  const { minutesId } = useParams();
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [minutes, setMinutes] = useState(null);
  const [attendees, setAttendees] = useState('');
  const [notes, setNotes] = useState('');
  const [sections, setSections] = useState({});
  const [dirty, setDirty] = useState(false);

  const loadMinutes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/meetings/minutes/${minutesId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load minutes');
      setMinutes(data);
      setAttendees(data.attendees || '');
      setNotes(data.notes || '');
      const initial = {};
      (data.agenda_items || data.items || []).forEach((item, i) => {
        const existing = (data.sections || []).find(
          (s) => s.item_id === (item.item_id || item.id) || s.index === i
        );
        initial[i] = {
          discussion: existing?.discussion || '',
          decision: existing?.decision || '',
          action_items: existing?.action_items || '',
        };
      });
      setSections(initial);
      setDirty(false);
    } catch (e) {
      showError(toast, e, { operation: 'load_minutes', page: 'MinutesEditor' });
    } finally {
      setLoading(false);
    }
  }, [minutesId]);

  useEffect(() => {
    if (minutesId) loadMinutes();
  }, [minutesId, loadMinutes]);

  const status = minutes?.status || 'draft';
  const readOnly = status === 'approved' || status === 'recorded' || status === 'in_review' || status === 'pending_review';

  const updateSection = (index, entry) => {
    setSections({ ...sections, [index]: entry });
    setDirty(true);
  };

  const buildPayload = () => ({
    attendees,
    notes,
    sections: Object.entries(sections).map(([index, entry]) => ({
      index: Number(index),
      item_id: (minutes?.agenda_items || minutes?.items || [])[Number(index)]?.item_id,
      ...entry,
    })),
  });

  const saveDraft = async (silent = false) => {
    setSaving(true);
    try {
      const res = await fetchWithAuth(`/meetings/minutes/${minutesId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to save draft');
      if (!silent) toast.success('Draft saved');
      setDirty(false);
    } catch (e) {
      showError(toast, e, { operation: 'save_minutes', page: 'MinutesEditor' });
      throw e;
    } finally {
      setSaving(false);
    }
  };

  const submitForReview = async () => {
    try {
      if (dirty) await saveDraft(true);
      const res = await fetchWithAuth(`/meetings/minutes/${minutesId}/submit`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to submit for review');
      toast.success('Minutes submitted for review');
      const trustId = selectedTrust?.trust_id || minutes?.trust_id;
      navigate(trustId ? `/governance/approvals/${trustId}` : '/governance');
    } catch (e) {
      showError(toast, e, { operation: 'submit_minutes', page: 'MinutesEditor' });
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content mobile-layout-offset">
          <div className="page-container">
            <div className="card-trust border border-border p-12 flex flex-col items-center justify-center rounded">
              <FileText className="w-12 h-12 text-muted-foreground/60 mb-3" />
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to draft minutes.</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  const agendaItems = minutes?.agenda_items || minutes?.items || [];
  const meetingDate = minutes?.meeting_date
    ? new Date(minutes.meeting_date).toLocaleDateString(undefined, {
        weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
      })
    : null;

  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content mobile-layout-offset">
        <div className="page-container">

          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <Link
                to={`/governance/history/${selectedTrust.trust_id}`}
                className="inline-flex items-center text-xs text-muted-foreground hover:text-navy mb-1"
              >
                <ArrowLeft className="w-3 h-3 mr-1" /> Meeting history
              </Link>
              <h1 className="page-title">{minutes?.title || 'Draft Minutes'}</h1>
              <p className="page-subtitle">
                {meetingDate ? `${meetingDate} · ` : ''}Record discussion and decisions for each agenda item
              </p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'Draft minutes against each agenda item from the meeting' },
                  { text: 'Save your draft at any time — nothing is final until submitted' },
                  { text: 'Submit for review when ready for co-trustee or advisor approval' },
                ]}
                taPrompt="Help me draft minutes for this trustee meeting"
                contextAlerts={status === 'changes_requested' ? [
                  { text: 'Changes were requested on these minutes', prompt: 'What changes were requested on my minutes and how do I address them?' },
                ] : []}
              />
              <Badge variant="outline" className="bg-slate-100 text-slate-600 border-slate-200">
                {STATUS_LABELS[status] || status}
              </Badge>
            </div>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-32 card-trust border border-border rounded animate-pulse" />
              ))}
            </div>
          ) : !minutes ? (
            <div className="card-trust border border-border p-12 flex flex-col items-center justify-center rounded">
              <FileText className="w-12 h-12 text-muted-foreground/60 mb-3" />
              <h2 className="text-xl font-semibold text-navy mb-1">Minutes not found</h2>
              <p className="text-sm text-muted-foreground mb-4">
                These minutes may have been removed, or the link is incorrect.
              </p>
              <Link to={`/governance/history/${selectedTrust.trust_id}`}>
                <Button variant="outline">Back to meeting history</Button>
              </Link>
            </div>
          ) : (
            <>
              {status === 'changes_requested' && minutes.review_notes && (
                <Card className="card-trust border border-red-200 bg-red-50 mb-4">
                  <CardContent className="p-4 flex items-start gap-3">
                    <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-red-800">Changes requested</p>
                      <p className="text-sm text-red-700 whitespace-pre-wrap">{minutes.review_notes}</p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Meeting metadata */}
              <Card className="card-trust border border-border mb-4">
                <CardContent className="p-5 grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <Users className="w-3.5 h-3.5" /> Attendees
                    </label>
                    <textarea
                      className="mt-1 w-full text-sm border border-border rounded-md px-3 py-2 bg-background text-navy focus:outline-none focus:ring-1 focus:ring-navy min-h-[48px] disabled:opacity-60"
                      value={attendees}
                      disabled={readOnly}
                      onChange={(e) => { setAttendees(e.target.value); setDirty(true); }}
                      placeholder="Trustees and advisors present"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <CalendarDays className="w-3.5 h-3.5" /> General Notes
                    </label>
                    <textarea
                      className="mt-1 w-full text-sm border border-border rounded-md px-3 py-2 bg-background text-navy focus:outline-none focus:ring-1 focus:ring-navy min-h-[48px] disabled:opacity-60"
                      value={notes}
                      disabled={readOnly}
                      onChange={(e) => { setNotes(e.target.value); setDirty(true); }}
                      placeholder="Call to order, quorum confirmation, adjournment…"
                    />
                  </div>
                </CardContent>
              </Card>

              {/* Per-agenda-item sections */}
              <div className="space-y-3">
                {agendaItems.length === 0 ? (
                  <div className="card-trust border border-border rounded-xl p-8 text-center">
                    <p className="text-sm text-muted-foreground">
                      No agenda items attached to these minutes. Use the general notes field above to record the meeting.
                    </p>
                  </div>
                ) : (
                  agendaItems.map((item, i) => (
                    <AgendaMinutesSection
                      key={item.item_id || i}
                      item={item}
                      index={i}
                      value={sections[i]}
                      onChange={updateSection}
                      readOnly={readOnly}
                    />
                  ))
                )}
              </div>

              {/* Action bar */}
              {!readOnly && (
                <div className="sticky bottom-4 mt-6">
                  <Card className="card-trust border border-border shadow-lg">
                    <CardContent className="p-4 flex flex-wrap items-center justify-between gap-3">
                      <div className="text-sm text-muted-foreground">
                        {dirty ? <span className="text-warning">Unsaved changes</span> : 'All changes saved'}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button variant="outline" onClick={() => saveDraft()} disabled={saving}>
                          <Save className="w-3.5 h-3.5 mr-1" /> {saving ? 'Saving…' : 'Save Draft'}
                        </Button>
                        <Button onClick={submitForReview} disabled={saving}>
                          <Send className="w-3.5 h-3.5 mr-1" /> Submit for Review
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              )}

              {readOnly && (status === 'approved' || status === 'recorded') && (
                <div className="mt-4 card-trust border border-success/20 bg-success/5 rounded-xl p-4 flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-success shrink-0" />
                  <p className="text-sm text-navy">
                    These minutes have been {status === 'recorded' ? 'approved and recorded' : 'approved'}.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
