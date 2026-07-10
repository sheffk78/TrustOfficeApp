import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
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
  CalendarDays,
  Clock,
  CalendarCheck,
  FileCheck,
  FileUp,
  Upload,
  Users,
  ClipboardList,
  GraduationCap,
  Shield,
  UserCheck,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import PageHelpButton from '@/components/PageHelpButton';
import { TrustManager } from '@/components/TrustManager';
import BankingSummaryCard from '@/components/BankingSummaryCard';
import SpendingThresholdCard from '@/components/SpendingThresholdCard';

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
    description: 'Accept property and update Trust Assets',
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
    title: 'View Trust Assets',
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
  const { user, selectedTrust, trusts, trustsLoading, loadTrusts, seedDemoData, subscription } = useAuth();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [weeklyBriefing, setWeeklyBriefing] = useState(null);

  // Onboarding accordion expansion state (starts collapsed)
  const [onboardingExpanded, setOnboardingExpanded] = useState(false);

  // Tax Calendar dashboard state
  const [taxDeadlines, setTaxDeadlines] = useState([]);
  const [taxDeadlinesLoading, setTaxDeadlinesLoading] = useState(false);
  
  // Dismissible upgrade banner state
  const [upgradeBannerDismissed, setUpgradeBannerDismissed] = useState(false);

  // WingPoint welcome modal state
  const [showWpWelcome, setShowWpWelcome] = useState(false);
  const [wpBannerVisible, setWpBannerVisible] = useState(false);

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

  // WingPoint welcome modal — show on first visit when ?wp=1 or not yet dismissed
  useEffect(() => {
    const wpParam = searchParams.get('wp');
    const dismissed = localStorage.getItem('wp_welcome_dismissed');
    const hasTrusts = trusts && trusts.length > 0;

    if (wpParam === '1' || (!dismissed && hasTrusts)) {
      setShowWpWelcome(true);
      setWpBannerVisible(false);
    } else if (dismissed && hasTrusts) {
      setWpBannerVisible(true);
    }
  }, [searchParams, trusts]);

  useEffect(() => {
    if (trustsLoading) return;
    if (selectedTrust) {
      loadDashboardData();
      loadTaxDeadlines();
      loadWeeklyBriefing();
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

  const loadWeeklyBriefing = async () => {
    if (!selectedTrust) return;
    try {
      const response = await fetchWithAuth(`/ai/weekly-briefing?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        const data = await response.json();
        setWeeklyBriefing(data.briefing || []);
      }
    } catch (error) {
      // Silent fail — briefing is non-critical
      console.error('Failed to load weekly briefing:', error);
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

  const dismissWpWelcome = () => {
    localStorage.setItem('wp_welcome_dismissed', 'true');
    setShowWpWelcome(false);
    setWpBannerVisible(true);
  };

  const goToTrustDocsFromWp = () => {
    localStorage.setItem('wp_welcome_dismissed', 'true');
    setShowWpWelcome(false);
    navigate('/vault');
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
        showError(toast, new Error(data.detail || 'Failed to dismiss'), { operation: 'dismiss', page: 'Dashboard' });
      }
    } catch (error) {
      console.error('Failed to dismiss insight:', error);
      showError(toast, error, { operation: 'dismiss', page: 'Dashboard' });
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
      showError(toast, error, { operation: 'create', page: 'Dashboard' });
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

  // Calculate onboarding progress from dashboard data — single unified ordered list
  const getOnboardingProgress = () => {
    const onboarding = dashboard?.onboarding_state;
    if (!onboarding) return { nextStep: null, completed: 0, total: 9, allSteps: [] };

    // Field names must match backend OnboardingState model (backend/models.py L1045)
    const steps = [
      { id: 'trust_doc', label: 'Add your trust document', done: onboarding.trust_doc_uploaded, action: '/vault', priority: 1 },
      { id: 'beneficiaries', label: 'Add beneficiaries', done: onboarding.beneficiaries_added, action: '/beneficiaries', priority: 2 },
      { id: 'successor_trustee', label: 'Name a successor trustee', done: onboarding.successor_trustee_added, action: '/settings#successor-trustee', priority: 3 },
      { id: 'assets', label: 'Add your trust assets', done: onboarding.assets_added, action: '/schedule-a', priority: 4 },
      { id: 'minutes', label: 'Hold your first trustee meeting', done: onboarding.minutes_generated, action: '/minutes/create?type=initial_trustee_meeting', priority: 5 },
      { id: 'ein_doc', label: 'Add EIN letter to vault', done: onboarding.ein_doc_uploaded, action: '/vault', priority: 6 },
      { id: 'formation_date', label: 'Add formation date', done: onboarding.formation_date_added, action: '/settings#formation-date', priority: 7 },
      { id: 'ein', label: 'Enter your EIN', done: onboarding.ein_entered, action: '/settings#ein', priority: 8 },
      { id: 'calendar', label: 'Review your tax calendar', done: onboarding.calendar_set, action: '/calendar', priority: 9 },
    ];

    const completed = steps.filter(s => s.done).length;
    const nextStep = steps.find(s => !s.done);
    return { nextStep, completed, total: steps.length, allSteps: steps };
  };

  // Get insights from dashboard API (single source of truth)
  const insights = dashboard?.governance_insights || [];
  const onboardingProgress = getOnboardingProgress();
  const healthScore = dashboard?.health_score;
  const stats = dashboard?.stats;
  const activities = dashboard?.recent_activity || [];
  const onboarding = dashboard?.onboarding_state;

  // Fix 14: Compute the single highest-priority "do this next" action
  const computeNextAction = () => {
    // Priority 1: Overdue tax deadline
    const overdueDeadline = taxDeadlines?.find(d => d.days_until < 0 || (d.is_overdue && d.filing_status === 'pending'));
    if (overdueDeadline) return {
      title: `${overdueDeadline.description || 'Tax deadline'} is overdue`,
      action: '/calendar',
      cta: 'Review deadline',
      context: `${Math.abs(overdueDeadline.days_remaining ?? overdueDeadline.days_until ?? 0)} days overdue`,
      variant: 'urgent'
    };

    // Priority 2: First incomplete onboarding step
    if (onboardingProgress.nextStep) return {
      title: onboardingProgress.nextStep.label,
      action: onboardingProgress.nextStep.action,
      cta: 'Start now',
      context: `${onboardingProgress.completed}/${onboardingProgress.total} setup steps done`,
      variant: 'onboarding'
    };

    // Priority 3: Highest-point governance insight
    const topInsight = [...insights].sort((a, b) => (b.points || 0) - (a.points || 0))[0];
    if (topInsight) return {
      title: topInsight.title || topInsight.description,
      action: topInsight.action_path || '/governance',
      cta: 'Fix this',
      context: `+${topInsight.points || 0} health points`,
      variant: 'insight'
    };

    return null; // All caught up
  };

  const nextAction = computeNextAction();

  // Determine if this is a new trust (less than 14 days old)
  const trustCreatedAt = selectedTrust?.created_at;
  const trustAgeDays = trustCreatedAt
    ? Math.floor((Date.now() - new Date(trustCreatedAt).getTime()) / (1000 * 60 * 60 * 24))
    : 0;
  const isNewTrust = trustAgeDays < 14;

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
        {subscription?.needs_upgrade && !upgradeBannerDismissed && (
          <div
            className="mx-auto max-w-4xl mt-4 mb-2 border border-amber-300 bg-gradient-to-r from-amber-50 to-yellow-50 dark:from-amber-950/30 dark:to-yellow-950/30 dark:border-amber-700"
            data-testid="upgrade-banner"
          >
            <div className="flex items-center gap-4 p-4">
              <div className="w-10 h-10 bg-amber-400/20 flex items-center justify-center flex-shrink-0">
                <Zap className="w-5 h-5 text-amber-600 dark:text-amber-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-amber-900 dark:text-amber-100">
                  Your current plan supports{' '}
                  <span className="font-semibold">{subscription.trust_limit}</span> trusts but you have{' '}
                  <span className="font-semibold">{subscription.trust_count}</span>. Upgrade to manage all your trusts.
                </p>
              </div>
              <Link
                to="/billing?wp=1&action=upgrade"
                className="inline-flex items-center gap-1.5 h-9 px-4 text-sm font-medium bg-amber-500 text-white hover:bg-amber-600 transition-colors flex-shrink-0"
                data-testid="upgrade-banner-cta"
              >
                Upgrade <ArrowRight className="w-4 h-4" />
              </Link>
              <button
                onClick={() => setUpgradeBannerDismissed(true)}
                className="text-amber-600 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-200 flex-shrink-0"
                aria-label="Dismiss upgrade banner"
                data-testid="upgrade-banner-dismiss"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}

        {/* WingPoint persistent banner — shows after welcome modal dismissal */}
        {wpBannerVisible && (
          <div
            className="mx-auto max-w-4xl mt-4 mb-2 border border-gold/30 bg-gold/10"
            data-testid="wp-persistent-banner"
          >
            <div className="flex items-center gap-4 p-4">
              <div className="w-10 h-10 bg-gold/20 flex items-center justify-center flex-shrink-0">
                <Sparkles className="w-5 h-5 text-gold" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-navy">
                  Your WingPoint trust is ready.{' '}
                  <Link to="/vault" className="font-semibold underline hover:text-navy/70">
                    Review your trust documents.
                  </Link>
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="page-container">
          {/* WingPoint Welcome Modal */}
          {showWpWelcome && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy/40" data-testid="wp-welcome-modal">
              <div className="bg-white border border-gold/30 max-w-lg w-full mx-4 p-8">
                <div className="flex items-start gap-4 mb-6">
                  <div className="w-12 h-12 bg-gold/10 flex items-center justify-center flex-shrink-0">
                    <Sparkles className="w-6 h-6 text-gold" />
                  </div>
                  <div className="flex-1">
                    <h2 className="font-serif text-xl text-navy mb-3">Welcome to TrustOffice, your WingPoint trust is here.</h2>
                  </div>
                </div>
                <div className="text-sm text-navy/80 space-y-3 mb-6">
                  <p>You are all set. Your trust documents are ready to review, and your management plan is active. Here is what you can do right now:</p>
                  <ul className="space-y-2 ml-4">
                    <li className="flex items-start gap-2">
                      <ChevronRight className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
                      <span>Review your trust in the Trust Documents tab.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <ChevronRight className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
                      <span>Add beneficiaries to make sure your trust reflects your wishes.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <ChevronRight className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
                      <span>Schedule a consultation with a trust advisor.</span>
                    </li>
                  </ul>
                </div>
                <div className="flex flex-col sm:flex-row gap-3">
                  <Button
                    onClick={goToTrustDocsFromWp}
                    className="btn-primary flex-1"
                    data-testid="wp-welcome-go-to-trust"
                  >
                    Go to My Trust Documents
                  </Button>
                  <Button
                    onClick={dismissWpWelcome}
                    variant="outline"
                    className="flex-1"
                    data-testid="wp-welcome-dismiss"
                  >
                    Maybe Later
                  </Button>
                </div>
              </div>
            </div>
          )}

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
              {/* Fix 14: "Do This Next" hero card */}
              {nextAction ? (
                <div
                  className={`mb-8 card-trust overflow-hidden ${
                    nextAction.variant === 'urgent'
                      ? 'bg-gradient-to-r from-error/10 to-error/5 border-l-4 border-l-error'
                      : nextAction.variant === 'onboarding'
                        ? 'bg-gradient-to-r from-gold/10 to-navy/5 border-l-4 border-l-gold'
                        : 'bg-gradient-to-r from-navy/10 to-navy/5 border-l-4 border-l-navy'
                  }`}
                  data-testid="do-this-next-hero"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                          Do This Next
                        </span>
                        {nextAction.variant === 'urgent' && (
                          <span className="font-mono text-[10px] uppercase tracking-widest px-1.5 py-0.5 bg-error/20 text-error">
                            Urgent
                          </span>
                        )}
                      </div>
                      <h2 className="font-serif text-2xl text-navy dark:text-foreground mb-1">
                        {nextAction.title}
                      </h2>
                      <p className="text-sm text-muted-foreground">{nextAction.context}</p>
                    </div>
                    <div className="flex-shrink-0">
                      <Link
                        to={nextAction.action}
                        className="btn-primary inline-flex items-center gap-2 h-12 px-6 text-base"
                        data-testid="do-this-next-cta"
                      >
                        {nextAction.cta}
                        <ArrowRight className="w-4 h-4" />
                      </Link>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mb-8 card-trust bg-gradient-to-r from-success/10 to-success/5 border-l-4 border-l-success" data-testid="all-caught-up-hero">
                  <div className="flex items-center gap-4 p-6">
                    <div className="w-12 h-12 bg-success/20 flex items-center justify-center">
                      <CheckCircle2 className="w-6 h-6 text-success" />
                    </div>
                    <div>
                      <h2 className="font-serif text-2xl text-navy dark:text-foreground mb-1">You're all caught up!</h2>
                      <p className="text-sm text-muted-foreground">No pending actions. Your trust governance is in great shape.</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Fix 13/14: Collapsed onboarding checklist accordion */}
              {onboarding && !onboarding.checklist_dismissed && onboardingProgress.completed < onboardingProgress.total && (
                <div className="mb-8 card-trust" data-testid="onboarding-checklist">
                  <button
                    onClick={() => setOnboardingExpanded(!onboardingExpanded)}
                    className="w-full flex items-center justify-between text-left"
                    data-testid="onboarding-accordion-toggle"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gold/20 flex items-center justify-center text-gold">
                        <Zap className="w-5 h-5" />
                      </div>
                      <div>
                        <h3 className="font-serif text-lg text-navy">Getting Started</h3>
                        <p className="text-sm text-muted-foreground">
                          {onboardingProgress.completed} of {onboardingProgress.total} setup steps complete
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      {/* Progress bar */}
                      <div className="hidden sm:block w-40 h-2 bg-navy/10">
                        <div
                          className="h-full bg-gold transition-all"
                          style={{ width: `${(onboardingProgress.completed / onboardingProgress.total) * 100}%` }}
                        />
                      </div>
                      <ChevronRight className={`w-5 h-5 text-muted-foreground transition-transform ${onboardingExpanded ? 'rotate-90' : ''}`} />
                      <button
                        onClick={(e) => { e.stopPropagation(); dismissOnboarding(); }}
                        className="text-muted-foreground hover:text-navy"
                        data-testid="dismiss-onboarding"
                      >
                        <X className="w-5 h-5" />
                      </button>
                    </div>
                  </button>

                  {onboardingExpanded && (
                    <div className="mt-6 pt-6 border-t border-navy/10">
                      {/* Start Here - Trustee 101 */}
                      <div className="mb-4">
                        <h4 className="font-mono text-xs uppercase tracking-widest text-gold mb-2">Start Here</h4>
                        <button
                          onClick={() => navigate('/course')}
                          className="w-full p-4 border-2 border-gold/30 bg-gold/5 hover:border-gold hover:bg-gold/10 transition-all text-left flex items-center gap-4 group"
                          data-testid="onboarding-step-trustee-101"
                        >
                          <div className="w-10 h-10 bg-gold/20 flex items-center justify-center group-hover:bg-gold/30 transition-colors flex-shrink-0">
                            <GraduationCap className="w-5 h-5 text-gold" />
                          </div>
                          <div className="flex-1">
                            <p className="font-mono text-xs font-medium text-navy">Watch Trustee 101 First</p>
                            <p className="text-xs text-muted-foreground mt-0.5">9 short video lessons (6-12 min each) that explain what a trust is, your duties, and how to avoid common traps. Start here before anything else.</p>
                          </div>
                          <ArrowRight className="w-4 h-4 text-gold opacity-0 group-hover:opacity-100 transition-opacity" />
                        </button>
                      </div>

                      {/* Unified step list */}
                      <div>
                        <h4 className="font-mono text-xs uppercase tracking-widest text-navy/60 mb-2">Setup Steps</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {onboardingProgress.allSteps.map((step, index) => (
                            <button
                              key={step.id}
                              onClick={() => {
                                if (step.done) return;
                                navigate(step.action);
                              }}
                              className={`p-4 border text-left transition-colors ${
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
                                <span className="font-mono text-[10px] text-muted-foreground">#{step.priority}</span>
                                <span className={`font-mono text-xs font-medium ${step.done ? 'text-success line-through' : 'text-navy'}`}>
                                  {step.label}
                                </span>
                                {step.done && (
                                  <span className="ml-auto font-mono text-[10px] uppercase tracking-widest text-success/60">
                                    Done
                                  </span>
                                )}
                              </div>
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
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

              {/* Pending Quarterly Draft Hero (Fix 3) */}
              {dashboard?.pending_quarterly_draft && (
                <div className="mb-6 card-trust border-l-4 border-l-blue-400 bg-blue-50/30" data-testid="quarterly-draft-hero">
                  <div className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-blue-400/20 to-navy/10 flex items-center justify-center">
                        <FileText className="w-5 h-5 text-blue-600" />
                      </div>
                      <div>
                        <h3 className="font-serif text-lg text-navy">
                          Your {dashboard.pending_quarterly_draft.quarter} minutes are drafted
                        </h3>
                        <p className="text-sm text-muted-foreground">Review and finalize when ready</p>
                      </div>
                    </div>
                    <Link
                      to={dashboard.pending_quarterly_draft.review_link}
                      className="btn btn-primary btn-sm"
                    >
                      Review now <ArrowRight className="w-4 h-4 inline ml-1" />
                    </Link>
                  </div>
                </div>
              )}

              {/* Weekly Briefing Hero — "3 things need your attention" */}
              {weeklyBriefing && weeklyBriefing.length > 0 && (
                <div className="mb-8 card-trust border-l-4 border-l-gold" data-testid="weekly-briefing-hero">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 bg-gradient-to-br from-gold/20 to-navy/10 flex items-center justify-center">
                      <CalendarCheck className="w-5 h-5 text-gold" />
                    </div>
                    <div>
                      <h3 className="font-serif text-lg text-navy">{weeklyBriefing.length} {weeklyBriefing.length === 1 ? 'thing' : 'things'} need{weeklyBriefing.length === 1 ? 's' : ''} your attention</h3>
                      <p className="text-sm text-muted-foreground">Weekly briefing</p>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {weeklyBriefing.map((item) => {
                      const severityColors = {
                        high: 'border-error/30 bg-error/5 text-error',
                        medium: 'border-warning/30 bg-warning/5 text-warning',
                        low: 'border-navy/20 bg-navy/5 text-navy/70',
                      };
                      const severityClass = severityColors[item.severity] || severityColors.low;
                      return (
                        <div key={item.id} className={`flex items-center justify-between p-3 border ${severityClass}`}>
                          <span className="text-sm font-medium">{item.title}</span>
                          <div className="flex items-center gap-2">
                            <Link
                              to={`/trust-assistant?prompt=${encodeURIComponent(item.cta_prompt)}`}
                              className="text-xs text-navy hover:text-navy/70 font-mono uppercase tracking-widest flex items-center gap-1"
                            >
                              Ask AI <ArrowRight className="w-3 h-3" />
                            </Link>
                            <Link
                              to={item.action_link}
                              className="text-xs text-navy/60 hover:text-navy font-mono uppercase tracking-widest flex items-center gap-1"
                            >
                              Fix now <ArrowRight className="w-3 h-3" />
                            </Link>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Today's Focus Card - Top 3 prioritized governance actions */}
              {insights.length > 0 && (() => {
                const typePriority = { error: 0, warning: 1, info: 2 };
                const sortedInsights = [...insights].sort((a, b) => {
                  const typeDiff = (typePriority[a.type] ?? 3) - (typePriority[b.type] ?? 3);
                  if (typeDiff !== 0) return typeDiff;
                  return b.points - a.points;
                });
                const topInsights = sortedInsights.slice(0, 3);
                const remainingCount = sortedInsights.length - topInsights.length;

                return (
                <div className="mb-8 card-trust corner-mark" data-testid="todays-focus-card">
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-gold/20 to-navy/10 flex items-center justify-center">
                        <Sparkles className="w-5 h-5 text-gold" />
                      </div>
                      <div>
                        <h3 className="font-serif text-lg text-navy">Today's Focus</h3>
                        <p className="text-sm text-muted-foreground">
                          {sortedInsights.length} action{sortedInsights.length !== 1 ? 's' : ''} to boost your score by +{sortedInsights.reduce((sum, i) => sum + i.points, 0)} points
                        </p>
                      </div>
                    </div>
                    {remainingCount > 0 && (
                      <Link
                        to="/governance"
                        className="text-navy hover:text-navy/70 font-mono text-xs uppercase tracking-widest flex items-center gap-1"
                      >
                        View All ({remainingCount} more) <ArrowRight className="w-3 h-3" />
                      </Link>
                    )}
                  </div>

                  <div className="space-y-3">
                    {topInsights.map((insight, index) => {
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
                                <span className={`font-mono text-xs ${
                                  isError ? 'text-error' : isWarning ? 'text-warning' : 'text-muted-foreground'
                                }`}>
                                  #{index + 1}
                                </span>
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

                  {healthScore?.total_score === (healthScore?.max_score || 115) && (
                    <div className="mt-4 p-4 bg-success/10 border border-success/20 flex items-center gap-3">
                      <CheckCircle2 className="w-5 h-5 text-success flex-shrink-0" />
                      <p className="text-sm text-success font-medium">
                        Excellent! Your governance is in perfect health. Keep up the great work!
                      </p>
                    </div>
                  )}
                </div>
                );
              })()}

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
                      className="text-navy hover:text-navy/70 font-mono text-xs uppercase tracking-widest flex items-center gap-1"
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
                  ) : taxDeadlines.every(d => d.filing_status === 'not_required') ? (
                    <div className="p-6 bg-navy/5 border border-navy/10 text-center rounded">
                      <p className="text-sm text-muted-foreground mb-1">Your next tax deadlines are in {(() => {
                        const upcoming = taxDeadlines.find(d => d.filing_status !== 'not_required' && d.filing_status !== 'filed');
                        return upcoming ? format(parseISO(upcoming.due_date), 'MMMM yyyy') : 'the upcoming tax year';
                      })()}.</p>
                      <p className="text-xs text-muted-foreground">Past deadlines before your trust was created are marked as not applicable.</p>
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

              {/* Banking Summary + Spending Threshold Cards */}
              {selectedTrust && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8" data-testid="banking-cards-row">
                  <BankingSummaryCard />
                  <SpendingThresholdCard />
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
                      {selectedTrust?.trustees && (
                        <p className="text-sm text-muted-foreground mt-1">
                          Trustees: {selectedTrust.trustees}
                        </p>
                      )}
                    </div>
                    <Link 
                      to="/governance" 
                      className="text-navy hover:text-navy/70 font-mono text-xs uppercase tracking-widest flex items-center gap-1"
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
                          <div key={i} className="flex items-center justify-between" title={criterion.description || criterion.name}>
                            <span className="text-sm text-muted-foreground flex items-center gap-2">
                              {criterion.achieved ? (
                                <CheckCircle2 className="w-4 h-4 text-success" />
                              ) : (
                                <Circle className="w-4 h-4 text-navy/30" />
                              )}
                              <span className="cursor-help border-b border-dotted border-muted-foreground/40" onClick={(e) => { e.preventDefault(); toast.info(criterion.name, { description: criterion.description }); }}>
                                {criterion.name}
                              </span>
                            </span>
                            <div className="flex items-center gap-2">
                              <div className="w-16 h-2 bg-navy/10">
                                <div
                                  className={`h-full ${criterion.achieved ? 'bg-success' : 'bg-navy/20'}`}
                                  style={{ width: `${(criterion.points / (criterion.max_points || 15)) * 100}%` }}
                                ></div>
                              </div>
                              <span className={`font-mono text-xs w-8 ${criterion.achieved ? 'text-success' : 'text-muted-foreground'}`}>
                                {criterion.points}/{criterion.max_points || 15}
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

                  {healthScore?.total_score < 96 && healthScore?.total_score >= 72 && !isNewTrust && (
                    <div className="mt-6 p-4 bg-warning/10 border border-warning/20 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-warning flex-shrink-0" />
                      <p className="text-sm text-warning">
                        Your governance score needs attention. Consider completing the suggested actions above.
                      </p>
                    </div>
                  )}

                  {healthScore?.total_score < 72 && !isNewTrust && (
                    <div className="mt-6 p-4 bg-error/10 border border-error/20 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-error flex-shrink-0" />
                      <p className="text-sm text-error">
                        Urgent: Your trust requires immediate attention. Complete pending tasks to improve your score.
                      </p>
                    </div>
                  )}

                  {healthScore?.total_score < 72 && isNewTrust && (
                    <div className="mt-6 p-4 bg-gold/10 border border-gold/20 flex items-start gap-3">
                      <Sparkles className="w-5 h-5 text-gold flex-shrink-0" />
                      <div>
                        <p className="text-sm text-navy font-medium">
                          Welcome! You're just getting started.
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                          Your score will build as you complete the steps below. Don't worry about the number right now, just follow the Getting Started checklist at your own pace.
                        </p>
                      </div>
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
                          <p className="font-medium text-sm text-navy group-hover:text-navy/70 transition-colors">
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
