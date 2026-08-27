import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import AgendaCard from '@/components/AgendaCard';
import MinutesDraft from '@/components/MinutesDraft';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  CalendarDays, Plus, FileText, CheckCircle2, ArrowRight,
} from 'lucide-react';

const MINUTES_STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-600 border-slate-200',
  pending_review: 'bg-warning/10 text-warning border-warning/20',
  in_review: 'bg-blue-100 text-blue-700 border-blue-200',
  changes_requested: 'bg-red-100 text-red-700 border-red-200',
  approved: 'bg-success/10 text-success border-success/20',
  recorded: 'bg-navy/10 text-navy border-navy/20',
};

function MeetingRow({ meeting, trustId }) {
  const agendaStatus = meeting.agenda_status || (meeting.agenda_id ? 'finalized' : null);
  const minutesStatus = meeting.minutes_status || null;

  return (
    <div className="card-trust border border-border rounded-xl p-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <p className="text-sm font-medium text-navy">
            {meeting.title || `Meeting — ${meeting.meeting_date
              ? new Date(meeting.meeting_date).toLocaleDateString(undefined, {
                  month: 'long', day: 'numeric', year: 'numeric',
                })
              : 'Date TBD'}`}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {meeting.meeting_date
              ? new Date(meeting.meeting_date).toLocaleDateString(undefined, {
                  weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
                })
              : 'No date set'}
            {meeting.item_count != null && ` · ${meeting.item_count} agenda item${meeting.item_count === 1 ? '' : 's'}`}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap shrink-0">
          {agendaStatus && (
            <Badge variant="outline" className="bg-slate-100 text-slate-600 border-slate-200 capitalize">
              Agenda: {agendaStatus.replace('_', ' ')}
            </Badge>
          )}
          {minutesStatus ? (
            <Badge variant="outline" className={`${MINUTES_STATUS_STYLES[minutesStatus] || MINUTES_STATUS_STYLES.draft} capitalize`}>
              Minutes: {minutesStatus.replace('_', ' ')}
            </Badge>
          ) : (
            <Badge variant="outline" className="bg-slate-50 text-slate-500 border-slate-200">
              No minutes
            </Badge>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 mt-3 flex-wrap">
        {meeting.agenda_id && (
          <Link to={`/governance/agendas/${meeting.agenda_id}`}>
            <Button variant="outline" size="sm">
              Agenda <ArrowRight className="w-3 h-3 ml-1" />
            </Button>
          </Link>
        )}
        {meeting.minutes_id && (
          <Link to={`/governance/minutes/${meeting.minutes_id}`}>
            <Button variant="outline" size="sm">
              Minutes <ArrowRight className="w-3 h-3 ml-1" />
            </Button>
          </Link>
        )}
        {minutesStatus === 'recorded' && (
          <span className="inline-flex items-center text-xs text-success">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Complete
          </span>
        )}
      </div>
    </div>
  );
}

export default function MeetingHistory() {
  const { trustId } = useParams();
  const { selectedTrust } = useAuth();
  const [loading, setLoading] = useState(true);
  const [meetings, setMeetings] = useState([]);
  const [pendingAgendas, setPendingAgendas] = useState([]);
  const [draftMinutes, setDraftMinutes] = useState([]);
  const [generating, setGenerating] = useState(false);

  const effectiveTrustId = trustId || selectedTrust?.trust_id;

  const loadHistory = useCallback(async () => {
    if (!effectiveTrustId) return;
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/meetings/${effectiveTrustId}/history`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load meeting history');
      setMeetings(data.meetings || data.history || []);
      setPendingAgendas(data.pending_agendas || []);
      setDraftMinutes(data.draft_minutes || []);
    } catch (e) {
      showError(toast, e, { operation: 'load_meeting_history', page: 'MeetingHistory' });
    } finally {
      setLoading(false);
    }
  }, [effectiveTrustId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const generateAgenda = async () => {
    if (!effectiveTrustId) return;
    setGenerating(true);
    try {
      const res = await fetchWithAuth(`/meetings/${effectiveTrustId}/agendas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to generate agenda');
      toast.success('Agenda generated');
      loadHistory();
    } catch (e) {
      showError(toast, e, { operation: 'generate_agenda', page: 'MeetingHistory' });
    } finally {
      setGenerating(false);
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content mobile-layout-offset">
          <div className="page-container">
            <div className="card-trust border border-border p-12 flex flex-col items-center justify-center rounded">
              <CalendarDays className="w-12 h-12 text-muted-foreground/60 mb-3" />
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to view meeting history.</p>
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
              <h1 className="page-title">Meeting History</h1>
              <p className="page-subtitle">
                Past trustee meetings, agendas, and minutes for {selectedTrust.trust_name || 'this trust'}
              </p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'Review past trustee meetings and their documentation status' },
                  { text: 'Open agendas and minutes to keep records up to date' },
                  { text: 'Generate an agenda when it is time for your next meeting' },
                ]}
                taPrompt="Walk me through my meeting history"
              />
              <Link to={`/governance/approvals/${effectiveTrustId}`}>
                <Button variant="outline">Approval Workflow</Button>
              </Link>
              <Button onClick={generateAgenda} disabled={generating}>
                <Plus className="w-4 h-4 mr-1" />
                {generating ? 'Generating…' : 'Generate Agenda'}
              </Button>
            </div>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-24 card-trust border border-border rounded animate-pulse" />
              ))}
            </div>
          ) : (
            <>
              {/* In-progress work */}
              {(pendingAgendas.length > 0 || draftMinutes.length > 0) && (
                <div className="mb-6">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                    In Progress
                  </h2>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {pendingAgendas.map((a) => (
                      <AgendaCard key={a.agenda_id} agenda={a} />
                    ))}
                    {draftMinutes.map((m) => (
                      <MinutesDraft key={m.minutes_id} minutes={m} />
                    ))}
                  </div>
                </div>
              )}

              {/* Past meetings */}
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                Past Meetings
              </h2>
              {meetings.length === 0 ? (
                <div className="card-trust border border-border p-12 flex flex-col items-center justify-center rounded">
                  <FileText className="w-12 h-12 text-muted-foreground/60 mb-3" />
                  <h2 className="text-xl font-semibold text-navy mb-1">No meetings yet</h2>
                  <p className="text-sm text-muted-foreground mb-4 text-center max-w-md">
                    Generate an agenda to prepare for your first documented trustee meeting.
                    Regular meeting minutes are a core part of trust administration.
                  </p>
                  <Button onClick={generateAgenda} disabled={generating}>
                    <Plus className="w-4 h-4 mr-1" />
                    {generating ? 'Generating…' : 'Generate your first agenda'}
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {meetings.map((m) => (
                    <MeetingRow key={m.meeting_id || m.agenda_id} meeting={m} trustId={effectiveTrustId} />
                  ))}
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
