import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import PageHelpButton from '@/components/PageHelpButton';

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
    <div className="page-header flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 className="page-title">Calendar</h1>
        <p className="page-subtitle">
          Trust tasks, tax deadlines, money events, and structure events in one place
        </p>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <PageHelpButton
          items={[
            { text: 'Track governance tasks, tax filing deadlines, money events, and structure events in one unified calendar' },
            { text: 'Filter by status (upcoming, overdue, completed) and type (trust tasks, tax filings, money events, structure events)' },
            { text: 'Money events include distributions, compensation payments, and investment purchases' },
            { text: 'Structure events include entity formations, asset conveyances, and communications' },
            { text: 'Mark tax filings as filed or extended, complete governance tasks' },
          ]}
          taPrompt="Walk me through the Calendar and how to manage trust tasks, tax deadlines, money events, and structure events"
        />
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
      </div>
    </div>
  );
}