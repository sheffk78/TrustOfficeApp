import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { showError, reportErrorToBackend } from '@/utils/errors';
import { useAnalysisPolling } from '@/hooks/useAnalysisPolling';
import OnboardingConfirmStep from '@/components/onboarding/OnboardingConfirmStep';
import {
  ArrowRight, ArrowLeft, CheckCircle2,
  Upload, Sparkles, Lock, CreditCard, Clock, Loader2, FileCheck,
  X, FileSearch,
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

// Use XMLHttpRequest for maximum mobile compatibility
const xhrRequest = (method, url, data = null, token = null) => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Accept', 'application/json');
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }

    xhr.onreadystatechange = function() {
      if (xhr.readyState === 4) {
        try {
          const response = xhr.responseText ? JSON.parse(xhr.responseText) : {};
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(response);
          } else {
            // Handle 403 subscription read-only errors
            if (xhr.status === 403) {
              const subStatus = xhr.getResponseHeader('X-Subscription-Status');
              if (subStatus || response.is_read_only) {
                window.dispatchEvent(new CustomEvent('subscription-readonly', {
                  detail: { status: subStatus || response.subscription_status || 'expired' }
                }));
              }
            }
            // Handle 401 auth errors with a clear message
            if (xhr.status === 401) {
              reject(new Error('Your session has expired. Please log in again.'));
              return;
            }
            // Surface the backend's error detail, not a generic "Request failed"
            const detail = response.detail || response.message || response.msg;
            const msg = typeof detail === 'string'
              ? detail
              : (detail?.message || detail?.msg || (detail && detail !== '{}' ? JSON.stringify(detail) : null) || 'We couldn\'t complete this action. Please try again, or contact support@trustoffice.app for help.');
            reject(new Error(msg));
          }
        } catch (e) {
          reject(new Error('Invalid server response'));
        }
      }
    };

    xhr.onerror = function() {
      reject(new Error('Network error - please check your connection'));
    };

    xhr.send(data ? JSON.stringify(data) : null);
  });
};

// Step names for progress indicator
const stepNames = ['Upload Document', 'Analyzing', 'Review Details', 'Welcome'];
const totalSteps = 4;

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { user, trusts, loadTrusts, setSelectedTrust, subscription, subscriptionExpired, loading: authLoading } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [checkingTrusts, setCheckingTrusts] = useState(true);
  const [createdTrustId, setCreatedTrustId] = useState('');
  const [createdTrustName, setCreatedTrustName] = useState('');

  // Trust document upload state
  const [trustDoc, setTrustDoc] = useState(null);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [docUploaded, setDocUploaded] = useState(false);
  const fileInputRef = useRef(null);

  // Skip document flag - when user skips upload and fills manually
  const [skipDocument, setSkipDocument] = useState(false);

  // Progress hint cycling for the analyzing screen
  const [hintIndex, setHintIndex] = useState(0);
  const progressHints = [
    'Reading document...',
    'Extracting trustee names...',
    'Identifying trust type...',
    'Finding distribution rules...',
  ];

  const [trustData, setTrustData] = useState({
    name: '',
    trust_type: 'revocable_living',
    jurisdiction: '',
    role: 'Trustee',
    review_cadence: 'quarterly',
    description: '',
    ein: '',
    state_code: '',
    start_date: '',
    tax_year_end_month: '12',
    tax_year_end_day: '31',
    is_fiscal_year: false,
  });

  // Trustee names - auto-filled with the signed-up user's name, editable
  // Multiple trustees can be added/removed for trusts with co-trustees
  const [trusteeNames, setTrusteeNames] = useState(['']);

  const getToken = () => localStorage.getItem('auth_token');

  // Check if subscription is inactive (expired and not trial)
  const isSubscriptionExpired = subscription && !subscription.is_active;

  // Analysis polling hook - polls the backend for AI extraction status
  const { extractedFields, error: analysisError, start: startPolling, stop: stopPolling, reset: resetPolling } = useAnalysisPolling(createdTrustId, {
    onComplete: (fields) => {
      // Move to review step. OnboardingConfirmStep handles pre-filling
      // trust data from extractedFields via its own useEffect.
      setStep(3);
    },
    onError: (errMsg) => {
      console.error('Analysis failed:', errMsg);
    },
  });

  // Cycle progress hints while analyzing
  useEffect(() => {
    if (step !== 2) return;
    const interval = setInterval(() => {
      setHintIndex(prev => (prev + 1) % progressHints.length);
    }, 3000);
    return () => clearInterval(interval);
  }, [step]);

  // Check if user already has trusts - redirect to dashboard if so
  useEffect(() => {
    const checkExistingTrusts = async () => {
      try {
        await loadTrusts();
      } catch (error) {
        console.error('Failed to check trusts:', error);
      } finally {
        setCheckingTrusts(false);
      }
    };
    checkExistingTrusts();
  }, []);

  useEffect(() => {
    if (!checkingTrusts && trusts && trusts.length > 0 && !isSubscriptionExpired) {
      navigate('/dashboard', { replace: true });
    }
  }, [checkingTrusts, trusts, navigate, isSubscriptionExpired]);

  // Auto-fill first trustee name with the signed-up user's name
  useEffect(() => {
    if (user?.name && trusteeNames[0] === '') {
      setTrusteeNames([user.name]);
    }
  }, [user?.name]);

  if (checkingTrusts) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  // File selection validation - same as current
  const handleDocSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Validate file type
    const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain', 'image/png', 'image/jpeg', 'image/jpg'];
    if (!allowedTypes.includes(file.type) && !file.name.toLowerCase().endsWith('.pdf') && !file.name.toLowerCase().endsWith('.doc') && !file.name.toLowerCase().endsWith('.docx') && !file.name.toLowerCase().endsWith('.txt')) {
      toast.error('Please upload a PDF, Word document, or text file');
      return;
    }

    if (file.size > 16 * 1024 * 1024) {
      toast.error('File is too large. Maximum size is 16MB.');
      return;
    }

    setTrustDoc(file);
    setDocUploaded(false);
  };

  // Document-first upload: create minimal trust, then upload doc to vault
  const handleDocUpload = async () => {
    if (!trustDoc) return;

    setUploadingDoc(true);
    setUploadProgress('Creating trust...');

    // If a previous trust was already created (e.g. user went back and is re-uploading),
    // stop any in-flight polling and reset the hook state before starting fresh.
    stopPolling();
    resetPolling();

    let newTrust = null;
    try {
      // Step 1: Create a minimal trust first
      const minimalTrustPayload = {
        name: 'My Trust',
        trust_type: 'revocable_living',
        jurisdiction: '',
        trustees: user?.name ? [user.name] : []
      };
      newTrust = await xhrRequest('POST', `${API_URL}/api/trusts`, minimalTrustPayload, getToken());
      setCreatedTrustId(newTrust.trust_id);
      setSelectedTrust(newTrust);
      await loadTrusts();

      // Step 2: Upload the file to the vault, which triggers AI analysis
      setUploadProgress('Uploading document...');
      const formData = new FormData();
      formData.append('file', trustDoc);
      formData.append('title', 'Declaration of Trust');
      formData.append('category', 'trust_instrument');

      const token = localStorage.getItem('auth_token');
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);

      let res;
      try {
        res = await fetch(`${API_URL}/api/trusts/${newTrust.trust_id}/vault/upload`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
          signal: controller.signal,
        });
      } catch (fetchError) {
        clearTimeout(timeoutId);
        if (fetchError.name === 'AbortError') {
          throw new Error('Upload timed out. Please try again.');
        }
        throw new Error('Could not reach the server. Check your connection and try again.');
      }
      clearTimeout(timeoutId);

      if (!res.ok) {
        let errorMsg = 'Upload failed';
        try {
          const errData = await res.json();
          errorMsg = errData.detail || errorMsg;
        } catch (e) {
          errorMsg = `Upload failed (${res.status})`;
        }
        throw new Error(errorMsg);
      }

      // Step 3: Move to analyzing screen and start polling
      setDocUploaded(true);
      toast.success('Trust document uploaded! We are analyzing it now.');
      setStep(2);
      // Start polling for analysis results.
      // The hook reads trustId from a ref, so it picks up the new
      // createdTrustId even though setCreatedTrustId hasn't re-rendered yet.
      startPolling();
    } catch (error) {
      console.error('Doc upload error:', error);
      showError(toast, error, { operation: 'upload_trust_doc', page: 'Onboarding' });
      setUploadProgress('');
      // If the trust was created but the upload failed, the user has a
      // half-created trust. We leave it in place (named "My Trust") so the
      // user can still proceed via manual entry. The next handleConfirmDetails
      // PUT will update it with the real data.
    } finally {
      setUploadingDoc(false);
    }
  };

  // For users without a digitized document: create trust and go to manual entry
  const handleSkipDoc = async () => {
    setLoading(true);
    try {
      const minimalTrustPayload = {
        name: 'My Trust',
        trust_type: 'revocable_living',
        jurisdiction: '',
        trustees: user?.name ? [user.name] : []
      };
      const newTrust = await xhrRequest('POST', `${API_URL}/api/trusts`, minimalTrustPayload, getToken());
      setCreatedTrustId(newTrust.trust_id);
      setSelectedTrust(newTrust);
      await loadTrusts();
      setSkipDocument(true);
      setStep(3);
    } catch (error) {
      console.error('Skip doc trust creation error:', error);
      showError(toast, error, { operation: 'create_trust', page: 'Onboarding' });
    } finally {
      setLoading(false);
    }
  };

  // Confirm details from OnboardingConfirmStep - update the trust with confirmed data
  const handleConfirmDetails = async () => {
    if (!trustData.name.trim()) {
      toast.error('Please enter your trust name before continuing.');
      return;
    }
    if (!trustData.jurisdiction) {
      toast.error('Please select your state so we can set up the correct compliance rules for your trust.');
      return;
    }
    if (!createdTrustId) {
      toast.error('Something went wrong. Please go back and try again.');
      setStep(1);
      return;
    }

    const month = Number(trustData.tax_year_end_month);
    const day = Number(trustData.tax_year_end_day);
    const computedFiscalYear = (month !== 12 || day !== 31);

    setLoading(true);

    try {
      // Send trustees as a JSON array, NOT a comma-joined string.
      // This fixes the bug where "Smith, Jr." gets split into two trustees.
      const filteredTrusteeNames = trusteeNames.filter(n => n.trim());
      const payload = {
        name: trustData.name,
        trust_type: trustData.trust_type,
        jurisdiction: trustData.jurisdiction,
        role: trustData.role,
        review_cadence: trustData.review_cadence,
        description: trustData.description || '',
        ein: trustData.ein || '',
        start_date: trustData.start_date || '',
        tax_year_end_month: month,
        tax_year_end_day: day,
        is_fiscal_year: computedFiscalYear,
        grantor_name: trustData.grantor_name || '',
        trustees: filteredTrusteeNames,
      };

      await xhrRequest('PUT', `${API_URL}/api/trusts/${createdTrustId}`, payload, getToken());

      await loadTrusts();
      setCreatedTrustName(trustData.name);
      setStep(4);
    } catch (error) {
      console.error('Confirm details error:', error);
      showError(toast, error, { operation: 'update_trust', page: 'Onboarding' });
    } finally {
      setLoading(false);
    }
  };

  const handleSeedDemo = async () => {
    setLoading(true);
    try {
      const result = await xhrRequest('POST', `${API_URL}/api/demo/seed`, null, getToken());

      if (result?.seeded) {
        await loadTrusts();
        toast.success('Demo data loaded!');
        setStep(4); // Skip to welcome
      } else {
        toast.info(result?.message || 'Demo data already exists');
        navigate('/dashboard');
      }
    } catch (error) {
      console.error('Seed demo error:', error);
      showError(toast, error, { operation: 'seed_demo_data', page: 'Onboarding' });
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const file = e.dataTransfer.files[0];
    if (file) {
      const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain', 'image/png', 'image/jpeg', 'image/jpg'];
      if (!allowedTypes.includes(file.type) && !file.name.toLowerCase().match(/\.(pdf|doc|docx|txt|png|jpg|jpeg)$/)) {
        toast.error('Please upload a PDF, Word document, or text file');
        return;
      }
      if (file.size > 16 * 1024 * 1024) {
        toast.error('File is too large. Maximum size is 16MB.');
        return;
      }
      setTrustDoc(file);
      setDocUploaded(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  return (
    <div className="min-h-screen bg-subtle-bg" data-testid="onboarding-page">
      {/* Header */}
      <div className="bg-navy text-white py-4 px-8">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <img
            src="/assets/trustoffice-logo-vertical.svg"
            alt="TrustOffice"
            className="h-8"
          />
          <span className="font-mono text-[10px] uppercase tracking-widest text-white/60">
            {step <= totalSteps ? stepNames[step - 1] : 'Getting Started'}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      {step <= totalSteps && (
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
            Step {step} of {totalSteps}
          </p>
        </div>
      )}

      {/* Content */}
      <div className="max-w-3xl mx-auto px-8 pb-16">

        {/* EXPIRED SUBSCRIPTION - Show upgrade options */}
        {isSubscriptionExpired && step === 1 && (
          <div className="mt-8">
            <div className="card-trust corner-mark mb-8">
              <div className="text-center mb-8">
                <div className="w-16 h-16 bg-warning/10 dark:bg-warning/20 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Clock className="w-8 h-8 text-warning" />
                </div>
                <h1 className="font-serif text-4xl text-navy mb-3">
                  Your Free Access Has Ended
                </h1>
                <p className="text-lg text-muted-foreground max-w-xl mx-auto">
                  Subscribe now to continue using TrustOffice and manage your trusts professionally.
                </p>
              </div>

              <div className="bg-navy/5 border border-navy/10 p-6 mb-8">
                <p className="font-medium text-navy mb-4">What you get with TrustOffice:</p>
                <div className="grid md:grid-cols-2 gap-3">
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                    <span>Up to 10 trusts & entities</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                    <span>AI-powered minutes generation</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                    <span>Defensibility tracking</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                    <span>PDF generation & exports</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                    <span>Distribution management</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                    <span>Beneficiary tracking</span>
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-4">
                <Button
                  onClick={() => navigate('/pricing')}
                  className="btn-primary w-full py-6 text-lg"
                  data-testid="subscribe-now-cta"
                >
                  <CreditCard className="w-5 h-5 mr-2" />
                  Subscribe Now - Starting at $79/month
                </Button>

                <div className="text-center">
                  <p className="text-sm text-muted-foreground mb-2">Save 17% with annual billing</p>
                </div>

                <div className="border-t border-border pt-4 mt-2">
                  <p className="text-xs text-muted-foreground text-center mb-3">
                    Your data is safe. You can view everything in read-only mode.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      localStorage.setItem('skip_onboarding', 'true');
                      navigate('/dashboard');
                    }}
                    className="w-full"
                    data-testid="view-readonly-btn"
                  >
                    Continue in Read-Only Mode
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* STEP 1: Document Upload */}
        {step === 1 && !isSubscriptionExpired && (
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
                      <p className="text-sm text-muted-foreground">PDF, Word document, or text file (max 16MB)</p>
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
                  <div className="flex items-center justify-center gap-2 py-4">
                    <Loader2 className="w-5 h-5 text-navy animate-spin" />
                    <span className="text-sm text-muted-foreground">{uploadProgress}</span>
                  </div>
                )}

                {/* Skip option - for users without a digitized document */}
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

              {/* Demo data option - secondary, below the form */}
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
        )}

        {/* STEP 2: AI Analyzing */}
        {step === 2 && (
          <div className="mt-8">
            <button
              onClick={() => {
                stopPolling();
                resetPolling();
                setTrustDoc(null);
                setDocUploaded(false);
                setStep(1);
              }}
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

                    {/* Cycling progress hints */}
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
                        onClick={() => {
                          resetPolling();
                          stopPolling();
                          setStep(1);
                          setDocUploaded(false);
                          setTrustDoc(null);
                        }}
                        className="btn-primary h-12"
                        data-testid="retry-upload-btn"
                      >
                        <Upload className="w-5 h-5 mr-2" />
                        Try Again - Re-upload
                      </Button>
                      <Button
                        onClick={() => {
                          stopPolling();
                          resetPolling();
                          setSkipDocument(true);
                          setStep(3);
                        }}
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
        {step === 4 && (
          <div className="mt-8">
            <div className="card-trust corner-mark text-center mb-8">
              <div className="w-16 h-16 bg-success/10 flex items-center justify-center mx-auto mb-6 rounded-full">
                <CheckCircle2 className="w-8 h-8 text-success" />
              </div>

              <h1 className="font-serif text-3xl text-navy mb-2">
                {createdTrustName ? `${createdTrustName} is Ready!` : "You're All Set!"}
              </h1>
              <p className="text-muted-foreground mb-8">
                Your trust is created. Head to your dashboard to see your next steps.
              </p>

              <div className="text-left mb-8">
                <h3 className="text-xl font-serif text-navy dark:text-foreground mb-2">You're all set!</h3>
                <p className="text-muted-foreground mb-4">Your dashboard will guide you through the next steps to get your trust fully configured.</p>
                <Link to="/dashboard" className="btn-primary inline-flex items-center gap-2 h-12 px-6 text-base">
                  Go to Dashboard <ArrowRight className="w-4 h-4" />
                </Link>
              </div>

              <div className="bg-navy/5 border border-navy/10 p-4 mb-6">
                <p className="text-sm text-navy text-left">
                  <strong>Tip:</strong> You can also explore the app with demo data to see all features in action. Demo data is separate from your real trust and can be deleted anytime in Settings.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}