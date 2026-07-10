import { useCallback, useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import { fetchWithAuth, getErrorMessage } from '@/utils/api';
import { trackFeatureBlocked } from '@/utils/analytics';

/**
 * useReadOnlyAwareSubmit - Hook for form submissions that handles read-only mode
 * 
 * Returns a submit handler that:
 * - Checks isReadOnly before making the request
 * - Shows appropriate toast messages for read-only errors
 * - Handles 403 responses gracefully
 * - Optionally triggers upgrade modal
 * 
 * Usage:
 *   const { submit, isReadOnly, showUpgradeModal, setShowUpgradeModal, blockedFeature } = useReadOnlyAwareSubmit();
 *   
 *   const handleSubmit = async () => {
 *     const response = await submit('/api/distributions', {
 *       method: 'POST',
 *       body: JSON.stringify(data)
 *     }, { featureName: 'create distribution', useModal: true });
 *     if (response?.ok) { ... }
 *   };
 */
export const useReadOnlyAwareSubmit = () => {
  const { isReadOnly, subscription, loadSubscriptionState } = useAuth();
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [blockedFeature, setBlockedFeature] = useState('this feature');
  
  const submit = useCallback(async (endpoint, options = {}, config = {}) => {
    const { featureName = 'make changes', useModal = false, location = 'unknown' } = config;
    
    // Pre-check: if we know we're read-only, don't even try
    if (isReadOnly) {
      // Track the blocked action
      trackFeatureBlocked({
        feature_name: featureName,
        location,
        subscription_status: subscription?.status || 'expired'
      });
      
      if (useModal) {
        setBlockedFeature(featureName);
        setShowUpgradeModal(true);
      } else {
        toast.error('Subscription required', {
          description: 'Your subscription is inactive. Please subscribe to make changes.',
          action: {
            label: 'Subscribe',
            onClick: () => window.location.href = '/settings/billing'
          }
        });
      }
      return null;
    }
    
    try {
      const response = await fetchWithAuth(endpoint, options);
      
      // Handle 403 (read-only mode detected by server)
      if (response.status === 403) {
        const errorData = await response.json().catch(() => ({}));
        
        if (errorData.is_read_only) {
          // Update local state to reflect server state
          await loadSubscriptionState();
          
          // Track the blocked action
          trackFeatureBlocked({
            feature_name: featureName,
            location,
            subscription_status: errorData.subscription_status || 'expired'
          });
          
          if (useModal) {
            setBlockedFeature(featureName);
            setShowUpgradeModal(true);
          } else {
            toast.error('Subscription required', {
              description: errorData.detail || 'Please subscribe to make changes.',
              action: {
                label: 'Subscribe',
                onClick: () => window.location.href = '/settings/billing'
              }
            });
          }
        } else {
          toast.error('Access denied', {
            description: errorData.detail || 'You do not have permission to perform this action.'
          });
        }
        return response;
      }
      
      return response;
    } catch (error) {
      toast.error('Request failed', {
        description: error.message
      });
      return null;
    }
  }, [isReadOnly, subscription, loadSubscriptionState]);
  
  return { 
    submit, 
    isReadOnly, 
    showUpgradeModal, 
    setShowUpgradeModal, 
    blockedFeature 
  };
};

/**
 * useReadOnlyCheck - Simple hook to check read-only status with modal support
 * 
 * Returns:
 *   - isReadOnly: boolean
 *   - showReadOnlyToast: function to show a toast if read-only
 *   - triggerUpgradeModal: function to trigger upgrade modal
 *   - canWrite: boolean (opposite of isReadOnly)
 *   - modalState: { show, setShow, feature }
 */
export const useReadOnlyCheck = () => {
  const { isReadOnly, subscription } = useAuth();
  const [showModal, setShowModal] = useState(false);
  const [modalFeature, setModalFeature] = useState('this feature');
  
  const showReadOnlyToast = useCallback((featureName = 'make changes', location = 'unknown') => {
    if (isReadOnly) {
      trackFeatureBlocked({
        feature_name: featureName,
        location,
        subscription_status: subscription?.status || 'expired'
      });
      
      toast.error('Subscription required', {
        description: 'Your subscription is inactive. Please subscribe to make changes.',
        action: {
          label: 'Subscribe',
          onClick: () => window.location.href = '/settings/billing'
        }
      });
      return true;
    }
    return false;
  }, [isReadOnly, subscription]);
  
  const triggerUpgradeModal = useCallback((featureName = 'this feature', location = 'unknown') => {
    if (isReadOnly) {
      trackFeatureBlocked({
        feature_name: featureName,
        location,
        subscription_status: subscription?.status || 'expired'
      });
      setModalFeature(featureName);
      setShowModal(true);
      return true;
    }
    return false;
  }, [isReadOnly, subscription]);
  
  return {
    isReadOnly,
    canWrite: !isReadOnly,
    showReadOnlyToast,
    triggerUpgradeModal,
    modalState: {
      show: showModal,
      setShow: setShowModal,
      feature: modalFeature
    }
  };
};

export default useReadOnlyAwareSubmit;
