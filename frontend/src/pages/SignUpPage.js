import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

// Checkout-first model (2026-09-04): free account registration is disabled.
// This page used to host the signup form; every entry point now routes to
// /pricing where the guest-checkout modal collects email/name and Stripe
// provisions the account on payment (webhook: _provision_guest_account).
//
// WingPoint / referral / coupon params are carried through to /pricing so
// attribution and coupons survive the redirect.
export default function SignUpPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    // Preserve WingPoint attribution for the post-payment webhook
    const wpRef = searchParams.get('wp_ref');
    const trustName = searchParams.get('trust_name');
    if (wpRef) sessionStorage.setItem('wp_ref', wpRef);
    if (trustName) sessionStorage.setItem('wp_trust_name', decodeURIComponent(trustName));

    // Carry referral + coupon + WP params to pricing
    const pricingParams = new URLSearchParams();
    const ref = searchParams.get('ref');
    const coupon = searchParams.get('coupon');
    const plan = searchParams.get('plan');
    if (ref) pricingParams.set('ref', ref);
    if (coupon) pricingParams.set('coupon', coupon);
    if (ref && ref.toLowerCase() === 'wp') pricingParams.set('wp', '1');
    if (plan) pricingParams.set('plan', plan);

    const qs = pricingParams.toString();
    navigate(qs ? `/pricing?${qs}` : '/pricing', { replace: true });
  }, [navigate, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-navy/5" data-testid="signup-page">
      <div className="text-center">
        <p className="text-navy font-medium">TrustOffice is subscribe-first.</p>
        <p className="text-sm text-muted-foreground mt-1">Redirecting you to pricing…</p>
      </div>
    </div>
  );
}