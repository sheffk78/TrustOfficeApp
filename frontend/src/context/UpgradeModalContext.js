import { createContext, useContext, useState, useCallback } from 'react';
import { UpgradeModal } from '@/components/UpgradeModal';
import { trackFeatureBlocked } from '@/utils/analytics';
import { useAuth } from '@/context/AuthContext';

const UpgradeModalContext = createContext(null);

/**
 * UpgradeModalProvider - Global provider for upgrade modal
 * Wrap your app with this to enable upgrade modal triggering from anywhere
 */
export const UpgradeModalProvider = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [featureAttempted, setFeatureAttempted] = useState('this feature');
  const [trigger, setTrigger] = useState('blocked_action');
  const { isReadOnly, subscription } = useAuth();
  
  const showUpgradeModal = useCallback((feature = 'this feature', triggerSource = 'blocked_action', location = 'unknown') => {
    // Track the blocked action
    // Note: callers already check isReadOnly before invoking showUpgradeModal,
    // so we do NOT guard on isReadOnly here — double-guarding blocked the modal
    // for free-tier and paid users hitting trust limits.
    trackFeatureBlocked({
      feature_name: feature,
      location,
      subscription_status: subscription?.status || 'expired'
    });
    
    setFeatureAttempted(feature);
    setTrigger(triggerSource);
    setIsOpen(true);
    return true;
  }, [subscription]);
  
  const hideUpgradeModal = useCallback(() => {
    setIsOpen(false);
  }, []);
  
  const value = {
    showUpgradeModal,
    hideUpgradeModal,
    isModalOpen: isOpen
  };
  
  return (
    <UpgradeModalContext.Provider value={value}>
      {children}
      <UpgradeModal 
        open={isOpen} 
        onClose={hideUpgradeModal}
        featureAttempted={featureAttempted}
        trigger={trigger}
      />
    </UpgradeModalContext.Provider>
  );
};

/**
 * useUpgradeModal - Hook to access upgrade modal functions
 * 
 * Usage:
 *   const { showUpgradeModal } = useUpgradeModal();
 *   
 *   const handleCreate = () => {
 *     if (isReadOnly) {
 *       showUpgradeModal('create distribution', 'button_click', 'distributions_page');
 *       return;
 *     }
 *     // ... proceed with creation
 *   };
 */
export const useUpgradeModal = () => {
  const context = useContext(UpgradeModalContext);
  if (!context) {
    throw new Error('useUpgradeModal must be used within UpgradeModalProvider');
  }
  return context;
};

export default UpgradeModalProvider;
