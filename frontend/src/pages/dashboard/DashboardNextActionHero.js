import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { getNextActionVariantClass } from './constants';

/**
 * "Do This Next" hero card — shows the single highest-priority action,
 * or an "all caught up" card when there are no pending actions.
 */
export function DashboardNextActionHero({ nextAction }) {
  if (nextAction) {
    return (
      <div
        className={`mb-8 card-trust overflow-hidden ${getNextActionVariantClass(nextAction.variant)}`}
        data-testid="do-this-next-hero"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Do This Next
              </span>
              {nextAction.variant === 'urgent' && (
                <span className="font-mono text-[10px] uppercase tracking-widest px-1.5 py-0.5 bg-error/20 text-error">
                  Urgent
                </span>
              )}
            </div>
            <h2 className="font-serif text-2xl text-navy dark:text-foreground mb-1">
              {nextAction.title}
            </h2>
            <p className="text-sm text-muted-foreground">{nextAction.context}</p>
          </div>
          <div className="flex-shrink-0">
            <Link
              to={nextAction.action}
              className="btn-primary inline-flex items-center gap-2 h-12 px-6 text-base"
              data-testid="do-this-next-cta"
            >
              {nextAction.cta}
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-8 card-trust bg-gradient-to-r from-success/10 to-success/5 border-l-4 border-l-success" data-testid="all-caught-up-hero">
      <div className="flex items-center gap-4 p-6">
        <div className="w-12 h-12 bg-success/20 flex items-center justify-center">
          <CheckCircle2 className="w-6 h-6 text-success" />
        </div>
        <div>
          <h2 className="font-serif text-2xl text-navy dark:text-foreground mb-1">You're all caught up!</h2>
          <p className="text-sm text-muted-foreground">No pending actions. Your trust governance is in great shape.</p>
        </div>
      </div>
    </div>
  );
}