import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { 
  FileText, 
  DollarSign,
  Receipt,
  Calendar,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Circle,
  X,
  Zap,
  TrendingUp,
  Building2,
  Wallet,
  Package,
  UserPlus,
  Landmark,
  PlusCircle,
  Sparkles,
  ChevronRight,
  Loader2,
  Bot,
  CalendarDays,
  Clock,
  CalendarCheck,
  FileCheck,
  FileUp,
  Upload,
  Users,
  ClipboardList
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import PageHelpButton from '@/components/PageHelpButton';
import { TrustManager } from '@/components/TrustManager';

const QUICK_ACTIONS = [
  {
    title: 'Record Distribution',
    description: 'Document a distribution to beneficiaries',
    icon: DollarSign,
    path: '/minutes/template/distribution_to_beneficiaries',
    color: 'bg-success/10 text-success'
  },
  {
    title: 'Add Asset to Trust',
    description: 'Accept property and update Schedule A',
    icon: PlusCircle,
    path: '/minutes/template/acceptance_of_property',
    color: 'bg-blue-500/10 text-blue-600'
  },
  {
    title: 'Open Bank Account',
    description: 'Authorize a new trust bank account',
    icon: Landmark,
    path: '/minutes/template/bank_account_authorization',
    color: 'bg-purple-500/10 text-purple-600'
  },
  {
    title: 'Appoint Trustee',
    description: 'Add or replace a trustee',
    icon: UserPlus,
    path: '/minutes/template/appointment_additional_trustee',
    color: 'bg-orange-500/10 text-orange-600'
  },
  {
    title: 'View Schedule A',
    description: 'Manage trust assets and corpus',
    icon: Package,
    path: '/schedule-a',
    color: 'bg-navy/10 text-navy'
  },
  {
    title: 'General Meeting',
    description: 'Record a trustee meeting',
    icon: FileText,
    path: '/minutes/template/general_meeting',
    color: 'bg-gold/20 text-gold'
  }
];

// Map insight types to icons
const INSIGHT_ICONS = {
  'Quarterly Minutes': FileText,
  'Task Compliance': Calendar,
  'Compensation Alignment': Wallet,
  'Distribution Documentation': DollarSign,
  'Annual Review': TrendingUp,
  'Asset Valuation Freshness': Package
};

export default function DashboardPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, selectedTrust, trusts, trustsLoading, loadTrusts, seedDemoData } = useAuth();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Tax Calendar dashboard state
  const [taxDeadlines, setTaxDeadlines] = useState([]);
  const [taxDeadlinesLoading, setTaxDeadlinesLoading] = useState(false);
  
  // AI Suggestions state
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [aiSuggestionsLoading, setAiSuggestionsLoading] = useState(false);
  const [aiSuggestionsError, setAiSuggestionsError] = useState(false);
  const [aiSuggestionsFallback, setAiSuggestionsFallback] = useState(false); // True when using static fallback

  // Show welcome toast after successful purchase
  useEffect(() => {
    if (searchParams.get('welcome') === 'true') {
      toast.success('Welcome to TrustOffice!', {
        description: 'Your subscription is now active. Let\'s get your trust organized.',
        duration: 6000
      });
      // Remove the query param to prevent showing again on refresh
      searchParams.delete('welcome');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (trustsLoading) return;
    if (selectedTrust) {
      loadDashboardData();
      loadAiSuggestions();
      loadTaxDeadlines();
    } else {
      // No trust selected — stop loading to prevent blank screen
      setLoading(false);
    }
  }, [selectedTrust, trusts, trustsLoading]);

  const loadDashboardData = async () => {
    if (!selectedTrust) {
      setLoading(false);
      return;
    }
    
    setLoading(true);
    try {
      // Single unified API call with trust_id parameter
      const response = await fetchWithAuth(`/dashboard?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        const data = await response.json();
        setDashboard(data);
      } else {
        console.error('Failed to load dashboard');
      }
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Load upcoming tax deadlines for dashboard widget
  const loadTaxDeadlines = async () => {
    if (!selectedTrust) return;
    setTaxDeadlinesLoading(true);
    try {
      const response = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/tax-calendar/upcoming?days=90`);
      if (response.ok) {
        const data = await response.json();
        setTaxDeadlines(data.upcoming || []);
      }
    } catch (error) {
      console.error('Failed to load tax deadlines:', error);
    } finally {
      setTaxDeadlinesLoading(false);
    }
  };

  // Load AI-generated governance suggestions with fallback to static insights
  const loadAiSuggestions = async () => {
    if (!selectedTrust) return;
    
    setAiSuggestionsLoading(true);
    setAiSuggestionsError(false);
    setAiSuggestionsFallback(false);
    
    try {
      const response = await fetchWithAuth('/ai/governance-suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trust_id: selectedTrust.trust_id })
      });
      
      if (response.ok) {
        const data = await response.json();
        setAiSuggestions(data.suggestions || []);
        setAiSuggestionsFallback(false);
      } else {
        // AI failed - use static governance insights as fallback
        console.error('AI suggestions unavailable, using static fallback');
        applyFallbackSuggestions();
      }
    } catch (error) {
      console.error('Failed to load AI suggestions:', error);
      // AI failed - use static governance insights as fallback
      applyFallbackSuggestions();
    } finally {
      setAiSuggestionsLoading(false);
    }
  };

  // Fallback to static governance insights when AI is unavailable
  const applyFallbackSuggestions = () => {
    // Use the existing governance_insights from dashboard data as fallback
    const insights = dashboard?.governance_insights || [];
    const fallbackSuggestions = insights.slice(0, 4).map(insight => ({
      title: insight.title,
      description: insight.description,
      route: insight.action_path,
      estimated_points_gain: insight.points
    }));
    
    if (fallbackSuggestions.length > 0) {
      setAiSuggestions(fallbackSuggestions);
      setAiSuggestionsFallback(true);
      setAiSuggestionsError(false);
    } else {
      // No fallback data available either
      setAiSuggestionsError(true);
      setAiSuggestions([]);
    }
  };

  const dismissOnboarding = async () => {
    try {
      await fetchWithAuth('/onboarding/dismiss', { method: 'POST' });
      setDashboard(prev => ({
        ...prev,
        onboarding_state: { ...prev.onboarding_state, checklist_dismissed: true }
      }));
    } catch (error) {
      console.error('Failed to dismiss onboarding:', error);
    }
  };

  const dismissInsight = async (criterionName) => {
    if (!selectedTrust) return;
    try {
      const response = await fetchWithAuth('/insights/dismiss', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          criterion_name: criterionName
        })
      });
      if (response.ok) {
        toast.success('Recommendation dismissed');
        await loadDashboardData();
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to dismiss');
      }
    } catch (error) {
      console.error('Failed to dismiss insight:', error);
      toast.error('Failed to dismiss recommendation');
    }
  };

  const handleCreateDemo = async () => {
    setLoading(true);
    try {
      const result = await seedDemoData();
      if (result?.seeded) {
        toast.success('Demo data created successfully');
        await loadTrusts();
      } else {
        toast.info('You already have trusts. Demo data can only be created for new accounts.');
      }
    } catch (error) {
      console.error('Failed to create demo:', error);
      toast.error('Failed to create demo data');
    } finally {
      setLoading(false);
    }
  };

  const getScoreColor = (score) => {
    if (score >= 96) return 'score-good';
    if (score >= 72) return 'score-warning';
    return 'score-critical';
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'approved': return 'badge-success';
      case 'review': return 'badge-warning';
      case 'declined': return 'badge-error';
      default: return '';
    }
  };

  const formatDate = (dateString) => {
    try {
      return format(parseISO(dateString), 'MMM d, yyyy');
    } catch {
      return dateString;
    }
  };

  const getActivityIcon = (type) => {
    switch (type) {
      case 'minutes': return <FileText className="w-4 h-4" />;
      case 'distribution': return <DollarSign className="w-4 h-4" />;
      case 'expense': return <Receipt className="w-4 h-4" />;
      case 'compensation': return <Wallet className="w-4 h-4" />;
      case 'task': return <CheckCircle2 className="w-4 h-4" />;
      default: return <FileText className="w-4 h-4" />;
    }
  };

  // Calculate onboarding progress from dashboard data
  const getOnboardingProgress = () => {
    const onboarding = dashboard?.onboarding_state;
    if (!onboarding) return { completed: 0, total: 8, profileSteps: [], setupSteps: [] };
    
    const profileSteps = [
      { 
        id: 'formation_date', 
        label: 'Add Formation Date',
        description: 'The IRS uses this to calculate your filing deadlines.',
        done: onboarding.formation_date_added,
        icon: CalendarCheck,
        action: '/settings'
      },
      { 
        id: 'ein', 
        label: 'Enter Your EIN',
        description: 'Every trust needs an EIN for tax filing. Don\'t have one yet? Skip this for now.',
        done: onboarding.ein_entered,
        icon: FileCheck,
        action: '/settings'
      },
      { 
        id: 'trust_doc', 
        label: 'Add Trust Document to Vault',
        description: 'Your signed, notarized Declaration of Trust. Link it from Google Drive, Dropbox, or wherever you store it.',
        done: onboarding.trust_doc_uploaded,
        icon: FileUp,
        action: '/vault'
      },
      { 
        id: 'ein_doc', 
        label: 'Add EIN Letter to Vault',
        description: 'The IRS confirmation letter (CP575) for your EIN. Skip if you don\'t have it yet.',
        done: onboarding.ein_doc_uploaded,
        icon: Upload,
        action: '/vault'
      }
    ];
    
    const setupSteps = [
      { 
        id: 'beneficiaries', 
        label: 'Set Up Beneficiaries',
        description: 'Every distribution requires a named beneficiary. This is step one before you can record anything else.',
        done: onboarding.beneficiaries_added,
        icon: Users,
        action: '/beneficiaries'
      },
      { 
        id: 'assets', 
        label: 'Open a Trust Bank Account',
        description: 'The most important first step — a trust needs its own bank account before anything else. We\'ll help you set it up.',
        done: onboarding.assets_added,
        icon: Package,
        action: '/structures'
      },
      { 
        id: 'minutes', 
        label: 'Hold Your First Trustee Meeting',
        description: 'Trustees are legally required to document decisions. Your first meeting covers accepting trusteeship, opening bank accounts, and setting up the trust.',
        done: onboarding.minutes_generated,
        icon: ClipboardList,
        action: '/minutes/create?type=initial_trustee_meeting&from=onboarding'
      },
      { 
        id: 'calendar', 
        label: 'Check Your Tax Calendar',
        description: 'Your trust has hard filing deadlines. We\'ve calculated yours based on your setup. Miss one and the IRS notices.',
        done: onboarding.calendar_set,
        icon: Calendar,
        action: '/calendar'
      }
    ];
    
    const allSteps = [...profileSteps, ...setupSteps];
    const completed = allSteps.filter(s => s.done).length;
    return { completed, total: allSteps.length, profileSteps, setupSteps, steps: allSteps };
  };

  // Get insights from dashboard API (single source of truth)
  const insights = dashboard?.governance_insights || [];
  const onboardingProgress = getOnboardingProgress();
  const healthScore = dashboard?.health_score;
  const stats = dashboard?.stats;
  const activities = dashboard?.recent_activity || [];
  const onboarding = dashboard?.onboarding_state;

  // Empty state - no trusts
  if (!loading && trusts.length === 0) {
    return (
      <div className="main-layout" data-testid="dashboard-page">
        <Sidebar />
        <main className="main-content">
          <div className="page-container">
            <div className="empty-state max-w-lg mx-auto mt-16">
              <div className="w-16 h-16 bg-navy/5 flex items-center justify-center mx-auto mb-6">
                <FileText className="w-8 h-8 text-navy/30" />
              </div>
              <h2 className="font-serif text-2xl text-navy mb-2">No Trusts Yet</h2>
              <p className="text-muted-foreground mb-6">
                Create your first trust to start managing governance
              </p>
              <div className="space-y-3">
                <Button onClick={() => navigate('/onboarding')} className="btn-primary">
                  Create Your First Trust
                </Button>
                <Button onClick={handleCreateDemo} variant="outline" className="btn-secondary">
                  Use Demo Data
                </Button>
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="main-layout" data-testid="dashboard-page">
      <Sidebar />
      <main className="main-content dot-grid">
        {/* Subscription Banners */}
        
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-start justify-between">
            <div>
              <h1 className="page-title">Dashboard</h1>
              <p className="page-subtitle">
                Trust administration at a glance — view key metrics, upcoming deadlines, and quick actions for {selectedTrust?.name || 'your trust'}
              </p>
            </div>
            <PageHelpButton
              items={[
                { text: "View your trust's key metrics at a glance — defensibility score, upcoming deadlines, and recent activity" },
                { text: 'Use Quick Actions to jump to common tasks like recording a distribution or adding an asset' },
                { text: 'Complete your onboarding checklist to set up your trust profile' },
              ]}
              taPrompt="Walk me through the Dashboard page and what I should do first"
            />
          </div>

          {/* Trust Manager Section — shown when user has 2+ trusts */}
          {trusts.length >= 2 && !loading && (
            <div className="mb-8" data-testid="trust-manager-section">
              <TrustManager embedded />
            </div>
          )}

          {loading ? (
            <div className="card-grid">
              {[1, 2, 3].map((i) => (
                <div key={i} className="card-trust">
                  <div className="skeleton h-6 w-32 mb-4"></div>
                  <div className="skeleton h-20 w-full"></div>
                </div>
              ))}
            </div>
          ) : (
            <>
              {/* Onboarding Checklist */}
              {onboarding && !onboarding.checklist_dismissed && onboardingProgress.completed < onboardingProgress.total && (
                <div className="mb-8 card-trust border-l-4 border-l-gold bg-gold/5" data-testid="onboarding-checklist">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gold/20 flex items-center justify-center text-gold">
                        <Zap className="w-5 h-5" />
                      </div>
                      <div>
                        <h3 className="font-serif text-lg text-navy">Getting Started</h3>
                        <p className="text-sm text-muted-foreground">
                          {onboardingProgress.completed}/{onboardingProgress.total} steps completed
                        </p>
                      </div>
                    </div>
                    <button 
                      onClick={dismissOnboarding}
                      className="text-muted-foreground hover:text-navy"
                      data-testid="dismiss-onboarding"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                  
                  {/* Profile Completion Section */}
                  <div className="mb-4">
                    <h4 className="font-mono text-xs uppercase tracking-widest text-navy/60 mb-2">Complete Your Trust Profile</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {onboardingProgress.profileSteps.map(step => {
                        const Icon = step.icon;
                        return (
                          <button
                            key={step.id}
                            onClick={() => !step.done && navigate(step.action)}
                            disabled={step.done}
                            className={`p-4 border text-left transition-colors ${
                              step.done 
                                ? 'border-success/30 bg-success/5 cursor-default' 
                                : 'border-navy/20 hover:border-navy/40 cursor-pointer'
                            }`}
                            data-testid={`onboarding-step-${step.id}`}
                          >
                            <div className="flex items-center gap-2 mb-1.5">
                              {step.done ? (
                                <CheckCircle2 className="w-4 h-4 text-success" />
                              ) : (
                                <Circle className="w-4 h-4 text-muted-foreground" />
                              )}
                              <Icon className={`w-4 h-4 ${step.done ? 'text-success' : 'text-navy'}`} />
                              <span className={`font-mono text-xs font-medium ${step.done ? 'text-success line-through' : 'text-navy'}`}>
                                {step.label}
                              </span>
                            </div>
                            <p className={`text-xs leading-relaxed ${step.done ? 'text-success/60' : 'text-muted-foreground'}`}>
                              {step.description}
                            </p>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Trust Setup Section */}
                  <div>
                    <h4 className="font-mono text-xs uppercase tracking-widest text-navy/60 mb-2">Get Your Trust Running</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {onboardingProgress.setupSteps.map(step => {
                        const Icon = step.icon;
                        return (
                          <button
                            key={step.id}
                            onClick={() => !step.done && navigate(step.action)}
                            disabled={step.done}
                            className={`p-4 border text-left transition-colors ${
                              step.done 
                                ? 'border-success/30 bg-success/5 cursor-default' 
                                : 'border-navy/20 hover:border-navy/40 cursor-pointer'
                            }`}
                            data-testid={`onboarding-step-${step.id}`}
                          >
                            <div className="flex items-center gap-2 mb-1.5">
                              {step.done ? (
                                <CheckCircle2 className="w-4 h-4 text-success" />
                              ) : (
                                <Circle className="w-4 h-4 text-muted-foreground" />
                              )}
                              <Icon className={`w-4 h-4 ${step.done ? 'text-success' : 'text-navy'}`} />
                              <span className={`font-mono text-xs font-medium ${step.done ? 'text-success line-through' : 'text-navy'}`}>
                                {step.label}
                              </span>
                            </div>
                            <p className={`text-xs leading-relaxed ${step.done ? 'text-success/60' : 'text-muted-foreground'}`}>
                              {step.description}
                            </p>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* Re-show Getting Started if checklist was dismissed but not fully complete */}
              {onboarding && onboarding.checklist_dismissed && onboardingProgress.completed < onboardingProgress.total && (
                <div className="mb-6">
                  <button
                    onClick={async () => {
                      await fetchWithAuth('/onboarding/dismiss', { method: 'DELETE' });
                      // Refresh dashboard to re-fetch onboarding state
                      window.location.reload();
                    }}
                    className="text-sm text-navy/60 hover:text-navy font-mono flex items-center gap-1.5"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    Show Getting Started ({onboardingProgress.completed}/{onboardingProgress.total} complete)
                  </button>
                </div>
              )}

              {/* What's Next Card - Using governance_insights from /api/dashboard */}
              {insights.length > 0 && (
                <div className="mb-8 card-trust corner-mark" data-testid="whats-next-card">
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-gold/20 to-navy/10 flex items-center justify-center">
                        <Sparkles className="w-5 h-5 text-gold" />
                      </div>
                      <div>
                        <h3 className="font-serif text-lg text-navy">What's Next</h3>
                        <p className="text-sm text-muted-foreground">
                          {insights.length} action{insights.length !== 1 ? 's' : ''} to boost your score by +{insights.reduce((sum, i) => sum + i.points, 0)} points
                        </p>
                      </div>
                    </div>
                    <Link 
                      to="/governance" 
                      className="text-navy hover:text-gold font-mono text-xs uppercase tracking-widest flex items-center gap-1"
                    >
                      Full Report <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>
                  
                  <div className="space-y-3">
                    {insights.slice(0, 5).map((insight, index) => {
                      const InsightIcon = INSIGHT_ICONS[insight.criterion_name] || AlertCircle;
                      const isError = insight.type === 'error';
                      const isWarning = insight.type === 'warning';
                      
                      return (
                        <div 
                          key={index}
                          className={`relative flex items-center justify-between p-4 border transition-all hover:shadow-sm ${
                            isError ? 'border-error/30 bg-error/5 hover:border-error/50' :
                            isWarning ? 'border-warning/30 bg-warning/5 hover:border-warning/50' :
                            'border-navy/20 bg-navy/5 hover:border-navy/30'
                          }`}
                          data-testid={`insight-${index}`}
                        >
                          <div className="flex items-center gap-4 flex-1">
                            <div className={`w-10 h-10 flex items-center justify-center flex-shrink-0 ${
                              isError ? 'bg-error/20 text-error' :
                              isWarning ? 'bg-warning/20 text-warning' :
                              'bg-navy/10 text-navy'
                            }`}>
                              <InsightIcon className="w-5 h-5" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-0.5">
                                <h4 className="font-medium text-navy">{insight.title}</h4>
                                <span className={`px-2 py-0.5 text-xs font-mono ${
                                  isError ? 'bg-error/20 text-error' :
                                  isWarning ? 'bg-warning/20 text-warning' :
                                  'bg-success/20 text-success'
                                }`}>
                                  +{insight.points} pts
                                </span>
                              </div>
                              <p className="text-sm text-muted-foreground">{insight.description}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                            <button
                              onClick={() => dismissInsight(insight.criterion_name)}
                              className="text-muted-foreground hover:text-error transition-colors p-1"
                              title="Dismiss this recommendation"
                              data-testid={`insight-dismiss-${index}`}
                            >
                              <X className="w-4 h-4" />
                            </button>
                            <Button 
                              onClick={() => navigate(insight.action_path)}
                              size="sm"
                              className={`${
                                isError ? 'bg-error hover:bg-error/90 text-white' :
                                isWarning ? 'bg-warning hover:bg-warning/90 text-white' :
                                'btn-primary'
                              }`}
                              data-testid={`insight-action-${index}`}
                            >
                              {insight.action_label}
                              <ChevronRight className="w-4 h-4 ml-1" />
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  
                  {healthScore?.total_score === (healthScore?.max_score || 120) && (
                    <div className="mt-4 p-4 bg-success/10 border border-success/20 flex items-center gap-3">
                      <CheckCircle2 className="w-5 h-5 text-success flex-shrink-0" />
                      <p className="text-sm text-success font-medium">
                        Excellent! Your governance is in perfect health. Keep up the great work!
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* AI-Generated Suggestions Card */}
              <div className="mb-8 card-trust corner-mark" data-testid="ai-suggestions-card">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gradient-to-br from-gold/30 to-gold/10 flex items-center justify-center">
                      <Bot className="w-5 h-5 text-gold" />
                    </div>
                    <div>
                      <h3 className="font-serif text-lg text-navy">AI Recommendations</h3>
                      <p className="text-sm text-muted-foreground">
                        Personalized suggestions to improve governance
                      </p>
                    </div>
                  </div>
                  {!aiSuggestionsLoading && !aiSuggestionsError && (
                    <button
                      onClick={loadAiSuggestions}
                      className="text-navy hover:text-gold font-mono text-xs uppercase tracking-widest flex items-center gap-1"
                    >
                      Refresh <Sparkles className="w-3 h-3" />
                    </button>
                  )}
                </div>
                
                {aiSuggestionsLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin text-gold mr-2" />
                    <span className="text-sm text-muted-foreground">Generating suggestions...</span>
                  </div>
                ) : aiSuggestionsError ? (
                  <div className="p-4 bg-muted/50 border border-muted text-center">
                    <p className="text-sm text-muted-foreground">
                      Unable to load AI suggestions. 
                      <button 
                        onClick={loadAiSuggestions} 
                        className="text-navy hover:text-gold ml-1 underline"
                      >
                        Try again
                      </button>
                    </p>
                  </div>
                ) : aiSuggestions.length > 0 ? (
                  <div className="space-y-3">
                    {aiSuggestions.slice(0, 4).map((suggestion, index) => (
                      <div 
                        key={index}
                        className="flex items-center justify-between p-4 border border-gold/20 bg-gold/5 hover:border-gold/40 transition-all hover:shadow-sm"
                        data-testid={`ai-suggestion-${index}`}
                      >
                        <div className="flex-1 mr-4">
                          <h4 className="font-medium text-navy text-sm mb-1">{suggestion.title}</h4>
                          <p className="text-xs text-muted-foreground line-clamp-2">{suggestion.description}</p>
                          {suggestion.estimated_points_gain && (
                            <span className="inline-block mt-1 px-2 py-0.5 text-xs font-mono bg-success/20 text-success">
                              +{suggestion.estimated_points_gain} pts
                            </span>
                          )}
                        </div>
                        <Button 
                          onClick={() => navigate(suggestion.route)}
                          size="sm"
                          className="btn-secondary flex-shrink-0"
                          data-testid={`ai-suggestion-action-${index}`}
                        >
                          Go
                          <ChevronRight className="w-4 h-4 ml-1" />
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-4 bg-success/10 border border-success/20 text-center">
                    <p className="text-sm text-success">
                      No additional suggestions. Your governance practices look good!
                    </p>
                  </div>
                )}
                
                <p className="text-xs text-muted-foreground mt-4 flex items-center gap-1 font-mono">
                  <Sparkles className="w-3 h-3" />
                  {aiSuggestionsFallback 
                    ? 'Showing governance insights. AI suggestions unavailable.'
                    : 'AI-generated suggestions. You decide which actions to take.'
                  }
                </p>
              </div>

              {/* Tax Calendar Widget */}
              {selectedTrust && (
                <div className="mb-8 card-trust corner-mark">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-navy/20 to-navy/10 flex items-center justify-center">
                        <CalendarDays className="w-5 h-5 text-navy" />
                      </div>
                      <div>
                        <h3 className="font-serif text-lg text-navy">Tax Calendar</h3>
                        <p className="text-sm text-muted-foreground">Upcoming filing deadlines</p>
                      </div>
                    </div>
                    <Link 
                      to="/calendar" 
                      className="text-navy hover:text-gold font-mono text-xs uppercase tracking-widest flex items-center gap-1"
                    >
                      View All <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>

                  {taxDeadlinesLoading ? (
                    <div className="flex items-center justify-center py-6">
                      <Loader2 className="w-5 h-5 animate-spin text-navy mr-2" />
                      <span className="text-sm text-muted-foreground">Loading deadlines...</span>
                    </div>
                  ) : taxDeadlines.length === 0 ? (
                    <div className="p-6 bg-navy/5 border border-navy/10 text-center rounded">
                      <p className="text-sm text-muted-foreground mb-3">No tax calendar generated yet.</p>
                      <Link to="/calendar?type=tax">
                        <Button size="sm" className="btn-secondary">
                          <CalendarDays className="w-4 h-4 mr-2" />
                          Set Up Tax Calendar
                        </Button>
                      </Link>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {taxDeadlines.slice(0, 5).map((d) => {
                        const overdue = d.is_overdue && d.filing_status === 'pending';
                        return (
                          <div key={d.entry_id} className={`flex items-center justify-between p-3 border ${overdue ? 'border-red-200 bg-red-50/50' : 'border-navy/10'} rounded`}>
                            <div className="flex items-center gap-3">
                              <div className="flex flex-col items-center min-w-[48px]">
                                <div className="text-[10px] font-medium text-neutral-500 uppercase">{format(parseISO(d.due_date), 'MMM')}</div>
                                <div className={`text-lg font-bold ${overdue ? 'text-red-600' : 'text-navy'}`}>{format(parseISO(d.due_date), 'd')}</div>
                              </div>
                              <div>
                                <p className="font-medium text-sm text-navy">{d.description}</p>
                                {overdue ? (
                                  <p className="text-xs text-red-600">Overdue by {Math.abs(d.days_remaining)} days</p>
                                ) : d.days_remaining <= 30 ? (
                                  <p className="text-xs text-warning">Due in {d.days_remaining} days</p>
                                ) : (
                                  <p className="text-xs text-muted-foreground">Due {format(parseISO(d.due_date), 'MMMM d, yyyy')}</p>
                                )}
                              </div>
                            </div>
                            <span className={`font-mono text-[10px] uppercase tracking-wider px-2 py-1 rounded ${
                              d.filing_status === 'filed' || d.filing_status === 'not_required' 
                                ? 'bg-emerald-100 text-emerald-700' 
                                : overdue 
                                  ? 'bg-red-100 text-red-700' 
                                  : 'bg-slate-100 text-slate-600'
                            }`}>
                              {d.filing_status === 'filed' ? 'Filed' : d.filing_status === 'not_required' ? 'N/A' : overdue ? 'Overdue' : 'Pending'}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Top Row - Governance Score & Quick Actions */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* Defensibility Score */}
                <div className="lg:col-span-2 card-trust corner-mark">
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <p className="label-trust mb-1">Trust Health</p>
                      <h2 className="font-serif text-2xl text-navy">{dashboard?.trust_name || selectedTrust?.name}</h2>
                    </div>
                    <Link 
                      to="/governance" 
                      className="text-navy hover:text-gold font-mono text-xs uppercase tracking-widest flex items-center gap-1"
                      data-testid="view-governance-link"
                    >
                      View Details <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>

                  <div className="flex items-center gap-8">
                    <div className="score-circle">
                      <span className={`score-indicator ${getScoreColor(healthScore?.total_score || 0)}`}>
                        {healthScore?.total_score || 0}
                      </span>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
                        Score
                      </span>
                    </div>

                    {/* 5-Criteria Display */}
                    {healthScore?.criteria ? (
                      <div className="flex-1 space-y-3">
                        {healthScore.criteria.map((criterion, i) => (
                          <div key={i} className="flex items-center justify-between">
                            <span className="text-sm text-muted-foreground flex items-center gap-2">
                              {criterion.achieved ? (
                                <CheckCircle2 className="w-4 h-4 text-success" />
                              ) : (
                                <Circle className="w-4 h-4 text-navy/30" />
                              )}
                              {criterion.name}
                            </span>
                            <div className="flex items-center gap-2">
                              <div className="w-16 h-2 bg-navy/10">
                                <div 
                                  className={`h-full ${criterion.achieved ? 'bg-success' : 'bg-navy/20'}`} 
                                  style={{ width: `${(criterion.points / 20) * 100}%` }}
                                ></div>
                              </div>
                              <span className={`font-mono text-xs w-8 ${criterion.achieved ? 'text-success' : 'text-muted-foreground'}`}>
                                {criterion.points}/20
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="flex-1 text-muted-foreground text-sm">
                        Loading criteria...
                      </div>
                    )}
                  </div>

                  {healthScore?.total_score < 72 && healthScore?.total_score >= 48 && (
                    <div className="mt-6 p-4 bg-warning/10 border border-warning/20 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-warning flex-shrink-0" />
                      <p className="text-sm text-warning">
                        Your governance score needs attention. Consider completing the suggested actions above.
                      </p>
                    </div>
                  )}

                  {healthScore?.total_score < 48 && (
                    <div className="mt-6 p-4 bg-error/10 border border-error/20 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-error flex-shrink-0" />
                      <p className="text-sm text-error">
                        Urgent: Your trust requires immediate attention. Complete pending tasks to improve your score.
                      </p>
                    </div>
                  )}
                </div>

                {/* Quick Actions - Enhanced */}
                <div className="card-trust">
                  <div className="flex items-center justify-between mb-4">
                    <p className="label-trust">Quick Actions</p>
                    <Link 
                      to="/minutes/templates"
                      className="text-xs text-muted-foreground hover:text-navy"
                    >
                      All Templates
                    </Link>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {QUICK_ACTIONS.map((action, index) => {
                      const Icon = action.icon;
                      return (
                        <button
                          key={index}
                          onClick={() => navigate(action.path)}
                          className="p-3 text-left border border-border hover:border-gold transition-colors group"
                          data-testid={`quick-action-${index}`}
                        >
                          <div className={`w-8 h-8 ${action.color} flex items-center justify-center mb-2`}>
                            <Icon className="w-4 h-4" />
                          </div>
                          <p className="font-medium text-sm text-navy group-hover:text-gold transition-colors">
                            {action.title}
                          </p>
                          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                            {action.description}
                          </p>
                        </button>
                      );
                    })}
                  </div>

                  {/* Stats from /api/dashboard */}
                  <div className="mt-6 pt-6 border-t border-navy/10">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="font-mono text-2xl text-navy">{stats?.total_decisions || 0}</p>
                        <p className="label-trust">Decisions</p>
                      </div>
                      <div>
                        <p className="font-mono text-2xl text-warning">{stats?.pending_reviews || 0}</p>
                        <p className="label-trust">Pending</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Recent Activity */}
              <div className="card-trust">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <p className="label-trust mb-1">Recent Activity</p>
                    <h2 className="font-serif text-xl text-navy">Timeline</h2>
                  </div>
                  {stats && (
                    <div className="text-right">
                      <p className="font-mono text-sm text-muted-foreground">
                        {stats.total_distributions} distributions
                      </p>
                      <p className="font-mono text-xs text-muted-foreground">
                        ${stats.ytd_distributions_amount?.toLocaleString()} YTD
                      </p>
                    </div>
                  )}
                </div>

                {activities.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-muted-foreground">No activity yet</p>
                    <Button 
                      onClick={() => navigate('/minutes/create')}
                      className="btn-secondary mt-4"
                    >
                      Record Your First Minutes
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-0">
                    {activities.map((activity, index) => (
                      <div 
                        key={`${activity.type}-${activity.id}`} 
                        className={`timeline-item ${activity.type}`}
                      >
                        <div className="flex items-start gap-4">
                          <div className={`w-8 h-8 flex items-center justify-center ${
                            activity.type === 'minutes' ? 'bg-navy/10 text-navy' :
                            activity.type === 'distribution' ? 'bg-gold/20 text-gold' :
                            activity.type === 'compensation' ? 'bg-navy/10 text-navy' :
                            activity.type === 'task' ? 'bg-success/20 text-success' :
                            'bg-muted text-muted-foreground'
                          }`}>
                            {getActivityIcon(activity.type)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-navy truncate">{activity.title}</p>
                            <div className="flex items-center gap-3 mt-1">
                              <span className="font-mono text-xs text-muted-foreground">
                                {formatDate(activity.date)}
                              </span>
                              {activity.status && (
                                <span className={`badge-trust ${getStatusBadgeClass(activity.status)}`}>
                                  {activity.status}
                                </span>
                              )}
                              {activity.entry_type && (
                                <span className="badge-trust">
                                  {activity.entry_type}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
