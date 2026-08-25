import { Link } from 'react-router-dom';
import {
  Receipt,
  DollarSign,
  Wallet,
  TrendingUp,
  PlusCircle,
  Package,
  FileText,
} from 'lucide-react';

/**
 * Quick Actions card — consolidated to 8 highest-frequency actions.
 * Rare lifecycle events (Open Bank Account, Appoint Trustee, View Structures)
 * are accessible via the "All Templates" link and sidebar. Benevolence is
 * niche and available in the sidebar.
 */

export const QUICK_ACTIONS = [
  {
    title: 'Record Distribution',
    description: 'Document a distribution to beneficiaries',
    icon: DollarSign,
    path: '/minutes/template/distribution_to_beneficiaries',
    color: 'bg-success/10 text-success'
  },
  {
    title: 'Distributions',
    description: 'Beneficiary payments',
    icon: DollarSign,
    path: '/distributions',
    color: 'bg-success/10 text-success'
  },
  {
    title: 'Transactions',
    description: 'Ledger & imports',
    icon: Receipt,
    path: '/transactions',
    color: 'bg-navy/10 text-navy'
  },
  {
    title: 'Add Asset to Trust',
    description: 'Accept property and update Trust Assets',
    icon: PlusCircle,
    path: '/minutes/template/acceptance_of_property',
    color: 'bg-navy/10 text-navy'
  },
  {
    title: 'View Trust Assets',
    description: 'Manage trust assets and corpus',
    icon: Package,
    path: '/schedule-a',
    color: 'bg-navy/10 text-navy'
  },
  {
    title: 'General Meeting',
    description: 'Record a trustee meeting',
    icon: FileText,
    path: '/minutes/template/general_meeting',
    color: 'bg-gold/20 text-gold'
  },
  {
    title: 'Investments',
    description: 'Holdings & returns',
    icon: TrendingUp,
    path: '/investments',
    color: 'bg-gold/10 text-gold'
  },
  {
    title: 'Compensation',
    description: 'Trustee payments',
    icon: Wallet,
    path: '/compensation',
    color: 'bg-navy/10 text-navy'
  }
];

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