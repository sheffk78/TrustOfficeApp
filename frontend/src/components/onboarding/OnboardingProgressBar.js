import { STEP_NAMES, TOTAL_STEPS } from './onboardingConstants';

/**
 * The onboarding header — logo + current step name — and the progress bar
 * with numbered segments. Hidden when step exceeds TOTAL_STEPS.
 */
export default function OnboardingProgressBar({ step }) {
  const showProgress = step <= TOTAL_STEPS;
  return (
    <>
      {/* Header */}
      <div className="bg-navy text-white py-4 px-8">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <img
            src="/assets/trustoffice-logo-vertical.svg"
            alt="TrustOffice"
            className="h-8"
          />
          <span className="font-mono text-[10px] uppercase tracking-widest text-white/60">
            {showProgress ? STEP_NAMES[step - 1] : 'Getting Started'}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      {showProgress && (
        <div className="max-w-3xl mx-auto px-8 pt-8">
          <div className="flex items-center gap-2 mb-2">
            {[1, 2, 3, 4].map((s) => (
              <div
                key={s}
                className={`flex-1 h-1 rounded-full transition-colors ${
                  s <= step ? 'bg-navy' : 'bg-navy/20'
                }`}
              />
            ))}
          </div>
          <p className="text-xs text-muted-foreground text-right">
            Step {step} of {TOTAL_STEPS}
          </p>
        </div>
      )}
    </>
  );
}
