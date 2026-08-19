import { useEffect, useRef } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sparkles, ArrowRight, Lock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { trackTrialBannerViewed, trackTrialBannerClicked } from '@/utils/analytics';

/**
 * TrialBanner - Shows status banner for free-tier users
 * Displays at the top of dashboard to indicate free access status
 * and encourage upgrade to paid plan for full features.
 */
export const TrialBanner = ({ location = 'dashboard' }) => {
  const { subscription } = useAuth();
  const hasTrackedView = useRef(false);
  
  // forever_free is a permanent free tier, NOT a trial — never show upgrade nudges.
  if (subscription?.plan_type === 'forever_free') return null;

  // Show for active free users (legacy trial or free) — NOT gifted users, NOT forever_free
  const isGiftedUser = subscription?.is_gifted;
  const isActiveFreeTier = !isGiftedUser && (
    (subscription?.is_trial && subscription?.is_active) || 
    (subscription?.plan_type === 'free' && subscription?.is_active)
  );
  
  // Track banner view once
  useEffect(() => {
    if (isActiveFreeTier && !hasTrackedView.current) {
      trackTrialBannerViewed({ days_remaining: subscription?.trial_days_remaining, location });
      hasTrackedView.current = true;
    }
  }, [isActiveFreeTier, location]);
  
  if (!isActiveFreeTier) return null;
  
  const handleUpgradeClick = () => {
    trackTrialBannerClicked({ days_remaining: subscription?.trial_days_remaining, location });
  };
  
  return (
    <div 
      className="bg-gradient-to-r from-navy/5 to-gold/5 border-b border-navy/10 pl-4 lg:pl-64 px-4 py-3"
      data-testid="trial-banner"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-success/10 rounded-full">
            <Lock className="h-4 w-4 text-navy" />
          </div>
          <div>
            <p className="text-sm font-medium text-navy">
              Free Plan — You can view your data, but cannot make changes
            </p>
            <p className="text-xs text-muted-foreground">
              Your data is safe and fully viewable. Purchase a plan to unlock PDF exports, multiple trusts, advanced templates, and the ability to make changes
            </p>
          </div>
        </div>
        <Link to="/settings/billing" onClick={handleUpgradeClick}>
          <Button 
            size="sm" 
            className="btn-primary flex items-center gap-2"
            data-testid="trial-upgrade-btn"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Upgrade Now
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </Link>
      </div>
    </div>
  );
};

export default TrialBanner;