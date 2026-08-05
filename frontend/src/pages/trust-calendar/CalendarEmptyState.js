import { Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';

// Calendar empty states.
// mode='complete'  – no events at all for the year (offers Create Task + Generate Tax).
// mode='filtered'  – events exist but the current filters match nothing.
//
// Props:
//   mode                   – 'complete' | 'filtered'
//   year                   – selected calendar year
//   statusFilter           – current status filter key
//   typeFilter             – current type filter key
//   onCreateTask           – () => void   (complete mode only)
//   onGenerateTaxCalendar  – () => void  (both modes)
export default function CalendarEmptyState({
  mode,
  year,
  statusFilter,
  typeFilter,
  onCreateTask,
  onGenerateTaxCalendar,
}) {
  if (mode === 'complete') {
    return (
      <div className="card-trust text-center py-12" data-testid="empty-complete">
        <Calendar className="w-12 h-12 text-navy/30 mx-auto mb-4" aria-hidden="true" />
        <h3 className="font-serif text-xl text-navy mb-2">Set up your trust calendar</h3>
        <p className="text-muted-foreground mb-4 max-w-md mx-auto">
          Your calendar tracks both trust tasks and tax filing deadlines in one place.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Button onClick={onCreateTask} className="btn-secondary">
            Create a Task
          </Button>
          <Button onClick={onGenerateTaxCalendar} className="btn-primary" data-testid="empty-generate-tax">
            Generate Tax Deadlines
          </Button>
        </div>
      </div>
    );
  }

  // mode === 'filtered'
  const emptyLabel =
    statusFilter !== 'all'
      ? statusFilter
      : typeFilter === 'tax_deadline'
        ? 'tax'
        : 'matching';

  const emptyMessage = (() => {
    if (statusFilter === 'upcoming') return "No upcoming deadlines. You're all caught up.";
    if (statusFilter === 'overdue') return "No overdue items. Great work.";
    if (statusFilter === 'completed') return "No completed items yet.";
    if (statusFilter === 'all' && typeFilter === 'tax_deadline') return `No tax calendar for ${year}. Generate one to see deadlines.`;
    if (statusFilter === 'all' && typeFilter === 'governance_task') return "No trust tasks of this type.";
    if (statusFilter === 'all' && typeFilter === 'money') return "No money events (distributions, compensation, investments) for this year.";
    if (statusFilter === 'all' && typeFilter === 'structure') return "No structure events (entities, assets, communications) for this year.";
    return "No items match the current filters.";
  })();

  return (
    <div className="card-trust text-center py-12" data-testid="empty-filtered">
      <h3 className="font-serif text-xl text-navy mb-2">
        No {emptyLabel} items
      </h3>
      <p className="text-muted-foreground">{emptyMessage}</p>
      {statusFilter === 'all' && typeFilter === 'tax_deadline' && (
        <Button onClick={onGenerateTaxCalendar} className="btn-primary mt-4" data-testid="empty-tax-generate">
          Generate {year} Tax Calendar
        </Button>
      )}
    </div>
  );
}