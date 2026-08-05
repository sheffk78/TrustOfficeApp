import { Link } from 'react-router-dom';
import { CalendarDays, ArrowRight, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { format, parseISO } from 'date-fns';

// Determine the status badge text for a tax deadline
function getDeadlineStatusText(d) {
  if (d.filing_status === 'filed') return 'Filed';
  if (d.filing_status === 'not_required') return 'N/A';
  if (d.is_overdue && d.filing_status === 'pending') return 'Overdue';
  return 'Pending';
}

// Determine the status badge color class for a tax deadline
function getDeadlineStatusClass(d) {
  const isFiledOrNotRequired = d.filing_status === 'filed' || d.filing_status === 'not_required';
  const isOverdue = d.is_overdue && d.filing_status === 'pending';
  if (isFiledOrNotRequired) return 'bg-success/10 text-success';
  if (isOverdue) return 'bg-error/10 text-error';
  return 'bg-navy/5 text-navy/60';
}

// Render the due-date subtitle for a deadline entry
function getDeadlineSubtitle(d, overdue) {
  if (overdue) {
    return <p className="text-xs text-error">Overdue by {Math.abs(d.days_remaining)} days</p>;
  }
  if (d.days_remaining <= 30) {
    return <p className="text-xs text-warning">Due in {d.days_remaining} days</p>;
  }
  return <p className="text-xs text-muted-foreground">Due {format(parseISO(d.due_date), 'MMMM d, yyyy')}</p>;
}

function DeadlineRow({ d }) {
  const overdue = d.is_overdue && d.filing_status === 'pending';
  return (
    <div key={d.entry_id} className={`flex items-center justify-between p-3 border ${overdue ? 'border-error/20 bg-error/5' : 'border-navy/10'} rounded`}>
      <div className="flex items-center gap-3">
        <div className="flex flex-col items-center min-w-[48px]">
          <div className="text-[10px] font-medium text-neutral-500 uppercase">{format(parseISO(d.due_date), 'MMM')}</div>
          <div className={`text-lg font-bold ${overdue ? 'text-error' : 'text-navy'}`}>{format(parseISO(d.due_date), 'd')}</div>
        </div>
        <div>
          <p className="font-medium text-sm text-navy">{d.description}</p>
          {getDeadlineSubtitle(d, overdue)}
        </div>
      </div>
      <span className={`font-mono text-[10px] uppercase tracking-wider px-2 py-1 rounded ${getDeadlineStatusClass(d)}`}>
        {getDeadlineStatusText(d)}
      </span>
    </div>
  );
}

function AllNotRequiredState({ taxDeadlines }) {
  const upcomingMonth = (() => {
    const upcoming = taxDeadlines.find(
      d => d.filing_status !== 'not_required' && d.filing_status !== 'filed'
    );
    return upcoming ? format(parseISO(upcoming.due_date), 'MMMM yyyy') : 'the upcoming tax year';
  })();

  return (
    <div className="p-6 bg-navy/5 border border-navy/10 text-center rounded">
      <p className="text-sm text-muted-foreground mb-1">Your next tax deadlines are in {upcomingMonth}.</p>
      <p className="text-xs text-muted-foreground">Past deadlines before your trust was created are marked as not applicable.</p>
    </div>
  );
}

/**
 * Tax Calendar widget — shows upcoming filing deadlines.
 * Hidden when benevolence mode (508c3) is enabled.
 * Handles loading, empty, all-not-required, and deadline list states.
 */
export function DashboardTaxCalendar({ selectedTrust, taxDeadlines, taxDeadlinesLoading }) {
  if (!selectedTrust || selectedTrust.benevolence_enabled) return null;

  const allNotRequired = taxDeadlines.length > 0 && taxDeadlines.every(d => d.filing_status === 'not_required');

  return (
    <div className="mb-8 card-trust corner-mark">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-navy/20 to-navy/10 flex items-center justify-center">
            <CalendarDays className="w-5 h-5 text-navy" />
          </div>
          <div>
            <h3 className="font-serif text-lg text-navy">Tax Calendar</h3>
            <p className="text-sm text-muted-foreground">Upcoming filing deadlines</p>
          </div>
        </div>
        <Link
          to="/calendar"
          className="text-navy hover:text-navy/70 font-mono text-xs uppercase tracking-widest flex items-center gap-1"
        >
          View All <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      {taxDeadlinesLoading ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="w-5 h-5 animate-spin text-navy mr-2" />
          <span className="text-sm text-muted-foreground">Loading deadlines...</span>
        </div>
      ) : taxDeadlines.length === 0 ? (
        <div className="p-6 bg-navy/5 border border-navy/10 text-center rounded">
          <p className="text-sm text-muted-foreground mb-3">No tax calendar generated yet.</p>
          <Link to="/calendar?type=tax">
            <Button size="sm" className="btn-secondary">
              <CalendarDays className="w-4 h-4 mr-2" />
              Set Up Tax Calendar
            </Button>
          </Link>
        </div>
      ) : allNotRequired ? (
        <AllNotRequiredState taxDeadlines={taxDeadlines} />
      ) : (
        <div className="space-y-3">
          {taxDeadlines.slice(0, 5).map(d => <DeadlineRow key={d.entry_id} d={d} />)}
        </div>
      )}
    </div>
  );
}