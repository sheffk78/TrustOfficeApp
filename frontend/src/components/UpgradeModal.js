import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, Sparkles, Check, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { trackUpgradeModalShown, trackUpgradeModalClicked } from '@/utils/analytics';

/**
 * UpgradeModal - Shows when read-only user tries a blocked action
 * Prompts user to upgrade their subscription
 */
export const UpgradeModal = ({ 
  open, 
  onClose, 
  featureAttempted = 'this feature',
  trigger = 'blocked_action' 
}) => {
  const navigate = useNavigate();
  
  // Track modal view
  useEffect(() => {
    if (open) {
      trackUpgradeModalShown({ 
        trigger, 
        feature_attempted: featureAttempted 
      });
    }
  }, [open, trigger, featureAttempted]);
  
  const handleUpgradeClick = () => {
    trackUpgradeModalClicked({ 
      trigger, 
      feature_attempted: featureAttempted 
    });
    onClose();
    navigate('/settings?tab=subscription');
  };
  
  const features = [
    'Unlimited minutes and distributions',
    'Schedule A asset tracking',
    'Governance health monitoring',
    'PDF exports and reports',
    'Trust certificate management',
    'Priority email support'
  ];
  
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md" data-testid="upgrade-modal">
        <DialogHeader className="text-center">
          <div className="mx-auto mb-4 w-12 h-12 bg-amber-100 dark:bg-amber-900/50 rounded-full flex items-center justify-center">
            <Lock className="h-6 w-6 text-amber-600 dark:text-amber-400" />
          </div>
          <DialogTitle className="text-xl font-serif">
            Subscription Required
          </DialogTitle>
          <DialogDescription className="text-base">
            To {featureAttempted}, you need an active subscription.
          </DialogDescription>
        </DialogHeader>
        
        <div className="py-4">
          <div className="bg-slate-50 dark:bg-slate-900/50 rounded-lg p-4 mb-4">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">
              TrustOffice includes:
            </p>
            <ul className="space-y-2">
              {features.map((feature, index) => (
                <li key={index} className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                  <Check className="h-4 w-4 text-green-500 flex-shrink-0" />
                  {feature}
                </li>
              ))}
            </ul>
          </div>
          
          <div className="flex items-center justify-center gap-2 text-sm text-slate-500 mb-4">
            <span className="font-semibold text-slate-700 dark:text-slate-300">$79/month</span>
            <span>or</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300">$790/year</span>
            <span className="text-green-600 dark:text-green-400">(save 17%)</span>
          </div>
        </div>
        
        <div className="flex flex-col gap-2">
          <Button 
            onClick={handleUpgradeClick}
            className="w-full bg-navy hover:bg-navy/90 text-white flex items-center justify-center gap-2"
            data-testid="upgrade-modal-cta"
          >
            <Sparkles className="h-4 w-4" />
            Subscribe Now
            <ArrowRight className="h-4 w-4" />
          </Button>
          <Button 
            variant="ghost" 
            onClick={onClose}
            className="w-full text-slate-500"
            data-testid="upgrade-modal-dismiss"
          >
            Maybe Later
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default UpgradeModal;
