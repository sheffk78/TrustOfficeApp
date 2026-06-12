import { useEffect, useState, useRef } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Gift, Sparkles, ArrowRight, Clock, Calendar } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

/**
 * GiftedBanner — Shows a sticky horizontal banner at the top of the app
 * for users who have been gifted admin-granted access.
 * 
 * Design based on ImpersonationBanner (fixed/sticky at top of viewport).
 * Warm, appreciative tone — "We've gifted you..." not "You're on a trial."
 * 
 * Gift type messaging:
 * - 14-day: "You've been gifted 14 days of TrustOffice Pro — N days remaining"
 * - Monthly: "You've been gifted 1 month of TrustOffice Pro — expires DATE"
 * - Annual: "You've been gifted 1 year of TrustOffice Pro — expires DATE"
 * 
 * Urgency (≤3 days remaining): "Your gifted access ends soon — upgrade to keep your workspace"
 */
export const GiftedBanner = () => {
  const { user, subscription } = useAuth();
  const hasTrackedView = useRef(false);
  const [dismissed, setDismissed] = useState(false);

  // ADMIN BYPASS: Never show for admins
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';
  
  // Only show for gifted users with active subscription
  const showBanner = !isAdmin && 
                     subscription?.is_gifted && 
                     subscription?.is_active && 
                     !dismissed;

  // Check for gift type specific info
  const giftType = subscription?.gift_type || '14day';
  const daysRemaining = subscription?.gift_days_remaining ?? subscription?.trial_days_remaining;

  // Format gift type for display
  const getGiftLabel = () => {
    switch (giftType) {
      case '14day': return '14 days';
      case 'monthly': return '1 month';
      case 'annual': return '1 year';
      default: return '14 days';
    }
  };

  const getGiftExpiryLabel = () => {
    if (giftType === '14day' && daysRemaining !== null && daysRemaining !== undefined) {
      return `${daysRemaining} day${daysRemaining !== 1 ? 's' : ''} remaining`;
    }
    if (subscription?.trial_days_remaining && giftType === '14day') {
      return `${subscription.trial_days_remaining} day${subscription.trial_days_remaining !== 1 ? 's' : ''} remaining`;
    }
    return '';
  };

  // Track banner view once
  useEffect(() => {
    if (showBanner && !hasTrackedView.current) {
      try {
        if (typeof window.gtag === 'function') {
          window.gtag('event', 'gifted_banner_viewed', {
            gift_type: giftType,
            days_remaining: daysRemaining
          });
        }
      } catch (e) {
        console.error('Failed to track banner view:', e);
      }
      hasTrackedView.current = true;
    }
  }, [showBanner, giftType, daysRemaining]);

  if (!showBanner) return null;

  const handleUpgradeClick = () => {
    try {
      if (typeof window.gtag === 'function') {
        window.gtag('event', 'gifted_banner_clicked', {
          gift_type: giftType,
          days_remaining: daysRemaining
        });
      }
    } catch (e) {
      console.error('Failed to track banner click:', e);
    }
  };

  const isUrgent = giftType === '14day' && daysRemaining !== null && daysRemaining <= 3;

  return (
    <div className="fixed top-0 left-0 right-0 z-[90] bg-gradient-to-r from-gold to-gold/90 text-navy shadow-lg" data-testid="gifted-banner">
      <div className="flex items-center justify-between px-4 py-2.5 max-w-7xl mx-auto lg:ml-64">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center gap-2 bg-white/20 rounded-full px-3 py-1 flex-shrink-0">
            <Gift className="w-4 h-4" />
            <span className="text-xs font-bold uppercase tracking-wider">Gifted</span>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold truncate">
              {isUrgent
                ? 'Your gifted access ends soon — upgrade to keep your workspace'
                : `You've been gifted ${getGiftLabel()} of TrustOffice Pro`
              }
            </p>
            <p className="text-xs text-navy/70 flex items-center gap-1">
              {giftType === '14day' ? (
                <>
                  <Clock className="w-3 h-3 flex-shrink-0" />
                  {getGiftExpiryLabel() || 'Full Pro access'}
                </>
              ) : (
                <>
                  <Calendar className="w-3 h-3 flex-shrink-0" />
                  Full Pro access — no credit card needed
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <Link to="/settings/billing" onClick={handleUpgradeClick}>
            <Button
              size="sm"
              className="bg-navy hover:bg-navy/90 text-white flex items-center gap-2 font-semibold whitespace-nowrap"
              data-testid="gifted-upgrade-btn"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Upgrade to Keep Access
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          </Link>
          <button
            onClick={() => setDismissed(true)}
            className="p-1.5 rounded-full hover:bg-white/20 transition-colors flex-shrink-0"
            aria-label="Dismiss"
            data-testid="gifted-banner-dismiss"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
};

export default GiftedBanner;
