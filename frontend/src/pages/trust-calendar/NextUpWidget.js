import { Link } from 'react-router-dom';
import { AlertTriangle, Bot, Clock, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatDate, eventTitle } from './calendarHelpers';

// "Next Up" widget: the most urgent pending item, with contextual action
// buttons (Mark Filed / Extend for tax; Complete for governance tasks;
// View link for money/structure events) and an "Ask AI" shortcut.
//
// Props:
//   nextUp              – the next-up event object (or null)
//   onCompleteTask      – (taskId) => void
//   onMarkFiledConfirm  – ({ action, entryId, label, taxYear }) => void
export default function NextUpWidget({ nextUp, onCompleteTask, onMarkFiledConfirm, onDismiss }) {
  if (!nextUp) return null;

  const isTax = nextUp.event_type === 'tax_deadline';
  const isGovernance = nextUp.event_type === 'governance_task';
  const isOther = !isTax && !isGovernance;
  const title = eventTitle(nextUp);

  return (
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
              <div className="font-medium text-navy">{title}</div>
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
            {isTax && nextUp.filing_status === 'pending' && (
              <>
                <Button
                  size="sm"
                  className="btn-primary"
                  onClick={() => onMarkFiledConfirm({
                    action: 'filed',
                    entryId: nextUp.entry_id,
                    label: nextUp.title || nextUp.deadline_type,
                    taxYear: nextUp.tax_year,
                  })}
                >
                  Mark Filed
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-warning text-warning"
                  onClick={() => onMarkFiledConfirm({
                    action: 'extended',
                    entryId: nextUp.entry_id,
                    label: nextUp.title || nextUp.deadline_type,
                    taxYear: nextUp.tax_year,
                  })}
                >
                  Extend
                </Button>
              </>
            )}
            {isGovernance && nextUp.status !== 'completed' && (
              <Button size="sm" className="btn-primary" onClick={() => onCompleteTask(nextUp.id)}>
                Complete
              </Button>
            )}
            {isOther && nextUp.link && (
              <Link
                to={nextUp.link}
                className="inline-flex items-center px-3 py-1.5 text-xs text-gold hover:bg-gold/10 transition-colors border border-gold/20"
                title="View on its page"
              >
                View →
              </Link>
            )}
            <Link
              to={`/trust-assistant?prompt=${encodeURIComponent(
                `Explain what I need to do for the ${title} on ${formatDate(nextUp.date)} and help me prepare.`
              )}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-gold hover:bg-gold/10 transition-colors border border-gold/20"
              title="Ask Trust Assistant for help"
              data-testid="ta-next-up-help"
            >
              <Bot className="w-3.5 h-3.5" />
              Ask AI
            </Link>
            {onDismiss && (
              <button
                onClick={onDismiss}
                className="text-muted-foreground hover:text-navy transition-colors p-1 ml-2"
                aria-label="Dismiss"
                data-testid="next-up-dismiss"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}