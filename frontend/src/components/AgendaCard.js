import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CalendarDays, ListOrdered, ChevronRight, CheckCircle2 } from 'lucide-react';

const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-600 border-slate-200',
  finalized: 'bg-warning/10 text-warning border-warning/20',
  in_progress: 'bg-blue-100 text-blue-700 border-blue-200',
  completed: 'bg-success/10 text-success border-success/20',
};

const STATUS_LABELS = {
  draft: 'Draft',
  finalized: 'Finalized',
  in_progress: 'In Progress',
  completed: 'Completed',
};

/**
 * AgendaCard — summary card for a meeting agenda.
 *
 * Props:
 *   agenda: { agenda_id, meeting_date, title, status, items: [] }
 *   compact: boolean — render a slimmer row variant for dense lists
 */
export default function AgendaCard({ agenda, compact = false }) {
  if (!agenda) return null;

  const itemCount = agenda.items?.length ?? agenda.item_count ?? 0;
  const status = agenda.status || 'draft';
  const meetingDate = agenda.meeting_date
    ? new Date(agenda.meeting_date).toLocaleDateString(undefined, {
        weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
      })
    : 'Date TBD';

  if (compact) {
    return (
      <Link to={`/governance/agendas/${agenda.agenda_id}`} className="block">
        <div className="card-trust border border-border rounded-xl p-4 flex items-center justify-between hover:border-navy/30 transition-colors">
          <div className="flex items-center gap-3 min-w-0">
            <CalendarDays className="w-4 h-4 text-navy shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-navy truncate">
                {agenda.title || `Meeting — ${meetingDate}`}
              </p>
              <p className="text-xs text-muted-foreground">
                {meetingDate} · {itemCount} item{itemCount === 1 ? '' : 's'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge variant="outline" className={STATUS_STYLES[status] || STATUS_STYLES.draft}>
              {STATUS_LABELS[status] || status}
            </Badge>
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          </div>
        </div>
      </Link>
    );
  }

  return (
    <Card className="card-trust border border-border">
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-navy/5 flex items-center justify-center">
              <CalendarDays className="w-4.5 h-4.5 text-navy" />
            </div>
            <div>
              <h3 className="font-semibold text-navy text-sm">
                {agenda.title || 'Trustee Meeting'}
              </h3>
              <p className="text-xs text-muted-foreground">{meetingDate}</p>
            </div>
          </div>
          <Badge variant="outline" className={STATUS_STYLES[status] || STATUS_STYLES.draft}>
            {status === 'completed' && <CheckCircle2 className="w-3 h-3 mr-1" />}
            {STATUS_LABELS[status] || status}
          </Badge>
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4">
          <ListOrdered className="w-3.5 h-3.5" />
          <span>{itemCount} agenda item{itemCount === 1 ? '' : 's'}</span>
        </div>

        <Link to={`/governance/agendas/${agenda.agenda_id}`}>
          <Button variant="outline" size="sm" className="w-full">
            Open Agenda
            <ChevronRight className="w-3.5 h-3.5 ml-1" />
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}
