import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, FileText, Settings, Shield, DollarSign } from 'lucide-react';

const navItems = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Home' },
  { path: '/minutes', icon: FileText, label: 'Minutes' },
  { path: '/distributions', icon: DollarSign, label: 'Money' },
  { path: '/governance', icon: Shield, label: 'Score' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

export const MobileBottomNav = () => {
  const location = useLocation();
  
  return (
    <nav className="mobile-bottom-nav" data-testid="mobile-bottom-nav">
      {navItems.map((item) => {
        const Icon = item.icon;
        const isActive = location.pathname === item.path || 
          (item.path !== '/dashboard' && location.pathname.startsWith(item.path));
        
        return (
          <Link
            key={item.path}
            to={item.path}
            className={`mobile-bottom-nav-item ${isActive ? 'active' : ''}`}
            data-testid={`mobile-nav-${item.label.toLowerCase()}`}
          >
            <Icon />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
};
