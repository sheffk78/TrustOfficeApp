import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Check, ArrowRight } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Use XMLHttpRequest for maximum compatibility
const xhrPost = (url, data, token = null) => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Accept', 'application/json');
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }
    
    xhr.onreadystatechange = function() {
      if (xhr.readyState === 4) {
        try {
          const response = xhr.responseText ? JSON.parse(xhr.responseText) : {};
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(response);
          } else {
            reject(new Error(response.detail || `Request failed`));
          }
        } catch (e) {
          reject(new Error('Invalid server response'));
        }
      }
    };
    
    xhr.onerror = function() {
      reject(new Error('Network error'));
    };
    
    xhr.send(data ? JSON.stringify(data) : null);
  });
};

const features = [
  'Unlimited trust records',
  'Guided minutes templates',
  'Schedule A asset tracking',
  'Distribution management',
  'PDF export with watermark control',
  'Governance health scoring',
  'Email notifications',
  'Benevolence mode for charitable trusts'
];

export default function PricingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const [loading, setLoading] = useState(null);
  const [couponApplied, setCouponApplied] = useState(false);
  
  // Get coupon from URL if present
  const couponCode = searchParams.get('coupon') || searchParams.get('promo');
  
  useEffect(() => {
    if (couponCode) {
      setCouponApplied(true);
      toast.success(`Coupon "${couponCode}" will be applied at checkout`);
    }
  }, [couponCode]);

  const handleCheckout = async (planType) => {
    // If not logged in, redirect to signup first
    if (!user) {
      // Store intent in sessionStorage so we can continue after signup
      sessionStorage.setItem('checkout_intent', JSON.stringify({
        plan: planType,
        coupon: couponCode
      }));
      toast.info('Please create an account first to start your subscription');
      navigate('/signup');
      return;
    }

    setLoading(planType);
    
    try {
      const token = localStorage.getItem('auth_token');
      const baseUrl = window.location.origin;
      
      const checkoutData = {
        plan_type: planType,
        success_url: `${baseUrl}/dashboard?welcome=true`,
        cancel_url: `${baseUrl}/pricing${couponCode ? `?coupon=${couponCode}` : ''}`
      };
      
      // Add coupon if present
      if (couponCode) {
        checkoutData.promotion_code = couponCode;
      }
      
      // Add Rewardful referral ID for affiliate tracking
      if (typeof window !== 'undefined' && window.Rewardful && window.Rewardful.referral) {
        checkoutData.referral_id = window.Rewardful.referral;
      }
      
      const result = await xhrPost(
        `${API_URL}/api/subscription/create-checkout`,
        checkoutData,
        token
      );
      
      if (result.checkout_url) {
        window.location.href = result.checkout_url;
      } else {
        throw new Error('Failed to create checkout session');
      }
    } catch (error) {
      console.error('Checkout error:', error);
      toast.error(error.message || 'Failed to start checkout');
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="min-h-screen bg-subtle-bg">
      {/* Header */}
      <header className="bg-navy text-white py-6 px-8">
        <div className="max-w-6xl mx-auto flex justify-between items-center">
          <Link to="/" className="flex items-center gap-3">
            <img 
              src="https://customer-assets.emergentagent.com/job_98ad4c89-4a05-4aed-ab1d-a934650bd7f4/artifacts/5h7i559r_Trust%20Office%20Logo%20%281%29.svg"
              alt="TrustOffice"
              className="h-8 brightness-0 invert"
            />
          </Link>
          {user ? (
            <Link to="/dashboard" className="text-sm hover:text-gold transition-colors">
              Go to Dashboard
            </Link>
          ) : (
            <Link to="/login" className="text-sm hover:text-gold transition-colors">
              Sign In
            </Link>
          )}
        </div>
      </header>

      {/* Hero */}
      <section className="py-16 px-8 text-center">
        <h1 className="font-serif text-4xl md:text-5xl text-navy mb-4">
          Trust Governance Made Simple
        </h1>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-4">
          The workspace for trustees who take their duties seriously.
        </p>
        {couponApplied && (
          <div className="inline-block bg-gold/20 text-gold-dark px-4 py-2 rounded-full text-sm font-medium">
            Coupon "{couponCode}" will be applied at checkout
          </div>
        )}
      </section>

      {/* Pricing Cards */}
      <section className="pb-20 px-8">
        <div className="max-w-4xl mx-auto grid md:grid-cols-2 gap-8">
          {/* Monthly Plan */}
          <div className="card-trust corner-mark p-8">
            <div className="text-center mb-8">
              <h2 className="font-serif text-2xl text-navy mb-2">Monthly</h2>
              <div className="flex items-baseline justify-center gap-1">
                <span className="font-serif text-5xl text-navy">$79</span>
                <span className="text-muted-foreground">/month</span>
              </div>
              <p className="text-sm text-muted-foreground mt-2">
                Billed monthly, cancel anytime
              </p>
            </div>
            
            <ul className="space-y-3 mb-8">
              {features.map((feature, i) => (
                <li key={i} className="flex items-start gap-3">
                  <Check className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                  <span className="text-sm">{feature}</span>
                </li>
              ))}
            </ul>
            
            <Button 
              onClick={() => handleCheckout('monthly')}
              disabled={loading !== null}
              className="w-full btn-secondary"
              data-testid="monthly-checkout-btn"
            >
              {loading === 'monthly' ? 'Loading...' : 'Get Started'}
              <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </div>

          {/* Annual Plan */}
          <div className="card-trust corner-mark p-8 border-2 border-gold relative overflow-visible mt-4">
            <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gold text-navy px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-full shadow-md whitespace-nowrap z-10">
              Best Value
            </div>
            
            <div className="text-center mb-8">
              <h2 className="font-serif text-2xl text-navy mb-2">Annual</h2>
              <div className="flex items-baseline justify-center gap-1">
                <span className="font-serif text-5xl text-navy">$790</span>
                <span className="text-muted-foreground">/year</span>
              </div>
              <p className="text-sm text-green-600 font-medium mt-2">
                Save $158 (2 months free)
              </p>
            </div>
            
            <ul className="space-y-3 mb-8">
              {features.map((feature, i) => (
                <li key={i} className="flex items-start gap-3">
                  <Check className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                  <span className="text-sm">{feature}</span>
                </li>
              ))}
            </ul>
            
            <Button 
              onClick={() => handleCheckout('annual')}
              disabled={loading !== null}
              className="w-full btn-primary"
              data-testid="annual-checkout-btn"
            >
              {loading === 'annual' ? 'Loading...' : 'Get Started'}
              <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </div>
        </div>

        {/* Trial Note */}
        <p className="text-center text-sm text-muted-foreground mt-8 max-w-xl mx-auto">
          Subscribe to start — $79/month or $790/year. The trust pays for governance tools the same way it pays for legal counsel.
        </p>
      </section>

      {/* Footer */}
      <footer className="bg-navy/5 py-8 px-8 text-center text-sm text-muted-foreground">
        <p>&copy; {new Date().getFullYear()} TrustOffice. All rights reserved.</p>
        <div className="mt-2 space-x-4">
          <a href="https://trustoffice.app/support" className="hover:text-navy">Support</a>
          <a href="https://trustoffice.app/privacy-policy/" className="hover:text-navy">Privacy</a>
          <a href="https://trustoffice.app/terms-of-service/" className="hover:text-navy">Terms</a>
        </div>
      </footer>
    </div>
  );
}
