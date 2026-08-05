import TrustCalendarCard from '@/components/TrustCalendarCard';

// Month-grouped event list with sticky month headers on mobile.
// Each event is rendered by the shared TrustCalendarCard component.
//
// Props:
//   grouped               – { [month: string]: event[] }
//   onComplete            – (taskId) => void
//   onUncomplete          – (taskId) => void
//   onDelete              – (taskId) => void
//   onToggleChecklist     – (taskId, itemIndex) => void
//   onMarkFiled           – (entryId) => void
//   onMarkExtended        – (entryId) => void
export default function EventList({
  grouped,
  onComplete,
  onUncomplete,
  onDelete,
  onToggleChecklist,
  onMarkFiled,
  onMarkExtended,
}) {
  return (
    <div className="space-y-6" data-testid="event-list">
      {Object.entries(grouped).map(([month, items]) => (
        <div key={month}>
          <h3
            className="text-sm font-semibold text-neutral-500 uppercase tracking-wide mb-2 sticky top-0 bg-white z-10 py-1 sm:static sm:bg-transparent sm:z-auto sm:py-0"
            data-testid={`month-header-${month}`}
          >
            {month}
          </h3>
          <div className="space-y-3">
            {items.map((event) => (
              <TrustCalendarCard
                key={event.id || event.entry_id}
                event={event}
                onComplete={onComplete}
                onUncomplete={onUncomplete}
                onDelete={onDelete}
                onToggleChecklist={onToggleChecklist}
                onMarkFiled={onMarkFiled}
                onMarkExtended={onMarkExtended}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}