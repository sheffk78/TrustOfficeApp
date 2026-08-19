import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FilePen,
  Coins,
  Bot,
  MoreHorizontal,
  Settings,
  UsersRound,
  Network,
  MessageSquare,
  FolderOpen,
  HeartPulse,
  BarChart3,
  BookOpen,
  GraduationCap,
  X,
  Package,
  Send,
  Wallet,
  TrendingUp,
  HeartHandshake,
  ArrowUpDown,
  Receipt,
  Layers,
  Users,
  Calendar,
  ClipboardList,
  Scale,
  Activity,
  MapPin,
  Gavel,
  Briefcase,
  NotebookTabs,
  Library,
  FileText,
} from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';

// ═══ 5 primary nav items (max for a bottom bar) ═══
const primaryNav = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Home' },
  { path: '/schedule-a', icon: Package, label: 'Assets' },
  {
    path: '/distributions',
    icon: Coins,
    label: 'Money',
    subMenu: [
      { path: '/distributions', icon: Send, label: 'Distributions' },
      { path: '/compensation', icon: Wallet, label: 'Compensation' },
      { path: '/expenses', icon: Receipt, label: 'Expenses' },
      { path: '/investments', icon: TrendingUp, label: 'Investments' },
      { path: '/benevolence', icon: HeartHandshake, label: 'Benevolence', requiresBenevolence: true },
      { path: '/benevolence/policy', icon: FileText, label: 'Policy', requiresBenevolence: true },
      { path: '/transactions', icon: ArrowUpDown, label: 'Transactions' },
    ],
  },
  { path: '/trust-assistant', icon: Bot, label: 'Assistant' },
  // 'More' is special — opens a slide-up panel
  { path: '__more__', icon: MoreHorizontal, label: 'More', isMore: true },
];

// ═══ Secondary items shown in the 'More' slide-up panel (grouped) ═══
const moreNavGroups = [
  {
    groupLabel: 'Trust Structure',
    items: [
      { path: '/structures', icon: Network, label: 'Trust & Entities' },
      { path: '/beneficiaries', icon: Users, label: 'Beneficiaries' },
    ],
  },
  {
    groupLabel: 'Governance',
    items: [
      { path: '/calendar', icon: Calendar, label: 'Calendar' },
      { path: '/minutes', icon: FilePen, label: 'Minutes' },
      { path: '/audit-trail', icon: ClipboardList, label: 'Audit Trail' },
    ],
  },
  {
    groupLabel: 'Compliance',
    items: [
      { path: '/governance', icon: HeartPulse, label: 'Trust Health' },
      { path: '/risk', icon: Activity, label: 'Risk Dashboard' },
      { path: '/state-compliance', icon: MapPin, label: 'State Compliance' },
      { path: '/authority', icon: Gavel, label: 'Trustee Powers' },
    ],
  },
  {
    groupLabel: 'Documents',
    items: [
      { path: '/vault', icon: FolderOpen, label: 'Vault' },
      { path: '/admin-kits', icon: Briefcase, label: 'Admin Templates' },
      { path: '/binder', icon: NotebookTabs, label: 'Record Book' },
    ],
  },
  {
    groupLabel: 'Communication',
    items: [
      { path: '/messaging', icon: MessageSquare, label: 'Messages' },
      { path: '/communications', icon: Send, label: 'Communications' },
    ],
  },
  {
    groupLabel: 'Learn',
    items: [
      { path: '/course', icon: GraduationCap, label: 'Trustee 101' },
      { path: '/knowledge', icon: BookOpen, label: 'Articles' },
    ],
  },
  {
    groupLabel: 'Settings',
    items: [
      { path: '/settings', icon: Settings, label: 'Settings' },
      { path: '/trust-roles', icon: UsersRound, label: 'Trust Roles' },
    ],
  },
];

// Flatten all moreNav items for active-state checking
const allMoreItems = moreNavGroups.flatMap(g => g.items);

export const MobileBottomNav = () => {
  const location = useLocation();
  const { selectedTrust } = useAuth();
  const [openMenu, setOpenMenu] = useState(null); // 'Money' | '__more__' | null
  const menuRef = useRef(null);
  const moreSheetRef = useRef(null);

  // Close any open popup on outside click
  useEffect(() => {
    if (!openMenu) return;
    const handleClick = (e) => {
      if (
        menuRef.current && !menuRef.current.contains(e.target) &&
        moreSheetRef.current && !moreSheetRef.current.contains(e.target)
      ) {
        setOpenMenu(null);
      }
    };
    const handleEscape = (e) => {
      if (e.key === 'Escape') setOpenMenu(null);
    };
    document.addEventListener('click', handleClick);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('click', handleClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [openMenu]);

  // Close popups on route change
  useEffect(() => {
    setOpenMenu(null);
  }, [location.pathname]);

  const isActive = (item) => {
    if (location.pathname === item.path) return true;
    if (item.subMenu) {
      return item.subMenu.some((s) => location.pathname === s.path);
    }
    if (item.isMore) {
      return allMoreItems.some((s) => location.pathname === s.path);
    }
    return false;
  };

  const isSubActive = (subPath) => location.pathname === subPath;

  // Filter benevolence items from subMenu based on trust's benevolence_enabled flag
  const filterSubMenu = (subMenu) => {
    if (!subMenu) return subMenu;
    return subMenu.filter(item => {
      if (item.requiresBenevolence && !selectedTrust?.benevolence_enabled) return false;
      return true;
    });
  };

  return (
    <>
      <nav
        className="mobile-bottom-nav"
        data-testid="mobile-bottom-nav"
        ref={menuRef}
      >
        {primaryNav.map((item) => {
          const Icon = item.icon;
          const active = isActive(item);

          // ─── Money item with submenu popup ───
          if (item.subMenu) {
            const visibleSubItems = filterSubMenu(item.subMenu);
            return (
              <div
                key={item.path}
                className="mobile-bottom-nav-item-wrapper"
              >
                <button
                  onClick={() =>
                    setOpenMenu(openMenu === item.label ? null : item.label)
                  }
                  className={`mobile-bottom-nav-item ${active ? 'active' : ''}`}
                  data-testid={`mobile-nav-${item.label.toLowerCase()}`}
                  aria-expanded={openMenu === item.label}
                  aria-label={item.label}
                >
                  <Icon />
                  <span>{item.label}</span>
                </button>
                {openMenu === item.label && (
                  <div
                    className="mobile-submenu-popup"
                    role="menu"
                  >
                    {visibleSubItems.map((sub) => {
                      const SubIcon = sub.icon;
                      const subActive = isSubActive(sub.path);
                      return (
                        <Link
                          key={sub.path}
                          to={sub.path}
                          onClick={() => setOpenMenu(null)}
                          className={`mobile-submenu-item ${subActive ? 'active' : ''}`}
                          data-testid={`mobile-submenu-${sub.label.toLowerCase().replace(/\s+/g, '-')}`}
                        >
                          <SubIcon className="w-5 h-5" />
                          <span>{sub.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          }

          // ─── 'More' button opens slide-up sheet ───
          if (item.isMore) {
            return (
              <button
                key={item.label}
                onClick={() =>
                  setOpenMenu(openMenu === '__more__' ? null : '__more__')
                }
                className={`mobile-bottom-nav-item ${active ? 'active' : ''}`}
                data-testid="mobile-nav-more"
                aria-expanded={openMenu === '__more__'}
                aria-label="More navigation"
              >
                <Icon />
                <span>{item.label}</span>
              </button>
            );
          }

          // ─── Standard link items ───
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`mobile-bottom-nav-item ${active ? 'active' : ''}`}
              data-testid={`mobile-nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
              aria-label={item.label}
              aria-current={active ? 'page' : undefined}
            >
              <Icon />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* ─── 'More' slide-up sheet (grouped) ─── */}
      {openMenu === '__more__' && (
        <>
          <div
            className="mobile-more-overlay"
            onClick={() => setOpenMenu(null)}
          />
          <div
            className="mobile-more-sheet"
            ref={moreSheetRef}
            role="dialog"
            aria-label="More navigation"
            data-testid="mobile-more-sheet"
          >
            <div className="mobile-more-sheet-header">
              <span className="mobile-more-sheet-title">More</span>
              <button
                className="mobile-more-sheet-close"
                onClick={() => setOpenMenu(null)}
                aria-label="Close menu"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="mobile-more-grid">
              {moreNavGroups.map((group) => (
                <div key={group.groupLabel} className="mobile-more-group">
                  <p className="mobile-more-group-label">{group.groupLabel}</p>
                  <div className="mobile-more-group-items">
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      const active = isSubActive(item.path);
                      return (
                        <Link
                          key={item.path}
                          to={item.path}
                          className={`mobile-more-item ${active ? 'active' : ''}`}
                          data-testid={`mobile-more-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
                        >
                          <Icon className="w-6 h-6" />
                          <span>{item.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
};