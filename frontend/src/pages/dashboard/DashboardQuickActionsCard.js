import { Link } from 'react-router-dom';
import {
  Receipt,
  DollarSign,
  Wallet,
  TrendingUp,
  HeartHandshake,
} from 'lucide-react';
import { QUICK_ACTIONS } from './constants';

/**
 * Quick Actions card — shows common task shortcuts and dashboard stats.
 */
export function DashboardQuickActionsCard({ stats, navigate }) {
  return (
    <div className="card-trust">
      <div className="flex items-center justify-between mb-4">
        <p className="label-trust">Quick Actions</p>
        <Link
          to="/minutes/templates"
          className="text-xs text-muted-foreground hover:text-navy"
        >
          All Templates
        </Link>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {QUICK_ACTIONS.map((action, index) => {
          const Icon = action.icon;
          return (
            <button
              key={index}
              onClick={() => navigate(action.path)}
              className="p-3 text-left border border-border hover:border-gold transition-colors group"
              data-testid={`quick-action-${index}`}
            >
              <div className={`w-8 h-8 ${action.color} flex items-center justify-center mb-2`}>
                {Icon && <Icon className="w-4 h-4" />}
              </div>
              <p className="font-medium text-sm text-navy group-hover:text-navy/70 transition-colors">
                {action.title}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                {action.description}
              </p>
            </button>
          );
        })}
      </div>

      {/* Stats from /api/dashboard */}
      <div className="mt-6 pt-6 border-t border-navy/10">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="font-mono text-2xl text-navy">{stats?.total_decisions || 0}</p>
            <p className="label-trust">Decisions</p>
          </div>
          <div>
            <p className="font-mono text-2xl text-warning">{stats?.pending_reviews || 0}</p>
            <p className="label-trust">Pending</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// Money section quick links — config-driven grid of financial feature links
const MONEY_LINKS = [
  { to: '/transactions', Icon: Receipt, color: 'bg-navy/10 text-navy', title: 'Transactions', subtitle: 'Ledger & imports' },
  { to: '/distributions', Icon: DollarSign, color: 'bg-success/10 text-success', title: 'Distributions', subtitle: 'Beneficiary payments' },
  { to: '/compensation', Icon: Wallet, color: 'bg-navy/10 text-navy', title: 'Compensation', subtitle: 'Trustee payments' },
  { to: '/investments', Icon: TrendingUp, color: 'bg-gold/10 text-gold', title: 'Investments', subtitle: 'Holdings & returns' },
  { to: '/benevolence', Icon: HeartHandshake, color: 'bg-success/10 text-success', title: 'Benevolence', subtitle: 'Charitable giving log' },
];

/**
 * Money section — grid of quick links to financial features.
 */
export function DashboardMoneySection() {
  return (
    <div className="mb-8 card-trust" data-testid="money-section-links">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-gold/20 to-navy/10 flex items-center justify-center">
            <DollarSign className="w-5 h-5 text-gold" />
          </div>
          <div>
            <h3 className="font-serif text-lg text-navy">Money</h3>
            <p className="text-sm text-muted-foreground">Track distributions, compensation, investments, and transactions</p>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {MONEY_LINKS.map(link => {
          const Icon = link.Icon;
          return (
            <Link key={link.to} to={link.to} className="p-3 text-left border border-border hover:border-gold transition-colors group">
              <div className={`w-8 h-8 ${link.color} flex items-center justify-center mb-2`}>
                <Icon className="w-4 h-4" />
              </div>
              <p className="font-medium text-sm text-navy group-hover:text-navy/70 transition-colors">{link.title}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{link.subtitle}</p>
            </Link>
          );
        })}
      </div>
    </div>
  );
}