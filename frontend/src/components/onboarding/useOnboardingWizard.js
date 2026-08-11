import { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useAnalysisPolling } from '@/hooks/useAnalysisPolling';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import { xhrRequest } from './xhrRequest';
import { validateDocFile } from './docValidation';
import {
  API_URL,
  INITIAL_TRUST_DATA,
} from './onboardingConstants';

/**
 * Custom hook that manages the multi-step onboarding wizard:
 *  - step navigation (1→2→3→4)
 *  - trust creation (via doc upload or manual skip)
 *  - trust detail confirmation
 *  - demo data seeding
 *  - analysis polling coordination
 */
export function useOnboardingWizard() {
  const navigate = useNavigate();
  const { user, trusts, loadTrusts, setSelectedTrust, subscription } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [checkingTrusts, setCheckingTrusts] = useState(true);
  const [createdTrustId, setCreatedTrustId] = useState('');
  const [createdTrustName, setCreatedTrustName] = useState('');
  const [trustDoc, setTrustDoc] = useState(null);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [docUploaded, setDocUploaded] = useState(false);
  const [skipDocument, setSkipDocument] = useState(false);
  const initialTrustCheckDone = useRef(false);
  const fileInputRef = useRef(null);

  const [trustData, setTrustData] = useState(INITIAL_TRUST_DATA);
  const [trusteeNames, setTrusteeNames] = useState(['']);

  const getToken = () => localStorage.getItem('auth_token');
  const isSubscriptionExpired = subscription && !subscription.is_active;

  const { extractedFields, error: analysisError, start: startPolling, stop: stopPolling, reset: resetPolling } = useAnalysisPolling(createdTrustId, {
    onComplete: () => setStep(3),
    onError: (errMsg) => console.error('Analysis failed:', errMsg),
  });

  const goToStep = useCallback((s) => setStep(s), []);

  const resetAnalysisState = useCallback(() => {
    stopPolling();
    resetPolling();
    setTrustDoc(null);
    setDocUploaded(false);
  }, [stopPolling, resetPolling]);

  /** Create the minimal trust shell before uploading or skipping the document. */
  const createMinimalTrust = useCallback(async () => {
    const payload = {
      name: 'My Trust',
      trust_type: 'revocable_living',
      jurisdiction: '',
      trustees: user?.name ? [user.name] : [],
    };
    const newTrust = await xhrRequest('POST', `${API_URL}/api/trusts`, payload, getToken());
    setCreatedTrustId(newTrust.trust_id);
    setSelectedTrust(newTrust);
    await loadTrusts();
    return newTrust;
  }, [user, setSelectedTrust, loadTrusts]);

  /** Upload the selected trust document to the newly created trust's vault. */
  const uploadTrustDocument = useCallback(async (trustId, file) => {
    setUploadProgress('Uploading document...');
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', 'Declaration of Trust');
    formData.append('category', 'trust_instrument');

    const token = localStorage.getItem('auth_token');
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120000);

    let res;
    try {
      res = await fetch(`${API_URL}/api/trusts/${trustId}/vault/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
        signal: controller.signal,
      });
    } catch (fetchError) {
      clearTimeout(timeoutId);
      if (fetchError.name === 'AbortError') throw new Error('Upload timed out. Please try again.');
      throw new Error('Could not reach the server. Check your connection and try again.');
    }
    clearTimeout(timeoutId);

    if (!res.ok) {
      let errorMsg = 'Upload failed';
      try {
        const errData = await res.json();
        errorMsg = errData.detail || errorMsg;
      } catch {
        errorMsg = `Upload failed (${res.status})`;
      }
      throw new Error(errorMsg);
    }
    return res;
  }, []);

  /** Full document-first flow: create trust → upload doc → start analysis polling. */
  const handleDocUpload = useCallback(async () => {
    if (!trustDoc) return;
    setUploadingDoc(true);
    setUploadProgress('Creating trust...');
    stopPolling();
    resetPolling();

    try {
      const newTrust = await createMinimalTrust();
      await uploadTrustDocument(newTrust.trust_id, trustDoc);
      setDocUploaded(true);
      toast.success('Trust document uploaded! We are analyzing it now.');
      setStep(2);
      startPolling();
    } catch (error) {
      console.error('Doc upload error:', error);
      showError(toast, error, { operation: 'upload_trust_doc', page: 'Onboarding' });
      setUploadProgress('');
    } finally {
      setUploadingDoc(false);
    }
  }, [trustDoc, createMinimalTrust, uploadTrustDocument, stopPolling, resetPolling, startPolling]);

  /** Skip the document and go straight to manual entry. */
  const handleSkipDoc = useCallback(async () => {
    setLoading(true);
    try {
      await createMinimalTrust();
      setSkipDocument(true);
      setStep(3);
    } catch (error) {
      console.error('Skip doc trust creation error:', error);
      showError(toast, error, { operation: 'create_trust', page: 'Onboarding' });
    } finally {
      setLoading(false);
    }
  }, [createMinimalTrust]);

  /** Confirm the trust details from step 3 (OnboardingConfirmStep). */
  const handleConfirmDetails = useCallback(async () => {
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
        successor_trustee_name: trustData.successor_trustee_name || '',
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
  }, [trustData, createdTrustId, trusteeNames, loadTrusts]);

  /** Seed demo data for exploration. */
  const handleSeedDemo = useCallback(async () => {
    setLoading(true);
    try {
      const result = await xhrRequest('POST', `${API_URL}/api/demo/seed`, null, getToken());
      if (result?.seeded) {
        await loadTrusts();
        toast.success('Demo data loaded!');
        setStep(4);
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
  }, [loadTrusts, navigate]);

  /** File selection from input change. */
  const handleDocSelect = useCallback((e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!validateDocFile(file)) return;
    setTrustDoc(file);
    setDocUploaded(false);
  }, []);

  /** File drop handler for drag-and-drop zone. */
  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!validateDocFile(file)) return;
    setTrustDoc(file);
    setDocUploaded(false);
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  return {
    // context
    user, trusts, subscription, isSubscriptionExpired,
    loadTrusts, navigate,
    // step state
    step, setStep, goToStep,
    loading, setLoading,
    checkingTrusts, setCheckingTrusts,
    createdTrustId, createdTrustName,
    skipDocument, setSkipDocument,
    initialTrustCheckDone,
    // doc state
    trustDoc, setTrustDoc,
    uploadingDoc, uploadProgress,
    docUploaded, setDocUploaded,
    fileInputRef,
    // trust form state
    trustData, setTrustData,
    trusteeNames, setTrusteeNames,
    // analysis
    extractedFields, analysisError,
    startPolling, stopPolling, resetPolling, resetAnalysisState,
    // handlers
    handleDocUpload, handleSkipDoc, handleConfirmDetails, handleSeedDemo,
    handleDocSelect, handleDrop, handleDragOver,
  };
}
