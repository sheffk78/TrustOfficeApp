import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useSearchParams } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import {
  Calendar, Plus, AlertTriangle, Clock, X,
} from 'lucide-react';
import { format, parseISO, addDays } from 'date-fns';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import PageHelpButton from '@/components/PageHelpButton';
import TrustCalendarCard from '@/components/TrustCalendarCard';

// Task types for the create-task modal (minus tax_filing_1041 and tax_filing_k1,
// which are now handled by the tax calendar)
const TASK_TYPES = [
  { value: 'annual_review', label: 'Annual Review' },
  { value: 'quarterly_review', label: 'Quarterly Review' },
  { value: 'compensation_review', label: 'Compensation Review' },
  { value: 'distribution_review', label: 'Distribution Review' },
  { value: 'insurance_compliance', label: 'Insurance Compliance' },
  { value: 'transaction_review', label: 'Transaction Review' },
  { value: 'custom', label: 'Custom Task' },
];

const STATUS_TABS = [
  { key: 'upcoming', label: 'Upcoming' },
  { key: 'overdue', label: 'Overdue' },
  { key: 'completed', label: 'Completed' },
  { key: 'all', label: 'All' },
];

const TYPE_FILTERS = [
  { key: 'all', label: 'All Types' },
  { key: 'governance_task', label: 'Trust Tasks' },
  { key: 'tax_deadline', label: 'Tax Filings' },
];

export default function TrustCalendarPage() {
  const { selectedTrust } = useAuth();
  const [searchParams] = useSearchParams();

  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [year, setYear] = useState(new Date().getFullYear());
  const [statusFilter, setStatusFilter] = useState('upcoming');
  const [typeFilter, setTypeFilter] = useState(() => {
    const qp = searchParams.get('type');
    if (qp === 'tax') return 'tax_deadline';
    if (qp === 'tasks') return 'governance_task';
    return 'all';
  });
  const [showModal, setShowModal] = useState(false);
  const [nextUpConfirm, setNextUpConfirm] = useState(null); // null | { action: 'filed'|'extended', entryId, label, taxYear }
  const [newTask, setNewTask] = useState({
    task_type: 'quarterly_review',
    due_date: format(addDays(new Date(), 30), 'yyyy-MM-dd'),
    description: '',
  });
  const [trustProfile, setTrustProfile] = useState({});

  // ── Load unified calendar feed ─────────────────────────────
  const loadEvents = useCallback(async () => {
    if (!selectedTrust) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/calendar/events?trust_id=${selectedTrust.trust_id}`);
      if (!res.ok) throw new Error('Failed to load calendar');
      const data = await res.json();
      setEvents(data.events || []);
    } catch (e) {
      console.error('Failed to load calendar events:', e);
      showError(toast, e, { operation: 'load', page: 'TrustCalendar' });
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [selectedTrust]);

  useEffect(() => {
    if (selectedTrust) {
      loadEvents();
      setTrustProfile({
        ein: selectedTrust?.ein || '',
        stateCode: selectedTrust?.state_code || '',
        taxYearEndMonth: selectedTrust?.tax_year_end_month || 12,
        taxYearEndDay: selectedTrust?.tax_year_end_day || 31,
        isFiscalYear: selectedTrust?.is_fiscal_year || false,
      });
    } else {
      setLoading(false);
    }
  }, [selectedTrust, loadEvents]);

  const formatDate = (dateString) => {
    try {
      return format(parseISO(dateString), 'MMM d, yyyy');
    } catch {
      return dateString;
    }
  };

  // ── Year filtering: filter ALL events by due_date calendar year ──
  const yearEvents = useMemo(() => {
    return events.filter(e => {
      if (!e.date) return false;
      try {
        return parseISO(e.date).getFullYear() === year;
      } catch {
        return false;
      }
    });
  }, [events, year]);

  // ── Tax entries for selected year (for banner + generate button) ──
  const taxEntriesForYear = useMemo(
    () => yearEvents.filter(e => e.event_type === 'tax_deadline'),
    [yearEvents]
  );

  const hasTaxCalendar = taxEntriesForYear.length > 0;

  // ── Summary counts (from yearEvents, before status/type filter) ──
  const summary = useMemo(() => {
    const total = yearEvents.length;
    const completed = yearEvents.filter(e => e.status === 'completed').length;
    const overdue = yearEvents.filter(e => e.status === 'overdue').length;
    const pending = total - completed - overdue;
    return { total, completed, pending, overdue };
  }, [yearEvents]);

  // ── Status tab counts (within current type filter) ──
  const tabCounts = useMemo(() => {
    const typeFiltered = typeFilter === 'all'
      ? yearEvents
      : yearEvents.filter(e => e.event_type === typeFilter);
    return {
      upcoming: typeFiltered.filter(e => e.status === 'upcoming').length,
      overdue: typeFiltered.filter(e => e.status === 'overdue').length,
      completed: typeFiltered.filter(e => e.status === 'completed').length,
      all: typeFiltered.length,
    };
  }, [yearEvents, typeFilter]);

  // ── "Next Up" widget: most urgent pending item ──────────────
  const nextUp = useMemo(() => {
    const pending = yearEvents.filter(e =>
      e.status !== 'completed' && e.date
    );
    if (pending.length === 0) return null;
    pending.sort((a, b) => a.date.localeCompare(b.date));
    return pending[0];
  }, [yearEvents]);

  // ── Filtered + grouped events ──────────────────────────────
  const filteredEvents = useMemo(() => {
    let result = yearEvents;
    // Status filter
    if (statusFilter !== 'all') {
      result = result.filter(e => e.status === statusFilter);
    }
    // Type filter
    if (typeFilter !== 'all') {
      result = result.filter(e => e.event_type === typeFilter);
    }
    return result;
  }, [yearEvents, statusFilter, typeFilter]);

  const grouped = useMemo(() => {
    const byMonth = {};
    filteredEvents.forEach(e => {
      if (!e.date) return;
      try {
        const mo = format(parseISO(e.date), 'MMMM yyyy');
        if (!byMonth[mo]) byMonth[mo] = [];
        byMonth[mo].push(e);
      } catch { /* skip bad dates */ }
    });
    return byMonth;
  }, [filteredEvents]);

  // ── Tax calendar actions ───────────────────────────────────
  const generateTaxCalendar = async () => {
    if (!selectedTrust) return;
    try {
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/tax-calendar/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tax_year: year }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 409) {
          toast.info(data.detail || `Tax calendar for ${year} already exists`);
          return;
        }
        throw new Error(data.detail || 'Failed to generate');
      }
      toast.success(`Generated ${data.entries_created} tax deadlines for ${year}`);
      loadEvents();
    } catch (e) {
      showError(toast, e, { operation: 'generate_tax_calendar', page: 'TrustCalendar' });
    }
  };

  const markFiled = async (entryId) => {
    try {
      const res = await fetchWithAuth(`/tax-calendar/${entryId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filing_status: 'filed' }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to update');
      }
      toast.success('Marked as filed');
      loadEvents();
    } catch (e) {
      showError(toast, e, { operation: 'mark_filed', page: 'TrustCalendar' });
    }
  };

  const markExtended = async (entryId) => {
    try {
      const res = await fetchWithAuth(`/tax-calendar/${entryId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filing_status: 'extended' }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to update');
      }
      toast.success('Marked as extended');
      loadEvents();
    } catch (e) {
      showError(toast, e, { operation: 'mark_extended', page: 'TrustCalendar' });
    }
  };

  // ── Governance task actions ────────────────────────────────
  const handleCreateTask = async () => {
    if (!selectedTrust) return;
    try {
      const res = await fetchWithAuth('/tasks', {
        method: 'POST',
        body: JSON.stringify({ trust_id: selectedTrust.trust_id, ...newTask }),
      });
      if (res.ok) {
        toast.success('Task created');
        setShowModal(false);
        setNewTask({
          task_type: 'quarterly_review',
          due_date: format(addDays(new Date(), 30), 'yyyy-MM-dd'),
          description: '',
        });
        loadEvents();
      }
    } catch (e) {
      showError(toast, e, { operation: 'create', page: 'TrustCalendar' });
    }
  };

  const handleCompleteTask = async (taskId) => {
    try {
      const res = await fetchWithAuth(`/tasks/${taskId}/complete`, { method: 'PATCH' });
      if (res.ok) {
        toast.success('Task completed');
        loadEvents();
      }
    } catch (e) {
      showError(toast, e, { operation: 'complete', page: 'TrustCalendar' });
    }
  };

  const handleUncompleteTask = async (taskId) => {
    try {
      const res = await fetchWithAuth(`/tasks/${taskId}/uncomplete`, { method: 'PATCH' });
      if (res.ok) {
        toast.info('Task marked incomplete');
        loadEvents();
      }
    } catch (e) {
      showError(toast, e, { operation: 'update', page: 'TrustCalendar' });
    }
  };

  const handleDeleteTask = async (taskId) => {
    if (!confirm('Delete this task?')) return;
    try {
      const res = await fetchWithAuth(`/tasks/${taskId}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success('Task deleted');
        loadEvents();
      }
    } catch (e) {
      showError(toast, e, { operation: 'delete', page: 'TrustCalendar' });
    }
  };

  const handleToggleChecklist = async (taskId, itemIndex) => {
    const task = events.find(e => e.id === taskId);
    if (!task || !task.checklist) return;
    const completed = !task.checklist[itemIndex]?.completed;
    try {
      const res = await fetchWithAuth(`/tasks/${taskId}/checklist/${itemIndex}`, {
        method: 'PATCH',
        body: JSON.stringify({ completed }),
      });
      if (res.ok) loadEvents();
    } catch (e) {
      showError(toast, e, { operation: 'update', page: 'TrustCalendar' });
    }
  };

  // ── Render ─────────────────────────────────────────────────
  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content dot-grid">
          <div className="page-container">
            <div className="card-trust text-center py-12">
              <Calendar className="w-12 h-12 text-navy/30 mx-auto mb-4" aria-hidden="true" />
              <h2 className="font-serif text-xl text-navy mb-1">Select a trust</h2>
              <p className="text-muted-foreground">Choose a trust from the sidebar to view its calendar.</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  const showTaxInfoBar = typeFilter === 'all' || typeFilter === 'tax_deadline';
  const showGenerateBtn = (typeFilter === 'all' || typeFilter === 'tax_deadline') && !hasTaxCalendar;

  // Empty state logic
  const isEmpty = yearEvents.length === 0;
  const isFilteredEmpty = !isEmpty && filteredEvents.length === 0;

  return (
    <div className="main-layout" data-testid="trust-calendar-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* ── Page Header ──────────────────────────────────── */}
          <div className="page-header flex items-center justify-between flex-wrap gap-3">
            <div>
              <h1 className="page-title">Calendar</h1>
              <p className="page-subtitle">
                Trust tasks and tax filing deadlines in one place
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <PageHelpButton
                items={[
                  { text: 'Track governance tasks and tax filing deadlines in one unified calendar' },
                  { text: 'Filter by status (upcoming, overdue, completed) and type (trust tasks, tax filings)' },
                  { text: 'Mark tax filings as filed or extended, complete governance tasks' },
                ]}
                taPrompt="Walk me through the Calendar and how to manage trust tasks and tax deadlines"
              />
              {/* Year selector */}
              <select
                value={year}
                onChange={e => setYear(Number(e.target.value))}
                className="border border-navy/20 bg-white px-3 py-2 text-sm font-mono"
                aria-label="Calendar year"
                data-testid="year-select"
              >
                {[year - 1, year, year + 1].map(y => (
                  <option key={y} value={y}>
                    {trustProfile.isFiscalYear
                      ? `FY ${y} (ends ${trustProfile.taxYearEndMonth}/${trustProfile.taxYearEndDay})`
                      : `Calendar ${y}`}
                  </option>
                ))}
              </select>
              <Button
                onClick={() => setShowModal(true)}
                className="btn-primary"
                data-testid="create-task-btn"
              >
                <Plus className="w-4 h-4 mr-2" aria-hidden="true" /> New Task
              </Button>
            </div>
          </div>

          {/* ── "Next Up" Widget ─────────────────────────────── */}
          {!loading && nextUp && (
            <div className="mb-4" data-testid="next-up-widget">
              <div className="card-trust border-l-4 border-l-gold bg-gold/5">
                <div className="flex items-center justify-between gap-4 flex-wrap">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-10 h-10 bg-gold/20">
                      {nextUp.status === 'overdue'
                        ? <AlertTriangle className="w-5 h-5 text-red-600" aria-hidden="true" />
                        : <Clock className="w-5 h-5 text-gold" aria-hidden="true" />}
                    </div>
                    <div>
                      <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Next Up</div>
                      <div className="font-medium text-navy">
                        {nextUp.event_type === 'tax_deadline'
                          ? (nextUp.title || nextUp.deadline_type)
                          : (nextUp.title || nextUp.task_type?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))}
                      </div>
                      <div className="font-mono text-xs text-muted-foreground">
                        Due {formatDate(nextUp.date)}
                        {typeof nextUp.days_remaining === 'number' && (
                          nextUp.status === 'overdue'
                            ? ` · ${Math.abs(nextUp.days_remaining)} days overdue`
                            : ` · ${nextUp.days_remaining} days left`
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {nextUp.event_type === 'tax_deadline' && nextUp.filing_status === 'pending' && (
                      <>
                        <Button size="sm" className="btn-primary" onClick={() => setNextUpConfirm({ action: 'filed', entryId: nextUp.entry_id, label: nextUp.title || nextUp.deadline_type, taxYear: nextUp.tax_year })}>
                          Mark Filed
                        </Button>
                        <Button size="sm" variant="outline" className="border-warning text-warning" onClick={() => setNextUpConfirm({ action: 'extended', entryId: nextUp.entry_id, label: nextUp.title || nextUp.deadline_type, taxYear: nextUp.tax_year })}>
                          Extend
                        </Button>
                      </>
                    )}
                    {nextUp.event_type === 'governance_task' && nextUp.status !== 'completed' && (
                      <Button size="sm" className="btn-primary" onClick={() => handleCompleteTask(nextUp.id)}>
                        Complete
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── Tax Setup Banner ────────────────────────────── */}
          {!loading && !hasTaxCalendar && (
            <div className="mb-4 flex items-center justify-between gap-3 bg-warning/5 border border-warning/20 px-4 py-3" data-testid="tax-setup-banner">
              <div className="text-sm text-warning">
                Tax deadlines not set up for {year}.
              </div>
              <Button size="sm" onClick={generateTaxCalendar} className="btn-primary" data-testid="generate-tax-banner-btn">
                Generate
              </Button>
            </div>
          )}

          {/* ── Summary Row ─────────────────────────────────── */}
          {!loading && !isEmpty && (
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
          )}

          {/* ── Status Filter Tabs ──────────────────────────── */}
          {!loading && !isEmpty && (
            <div className="flex gap-2 mb-3 flex-wrap" data-testid="status-tabs">
              {STATUS_TABS.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setStatusFilter(tab.key)}
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
          )}

          {/* ── Type Filter ─────────────────────────────────── */}
          {!loading && !isEmpty && (
            <div className="mb-4" data-testid="type-filter">
              {/* Desktop: segmented control */}
              <div className="hidden sm:flex gap-2">
                {TYPE_FILTERS.map(tf => (
                  <button
                    key={tf.key}
                    onClick={() => setTypeFilter(tf.key)}
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
                onChange={e => setTypeFilter(e.target.value)}
                className="sm:hidden border border-navy/20 bg-white px-3 py-2 text-sm w-full"
                aria-label="Filter by type"
              >
                {TYPE_FILTERS.map(tf => (
                  <option key={tf.key} value={tf.key}>{tf.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* ── Trust Profile Info Bar ──────────────────────── */}
          {!loading && showTaxInfoBar && filteredEvents.some(e => e.event_type === 'tax_deadline') && (
            <div className="mb-4 bg-white border border-navy/10 px-4 py-2.5" data-testid="trust-profile-bar">
              <div className="text-sm text-muted-foreground truncate">
                {trustProfile.ein && trustProfile.taxYearEndMonth ? (
                  <>
                    EIN: <b className="text-navy">{trustProfile.ein}</b> · {' '}
                    {trustProfile.isFiscalYear ? 'Fiscal year ends' : 'Tax year ends'}: {' '}
                    <b className="text-navy">{trustProfile.taxYearEndMonth}/{trustProfile.taxYearEndDay}</b>
                    {trustProfile.isFiscalYear && (
                      <span className="ml-2 text-xs bg-warning/10 text-warning px-1.5 py-0.5">Fiscal</span>
                    )}
                  </>
                ) : (
                  <>Set your trust EIN and tax year end in <b className="text-navy">Settings → Trust Profile</b> for accurate deadlines.</>
                )}
              </div>
            </div>
          )}

          {/* ── Generate Tax Calendar button (in-flow) ──────── */}
          {!loading && showGenerateBtn && !isEmpty && (
            <div className="mb-4" data-testid="generate-tax-inline">
              <Button onClick={generateTaxCalendar} className="btn-primary" data-testid="generate-tax-btn">
                Generate {year} Tax Calendar
              </Button>
            </div>
          )}

          {/* ── Events / Empty States ───────────────────────── */}
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map(i => (
                <div key={i} className="card-trust">
                  <div className="skeleton h-6 w-48 mb-2"></div>
                  <div className="skeleton h-4 w-32"></div>
                </div>
              ))}
            </div>
          ) : isEmpty ? (
            /* Complete empty state */
            <div className="card-trust text-center py-12" data-testid="empty-complete">
              <Calendar className="w-12 h-12 text-navy/30 mx-auto mb-4" aria-hidden="true" />
                <h3 className="font-serif text-xl text-navy mb-2">Set up your trust calendar</h3>
                <p className="text-muted-foreground mb-4 max-w-md mx-auto">
                  Your calendar tracks both trust tasks and tax filing deadlines in one place.
                </p>
              <div className="flex items-center justify-center gap-3">
                <Button onClick={() => setShowModal(true)} className="btn-secondary">
                  Create a Task
                </Button>
                <Button onClick={generateTaxCalendar} className="btn-primary" data-testid="empty-generate-tax">
                  Generate Tax Deadlines
                </Button>
              </div>
            </div>
          ) : isFilteredEmpty ? (
            /* Filtered empty state */
            <div className="card-trust text-center py-12" data-testid="empty-filtered">
              <h3 className="font-serif text-xl text-navy mb-2">
                No {statusFilter !== 'all' ? statusFilter : typeFilter === 'tax_deadline' ? 'tax' : 'matching'} items
              </h3>
              <p className="text-muted-foreground">
                {statusFilter === 'upcoming' && "No upcoming deadlines. You're all caught up."}
                {statusFilter === 'overdue' && "No overdue items. Great work."}
                {statusFilter === 'completed' && "No completed items yet."}
                {statusFilter === 'all' && typeFilter === 'tax_deadline' && `No tax calendar for ${year}. Generate one to see deadlines.`}
                {statusFilter === 'all' && typeFilter === 'governance_task' && "No trust tasks of this type."}
                {statusFilter === 'all' && typeFilter === 'all' && "No items match the current filters."}
              </p>
              {statusFilter === 'all' && typeFilter === 'tax_deadline' && (
                <Button onClick={generateTaxCalendar} className="btn-primary mt-4" data-testid="empty-tax-generate">
                  Generate {year} Tax Calendar
                </Button>
              )}
            </div>
          ) : (
            /* Month-grouped event list with sticky headers on mobile */
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
                    {items.map(event => (
                      <TrustCalendarCard
                        key={event.id || event.entry_id}
                        event={event}
                        onComplete={handleCompleteTask}
                        onUncomplete={handleUncompleteTask}
                        onDelete={handleDeleteTask}
                        onToggleChecklist={handleToggleChecklist}
                        onMarkFiled={markFiled}
                        onMarkExtended={markExtended}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* ── Create Task Modal ──────────────────────────────── */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowModal(false)}>
          <div className="bg-white p-6 w-full max-w-md corner-mark" onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === 'Escape') setShowModal(false); }} role="dialog" aria-modal="true" aria-label="Create task" data-testid="create-task-modal">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-serif text-xl text-navy">Create Task</h2>
              <button onClick={() => setShowModal(false)} className="text-navy hover:text-navy/70" aria-label="Close dialog">
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="label-trust mb-2 block">Task Type</label>
                <select
                  value={newTask.task_type}
                  onChange={e => setNewTask({ ...newTask, task_type: e.target.value })}
                  className="input-trust w-full"
                  data-testid="task-type-select"
                >
                  {TASK_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label-trust mb-2 block">Due Date</label>
                <Input
                  type="date"
                  value={newTask.due_date}
                  onChange={e => setNewTask({ ...newTask, due_date: e.target.value })}
                  className="input-trust"
                  data-testid="task-due-date"
                />
              </div>

              <div>
                <label className="label-trust mb-2 block">Description (Optional)</label>
                <Input
                  value={newTask.description}
                  onChange={e => setNewTask({ ...newTask, description: e.target.value })}
                  placeholder="Add task description..."
                  className="input-trust"
                  data-testid="task-description"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <Button onClick={() => setShowModal(false)} variant="outline" className="flex-1 btn-secondary">
                  Cancel
                </Button>
                <Button onClick={handleCreateTask} className="flex-1 btn-primary" data-testid="submit-task-btn">
                  Create Task
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Next Up Confirm Dialog ─────────────────────────── */}
      {nextUpConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setNextUpConfirm(null)}>
          <div className="bg-white p-6 w-full max-w-sm corner-mark" onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === 'Escape') setNextUpConfirm(null); if (e.key === 'Enter') { if (nextUpConfirm.action === 'filed') markFiled(nextUpConfirm.entryId); else markExtended(nextUpConfirm.entryId); setNextUpConfirm(null); } }} role="dialog" aria-modal="true" aria-label={nextUpConfirm.action === 'filed' ? 'Confirm mark as filed' : 'Confirm mark as extended'} data-testid="nextup-confirm">
            <h3 className="font-serif text-lg text-navy mb-2">
              {nextUpConfirm.action === 'filed' ? 'Confirm: Mark as Filed' : 'Confirm: Mark as Extended'}
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              {nextUpConfirm.action === 'filed'
                ? `Mark "${nextUpConfirm.label}" as filed for tax year ${nextUpConfirm.taxYear}?`
                : `Mark "${nextUpConfirm.label}" as extended?`}
            </p>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1 btn-secondary" onClick={() => setNextUpConfirm(null)}>
                Cancel
              </Button>
              <Button
                className="flex-1 btn-primary"
                onClick={() => {
                  if (nextUpConfirm.action === 'filed') markFiled(nextUpConfirm.entryId);
                  else markExtended(nextUpConfirm.entryId);
                  setNextUpConfirm(null);
                }}
              >
                Confirm
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}