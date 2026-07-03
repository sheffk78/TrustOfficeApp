import { useState, useEffect } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { Lock, Eye, EyeOff, ArrowLeft, Loader2, CheckCircle, AlertTriangle } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');
  const coupon = searchParams.get('coupon');
  
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) {
      setVerifying(false);
      return;
    }
    
    // Verify token is valid
    const verifyToken = async () => {
      try {
        const response = await fetch(`${API}/api/auth/verify-reset-token?token=${token}`);
        if (response.ok) {
          setTokenValid(true);
        }
      } catch (error) {
        console.error('Token verification failed:', error);
      } finally {
        setVerifying(false);
      }
    };
    
    verifyToken();
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    
    if (password !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    
    setLoading(true);
    
    try {
      const response = await fetch(`${API}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password })
      });
      
      if (response.ok) {
        setSuccess(true);
        toast.success('Password reset successfully!');
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to reset password');
      }
    } catch (error) {
      toast.error('Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Loading state
  if (verifying) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-subtle-bg p-4">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-navy mx-auto mb-4" />
          <p className="text-muted-foreground">Verifying reset link...</p>
        </div>
      </div>
    );
  }

  // Invalid/missing token
  if (!token || !tokenValid) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-subtle-bg p-4">
        <div className="w-full max-w-md">
          <div className="card-trust corner-mark text-center" data-testid="invalid-token-card">
            <div className="w-16 h-16 mx-auto mb-4 bg-error/10 flex items-center justify-center">
              <AlertTriangle className="w-8 h-8 text-error" />
            </div>
            <h2 className="font-serif text-xl text-navy mb-2">Invalid or Expired Link</h2>
            <p className="text-muted-foreground mb-6">
              This password reset link is invalid or has expired. Please request a new one.
            </p>
            <div className="space-y-3">
              <Link to="/forgot-password">
                <Button className="btn-primary w-full">
                  Request New Link
                </Button>
              </Link>
              <Link to="/">
                <Button className="btn-secondary w-full">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Back to Login
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Success state
  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-subtle-bg p-4">
        <div className="w-full max-w-md">
          <div className="card-trust corner-mark text-center" data-testid="success-card">
            <div className="w-16 h-16 mx-auto mb-4 bg-success/10 flex items-center justify-center">
              <CheckCircle className="w-8 h-8 text-success" />
            </div>
            <h2 className="font-serif text-xl text-navy mb-2">Password Reset Complete</h2>
            <p className="text-muted-foreground mb-6">
              {coupon 
                ? "Your password is set. Now choose your TrustOffice plan to activate your trust. Your $50 WingPoint discount will be applied at checkout."
                : "Your password has been successfully reset. You can now log in with your new password."
              }
            </p>
            <Button 
              onClick={() => navigate(coupon ? `/pricing?coupon=${coupon}` : '/')}
              className="btn-primary w-full"
              data-testid="go-to-login-btn"
            >
              {coupon ? 'Choose Your Plan' : 'Go to Login'}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-subtle-bg p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 mx-auto mb-4 bg-navy flex items-center justify-center">
            <span className="font-serif text-3xl text-white font-bold">T</span>
          </div>
          <h1 className="font-serif text-2xl text-navy">TrustOffice</h1>
        </div>

        <div className="card-trust corner-mark" data-testid="reset-password-card">
          <div className="text-center mb-6">
            <h2 className="font-serif text-xl text-navy mb-2">Create New Password</h2>
            <p className="text-sm text-muted-foreground">
              Enter your new password below. Make sure it's at least 8 characters.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="password" className="label-trust">New Password</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min. 8 characters"
                  className="input-trust pl-10 pr-10"
                  disabled={loading}
                  data-testid="new-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-navy"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div>
              <Label htmlFor="confirmPassword" className="label-trust">Confirm Password</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="confirmPassword"
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm your password"
                  className="input-trust pl-10"
                  disabled={loading}
                  data-testid="confirm-password-input"
                />
              </div>
            </div>

            {/* Password requirements */}
            <div className="text-xs text-muted-foreground space-y-1">
              <p className={password.length >= 8 ? 'text-success' : ''}>
                {password.length >= 8 ? '✓' : '○'} At least 8 characters
              </p>
              <p className={password && password === confirmPassword ? 'text-success' : ''}>
                {password && password === confirmPassword ? '✓' : '○'} Passwords match
              </p>
            </div>

            <Button 
              type="submit" 
              className="btn-primary w-full"
              disabled={loading || password.length < 8 || password !== confirmPassword}
              data-testid="reset-password-btn"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Resetting...
                </>
              ) : (
                'Reset Password'
              )}
            </Button>
          </form>

          <div className="mt-6 text-center">
            <Link 
              to="/" 
              className="text-sm text-navy hover:text-navy/70 flex items-center justify-center gap-2"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
