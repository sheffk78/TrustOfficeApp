import { Button } from '@/components/ui/button';
import {
  ArrowLeft, Upload, Loader2, FileSearch, X,
} from './onboardingConstants';

/**
 * Step 2 of the onboarding wizard — the AI analysis screen with cycling
 * progress hints, a back button, and an error/retry fallback.
 */
export default function AnalyzingStep({
  analysisError,
  hintIndex,
  progressHints,
  onBack,
  onRetry,
  onEnterManually,
}) {
  return (
    <div className="mt-8">
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-muted-foreground hover:text-navy mb-6 transition-colors"
        type="button"
        data-testid="analysis-back-btn"
      >
        <ArrowLeft className="w-4 h-4" />
        <span className="font-mono text-xs uppercase tracking-widest">Back</span>
      </button>

      <div className="card-trust corner-mark mb-8 text-center" data-testid="analysis-screen">
        <div className="py-8">
          {!analysisError ? (
            <>
              <div className="w-20 h-20 bg-navy/5 rounded-full flex items-center justify-center mx-auto mb-6">
                <FileSearch className="w-10 h-10 text-navy animate-pulse" />
              </div>
              <h1 className="font-serif text-3xl text-navy mb-3">
                Analyzing Your Document
              </h1>
              <p className="text-muted-foreground mb-8 max-w-md mx-auto">
                Our AI is reading your trust document and extracting key details...
              </p>

              <div className="flex items-center justify-center gap-2 mb-6 min-h-[28px]">
                <Loader2 className="w-4 h-4 text-navy animate-spin" />
                <span className="text-sm text-navy font-medium transition-opacity">
                  {progressHints[hintIndex]}
                </span>
              </div>

              <p className="text-xs text-muted-foreground">
                This usually takes 30-60 seconds. You can continue while it processes.
              </p>
            </>
          ) : (
            <>
              <div className="w-20 h-20 bg-warning/10 rounded-full flex items-center justify-center mx-auto mb-6">
                <X className="w-10 h-10 text-warning" />
              </div>
              <h1 className="font-serif text-3xl text-navy mb-3">
                Analysis Failed
              </h1>
              <p className="text-muted-foreground mb-8 max-w-md mx-auto">
                {analysisError}
              </p>
              <div className="flex flex-col gap-3 max-w-sm mx-auto">
                <Button
                  onClick={onRetry}
                  className="btn-primary h-12"
                  data-testid="retry-upload-btn"
                >
                  <Upload className="w-5 h-5 mr-2" />
                  Try Again - Re-upload
                </Button>
                <Button
                  onClick={onEnterManually}
                  variant="outline"
                  className="h-12"
                  data-testid="enter-manually-btn"
                >
                  Enter Manually
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
