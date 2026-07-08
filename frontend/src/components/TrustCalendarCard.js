import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  CheckCircle2, Clock, AlertTriangle, DollarSign,
  ChevronDown, ChevronUp, X, Check, Shield, Bot,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const DEADLINE_LABELS = {
  federal_1041: 'Form 1041 — Income Tax Return',
  federal_1041_extension: 'Form 1041 — Extended Deadline',
  k1_beneficiaries: 'Schedule K-1 — Beneficiary Allocations',
  estimated_q1: 'Q1 Estimated Tax Payment',
  estimated_q2: 'Q2 Estimated Tax Payment',
  estimated_q3: 'Q3 Estimated Tax Payment',
  estimated_q4: 'Q4 Estimated Tax Payment',
};

function FilingStatusBadge({ filingStatus, overdue }) {
  if (filingStatus === 'filed' || filingStatus === 'not_required') {
    return <span className="inline-flex items-center px-2 py-0.5 text-xs font-semibold bg-emerald-100 text-emerald-700">Filed</span>;
  }
  if (filingStatus === 'extended') {
    return <span className="inline-flex items-center px-2 py-0.5 text-xs font-semibold border border-warning text-warning">Extended</span>;
  }
  if (overdue) {
    return <span className="inline-flex items-center px-2 py-0.5 text-xs font-semibold bg-red-100 text-red-700">Overdue</span>;
  }
  return <span className="inline-flex items-center px-2 py-0.5 text-xs font-semibold border border-slate-300 text-slate-600">Pending</span>;
}

function StatusIcon({ status, eventType }) {
  if (status === 'completed') return <CheckCircle2 className="w-5 h-5 text-emerald-600" />;
  if (status === 'overdue') return <AlertTriangle className="w-5 h-5 text-red-600" />;
  return <Clock className="w-5 h-5 text-navy" />;
}

function statusBorderClass(status) {
  if (status === 'completed') return 'border-l-emerald-600';
  if (status === 'overdue') return 'border-l-red-600';
  return 'border-l-navy';
}

function humanizeTaskType(taskType) {
  return taskType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatDate(dateString) {
  try { return format(parseISO(dateString), 'MMM d, yyyy'); } catch { return dateString; }
}

/**
 * Polymorphic calendar card.
 * Renders governance task or tax deadline variant based on event_type.
 */
export default function TrustCalendarCard({ event, onComplete, onUncomplete, onDelete, onToggleChecklist, onMarkFiled, onMarkExtended }) {
  const [expanded, setExpanded] = useState(false);
  const [showConfirm, setShowConfirm] = useState(null); // null | 'filed' | 'extended'

  const isTax = event.event_type === 'tax_deadline';
  const isGovernance = event.event_type === 'governance_task';
  const status = event.status || 'upcoming';
  const overdue = status === 'overdue';
  const due = event.date ? parseISO(event.date) : null;

  // ── Tax deadline card ──────────────────────────────────────
  if (isTax) {
    const label = DEADLINE_LABELS[event.deadline_type] || event.title || event.deadline_type;
    const filingStatus = event.filing_status || 'pending';
    const isPending = filingStatus === 'pending';

    return (
      <div
        className={`card-trust border-l-4 ${statusBorderClass(status)} relative transition-shadow hover:shadow-md`}
        data-testid={`tax-card-${event.entry_id}`}
      >
        {/* Thin gold accent border for tax cards */}
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-gold/30" />

        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div className="flex items-start gap-4 flex-1">
            <div className="flex items-center justify-center w-10 h-10 bg-gold/10 shrink-0">
              <DollarSign className="w-5 h-5 text-gold" aria-hidden="true" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h3 className="font-medium text-navy text-sm sm:text-base">{label}</h3>
                <FilingStatusBadge filingStatus={filingStatus} overdue={overdue} />
              </div>

              {event.description && (
                <p className="text-sm text-muted-foreground mt-1">{event.description}</p>
              )}

              {/* Date block */}
              {due && (
                <div className="flex items-center gap-4 mt-2">
                  <span className="font-mono text-xs text-muted-foreground">
                    Due: {format(due, 'MMM d, yyyy')}
                  </span>
                  {event.is_fiscal_year && (
                    <span className="text-xs bg-warning/10 text-warning px-1.5 py-0.5">Fiscal Year</span>
                  )}
                </div>
              )}

              {/* Days remaining countdown */}
              {typeof event.days_remaining === 'number' && filingStatus === 'pending' && (
                <div className={`text-xs mt-1.5 flex items-center gap-1 ${overdue ? 'text-red-600' : event.days_remaining <= 30 ? 'text-warning' : 'text-muted-foreground'}`}>
                  {overdue ? (
                    <><AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" /> Due {Math.abs(event.days_remaining)} days ago</>
                  ) : (
                    <><Clock className="w-3.5 h-3.5" aria-hidden="true" /> {event.days_remaining} days remaining</>
                  )}
                </div>
              )}

              {/* Notes */}
              {event.notes && (
                <p className="text-xs text-muted-foreground italic mt-1.5">Note: {event.notes}</p>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 shrink-0">
            {isPending && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowConfirm('filed')}
                  className="border-emerald-600 text-emerald-700 hover:bg-emerald-50"
                  data-testid={`mark-filed-${event.entry_id}`}
                >
                  <Check className="w-3.5 h-3.5 mr-1" aria-hidden="true" /> Mark Filed
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowConfirm('extended')}
                  className="border-warning text-warning hover:bg-warning/5"
                  data-testid={`mark-extended-${event.entry_id}`}
                >
                  Extend
                </Button>
              </>
            )}
            <Link
              to={`/trust-assistant?prompt=${encodeURIComponent(`Explain what I need to do for the ${label} deadline on ${due ? format(due, 'MMM d, yyyy') : 'the due date'} and help me prepare.`)}`}
              className="inline-flex items-center gap-1 px-2 py-1.5 text-xs text-gold hover:bg-gold/10 transition-colors"
              title="Ask Trust Assistant for help"
              data-testid={`ta-help-${event.entry_id}`}
            >
              <Bot className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Ask AI</span>
            </Link>
          </div>
        </div>

        {/* Confirm dialog */}
        {showConfirm && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowConfirm(null)}>
            <div className="bg-white p-6 w-full max-w-sm corner-mark" onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === 'Escape') setShowConfirm(null); if (e.key === 'Enter') { if (showConfirm === 'filed') onMarkFiled(event.entry_id); else onMarkExtended(event.entry_id); setShowConfirm(null); } }} role="dialog" aria-modal="true" aria-label={showConfirm === 'filed' ? 'Confirm mark as filed' : 'Confirm mark as extended'} data-testid={`confirm-${showConfirm}-${event.entry_id}`}>
              <h3 className="font-serif text-lg text-navy mb-2">
                {showConfirm === 'filed' ? 'Confirm: Mark as Filed' : 'Confirm: Mark as Extended'}
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                {showConfirm === 'filed'
                  ? `Mark "${label}" as filed for tax year ${event.tax_year}?`
                  : `Mark "${label}" as extended?`}
              </p>
              <div className="flex gap-3">
                <Button variant="outline" className="flex-1 btn-secondary" onClick={() => setShowConfirm(null)}>
                  Cancel
                </Button>
                <Button
                  className="flex-1 btn-primary"
                  onClick={() => {
                    if (showConfirm === 'filed') onMarkFiled(event.entry_id);
                    else onMarkExtended(event.entry_id);
                    setShowConfirm(null);
                  }}
                  data-testid={`confirm-${showConfirm}-btn-${event.entry_id}`}
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

  // ── Governance task card ───────────────────────────────────
  const checklist = event.checklist || [];
  const checklistCompleted = checklist.filter(ci => ci.completed).length;

  return (
    <div
      className={`card-trust border-l-4 ${statusBorderClass(status)} transition-shadow hover:shadow-md`}
      data-testid={`task-card-${event.id}`}
    >
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div className="flex items-start gap-4 flex-1">
          <div className="flex items-center justify-center w-10 h-10 bg-navy/5 shrink-0">
            <Shield className="w-5 h-5 text-navy" aria-hidden="true" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3">
              <h3 className="font-medium text-navy text-sm sm:text-base">
                {humanizeTaskType(event.task_type || event.title || '')}
              </h3>
              {checklist.length > 0 && (
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="text-xs font-mono text-muted-foreground hover:text-navy flex items-center gap-1"
                  data-testid={`toggle-checklist-${event.id}`}
                >
                  {expanded ? (
                    <>Hide checklist <ChevronUp className="w-3 h-3" aria-hidden="true" /></>
                  ) : (
                    <>Checklist ({checklistCompleted}/{checklist.length}) <ChevronDown className="w-3 h-3" aria-hidden="true" /></>
                  )}
                </button>
              )}
            </div>

            {event.description && (
              <p className="text-sm text-muted-foreground mt-1">{event.description}</p>
            )}

            <div className="flex items-center gap-4 mt-2 flex-wrap">
              <span className="font-mono text-xs text-muted-foreground">
                Due: {formatDate(event.date)}
              </span>
              {typeof event.days_remaining === 'number' && status !== 'completed' && (
                <span className={`font-mono text-xs ${overdue ? 'text-red-600' : 'text-muted-foreground'}`}>
                  {overdue
                    ? `${Math.abs(event.days_remaining)} days overdue`
                    : `${event.days_remaining} days left`}
                </span>
              )}
              {event.completed_at && (
                <span className="font-mono text-xs text-emerald-600">
                  Completed: {formatDate(event.completed_at)}
                </span>
              )}
            </div>

            {/* Expandable checklist */}
            {expanded && checklist.length > 0 && (
              <div className="mt-4 pt-3 border-t border-navy/10">
                <div className="space-y-2">
                  {checklist.map((item, idx) => (
                    <label
                      key={idx}
                      className={`flex items-start gap-3 p-2 cursor-pointer hover:bg-muted/30 transition-colors ${item.completed ? 'opacity-70' : ''}`}
                    >
                      <button
                        role="checkbox"
                        aria-checked={item.completed}
                        aria-label={item.completed ? `Mark "${item.text}" as incomplete` : `Mark "${item.text}" as complete`}
                        onClick={() => onToggleChecklist(event.id, idx)}
                        className={`w-5 h-5 flex items-center justify-center rounded-none border-2 transition-colors focus:ring-2 focus:ring-gold focus:ring-offset-1 ${
                          item.completed ? 'bg-gold border-gold text-navy' : 'border-navy/30 hover:border-gold'
                        }`}
                      >
                        {item.completed ? <span className="text-xs">&#10003;</span> : ''}
                      </button>
                      <span className={`text-sm ${item.completed ? 'line-through text-muted-foreground' : 'text-navy'}`}>
                        {item.text}
                      </span>
                    </label>
                  ))}
                </div>
                {/* Progress bar */}
                <div className="mt-3 pt-2 border-t border-navy/5">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-muted rounded-none">
                      <div
                        className="h-full bg-gold rounded-none transition-all duration-300"
                        style={{ width: `${(checklistCompleted / checklist.length) * 100}%` }}
                      />
                    </div>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {checklistCompleted}/{checklist.length}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 sm:ml-4">
          {status !== 'completed' ? (
            <Button
              onClick={() => onComplete(event.id)}
              size="sm"
              className="btn-primary"
              data-testid={`complete-task-${event.id}`}
            >
              Complete
            </Button>
          ) : (
            <Button
              onClick={() => onUncomplete(event.id)}
              size="sm"
              variant="outline"
              className="btn-secondary"
            >
              Undo
            </Button>
          )}
          <Link
            to={`/trust-assistant?prompt=${encodeURIComponent(`Explain what I need to do for the ${humanizeTaskType(event.task_type || event.title || '')} deadline on ${formatDate(event.date)} and help me prepare.`)}`}
            className="inline-flex items-center gap-1 px-2 py-1.5 text-xs text-gold hover:bg-gold/10 transition-colors"
            title="Ask Trust Assistant for help"
            data-testid={`ta-help-task-${event.id}`}
          >
            <Bot className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Ask AI</span>
          </Link>
          <Button
            onClick={() => onDelete(event.id)}
            size="sm"
            variant="ghost"
            className="text-red-600 hover:text-red-600 hover:bg-red-50"
            aria-label="Delete task"
            data-testid={`delete-task-${event.id}`}
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}