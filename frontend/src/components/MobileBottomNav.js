import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, FileText, Settings, Shield, DollarSign, Wallet, TrendingUp } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';

const mainNav = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Home' },
  { path: '/minutes', icon: FileText, label: 'Minutes' },
  { path: '/distributions', icon: DollarSign, label: 'Money', subMenu: [
    { path: '/distributions', icon: DollarSign, label: 'Distributions' },
    { path: '/compensation', icon: Wallet, label: 'Compensation' },
    { path: '/investments', icon: TrendingUp, label: 'Investments' },
  ]},
  { path: '/governance', icon: Shield, label: 'Trust Health' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

export const MobileBottomNav = () => {
  const location = useLocation();
  const [openMenu, setOpenMenu] = useState(null);
  const menuRef = useRef(null);

  // Close submenu on outside click
  useEffect(() => {
    if (!openMenu) return;
    const handleClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setOpenMenu(null);
      }
    };
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [openMenu]);

  const isActive = (item) => {
    if (location.pathname === item.path) return true;
    if (item.subMenu) {
      return item.subMenu.some(s => location.pathname === s.path);
    }
    return false;
  };

  return (
    <nav className="mobile-bottom-nav" data-testid="mobile-bottom-nav" ref={menuRef}>
      {mainNav.map((item) => {
        const Icon = item.icon;
        const active = isActive(item);

        if (item.subMenu) {
          return (
            <div key={item.path} className="relative flex flex-col items-center">
              <button
                onClick={() => setOpenMenu(openMenu === item.label ? null : item.label)}
                className={`mobile-bottom-nav-item ${active ? 'active' : ''}`}
                data-testid={`mobile-nav-${item.label.toLowerCase()}`}
                aria-expanded={openMenu === item.label}
              >
                <Icon />
                <span>{item.label}</span>
              </button>
              {openMenu === item.label && (
                <div className="absolute bottom-full mb-2 bg-white border border-neutral-200 shadow-lg rounded-lg overflow-hidden min-w-[160px] z-50">
                  {item.subMenu.map((sub) => {
                    const SubIcon = sub.icon;
                    const subActive = location.pathname === sub.path;
                    return (
                      <Link
                        key={sub.path}
                        to={sub.path}
                        onClick={() => setOpenMenu(null)}
                        className={`flex items-center gap-2 px-4 py-3 text-sm hover:bg-neutral-50 ${subActive ? 'text-navy font-medium bg-navy/5' : 'text-neutral-700'}`}
                      >
                        <SubIcon className="w-4 h-4" />
                        {sub.label}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        }

        return (
          <Link
            key={item.path}
            to={item.path}
            className={`mobile-bottom-nav-item ${active ? 'active' : ''}`}
            data-testid={`mobile-nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
          >
            <Icon />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
};
