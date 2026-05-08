import { useEffect, useRef } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Check, Sparkles, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { trackTrialBannerViewed, trackTrialBannerClicked } from '@/utils/analytics';

/**
 * TrialBanner - Shows status banner for active free-tier users
 * Displays at the top of dashboard to indicate free access status
 */
export const TrialBanner = ({ location = 'dashboard' }) => {
  const { subscription } = useAuth();
  const hasTrackedView = useRef(false);
  
  // Only show for active free-tier users
  const isActiveFreeTier = subscription?.is_trial && subscription?.is_active;
  
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
      className="bg-gradient-to-r from-navy/5 to-gold/5 border-b border-navy/10 px-4 py-3"
      data-testid="trial-banner"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-success/10 rounded-full">
            <Check className="h-4 w-4 text-success" />
          </div>
          <div>
            <p className="text-sm font-medium text-navy">
              Free Access — All Features Included
            </p>
            <p className="text-xs text-muted-foreground">
              Individual trustees get full access at no cost
            </p>
          </div>
        </div>
        <Link to="/settings?tab=subscription" onClick={handleUpgradeClick}>
          <Button 
            size="sm" 
            className="bg-navy hover:bg-navy/90 text-white flex items-center gap-2"
            data-testid="trial-upgrade-btn"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Upgrade for Teams
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </Link>
      </div>
    </div>
  );
};

export default TrialBanner;