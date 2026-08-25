import { Link, useNavigate } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { FileText, ArrowRight } from 'lucide-react';
import PageHelpButton from '@/components/PageHelpButton';
import { TrustManager } from '@/components/TrustManager';
import BankingSummaryCard from '@/components/BankingSummaryCard';
import SpendingThresholdCard from '@/components/SpendingThresholdCard';
import { useState } from 'react';

import { useDashboardData } from './dashboard/useDashboardData';
import { DashboardBanners } from './dashboard/DashboardBanners';
import { DashboardWpWelcome } from './dashboard/DashboardWpWelcome';
import { DashboardNextActionHero } from './dashboard/DashboardNextActionHero';
import { DashboardOnboardingChecklist } from './dashboard/DashboardOnboardingChecklist';
import { DashboardWeeklyBriefing } from './dashboard/DashboardWeeklyBriefing';
import { DashboardTodaysFocus } from './dashboard/DashboardTodaysFocus';
import { DashboardTaxCalendar } from './dashboard/DashboardTaxCalendar';
import { DashboardHealthScoreCard } from './dashboard/DashboardHealthScoreCard';
import { DashboardQuickActionsCard } from './dashboard/DashboardQuickActionsCard';
import { DashboardRecentActivity } from './dashboard/DashboardRecentActivity';
import { ReviewPromptModal } from '@/components/ReviewPromptModal';
import { FeedbackPromptModal } from '@/components/FeedbackPromptModal';
import { getOnboardingProgress, computeNextAction } from './dashboard/constants';

export default function DashboardPage() {
  const navigate = useNavigate();
  const [nextActionDismissed, setNextActionDismissed] = useState(false);
  const [weeklyBriefingDismissed, setWeeklyBriefingDismissed] = useState(false);
  const {
    user,
    selectedTrust,
    trusts,
    trustsLoading,
    subscription,
    dashboard,
    loading,
    weeklyBriefing,
    onboardingExpanded,
    setOnboardingExpanded,
    taxDeadlines,
    taxDeadlinesLoading,
    upgradeBannerDismissed,
    setUpgradeBannerDismissed,
    showWpWelcome,
    wpBannerVisible,
    toggleOnboardingStep,
    dismissOnboarding,
    dismissWpWelcome,
    goToTrustDocsFromWp,
    dismissInsight,
    handleCreateDemo,
    restoreChecklist,
  } = useDashboardData();

  // Get insights from dashboard API (single source of truth)
  const insights = dashboard?.governance_insights || [];
  const onboarding = dashboard?.onboarding_state;
  const onboardingProgress = getOnboardingProgress(onboarding, selectedTrust);
  const healthScore = dashboard?.health_score;
  const stats = dashboard?.stats;
  const activities = dashboard?.recent_activity || [];
  const nextAction = computeNextAction(taxDeadlines, onboardingProgress, insights);

  // Progressive disclosure gate — recommendation sections (Today's Focus,
  // Weekly Briefing, Tax Calendar) are noise for new users who haven't
  // finished Getting Started. They only appear once onboarding is complete
  // OR the user has explicitly dismissed the checklist.
  const onboardingComplete =
    onboardingProgress.completed >= onboardingProgress.total ||
    onboarding?.checklist_dismissed === true;

  // Review prompt: show when all onboarding steps are complete OR checklist is dismissed
  const showReviewPrompt = !loading && onboarding && (
    onboardingProgress.completed >= onboardingProgress.total ||
    onboarding.checklist_dismissed === true
  );

  // Feedback prompt: show after user has created 3+ minutes entries
  // total_decisions = minutes_records + minutes_templates counts from backend
  const showFeedbackPrompt = !loading && stats && (stats.total_decisions >= 3);

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
        <DashboardBanners
          wpBannerVisible={wpBannerVisible}
        />

        <div className="page-container">
          <DashboardWpWelcome
            showWpWelcome={showWpWelcome}
            goToTrustDocsFromWp={() => goToTrustDocsFromWp(navigate)}
            dismissWpWelcome={dismissWpWelcome}
          />

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
            <div>
              <p className="text-sm text-muted-foreground mb-6" data-testid="dashboard-loading-text">
                Loading your trust dashboard…
              </p>
              <div className="card-grid">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="card-trust">
                    <div className="skeleton h-6 w-32 mb-4"></div>
                    <div className="skeleton h-20 w-full"></div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <>
              <DashboardNextActionHero
                nextAction={nextActionDismissed ? null : nextAction}
                onDismiss={() => setNextActionDismissed(true)}
              />

              <DashboardOnboardingChecklist
                onboarding={onboarding}
                onboardingProgress={onboardingProgress}
                onboardingExpanded={onboardingExpanded}
                setOnboardingExpanded={setOnboardingExpanded}
                toggleOnboardingStep={toggleOnboardingStep}
                dismissOnboarding={dismissOnboarding}
                restoreChecklist={restoreChecklist}
              />

              {/* Pending Quarterly Draft Hero (Fix 3) */}
              {dashboard?.pending_quarterly_draft && (
                <div className="mb-6 card-trust border-l-4 border-l-gold bg-gold/5" data-testid="quarterly-draft-hero">
                  <div className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-gold/20 to-navy/10 flex items-center justify-center">
                        <FileText className="w-5 h-5 text-gold" />
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

              {/*
               * Phase 2 — recommendations only appear once onboarding is
               * complete or dismissed. New users (Phase 1) only see the
               * Getting Started checklist (which dominates) and the single
               * "Do This Next" hero that reinforces the next onboarding step.
               *
               * Priority order when shown: Today's Focus → Weekly Briefing
               * → Tax Calendar. The "Do This Next" hero (above the checklist)
               * already leads with the single top priority, so these flow as
               * secondary recommendations rather than competing CTAs.
               */}
              {onboardingComplete && (
                <>
                  <DashboardTodaysFocus
                    insights={insights}
                    healthScore={healthScore}
                    dismissInsight={dismissInsight}
                    nextAction={nextAction}
                  />

                  <DashboardWeeklyBriefing
                    weeklyBriefing={weeklyBriefingDismissed ? [] : weeklyBriefing}
                    insights={insights}
                    onDismiss={() => setWeeklyBriefingDismissed(true)}
                  />

                  <DashboardTaxCalendar
                    selectedTrust={selectedTrust}
                    taxDeadlines={taxDeadlines}
                    taxDeadlinesLoading={taxDeadlinesLoading}
                  />
                </>
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
                <DashboardHealthScoreCard
                  dashboard={dashboard}
                  selectedTrust={selectedTrust}
                  healthScore={healthScore}
                  isNewTrust={isNewTrust}
                />
                <DashboardQuickActionsCard stats={stats} navigate={navigate} />
              </div>

              <DashboardRecentActivity activities={activities} stats={stats} />
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* Review prompt — triggers when onboarding is complete or dismissed */}
      <ReviewPromptModal show={showReviewPrompt} />

      {/* Feedback prompt — triggers after 3rd minutes entry created */}
      <FeedbackPromptModal show={showFeedbackPrompt} />
    </div>
  );
}