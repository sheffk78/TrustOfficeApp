import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { ThemeToggle } from '@/components/ThemeToggle';
import { fetchWithAuth } from '@/utils/api';
import { 
  LayoutDashboard, 
  FileText, 
  DollarSign, 
  Receipt, 
  Shield, 
  Settings,
  LogOut,
  Menu,
  X,
  ChevronDown,
  Calendar,
  Building2,
  Wallet,
  Package,
  Award,
  Users,
  Sparkles,
  Crown
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { HeartHandshake } from 'lucide-react';

const navItems = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/calendar', icon: Calendar, label: 'Calendar', group: 'Governance' },
  { path: '/minutes', icon: FileText, label: 'Minutes', group: 'Governance' },
  { path: '/guided-minutes', icon: Sparkles, label: 'Guided Minutes', group: 'Governance', badge: 'beta' },
  { path: '/distributions', icon: DollarSign, label: 'Distributions', group: 'Money' },
  { path: '/compensation', icon: Wallet, label: 'Compensation', group: 'Money' },
  { path: '/benevolence', icon: HeartHandshake, label: 'Benevolence', group: 'Money', requiresBenevolence: true },
  { path: '/structures', icon: Building2, label: 'Structures', group: 'Structures' },
  { path: '/schedule-a', icon: Package, label: 'Schedule A', group: 'Structures' },
  { path: '/beneficiaries', icon: Users, label: 'Beneficiaries', group: 'Structures' },
  { path: '/governance', icon: Shield, label: 'Governance Health' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

export const Sidebar = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, trusts, selectedTrust, setSelectedTrust, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  // Check if user is admin
  useEffect(() => {
    const checkAdminStatus = async () => {
      try {
        const response = await fetchWithAuth('/api/admin/stats');
        if (response.ok) {
          setIsAdmin(true);
        }
      } catch {
        setIsAdmin(false);
      }
    };
    
    if (user) {
      checkAdminStatus();
    }
  }, [user]);

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const handleTrustSelect = (trust) => {
    setSelectedTrust(trust);
  };

  return (
    <>
      {/* Mobile menu button */}
      <button
        className="mobile-menu-btn"
        onClick={() => setMobileOpen(true)}
        data-testid="mobile-menu-btn"
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Mobile overlay */}
      <div 
        className={`sidebar-overlay ${mobileOpen ? 'open' : ''}`}
        onClick={() => setMobileOpen(false)}
      />

      {/* Sidebar */}
      <aside className={`sidebar-trust ${mobileOpen ? 'open' : ''}`} data-testid="sidebar">
        {/* Close button for mobile */}
        <button
          className="lg:hidden absolute top-4 right-4 text-white/60 hover:text-white"
          onClick={() => setMobileOpen(false)}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Logo */}
        <div className="p-6 border-b border-white/10">
          <Link to="/dashboard" className="block">
            <img 
              src="https://customer-assets.emergentagent.com/job_98ad4c89-4a05-4aed-ab1d-a934650bd7f4/artifacts/5h7i559r_Trust%20Office%20Logo%20%281%29.svg"
              alt="TrustOffice"
              className="h-8 brightness-0 invert cursor-pointer hover:opacity-80 transition-opacity"
              data-testid="logo-home-link"
            />
          </Link>
          <p className="font-mono text-[9px] uppercase tracking-widest text-white/40 mt-2">
            AnchorPoint Governance
          </p>
        </div>

        {/* Trust selector */}
        {trusts.length > 0 && (
          <div className="p-4 border-b border-white/10">
            <p className="font-mono text-[9px] uppercase tracking-widest text-white/40 mb-2">
              Active Trust
            </p>
            <DropdownMenu>
              <DropdownMenuTrigger className="w-full text-left p-3 bg-white/5 hover:bg-white/10 flex items-center justify-between" data-testid="trust-selector">
                <span className="font-mono text-sm text-white truncate">
                  {selectedTrust?.name || 'Select Trust'}
                </span>
                <ChevronDown className="w-4 h-4 text-white/60" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-56">
                {trusts.map((trust) => (
                  <DropdownMenuItem
                    key={trust.trust_id}
                    onClick={() => handleTrustSelect(trust)}
                    className="font-mono text-sm"
                    data-testid={`trust-option-${trust.trust_id}`}
                  >
                    {trust.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 py-4 overflow-y-auto">
          {navItems
            .filter(item => !item.requiresBenevolence || selectedTrust?.benevolence_enabled)
            .map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path || 
              (item.path === '/minutes' && location.pathname.startsWith('/minutes')) ||
              (item.path === '/guided-minutes' && location.pathname === '/guided-minutes');
            
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`sidebar-item ${isActive ? 'active' : ''}`}
                onClick={() => setMobileOpen(false)}
                data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
              >
                <Icon className="w-5 h-5" />
                <span className="flex items-center gap-2">
                  {item.label}
                  {item.badge && (
                    <span className="px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider bg-gold/20 text-gold">
                      {item.badge}
                    </span>
                  )}
                </span>
              </Link>
            );
          })}
          
          {/* Admin link - only visible to admins */}
          {isAdmin && (
            <Link
              to="/admin"
              className={`sidebar-item ${location.pathname === '/admin' ? 'active' : ''}`}
              onClick={() => setMobileOpen(false)}
              data-testid="nav-admin"
            >
              <Crown className="w-5 h-5" />
              <span className="flex items-center gap-2">
                Admin
                <span className="px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider bg-gold/20 text-gold">
                  staff
                </span>
              </span>
            </Link>
          )}
        </nav>

        {/* User section */}
        <div className="p-4 border-t border-white/10">
          <div className="flex items-center gap-3 mb-4">
            {user?.picture ? (
              <img src={user.picture} alt={user.name} className="w-10 h-10 object-cover" />
            ) : (
              <div className="w-10 h-10 bg-gold flex items-center justify-center">
                <span className="font-serif font-bold text-[#010079]">
                  {user?.name?.charAt(0) || 'U'}
                </span>
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-medium truncate">{user?.name}</p>
              <p className="font-mono text-[10px] text-white/40 truncate">{user?.email}</p>
            </div>
          </div>
          
          {/* Theme Toggle */}
          <ThemeToggle className="text-white/60 hover:text-white w-full mb-3" />
          
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-white/60 hover:text-white w-full"
            data-testid="logout-btn"
          >
            <LogOut className="w-4 h-4" />
            <span className="font-mono text-xs uppercase tracking-widest">Sign Out</span>
          </button>
        </div>
      </aside>
    </>
  );
};
