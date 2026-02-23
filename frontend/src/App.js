import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import LoginPage from "@/pages/LoginPage";
import SignUpPage from "@/pages/SignUpPage";
import AuthCallback from "@/pages/AuthCallback";
import DashboardPage from "@/pages/DashboardPage";
import MinutesPage from "@/pages/MinutesPage";
import NewMinutesPage from "@/pages/NewMinutesPage";
import DistributionsPage from "@/pages/DistributionsPage";
import ExpensesPage from "@/pages/ExpensesPage";
import GovernancePage from "@/pages/GovernancePage";
import SettingsPage from "@/pages/SettingsPage";
import OnboardingPage from "@/pages/OnboardingPage";
import CalendarPage from "@/pages/CalendarPage";
import EntitiesPage from "@/pages/EntitiesPage";
import EntityDetailPage from "@/pages/EntityDetailPage";
import StructurePage from "@/pages/StructurePage";
import CompensationPage from "@/pages/CompensationPage";
import BillingPage from "@/pages/BillingPage";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { SubscriptionGate } from "@/components/SubscriptionGate";

// Protected Route component
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  // If user was passed via navigation state (e.g., from AuthCallback), use it
  const hasUserFromState = location.state?.user;

  // Show loading spinner while auth is being verified
  if (loading) {
    return (
      <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto mb-4"></div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading</p>
        </div>
      </div>
    );
  }

  // After loading is complete, check if user is authenticated
  if (!user && !hasUserFromState) {
    return <Navigate to="/" replace />;
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

// App Router with session_id detection
const AppRouter = () => {
  const location = useLocation();

  // CRITICAL: Check URL fragment synchronously for session_id (OAuth callback)
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }

  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route path="/signup" element={<SignUpPage />} />
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
      <Route path="/minutes/new" element={
        <SubscriptionProtectedRoute>
          <NewMinutesPage />
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
      <Route path="/entities" element={
        <SubscriptionProtectedRoute>
          <EntitiesPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/entities/:entityId" element={
        <SubscriptionProtectedRoute>
          <EntityDetailPage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/structure" element={
        <SubscriptionProtectedRoute>
          <StructurePage />
        </SubscriptionProtectedRoute>
      } />
      <Route path="/governance" element={
        <SubscriptionProtectedRoute>
          <GovernancePage />
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
    </Routes>
  );
};

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRouter />
        <Toaster position="top-right" />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
