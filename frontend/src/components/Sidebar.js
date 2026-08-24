import { useState, useRef, useLayoutEffect, useEffect, useCallback } from 'react';
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
  Library,
  NotebookTabs,
  BarChart3,
  Bot,
  GraduationCap,
  Briefcase,
  UsersRound,
  ScrollText,
  FilePlus,
  FileText
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

  // ═══ ASSETS — the core of the trust ═══
  { key: 'assets', icon: Package, label: 'Assets', items: [
    { path: '/schedule-a', icon: Package, label: 'Schedule A', tooltip: 'View all trust assets' },
    { path: '/minutes/template/acceptance_of_property', icon: FilePlus, label: 'Add Asset', badge: 'NEW', tooltip: 'Add a new asset to the trust' },
  ]},

  // ═══ MONEY ═══
  { key: 'money', icon: Coins, label: 'Money', items: [
    { path: '/distributions', icon: Send, label: 'Distributions' },
    { path: '/compensation', icon: Wallet, label: 'Compensation' },
    { path: '/expenses', icon: Receipt, label: 'Expenses' },
    { path: '/investments', icon: TrendingUp, label: 'Investments' },
    { path: '/benevolence', icon: HeartHandshake, label: 'Benevolence', requiresBenevolence: true },
    { path: '/benevolence?tab=policy', icon: FileText, label: 'Policy', parentPath: '/benevolence', requiresBenevolence: true },
    { path: '/transactions', icon: ArrowUpDown, label: 'Transaction Ledger' },
  ]},

  // ═══ TRUST STRUCTURE — legal architecture ═══
  { key: 'trust-structure', icon: Network, label: 'Trust Structure', items: [
    { path: '/structures', icon: Layers, label: 'Trust & Entities' },
    { path: '/beneficiaries', icon: Users, label: 'Beneficiaries' },
  ]},

  // ═══ COMMUNICATION ═══
  { key: 'communication', icon: MessageSquare, label: 'Communication', items: [
    { path: '/messaging', icon: MessageSquare, label: 'Messages', badge: 'NEW' },
    { path: '/communications', icon: Send, label: 'Communications' },
  ]},

  // ═══ GOVERNANCE — records and meetings ═══
  { key: 'governance', icon: BookOpen, label: 'Governance', items: [
    { path: '/calendar', icon: Calendar, label: 'Calendar' },
    { path: '/minutes', icon: FilePen, label: 'Minutes' },
    { path: '/audit-trail', icon: ClipboardList, label: 'Audit Trail' },
  ]},

  // ═══ HEALTH & COMPLIANCE ═══
  { key: 'health-compliance', icon: Scale, label: 'Health & Compliance', items: [
    { path: '/governance', icon: HeartPulse, label: 'Trust Health' },
    { path: '/governance?tab=risk', icon: Activity, label: 'Risk Dashboard' },
    { path: '/governance?tab=state', icon: MapPin, label: 'State Compliance' },
  ]},

  // ═══ DOCUMENTS ═══
  { key: 'documents', icon: FolderOpen, label: 'Documents', items: [
    { path: '/vault', icon: FolderOpen, label: 'Vault' },
    { path: '/vault?tab=templates', icon: Briefcase, label: 'Admin Templates', badge: 'NEW' },
    { path: '/vault?tab=binder', icon: NotebookTabs, label: 'Record Book' },
  ]},

  // ═══ LEARN ═══
  { key: 'learn', icon: Library, label: 'Learn', items: [
    { path: '/course', icon: GraduationCap, label: 'Trustee 101' },
    { path: '/knowledge', icon: BookOpen, label: 'Browse Articles' },
    { path: '/knowledge/admin', icon: FilePen, label: 'Manage Articles', adminOnly: true },
  ]},

  // ═══ STANDALONE ITEMS ═══
  { key: 'trustee-powers', icon: Gavel, label: 'Trustee Powers', items: [] },
  { key: 'settings', icon: Settings, label: 'Settings', items: [] },
];

// Flat list for easy lookup
const ALL_ITEMS = NAV_GROUPS.flatMap(g => g.items);

const SIDEBAR_SCROLL_KEY = 'sidebar-scroll';
const SIDEBAR_GROUPS_KEY = 'sidebar-expanded-groups';

// Paths that match by prefix (not just exact equality)
const PREFIX_PATHS = new Set(['/minutes', '/structures', '/entities', '/knowledge', '/course', '/schedule-a', '/benevolence']);

/**
 * Check whether a nav item path matches the current pathname.
 * Exact match always wins. For paths in PREFIX_PATHS, also matches by prefix.
 */
const isPathActive = (itemPath, pathname) => {
  if (pathname === itemPath) return true;
  // /entities matches the /structures group (same nav section)
  if (itemPath === '/structures' && (pathname.startsWith('/structures') || pathname.startsWith('/entities'))) {
    return true;
  }
  if (itemPath === '/minutes' && pathname.startsWith('/minutes')) return true;
  if (itemPath === '/schedule-a' && pathname.startsWith('/schedule-a')) return true;
  if (itemPath === '/benevolence' && pathname.startsWith('/benevolence')) return true;
  // /course matches by prefix so sub-routes highlight the nav item
  if (itemPath === '/course' && pathname.startsWith('/course')) return true;
  return false;
};

/**
 * Check whether an item is visible given the current trust's benevolence flag.
 */
const isItemVisible = (item, selectedTrust, isAdmin) => {
  if (item.requiresBenevolence && !selectedTrust?.benevolence_enabled) return false;
  if (item.adminOnly && !isAdmin) return false;
  return true;
};

/**
 * Resolve the link target path for a single-item (no children) nav group.
 */
const resolveSingleGroupPath = (groupKey) => {
  switch (groupKey) {
    case 'dashboard': return '/dashboard';
    case 'trust-assistant': return '/trust-assistant';
    case 'trustee-powers': return '/authority';
    case 'settings': return '/settings';
    default: return '/settings';
  }
};

// ─── Sub-components ────────────────────────────────────────────────

const NavBadge = ({ badge, variant = 'gold' }) => {
  const base = 'px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider';
  const styles = variant === 'solid'
    ? 'bg-gold text-navy font-bold'
    : 'bg-gold/20 text-gold';
  return <span className={`${base} ${styles}`}>{badge}</span>;
};

const StandaloneNavItem = ({ group, pathname, onClick }) => {
  const GroupIcon = group.icon;
  const path = resolveSingleGroupPath(group.key);
  const isActive = isPathActive(path, pathname);

  return (
    <div>
      <Link
        to={path}
        className={`sidebar-item ${group.standout ? 'sidebar-item-standout' : ''} ${isActive ? 'active' : ''}`}
        onClick={onClick}
        data-testid={`nav-${group.key}`}
      >
        <GroupIcon className={`w-5 h-5 ${group.standout ? 'text-gold' : ''}`} />
        <span className="flex items-center gap-2">
          {group.label}
          {group.badge && <NavBadge badge={group.badge} variant="solid" />}
        </span>
      </Link>
    </div>
  );
};

const NavGroupItem = ({ group, pathname, selectedTrust, isAdmin, isExpanded, onToggle, onLinkClick }) => {
  const GroupIcon = group.icon;
  const visibleItems = group.items.filter(item => isItemVisible(item, selectedTrust, isAdmin));
  const hasActiveChild = visibleItems.some(item => isPathActive(item.path, pathname));

  return (
    <div className="mb-1">
      <button
        onClick={() => onToggle(group.key)}
        className={`sidebar-item w-full justify-between ${hasActiveChild ? 'text-gold' : ''}`}
        data-testid={`nav-group-${group.key}`}
        aria-expanded={isExpanded}
        aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${group.label} section`}
      >
        <div className="flex items-center gap-3">
          <GroupIcon className="w-5 h-5" />
          <span>{group.label}</span>
        </div>
        <ChevronRight className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
      </button>

      {isExpanded && (
        <div className="ml-4 border-l border-white/10">
          {visibleItems.map((item) => {
            const ItemIcon = item.icon;
            const isActive = isPathActive(item.path, pathname);
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`sidebar-item pl-6 py-2 ${isActive ? 'active' : ''}`}
                onClick={onLinkClick}
                data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
                title={item.tooltip}
              >
                <ItemIcon className="w-4 h-4" />
                <span className="flex items-center gap-2">
                  {item.label}
                  {item.badge && <NavBadge badge={item.badge} />}
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
};

const StaffLink = ({ to, label, badge, icon: Icon, pathname, onClick, testId }) => {
  const isActive = pathname === to;
  return (
    <Link
      to={to}
      className={`sidebar-item ${isActive ? 'active' : ''}`}
      onClick={onClick}
      data-testid={testId}
    >
      <Icon className="w-5 h-5" />
      <span className="flex items-center gap-2">
        {label}
        <NavBadge badge={badge} />
      </span>
    </Link>
  );
};

const TrustSelector = ({ trusts, selectedTrust, onSelect }) => (
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
            onClick={() => onSelect(trust)}
            className="font-mono text-sm"
            data-testid={`trust-option-${trust.trust_id}`}
          >
            {trust.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
);

const UserSection = ({ user, onLogout }) => (
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
      onClick={onLogout}
      className="flex items-center gap-2 text-white/60 hover:text-white w-full"
      data-testid="logout-btn"
    >
      <LogOut className="w-4 h-4" />
      <span className="font-mono text-xs uppercase tracking-widest">Sign Out</span>
    </button>
  </div>
);

// ─── Custom hooks (extracted from Sidebar to reduce brain_method) ───

/**
 * Persist sidebar scroll position to sessionStorage (restore on remount).
 */
const useSidebarScroll = (navRef) => {
  const scrollTimer = useRef(null);

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
  const handleNavScroll = useCallback(() => {
    if (scrollTimer.current) return;
    scrollTimer.current = setTimeout(() => {
      if (navRef.current) {
        try {
          sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(navRef.current.scrollTop));
        } catch (e) { /* ignore */ }
      }
      scrollTimer.current = null;
    }, 150);
  }, [navRef]);

  const saveScrollPosition = useCallback(() => {
    if (navRef.current) {
      try {
        sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(navRef.current.scrollTop));
      } catch (e) { /* ignore */ }
      }
  }, [navRef]);

  // Clean up any pending scroll timer on unmount
  useEffect(() => {
    return () => {
      if (scrollTimer.current) {
        clearTimeout(scrollTimer.current);
        scrollTimer.current = null;
      }
    };
  }, []);

  return { handleNavScroll, saveScrollPosition };
};

/**
 * Track which nav groups are expanded, persisted to sessionStorage.
 */
const useExpandedGroups = (activeGroup) => {
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

  const toggleGroup = useCallback((key) => {
    setExpandedGroups(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  return { expandedGroups, toggleGroup };
};

// ─── NavList: renders all nav groups (extracted from Sidebar body) ───

const NavList = ({
  pathname,
  selectedTrust,
  expandedGroups,
  toggleGroup,
  onLinkClick,
  isAdmin,
  user,
}) => (
  <>
    {NAV_GROUPS.map((group) => {
      const isExpanded = expandedGroups[group.key];

      // Single-item groups render directly
      if (group.items.length === 0) {
        return (
          <StandaloneNavItem
            key={group.key}
            group={group}
            pathname={pathname}
            onClick={onLinkClick}
          />
        );
      }

      // Grouped items with accordion
      return (
        <NavGroupItem
          key={group.key}
          group={group}
          pathname={pathname}
          selectedTrust={selectedTrust}
          isAdmin={isAdmin}
          isExpanded={isExpanded}
          onToggle={toggleGroup}
          onLinkClick={onLinkClick}
        />
      );
    })}

    {/* Admin link - only visible to admins */}
    {isAdmin && (
      <StaffLink
        to="/admin"
        label="Admin"
        badge="staff"
        icon={Crown}
        pathname={pathname}
        onClick={onLinkClick}
        testId="nav-admin"
      />
    )}

    {/* Stats link - visible to stats users. Appears next to Admin */}
    {user?.is_stats_user && (
      <StaffLink
        to="/stats"
        label="Stats"
        badge="view"
        icon={BarChart3}
        pathname={pathname}
        onClick={onLinkClick}
        testId="nav-stats"
      />
    )}
  </>
);

// ─── Main component ────────────────────────────────────────────────

export const Sidebar = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, trusts, selectedTrust, setSelectedTrust, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const navRef = useRef(null);

  // Determine which group should be expanded based on current route
  const activeGroup = NAV_GROUPS.find(g =>
    g.items.some(item =>
      isPathActive(item.path, location.pathname)
    )
  )?.key || null;

  const { expandedGroups, toggleGroup } = useExpandedGroups(activeGroup);
  const { handleNavScroll, saveScrollPosition } = useSidebarScroll(navRef);

  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const handleLinkClick = () => {
    saveScrollPosition();
    setMobileOpen(false);
  };

  return (
    <>
      {/* Mobile menu button — hidden on mobile via CSS (.mobile-menu-btn display:none at <1024px).
          Bottom nav is the primary mobile navigation. Sidebar is accessible from 'More' menu. */}
      <button
        className="mobile-menu-btn"
        onClick={() => setMobileOpen(true)}
        data-testid="mobile-menu-btn"
        aria-label="Open navigation menu"
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
          aria-label="Close navigation menu"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Logo */}
        <div className="p-6 border-b border-white/10">
          <Link to="/dashboard" className="block">
            <img
              src="/assets/trustoffice-logo-vertical.svg?v=3"
              alt="TrustOffice"
              className="h-8 cursor-pointer hover:opacity-80 transition-opacity"
              data-testid="logo-home-link"
            />
          </Link>
        </div>

        {/* Trust selector */}
        {trusts.length > 0 && (
          <TrustSelector
            trusts={trusts}
            selectedTrust={selectedTrust}
            onSelect={setSelectedTrust}
          />
        )}

        {/* Navigation */}
        <nav ref={navRef} onScroll={handleNavScroll} className="flex-1 py-4 overflow-y-auto">
          <NavList
            pathname={location.pathname}
            selectedTrust={selectedTrust}
            expandedGroups={expandedGroups}
            toggleGroup={toggleGroup}
            onLinkClick={handleLinkClick}
            isAdmin={isAdmin}
            user={user}
          />
        </nav>

        <UserSection user={user} onLogout={handleLogout} />
      </aside>
    </>
  );
};