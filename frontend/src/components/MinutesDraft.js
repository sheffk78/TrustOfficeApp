import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { FileText, ChevronRight, User, Clock } from 'lucide-react';

const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-600 border-slate-200',
  pending_review: 'bg-warning/10 text-warning border-warning/20',
  in_review: 'bg-blue-100 text-blue-700 border-blue-200',
  changes_requested: 'bg-red-100 text-red-700 border-red-200',
  approved: 'bg-success/10 text-success border-success/20',
  recorded: 'bg-navy/10 text-navy border-navy/20',
};

const STATUS_LABELS = {
  draft: 'Draft',
  pending_review: 'Pending Review',
  in_review: 'In Review',
  changes_requested: 'Changes Requested',
  approved: 'Approved',
  recorded: 'Recorded',
};

/**
 * MinutesDraft — minutes draft card for lists.
 *
 * Props:
 *   minutes: { minutes_id, title, status, updated_at, meeting_date, approver_name, agenda_id }
 */
export default function MinutesDraft({ minutes }) {
  if (!minutes) return null;

  const status = minutes.status || 'draft';
  const lastEdited = minutes.updated_at
    ? new Date(minutes.updated_at).toLocaleDateString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric',
      })
    : null;
  const meetingDate = minutes.meeting_date
    ? new Date(minutes.meeting_date).toLocaleDateString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric',
      })
    : null;

  return (
    <Link to={`/governance/minutes/${minutes.minutes_id}`} className="block">
      <div className="card-trust border border-border rounded-xl p-4 hover:border-navy/30 transition-colors">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-navy/5 flex items-center justify-center shrink-0 mt-0.5">
              <FileText className="w-4 h-4 text-navy" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-navy truncate">
                {minutes.title || `Minutes${meetingDate ? ` — ${meetingDate}` : ''}`}
              </p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-muted-foreground">
                {lastEdited && (
                  <span className="inline-flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    Edited {lastEdited}
                  </span>
                )}
                {minutes.approver_name && (
                  <span className="inline-flex items-center gap-1">
                    <User className="w-3 h-3" />
                    Approver: {minutes.approver_name}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge variant="outline" className={STATUS_STYLES[status] || STATUS_STYLES.draft}>
              {STATUS_LABELS[status] || status}
            </Badge>
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          </div>
        </div>
      </div>
    </Link>
  );
}
