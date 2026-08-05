// Summary counts row: desktop 4-col grid + mobile compact row.
// Hidden when the calendar is empty.
//
// Props:
//   summary – { total, completed, pending, overdue }
export default function SummaryRow({ summary }) {
  return (
    <div className="mb-4" data-testid="summary-row">
      {/* Desktop: 4-col grid */}
      <div className="hidden sm:grid grid-cols-4 gap-3">
        <div className="card-trust !p-4">
          <div className="text-2xl font-bold text-navy">{summary.total}</div>
          <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider">Total</div>
        </div>
        <div className="card-trust !p-4">
          <div className="text-2xl font-bold text-emerald-600">{summary.completed}</div>
          <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider">Completed</div>
        </div>
        <div className="card-trust !p-4">
          <div className="text-2xl font-bold text-navy">{summary.pending}</div>
          <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider">Pending</div>
        </div>
        <div className="card-trust !p-4">
          <div className="text-2xl font-bold text-red-600">{summary.overdue}</div>
          <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider">Overdue</div>
        </div>
      </div>
      {/* Mobile: compact row */}
      <div className="sm:hidden flex items-center justify-around py-2">
        <div className="text-center">
          <div className="text-lg font-bold text-navy">{summary.total}</div>
          <div className="text-[10px] text-muted-foreground font-mono uppercase">Total</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-emerald-600">{summary.completed}</div>
          <div className="text-[10px] text-muted-foreground font-mono uppercase">Done</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-navy">{summary.pending}</div>
          <div className="text-[10px] text-muted-foreground font-mono uppercase">Pending</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-red-600">{summary.overdue}</div>
          <div className="text-[10px] text-muted-foreground font-mono uppercase">Overdue</div>
        </div>
      </div>
    </div>
  );
}