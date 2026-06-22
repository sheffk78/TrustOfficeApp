import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { Mail, ArrowLeft, Loader2, CheckCircle, AlertCircle, X } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Clear previous errors
    setFormError('');
    
    if (!email) {
      setFormError('Please enter your email address to continue.');
      return;
    }
    
    // Basic email format validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setFormError('Please enter a valid email address (e.g., you@example.com).');
      return;
    }
    
    setLoading(true);
    
    try {
      const response = await fetch(`${API}/api/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      
      if (response.ok) {
        setSubmitted(true);
      } else {
        const data = await response.json().catch(() => ({}));
        const msg = data.detail || 'Unable to process your request. Please try again or contact support.';
        setFormError(msg);
        toast.error(msg);
      }
    } catch (error) {
      const msg = 'Network error — please check your internet connection and try again.';
      setFormError(msg);
      toast.error('Failed to send reset email. Please try again.');
    } finally {
      setLoading(false);
    }
  };

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

        <div className="card-trust corner-mark" data-testid="forgot-password-card">
          {submitted ? (
            // Success state
            <div className="text-center py-4">
              <div className="w-16 h-16 mx-auto mb-4 bg-success/10 flex items-center justify-center">
                <CheckCircle className="w-8 h-8 text-success" />
              </div>
              <h2 className="font-serif text-xl text-navy mb-2">Check Your Email</h2>
              <p className="text-muted-foreground mb-6">
                If an account exists with <strong>{email}</strong>, you'll receive a password reset link shortly.
              </p>
              <p className="text-sm text-muted-foreground mb-6">
                The link will expire in 1 hour. Don't forget to check your spam folder.
              </p>
              <Link to="/">
                <Button className="btn-secondary w-full">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Back to Login
                </Button>
              </Link>
            </div>
          ) : (
            // Form state
            <>
              <div className="text-center mb-6">
                <h2 className="font-serif text-xl text-navy mb-2">Forgot Password?</h2>
                <p className="text-sm text-muted-foreground">
                  Enter your email address and we'll send you a link to reset your password.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                {/* Inline error state */}
                {formError && (
                  <div className="p-3 bg-error/10 border border-error/20 flex items-start gap-2" data-testid="forgot-password-error">
                    <AlertCircle className="w-4 h-4 text-error flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-error">Unable to send reset link</p>
                      <p className="text-xs text-error/80 mt-0.5">{formError}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormError('')}
                      className="text-error/60 hover:text-error flex-shrink-0"
                      aria-label="Dismiss error"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
                <div>
                  <Label htmlFor="email" className="label-trust">Email Address</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => { setEmail(e.target.value); if (formError) setFormError(''); }}
                      placeholder="you@example.com"
                      className={`input-trust pl-10 ${formError ? 'border-error/40' : ''}`}
                      disabled={loading}
                      data-testid="forgot-email-input"
                    />
                  </div>
                </div>

                <Button 
                  type="submit" 
                  className="btn-primary w-full"
                  disabled={loading}
                  data-testid="send-reset-btn"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    'Send Reset Link'
                  )}
                </Button>
              </form>

              <div className="mt-6 text-center">
                <Link 
                  to="/" 
                  className="text-sm text-navy hover:text-gold flex items-center justify-center gap-2"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to Login
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
