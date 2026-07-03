import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { showError, reportErrorToBackend } from '@/utils/errors';
import {
  ArrowRight,
  ArrowLeft,
  Building2,
  CheckCircle2,
  FileText,
  Users,
  Package,
  Calendar,
  ClipboardList,
  Upload,
  Sparkles,
  Lock,
  CreditCard,
  Clock,
  Loader2,
  FileCheck,
  ChevronDown,
  Plus,
  X,
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

// Quick start tasks shown after trust creation + document upload
const QUICK_START_TASKS = [
  { label: 'Set up beneficiaries', path: '/beneficiaries', icon: Users, description: 'Add the people who benefit from your trust' },
  { label: 'Set up your trust structure', path: '/structures', icon: Package, description: 'Add your trust entity and any related LLCs or structures' },
  { label: 'Hold your first trustee meeting', path: '/minutes/create?type=initial_trustee_meeting&from=onboarding', icon: ClipboardList, description: 'Document your acceptance of trusteeship and initial decisions' },
  { label: 'Check your tax calendar', path: '/calendar', icon: Calendar, description: 'See your filing deadlines based on your trust setup' },
];

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { user, trusts, loadTrusts, setSelectedTrust, subscription, subscriptionExpired, loading: authLoading } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [checkingTrusts, setCheckingTrusts] = useState(true);
  const [createdTrustName, setCreatedTrustName] = useState('');
  const [createdTrustId, setCreatedTrustId] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Trust document upload state
  const [trustDoc, setTrustDoc] = useState(null);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [docUploaded, setDocUploaded] = useState(false);
  const fileInputRef = useRef(null);

  const [trustData, setTrustData] = useState({
    name: '',
    trust_type: 'family',
    jurisdiction: '',
    role: 'Trustee',
    review_cadence: 'quarterly',
    description: '',
    ein: '',
    state_code: '',
    tax_year_end_month: '12',
    tax_year_end_day: '31',
    is_fiscal_year: false,
    trustees: ''
  });

  // Trustee names - auto-filled with the signed-up user's name, editable
  // Multiple trustees can be added/removed for trusts with co-trustees
  const [trusteeNames, setTrusteeNames] = useState(['']);

  const getToken = () => localStorage.getItem('auth_token');

  // Check if subscription is inactive
  const isSubscriptionExpired = subscription && !subscription.is_active;
  const isSubscriptionInactive = subscription && !subscription.is_active && subscription.is_trial === false;

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
  }, [user]);

  if (checkingTrusts) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const handleCreateTrust = async () => {
    if (!trustData.name.trim()) {
      toast.error('Please enter your trust name before continuing.');
      return;
    }
    if (!trustData.jurisdiction) {
      toast.error('Please select your state so we can set up the correct compliance rules for your trust.');
      return;
    }

    const month = Number(trustData.tax_year_end_month);
    const day = Number(trustData.tax_year_end_day);
    const computedFiscalYear = (month !== 12 || day !== 31);

    setLoading(true);

    try {
      // Join trustee names into a comma-separated string for the backend
      const filteredTrusteeNames = trusteeNames.filter(n => n.trim());
      const trusteesString = filteredTrusteeNames.join(', ');
      const payload = { ...trustData, trustees: trusteesString, is_fiscal_year: computedFiscalYear };
      const newTrust = await xhrRequest('POST', `${API_URL}/api/trusts`, payload, getToken());

      setSelectedTrust(newTrust);
      await loadTrusts();
      setCreatedTrustName(trustData.name);
      setCreatedTrustId(newTrust.trust_id);

      toast.success('Trust created');
      setStep(2); // Go to document upload
    } catch (error) {
      console.error('Create trust error:', error);
      showError(toast, error, { operation: 'create_trust', page: 'Onboarding' });
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
        setStep(3); // Skip doc upload, go to welcome
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

  const handleDocUpload = async () => {
    if (!trustDoc) return;

    setUploadingDoc(true);
    setUploadProgress('Uploading...');

    try {
      const formData = new FormData();
      formData.append('file', trustDoc);
      formData.append('title', 'Declaration of Trust');
      formData.append('category', 'trust_instrument');

      const token = localStorage.getItem('auth_token');
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);

      let res;
      try {
        res = await fetch(`${API_URL}/api/trusts/${createdTrustId}/vault/upload`, {
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

      setUploadProgress('Analyzing document...');
      setDocUploaded(true);
      toast.success('Trust document uploaded! We are analyzing it now.');
    } catch (error) {
      console.error('Doc upload error:', error);
      showError(toast, error, { operation: 'upload_trust_doc', page: 'Onboarding' });
      setUploadProgress('');
    } finally {
      setUploadingDoc(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const file = e.dataTransfer.files[0];
    if (file) {
      // Reuse the validation logic
      const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'];
      if (!allowedTypes.includes(file.type) && !file.name.toLowerCase().match(/\.(pdf|doc|docx|txt)$/)) {
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

  // Step names for progress indicator
  const stepNames = ['Trust Details', 'Trust Document', 'Welcome'];
  const totalSteps = 3;

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
            {[1, 2, 3].map((s) => (
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

        {/* STEP 1: Trust Setup (for active users) */}
        {step === 1 && !isSubscriptionExpired && (
          <div className="mt-8">
            <div className="card-trust corner-mark mb-8">
              <div className="mb-8">
                <h1 className="font-serif text-4xl text-navy mb-3">
                  Welcome to TrustOffice, {user?.name?.split(' ')[0] || 'there'}
                </h1>
                <p className="text-lg text-muted-foreground">
                  Let's set up your trust. This takes about 2 minutes.
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

              {/* Trust creation form - simplified to 3 required fields */}
              <div className="space-y-5">
                <div>
                  <Label className="label-trust text-sm">Trust Name <span className="text-warning">*</span></Label>
                  <Input
                    type="text"
                    value={trustData.name}
                    onChange={(e) => setTrustData({ ...trustData, name: e.target.value })}
                    className="mt-1.5 input-trust h-11 text-base"
                    placeholder="e.g., Smith Family Trust"
                    data-testid="trust-name-input"
                    autoFocus
                  />
                  <p className="text-xs text-muted-foreground mt-1.5">Enter the name exactly as it appears on your trust document.</p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="label-trust text-sm">Trust Type</Label>
                    <Select
                      value={trustData.trust_type}
                      onValueChange={(v) => setTrustData({ ...trustData, trust_type: v })}
                    >
                      <SelectTrigger className="mt-1.5 input-trust h-11 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="family">Family</SelectItem>
                        <SelectItem value="charitable">Charitable</SelectItem>
                        <SelectItem value="business">Business</SelectItem>
                        <SelectItem value="ecclesiastical">Ecclesiastical</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="label-trust text-sm">State <span className="text-warning">*</span></Label>
                    <select
                      value={trustData.jurisdiction}
                      onChange={(e) => setTrustData({ ...trustData, jurisdiction: e.target.value })}
                      className="mt-1.5 input-trust h-11 text-sm w-full rounded border border-input bg-background px-3 py-2 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
                      data-testid="jurisdiction-input"
                    >
                      <option value="" disabled>Select state</option>
                      <option value="AL">Alabama</option>
                      <option value="AK">Alaska</option>
                      <option value="AZ">Arizona</option>
                      <option value="AR">Arkansas</option>
                      <option value="CA">California</option>
                      <option value="CO">Colorado</option>
                      <option value="CT">Connecticut</option>
                      <option value="DE">Delaware</option>
                      <option value="DC">District of Columbia</option>
                      <option value="FL">Florida</option>
                      <option value="GA">Georgia</option>
                      <option value="HI">Hawaii</option>
                      <option value="ID">Idaho</option>
                      <option value="IL">Illinois</option>
                      <option value="IN">Indiana</option>
                      <option value="IA">Iowa</option>
                      <option value="KS">Kansas</option>
                      <option value="KY">Kentucky</option>
                      <option value="LA">Louisiana</option>
                      <option value="ME">Maine</option>
                      <option value="MD">Maryland</option>
                      <option value="MA">Massachusetts</option>
                      <option value="MI">Michigan</option>
                      <option value="MN">Minnesota</option>
                      <option value="MS">Mississippi</option>
                      <option value="MO">Missouri</option>
                      <option value="MT">Montana</option>
                      <option value="NE">Nebraska</option>
                      <option value="NV">Nevada</option>
                      <option value="NH">New Hampshire</option>
                      <option value="NJ">New Jersey</option>
                      <option value="NM">New Mexico</option>
                      <option value="NY">New York</option>
                      <option value="NC">North Carolina</option>
                      <option value="ND">North Dakota</option>
                      <option value="OH">Ohio</option>
                      <option value="OK">Oklahoma</option>
                      <option value="OR">Oregon</option>
                      <option value="PA">Pennsylvania</option>
                      <option value="RI">Rhode Island</option>
                      <option value="SC">South Carolina</option>
                      <option value="SD">South Dakota</option>
                      <option value="TN">Tennessee</option>
                      <option value="TX">Texas</option>
                      <option value="UT">Utah</option>
                      <option value="VT">Vermont</option>
                      <option value="VA">Virginia</option>
                      <option value="WA">Washington</option>
                      <option value="WV">West Virginia</option>
                      <option value="WI">Wisconsin</option>
                      <option value="WY">Wyoming</option>
                    </select>
                  </div>
                </div>

                {/* Trustee Name(s) - auto-filled with user's name, add/remove for multiple trustees */}
                <div>
                  <Label className="label-trust text-sm">Trustee Name(s)</Label>
                  <p className="text-xs text-muted-foreground mt-1 mb-2">We've pre-filled your name from your account. Update it or add co-trustees if your trust has multiple trustees.</p>
                  <div className="space-y-2">
                    {trusteeNames.map((name, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <Input
                          type="text"
                          value={name}
                          onChange={(e) => {
                            const updated = [...trusteeNames];
                            updated[idx] = e.target.value;
                            setTrusteeNames(updated);
                          }}
                          className="input-trust h-11 text-base"
                          placeholder={idx === 0 ? "Your name (as trustee)" : "Co-trustee name"}
                        />
                        {trusteeNames.length > 1 && (
                          <button
                            type="button"
                            onClick={() => setTrusteeNames(trusteeNames.filter((_, i) => i !== idx))}
                            className="flex-shrink-0 w-9 h-9 flex items-center justify-center text-neutral-400 hover:text-red-500 transition-colors"
                            aria-label="Remove trustee"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => setTrusteeNames([...trusteeNames, ''])}
                    className="flex items-center gap-1.5 text-sm text-navy hover:text-navy/80 mt-2 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Add co-trustee</span>
                  </button>
                </div>

                {/* Advanced settings - collapsible */}
                <div>
                  <button
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="flex items-center gap-1 text-sm text-muted-foreground hover:text-navy transition-colors"
                    type="button"
                  >
                    <ChevronDown className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
                    <span>Advanced settings (tax year end, description)</span>
                  </button>

                  {showAdvanced && (
                    <div className="mt-4 space-y-4 p-4 bg-navy/5 border border-navy/10">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <Label className="label-trust text-xs">Tax Year End - Month</Label>
                          <Select
                            value={trustData.tax_year_end_month}
                            onValueChange={(v) => setTrustData({ ...trustData, tax_year_end_month: v })}
                          >
                            <SelectTrigger className="mt-1 input-trust h-9 text-sm">
                              <SelectValue placeholder="Month" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="12">DEC (Calendar)</SelectItem>
                              <SelectItem value="1">JAN</SelectItem>
                              <SelectItem value="2">FEB</SelectItem>
                              <SelectItem value="3">MAR</SelectItem>
                              <SelectItem value="4">APR</SelectItem>
                              <SelectItem value="5">MAY</SelectItem>
                              <SelectItem value="6">JUN</SelectItem>
                              <SelectItem value="7">JUL</SelectItem>
                              <SelectItem value="8">AUG</SelectItem>
                              <SelectItem value="9">SEP</SelectItem>
                              <SelectItem value="10">OCT</SelectItem>
                              <SelectItem value="11">NOV</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div>
                          <Label className="label-trust text-xs">Day</Label>
                          <Input
                            type="number"
                            min={1}
                            max={31}
                            value={trustData.tax_year_end_day}
                            onChange={(e) => setTrustData({ ...trustData, tax_year_end_day: e.target.value })}
                            className="mt-1 input-trust h-9 text-sm"
                            placeholder="31"
                            data-testid="tax-day-input"
                          />
                        </div>
                      </div>
                      {trustData.tax_year_end_month && trustData.tax_year_end_day &&
                       !(Number(trustData.tax_year_end_month) === 12 && Number(trustData.tax_year_end_day) === 31) && (
                        <p className="text-xs text-muted-foreground">
                          Fiscal year - tax deadlines will be calculated from this date.
                        </p>
                      )}
                      <div>
                        <Label className="label-trust text-xs">Description (optional)</Label>
                        <Input
                          type="text"
                          value={trustData.description}
                          onChange={(e) => setTrustData({ ...trustData, description: e.target.value })}
                          className="mt-1 input-trust h-9 text-sm"
                          placeholder="Brief description of your trust purpose"
                        />
                      </div>
                    </div>
                  )}
                </div>

                <Button
                  onClick={handleCreateTrust}
                  className="w-full btn-primary h-12 text-base"
                  disabled={loading || !trustData.name.trim() || !trustData.jurisdiction}
                  data-testid="create-trust-btn"
                >
                  {loading ? (
                    <><Loader2 className="w-5 h-5 mr-2 animate-spin" /> Creating...</>
                  ) : (
                    <>Continue <ArrowRight className="w-5 h-5 ml-2" /></>
                  )}
                </Button>
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

        {/* STEP 2: Trust Document Upload */}
        {step === 2 && (
          <div className="mt-8">
            <button
              onClick={() => setStep(1)}
              className="flex items-center gap-2 text-muted-foreground hover:text-navy mb-6 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span className="font-mono text-xs uppercase tracking-widest">Back</span>
            </button>

            <div className="card-trust corner-mark mb-8">
              <div className="mb-6">
                <h1 className="font-serif text-3xl text-navy mb-2">
                  Upload Your Trust Document
                </h1>
                <p className="text-muted-foreground">
                  Upload your signed Declaration of Trust and we'll analyze it automatically, extracting key provisions, distribution rules, and trustee powers.
                </p>
              </div>

              {!docUploaded ? (
                <>
                  {/* Drop zone */}
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
                </>
              ) : (
                /* Upload success */
                <div className="text-center py-6">
                  <div className="w-16 h-16 bg-success/10 flex items-center justify-center mx-auto mb-4 rounded-full">
                    <CheckCircle2 className="w-8 h-8 text-success" />
                  </div>
                  <h3 className="font-serif text-xl text-navy mb-2">Document Uploaded!</h3>
                  <p className="text-sm text-muted-foreground mb-1">
                    Your trust document is being analyzed. This takes about 30-60 seconds.
                  </p>
                  <p className="text-sm text-muted-foreground">
                    You can continue setup while it processes in the background.
                  </p>
                </div>
              )}

              {/* Skip option */}
              <div className="mt-6 pt-6 border-t border-navy/10">
                <button
                  onClick={() => setStep(3)}
                  className="w-full text-center text-sm text-muted-foreground hover:text-navy transition-colors py-2"
                  data-testid="skip-doc-upload"
                >
                  {docUploaded ? 'Continue to Dashboard' : "I don't have it digitized - skip for now"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* STEP 3: Welcome / Quick Start */}
        {step === 3 && (
          <div className="mt-8">
            <div className="card-trust corner-mark text-center mb-8">
              <div className="w-16 h-16 bg-success/10 flex items-center justify-center mx-auto mb-6 rounded-full">
                <CheckCircle2 className="w-8 h-8 text-success" />
              </div>

              <h1 className="font-serif text-3xl text-navy mb-2">
                {createdTrustName ? `${createdTrustName} is Ready!` : "You're All Set!"}
              </h1>
              <p className="text-muted-foreground mb-8">
                Here are your recommended next steps, in order:
              </p>

              <div className="text-left mb-8">
                <div className="space-y-3">
                  {QUICK_START_TASKS.map((task, index) => (
                    <button
                      key={index}
                      onClick={() => navigate(task.path)}
                      className="w-full p-4 border border-navy/10 hover:border-navy/30 hover:bg-navy/5 transition-all flex items-center gap-4 text-left group"
                      data-testid={`quick-start-${task.id || index}`}
                    >
                      <div className="w-10 h-10 bg-navy/10 flex items-center justify-center group-hover:bg-navy/20 transition-colors flex-shrink-0">
                        <task.icon className="w-5 h-5 text-navy" />
                      </div>
                      <div className="flex-1">
                        <p className="font-medium text-navy">{task.label}</p>
                        <p className="text-xs text-muted-foreground">{task.description}</p>
                      </div>
                      <ArrowRight className="w-4 h-4 text-navy opacity-0 group-hover:opacity-100 transition-opacity" />
                    </button>
                  ))}
                </div>
              </div>

              <div className="bg-navy/5 border border-navy/10 p-4 mb-6">
                <p className="text-sm text-navy text-left">
                  <strong>Tip:</strong> You can also explore the app with demo data to see all features in action. Demo data is separate from your real trust and can be deleted anytime in Settings.
                </p>
              </div>

              <Button
                onClick={() => navigate('/dashboard')}
                className="w-full btn-primary h-12"
                data-testid="go-to-dashboard-btn"
              >
                Go to Dashboard
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}