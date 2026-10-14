import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import PageHeader from '@/components/PageHeader';

// Calendar page header: title + subtitle, help button, year selector, and
// the "New Task" button.
//
// Props:
//   year            – selected calendar year
//   onYearChange    – (yearNumber) => void
//   onCreateTask    – () => void
//   trustProfile    – { isFiscalYear, taxYearEndMonth, taxYearEndDay, ... }
export default function CalendarPageHeader({ year, onYearChange, onCreateTask, trustProfile }) {
  return (
    <PageHeader
      title="Calendar"
      subtitle="Trust tasks, tax deadlines, money events, and structure events in one place"
      actions={
        <>
          {/* Year selector */}
          <select
            value={year}
            onChange={(e) => onYearChange(Number(e.target.value))}
            className="border border-navy/20 bg-white px-3 py-2 text-sm font-mono"
            aria-label="Calendar year"
            data-testid="year-select"
          >
            {[year - 1, year, year + 1].map((y) => (
              <option key={y} value={y}>
                {trustProfile.isFiscalYear
                  ? `FY ${y} (ends ${trustProfile.taxYearEndMonth}/${trustProfile.taxYearEndDay})`
                  : `Calendar ${y}`}
              </option>
            ))}
          </select>
          <Button onClick={onCreateTask} className="btn-primary" data-testid="create-task-btn">
            <Plus className="w-4 h-4 mr-2" aria-hidden="true" /> New Task
          </Button>
        </>
      }
    />
  );
}