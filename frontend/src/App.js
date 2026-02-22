import { useEffect, useRef, useState } from "react";
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
import { AuthProvider, useAuth } from "@/context/AuthContext";

// Protected Route component
const ProtectedRoute = ({ children }) => {
  const { user, loading, checkAuth } = useAuth();
  const location = useLocation();
  const hasChecked = useRef(false);

  useEffect(() => {
    // Skip if user data passed from AuthCallback via location state
    if (location.state?.user) {
      return;
    }
    
    // Only check once
    if (!hasChecked.current && !user) {
      hasChecked.current = true;
      checkAuth();
    }
  }, [checkAuth, user, location.state]);

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

  if (!user && !location.state?.user) {
    return <Navigate to="/" replace />;
  }

  return children;
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
        <ProtectedRoute>
          <DashboardPage />
        </ProtectedRoute>
      } />
      <Route path="/minutes" element={
        <ProtectedRoute>
          <MinutesPage />
        </ProtectedRoute>
      } />
      <Route path="/minutes/new" element={
        <ProtectedRoute>
          <NewMinutesPage />
        </ProtectedRoute>
      } />
      <Route path="/distributions" element={
        <ProtectedRoute>
          <DistributionsPage />
        </ProtectedRoute>
      } />
      <Route path="/expenses" element={
        <ProtectedRoute>
          <ExpensesPage />
        </ProtectedRoute>
      } />
      <Route path="/governance" element={
        <ProtectedRoute>
          <GovernancePage />
        </ProtectedRoute>
      } />
      <Route path="/settings" element={
        <ProtectedRoute>
          <SettingsPage />
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
