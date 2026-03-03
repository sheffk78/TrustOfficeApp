import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { 
  ArrowRight, 
  ArrowLeft, 
  Building2, 
  Sparkles, 
  FileText, 
  DollarSign, 
  Users, 
  Shield, 
  Calendar,
  CheckCircle2,
  LayoutDashboard,
  ClipboardList,
  HeartHandshake,
  FolderTree,
  PieChart
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

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
            reject(new Error(response.detail || `Request failed`));
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

// Feature cards for the tour
const FEATURES = [
  {
    icon: FileText,
    title: 'Meeting Minutes',
    description: 'Generate professional trustee meeting minutes with AI assistance. Choose from 25+ templates for distributions, asset changes, and governance decisions.',
    color: 'navy'
  },
  {
    icon: ClipboardList,
    title: 'Schedule A Tracking',
    description: 'Maintain a complete inventory of trust assets. Track acquisitions, dispositions, and current valuations all in one place.',
    color: 'navy'
  },
  {
    icon: DollarSign,
    title: 'Distributions',
    description: 'Record and approve beneficiary distributions with proper documentation. Track HEMS compliance and maintain audit trails.',
    color: 'navy'
  },
  {
    icon: Users,
    title: 'Beneficiary Management',
    description: 'Issue unit certificates, track beneficial interests, and maintain transfer histories for all trust beneficiaries.',
    color: 'navy'
  },
  {
    icon: Shield,
    title: 'Governance Health',
    description: 'Monitor your trust administration with a governance score. Get alerts for overdue reviews and compliance tasks.',
    color: 'navy'
  },
  {
    icon: HeartHandshake,
    title: 'Benevolence Tracking',
    description: 'For charitable trusts: track grants, document approvals, and maintain records of benevolent giving.',
    color: 'gold'
  }
];

// Quick start tasks shown after trust creation
const QUICK_START_TASKS = [
  { label: 'Record your first meeting minutes', path: '/guided-minutes', icon: FileText },
  { label: 'Add assets to Schedule A', path: '/schedule-a', icon: ClipboardList },
  { label: 'Set up beneficiaries', path: '/beneficiaries', icon: Users },
  { label: 'Review governance tasks', path: '/governance', icon: Shield }
];

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { user, trusts, loadTrusts, setSelectedTrust } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [checkingTrusts, setCheckingTrusts] = useState(true);
  const [createdTrustName, setCreatedTrustName] = useState('');
  
  const [trustData, setTrustData] = useState({
    name: '',
    trust_type: 'family',
    jurisdiction: '',
    role: 'Trustee',
    review_cadence: 'quarterly',
    description: ''
  });

  const getToken = () => localStorage.getItem('auth_token');

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
    if (!checkingTrusts && trusts && trusts.length > 0) {
      navigate('/dashboard', { replace: true });
    }
  }, [checkingTrusts, trusts, navigate]);

  if (checkingTrusts) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const handleCreateTrust = async () => {
    if (!trustData.name.trim()) {
      toast.error('Trust name is required');
      return;
    }

    setLoading(true);

    try {
      const newTrust = await xhrRequest('POST', `${API_URL}/api/trusts`, trustData, getToken());
      
      setSelectedTrust(newTrust);
      await loadTrusts();
      setCreatedTrustName(trustData.name);

      toast.success('Trust created successfully');
      setStep(4); // Go to quick start
    } catch (error) {
      console.error('Create trust error:', error);
      toast.error(error.message || 'Failed to create trust');
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
        toast.success('Demo data loaded successfully!');
        setStep(5); // Go to demo welcome
      } else {
        toast.info(result?.message || 'Demo data already exists');
        navigate('/dashboard');
      }
    } catch (error) {
      console.error('Seed demo error:', error);
      toast.error(error.message || 'Failed to create demo data');
    } finally {
      setLoading(false);
    }
  };

  // Step names for progress indicator
  const stepNames = ['Welcome', 'Features', 'Setup', 'Start'];
  const totalSteps = 4;

  return (
    <div className="min-h-screen bg-subtle-bg" data-testid="onboarding-page">
      {/* Header */}
      <div className="bg-navy text-white py-4 px-8">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <img 
            src="https://customer-assets.emergentagent.com/job_98ad4c89-4a05-4aed-ab1d-a934650bd7f4/artifacts/5h7i559r_Trust%20Office%20Logo%20%281%29.svg"
            alt="TrustOffice"
            className="h-8 brightness-0 invert"
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
        
        {/* STEP 1: Welcome */}
        {step === 1 && (
          <div className="mt-8">
            <div className="card-trust corner-mark mb-8">
              <div className="text-center mb-8">
                <h1 className="font-serif text-4xl text-navy mb-3">
                  Welcome to TrustOffice, {user?.name?.split(' ')[0] || 'User'}
                </h1>
                <p className="text-lg text-muted-foreground max-w-xl mx-auto">
                  The governance workspace for trustees who want to manage their trusts with confidence and professionalism.
                </p>
              </div>

              <div className="bg-navy/5 border border-navy/10 p-6 mb-8">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 bg-success/20 rounded-full flex items-center justify-center">
                    <CheckCircle2 className="w-5 h-5 text-success" />
                  </div>
                  <div>
                    <p className="font-medium text-navy">14-Day Free Trial Active</p>
                    <p className="text-sm text-muted-foreground">Full access to all features. No credit card required.</p>
                  </div>
                </div>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                <button 
                  onClick={() => setStep(2)}
                  className="p-6 border border-navy/20 hover:border-navy/40 hover:bg-navy/5 transition-all text-left group"
                  data-testid="see-features-btn"
                >
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 bg-navy/10 flex items-center justify-center group-hover:bg-navy/20 transition-colors">
                      <LayoutDashboard className="w-6 h-6 text-navy" />
                    </div>
                    <div className="flex-1">
                      <h3 className="font-serif text-xl text-navy mb-1">See What's Possible</h3>
                      <p className="text-sm text-muted-foreground">
                        Quick tour of features before you start
                      </p>
                    </div>
                    <ArrowRight className="w-5 h-5 text-navy opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </button>

                <button 
                  onClick={() => setStep(3)}
                  className="p-6 border border-navy/20 hover:border-navy/40 hover:bg-navy/5 transition-all text-left group"
                  data-testid="skip-to-setup-btn"
                >
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 bg-navy/10 flex items-center justify-center group-hover:bg-navy/20 transition-colors">
                      <Building2 className="w-6 h-6 text-navy" />
                    </div>
                    <div className="flex-1">
                      <h3 className="font-serif text-xl text-navy mb-1">I'm Ready to Start</h3>
                      <p className="text-sm text-muted-foreground">
                        Jump straight into setting up your trust
                      </p>
                    </div>
                    <ArrowRight className="w-5 h-5 text-navy opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* STEP 2: Feature Tour */}
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
              <h1 className="font-serif text-3xl text-navy mb-2">What You Can Do</h1>
              <p className="text-muted-foreground mb-8">
                TrustOffice helps you maintain professional trust governance with these key features:
              </p>

              <div className="grid md:grid-cols-2 gap-4 mb-8">
                {FEATURES.map((feature, index) => (
                  <div 
                    key={index}
                    className={`p-4 border ${feature.color === 'gold' ? 'border-gold/30 bg-gold/5' : 'border-navy/10'}`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`w-10 h-10 flex items-center justify-center ${feature.color === 'gold' ? 'bg-gold/20' : 'bg-navy/10'}`}>
                        <feature.icon className={`w-5 h-5 ${feature.color === 'gold' ? 'text-gold' : 'text-navy'}`} />
                      </div>
                      <div className="flex-1">
                        <h3 className="font-medium text-navy mb-1">{feature.title}</h3>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          {feature.description}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex gap-4">
                <Button
                  onClick={() => setStep(3)}
                  className="flex-1 btn-primary h-12"
                  data-testid="continue-to-setup-btn"
                >
                  Continue to Setup
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* STEP 3: Trust Setup / Demo Choice */}
        {step === 3 && (
          <div className="mt-8">
            <button 
              onClick={() => setStep(2)}
              className="flex items-center gap-2 text-muted-foreground hover:text-navy mb-6 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span className="font-mono text-xs uppercase tracking-widest">Back</span>
            </button>

            <div className="card-trust corner-mark mb-6">
              <h1 className="font-serif text-3xl text-navy mb-2">Choose How to Start</h1>
              <p className="text-muted-foreground mb-8">
                You can create your own trust or explore with sample data first.
              </p>

              <div className="grid md:grid-cols-2 gap-6 mb-6">
                {/* Create Trust Option */}
                <div className="border border-navy/20 p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-12 h-12 bg-navy/10 flex items-center justify-center">
                      <Building2 className="w-6 h-6 text-navy" />
                    </div>
                    <div>
                      <h3 className="font-serif text-xl text-navy">Create Your Trust</h3>
                      <p className="text-xs text-muted-foreground">Start fresh with your own data</p>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <Label className="label-trust">Trust Name *</Label>
                      <Input
                        type="text"
                        value={trustData.name}
                        onChange={(e) => setTrustData({ ...trustData, name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., Smith Family Trust"
                        data-testid="trust-name-input"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="label-trust">Type</Label>
                        <Select 
                          value={trustData.trust_type} 
                          onValueChange={(v) => setTrustData({ ...trustData, trust_type: v })}
                        >
                          <SelectTrigger className="mt-1 input-trust">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="family">Family Trust</SelectItem>
                            <SelectItem value="charitable">Charitable</SelectItem>
                            <SelectItem value="business">Business Trust</SelectItem>
                            <SelectItem value="ecclesiastical">Ecclesiastical</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="label-trust">Your Role</Label>
                        <Select 
                          value={trustData.role} 
                          onValueChange={(v) => setTrustData({ ...trustData, role: v })}
                        >
                          <SelectTrigger className="mt-1 input-trust">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Trustee">Trustee</SelectItem>
                            <SelectItem value="Co-Trustee">Co-Trustee</SelectItem>
                            <SelectItem value="Successor Trustee">Successor</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    <div>
                      <Label className="label-trust">Jurisdiction</Label>
                      <Input
                        type="text"
                        value={trustData.jurisdiction}
                        onChange={(e) => setTrustData({ ...trustData, jurisdiction: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., Delaware, Nevada"
                        data-testid="jurisdiction-input"
                      />
                    </div>

                    <Button
                      onClick={handleCreateTrust}
                      className="w-full btn-primary h-11"
                      disabled={loading || !trustData.name.trim()}
                      data-testid="create-trust-btn"
                    >
                      {loading ? 'Creating...' : 'Create Trust'}
                    </Button>
                  </div>
                </div>

                {/* Demo Data Option */}
                <div className="border border-gold/30 bg-gold/5 p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-12 h-12 bg-gold/20 flex items-center justify-center">
                      <Sparkles className="w-6 h-6 text-gold" />
                    </div>
                    <div>
                      <h3 className="font-serif text-xl text-navy">Explore with Demo</h3>
                      <p className="text-xs text-muted-foreground">See the app with sample data</p>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="text-sm text-muted-foreground space-y-2">
                      <p className="font-medium text-navy">Demo includes:</p>
                      <ul className="space-y-1 ml-4">
                        <li className="flex items-center gap-2">
                          <CheckCircle2 className="w-3 h-3 text-success" />
                          <span>2 sample trusts with full data</span>
                        </li>
                        <li className="flex items-center gap-2">
                          <CheckCircle2 className="w-3 h-3 text-success" />
                          <span>Meeting minutes & templates</span>
                        </li>
                        <li className="flex items-center gap-2">
                          <CheckCircle2 className="w-3 h-3 text-success" />
                          <span>Assets, distributions & more</span>
                        </li>
                        <li className="flex items-center gap-2">
                          <CheckCircle2 className="w-3 h-3 text-success" />
                          <span>Beneficiaries with unit certificates</span>
                        </li>
                      </ul>
                    </div>

                    <div className="bg-white/50 border border-gold/20 p-3">
                      <p className="text-xs text-muted-foreground">
                        <strong className="text-navy">Easy to remove:</strong> Demo data can be deleted anytime in Settings without affecting any trusts you create.
                      </p>
                    </div>

                    <Button
                      onClick={handleSeedDemo}
                      className="w-full btn-gold h-11"
                      disabled={loading}
                      data-testid="load-demo-btn"
                    >
                      {loading ? 'Loading...' : 'Load Demo Data'}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* STEP 4: Quick Start (after creating own trust) */}
        {step === 4 && (
          <div className="mt-8">
            <div className="card-trust corner-mark text-center mb-8">
              <div className="w-16 h-16 bg-success/10 flex items-center justify-center mx-auto mb-6 rounded-full">
                <CheckCircle2 className="w-8 h-8 text-success" />
              </div>

              <h1 className="font-serif text-3xl text-navy mb-2">
                {createdTrustName || 'Your Trust'} is Ready!
              </h1>
              <p className="text-muted-foreground mb-8">
                Here's how to get the most out of TrustOffice
              </p>

              <div className="text-left mb-8">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
                  Recommended First Steps
                </p>
                <div className="space-y-3">
                  {QUICK_START_TASKS.map((task, index) => (
                    <button
                      key={index}
                      onClick={() => navigate(task.path)}
                      className="w-full p-4 border border-navy/10 hover:border-navy/30 hover:bg-navy/5 transition-all flex items-center gap-4 text-left group"
                    >
                      <div className="w-8 h-8 bg-navy/10 flex items-center justify-center group-hover:bg-navy/20 transition-colors">
                        <task.icon className="w-4 h-4 text-navy" />
                      </div>
                      <span className="flex-1 text-sm text-navy">{task.label}</span>
                      <ArrowRight className="w-4 h-4 text-navy opacity-0 group-hover:opacity-100 transition-opacity" />
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex gap-4">
                <Button
                  onClick={() => navigate('/dashboard')}
                  className="flex-1 btn-primary h-12"
                  data-testid="go-to-dashboard-btn"
                >
                  Go to Dashboard
                </Button>
                <Button
                  onClick={() => navigate('/guided-minutes')}
                  variant="outline"
                  className="flex-1 btn-secondary h-12"
                >
                  Create First Minutes
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* STEP 5: Demo Welcome (after loading demo data) */}
        {step === 5 && (
          <div className="mt-8">
            <div className="card-trust corner-mark mb-8">
              <div className="text-center mb-8">
                <div className="w-16 h-16 bg-gold/20 flex items-center justify-center mx-auto mb-6 rounded-full">
                  <Sparkles className="w-8 h-8 text-gold" />
                </div>

                <h1 className="font-serif text-3xl text-navy mb-2">
                  Demo Data Loaded!
                </h1>
                <p className="text-muted-foreground max-w-lg mx-auto">
                  Explore the Smith Family Trust and Johnson Education Trust to see all features in action.
                </p>
              </div>

              <div className="bg-navy/5 border border-navy/10 p-6 mb-8">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
                  What's Included in Demo
                </p>
                <div className="grid md:grid-cols-3 gap-4 text-center">
                  <div className="p-3">
                    <p className="font-mono text-2xl text-navy">2</p>
                    <p className="text-xs text-muted-foreground">Sample Trusts</p>
                  </div>
                  <div className="p-3">
                    <p className="font-mono text-2xl text-navy">12+</p>
                    <p className="text-xs text-muted-foreground">Meeting Minutes</p>
                  </div>
                  <div className="p-3">
                    <p className="font-mono text-2xl text-navy">11</p>
                    <p className="text-xs text-muted-foreground">Schedule A Assets</p>
                  </div>
                </div>
              </div>

              <div className="text-left mb-8">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
                  Try These Features
                </p>
                <div className="grid md:grid-cols-2 gap-3">
                  <button
                    onClick={() => navigate('/dashboard')}
                    className="p-4 border border-navy/10 hover:border-navy/30 transition-all flex items-center gap-3 text-left"
                  >
                    <PieChart className="w-5 h-5 text-navy" />
                    <div>
                      <p className="text-sm font-medium text-navy">Dashboard</p>
                      <p className="text-xs text-muted-foreground">See governance health score</p>
                    </div>
                  </button>
                  <button
                    onClick={() => navigate('/minutes')}
                    className="p-4 border border-navy/10 hover:border-navy/30 transition-all flex items-center gap-3 text-left"
                  >
                    <FileText className="w-5 h-5 text-navy" />
                    <div>
                      <p className="text-sm font-medium text-navy">Minutes</p>
                      <p className="text-xs text-muted-foreground">View sample meeting records</p>
                    </div>
                  </button>
                  <button
                    onClick={() => navigate('/schedule-a')}
                    className="p-4 border border-navy/10 hover:border-navy/30 transition-all flex items-center gap-3 text-left"
                  >
                    <ClipboardList className="w-5 h-5 text-navy" />
                    <div>
                      <p className="text-sm font-medium text-navy">Schedule A</p>
                      <p className="text-xs text-muted-foreground">Browse trust assets</p>
                    </div>
                  </button>
                  <button
                    onClick={() => navigate('/beneficiaries')}
                    className="p-4 border border-navy/10 hover:border-navy/30 transition-all flex items-center gap-3 text-left"
                  >
                    <Users className="w-5 h-5 text-navy" />
                    <div>
                      <p className="text-sm font-medium text-navy">Beneficiaries</p>
                      <p className="text-xs text-muted-foreground">View unit certificates</p>
                    </div>
                  </button>
                </div>
              </div>

              <div className="bg-gold/10 border border-gold/30 p-4 mb-6">
                <p className="text-sm text-navy">
                  <strong>Tip:</strong> Use the trust selector in the sidebar to switch between the two demo trusts. 
                  The Smith Family Trust has benevolence features enabled.
                </p>
              </div>

              <Button
                onClick={() => navigate('/dashboard')}
                className="w-full btn-gold h-12"
                data-testid="explore-dashboard-btn"
              >
                Start Exploring
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
