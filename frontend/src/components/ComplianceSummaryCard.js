import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Shield, AlertCircle, CalendarClock, ArrowUpRight } from 'lucide-react';

/**
 * Compliance Summary Card — shows instant "am I compliant?" answer on Risk Dashboard.
 *
 * Props:
 *   score         — compliance score (0-100), defaults to 100
 *   alertActive   — boolean, whether compliance alert is active
 *   nextDeadline  — ISO string or null, next upcoming compliance deadline
 */
export default function ComplianceSummaryCard({
  score = 100,
  alertActive = false,
  nextDeadline = null,
}) {
  // Score color logic
  const scoreColor =
    score >= 90 ? 'text-success' :
    score >= 70 ? 'text-warning' :
    'text-error';

  const scoreBg =
    score >= 90 ? 'bg-success/10 border-success/20' :
    score >= 70 ? 'bg-warning/10 border-warning/20' :
    'bg-error/10 border-error/20';

  // Format deadline
  let deadlineLabel = null;
  if (nextDeadline) {
    const d = new Date(nextDeadline);
    if (!isNaN(d.getTime())) {
      const today = new Date();
      const days = Math.ceil((d - today) / (1000 * 60 * 60 * 24));
      if (days < 0) {
        deadlineLabel = `${Math.abs(days)} day(s) overdue`;
      } else if (days === 0) {
        deadlineLabel = 'Due today';
      } else {
        deadlineLabel = `Due in ${days} day(s) (${d.toLocaleDateString()})`;
      }
    }
  }

  return (
    <Card className={`mb-6 border ${scoreBg}`}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <Shield className={`w-8 h-8 ${scoreColor}`} />
            <div>
              <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
                Compliance Summary
              </p>
              <p className={`text-2xl font-bold ${scoreColor}`}>
                {score}<span className="text-sm font-normal text-muted-foreground/40">/100</span>
              </p>
            </div>
          </div>
          <Link
            to="/state-compliance"
            className="text-xs text-navy hover:text-navy/70 flex items-center gap-1 flex-shrink-0"
          >
            View details
            <ArrowUpRight className="w-3 h-3" />
          </Link>
        </div>

        <div className="mt-3 space-y-1.5">
          {alertActive && (
            <div className="flex items-center gap-2 text-sm text-error">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>Compliance alert active — review required actions</span>
            </div>
          )}
          {deadlineLabel && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CalendarClock className="w-4 h-4 flex-shrink-0 text-muted-foreground" />
              <span>Next deadline: {deadlineLabel}</span>
            </div>
          )}
          {!alertActive && !deadlineLabel && score >= 90 && (
            <div className="flex items-center gap-2 text-sm text-success">
              <Shield className="w-4 h-4 flex-shrink-0" />
              <span>All compliance requirements current</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}