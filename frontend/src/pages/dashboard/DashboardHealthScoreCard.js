import { Link } from 'react-router-dom';
import { CheckCircle2, Circle, ArrowRight, AlertCircle, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { getScoreColor } from './constants';

/**
 * Trust Health / Defensibility Score card.
 * Shows the overall score circle, 5-criteria breakdown with progress bars,
 * and conditional warning/urgent/welcome banners based on score + trust age.
 */
export function DashboardHealthScoreCard({ dashboard, selectedTrust, healthScore, isNewTrust }) {
  return (
    <div className="lg:col-span-2 card-trust corner-mark">
      <div className="flex items-start justify-between mb-6">
        <div>
          <p className="label-trust mb-1">Trust Health</p>
          <h2 className="font-serif text-2xl text-navy">{dashboard?.trust_name || selectedTrust?.name}</h2>
          {selectedTrust?.trustees && (
            <p className="text-sm text-muted-foreground mt-1">
              Trustees: {selectedTrust.trustees}
            </p>
          )}
        </div>
        <Link
          to="/governance"
          className="text-navy hover:text-navy/70 font-mono text-xs uppercase tracking-widest flex items-center gap-1"
          data-testid="view-governance-link"
        >
          View Details <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      <div className="flex items-center gap-8">
        <div className="score-circle">
          <span className={`score-indicator ${getScoreColor(healthScore?.total_score || 0)}`}>
            {healthScore?.total_score || 0}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
            Score
          </span>
        </div>

        {/* 5-Criteria Display */}
        {healthScore?.criteria ? (
          <div className="flex-1 space-y-3">
            {healthScore.criteria.map((criterion, i) => (
              <div key={i} className="flex items-center justify-between" title={criterion.description || criterion.name}>
                <span className="text-sm text-muted-foreground flex items-center gap-2">
                  {criterion.achieved ? (
                    <CheckCircle2 className="w-4 h-4 text-success" />
                  ) : (
                    <Circle className="w-4 h-4 text-navy/30" />
                  )}
                  <span className="cursor-help border-b border-dotted border-muted-foreground/40" onClick={(e) => { e.preventDefault(); toast.info(criterion.name, { description: criterion.description }); }}>
                    {criterion.name}
                  </span>
                </span>
                <div className="flex items-center gap-2">
                  <div className="w-16 h-2 bg-navy/10">
                    <div
                      className={`h-full ${criterion.achieved ? 'bg-success' : 'bg-navy/20'}`}
                      style={{ width: `${(criterion.points / (criterion.max_points || 15)) * 100}%` }}
                    ></div>
                  </div>
                  <span className={`font-mono text-xs w-8 ${criterion.achieved ? 'text-success' : 'text-muted-foreground'}`}>
                    {criterion.points}/{criterion.max_points || 15}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex-1 text-muted-foreground text-sm">
            Loading criteria...
          </div>
        )}
      </div>

      <ScoreBanners healthScore={healthScore} isNewTrust={isNewTrust} />
    </div>
  );
}

function ScoreBanners({ healthScore, isNewTrust }) {
  const score = healthScore?.total_score;
  const needsAttention = score < 96 && score >= 72 && !isNewTrust;
  const isUrgent = score < 72 && !isNewTrust;
  const isNewAndLowScore = score < 72 && isNewTrust;

  if (needsAttention) {
    return (
      <div className="mt-6 p-4 bg-warning/10 border border-warning/20 flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-warning flex-shrink-0" />
        <p className="text-sm text-warning">
          Your governance score needs attention. Consider completing the suggested actions above.
        </p>
      </div>
    );
  }

  if (isUrgent) {
    return (
      <div className="mt-6 p-4 bg-error/10 border border-error/20 flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-error flex-shrink-0" />
        <p className="text-sm text-error">
          Urgent: Your trust requires immediate attention. Complete pending tasks to improve your score.
        </p>
      </div>
    );
  }

  if (isNewAndLowScore) {
    return (
      <div className="mt-6 p-4 bg-gold/10 border border-gold/20 flex items-start gap-3">
        <Sparkles className="w-5 h-5 text-gold flex-shrink-0" />
        <div>
          <p className="text-sm text-navy font-medium">
            Welcome! You're just getting started.
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Your score will build as you complete the steps below. Don't worry about the number right now, just follow the Getting Started checklist at your own pace.
          </p>
        </div>
      </div>
    );
  }

  return null;
}