import { STATUS_TABS, TYPE_FILTERS } from './calendarConfig';

// Renders the status filter tabs (with counts) and the type filter
// (desktop: segmented control, mobile: dropdown). Both are hidden when the
// calendar is empty.
//
// Props:
//   statusFilter     – current status filter key
//   onStatusChange   – (key) => void
//   typeFilter       – current type filter key
//   onTypeChange     – (key) => void
//   tabCounts        – { upcoming, overdue, completed, all } counts
export default function CalendarFilterControls({
  statusFilter,
  onStatusChange,
  typeFilter,
  onTypeChange,
  tabCounts,
}) {
  return (
    <>
      {/* ── Status Filter Tabs ──────────────────────────── */}
      <div className="flex gap-2 mb-3 flex-wrap" data-testid="status-tabs">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onStatusChange(tab.key)}
            className={`px-4 py-2 font-mono text-xs uppercase tracking-widest transition-colors ${
              statusFilter === tab.key
                ? 'bg-navy text-white'
                : 'bg-white border border-navy/20 text-navy hover:bg-navy/5'
            }`}
            data-testid={`filter-${tab.key}`}
          >
            {tab.label} ({tabCounts[tab.key]})
          </button>
        ))}
      </div>

      {/* ── Type Filter ─────────────────────────────────── */}
      <div className="mb-4" data-testid="type-filter">
        {/* Desktop: segmented control */}
        <div className="hidden sm:flex gap-2">
          {TYPE_FILTERS.map((tf) => (
            <button
              key={tf.key}
              onClick={() => onTypeChange(tf.key)}
              className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider transition-colors ${
                typeFilter === tf.key
                  ? 'bg-navy/10 text-navy border border-navy/30'
                  : 'text-muted-foreground border border-transparent hover:text-navy'
              }`}
              data-testid={`type-filter-${tf.key}`}
            >
              {tf.label}
            </button>
          ))}
        </div>
        {/* Mobile: dropdown */}
        <select
          value={typeFilter}
          onChange={(e) => onTypeChange(e.target.value)}
          className="sm:hidden border border-navy/20 bg-white px-3 py-2 text-sm w-full"
          aria-label="Filter by type"
        >
          {TYPE_FILTERS.map((tf) => (
            <option key={tf.key} value={tf.key}>{tf.label}</option>
          ))}
        </select>
      </div>
    </>
  );
}