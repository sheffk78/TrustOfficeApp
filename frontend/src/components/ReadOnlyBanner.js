import { useAuth } from '@/context/AuthContext';
import { AlertTriangle, Lock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

/**
 * ReadOnlyBanner - Shows when subscription is expired and user is in read-only mode
 * Displays at the top of pages to inform users they can view but not modify data
 * Admins never see this banner
 */
export const ReadOnlyBanner = () => {
  const { user, isReadOnly, subscription, subscriptionExpired, loading } = useAuth();
  
  // Don't show while loading auth state to prevent flickering
  if (loading) return null;
  
  // ADMIN BYPASS: Never show banner for admins
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';
  if (isAdmin) return null;
  
  // Don't show if subscription hasn't been loaded yet
  if (!subscription) return null;
  
  // Don't show if not in read-only mode
  if (!isReadOnly && !subscriptionExpired) return null;
  
  // Don't show for active free-tier users
  if (subscription?.is_trial && subscription?.is_active) return null;
  
  const trialExpired = subscription?.status === 'expired';
  const subCanceled = subscription?.status === 'canceled';
  
  return (
    <div 
      className="bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800 px-4 py-3 lg:ml-64"
      data-testid="read-only-banner"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-amber-100 dark:bg-amber-900/50 rounded-full">
            <Lock className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
              {trialExpired 
                ? 'Your free access has ended' 
                : subCanceled 
                  ? 'Your subscription has been canceled'
                  : 'Access inactive'}
            </p>
            <p className="text-xs text-amber-600 dark:text-amber-400">
              You can view all your data, but creating or editing is disabled until you subscribe.
            </p>
          </div>
        </div>
        <Link to="/pricing">
          <Button 
            size="sm" 
            className="bg-amber-600 hover:bg-amber-700 text-white"
            data-testid="subscribe-now-btn"
          >
            Subscribe Now
          </Button>
        </Link>
      </div>
    </div>
  );
};

/**
 * ReadOnlyTooltip - Shows a tooltip/badge for disabled buttons
 */
export const ReadOnlyTooltip = ({ children }) => {
  const { isReadOnly } = useAuth();
  
  if (!isReadOnly) return children;
  
  return (
    <div className="relative group">
      {children}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-slate-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-50">
        <div className="flex items-center gap-1">
          <Lock className="h-3 w-3" />
          Subscription required
        </div>
      </div>
    </div>
  );
};

/**
 * ReadOnlyWrapper - Wraps form buttons to disable them in read-only mode
 */
export const ReadOnlyWrapper = ({ children, showTooltip = true }) => {
  const { isReadOnly } = useAuth();
  
  if (!isReadOnly) return children;
  
  // Clone children and add disabled prop
  const disabledChildren = Array.isArray(children) 
    ? children.map((child, i) => 
        child?.props ? { ...child, props: { ...child.props, disabled: true, key: i } } : child
      )
    : children?.props 
      ? { ...children, props: { ...children.props, disabled: true } }
      : children;
  
  if (showTooltip) {
    return <ReadOnlyTooltip>{disabledChildren}</ReadOnlyTooltip>;
  }
  
  return disabledChildren;
};

export default ReadOnlyBanner;
