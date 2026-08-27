import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import PageHelpButton from '@/components/PageHelpButton';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { parseISO, differenceInDays } from 'date-fns';
import { safeFormatDate } from '@/utils/safeDate';
import {
  CalendarClock,
  Plus,
  RefreshCw,
  CheckCircle2,
  Clock,
  Sparkles,
} from 'lucide-react';

const CATEGORIES = [
  { value: 'tax', label: 'Tax' },
  { value: 'compliance', label: 'Compliance' },
  { value: 'meeting', label: 'Meeting' },
  { value: 'filing', label: 'Filing' },
  { value: 'review', label: 'Review' },
  { value: 'other', label: 'Other' },
];

const PRIORITIES = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

const priorityDot = (p) => {
  switch ((p || '').toLowerCase()) {
    case 'critical':
      return 'bg-error';
    case 'high':
      return 'bg-orange-500';
    case 'medium':
      return 'bg-warning';
    default:
      return 'bg-muted-foreground/40';
  }
};

const statusBadge = (status) => {
  switch ((status || '').toLowerCase()) {
    case 'overdue':
      return 'bg-error/10 text-error border-error/20';
    case 'due_soon':
      return 'bg-warning/10 text-warning border-warning/20';
    case 'completed':
      return 'bg-success/10 text-success border-success/20';
    case 'waived':
      return 'bg-muted text-muted-foreground border-border';
    default:
      return 'bg-navy/5 text-navy border-navy/10';
  }
};

export default function DeadlineDashboard() {
  const { selectedTrust } = useAuth();
  const [deadlines, setDeadlines] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [autoGenLoading, setAutoGenLoading] = useState(false);

  // Filters
  const [filterCategory, setFilterCategory] = useState('all');
  const [filterPriority, setFilterPriority] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');

  // Form
  const [form, setForm] = useState({
    title: '',
    category: 'compliance',
    due_date: '',
    priority: 'medium',
  });

  const loadDeadlines = useCallback(async () => {
    if (!selectedTrust) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [listRes, sumRes] = await Promise.all([
        fetchWithAuth(`/deadlines/${selectedTrust.trust_id}`),
        fetchWithAuth(`/deadlines/${selectedTrust.trust_id}/summary`),
      ]);
      if (listRes.ok) {
        const data = await listRes.json();
        setDeadlines(data.deadlines || data || []);
      }
      if (sumRes.ok) {
        setSummary(await sumRes.json());
      }
    } catch (error) {
      showError(toast, error, { operation: 'load_deadlines', page: 'DeadlineDashboard', silent: true });
    } finally {
      setLoading(false);
    }
  }, [selectedTrust]);

  useEffect(() => {
    loadDeadlines();
  }, [loadDeadlines]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.title || !form.due_date) {
      toast.error('Title and due date are required');
      return;
    }
    setSaving(true);
    try {
      const res = await fetchWithAuth('/deadlines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          title: form.title,
          category: form.category,
          due_date: form.due_date,
          priority: form.priority,
        }),
      });
      if (!res.ok) throw new Error('Failed to create deadline');
      toast.success('Deadline created');
      setAddOpen(false);
      setForm({ title: '', category: 'compliance', due_date: '', priority: 'medium' });
      loadDeadlines();
    } catch (error) {
      showError(toast, error, { operation: 'create_deadline', page: 'DeadlineDashboard', silent: true });
    } finally {
      setSaving(false);
    }
  };

  const handleAction = async (deadlineId, action, body) => {
    try {
      const res = await fetchWithAuth(`/deadlines/${deadlineId}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) throw new Error(`Failed to ${action} deadline`);
      toast.success(
        action === 'complete'
          ? 'Deadline marked complete'
          : action === 'snooze'
          ? `Snoozed ${body?.days || 7} days`
          : 'Deadline waived'
      );
      loadDeadlines();
    } catch (error) {
      showError(toast, error, { operation: 'deadline_action', page: 'DeadlineDashboard', silent: true });
    }
  };

  const handleAutoGenerate = async () => {
    setAutoGenLoading(true);
    try {
      const res = await fetchWithAuth(`/deadlines/${selectedTrust.trust_id}/auto-generate`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to auto-generate deadlines');
      const data = await res.json();
      toast.success(`Generated ${data.created_count ?? data.created ?? 0} deadlines`);
      loadDeadlines();
    } catch (error) {
      showError(toast, error, { operation: 'auto_generate_deadlines', page: 'DeadlineDashboard', silent: true });
    } finally {
      setAutoGenLoading(false);
    }
  };

  const daysUntil = (dueDate) => {
    try {
      return differenceInDays(parseISO(dueDate), new Date());
    } catch {
      return null;
    }
  };

  const countdownClass = (d) => {
    if (d === null) return 'text-muted-foreground';
    if (d < 0) return 'text-error font-semibold';
    if (d < 7) return 'text-orange-600 font-medium';
    if (d < 30) return 'text-warning';
    return 'text-muted-foreground';
  };

  const countdownLabel = (d) => {
    if (d === null) return '';
    if (d < 0) return `${Math.abs(d)}d overdue`;
    if (d === 0) return 'Due today';
    return `${d}d remaining`;
  };

  const filtered = useMemo(() => {
    let list = [...deadlines];
    if (filterCategory !== 'all') list = list.filter((d) => (d.category || 'other') === filterCategory);
    if (filterPriority !== 'all') list = list.filter((d) => (d.priority || 'medium') === filterPriority);
    if (filterStatus !== 'all') list = list.filter((d) => (d.status || 'upcoming') === filterStatus);
    list.sort((a, b) => {
      const da = a.due_date || '';
      const db = b.due_date || '';
      return da < db ? -1 : da > db ? 1 : 0;
    });
    return list;
  }, [deadlines, filterCategory, filterPriority, filterStatus]);

  const summaryCards = [
    { key: 'total', label: 'Total', value: summary?.total ?? deadlines.length, cls: 'text-navy' },
    { key: 'upcoming', label: 'Upcoming', value: summary?.upcoming ?? 0, cls: 'text-navy' },
    { key: 'due_soon', label: 'Due Soon', value: summary?.due_soon ?? 0, cls: 'text-warning' },
    { key: 'overdue', label: 'Overdue', value: summary?.overdue ?? 0, cls: 'text-error' },
    { key: 'completed', label: 'Completed', value: summary?.completed ?? 0, cls: 'text-success' },
  ];

  return (
    <div className="main-layout" data-testid="deadline-dashboard-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Deadlines</h1>
              <p className="page-subtitle">
                Track compliance, tax, and filing deadlines for {selectedTrust?.trust_name || 'your trust'}
              </p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'View upcoming, due soon, and overdue deadlines' },
                  { text: 'Complete, snooze, or waive deadlines as circumstances change' },
                  { text: 'Auto-generate standard deadlines from trust type and state rules' },
                ]}
                taPrompt="Walk me through the Deadlines page and what each deadline means"
              />
              <Button
                onClick={loadDeadlines}
                variant="outline"
                className="btn-secondary"
                data-testid="refresh-deadlines-btn"
              >
                <RefreshCw className="w-4 h-4 mr-2" />
                Refresh
              </Button>
              <Button
                onClick={handleAutoGenerate}
                variant="outline"
                className="btn-secondary"
                disabled={autoGenLoading || !selectedTrust}
                data-testid="auto-generate-btn"
              >
                <Sparkles className="w-4 h-4 mr-2" />
                {autoGenLoading ? 'Generating…' : 'Auto-Generate'}
              </Button>
              <Button
                onClick={() => setAddOpen(true)}
                className="btn-primary"
                disabled={!selectedTrust}
                data-testid="add-deadline-btn"
              >
                <Plus className="w-4 h-4 mr-2" />
                Add Deadline
              </Button>
            </div>
          </div>

          {!selectedTrust ? (
            <div className="card-trust p-8 text-center text-muted-foreground">
              <CalendarClock className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>Select a trust to view its deadlines.</p>
            </div>
          ) : loading ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="card-trust"><div className="skeleton h-16 w-full"></div></div>
                ))}
              </div>
              <div className="card-trust"><div className="skeleton h-64 w-full"></div></div>
            </div>
          ) : (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                {summaryCards.map((c) => (
                  <div key={c.key} className="card-trust text-center py-4" data-testid={`summary-${c.key}`}>
                    <p className={`font-mono text-2xl font-semibold ${c.cls}`}>{c.value}</p>
                    <p className="text-xs uppercase tracking-wider text-muted-foreground mt-1">{c.label}</p>
                  </div>
                ))}
              </div>

              {/* Filter bar */}
              <div className="flex flex-wrap items-center gap-3 mb-4">
                <Select value={filterCategory} onValueChange={setFilterCategory}>
                  <SelectTrigger className="w-40" data-testid="filter-category">
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All categories</SelectItem>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={filterPriority} onValueChange={setFilterPriority}>
                  <SelectTrigger className="w-36" data-testid="filter-priority">
                    <SelectValue placeholder="Priority" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All priorities</SelectItem>
                    {PRIORITIES.map((p) => (
                      <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={filterStatus} onValueChange={setFilterStatus}>
                  <SelectTrigger className="w-36" data-testid="filter-status">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    <SelectItem value="upcoming">Upcoming</SelectItem>
                    <SelectItem value="due_soon">Due Soon</SelectItem>
                    <SelectItem value="overdue">Overdue</SelectItem>
                    <SelectItem value="completed">Completed</SelectItem>
                    <SelectItem value="waived">Waived</SelectItem>
                  </SelectContent>
                </Select>
                <span className="text-xs text-muted-foreground ml-auto font-mono">
                  {filtered.length} of {deadlines.length}
                </span>
              </div>

              {/* Timeline list */}
              {filtered.length === 0 ? (
                <div className="card-trust p-8 text-center text-muted-foreground">
                  <CheckCircle2 className="w-10 h-10 mx-auto mb-3 text-success" />
                  <p>No deadlines match your filters.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {filtered.map((d, i) => {
                    const du = daysUntil(d.due_date);
                    const isActionable =
                      (d.status || 'upcoming') !== 'completed' && (d.status || '') !== 'waived';
                    return (
                      <div
                        key={d.id || d.deadline_id || i}
                        className="card-trust flex flex-col md:flex-row md:items-center gap-4 p-4"
                        data-testid={`deadline-row-${i}`}
                      >
                        <div className="flex items-start gap-3 flex-1 min-w-0">
                          <span className={`mt-1.5 w-2.5 h-2.5 rounded-full flex-shrink-0 ${priorityDot(d.priority)}`} />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h4 className="font-medium text-navy truncate">{d.title}</h4>
                              <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
                                {d.category || 'other'}
                              </Badge>
                              <span
                                className={`inline-block px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider border ${statusBadge(
                                  d.status
                                )}`}
                              >
                                {(d.status || 'upcoming').replace('_', ' ')}
                              </span>
                            </div>
                            {d.description && (
                              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{d.description}</p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-4 flex-shrink-0">
                          <div className="text-right">
                            <p className="font-mono text-sm text-navy">
                              {safeFormatDate(d.due_date, 'MMM d, yyyy', '—')}
                            </p>
                            <p className={`text-xs font-mono ${countdownClass(du)}`}>{countdownLabel(du)}</p>
                          </div>
                          {isActionable && (
                            <div className="flex items-center gap-1">
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-8 text-xs"
                                onClick={() => handleAction(d.id || d.deadline_id, 'complete')}
                                data-testid={`complete-${i}`}
                              >
                                <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                                Complete
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-8 text-xs"
                                onClick={() => handleAction(d.id || d.deadline_id, 'snooze', { days: 7 })}
                                data-testid={`snooze-${i}`}
                              >
                                <Clock className="w-3.5 h-3.5 mr-1" />
                                Snooze 7d
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-8 text-xs text-muted-foreground"
                                onClick={() => handleAction(d.id || d.deadline_id, 'waive')}
                                data-testid={`waive-${i}`}
                              >
                                Waive
                              </Button>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* Add Deadline Dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Deadline</DialogTitle>
            <DialogDescription>
              Create a custom deadline for {selectedTrust?.trust_name || 'this trust'}.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="dl-title">Title</Label>
              <Input
                id="dl-title"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="e.g. File Form 1041"
                required
                data-testid="deadline-title-input"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Category</Label>
                <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                  <SelectTrigger data-testid="deadline-category-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Priority</Label>
                <Select value={form.priority} onValueChange={(v) => setForm({ ...form, priority: v })}>
                  <SelectTrigger data-testid="deadline-priority-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PRIORITIES.map((p) => (
                      <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="dl-date">Due Date</Label>
              <Input
                id="dl-date"
                type="date"
                value={form.due_date}
                onChange={(e) => setForm({ ...form, due_date: e.target.value })}
                required
                data-testid="deadline-date-input"
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setAddOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" className="btn-primary" disabled={saving} data-testid="deadline-submit-btn">
                {saving ? 'Saving…' : 'Create Deadline'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
