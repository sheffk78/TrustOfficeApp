import { useEffect, useRef } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Clock, Sparkles, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { trackTrialBannerViewed, trackTrialBannerClicked } from '@/utils/analytics';

/**
 * TrialBanner - Shows countdown for active trial users
 * Displays at the top of dashboard to remind users of trial expiration
 */
export const TrialBanner = ({ location = 'dashboard' }) => {
  const { subscription } = useAuth();
  const hasTrackedView = useRef(false);
  
  // Only show for active trials
  const isActiveTrial = subscription?.is_trial && subscription?.is_active;
  const daysRemaining = subscription?.trial_days_remaining;
  
  // Track banner view once
  useEffect(() => {
    if (isActiveTrial && daysRemaining !== undefined && !hasTrackedView.current) {
      trackTrialBannerViewed({ days_remaining: daysRemaining, location });
      hasTrackedView.current = true;
    }
  }, [isActiveTrial, daysRemaining, location]);
  
  if (!isActiveTrial || daysRemaining === undefined) return null;
  
  const handleUpgradeClick = () => {
    trackTrialBannerClicked({ days_remaining: daysRemaining, location });
  };
  
  // Color scheme based on urgency
  const isUrgent = daysRemaining <= 3;
  const isWarning = daysRemaining <= 7 && daysRemaining > 3;
  
  const bgColor = isUrgent 
    ? 'bg-gradient-to-r from-red-50 to-orange-50 dark:from-red-950/30 dark:to-orange-950/30 border-red-200 dark:border-red-800'
    : isWarning
      ? 'bg-gradient-to-r from-amber-50 to-yellow-50 dark:from-amber-950/30 dark:to-yellow-950/30 border-amber-200 dark:border-amber-800'
      : 'bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 border-blue-200 dark:border-blue-800';
  
  const textColor = isUrgent
    ? 'text-red-800 dark:text-red-200'
    : isWarning
      ? 'text-amber-800 dark:text-amber-200'
      : 'text-blue-800 dark:text-blue-200';
  
  const iconBg = isUrgent
    ? 'bg-red-100 dark:bg-red-900/50'
    : isWarning
      ? 'bg-amber-100 dark:bg-amber-900/50'
      : 'bg-blue-100 dark:bg-blue-900/50';
  
  const iconColor = isUrgent
    ? 'text-red-600 dark:text-red-400'
    : isWarning
      ? 'text-amber-600 dark:text-amber-400'
      : 'text-blue-600 dark:text-blue-400';
  
  const buttonClass = isUrgent
    ? 'bg-red-600 hover:bg-red-700 text-white'
    : isWarning
      ? 'bg-amber-600 hover:bg-amber-700 text-white'
      : 'bg-blue-600 hover:bg-blue-700 text-white';
  
  return (
    <div 
      className={`${bgColor} border-b px-4 py-3`}
      data-testid="trial-banner"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className={`p-2 ${iconBg} rounded-full`}>
            <Clock className={`h-4 w-4 ${iconColor}`} />
          </div>
          <div>
            <p className={`text-sm font-medium ${textColor}`}>
              {daysRemaining === 0 
                ? 'Your trial expires today!'
                : daysRemaining === 1 
                  ? '1 day left in your trial'
                  : `${daysRemaining} days left in your trial`}
            </p>
            <p className={`text-xs ${iconColor}`}>
              {isUrgent 
                ? 'Upgrade now to keep full access to all features'
                : 'Upgrade anytime to unlock all premium features'}
            </p>
          </div>
        </div>
        <Link to="/settings?tab=subscription" onClick={handleUpgradeClick}>
          <Button 
            size="sm" 
            className={`${buttonClass} flex items-center gap-2`}
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
