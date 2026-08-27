import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import PageHelpButton from '@/components/PageHelpButton';
import {
  BarChart3,
  DollarSign,
  TrendingUp,
  Users,
  RefreshCw,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  AlertTriangle,
  Megaphone,
  Share2,
  Search,
  Users as UsersIcon,
  Wallet,
  TrendingDown,
} from 'lucide-react';

const DATE_PRESETS = [
  { key: 'today', label: 'Today' },
  { key: 'this_week', label: 'This Week' },
  { key: 'this_month', label: 'This Month' },
  { key: 'last_30_days', label: 'Last 30 Days' },
  { key: 'last_90_days', label: 'Last 90 Days' },
  { key: 'all_time', label: 'All Time' },
];

export default function StatsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';
  const isStatsUser = user?.is_stats_user || isAdmin;

  const [loading, setLoading] = useState(true);
  const [revenueData, setRevenueData] = useState(null);
  const [error, setError] = useState(null);
  const [preset, setPreset] = useState('last_30_days');
  const [activeTab, setActiveTab] = useState('revenue');
  const [expenseData, setExpenseData] = useState(null);
  const [expenseLoading, setExpenseLoading] = useState(false);

  // Redirect if not stats user and not admin
  useEffect(() => {
    if (user && !isStatsUser) {
      navigate('/dashboard', { replace: true });
    }
  }, [user, isStatsUser, navigate]);

  const fetchRevenueData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchWithAuth(`/stats/dashboard?preset=${preset}`);
      if (response.ok) {
        const data = await response.json();
        setRevenueData(data);
      } else if (response.status === 403) {
        setError('You do not have permission to view stats.');
        if (!isStatsUser) {
          navigate('/dashboard', { replace: true });
        }
      } else {
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.detail || 'Failed to load revenue data');
      }
    } catch (err) {
      console.error('Failed to fetch revenue data:', err);
      setError('Failed to load revenue data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [preset, isStatsUser, navigate]);

  useEffect(() => {
    if (user && isStatsUser) {
      fetchRevenueData();
    }
  }, [user, isStatsUser, fetchRevenueData]);

  // Fetch expense data
  const fetchExpenseData = useCallback(async () => {
    setExpenseLoading(true);
    try {
      const response = await fetchWithAuth(`/stats/marketing-expenses?preset=all_time`);
      if (response.ok) {
        const data = await response.json();
        setExpenseData(data);
      }
    } catch (err) {
      console.error('Failed to fetch expense data:', err);
    } finally {
      setExpenseLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user && isStatsUser && activeTab === 'expenses' && !expenseData) {
      fetchExpenseData();
    }
  }, [user, isStatsUser, activeTab, expenseData, fetchExpenseData]);

  const formatCurrency = (cents) => {
    if (!cents && cents !== 0) return '$0.00';
    return `$${(cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const formatMonth = (monthStr) => {
    const [year, month] = monthStr.split('-');
    const date = new Date(parseInt(year), parseInt(month) - 1);
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  };

  // Access denied check
  if (user && !isStatsUser) {
    return (
      <div className="min-h-screen bg-background flex">
        <Sidebar />
        <main className="flex-1 p-8 lg:ml-64 pb-24 lg:pb-8">
          <div className="max-w-2xl mx-auto text-center py-20">
            <BarChart3 className="w-16 h-16 mx-auto mb-6 text-muted-foreground" />
            <h1 className="font-serif text-3xl text-navy dark:text-white mb-4">Access Denied</h1>
            <p className="text-muted-foreground">
              You don't have permission to view the stats dashboard.
            </p>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  if (loading && !revenueData) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <RefreshCw className="w-8 h-8 animate-spin text-navy dark:text-white" />
      </div>
    );
  }

  const maxRevenue = revenueData?.revenue_by_month?.length > 0
    ? Math.max(...revenueData.revenue_by_month.map(m => m.amount_cents))
    : 0;

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <main className="flex-1 p-4 lg:p-8 lg:ml-64 pb-24 lg:pb-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title flex items-center gap-3">
                <BarChart3 className="w-8 h-8 text-navy dark:text-white" />
                Business Dashboard
              </h1>
              <p className="page-subtitle">Revenue, expenses, and profitability</p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'View revenue metrics, subscription analytics, and business performance' },
                  { text: 'Track MRR, ARR, paid customers, and revenue trends over time' },
                  { text: 'Monitor marketing expenses by category and net profitability' },
                  { text: 'Filter by date range to analyze specific periods' },
                ]}
                taPrompt="Walk me through the Stats dashboard"
              />
              <button
                onClick={() => {
                  fetchRevenueData();
                  if (activeTab === 'expenses') fetchExpenseData();
                }}
                className="btn-primary flex items-center gap-2"
                disabled={loading || expenseLoading}
              >
                <RefreshCw className={`w-4 h-4 ${loading || expenseLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {/* Tab Switcher */}
          <div className="flex gap-1 mb-6 border-b border-navy/10 dark:border-white/10 stats-tab-bar">
            <button
              onClick={() => setActiveTab('revenue')}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'revenue'
                  ? 'border-gold text-navy dark:text-white'
                  : 'border-transparent text-muted-foreground hover:text-navy dark:hover:text-white'
              }`}
            >
              <DollarSign className="w-4 h-4 inline mr-2" />
              Revenue
            </button>
            <button
              onClick={() => setActiveTab('expenses')}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'expenses'
                  ? 'border-gold text-navy dark:text-white'
                  : 'border-transparent text-muted-foreground hover:text-navy dark:hover:text-white'
              }`}
            >
              <TrendingDown className="w-4 h-4 inline mr-2" />
              Expenses
            </button>
          </div>

          {/* Error state */}
          {error && (
            <div className="card-trust p-4 mb-6 border border-rust/30 bg-rust/5 dark:bg-rust/10">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-rust" />
                <div>
                  <p className="font-medium text-rust">{error}</p>
                  {revenueData?.stripe_error && (
                    <p className="text-sm text-muted-foreground mt-1">
                      Stripe API error: {revenueData.stripe_error}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Date Range Selector */}
          <div className="card-trust p-4 mb-6">
            <div className="flex items-center gap-2 mb-3">
              <Calendar className="w-4 h-4 text-muted-foreground" />
              <span className="font-medium text-navy dark:text-white text-sm">Date Range</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {DATE_PRESETS.map((p) => (
                <button
                  key={p.key}
                  onClick={() => setPreset(p.key)}
                  className={`px-3 py-1.5 text-sm font-mono transition-colors ${
                    preset === p.key
                      ? 'bg-navy text-white dark:bg-gold dark:text-navy'
                      : 'bg-navy/5 dark:bg-white/5 text-navy dark:text-white hover:bg-navy/10 dark:hover:bg-white/10'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {revenueData?.date_range && (
              <p className="text-xs text-muted-foreground mt-2 font-mono">
                {new Date(revenueData.date_range.start).toLocaleDateString()} — {new Date(revenueData.date_range.end).toLocaleDateString()}
              </p>
            )}
          </div>

          {/* Revenue Tab */}
          {activeTab === 'revenue' && revenueData && (
            <>
              {/* Revenue Metric Cards */}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
                <div className="card-trust p-4" title="Gross revenue from all paid TrustOffice invoices (Stripe) in the selected date range">
                  <div className="flex items-center gap-2 text-muted-foreground mb-1">
                    <DollarSign className="w-4 h-4 text-gold" />
                    <span className="text-xs">Total Revenue</span>
                  </div>
                  <p className="text-2xl font-bold text-navy dark:text-white">
                    {revenueData.total_revenue_formatted}
                  </p>
                </div>
                <div className="card-trust p-4" title="Monthly Recurring Revenue — (monthly subscribers × $79) + (annual subscribers × $65.83)">
                  <div className="flex items-center gap-2 text-muted-foreground mb-1">
                    <TrendingUp className="w-4 h-4 text-gold" />
                    <span className="text-xs">MRR</span>
                  </div>
                  <p className="text-2xl font-bold text-gold">
                    {revenueData.mrr_formatted}
                  </p>
                </div>
                <div className="card-trust p-4" title="Annual Recurring Revenue — MRR × 12. A projection of annual revenue based on current monthly subscriptions">
                  <div className="flex items-center gap-2 text-muted-foreground mb-1">
                    <TrendingUp className="w-4 h-4 text-navy dark:text-white" />
                    <span className="text-xs">ARR</span>
                  </div>
                  <p className="text-2xl font-bold text-navy dark:text-white">
                    {revenueData.arr_formatted}
                  </p>
                </div>
                <div className="card-trust p-4">
                  <div className="flex items-center gap-2 text-muted-foreground mb-1">
                    <Users className="w-4 h-4 text-navy dark:text-white" />
                    <span className="text-xs">Paid Customers</span>
                  </div>
                  <p className="text-2xl font-bold text-navy dark:text-white">
                    {revenueData.paid_customers}
                  </p>
                </div>
                <div className="card-trust p-4">
                  <div className="flex items-center gap-2 text-muted-foreground mb-1">
                    <DollarSign className="w-4 h-4 text-navy dark:text-white" />
                    <span className="text-xs">Avg/Customer</span>
                  </div>
                  <p className="text-2xl font-bold text-navy dark:text-white">
                    {revenueData.avg_revenue_per_customer_formatted}
                  </p>
                </div>
              </div>

              {/* Period Revenue Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                <div className="card-trust p-4">
                  <div className="text-xs text-muted-foreground mb-1">Today</div>
                  <p className="text-lg font-bold text-navy dark:text-white">
                    {revenueData.revenue_today_formatted}
                  </p>
                </div>
                <div className="card-trust p-4">
                  <div className="text-xs text-muted-foreground mb-1">This Week</div>
                  <p className="text-lg font-bold text-navy dark:text-white">
                    {revenueData.revenue_this_week_formatted}
                  </p>
                </div>
                <div className="card-trust p-4">
                  <div className="text-xs text-muted-foreground mb-1">This Month</div>
                  <p className="text-lg font-bold text-navy dark:text-white">
                    {revenueData.revenue_this_month_formatted}
                  </p>
                </div>
                <div className="card-trust p-4">
                  <div className="text-xs text-muted-foreground mb-1">All Time</div>
                  <p className="text-lg font-bold text-gold">
                    {revenueData.revenue_all_time_formatted}
                  </p>
                </div>
              </div>

              {/* Revenue Over Time & Plan Breakdown */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* Revenue Chart */}
                <div className="card-trust p-6 lg:col-span-2">
                  <h2 className="font-serif text-xl text-navy dark:text-white mb-4">Revenue Over Time</h2>
                  {revenueData.revenue_by_month?.length > 0 ? (
                    <div className="space-y-2">
                      {revenueData.revenue_by_month.map((month) => (
                        <div key={month.month} className="flex items-center gap-3">
                          <span className="text-xs font-mono text-muted-foreground w-20 shrink-0">
                            {formatMonth(month.month)}
                          </span>
                          <div className="flex-1 bg-navy/5 dark:bg-white/5 h-8 relative overflow-hidden">
                            <div
                              className="h-full bg-gold/80 dark:bg-gold/60 transition-all duration-300"
                              style={{
                                width: maxRevenue > 0 ? `${(month.amount_cents / maxRevenue) * 100}%` : '0%',
                              }}
                            />
                          </div>
                          <span className="text-sm font-mono text-navy dark:text-white w-24 text-right shrink-0">
                            {formatCurrency(month.amount_cents)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
                      <p>No revenue data available for this period</p>
                    </div>
                  )}
                </div>

                {/* Plan Breakdown */}
                <div className="card-trust p-6">
                  <h2 className="font-serif text-xl text-navy dark:text-white mb-4">Plan Breakdown</h2>
                  <div className="space-y-4">
                    <div className="p-4 bg-navy/5 dark:bg-white/5">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium text-navy dark:text-white">Monthly</span>
                        <span className="text-sm font-mono text-gold">{revenueData.subscriptions_by_plan?.monthly || 0} invoices</span>
                      </div>
                      <div className="w-full bg-navy/10 dark:bg-white/10 h-2">
                        <div
                          className="h-full bg-gold transition-all"
                          style={{
                            width: `${((revenueData.subscriptions_by_plan?.monthly || 0) / Math.max((revenueData.subscriptions_by_plan?.monthly || 0) + (revenueData.subscriptions_by_plan?.annual || 0), 1)) * 100}%`
                          }}
                        />
                      </div>
                    </div>
                    <div className="p-4 bg-navy/5 dark:bg-white/5">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium text-navy dark:text-white">Annual</span>
                        <span className="text-sm font-mono text-navy dark:text-white">{revenueData.subscriptions_by_plan?.annual || 0} invoices</span>
                      </div>
                      <div className="w-full bg-navy/10 dark:bg-white/10 h-2">
                        <div
                          className="h-full bg-navy dark:bg-white transition-all"
                          style={{
                            width: `${((revenueData.subscriptions_by_plan?.annual || 0) / Math.max((revenueData.subscriptions_by_plan?.monthly || 0) + (revenueData.subscriptions_by_plan?.annual || 0), 1)) * 100}%`
                          }}
                        />
                      </div>
                    </div>
                    <div className="border-t border-navy/10 dark:border-white/10 pt-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-muted-foreground">Active Monthly Subs</span>
                        <span className="text-sm font-bold text-navy dark:text-white">{revenueData.monthly_subs || 0}</span>
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-sm font-medium text-muted-foreground">Active Annual Subs</span>
                        <span className="text-sm font-bold text-navy dark:text-white">{revenueData.annual_subs || 0}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Recent Transactions (admin only sees customer emails) */}
              <div className="card-trust p-6">
                <h2 className="font-serif text-xl text-navy dark:text-white mb-4">
                  Recent Transactions
                </h2>
                {revenueData.recent_transactions?.length > 0 ? (
                  <div className="overflow-x-auto table-scroll-wrapper">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-navy/10 dark:border-white/10">
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Date</th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Amount</th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Plan</th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {revenueData.recent_transactions.slice(0, 20).map((tx, idx) => (
                          <tr key={idx} className="border-b border-navy/5 dark:border-white/5 hover:bg-navy/5 dark:hover:bg-white/5">
                            <td className="py-3 px-4 text-sm text-navy dark:text-white">
                              {new Date(tx.date).toLocaleDateString()}
                            </td>
                            <td className="py-3 px-4 text-sm font-mono text-gold">
                              {formatCurrency(tx.amount_cents)}
                            </td>
                            <td className="py-3 px-4">
                              <span className={`px-2 py-0.5 text-xs font-mono ${
                                tx.plan === 'annual'
                                  ? 'bg-navy/10 dark:bg-white/10 text-navy dark:text-white'
                                  : 'bg-gold/20 text-gold'
                              }`}>
                                {tx.plan}
                              </span>
                            </td>
                            <td className="py-3 px-4">
                              <span className="px-2 py-0.5 text-xs bg-success/10 text-success dark:bg-success/20 dark:text-success">
                                {tx.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <p>No transactions found for this period</p>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Expenses Tab */}
          {activeTab === 'expenses' && (
            <>
              {expenseLoading && !expenseData ? (
                <div className="flex items-center justify-center py-20">
                  <RefreshCw className="w-8 h-8 animate-spin text-navy dark:text-white" />
                </div>
              ) : expenseData ? (
                <>
                  {/* P&L Summary */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                    <div className="card-trust p-4">
                      <div className="flex items-center gap-2 text-muted-foreground mb-1">
                        <DollarSign className="w-4 h-4 text-gold" />
                        <span className="text-xs">Revenue (All Time)</span>
                      </div>
                      <p className="text-2xl font-bold text-navy dark:text-white">
                        {revenueData ? revenueData.revenue_all_time_formatted : '—'}
                      </p>
                    </div>
                    <div className="card-trust p-4">
                      <div className="flex items-center gap-2 text-muted-foreground mb-1">
                        <TrendingDown className="w-4 h-4 text-rust" />
                        <span className="text-xs">Total Expenses</span>
                      </div>
                      <p className="text-2xl font-bold text-rust">
                        {expenseData.total_expenses_formatted}
                      </p>
                    </div>
                    <div className="card-trust p-4">
                      <div className="flex items-center gap-2 text-muted-foreground mb-1">
                        <Wallet className="w-4 h-4 text-navy dark:text-white" />
                        <span className="text-xs">Net P&amp;L</span>
                      </div>
                      <p className={`text-2xl font-bold ${
                        revenueData && (revenueData.revenue_all_time_cents - expenseData.total_expenses_cents) >= 0
                          ? 'text-success'
                          : 'text-rust'
                      }`}>
                        {revenueData
                          ? formatCurrency(revenueData.revenue_all_time_cents - expenseData.total_expenses_cents)
                          : formatCurrency(-expenseData.total_expenses_cents)}
                      </p>
                    </div>
                  </div>

                  {/* Category Cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
                    {expenseData.by_category?.filter(c => c.total_cents > 0).map((cat) => {
                      const icon = cat.category === 'marketing_build' ? <Megaphone className="w-5 h-5 text-gold" />
                        : cat.category === 'meta_ads' ? <Share2 className="w-5 h-5 text-gold" />
                        : cat.category === 'google_ads' ? <Search className="w-5 h-5 text-gold" />
                        : cat.category === 'linkdaddy_seo' ? <Search className="w-5 h-5 text-gold" />
                        : <UsersIcon className="w-5 h-5 text-gold" />;
                      return (
                        <div key={cat.category} className="card-trust p-5">
                          <div className="flex items-center gap-3 mb-3">
                            <div className="w-10 h-10 rounded-full bg-gold/20 flex items-center justify-center">
                              {icon}
                            </div>
                            <div>
                              <p className="font-medium text-navy dark:text-white">{cat.label}</p>
                              <p className="text-xs text-muted-foreground">{cat.description}</p>
                            </div>
                          </div>
                          <p className="text-xl font-bold text-rust font-mono">
                            {cat.total_formatted}
                          </p>
                        </div>
                      );
                    })}
                  </div>

                  {/* Empty categories (no spend yet) */}
                  {expenseData.by_category?.filter(c => c.total_cents === 0).length > 0 && (
                    <div className="mb-8">
                      <p className="text-sm text-muted-foreground mb-3">Categories with no spend yet:</p>
                      <div className="flex flex-wrap gap-2">
                        {expenseData.by_category.filter(c => c.total_cents === 0).map((cat) => (
                          <span key={cat.category} className="px-3 py-1.5 text-xs font-mono bg-navy/5 dark:bg-white/5 text-muted-foreground">
                            {cat.label}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Monthly Expense Chart */}
                  {expenseData.by_month?.length > 0 && (
                    <div className="card-trust p-6 mb-8">
                      <h2 className="font-serif text-xl text-navy dark:text-white mb-4">Expenses Over Time</h2>
                      <div className="space-y-2">
                        {expenseData.by_month.map((month) => {
                          const maxExpense = Math.max(...expenseData.by_month.map(m => m.amount_cents), 1);
                          return (
                            <div key={month.month} className="flex items-center gap-3">
                              <span className="text-xs font-mono text-muted-foreground w-20 shrink-0">
                                {formatMonth(month.month)}
                              </span>
                              <div className="flex-1 bg-navy/5 dark:bg-white/5 h-8 relative overflow-hidden">
                                <div
                                  className="h-full bg-rust/60 transition-all duration-300"
                                  style={{
                                    width: maxExpense > 0 ? `${(month.amount_cents / maxExpense) * 100}%` : '0%',
                                  }}
                                />
                              </div>
                              <span className="text-sm font-mono text-rust w-24 text-right shrink-0">
                                {month.amount_formatted}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="card-trust p-12 text-center">
                  <TrendingDown className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-30" />
                  <h2 className="font-serif text-xl text-navy dark:text-white mb-2">No Expense Data</h2>
                  <p className="text-muted-foreground">
                    Marketing expense data will appear here once entries are added.
                  </p>
                </div>
              )}
            </>
          )}

          {/* Empty state when no data and no error */}
          {activeTab === 'revenue' && !revenueData && !loading && !error && (
            <div className="card-trust p-12 text-center">
              <BarChart3 className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-30" />
              <h2 className="font-serif text-xl text-navy dark:text-white mb-2">No Revenue Data</h2>
              <p className="text-muted-foreground">
                Revenue data will appear here once there are paid subscriptions.
              </p>
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}