import React, { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { ImpersonationBanner } from "@/components/ImpersonationBanner";
import LoginPage from "@/pages/LoginPage";
import SignUpPage from "@/pages/SignUpPage";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import AuthCallback from "@/pages/AuthCallback";
import DashboardPage from "@/pages/DashboardPage";
import MinutesPage from "@/pages/MinutesPage";
import MinutesDetailPage from "@/pages/MinutesDetailPage";
import NewMinutesPage from "@/pages/NewMinutesPage";
import MinutesTemplatesPage from "@/pages/MinutesTemplatesPage";
import MinutesTemplateFormPage from "@/pages/MinutesTemplateFormPage";
import GuidedMinutesPage from "@/pages/GuidedMinutesPage";
import DistributionsPage from "@/pages/DistributionsPage";
import ExpensesPage from "@/pages/ExpensesPage";
import GovernancePage from "@/pages/GovernancePage";
import SettingsPage from "@/pages/SettingsPage";
import OnboardingPage from "@/pages/OnboardingPage";
import CalendarPage from "@/pages/CalendarPage";
import EntityDetailPage from "@/pages/EntityDetailPage";
import StructuresPage from "@/pages/StructuresPage";
import CompensationPage from "@/pages/CompensationPage";
import BillingPage from "@/pages/BillingPage";
import ScheduleAPage from "@/pages/ScheduleAPage";
import BenevolencePage from "@/pages/BenevolencePage";
import PricingPage from "@/pages/PricingPage";
import AuthorityPage from "@/pages/AuthorityPage";
import RetroactiveMinutesPage from "@/pages/RetroactiveMinutesPage";
import AuditTrailPage from "@/pages/AuditTrailPage";
import BeneficiariesPage from "@/pages/BeneficiariesPage";
import AffiliatePage from "@/pages/AffiliatePage";
import AdminPage from "@/pages/AdminPage";
import TaxCalendarPage from "@/pages/TaxCalendarPage";
import StateCompliancePage from "@/pages/StateCompliancePage";
import NotFoundPage from "@/pages/NotFoundPage";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { UpgradeModalProvider } from "@/context/UpgradeModalContext";
import { SubscriptionGate } from "@/components/SubscriptionGate";

// GA4 page view tracking for SPA navigation
const useGA4PageTracking = () => {
  const location = useLocation();
  
  useEffect(() => {
    // Ensure gtag is available and send page view on route change
    if (typeof window.gtag === 'function') {
      window.gtag('config', 'G-MT6FBPRE60', {
        page_path: location.pathname + location.search,
        page_title: document.title
      });
    }
  }, [location]);
};

// Protected Route component
const ProtectedRoute = ({ children }) => {
  const { user, loading, trusts, trustsLoading } = useAuth();
  const location = useLocation();
  const [loadingTimeout, setLoadingTimeout] = useState(false);

  // Timeout to prevent infinite loading - after 10 seconds, proceed anyway
  useEffect(() => {
    const timer = setTimeout(() => {
      if (loading || trustsLoading) {
        console.warn('[ProtectedRoute] Loading timeout reached, proceeding anyway');
        setLoadingTimeout(true);
      }
    }, 10000);
    return () => clearTimeout(timer);
  }, [loading, trustsLoading]);

  // If user was passed via navigation state (e.g., from AuthCallback), use it
  const hasUserFromState = location.state?.user;

  // Check if this is an OAuth callback route
  const isCallback = location.pathname === '/auth/callback' || location.pathname === '/auth/google/callback';

  // Check if user is admin - admins skip onboarding
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';
  
  // Check for stored token
  const hasToken = localStorage.getItem('auth_token') !== null;

  // IMMEDIATE redirect: no token, no user, not loading — go to login
  if (!hasToken && !user && !loading) {
    return <Navigate to="/" replace />;
  }

  // Show loading spinner while auth is being verified (but not for trusts on onboarding)
  const isOnboarding = location.pathname.includes('/onboarding');
  const shouldShowLoading = (loading || (!isOnboarding && trustsLoading)) && !loadingTimeout;
  
  if (shouldShowLoading) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto mb-4"></div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading</p>
        </div>
      </div>
    );
  }

  // After loading timeout, if we still have a token, don't redirect - let user see the page
  // Only redirect to login if there's genuinely no token
  if (!hasToken && !user && !hasUserFromState && !isCallback) {
    return <Navigate to="/" replace />;
  }

  // Redirect new users (no trusts) to onboarding, except:
  // - Already on onboarding
  // - User is admin
  // - Still loading trusts
  // - User has explicit "skip onboarding" in localStorage (set when clicking read-only mode)
  // - User has a token but user data hasn't loaded yet (loading timeout scenario)
  const skipOnboarding = localStorage.getItem('skip_onboarding') === 'true';
  if (user && !trustsLoading && trusts && trusts.length === 0 && !isOnboarding && !isAdmin && !skipOnboarding) {
    return <Navigate to="/onboarding" replace />;
  }

  return children;
};

// Protected Route with Subscription Gate (for routes that require active subscription)
const SubscriptionProtectedRoute = ({ children }) => {
  return (
    <ProtectedRoute>
      <SubscriptionGate>
        {children}
      </SubscriptionGate>
    </ProtectedRoute>
  );
};

// App Router with session_id detection and GA4 tracking
const AppRouter = () => {
  const location = useLocation();
  
  // Track page views in GA4 on route changes
  useGA4PageTracking();

  // CRITICAL: Check URL fragment synchronously for session_id (OAuth callback)
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }

  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignUpPage />} />
      <Route path="/register" element={<SignUpPage />} />
      <Route path="/pricing" element={<PricingPage />} />
      <Route path="/affiliate" element={<AffiliatePage />} />
      <Route path="/help" element={<Navigate to="/dashboard" replace />} />
      <Route path="/about" element={<Navigate to="/" replace />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/auth/google/callback" element={<AuthCallback />} />
      <Route path="/onboarding" element={
        <ProtectedRoute>
          <OnboardingPage />
        </ProtectedRoute>
      } />
      <Route path="/dashboard" element={
        <SubscriptionProtectedRoute>
          <DashboardPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/calendar" element={
        <SubscriptionProtectedRoute>
          <CalendarPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/minutes" element={
        <SubscriptionProtectedRoute>
          <MinutesPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/minutes/:minutesId" element={
        <SubscriptionProtectedRoute>
          <MinutesDetailPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/minutes/new" element={
        <SubscriptionProtectedRoute>
          <NewMinutesPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/minutes/templates" element={
        <SubscriptionProtectedRoute>
          <MinutesTemplatesPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/minutes/template/:templateType" element={
        <SubscriptionProtectedRoute>
          <MinutesTemplateFormPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/guided-minutes" element={
        <SubscriptionProtectedRoute>
          <GuidedMinutesPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/schedule-a" element={
        <SubscriptionProtectedRoute>
          <ScheduleAPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/trust/units" element={
        <Navigate to="/beneficiaries" replace />
      } />
      <Route path="/trust/beneficiaries" element={
        <Navigate to="/beneficiaries" replace />
      } />
      <Route path="/beneficiaries" element={
        <SubscriptionProtectedRoute>
          <BeneficiariesPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/benevolence" element={
        <SubscriptionProtectedRoute>
          <BenevolencePage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/distributions" element={
        <SubscriptionProtectedRoute>
          <DistributionsPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/compensation" element={
        <SubscriptionProtectedRoute>
          <CompensationPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/expenses" element={
        <SubscriptionProtectedRoute>
          <ExpensesPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/structures" element={
        <SubscriptionProtectedRoute>
          <StructuresPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/authority" element={
        <SubscriptionProtectedRoute>
          <AuthorityPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/retroactive-minutes" element={
        <SubscriptionProtectedRoute>
          <RetroactiveMinutesPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/audit-trail" element={
        <SubscriptionProtectedRoute>
          <AuditTrailPage />
        </SubscriptionProtectedRoute>
      } />
      {/* Redirect old routes to new unified Structures page */}
      <Route path="/entities" element={<Navigate to="/structures?tab=entities" replace />} />
      <Route path="/structure" element={<Navigate to="/structures?tab=hierarchy" replace />} />
      <Route path="/entities/:entityId" element={
        <SubscriptionProtectedRoute>
          <EntityDetailPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/governance" element={
        <SubscriptionProtectedRoute>
          <GovernancePage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/tax-calendar" element={
        <SubscriptionProtectedRoute>
          <TaxCalendarPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/state-compliance" element={
        <SubscriptionProtectedRoute>
          <StateCompliancePage />
        </SubscriptionProtectedRoute>
      } />
      {/* Settings and Billing are accessible without active subscription */}
      <Route path="/settings" element={
        <ProtectedRoute>
          <SettingsPage />
        </ProtectedRoute>
      } />
      <Route path="/settings/billing" element={
        <ProtectedRoute>
          <BillingPage />
        </ProtectedRoute>
      } />
      {/* Admin panel - only accessible to admins */}
      <Route path="/admin" element={
        <ProtectedRoute>
          <AdminPage />
        </ProtectedRoute>
      } />

      {/* Catch-all 404 route - must be last */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
};

function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <UpgradeModalProvider>
            <ImpersonationBanner />
            <AppRouter />
            <Toaster position="top-right" />
          </UpgradeModalProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}

export default App;
