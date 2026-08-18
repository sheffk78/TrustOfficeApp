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
} from 'lucide-react';
import { useState, useRef, useEffect } from 'react';

// ═══ 5 primary nav items (max for a bottom bar) ═══
const primaryNav = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Home' },
  { path: '/minutes', icon: FilePen, label: 'Minutes' },
  {
    path: '/distributions',
    icon: Coins,
    label: 'Money',
    subMenu: [
      { path: '/distributions', icon: Coins, label: 'Distributions' },
      { path: '/compensation', icon: Coins, label: 'Compensation' },
      { path: '/investments', icon: BarChart3, label: 'Investments' },
      { path: '/benevolence', icon: HeartPulse, label: 'Benevolence' },
      { path: '/benevolence/policy', icon: FilePen, label: 'Policy' },
      { path: '/transactions', icon: Coins, label: 'Transactions' },
    ],
  },
  { path: '/trust-assistant', icon: Bot, label: 'Assistant' },
  // 'More' is special — opens a slide-up panel
  { path: '__more__', icon: MoreHorizontal, label: 'More', isMore: true },
];

// ═══ Secondary items shown in the 'More' slide-up panel ═══
const moreNav = [
  { path: '/settings', icon: Settings, label: 'Settings' },
  { path: '/trust-roles', icon: UsersRound, label: 'Trust Roles' },
  { path: '/structures', icon: Network, label: 'Structure' },
  { path: '/messaging', icon: MessageSquare, label: 'Messages' },
  { path: '/vault', icon: FolderOpen, label: 'Vault' },
  { path: '/governance', icon: HeartPulse, label: 'Trust Health' },
  { path: '/performance', icon: BarChart3, label: 'Performance' },
  { path: '/knowledge', icon: BookOpen, label: 'Knowledge Base' },
  { path: '/course', icon: GraduationCap, label: 'Trustee 101' },
];

export const MobileBottomNav = () => {
  const location = useLocation();
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
      return moreNav.some((s) => location.pathname === s.path);
    }
    return false;
  };

  const isSubActive = (subPath) => location.pathname === subPath;

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
                    {item.subMenu.map((sub) => {
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

      {/* ─── 'More' slide-up sheet ─── */}
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
              {moreNav.map((item) => {
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
        </>
      )}
    </>
  );
};