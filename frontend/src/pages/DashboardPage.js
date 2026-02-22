import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
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
  Wallet
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

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
      await seedDemoData();
      await loadTrusts();
    } catch (error) {
      console.error('Failed to create demo:', error);
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
      default: return <FileText className="w-4 h-4" />;
    }
  };

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
                      <span className={`score-indicator ${getScoreColor(governance?.overall_score || 0)}`}>
                        {governance?.overall_score || 0}
                      </span>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
                        Score
                      </span>
                    </div>

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
                  </div>

                  {governance?.status === 'warning' && (
                    <div className="mt-6 p-4 bg-warning/10 border border-warning/20 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-warning flex-shrink-0" />
                      <p className="text-sm text-warning">
                        Your governance score needs attention. Consider scheduling a review meeting.
                      </p>
                    </div>
                  )}

                  {governance?.status === 'critical' && (
                    <div className="mt-6 p-4 bg-error/10 border border-error/20 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-error flex-shrink-0" />
                      <p className="text-sm text-error">
                        Urgent: Your trust requires immediate attention. Schedule a review meeting now.
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
