import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import OnboardingConfirmStep from '@/components/onboarding/OnboardingConfirmStep';
import {
  PROGRESS_HINTS,
} from '@/components/onboarding/onboardingConstants';
import { useOnboardingWizard } from '@/components/onboarding/useOnboardingWizard';
import OnboardingProgressBar from '@/components/onboarding/OnboardingProgressBar';
import ExpiredSubscriptionStep from '@/components/onboarding/ExpiredSubscriptionStep';
import DocumentUploadStep from '@/components/onboarding/DocumentUploadStep';
import AnalyzingStep from '@/components/onboarding/AnalyzingStep';
import WelcomeStep from '@/components/onboarding/WelcomeStep';

export default function OnboardingPage() {
  const wizard = useOnboardingWizard();
  const {
    user, trusts, isSubscriptionExpired,
    step, setStep,
    checkingTrusts, setCheckingTrusts,
    skipDocument, setSkipDocument,
    initialTrustCheckDone,
    trustDoc, setTrustDoc, uploadingDoc, uploadProgress, docUploaded, setDocUploaded,
    fileInputRef,
    trustData, setTrustData, trusteeNames, setTrusteeNames,
    extractedFields, analysisError,
    stopPolling, resetPolling, resetAnalysisState,
    handleDocUpload, handleSkipDoc, handleConfirmDetails, handleSeedDemo,
    handleDocSelect, handleDrop, handleDragOver,
    loading, subscription, createdTrustName,
  } = wizard;

  // Progress hint cycling for the analyzing screen
  const [hintIndex, setHintIndex] = useState(0);
  useEffect(() => {
    if (step !== 2) return;
    const interval = setInterval(() => {
      setHintIndex(prev => (prev + 1) % PROGRESS_HINTS.length);
    }, 3000);
    return () => clearInterval(interval);
  }, [step]);

  // Check if user already has trusts - redirect to dashboard if so
  useEffect(() => {
    const checkExistingTrusts = async () => {
      try {
        await wizard.loadTrusts?.();
      } catch (error) {
        console.error('Failed to check trusts:', error);
      } finally {
        setCheckingTrusts(false);
      }
    };
    checkExistingTrusts();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!checkingTrusts && trusts && trusts.length > 0 && !isSubscriptionExpired) {
      if (!initialTrustCheckDone.current) {
        wizard.navigate('/dashboard', { replace: true });
      }
    }
    if (!checkingTrusts) {
      initialTrustCheckDone.current = true;
    }
  }, [checkingTrusts, trusts, isSubscriptionExpired]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fill first trustee name with the signed-up user's name
  useEffect(() => {
    if (user?.name && trusteeNames[0] === '') {
      setTrusteeNames([user.name]);
    }
  }, [user?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  if (checkingTrusts) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-subtle-bg" data-testid="onboarding-page">
      <OnboardingProgressBar step={step} />

      {/* Content */}
      <div className="max-w-3xl mx-auto px-8 pb-16">

        {/* EXPIRED SUBSCRIPTION */}
        {isSubscriptionExpired && step === 1 && <ExpiredSubscriptionStep />}

        {/* STEP 1: Document Upload */}
        {step === 1 && !isSubscriptionExpired && (
          <DocumentUploadStep
            user={user}
            subscription={subscription}
            trustDoc={trustDoc}
            fileInputRef={fileInputRef}
            handleDocSelect={handleDocSelect}
            handleDrop={handleDrop}
            handleDragOver={handleDragOver}
            handleDocUpload={handleDocUpload}
            handleSkipDoc={handleSkipDoc}
            handleSeedDemo={handleSeedDemo}
            uploadingDoc={uploadingDoc}
            uploadProgress={uploadProgress}
            loading={loading}
          />
        )}

        {/* STEP 2: AI Analyzing */}
        {step === 2 && (
          <AnalyzingStep
            analysisError={analysisError}
            hintIndex={hintIndex}
            progressHints={PROGRESS_HINTS}
            onBack={() => {
              stopPolling();
              resetPolling();
              setTrustDoc(null);
              setDocUploaded(false);
              setStep(1);
            }}
            onRetry={() => {
              resetPolling();
              stopPolling();
              setStep(1);
              setDocUploaded(false);
              setTrustDoc(null);
            }}
            onEnterManually={() => {
              stopPolling();
              resetPolling();
              setSkipDocument(true);
              setStep(3);
            }}
          />
        )}

        {/* STEP 3: Review Details (OnboardingConfirmStep) */}
        {step === 3 && (
          <div className="mt-8">
            <OnboardingConfirmStep
              extractedFields={extractedFields}
              trustData={trustData}
              setTrustData={setTrustData}
              trusteeNames={trusteeNames}
              setTrusteeNames={setTrusteeNames}
              onBack={() => setStep(skipDocument ? 1 : 2)}
              onConfirm={handleConfirmDetails}
              loading={loading}
            />
          </div>
        )}

        {/* STEP 4: Welcome / Quick Start */}
        {step === 4 && <WelcomeStep createdTrustName={createdTrustName} />}
      </div>
    </div>
  );
}
