import { useNavigate, Link } from 'react-router-dom';
import { Sparkles, AlertCircle, ArrowRight, ChevronRight, X, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { INSIGHT_ICONS } from './constants';

// Priority ordering for insight types (error > warning > info)
const TYPE_PRIORITY = { error: 0, warning: 1, info: 2 };

function sortInsightsByPriority(insights) {
  return [...insights].sort((a, b) => {
    const typeDiff = (TYPE_PRIORITY[a.type] ?? 3) - (TYPE_PRIORITY[b.type] ?? 3);
    if (typeDiff !== 0) return typeDiff;
    return b.points - a.points;
  });
}

function getInsightVariantClass(type) {
  switch (type) {
    case 'error':
      return {
        border: 'border-error/30 bg-error/5 hover:border-error/50',
        iconBg: 'bg-error/20 text-error',
        badge: 'bg-error/20 text-error',
        numberColor: 'text-error',
        button: 'bg-error hover:bg-error/90 text-white',
      };
    case 'warning':
      return {
        border: 'border-warning/30 bg-warning/5 hover:border-warning/50',
        iconBg: 'bg-warning/20 text-warning',
        badge: 'bg-warning/20 text-warning',
        numberColor: 'text-warning',
        button: 'bg-warning hover:bg-warning/90 text-white',
      };
    default:
      return {
        border: 'border-navy/20 bg-navy/5 hover:border-navy/30',
        iconBg: 'bg-navy/10 text-navy',
        badge: 'bg-success/20 text-success',
        numberColor: 'text-muted-foreground',
        button: 'btn-primary',
      };
  }
}

/**
 * Today's Focus card — shows top 3 prioritized governance insights.
 * Insights are sorted by type priority (error > warning > info), then by points.
 *
 * Dedup with "Do This Next" hero: when nextAction.variant === 'insight', the
 * hero already surfaces the single highest-priority insight. To avoid showing
 * the same recommendation twice, we skip the insight whose action_path matches
 * nextAction.action and surface the next ones (2nd, 3rd) here instead.
 */
export function DashboardTodaysFocus({ insights, healthScore, dismissInsight, nextAction }) {
  const navigate = useNavigate();

  if (!insights || insights.length === 0) return null;

  const sortedInsights = sortInsightsByPriority(insights);

  // If the Do This Next hero is already featuring a governance insight, skip
  // that insight here so the user sees the NEXT recommendation, not a repeat.
  const heroInsightAction = nextAction?.variant === 'insight' ? nextAction.action : null;
  const dedupedInsights = heroInsightAction
    ? sortedInsights.filter(i => i.action_path !== heroInsightAction)
    : sortedInsights;

  // Nothing left after dedup — the hero covers the only actionable insight.
  if (dedupedInsights.length === 0) return null;

  const topInsights = dedupedInsights.slice(0, 3);
  const remainingCount = dedupedInsights.length - topInsights.length;
  const totalPoints = dedupedInsights.reduce((sum, i) => sum + i.points, 0);
  const isPerfectScore = healthScore?.total_score === healthScore?.max_score;

  return (
    <div className="mb-8 card-trust corner-mark" data-testid="todays-focus-card">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-gold/20 to-navy/10 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-gold" />
          </div>
          <div>
            <h3 className="font-serif text-lg text-navy">Today's Focus</h3>
            <p className="text-sm text-muted-foreground">
              {sortedInsights.length} action{sortedInsights.length !== 1 ? 's' : ''} to boost your score by +{totalPoints} points
            </p>
          </div>
        </div>
        {remainingCount > 0 && (
          <Link
            to="/governance"
            className="text-navy hover:text-navy/70 font-mono text-xs uppercase tracking-widest flex items-center gap-1"
          >
            View All ({remainingCount} more) <ArrowRight className="w-3 h-3" />
          </Link>
        )}
      </div>

      <div className="space-y-3">
        {topInsights.map((insight, index) => {
          const InsightIcon = INSIGHT_ICONS[insight.criterion_name] || AlertCircle;
          const styles = getInsightVariantClass(insight.type);

          return (
            <div
              key={index}
              className={`relative flex items-center justify-between p-4 border transition-all hover:shadow-sm ${styles.border}`}
              data-testid={`insight-${index}`}
            >
              <div className="flex items-center gap-4 flex-1">
                <div className={`w-10 h-10 flex items-center justify-center flex-shrink-0 ${styles.iconBg}`}>
                  <InsightIcon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className={`font-mono text-xs ${styles.numberColor}`}>
                      #{index + 1}
                    </span>
                    <h4 className="font-medium text-navy">{insight.title}</h4>
                    <span className={`px-2 py-0.5 text-xs font-mono ${styles.badge}`}>
                      +{insight.points} pts
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{insight.description}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                <button
                  onClick={() => dismissInsight(insight.criterion_name)}
                  className="text-muted-foreground hover:text-error transition-colors p-1"
                  title="Dismiss this recommendation"
                  data-testid={`insight-dismiss-${index}`}
                >
                  <X className="w-4 h-4" />
                </button>
                <Button
                  onClick={() => navigate(insight.action_path)}
                  size="sm"
                  className={styles.button}
                  data-testid={`insight-action-${index}`}
                >
                  {insight.action_label}
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      {isPerfectScore && (
        <div className="mt-4 p-4 bg-success/10 border border-success/20 flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 text-success flex-shrink-0" />
          <p className="text-sm text-success font-medium">
            Excellent! Your governance is in perfect health. Keep up the great work!
          </p>
        </div>
      )}
    </div>
  );
}