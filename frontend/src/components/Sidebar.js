import { useState, useRef, useLayoutEffect, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { ThemeToggle } from '@/components/ThemeToggle';
import { 
  LayoutDashboard, 
  FilePen, 
  Coins, 
  Receipt, 
  Scale, 
  Settings,
  LogOut,
  Menu,
  X,
  ChevronDown,
  Calendar,
  Network,
  Wallet,
  Package,
  Award,
  Users,
  Crown,
  ArrowUpDown,
  TrendingUp,
  MessageSquare,
  FolderOpen,
  Clock,
  Activity,
  ChevronRight,
  Layers,
  Send,
  MapPin,
  Gavel,
  HeartPulse,
  ClipboardList,
  BookOpen,
  NotebookTabs,
  BarChart3,
  Bot,
  GraduationCap,
  Briefcase
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { HeartHandshake } from 'lucide-react';

const NAV_GROUPS = [
  // ═══ HERO ITEMS — gold-tinted standout links ═══
  { key: 'dashboard', icon: LayoutDashboard, label: 'Dashboard', items: [], standout: true },
  { key: 'trust-assistant', icon: Bot, label: 'Trust Assistant', items: [], standout: true, badge: 'NEW' },

  // ═══ LEARNING ═══
  { key: 'course', icon: GraduationCap, label: 'Trustee 101', items: [], standout: true },

  // ═══ CORE SECTIONS ═══
  { key: 'governance', icon: BookOpen, label: 'Governance', items: [
    { path: '/calendar', icon: Calendar, label: 'Calendar' },
    { path: '/minutes', icon: FilePen, label: 'Minutes' },
  ]},
  { key: 'money', icon: Coins, label: 'Money', items: [
    { path: '/distributions', icon: Send, label: 'Distributions' },
    { path: '/compensation', icon: Wallet, label: 'Compensation' },
    { path: '/investments', icon: TrendingUp, label: 'Investments' },
    { path: '/benevolence', icon: HeartHandshake, label: 'Benevolence', requiresBenevolence: true },
  ]},
  { key: 'structure', icon: Network, label: 'Structure', items: [
    { path: '/structures', icon: Layers, label: 'Structures' },
    { path: '/schedule-a', icon: Package, label: 'Schedule A' },
    { path: '/beneficiaries', icon: Users, label: 'Beneficiaries' },
    { path: '/communications', icon: MessageSquare, label: 'Communications' },
    { path: '/vault', icon: FolderOpen, label: 'Vault' },
    { path: '/admin-kits', icon: Briefcase, label: 'Admin Kits', badge: 'NEW' },
  ]},
  { key: 'compliance', icon: Scale, label: 'Compliance', items: [
    { path: '/risk', icon: Activity, label: 'Risk Dashboard' },
    { path: '/state-compliance', icon: MapPin, label: 'State Compliance' },
    { path: '/authority', icon: Gavel, label: 'Authority' },
    { path: '/audit-trail', icon: ClipboardList, label: 'Audit Trail' },
    { path: '/binder', icon: NotebookTabs, label: 'Binder Tools' },
  ]},
  { key: 'score', icon: HeartPulse, label: 'Trust Health', items: [] },
  { key: 'settings', icon: Settings, label: 'Settings', items: [] },
];

// Flat list for easy lookup
const ALL_ITEMS = NAV_GROUPS.flatMap(g => g.items);

const SIDEBAR_SCROLL_KEY = 'sidebar-scroll';
const SIDEBAR_GROUPS_KEY = 'sidebar-expanded-groups';

export const Sidebar = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, trusts, selectedTrust, setSelectedTrust, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const navRef = useRef(null);
  const scrollTimer = useRef(null);
  
  // Determine which group should be expanded based on current route
  const activeGroup = NAV_GROUPS.find(g => 
    g.items.some(item => 
      location.pathname === item.path || 
      (item.path === '/minutes' && location.pathname.startsWith('/minutes')) ||
      (item.path === '/structures' && location.pathname.startsWith('/structures')) ||
      (item.path === '/structures' && location.pathname.startsWith('/entities'))
    )
  )?.key || null;
  
  // Initialize expandedGroups from sessionStorage (survives remount) or fall back to active group
  const [expandedGroups, setExpandedGroups] = useState(() => {
    try {
      const saved = sessionStorage.getItem(SIDEBAR_GROUPS_KEY);
      if (saved) return JSON.parse(saved);
    } catch (e) { /* ignore */ }
    const initial = {};
    if (activeGroup) initial[activeGroup] = true;
    return initial;
  });

  // Persist expandedGroups to sessionStorage whenever it changes
  useEffect(() => {
    try {
      sessionStorage.setItem(SIDEBAR_GROUPS_KEY, JSON.stringify(expandedGroups));
    } catch (e) { /* ignore */ }
  }, [expandedGroups]);

  // Restore scroll position before paint to avoid visible jump
  useLayoutEffect(() => {
    if (!navRef.current) return;
    try {
      const saved = sessionStorage.getItem(SIDEBAR_SCROLL_KEY);
      if (saved != null) {
        navRef.current.scrollTop = parseInt(saved, 10) || 0;
      }
    } catch (e) { /* ignore */ }
  }, []);

  // Throttled scroll handler — save scroll position to sessionStorage
  const handleNavScroll = () => {
    if (scrollTimer.current) return;
    scrollTimer.current = setTimeout(() => {
      if (navRef.current) {
        try {
          sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(navRef.current.scrollTop));
        } catch (e) { /* ignore */ }
      }
      scrollTimer.current = null;
    }, 150);
  };

  // Clean up any pending scroll timer on unmount
  useEffect(() => {
    return () => {
      if (scrollTimer.current) {
        clearTimeout(scrollTimer.current);
        scrollTimer.current = null;
      }
    };
  }, []);

  const toggleGroup = (key) => {
    setExpandedGroups(prev => ({ ...prev, [key]: !prev[key] }));
  };

  // Save scroll position immediately (used on link clicks before navigation)
  const saveScrollPosition = () => {
    if (navRef.current) {
      try {
        sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(navRef.current.scrollTop));
      } catch (e) { /* ignore */ }
    }
  };
  
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';

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
              src="/assets/trustoffice-logo-vertical.svg"
              alt="TrustOffice"
              className="h-8 cursor-pointer hover:opacity-80 transition-opacity"
              data-testid="logo-home-link"
            />
          </Link>
        </div>

        {/* Trust selector */}
        {trusts.length > 0 && (
          <div className="sidebar-trust-selector">
            <p className="font-mono text-[9px] uppercase tracking-widest text-white/40 mb-2">
              Active Trust
            </p>
            <DropdownMenu>
              <DropdownMenuTrigger className="w-full text-left p-3 bg-white/5 hover:bg-white/10 flex items-center justify-between border border-white/15" data-testid="trust-selector">
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
        <nav ref={navRef} onScroll={handleNavScroll} className="flex-1 py-4 overflow-y-auto">
          {NAV_GROUPS.map((group) => {
            const GroupIcon = group.icon;
            const isExpanded = expandedGroups[group.key];
            
            // Single-item groups (Dashboard, Trust Assistant, Score, Settings) render directly
            if (group.items.length === 0) {
              const path = group.key === 'dashboard' ? '/dashboard' 
                : group.key === 'score' ? '/governance' 
                : group.key === 'trust-assistant' ? '/trust-assistant'
                : group.key === 'course' ? '/course'
                : '/settings';
              const isActive = location.pathname === path || (path === '/course' && location.pathname.startsWith('/course'));
              
              return (
                <div key={group.key}>
                  <Link
                    to={path}
                    className={`sidebar-item ${group.standout ? 'sidebar-item-standout' : ''} ${isActive ? 'active' : ''}`}
                    onClick={() => { saveScrollPosition(); setMobileOpen(false); }}
                    data-testid={`nav-${group.key}`}
                  >
                    <GroupIcon className={`w-5 h-5 ${group.standout ? 'text-gold' : ''}`} />
                    <span className="flex items-center gap-2">
                      {group.label}
                      {group.badge && (
                        <span className="px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider bg-gold text-navy font-bold">
                          {group.badge}
                        </span>
                      )}
                    </span>
                  </Link>
                  {/* Divider after Trustee 101 separates hero items from core nav */}
                  {group.key === 'course' && (
                    <div className="sidebar-section-divider" />
                  )}
                </div>
              );
            }
            
            // Grouped items with accordion
            const hasActiveChild = group.items.some(item => {
              if (item.requiresBenevolence && !selectedTrust?.benevolence_enabled) return false;
              return location.pathname === item.path || 
                (item.path === '/minutes' && location.pathname.startsWith('/minutes')) ||
                (item.path === '/structures' && location.pathname.startsWith('/structures')) ||
                (item.path === '/structures' && location.pathname.startsWith('/entities'));
            });
            
            return (
              <div key={group.key} className="mb-1">
                <button
                  onClick={() => toggleGroup(group.key)}
                  className={`sidebar-item w-full justify-between ${hasActiveChild ? 'text-gold' : ''}`}
                  data-testid={`nav-group-${group.key}`}
                  aria-expanded={isExpanded}
                >
                  <div className="flex items-center gap-3">
                    <GroupIcon className="w-5 h-5" />
                    <span>{group.label}</span>
                  </div>
                  <ChevronRight 
                    className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`} 
                  />
                </button>
                
                {isExpanded && (
                  <div className="ml-4 border-l border-white/10">
                    {group.items
                      .filter(item => !item.requiresBenevolence || selectedTrust?.benevolence_enabled)
                      .map((item) => {
                        const ItemIcon = item.icon;
                        const isActive = location.pathname === item.path || 
                          (item.path === '/minutes' && location.pathname.startsWith('/minutes')) ||
                          (item.path === '/structures' && location.pathname.startsWith('/structures')) ||
                          (item.path === '/structures' && location.pathname.startsWith('/entities'));
                        
                        return (
                          <Link
                            key={item.path}
                            to={item.path}
                            className={`sidebar-item pl-6 py-2 ${isActive ? 'active' : ''}`}
                            onClick={() => { saveScrollPosition(); setMobileOpen(false); }}
                            data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
                          >
                            <ItemIcon className="w-4 h-4" />
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
                  </div>
                )}
              </div>
            );
          })}
          
          {/* Admin link - only visible to admins */}
          {isAdmin && (
            <Link
              to="/admin"
              className={`sidebar-item ${location.pathname === '/admin' ? 'active' : ''}`}
              onClick={() => { saveScrollPosition(); setMobileOpen(false); }}
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
          
          {/* Stats link - visible to stats users. Appears next to Admin */}
          {(user?.is_stats_user) && (
            <Link
              to="/stats"
              className={`sidebar-item ${location.pathname === '/stats' ? 'active' : ''}`}
              onClick={() => { saveScrollPosition(); setMobileOpen(false); }}
              data-testid="nav-stats"
            >
              <BarChart3 className="w-5 h-5" />
              <span className="flex items-center gap-2">
                Stats
                <span className="px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider bg-gold/20 text-gold">
                  view
                </span>
              </span>
            </Link>
          )}
        </nav>

        {/* User section */}
        <div className="p-4 border-t border-white/10">
          {/* Notification center moved to Admin page */}
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