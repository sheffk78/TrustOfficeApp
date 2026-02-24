import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { 
  Plus, 
  FileText, 
  DollarSign, 
  Receipt,
  Calendar,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Circle,
  X,
  Lightbulb,
  Zap,
  TrendingUp,
  Building2,
  Wallet,
  Package,
  UserPlus,
  Landmark,
  PlusCircle
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

export default function DashboardPage() {
  const navigate = useNavigate();
  const { user, selectedTrust, trusts, loadTrusts, seedDemoData } = useAuth();
  const [governance, setGovernance] = useState(null);
  const [healthDetails, setHealthDetails] = useState(null);
  const [onboarding, setOnboarding] = useState(null);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (selectedTrust) {
      loadDashboardData();
    } else if (trusts.length === 0) {
      setLoading(false);
    }
  }, [selectedTrust]);

  const loadDashboardData = async () => {
    if (!selectedTrust) return;
    
    setLoading(true);
    try {
      // Load governance score
      const govResponse = await fetchWithAuth(`/governance/${selectedTrust.trust_id}`);
      if (govResponse.ok) {
        const govData = await govResponse.json();
        setGovernance(govData);
        // Check if response has criteria (5-criteria health score)
        if (govData.criteria) {
          setHealthDetails(govData);
        }
      }

      // Load onboarding state
      const onboardingResponse = await fetchWithAuth('/onboarding');
      if (onboardingResponse.ok) {
        setOnboarding(await onboardingResponse.json());
      }

      // Load recent activity
      const actResponse = await fetchWithAuth(`/activity?trust_id=${selectedTrust.trust_id}&limit=10`);
      if (actResponse.ok) {
        setActivities(await actResponse.json());
      }
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const dismissOnboarding = async () => {
    try {
      await fetchWithAuth('/onboarding/dismiss', { method: 'POST' });
      setOnboarding(prev => ({ ...prev, checklist_dismissed: true }));
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

  // Generate actionable insights from health criteria
  const getInsights = () => {
    if (!healthDetails?.criteria) return [];
    
    const insights = [];
    const criteria = healthDetails.criteria;
    
    criteria.forEach(c => {
      if (!c.achieved) {
        switch (c.name) {
          case 'Quarterly Minutes':
            insights.push({
              type: 'warning',
              icon: <FileText className="w-4 h-4" />,
              title: 'Missing Q Minutes',
              description: 'Generate minutes this quarter to earn +20 points',
              action: '/minutes/new',
              actionLabel: 'Record Now',
              points: 20
            });
            break;
          case 'Task Compliance':
            insights.push({
              type: 'error',
              icon: <Calendar className="w-4 h-4" />,
              title: 'Overdue Tasks',
              description: 'Complete overdue tasks to earn +20 points',
              action: '/calendar',
              actionLabel: 'View Tasks',
              points: 20
            });
            break;
          case 'Compensation Alignment':
            insights.push({
              type: 'error',
              icon: <Wallet className="w-4 h-4" />,
              title: 'Compensation Over Plan',
              description: 'YTD compensation exceeds approved amount',
              action: '/compensation',
              actionLabel: 'Review',
              points: 20
            });
            break;
          case 'Distribution Documentation':
            insights.push({
              type: 'info',
              icon: <DollarSign className="w-4 h-4" />,
              title: 'No Distributions Logged',
              description: 'Log your first distribution to earn +20 points',
              action: '/distributions',
              actionLabel: 'Add Distribution',
              points: 20
            });
            break;
          case 'Annual Review':
            insights.push({
              type: 'warning',
              icon: <TrendingUp className="w-4 h-4" />,
              title: 'Annual Review Due',
              description: 'Complete annual review for +20 points',
              action: '/calendar',
              actionLabel: 'Schedule Review',
              points: 20
            });
            break;
        }
      }
    });
    
    return insights;
  };

  // Calculate onboarding progress
  const getOnboardingProgress = () => {
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

  const insights = getInsights();
  const onboardingProgress = getOnboardingProgress();

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
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header">
            <h1 className="page-title">Dashboard</h1>
            <p className="page-subtitle">
              {selectedTrust?.name || 'Select a trust'} • {selectedTrust?.role}
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

              {/* Governance Insights - Only show if there are issues */}
              {insights.length > 0 && (
                <div className="mb-8 card-trust corner-mark border-l-4 border-l-warning" data-testid="governance-insights">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 bg-warning/20 flex items-center justify-center text-warning">
                      <Lightbulb className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="font-serif text-lg text-navy">Governance Insights</h3>
                      <p className="text-sm text-muted-foreground">
                        Actions to improve your health score (+{insights.reduce((sum, i) => sum + i.points, 0)} potential points)
                      </p>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {insights.slice(0, 3).map((insight, index) => (
                      <div 
                        key={index}
                        className={`p-4 border ${
                          insight.type === 'error' ? 'border-error/30 bg-error/5' :
                          insight.type === 'warning' ? 'border-warning/30 bg-warning/5' :
                          'border-navy/20 bg-navy/5'
                        }`}
                        data-testid={`insight-${index}`}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className={`w-8 h-8 flex items-center justify-center ${
                            insight.type === 'error' ? 'bg-error/20 text-error' :
                            insight.type === 'warning' ? 'bg-warning/20 text-warning' :
                            'bg-navy/10 text-navy'
                          }`}>
                            {insight.icon}
                          </div>
                          <span className="badge-trust bg-navy/10 text-navy">+{insight.points} pts</span>
                        </div>
                        <h4 className="font-medium text-navy text-sm mb-1">{insight.title}</h4>
                        <p className="text-xs text-muted-foreground mb-3">{insight.description}</p>
                        <Button 
                          onClick={() => navigate(insight.action)}
                          size="sm"
                          className="w-full btn-secondary text-xs"
                        >
                          {insight.actionLabel}
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top Row - Governance Score & Quick Actions */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* Governance Health Score */}
                <div className="lg:col-span-2 card-trust corner-mark">
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <p className="label-trust mb-1">Governance Health</p>
                      <h2 className="font-serif text-2xl text-navy">{selectedTrust?.name}</h2>
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
                      <span className={`score-indicator ${getScoreColor(healthDetails?.total_score || governance?.overall_score || 0)}`}>
                        {healthDetails?.total_score || governance?.overall_score || 0}
                      </span>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
                        Score
                      </span>
                    </div>

                    {/* 5-Criteria Display */}
                    {healthDetails?.criteria ? (
                      <div className="flex-1 space-y-3">
                        {healthDetails.criteria.map((criterion, i) => (
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
                      <div className="flex-1 space-y-4">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">Meeting Recency</span>
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-2 bg-navy/10">
                              <div 
                                className="h-full bg-navy" 
                                style={{ width: `${governance?.meeting_recency_score || 0}%` }}
                              ></div>
                            </div>
                            <span className="font-mono text-xs w-8">{governance?.meeting_recency_score || 0}</span>
                          </div>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">Decisions (90 days)</span>
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-2 bg-navy/10">
                              <div 
                                className="h-full bg-gold" 
                                style={{ width: `${governance?.decisions_count_score || 0}%` }}
                              ></div>
                            </div>
                            <span className="font-mono text-xs w-8">{governance?.decisions_count_score || 0}</span>
                          </div>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">Pending Reviews</span>
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-2 bg-navy/10">
                              <div 
                                className="h-full bg-success" 
                                style={{ width: `${governance?.pending_reviews_score || 0}%` }}
                              ></div>
                            </div>
                            <span className="font-mono text-xs w-8">{governance?.pending_reviews_score || 0}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {(governance?.status === 'warning' || (healthDetails?.total_score < 60 && healthDetails?.total_score >= 40)) && (
                    <div className="mt-6 p-4 bg-warning/10 border border-warning/20 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-warning flex-shrink-0" />
                      <p className="text-sm text-warning">
                        Your governance score needs attention. Consider scheduling a review meeting.
                      </p>
                    </div>
                  )}

                  {(governance?.status === 'critical' || (healthDetails?.total_score < 40)) && (
                    <div className="mt-6 p-4 bg-error/10 border border-error/20 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-error flex-shrink-0" />
                      <p className="text-sm text-error">
                        Urgent: Your trust requires immediate attention. Complete pending tasks to improve your score.
                      </p>
                    </div>
                  )}
                </div>

                {/* Quick Actions */}
                <div className="card-trust">
                  <p className="label-trust mb-4">Quick Actions</p>
                  <div className="space-y-3">
                    <Button 
                      onClick={() => navigate('/minutes/new')}
                      className="w-full btn-primary justify-start"
                      data-testid="quick-record-minutes"
                    >
                      <Plus className="w-4 h-4 mr-2" />
                      Record Minutes
                    </Button>
                    <Button 
                      onClick={() => navigate('/distributions')}
                      className="w-full btn-secondary justify-start"
                      data-testid="quick-add-distribution"
                    >
                      <DollarSign className="w-4 h-4 mr-2" />
                      Add Distribution
                    </Button>
                    <Button 
                      onClick={() => navigate('/expenses')}
                      className="w-full btn-secondary justify-start"
                      data-testid="quick-add-expense"
                    >
                      <Receipt className="w-4 h-4 mr-2" />
                      Add Expense
                    </Button>
                  </div>

                  {/* Stats */}
                  <div className="mt-6 pt-6 border-t border-navy/10">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="font-mono text-2xl text-navy">{governance?.total_decisions || 0}</p>
                        <p className="label-trust">Decisions</p>
                      </div>
                      <div>
                        <p className="font-mono text-2xl text-warning">{governance?.pending_reviews || 0}</p>
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
    </div>
  );
}
