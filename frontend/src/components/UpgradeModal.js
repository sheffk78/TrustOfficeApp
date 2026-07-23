import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, Sparkles, Check, ArrowRight, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAuth } from '@/context/AuthContext';
import { trackUpgradeModalShown, trackUpgradeModalClicked } from '@/utils/analytics';

/**
 * Phase 3: 3-tier pricing structure used by the upgrade modal.
 * Matches the canonical tiers in PricingPage.js / BillingPage.js.
 * Annual = monthly × 10 (2 months free).
 */
const TIERS = [
  {
    id: 'trustee',
    name: 'Trustee',
    monthly: 79,
    annual: 790,
    tagline: '1 trust, all governance tools',
    trustLimit: '1 trust'
  },
  {
    id: 'estate',
    name: 'Estate',
    monthly: 149,
    annual: 1490,
    tagline: 'Up to 8 trusts, multi-trust dashboard',
    trustLimit: 'Up to 8 trusts'
  },
  {
    id: 'advisor',
    name: 'Advisor',
    monthly: 399,
    annual: 3990,
    tagline: 'Unlimited trusts, client view, white-label',
    trustLimit: 'Unlimited trusts'
  }
];

// Normalize legacy plan types (monthly/annual) to the Trustee tier.
const normalizeTier = (planType) => {
  if (planType === 'monthly' || planType === 'annual') return 'trustee';
  return planType;
};

/**
 * UpgradeModal - Shows when read-only user tries a blocked action
 * Prompts user to upgrade their subscription.
 *
 * Phase 3: now tier-aware. Shows upgrade options based on the user's
 * current plan (Trustee → Estate/Advisor; Estate → Advisor) plus a
 * monthly/annual billing toggle. Free/expired users see all tiers.
 */
export const UpgradeModal = ({ 
  open, 
  onClose, 
  featureAttempted = 'this feature',
  trigger = 'blocked_action' 
}) => {
  const navigate = useNavigate();
  const { subscription } = useAuth();
  const [billingPeriod, setBillingPeriod] = useState('monthly');
  
  // Track modal view
  useEffect(() => {
    if (open) {
      trackUpgradeModalShown({ 
        trigger, 
        feature_attempted: featureAttempted 
      });
    }
  }, [open, trigger, featureAttempted]);
  
  // Determine which tiers to show as upgrade options based on current plan.
  // Free / expired / no subscription → show all tiers.
  // Trustee (or legacy) → show Estate + Advisor.
  // Estate → show Advisor only.
  // Advisor → show all (no upgrades available, just re-subscribe options).
  const currentPlanType = normalizeTier(subscription?.plan_type);
  const currentTierIndex = TIERS.findIndex((t) => t.id === currentPlanType);
  const isOnPaidTier = currentTierIndex >= 0 && currentPlanType !== 'forever_free' && currentPlanType !== 'free' && currentPlanType !== 'trial' && currentPlanType !== 'none';

  const upgradeTiers = (() => {
    if (!isOnPaidTier) return TIERS;
    return TIERS.filter((t) => TIERS.findIndex((x) => x.id === t.id) > currentTierIndex);
  })();

  const handleUpgradeClick = () => {
    trackUpgradeModalClicked({ 
      trigger, 
      feature_attempted: featureAttempted 
    });
    onClose();
    navigate('/settings/billing');
  };

  const handleManageSubscriptionClick = () => {
    trackUpgradeModalClicked({
      trigger,
      feature_attempted: featureAttempted
    });
    onClose();
    navigate('/settings/billing');
  };
  
  const features = [
    'Unlimited minutes and distributions',
    'Schedule A asset tracking',
    'Defensibility monitoring',
    'PDF exports and reports',
    'Trust certificate management',
    'Priority email support'
  ];

  const formatPrice = (tier) => {
    return billingPeriod === 'annual'
      ? { amount: tier.annual, unit: '/year' }
      : { amount: tier.monthly, unit: '/month' };
  };
  
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg" data-testid="upgrade-modal">
        <DialogHeader className="text-center">
          <div className="mx-auto mb-4 w-12 h-12 bg-warning/10 dark:bg-warning/30 rounded-full flex items-center justify-center">
            <Lock className="h-6 w-6 text-warning dark:text-warning" />
          </div>
          <DialogTitle className="text-xl font-serif">
            Subscription Required
          </DialogTitle>
          <DialogDescription className="text-base">
            To {featureAttempted}, you need an active subscription.
          </DialogDescription>
        </DialogHeader>
        
        <div className="py-4">
          <div className="bg-slate-50 dark:bg-slate-900/50 rounded p-4 mb-4">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">
              TrustOffice includes:
            </p>
            <ul className="space-y-2">
              {features.map((feature, index) => (
                <li key={index} className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                  <Check className="h-4 w-4 text-success flex-shrink-0" />
                  {feature}
                </li>
              ))}
            </ul>
          </div>

          {/* Phase 3: monthly/annual billing toggle */}
          <div className="flex justify-center mb-4">
            <div className="inline-flex items-center bg-slate-100 dark:bg-slate-800 rounded-full p-1">
              <button
                type="button"
                onClick={() => setBillingPeriod('monthly')}
                className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${billingPeriod === 'monthly' ? 'bg-navy text-white' : 'text-slate-500 dark:text-slate-400'}`}
              >
                Monthly
              </button>
              <button
                type="button"
                onClick={() => setBillingPeriod('annual')}
                className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${billingPeriod === 'annual' ? 'bg-navy text-white' : 'text-slate-500 dark:text-slate-400'}`}
              >
                Annual <span className="text-success">· 2 months free</span>
              </button>
            </div>
          </div>

          {/* Phase 3: tier-aware upgrade options.
              Shows all tiers (free/expired) or only higher tiers (paid user). */}
          {upgradeTiers.length > 0 ? (
            <div className="space-y-3 mb-4">
              {upgradeTiers.map((tier) => {
                const { amount, unit } = formatPrice(tier);
                const isUpgrade = TIERS.findIndex((t) => t.id === tier.id) > currentTierIndex;
                return (
                  <div
                    key={tier.id}
                    className={`flex items-center justify-between p-3 rounded border border-slate-200 dark:border-slate-700 ${tier.id === 'estate' ? 'bg-gold/5 border-gold/30' : ''}`}
                    data-testid={`upgrade-option-${tier.id}`}
                  >
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                        {tier.name}
                        {isUpgrade && isOnPaidTier && (
                          <span className="ml-2 text-xs text-success font-medium">Upgrade</span>
                        )}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">{tier.tagline}</p>
                    </div>
                    <div className="text-right ml-3">
                      <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                        ${amount}
                        <span className="text-xs font-normal text-slate-400">{unit}</span>
                      </p>
                      {billingPeriod === 'annual' && (
                        <p className="text-xs text-success">save ${tier.monthly * 2}</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center text-sm text-slate-500 dark:text-slate-400 mb-4">
              You're on the Advisor plan — the highest tier. Manage your subscription in billing settings.
            </div>
          )}

          <div className="flex items-center justify-center gap-2 text-sm text-slate-500 mb-4">
            <span className="font-semibold text-slate-700 dark:text-slate-300">${billingPeriod === 'annual' ? '790' : '79'}/{billingPeriod === 'annual' ? 'yr' : 'mo'}</span>
            <span>for Trustee ·</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300">${billingPeriod === 'annual' ? '1,490' : '149'}/{billingPeriod === 'annual' ? 'yr' : 'mo'}</span>
            <span>for Estate ·</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300">${billingPeriod === 'annual' ? '3,990' : '399'}/{billingPeriod === 'annual' ? 'yr' : 'mo'}</span>
            <span>for Advisor</span>
          </div>
        </div>
        
        <div className="flex flex-col gap-2">
          {upgradeTiers.length === 0 ? (
            <Button
              onClick={handleManageSubscriptionClick}
              className="w-full bg-navy hover:bg-navy/90 text-white flex items-center justify-center gap-2"
              data-testid="upgrade-modal-manage-subscription"
            >
              <Settings className="h-4 w-4" />
              Manage Subscription
              <ArrowRight className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              onClick={handleUpgradeClick}
              className="w-full bg-navy hover:bg-navy/90 text-white flex items-center justify-center gap-2"
              data-testid="upgrade-modal-cta"
            >
              <Sparkles className="h-4 w-4" />
              {isOnPaidTier ? 'Change My Plan' : 'Subscribe Now'}
              <ArrowRight className="h-4 w-4" />
            </Button>
          )}
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