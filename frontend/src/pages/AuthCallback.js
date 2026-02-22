import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

export default function AuthCallback() {
  const navigate = useNavigate();
  const { exchangeSession, setUser, setLoading, loadTrusts } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    // Use ref to prevent double processing in StrictMode
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      // Extract session_id from URL fragment
      const hash = window.location.hash;
      const sessionIdMatch = hash.match(/session_id=([^&]+)/);
      
      if (!sessionIdMatch) {
        toast.error('Authentication failed');
        navigate('/', { replace: true });
        return;
      }

      const sessionId = sessionIdMatch[1];

      try {
        setLoading(true);
        const data = await exchangeSession(sessionId);
        
        // Load trusts after auth
        await loadTrusts();
        
        toast.success('Welcome!');
        
        // Navigate to dashboard with user data to skip auth check
        navigate('/dashboard', { 
          replace: true,
          state: { user: data.user }
        });
      } catch (error) {
        console.error('Auth callback error:', error);
        toast.error('Authentication failed');
        navigate('/', { replace: true });
      } finally {
        setLoading(false);
      }
    };

    processAuth();
  }, [exchangeSession, navigate, setUser, setLoading, loadTrusts]);

  return (
    <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto mb-4"></div>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Completing Sign In
        </p>
      </div>
    </div>
  );
}
