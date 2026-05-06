import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import {
  CalendarDays, Clock, CheckCircle2, Circle, AlertTriangle,
  FileText, ExternalLink, ChevronDown, Check
} from 'lucide-react';
import { format, parseISO, differenceInDays } from 'date-fns';
import { toast } from 'sonner';

const DEADLINE_LABELS = {
  federal_1041: 'Form 1041 — Income Tax Return',
  federal_1041_extension: 'Form 1041 — Extended Deadline',
  k1_beneficiaries: 'Schedule K-1 — Beneficiary Allocations',
  estimated_q1: 'Q1 Estimated Tax Payment',
  estimated_q2: 'Q2 Estimated Tax Payment',
  estimated_q3: 'Q3 Estimated Tax Payment',
  estimated_q4: 'Q4 Estimated Tax Payment',
};

function statusBadge(status, overdue) {
  if (status === 'filed' || status === 'not_required') {
    return <Badge variant="success" className="bg-emerald-100 text-emerald-700 hover:bg-emerald-200">Filed</Badge>;
  }
  if (status === 'extended') {
    return <Badge variant="outline" className="border-amber-500 text-amber-700">Extended</Badge>;
  }
  if (overdue) {
    return <Badge variant="destructive" className="bg-red-100 text-red-700 hover:bg-red-200">Overdue</Badge>;
  }
  return <Badge variant="outline" className="border-slate-300 text-slate-600">Pending</Badge>;
}

export default function TaxCalendarPage() {
  const { selectedTrust } = useAuth();
  const [entries, setEntries] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [year, setYear] = useState(new Date().getFullYear());
  const [showGenerate, setShowGenerate] = useState(false);
  const [trustProfile, setTrustProfile] = useState({});

  useEffect(() => {
    if (selectedTrust) {
      loadCalendar();
      setTrustProfile({
        ein: selectedTrust?.ein || '',
        stateCode: selectedTrust?.state_code || '',
        taxYearEndMonth: selectedTrust?.tax_year_end_month || 12,
        taxYearEndDay: selectedTrust?.tax_year_end_day || 31,
        isFiscalYear: selectedTrust?.is_fiscal_year || false,
      });
    }
  }, [selectedTrust, year]);

  const loadCalendar = async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/api/trusts/${selectedTrust.trust_id}/tax-calendar?tax_year=${year}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load tax calendar');
      setEntries(data.entries || []);
      setSummary({
        total_entries: data.total_entries,
        filed_count: data.filed_count,
        pending_count: data.pending_count,
        overdue_count: data.overdue_count,
      });
    } catch (e) {
      toast.error(e.message);
      setEntries([]);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  };

  const generateCalendar = async () => {
    try {
      const res = await fetchWithAuth(`/api/trusts/${selectedTrust.trust_id}/tax-calendar/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tax_year: year }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 409) {
          toast.info(data.detail);
          return;
        }
        throw new Error(data.detail || 'Failed to generate');
      }
      toast.success(`Generated ${data.entries_created} tax deadlines for ${year}`);
      loadCalendar();
      setShowGenerate(false);
    } catch (e) {
      toast.error(e.message);
    }
  };

  const markFiled = async (entryId) => {
    try {
      const res = await fetchWithAuth(`/api/tax-calendar/${entryId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filing_status: 'filed' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update');
      toast.success('Marked as filed');
      loadCalendar();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const grouped = useMemo(() => {
    const byMonth = {};
    entries.forEach(e => {
      const mo = format(parseISO(e.due_date), 'MMMM yyyy');
      if (!byMonth[mo]) byMonth[mo] = [];
      byMonth[mo].push(e);
    });
    return byMonth;
  }, [entries]);

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <div className="md:pl-64 pb-20 md:pb-0">
          <div className="pt-16 md:pt-8 ml-4 mr-4">
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded-lg">
              <CalendarDays className="w-12 h-12 text-slate-400 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-neutral-600">Choose a trust from the sidebar to view its tax calendar.</p>
            </div>
          </div>
        </div>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-subtle-bg">
      <Sidebar />
      <div className="md:pl-64 pb-20 md:pb-0">
        <div className="pt-16 md:pt-8 ml-4 mr-4">
          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6 gap-4">
            <div>
              <h1 className="text-2xl font-bold text-navy flex items-center gap-2">
                <CalendarDays className="w-6 h-6 text-navy"/>
                Tax Calendar
              </h1>
              <p className="text-sm text-neutral-600 mt-1">
                Federal deadlines for <span className="font-semibold">{selectedTrust.name}</span>
              </p>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={year}
                onChange={e => setYear(Number(e.target.value))}
                className="border border-neutral-300 rounded-md px-3 py-2 text-sm bg-white"
              >
                {[year - 1, year, year + 1].map(y => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
              {summary?.total_entries === 0 ? (
                <Button onClick={generateCalendar} disabled={loading}>
                  <CalendarDays className="w-4 h-4 mr-2"/>
                  Generate {year} Calendar
                </Button>
              ) : null}
            </div>
          </div>

          {/* Summary Cards */}
          {summary && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
              <Card><CardContent className="p-4">
                <div className="text-2xl font-bold text-navy">{summary.total_entries}</div>
                <div className="text-xs text-neutral-600">Total Deadlines</div>
              </CardContent></Card>
              <Card><CardContent className="p-4">
                <div className="text-2xl font-bold text-emerald-600">{summary.filed_count}</div>
                <div className="text-xs text-neutral-600">Filed / N/A</div>
              </CardContent></Card>
              <Card><CardContent className="p-4">
                <div className="text-2xl font-bold text-slate-600">{summary.pending_count}</div>
                <div className="text-xs text-neutral-600">Pending</div>
              </CardContent></Card>
              <Card><CardContent className="p-4">
                <div className="text-2xl font-bold text-red-600">{summary.overdue_count}</div>
                <div className="text-xs text-neutral-600">Overdue</div>
              </CardContent></Card>
            </div>
          )}

          {/* Trust Profile Hint */}
          <Card className="mb-6 border border-neutral-200">
            <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="text-sm text-neutral-600">
                {trustProfile.ein
                  ? <>EIN: <b>{trustProfile.ein}</b> · Tax year ends: <b>{trustProfile.taxYearEndMonth}/{trustProfile.taxYearEndDay}</b></>
                  : <>Set your trust EIN and tax year end in <b>Settings → Trust Profile</b> for accurate deadlines.</>
                }
              </div>
            </CardContent>
          </Card>

          {/* Entries */}
          {loading ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-20 bg-white border border-neutral-200 rounded-lg animate-pulse"/>)}
            </div>
          ) : entries.length === 0 ? (
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded-lg">
              <CalendarDays className="w-12 h-12 text-slate-300 mb-3"/>
              <h2 className="text-lg font-semibold text-navy mb-1">No tax calendar yet</h2>
              <p className="text-sm text-neutral-600 mb-4 max-w-md text-center">
                Generate the {year} federal tax deadlines for this trust. Once created, you can track filing status, set reminders, and mark items complete.
              </p>
              <Button onClick={generateCalendar}>
                <CalendarDays className="w-4 h-4 mr-2"/>
                Generate {year} Tax Calendar
              </Button>
            </div>
          ) : (
            <div className="space-y-6">
              {Object.entries(grouped).map(([month, items]) => (
                <div key={month}>
                  <h3 className="text-sm font-semibold text-neutral-500 uppercase tracking-wide mb-2">{month}</h3>
                  <div className="space-y-2">
                    {items.map(entry => {
                      const overdue = entry.is_overdue && entry.filing_status === 'pending';
                      const due = parseISO(entry.due_date);
                      return (
                        <div key={entry.entry_id} className={`flex items-start gap-3 bg-white border ${overdue ? 'border-red-200' : 'border-neutral-200'} rounded-lg p-4`}>
                          <div className="flex flex-col items-center min-w-[56px]">
                            <div className="text-xs font-medium text-neutral-500 uppercase">{format(due, 'MMM')}</div>
                            <div className={`text-xl font-bold ${overdue ? 'text-red-600' : 'text-navy'}`}>{format(due, 'd')}</div>
                          </div>
                          <div className="flex-1">
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <div className="font-semibold text-navy text-sm">
                                  {DEADLINE_LABELS[entry.deadline_type] || entry.deadline_type}
                                </div>
                                {entry.description && (
                                  <div className="text-xs text-neutral-600 mt-0.5">{entry.description}</div>
                                )}
                                {entry.notes && (
                                  <div className="text-xs text-neutral-500 mt-1 italic">Note: {entry.notes}</div>
                                )}
                              </div>
                              <div>{statusBadge(entry.filing_status, overdue)}</div>
                            </div>
                            {overdue ? (
                              <div className="text-xs text-red-600 mt-2 flex items-center gap-1">
                                <AlertTriangle className="w-3.5 h-3.5"/>
                                Due {Math.abs(entry.days_remaining)} days ago
                              </div>
                            ) : entry.days_remaining !== null && entry.days_remaining <= 30 && entry.filing_status === 'pending' ? (
                              <div className="text-xs text-amber-600 mt-2 flex items-center gap-1">
                                <Clock className="w-3.5 h-3.5"/>
                                Due in {entry.days_remaining} days
                              </div>
                            ) : null}
                          </div>
                          {entry.filing_status === 'pending' && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => markFiled(entry.entry_id)}
                              className="shrink-0 border-emerald-500 text-emerald-700 hover:bg-emerald-50"
                            >
                              <Check className="w-3.5 h-3.5 mr-1"/>
                              Mark Filed
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}
