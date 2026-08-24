import { useNavigate } from 'react-router-dom';
import { Zap, CheckCircle2, Circle, X, ChevronRight, GraduationCap, ArrowRight } from 'lucide-react';

/**
 * Collapsed onboarding checklist accordion.
 * Shows progress bar, expandable step list with per-step toggle,
 * and a "Start Here" Trustee 101 link.
 */
export function DashboardOnboardingChecklist({
  onboarding,
  onboardingProgress,
  onboardingExpanded,
  setOnboardingExpanded,
  toggleOnboardingStep,
  dismissOnboarding,
  restoreChecklist,
}) {
  const navigate = useNavigate();
  const { completed, total, allSteps } = onboardingProgress;
  const isIncomplete = completed < total;

  // Re-show Getting Started if checklist was dismissed but not fully complete
  if (onboarding?.checklist_dismissed && isIncomplete) {
    return (
      <div className="mb-6">
        <button
          onClick={restoreChecklist}
          className="text-sm text-navy/60 hover:text-navy font-mono flex items-center gap-1.5"
        >
          <Zap className="w-3.5 h-3.5" />
          Show Getting Started ({completed}/{total} complete)
        </button>
      </div>
    );
  }

  // Don't render if dismissed or complete
  if (!onboarding || onboarding.checklist_dismissed || !isIncomplete) return null;

  return (
    <div className="mb-8 card-trust" data-testid="onboarding-checklist">
      <button
        onClick={() => setOnboardingExpanded(!onboardingExpanded)}
        className="w-full flex items-center justify-between text-left"
        data-testid="onboarding-accordion-toggle"
        aria-expanded={onboardingExpanded}
        aria-label={`${onboardingExpanded ? 'Collapse' : 'Expand'} Getting Started checklist`}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gold/20 flex items-center justify-center text-gold">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-serif text-lg text-navy">Getting Started</h3>
            <p className="text-sm text-muted-foreground">
              {completed} of {total} setup steps complete
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {/* Progress bar */}
          <div className="hidden sm:block w-40 h-2 bg-navy/10">
            <div
              className="h-full bg-gold transition-all"
              style={{ width: `${(completed / total) * 100}%` }}
            />
          </div>
          <ChevronRight className={`w-5 h-5 text-muted-foreground transition-transform ${onboardingExpanded ? 'rotate-90' : ''}`} />
          <button
            onClick={(e) => { e.stopPropagation(); dismissOnboarding(); }}
            className="text-muted-foreground hover:text-navy"
            data-testid="dismiss-onboarding"
            aria-label="Dismiss Getting Started checklist"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </button>

      {onboardingExpanded && (
        <div className="mt-6 pt-6 border-t border-navy/10">
          {/* Start Here - Trustee 101 */}
          <div className="mb-4">
            <h4 className="font-mono text-xs uppercase tracking-widest text-gold mb-2">Start Here</h4>
            <button
              onClick={() => navigate('/course')}
              className="w-full p-4 border-2 border-gold/30 bg-gold/5 hover:border-gold hover:bg-gold/10 transition-all text-left flex items-center gap-4 group"
              data-testid="onboarding-step-trustee-101"
            >
              <div className="w-10 h-10 bg-gold/20 flex items-center justify-center group-hover:bg-gold/30 transition-colors flex-shrink-0">
                <GraduationCap className="w-5 h-5 text-gold" />
              </div>
              <div className="flex-1">
                <p className="font-mono text-xs font-medium text-navy">Watch Trustee 101 First</p>
                <p className="text-xs text-muted-foreground mt-0.5">9 short video lessons (6-12 min each) that explain what a trust is, your duties, and how to avoid common traps. Start here before anything else.</p>
              </div>
              <ArrowRight className="w-4 h-4 text-gold opacity-0 group-hover:opacity-100 transition-opacity" />
            </button>
          </div>

          {/* Unified step list */}
          <div>
            <h4 className="font-mono text-xs uppercase tracking-widest text-navy/60 mb-2">Setup Steps</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {allSteps.map((step) => (
                <div
                  key={step.id}
                  className={`p-4 border text-left transition-colors ${
                    step.done
                      ? 'border-success/30 bg-success/5'
                      : 'border-navy/20 hover:border-navy/40'
                  }`}
                  data-testid={`onboarding-step-${step.id}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    {step.done ? (
                      <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                    ) : (
                      <Circle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    )}
                    <span className="font-mono text-[10px] text-muted-foreground">#{step.priority}</span>
                    <button
                      onClick={() => navigate(step.action)}
                      className={`flex-1 text-left font-mono text-xs font-medium ${step.done ? 'text-success line-through' : 'text-navy hover:underline'}`}
                    >
                      {step.label}
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleOnboardingStep(step.field, step.done);
                      }}
                      className={`flex-shrink-0 ml-auto px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider transition-colors ${
                        step.done
                          ? 'text-muted-foreground hover:text-navy border border-navy/20 hover:border-navy/40'
                          : 'text-success/70 hover:text-success border border-success/30 hover:border-success/50'
                      }`}
                      data-testid={`onboarding-toggle-${step.id}`}
                      title={step.done ? 'Uncheck this step' : 'Mark as done'}
                    >
                      {step.done ? 'Uncheck' : 'Done'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}