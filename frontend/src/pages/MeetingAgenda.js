import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import InfoTooltip from '@/components/InfoTooltip';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  CalendarDays, ArrowUp, ArrowDown, Pencil, Trash2, Plus,
  CheckCircle2, Play, ArrowLeft, GripVertical, FileText, Save, X,
} from 'lucide-react';

const TYPE_STYLES = {
  approval: 'bg-blue-100 text-blue-700 border-blue-200',
  review: 'bg-warning/10 text-warning border-warning/20',
  resolution: 'bg-navy/10 text-navy border-navy/20',
  discussion: 'bg-slate-100 text-slate-600 border-slate-200',
  ratification: 'bg-success/10 text-success border-success/20',
  notice: 'bg-purple-100 text-purple-700 border-purple-200',
};

const TYPE_LABELS = {
  approval: 'Approval',
  review: 'Review',
  resolution: 'Resolution',
  discussion: 'Discussion',
  ratification: 'Ratification',
  notice: 'Notice',
};

function AgendaItemRow({ item, index, total, readOnly, onMove, onEdit, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(item.title || '');
  const [draftNotes, setDraftNotes] = useState(item.notes || '');

  const save = () => {
    onEdit(index, { ...item, title: draftTitle.trim() || item.title, notes: draftNotes });
    setEditing(false);
  };

  const typeKey = (item.item_type || 'discussion').toLowerCase();

  return (
    <div className="card-trust border border-border rounded-xl p-4">
      <div className="flex items-start gap-3">
        {!readOnly && (
          <div className="flex flex-col items-center gap-0.5 pt-1 shrink-0">
            <button
              type="button"
              disabled={index === 0}
              onClick={() => onMove(index, -1)}
              className="text-muted-foreground hover:text-navy disabled:opacity-30"
              aria-label="Move up"
            >
              <ArrowUp className="w-3.5 h-3.5" />
            </button>
            <GripVertical className="w-3.5 h-3.5 text-muted-foreground/40" />
            <button
              type="button"
              disabled={index === total - 1}
              onClick={() => onMove(index, 1)}
              className="text-muted-foreground hover:text-navy disabled:opacity-30"
              aria-label="Move down"
            >
              <ArrowDown className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-xs font-mono text-muted-foreground">{index + 1}.</span>
            <Badge variant="outline" className={TYPE_STYLES[typeKey] || TYPE_STYLES.discussion}>
              {TYPE_LABELS[typeKey] || item.item_type || 'Discussion'}
            </Badge>
            {item.required && (
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Required</span>
            )}
          </div>

          {editing ? (
            <div className="space-y-2 mt-2">
              <input
                className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background text-navy focus:outline-none focus:ring-1 focus:ring-navy"
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                placeholder="Agenda item title"
              />
              <textarea
                className="w-full text-sm border border-border rounded-md px-3 py-2 bg-background text-navy focus:outline-none focus:ring-1 focus:ring-navy min-h-[72px]"
                value={draftNotes}
                onChange={(e) => setDraftNotes(e.target.value)}
                placeholder="Notes / context for this item"
              />
              <div className="flex gap-2">
                <Button size="sm" onClick={save}>
                  <Save className="w-3.5 h-3.5 mr-1" /> Save
                </Button>
                <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
                  <X className="w-3.5 h-3.5 mr-1" /> Cancel
                </Button>
              </div>
            </div>
          ) : (
            <>
              <p className="text-sm font-medium text-navy">{item.title}</p>
              {item.notes && (
                <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">{item.notes}</p>
              )}
            </>
          )}
        </div>

        {!readOnly && !editing && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={() => { setDraftTitle(item.title || ''); setDraftNotes(item.notes || ''); setEditing(true); }}
              className="p-1.5 text-muted-foreground hover:text-navy"
              aria-label="Edit item"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => onDelete(index)}
              className="p-1.5 text-muted-foreground hover:text-destructive"
              aria-label="Delete item"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function MeetingAgenda() {
  const { agendaId } = useParams();
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [agenda, setAgenda] = useState(null);
  const [items, setItems] = useState([]);
  const [dirty, setDirty] = useState(false);

  const loadAgenda = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/meetings/agendas/${agendaId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load agenda');
      setAgenda(data);
      setItems(data.items || []);
      setDirty(false);
    } catch (e) {
      showError(toast, e, { operation: 'load_agenda', page: 'MeetingAgenda' });
    } finally {
      setLoading(false);
    }
  }, [agendaId]);

  useEffect(() => {
    if (agendaId) loadAgenda();
  }, [agendaId, loadAgenda]);

  const readOnly = agenda?.status === 'completed' || agenda?.status === 'in_progress';

  const moveItem = (index, dir) => {
    const next = [...items];
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setItems(next);
    setDirty(true);
  };

  const editItem = (index, updated) => {
    const next = [...items];
    next[index] = updated;
    setItems(next);
    setDirty(true);
  };

  const deleteItem = (index) => {
    setItems(items.filter((_, i) => i !== index));
    setDirty(true);
  };

  const addItem = () => {
    setItems([...items, { title: 'New agenda item', item_type: 'discussion', notes: '' }]);
    setDirty(true);
  };

  const saveAgenda = async () => {
    setSaving(true);
    try {
      const res = await fetchWithAuth(`/meetings/agendas/${agendaId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to save agenda');
      toast.success('Agenda saved');
      setDirty(false);
      if (data.items) setItems(data.items);
    } catch (e) {
      showError(toast, e, { operation: 'save_agenda', page: 'MeetingAgenda' });
    } finally {
      setSaving(false);
    }
  };

  const finalizeAndStart = async () => {
    setSaving(true);
    try {
      if (dirty) {
        const res = await fetchWithAuth(`/meetings/agendas/${agendaId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to save agenda');
      }
      const finRes = await fetchWithAuth(`/meetings/agendas/${agendaId}/finalize`, {
        method: 'POST',
      });
      const finData = await finRes.json();
      if (!finRes.ok) throw new Error(finData.detail || 'Failed to finalize agenda');
      toast.success('Agenda finalized — meeting started');
      const trustId = selectedTrust?.trust_id || agenda?.trust_id;
      if (finData.minutes_id) {
        navigate(`/governance/minutes/${finData.minutes_id}`);
      } else if (trustId) {
        navigate(`/governance/approvals/${trustId}`);
      } else {
        loadAgenda();
      }
    } catch (e) {
      showError(toast, e, { operation: 'finalize_agenda', page: 'MeetingAgenda' });
    } finally {
      setSaving(false);
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content mobile-layout-offset">
          <div className="page-container">
            <div className="card-trust border border-border p-12 flex flex-col items-center justify-center rounded">
              <CalendarDays className="w-12 h-12 text-muted-foreground/60 mb-3" />
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to view meeting agendas.</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  const meetingDate = agenda?.meeting_date
    ? new Date(agenda.meeting_date).toLocaleDateString(undefined, {
        weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
      })
    : null;

  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content mobile-layout-offset">
        <div className="page-container">

          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <Link
                to={`/governance/history/${selectedTrust.trust_id}`}
                className="inline-flex items-center text-xs text-muted-foreground hover:text-navy mb-1"
              >
                <ArrowLeft className="w-3 h-3 mr-1" /> Meeting history
              </Link>
              <h1 className="page-title">{agenda?.title || 'Meeting Agenda'}</h1>
              <p className="page-subtitle">
                {meetingDate ? `${meetingDate} · ` : ''}Review, reorder, and finalize agenda items before the meeting
              </p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'Review the generated agenda items for this trustee meeting' },
                  { text: 'Reorder, edit, or remove items so the agenda reflects what you need to cover' },
                  { text: 'Finalize the agenda to start the meeting and begin drafting minutes' },
                ]}
                taPrompt="Walk me through preparing a meeting agenda"
              />
              {agenda?.status && (
                <Badge variant="outline" className="bg-slate-100 text-slate-600 border-slate-200 capitalize">
                  {agenda.status.replace('_', ' ')}
                </Badge>
              )}
            </div>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-20 card-trust border border-border rounded animate-pulse" />
              ))}
            </div>
          ) : !agenda ? (
            <div className="card-trust border border-border p-12 flex flex-col items-center justify-center rounded">
              <FileText className="w-12 h-12 text-muted-foreground/60 mb-3" />
              <h2 className="text-xl font-semibold text-navy mb-1">Agenda not found</h2>
              <p className="text-sm text-muted-foreground mb-4">
                This agenda may have been removed, or the link is incorrect.
              </p>
              <Link to={`/governance/history/${selectedTrust.trust_id}`}>
                <Button variant="outline">Back to meeting history</Button>
              </Link>
            </div>
          ) : (
            <>
              {/* Action bar */}
              {!readOnly && (
                <Card className="card-trust border border-border mb-4">
                  <CardContent className="p-4 flex flex-wrap items-center justify-between gap-3">
                    <div className="text-sm text-muted-foreground">
                      {items.length} item{items.length === 1 ? '' : 's'}
                      {dirty && <span className="text-warning ml-2">· Unsaved changes</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button variant="outline" size="sm" onClick={addItem}>
                        <Plus className="w-3.5 h-3.5 mr-1" /> Add item
                      </Button>
                      <Button variant="outline" size="sm" onClick={saveAgenda} disabled={!dirty || saving}>
                        <Save className="w-3.5 h-3.5 mr-1" /> {saving ? 'Saving…' : 'Save'}
                      </Button>
                      <Button size="sm" onClick={finalizeAndStart} disabled={saving || items.length === 0}>
                        <Play className="w-3.5 h-3.5 mr-1" /> Finalize & Start Meeting
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Agenda items */}
              <div className="space-y-2">
                <div className="flex items-center gap-1 text-xs uppercase tracking-wider text-muted-foreground mb-1">
                  Agenda Items
                  <InfoTooltip text="Agenda items are generated from your trust activity since the last meeting — approvals, reviews, and resolutions. Edit them to match what you plan to cover." />
                </div>
                {items.length === 0 ? (
                  <div className="card-trust border border-border rounded-xl p-8 text-center">
                    <p className="text-sm text-muted-foreground">No agenda items yet.</p>
                    {!readOnly && (
                      <Button variant="outline" size="sm" className="mt-3" onClick={addItem}>
                        <Plus className="w-3.5 h-3.5 mr-1" /> Add your first item
                      </Button>
                    )}
                  </div>
                ) : (
                  items.map((item, i) => (
                    <AgendaItemRow
                      key={item.item_id || i}
                      item={item}
                      index={i}
                      total={items.length}
                      readOnly={readOnly}
                      onMove={moveItem}
                      onEdit={editItem}
                      onDelete={deleteItem}
                    />
                  ))
                )}
              </div>

              {readOnly && agenda.minutes_id && (
                <div className="mt-4 flex justify-end">
                  <Link to={`/governance/minutes/${agenda.minutes_id}`}>
                    <Button>
                      <CheckCircle2 className="w-4 h-4 mr-2" /> Open minutes for this meeting
                    </Button>
                  </Link>
                </div>
              )}
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
