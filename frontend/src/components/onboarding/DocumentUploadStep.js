import { Button } from '@/components/ui/button';
import {
  Upload, Sparkles, Lock, FileCheck,
} from './onboardingConstants';

/**
 * Step 1 of the onboarding wizard — the document upload drop zone with
 * skip-to-manual-entry and demo-data options.
 */
export default function DocumentUploadStep({
  user,
  subscription,
  trustDoc,
  fileInputRef,
  handleDocSelect,
  handleDrop,
  handleDragOver,
  handleDocUpload,
  handleSkipDoc,
  handleSeedDemo,
  uploadingDoc,
  uploadProgress,
  loading,
}) {
  return (
    <div className="mt-8">
      <div className="card-trust corner-mark mb-8">
        <div className="mb-8">
          <h1 className="font-serif text-4xl text-navy mb-3">
            Welcome to TrustOffice, {user?.name?.split(' ')[0] || 'there'}
          </h1>
          <p className="text-lg text-muted-foreground">
            Upload your trust document and we'll extract the details automatically.
          </p>
        </div>

        {subscription?.plan_type === 'free' && (
          <div className="bg-navy/5 border border-navy/10 p-4 mb-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-warning/10 rounded-full flex items-center justify-center">
                <Lock className="w-5 h-5 text-warning" />
              </div>
              <div>
                <p className="font-medium text-navy">Free Plan - Core Features Only</p>
                <p className="text-sm text-muted-foreground">Minutes, distributions, and basic governance. Upgrade for the full toolkit.</p>
              </div>
            </div>
          </div>
        )}

        {/* Drop zone */}
        <div className="space-y-5">
          <div
            onClick={() => fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            className="border-2 border-dashed border-navy/20 hover:border-navy/40 transition-colors p-8 text-center cursor-pointer mb-4"
            data-testid="doc-drop-zone"
          >
            <input
              ref={fileInputRef}
              type="file"
              onChange={handleDocSelect}
              accept=".pdf,.doc,.docx,.txt,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
              className="hidden"
            />
            {trustDoc ? (
              <div className="flex items-center justify-center gap-3">
                <FileCheck className="w-8 h-8 text-success" />
                <div className="text-left">
                  <p className="font-medium text-navy">{trustDoc.name}</p>
                  <p className="text-sm text-muted-foreground">{(trustDoc.size / 1024).toFixed(0)} KB - Ready to upload</p>
                </div>
              </div>
            ) : (
              <div>
                <Upload className="w-12 h-12 text-navy/30 mx-auto mb-3" />
                <p className="font-medium text-navy mb-1">Click to upload or drag and drop</p>
                <p className="text-sm text-muted-foreground">PDF, Word document, or text file — up to 100MB (large PDFs auto-compressed)</p>
              </div>
            )}
          </div>

          {trustDoc && !uploadingDoc && (
            <Button
              onClick={handleDocUpload}
              className="w-full btn-primary h-12"
              data-testid="upload-trust-doc-btn"
            >
              <Upload className="w-5 h-5 mr-2" />
              Upload and Analyze
            </Button>
          )}

          {uploadingDoc && (
            <div className="py-4" aria-live="polite">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-muted-foreground">{uploadProgress}</span>
                <span className="text-xs text-muted-foreground/70">
                  {uploadProgress.includes('%') ? 'Large files may take a few minutes' : 'Compressing and securing your document — no need to do anything'}
                </span>
              </div>
              <div
                className="h-1.5 w-full rounded-full bg-muted overflow-hidden"
                role="progressbar"
                aria-label="Upload progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={uploadProgress.includes('%') ? parseInt(uploadProgress.replace(/\D/g, ''), 10) || 0 : 95}
              >
                <div
                  className="h-full bg-navy transition-all duration-300"
                  style={{ width: uploadProgress.includes('%') ? `${parseInt(uploadProgress.replace(/\D/g, ''), 10) || 0}%` : '95%' }}
                />
              </div>
            </div>
          )}

          {/* Skip option */}
          <div className="pt-2">
            <button
              onClick={handleSkipDoc}
              className="w-full text-center text-sm text-muted-foreground hover:text-navy transition-colors py-2"
              data-testid="skip-doc-upload"
            >
              I don't have it digitized - enter details manually
            </button>
          </div>
        </div>

        {/* Demo data option */}
        <div className="mt-8 pt-6 border-t border-navy/10">
          <p className="text-center text-sm text-muted-foreground mb-3">
            Not ready to set up your own trust yet?
          </p>
          <Button
            onClick={handleSeedDemo}
            variant="outline"
            className="w-full"
            disabled={loading}
            data-testid="load-demo-btn"
          >
            <Sparkles className="w-4 h-4 mr-2" />
            Explore with Demo Data
          </Button>
        </div>
      </div>
    </div>
  );
}
