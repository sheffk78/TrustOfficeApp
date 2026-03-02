import { useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import { fetchWithAuth, getErrorMessage } from '@/utils/api';

/**
 * useReadOnlyAwareSubmit - Hook for form submissions that handles read-only mode
 * 
 * Returns a submit handler that:
 * - Checks isReadOnly before making the request
 * - Shows appropriate toast messages for read-only errors
 * - Handles 403 responses gracefully
 * 
 * Usage:
 *   const { submit, isReadOnly } = useReadOnlyAwareSubmit();
 *   
 *   const handleSubmit = async () => {
 *     const response = await submit('/api/distributions', {
 *       method: 'POST',
 *       body: JSON.stringify(data)
 *     });
 *     if (response?.ok) { ... }
 *   };
 */
export const useReadOnlyAwareSubmit = () => {
  const { isReadOnly, loadSubscriptionState } = useAuth();
  
  const submit = useCallback(async (endpoint, options = {}) => {
    // Pre-check: if we know we're read-only, don't even try
    if (isReadOnly) {
      toast.error('Subscription required', {
        description: 'Your subscription is inactive. Please subscribe to make changes.',
        action: {
          label: 'Subscribe',
          onClick: () => window.location.href = '/settings?tab=subscription'
        }
      });
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
          
          toast.error('Subscription required', {
            description: errorData.detail || 'Please subscribe to make changes.',
            action: {
              label: 'Subscribe',
              onClick: () => window.location.href = '/settings?tab=subscription'
            }
          });
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
  }, [isReadOnly, loadSubscriptionState]);
  
  return { submit, isReadOnly };
};

/**
 * useReadOnlyCheck - Simple hook to check read-only status
 * 
 * Returns:
 *   - isReadOnly: boolean
 *   - showReadOnlyToast: function to show a toast if read-only
 *   - canWrite: boolean (opposite of isReadOnly)
 */
export const useReadOnlyCheck = () => {
  const { isReadOnly } = useAuth();
  
  const showReadOnlyToast = useCallback(() => {
    if (isReadOnly) {
      toast.error('Subscription required', {
        description: 'Your subscription is inactive. Please subscribe to make changes.',
        action: {
          label: 'Subscribe',
          onClick: () => window.location.href = '/settings?tab=subscription'
        }
      });
      return true;
    }
    return false;
  }, [isReadOnly]);
  
  return {
    isReadOnly,
    canWrite: !isReadOnly,
    showReadOnlyToast
  };
};

export default useReadOnlyAwareSubmit;
