import { useMemo } from 'react';
import { format, parseISO } from 'date-fns';

// Centralizes all derived calendar data: year filtering, summary counts,
// status-tab counts (within the type filter), the "Next Up" widget, the
// status+type filtered list, and month grouping for the sticky-header list.
//
// Inputs:
//   events       – raw calendar event array
//   year         – selected calendar year
//   statusFilter – 'upcoming' | 'overdue' | 'completed' | 'all'
//   typeFilter   – 'all' | 'governance_task' | 'tax_deadline' | 'money' | 'structure'
//
// Returns { yearEvents, taxEntriesForYear, hasTaxCalendar, summary, tabCounts,
//           nextUp, filteredEvents, grouped, isEmpty, isFilteredEmpty }
export function useCalendarData(events, year, statusFilter, typeFilter) {
  // ── Year filtering: filter ALL events by due_date calendar year ──
  const yearEvents = useMemo(() => {
    return events.filter((e) => {
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
    () => yearEvents.filter((e) => e.event_type === 'tax_deadline'),
    [yearEvents]
  );

  const hasTaxCalendar = taxEntriesForYear.length > 0;

  // ── Summary counts (from yearEvents, before status/type filter) ──
  const summary = useMemo(() => {
    const total = yearEvents.length;
    const completed = yearEvents.filter((e) => e.status === 'completed').length;
    const overdue = yearEvents.filter((e) => e.status === 'overdue').length;
    const pending = total - completed - overdue;
    return { total, completed, pending, overdue };
  }, [yearEvents]);

  // Apply only the type filter (for tab counts and shared reuse).
  const typeFilteredEvents = useMemo(() => {
    if (typeFilter === 'all') return yearEvents;
    if (typeFilter === 'money') return yearEvents.filter((e) => e.category === 'money');
    if (typeFilter === 'structure') return yearEvents.filter((e) => e.category === 'structure');
    return yearEvents.filter((e) => e.event_type === typeFilter);
  }, [yearEvents, typeFilter]);

  // ── Status tab counts (within current type filter) ──
  const tabCounts = useMemo(
    () => ({
      upcoming: typeFilteredEvents.filter((e) => e.status === 'upcoming').length,
      overdue: typeFilteredEvents.filter((e) => e.status === 'overdue').length,
      completed: typeFilteredEvents.filter((e) => e.status === 'completed').length,
      all: typeFilteredEvents.length,
    }),
    [typeFilteredEvents]
  );

  // ── "Next Up" widget: most urgent pending item ──────────────
  const nextUp = useMemo(() => {
    const pending = yearEvents.filter((e) => e.status !== 'completed' && e.date);
    if (pending.length === 0) return null;
    pending.sort((a, b) => a.date.localeCompare(b.date));
    return pending[0];
  }, [yearEvents]);

  // ── Filtered events (status + type) ─────────────────────────
  const filteredEvents = useMemo(() => {
    let result = typeFilteredEvents;
    if (statusFilter !== 'all') {
      result = result.filter((e) => e.status === statusFilter);
    }
    return result;
  }, [typeFilteredEvents, statusFilter]);

  // ── Month grouping for the sticky-header list ──────────────
  const grouped = useMemo(() => {
    const byMonth = {};
    filteredEvents.forEach((e) => {
      if (!e.date) return;
      try {
        const mo = format(parseISO(e.date), 'MMMM yyyy');
        if (!byMonth[mo]) byMonth[mo] = [];
        byMonth[mo].push(e);
      } catch {
        /* skip bad dates */
      }
    });
    return byMonth;
  }, [filteredEvents]);

  // Empty state logic
  const isEmpty = yearEvents.length === 0;
  const isFilteredEmpty = !isEmpty && filteredEvents.length === 0;

  return {
    yearEvents,
    taxEntriesForYear,
    hasTaxCalendar,
    summary,
    tabCounts,
    nextUp,
    filteredEvents,
    grouped,
    isEmpty,
    isFilteredEmpty,
  };
}