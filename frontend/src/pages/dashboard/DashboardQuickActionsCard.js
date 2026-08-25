import { Link } from 'react-router-dom';
import {
  Receipt,
  DollarSign,
  Wallet,
  TrendingUp,
  HeartHandshake,
  PlusCircle,
  Landmark,
  UserPlus,
  Package,
  FileText,
  Building2,
} from 'lucide-react';

/**
 * Quick Actions card — common task shortcuts plus financial feature links.
 * The former standalone full-width Money section was merged into this card
 * (money links live in their own row below the task shortcuts).
 */

const MONEY_LINKS = [
  { to: '/transactions', Icon: Receipt, color: 'bg-navy/10 text-navy', title: 'Transactions', subtitle: 'Ledger & imports' },
  { to: '/distributions', Icon: DollarSign, color: 'bg-success/10 text-success', title: 'Distributions', subtitle: 'Beneficiary payments' },
  { to: '/compensation', Icon: Wallet, color: 'bg-navy/10 text-navy', title: 'Compensation', subtitle: 'Trustee payments' },
  { to: '/investments', Icon: TrendingUp, color: 'bg-gold/10 text-gold', title: 'Investments', subtitle: 'Holdings & returns' },
  { to: '/benevolence', Icon: HeartHandshake, color: 'bg-success/10 text-success', title: 'Benevolence', subtitle: 'Charitable giving log' },
];

export const QUICK_ACTIONS = [
  {
    title: 'Record Distribution',
    description: 'Document a distribution to beneficiaries',
    icon: DollarSign,
    path: '/minutes/template/distribution_to_beneficiaries',
    color: 'bg-success/10 text-success'
  },
  {
    title: 'Add Asset to Trust',
    description: 'Accept property and update Trust Assets',
    icon: PlusCircle,
    path: '/minutes/template/acceptance_of_property',
    color: 'bg-navy/10 text-navy'
  },
  {
    title: 'Open Bank Account',
    description: 'Authorize a new trust bank account',
    icon: Landmark,
    path: '/minutes/template/bank_account_authorization',
    color: 'bg-gold/10 text-gold'
  },
  {
    title: 'Appoint Trustee',
    description: 'Add or replace a trustee',
    icon: UserPlus,
    path: '/minutes/template/appointment_additional_trustee',
    color: 'bg-warning/10 text-warning'
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
    title: 'View Structures',
    description: 'Manage trust entities and relationships',
    icon: Building2,
    path: '/structures',
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

      {/* Money links — moved here from the removed full-width Money section */}
      <div className="mt-6 pt-6 border-t border-navy/10">
        <p className="label-trust mb-3">Money</p>
        <div className="grid grid-cols-2 gap-3">
          {MONEY_LINKS.map(link => {
            const Icon = link.Icon;
            return (
              <Link key={link.to} to={link.to} className="p-3 text-left border border-border hover:border-gold transition-colors group" data-testid={`money-link-${link.title.toLowerCase()}`}>
                <div className={`w-8 h-8 ${link.color} flex items-center justify-center mb-2`}>
                  <Icon className="w-4 h-4" />
                </div>
                <p className="font-medium text-sm text-navy group-hover:text-navy/70 transition-colors">{link.title}</p>
                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{link.subtitle}</p>
              </Link>
            );
          })}
        </div>
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
