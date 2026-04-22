import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { Eye, X, UserCog } from 'lucide-react';

/**
 * ImpersonationBanner - Shows when an admin is viewing as another user
 * 
 * Displays a persistent orange banner at the top of the screen with:
 * - The impersonated user's email
 * - An "Exit" button to return to admin session
 * 
 * The banner is impossible to miss and always stays at the top.
 */
export const ImpersonationBanner = () => {
  const navigate = useNavigate();
  const { user, setUser, loadTrusts, loadSubscriptionState } = useAuth();
  const [impersonationData, setImpersonationData] = useState(null);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    // Check if we're in impersonation mode
    const stored = sessionStorage.getItem('impersonation_data');
    if (stored) {
      try {
        const data = JSON.parse(stored);
        setImpersonationData(data);
      } catch (e) {
        console.error('Failed to parse impersonation data:', e);
      }
    }
  }, [user]);

  const handleExit = async () => {
    setExiting(true);
    
    try {
      // Get the original admin token
      const adminToken = sessionStorage.getItem('admin_token');
      const adminData = sessionStorage.getItem('admin_user_data');
      
      if (!adminToken || !adminData) {
        toast.error('Admin session not found. Please log in again.');
        // Clear everything and redirect to login
        sessionStorage.removeItem('impersonation_data');
        sessionStorage.removeItem('admin_token');
        sessionStorage.removeItem('admin_user_data');
        localStorage.removeItem('auth_token');
        navigate('/login');
        return;
      }

      // Log the exit action (using admin token)
      try {
        await fetch(`${process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app'}/api/admin/impersonation/log-exit`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${adminToken}`
          }
        });
      } catch (e) {
        console.error('Failed to log impersonation exit:', e);
      }

      // Restore admin session
      localStorage.setItem('auth_token', adminToken);
      
      // Parse and set admin user data
      const adminUser = JSON.parse(adminData);
      setUser(adminUser);
      
      // Clear impersonation data
      sessionStorage.removeItem('impersonation_data');
      sessionStorage.removeItem('admin_token');
      sessionStorage.removeItem('admin_user_data');
      
      // Reload trusts and subscription for admin
      await loadTrusts();
      await loadSubscriptionState(adminUser.email);
      
      toast.success('Returned to admin account');
      
      // Navigate back to admin panel
      navigate('/admin');
      
    } catch (error) {
      console.error('Error exiting impersonation:', error);
      toast.error('Failed to exit impersonation mode');
    } finally {
      setExiting(false);
    }
  };

  // Don't render if not impersonating
  if (!impersonationData) {
    return null;
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-[100] bg-orange-500 text-white px-4 py-2 shadow-lg">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-orange-600 rounded-full px-3 py-1">
            <Eye className="w-4 h-4" />
            <span className="text-sm font-medium">VIEWING AS</span>
          </div>
          <div className="flex items-center gap-2">
            <UserCog className="w-5 h-5" />
            <span className="font-semibold">{impersonationData.email}</span>
            {impersonationData.name && (
              <span className="text-orange-100">({impersonationData.name})</span>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <span className="text-sm text-orange-100 hidden md:block">
            Admin: {impersonationData.adminEmail}
          </span>
          <Button
            onClick={handleExit}
            disabled={exiting}
            className="bg-white text-orange-600 hover:bg-orange-50 font-semibold"
            size="sm"
          >
            {exiting ? (
              <>Exiting...</>
            ) : (
              <>
                <X className="w-4 h-4 mr-1" />
                Exit Impersonation
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ImpersonationBanner;
