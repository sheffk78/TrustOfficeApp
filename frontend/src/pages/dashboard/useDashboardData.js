import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '../../utils/errors';
import { trackPurchaseConversion } from '@/utils/analytics';
import { useSearchParams } from 'react-router-dom';

/**
 * Custom hook that encapsulates all dashboard data fetching and state.
 * Handles: dashboard data, tax deadlines, weekly briefing, onboarding,
 * WingPoint welcome modal, and dismissible upgrade banner.
 */
export function useDashboardData() {
  const { user, selectedTrust, trusts, trustsLoading, loadTrusts, seedDemoData, subscription } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [weeklyBriefing, setWeeklyBriefing] = useState(null);

  // Onboarding accordion expansion state.
  // Defaults to EXPANDED so new users (onboarding incomplete) see the
  // Getting Started checklist dominating the dashboard. The checklist
  // component returns null when onboarding is complete/dismissed, so this
  // default only matters for the incomplete case.
  const [onboardingExpanded, setOnboardingExpanded] = useState(true);

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

      // Track purchase conversion for Google Ads + GA4
      trackPurchaseConversion({
        plan_type: user?.subscription?.plan_type || 'trustee',
        billing_period: user?.subscription?.billing_period || 'monthly',
        transaction_id: searchParams.get('session_id') || `checkout_${Date.now()}`,
      });

      // Remove the query param to prevent showing again on refresh
      searchParams.delete('welcome');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams, user]);

  // WingPoint welcome modal — show ONLY for WingPoint-provisioned users
  // Triggered by ?wp=1 param (set by WingPoint redirect flow) or a wp_origin flag on the user
  useEffect(() => {
    const wpParam = searchParams.get('wp');
    const dismissed = localStorage.getItem('wp_welcome_dismissed');
    const isWpUser = user?.wp_origin === true || user?.wp_origin === 'true';

    if (wpParam === '1' || (isWpUser && !dismissed)) {
      setShowWpWelcome(true);
      setWpBannerVisible(false);
    } else if (isWpUser && dismissed) {
      setWpBannerVisible(true);
    }
  }, [searchParams, user]);

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
    if (selectedTrust.benevolence_enabled) {
      setTaxDeadlines([]);
      setTaxDeadlinesLoading(false);
      return;
    }
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

  const toggleOnboardingStep = async (field, currentValue) => {
    try {
      // The consolidated Trustee Roles step controls the required successor
      // setup flag. Preserve the optional/deferred protector decision.
      const update = field === 'trustee_roles'
        ? { successor_trustee_added: !currentValue }
        : { [field]: !currentValue };
      const res = await fetchWithAuth('/onboarding', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
      });
      if (!res.ok) {
        toast.error('Failed to update. Please try again.');
        return;
      }
      // Update local state immediately
      setDashboard(prev => ({
        ...prev,
        onboarding_state: {
          ...prev.onboarding_state,
          ...(field === 'trustee_roles'
            ? { successor_trustee_added: !currentValue }
            : { [field]: !currentValue }),
        }
      }));
    } catch (error) {
      console.error('Failed to toggle onboarding step:', error);
      toast.error('Failed to update. Please try again.');
    }
  };

  const dismissOnboarding = async () => {
    try {
      const res = await fetchWithAuth('/onboarding/dismiss', { method: 'POST' });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        toast.error(errBody.detail || 'Failed to dismiss. Please try again.');
        return;
      }
      setDashboard(prev => ({
        ...prev,
        onboarding_state: { ...prev.onboarding_state, checklist_dismissed: true }
      }));
    } catch (error) {
      console.error('Failed to dismiss onboarding:', error);
      toast.error('Failed to dismiss. Please try again.');
    }
  };

  const dismissWpWelcome = () => {
    localStorage.setItem('wp_welcome_dismissed', 'true');
    setShowWpWelcome(false);
    setWpBannerVisible(true);
  };

  const goToTrustDocsFromWp = (navigate) => {
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

  const restoreChecklist = async () => {
    try {
      const res = await fetchWithAuth('/onboarding/dismiss', { method: 'DELETE' });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        toast.error(errBody.detail || 'Failed to restore checklist.');
        return;
      }
      window.location.reload();
    } catch (error) {
      toast.error('Failed to restore checklist. Please try again.');
    }
  };

  return {
    user,
    selectedTrust,
    trusts,
    trustsLoading,
    loadTrusts,
    subscription,
    dashboard,
    setDashboard,
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
    loadDashboardData,
    toggleOnboardingStep,
    dismissOnboarding,
    dismissWpWelcome,
    goToTrustDocsFromWp,
    dismissInsight,
    handleCreateDemo,
    restoreChecklist,
  };
}