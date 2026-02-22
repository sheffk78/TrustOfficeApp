import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import { ArrowRight, ArrowLeft, Building2, User, Calendar } from 'lucide-react';

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { user, loadTrusts, seedDemoData, setSelectedTrust } = useAuth();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  
  const [trustData, setTrustData] = useState({
    name: '',
    role: 'Trustee',
    review_cadence: 'quarterly',
    description: ''
  });

  const handleCreateTrust = async () => {
    if (!trustData.name.trim()) {
      toast.error('Trust name is required');
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API}/trusts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(trustData)
      });

      if (!response.ok) {
        throw new Error('Failed to create trust');
      }

      const newTrust = await response.json();
      
      // Load trusts and select the new one
      await loadTrusts();
      setSelectedTrust(newTrust);

      toast.success('Trust created successfully');
      setStep(3);
    } catch (error) {
      toast.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSeedDemo = async () => {
    setLoading(true);
    try {
      await seedDemoData();
      await loadTrusts();
      toast.success('Demo data created');
      navigate('/dashboard');
    } catch (error) {
      toast.error('Failed to create demo data');
    } finally {
      setLoading(false);
    }
  };

  const handleSkipToDemo = async () => {
    setLoading(true);
    try {
      await seedDemoData();
      await loadTrusts();
      toast.success('Welcome to TrustOffice');
      navigate('/dashboard');
    } catch (error) {
      toast.error('Failed to setup');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-subtle-bg" data-testid="onboarding-page">
      {/* Header */}
      <div className="bg-navy text-white py-4 px-8">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <img 
            src="https://customer-assets.emergentagent.com/job_98ad4c89-4a05-4aed-ab1d-a934650bd7f4/artifacts/5h7i559r_Trust%20Office%20Logo%20%281%29.svg"
            alt="TrustOffice"
            className="h-8 brightness-0 invert"
          />
          <span className="font-mono text-[10px] uppercase tracking-widest text-white/60">
            Getting Started
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="max-w-2xl mx-auto px-8 pt-8">
        <div className="wizard-steps">
          <div className={`wizard-step ${step >= 1 ? 'active' : ''} ${step > 1 ? 'completed' : ''}`}></div>
          <div className={`wizard-step ${step >= 2 ? 'active' : ''} ${step > 2 ? 'completed' : ''}`}></div>
          <div className={`wizard-step ${step >= 3 ? 'active' : ''}`}></div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-2xl mx-auto px-8 pb-16">
        {step === 1 && (
          <div className="card-trust corner-mark">
            <h1 className="font-serif text-3xl text-navy mb-2">Welcome, {user?.name || 'User'}</h1>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground mb-8">
              Let's set up your first trust
            </p>

            <div className="space-y-6">
              <div className="p-6 border border-navy/10 hover-lift cursor-pointer" onClick={() => setStep(2)}>
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 bg-navy/5 flex items-center justify-center">
                    <Building2 className="w-6 h-6 text-navy" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-serif text-xl text-navy mb-1">Create New Trust</h3>
                    <p className="text-sm text-muted-foreground">
                      Set up a trust from scratch with your own details
                    </p>
                  </div>
                  <ArrowRight className="w-5 h-5 text-navy" />
                </div>
              </div>

              <div className="p-6 border border-gold/30 bg-gold/5 hover-lift cursor-pointer" onClick={handleSkipToDemo}>
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 bg-gold/20 flex items-center justify-center">
                    <User className="w-6 h-6 text-gold" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-serif text-xl text-navy mb-1">Use Demo Data</h3>
                    <p className="text-sm text-muted-foreground">
                      Explore TrustOffice with sample trust data
                    </p>
                  </div>
                  <ArrowRight className="w-5 h-5 text-gold" />
                </div>
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="card-trust corner-mark">
            <button 
              onClick={() => setStep(1)}
              className="flex items-center gap-2 text-muted-foreground hover:text-navy mb-6"
            >
              <ArrowLeft className="w-4 h-4" />
              <span className="font-mono text-xs uppercase tracking-widest">Back</span>
            </button>

            <h1 className="font-serif text-3xl text-navy mb-2">Trust Details</h1>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground mb-8">
              Basic information about your trust
            </p>

            <div className="space-y-6">
              <div>
                <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Trust Name *
                </Label>
                <div className="relative mt-1">
                  <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    type="text"
                    value={trustData.name}
                    onChange={(e) => setTrustData({ ...trustData, name: e.target.value })}
                    className="pl-10 input-trust"
                    placeholder="Smith Family Trust"
                    data-testid="trust-name-input"
                  />
                </div>
              </div>

              <div>
                <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Your Role
                </Label>
                <Select 
                  value={trustData.role} 
                  onValueChange={(value) => setTrustData({ ...trustData, role: value })}
                >
                  <SelectTrigger className="mt-1 input-trust" data-testid="role-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Trustee">Trustee</SelectItem>
                    <SelectItem value="Co-Trustee">Co-Trustee</SelectItem>
                    <SelectItem value="Successor Trustee">Successor Trustee</SelectItem>
                    <SelectItem value="Trust Protector">Trust Protector</SelectItem>
                    <SelectItem value="Beneficiary">Beneficiary</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Review Cadence
                </Label>
                <Select 
                  value={trustData.review_cadence} 
                  onValueChange={(value) => setTrustData({ ...trustData, review_cadence: value })}
                >
                  <SelectTrigger className="mt-1 input-trust" data-testid="cadence-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="monthly">Monthly</SelectItem>
                    <SelectItem value="quarterly">Quarterly</SelectItem>
                    <SelectItem value="annual">Annual</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Description (Optional)
                </Label>
                <Textarea
                  value={trustData.description}
                  onChange={(e) => setTrustData({ ...trustData, description: e.target.value })}
                  className="mt-1 input-trust min-h-[100px]"
                  placeholder="Brief description of the trust's purpose..."
                  data-testid="trust-description-input"
                />
              </div>

              <Button
                onClick={handleCreateTrust}
                className="w-full btn-primary h-12"
                disabled={loading}
                data-testid="create-trust-btn"
              >
                {loading ? 'Creating...' : 'Create Trust'}
              </Button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="card-trust corner-mark text-center">
            <div className="w-16 h-16 bg-success/10 flex items-center justify-center mx-auto mb-6">
              <svg className="w-8 h-8 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>

            <h1 className="font-serif text-3xl text-navy mb-2">Trust Created</h1>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground mb-8">
              {trustData.name} is ready to use
            </p>

            <div className="space-y-4">
              <Button
                onClick={() => navigate('/dashboard')}
                className="w-full btn-gold h-12"
                data-testid="go-to-dashboard-btn"
              >
                Go to Dashboard
              </Button>

              <Button
                onClick={handleSeedDemo}
                variant="outline"
                className="w-full btn-secondary h-12"
                disabled={loading}
              >
                Add Sample Data
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
