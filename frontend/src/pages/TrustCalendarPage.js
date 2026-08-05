import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useSearchParams } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Calendar } from 'lucide-react';
import { format, addDays } from 'date-fns';
import { toast } from 'sonner';
import { showError } from '../utils/errors';

// Extracted config + helpers + sub-components (frontend/src/pages/trust-calendar/)
import { initialTypeFilter, defaultNewTask } from './trust-calendar/calendarConfig';
import { useCalendarData } from './trust-calendar/useCalendarData';
import CalendarPageHeader from './trust-calendar/CalendarPageHeader';
import SummaryRow from './trust-calendar/SummaryRow';
import CalendarFilterControls from './trust-calendar/CalendarFilterControls';
import NextUpWidget from './trust-calendar/NextUpWidget';
import TrustProfileBar from './trust-calendar/TrustProfileBar';
import CalendarEmptyState from './trust-calendar/CalendarEmptyState';
import EventList from './trust-calendar/EventList';
import CreateTaskModal from './trust-calendar/CreateTaskModal';
import NextUpConfirmDialog from './trust-calendar/NextUpConfirmDialog';

export default function TrustCalendarPage() {
  const { selectedTrust } = useAuth();
  const [searchParams] = useSearchParams();

  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [year, setYear] = useState(new Date().getFullYear());
  const [statusFilter, setStatusFilter] = useState('upcoming');
  const [typeFilter, setTypeFilter] = useState(() => initialTypeFilter(searchParams));
  const [showModal, setShowModal] = useState(false);
  const [nextUpConfirm, setNextUpConfirm] = useState(null); // null | { action: 'filed'|'extended', entryId, label, taxYear }
  const [newTask, setNewTask] = useState(() => defaultNewTask(addDays, format));
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

  // ── Derived calendar data (year filter, summary, tabs, next-up, grouped) ──
  const {
    yearEvents,
    hasTaxCalendar,
    summary,
    tabCounts,
    nextUp,
    filteredEvents,
    grouped,
    isEmpty,
    isFilteredEmpty,
  } = useCalendarData(events, year, statusFilter, typeFilter);

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
        setNewTask(defaultNewTask(addDays, format));
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
      } else {
        const errBody = await res.json().catch(() => ({}));
        showError(toast, new Error(errBody.detail || 'Failed to complete task'), { operation: 'complete', page: 'TrustCalendar' });
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
      } else {
        const errBody = await res.json().catch(() => ({}));
        showError(toast, new Error(errBody.detail || 'Failed to update task'), { operation: 'update', page: 'TrustCalendar' });
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
      } else {
        const errBody = await res.json().catch(() => ({}));
        showError(toast, new Error(errBody.detail || 'Failed to delete task'), { operation: 'delete', page: 'TrustCalendar' });
      }
    } catch (e) {
      showError(toast, e, { operation: 'delete', page: 'TrustCalendar' });
    }
  };

  const handleToggleChecklist = async (taskId, itemIndex) => {
    const task = events.find((e) => e.id === taskId);
    if (!task || !task.checklist) return;
    const completed = !task.checklist[itemIndex]?.completed;
    try {
      const res = await fetchWithAuth(`/tasks/${taskId}/checklist/${itemIndex}`, {
        method: 'PATCH',
        body: JSON.stringify({ completed }),
      });
      if (res.ok) {
        loadEvents();
      } else {
        const errBody = await res.json().catch(() => ({}));
        showError(toast, new Error(errBody.detail || 'Failed to update checklist'), { operation: 'update', page: 'TrustCalendar' });
      }
    } catch (e) {
      showError(toast, e, { operation: 'update', page: 'TrustCalendar' });
    }
  };

  // ── Next Up confirm handler dispatches to markFiled/markExtended ──
  const handleNextUpConfirm = (entryId) => {
    if (nextUpConfirm?.action === 'filed') markFiled(entryId);
    else markExtended(entryId);
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

  // Named predicates for the tax-info bar / generate-button visibility.
  const showTaxInfoBar = (typeFilter === 'all' || typeFilter === 'tax_deadline') && !['money', 'structure'].includes(typeFilter);
  const showGenerateBtn = (typeFilter === 'all' || typeFilter === 'tax_deadline') && !hasTaxCalendar && !['money', 'structure'].includes(typeFilter);
  const hasTaxInFilter = filteredEvents.some((e) => e.event_type === 'tax_deadline');

  return (
    <div className="main-layout" data-testid="trust-calendar-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* ── Page Header ──────────────────────────────────── */}
          <CalendarPageHeader
            year={year}
            onYearChange={setYear}
            onCreateTask={() => setShowModal(true)}
            trustProfile={trustProfile}
          />

          {/* ── "Next Up" Widget ─────────────────────────────── */}
          {!loading && (
            <NextUpWidget
              nextUp={nextUp}
              onCompleteTask={handleCompleteTask}
              onMarkFiledConfirm={setNextUpConfirm}
            />
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
          {!loading && !isEmpty && <SummaryRow summary={summary} />}

          {/* ── Status + Type Filter Controls ───────────────── */}
          {!loading && !isEmpty && (
            <CalendarFilterControls
              statusFilter={statusFilter}
              onStatusChange={setStatusFilter}
              typeFilter={typeFilter}
              onTypeChange={setTypeFilter}
              tabCounts={tabCounts}
            />
          )}

          {/* ── Trust Profile Info Bar ──────────────────────── */}
          {!loading && showTaxInfoBar && (
            <TrustProfileBar trustProfile={trustProfile} hasTaxInFilter={hasTaxInFilter} />
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
              {[1, 2, 3].map((i) => (
                <div key={i} className="card-trust">
                  <div className="skeleton h-6 w-48 mb-2"></div>
                  <div className="skeleton h-4 w-32"></div>
                </div>
              ))}
            </div>
          ) : isEmpty ? (
            <CalendarEmptyState
              mode="complete"
              year={year}
              onCreateTask={() => setShowModal(true)}
              onGenerateTaxCalendar={generateTaxCalendar}
            />
          ) : isFilteredEmpty ? (
            <CalendarEmptyState
              mode="filtered"
              year={year}
              statusFilter={statusFilter}
              typeFilter={typeFilter}
              onGenerateTaxCalendar={generateTaxCalendar}
            />
          ) : (
            <EventList
              grouped={grouped}
              onComplete={handleCompleteTask}
              onUncomplete={handleUncompleteTask}
              onDelete={handleDeleteTask}
              onToggleChecklist={handleToggleChecklist}
              onMarkFiled={markFiled}
              onMarkExtended={markExtended}
            />
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* ── Create Task Modal ──────────────────────────────── */}
      {showModal && (
        <CreateTaskModal
          newTask={newTask}
          setNewTask={setNewTask}
          onClose={() => setShowModal(false)}
          onCreate={handleCreateTask}
        />
      )}

      {/* ── Next Up Confirm Dialog ─────────────────────────── */}
      <NextUpConfirmDialog
        confirm={nextUpConfirm}
        onClose={() => setNextUpConfirm(null)}
        onConfirm={handleNextUpConfirm}
      />
    </div>
  );
}