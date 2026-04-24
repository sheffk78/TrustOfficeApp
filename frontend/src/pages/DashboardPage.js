import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import confetti from 'canvas-confetti';
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
  Bot
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const QUICK_ACTIONS = [
  {
    title: 'Record Distribution',
    description: 'Document a distribution to beneficiaries',
    icon: DollarSign,
    path: '/minutes/template/distribution_to_beneficiaries',
    color: 'bg-green-500/10 text-green-600'
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
  'Annual Review': TrendingUp
};

export default function DashboardPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, selectedTrust, trusts, loadTrusts, seedDemoData } = useAuth();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // AI Suggestions state
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [aiSuggestionsLoading, setAiSuggestionsLoading] = useState(false);
  const [aiSuggestionsError, setAiSuggestionsError] = useState(false);
  const [aiSuggestionsFallback, setAiSuggestionsFallback] = useState(false); // True when using static fallback

  // Show welcome toast + confetti after successful purchase
  useEffect(() => {
    if (searchParams.get('welcome') === 'true') {
      toast.success('Welcome to TrustOffice!', {
        description: 'Your subscription is now active. Let\'s get your trust organized.',
        duration: 6000
      });

      // Subtle confetti burst
      const end = Date.now() + 1500;
      const colors = ['#010079', '#d5ad36', '#ffffff'];
      const frame = () => {
        confetti({
          particleCount: 2,
          angle: 60,
          spread: 55,
          origin: { x: 0, y: 0.7 },
          colors,
        });
        confetti({
          particleCount: 2,
          angle: 120,
          spread: 55,
          origin: { x: 1, y: 0.7 },
          colors,
        });
        if (Date.now() < end) requestAnimationFrame(frame);
      };
      frame();

      // Remove the query param to prevent showing again on refresh
      searchParams.delete('welcome');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (selectedTrust) {
      loadDashboardData();
      loadAiSuggestions();
    } else if (!trustsLoading && trusts.length === 0) {
      setLoading(false);
    }
  }, [selectedTrust, trusts, trustsLoading]);

  const loadDashboardData = async () => {
    if (!selectedTrust) return;
    
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
    if (score >= 70) return 'score-good';
    if (score >= 40) return 'score-warning';
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
    if (!onboarding) return { completed: 0, total: 4, steps: [] };
    
    const steps = [
      { 
        id: 'entities', 
        label: 'Confirm Entities', 
        done: onboarding.entities_confirmed,
        icon: Building2,
        action: '/entities'
      },
      { 
        id: 'calendar', 
        label: 'Set Up Calendar', 
        done: onboarding.calendar_set,
        icon: Calendar,
        action: '/calendar'
      },
      { 
        id: 'minutes', 
        label: 'Generate Minutes', 
        done: onboarding.minutes_generated,
        icon: FileText,
        action: '/minutes/new'
      },
      { 
        id: 'distribution', 
        label: 'Log Distribution', 
        done: onboarding.distribution_logged,
        icon: DollarSign,
        action: '/distributions'
      }
    ];
    
    const completed = steps.filter(s => s.done).length;
    return { completed, total: steps.length, steps };
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
          <div className="page-header">
            <h1 className="page-title">Dashboard</h1>
            <p className="page-subtitle">
              {dashboard?.trust_name || selectedTrust?.name || 'Select a trust'} • {selectedTrust?.role}
            </p>
          </div>

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
                  
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {onboardingProgress.steps.map(step => {
                      const Icon = step.icon;
                      return (
                        <button
                          key={step.id}
                          onClick={() => !step.done && navigate(step.action)}
                          disabled={step.done}
                          className={`p-3 border text-left transition-colors ${
                            step.done 
                              ? 'border-success/30 bg-success/5 cursor-default' 
                              : 'border-navy/20 hover:border-navy/40 cursor-pointer'
                          }`}
                          data-testid={`onboarding-step-${step.id}`}
                        >
                          <div className="flex items-center gap-2 mb-1">
                            {step.done ? (
                              <CheckCircle2 className="w-4 h-4 text-success" />
                            ) : (
                              <Circle className="w-4 h-4 text-muted-foreground" />
                            )}
                            <Icon className={`w-4 h-4 ${step.done ? 'text-success' : 'text-navy'}`} />
                          </div>
                          <span className={`font-mono text-xs ${step.done ? 'text-success line-through' : 'text-navy'}`}>
                            {step.label}
                          </span>
                        </button>
                      );
                    })}
                  </div>
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
                          className={`flex items-center justify-between p-4 border transition-all hover:shadow-sm ${
                            isError ? 'border-error/30 bg-error/5 hover:border-error/50' :
                            isWarning ? 'border-warning/30 bg-warning/5 hover:border-warning/50' :
                            'border-navy/20 bg-navy/5 hover:border-navy/30'
                          }`}
                          data-testid={`insight-${index}`}
                        >
                          <div className="flex items-center gap-4">
                            <div className={`w-10 h-10 flex items-center justify-center flex-shrink-0 ${
                              isError ? 'bg-error/20 text-error' :
                              isWarning ? 'bg-warning/20 text-warning' :
                              'bg-navy/10 text-navy'
                            }`}>
                              <InsightIcon className="w-5 h-5" />
                            </div>
                            <div>
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
                          <Button 
                            onClick={() => navigate(insight.action_path)}
                            size="sm"
                            className={`flex-shrink-0 ${
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
                      );
                    })}
                  </div>
                  
                  {healthScore?.total_score === 100 && (
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

              {/* Top Row - Governance Score & Quick Actions */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* Governance Health Score */}
                <div className="lg:col-span-2 card-trust corner-mark">
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <p className="label-trust mb-1">Governance Health</p>
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

                  {healthScore?.total_score < 60 && healthScore?.total_score >= 40 && (
                    <div className="mt-6 p-4 bg-warning/10 border border-warning/20 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-warning flex-shrink-0" />
                      <p className="text-sm text-warning">
                        Your governance score needs attention. Consider completing the suggested actions above.
                      </p>
                    </div>
                  )}

                  {healthScore?.total_score < 40 && (
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
                      onClick={() => navigate('/minutes/new')}
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
