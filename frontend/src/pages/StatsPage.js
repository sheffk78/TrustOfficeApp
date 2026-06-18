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
  AlertTriangle
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
                Revenue Dashboard
              </h1>
              <p className="page-subtitle">Revenue metrics and subscription analytics</p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'View revenue metrics, subscription analytics, and business performance' },
                  { text: 'Track MRR, ARR, paid customers, and revenue trends over time' },
                  { text: 'Filter by date range to analyze specific periods' },
                ]}
                taPrompt="Walk me through the Stats dashboard"
              />
              <button
                onClick={fetchRevenueData}
                className="btn-primary flex items-center gap-2"
                disabled={loading}
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
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

          {/* Revenue Metric Cards */}
          {revenueData && (
            <>
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
                  <div className="overflow-x-auto">
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
                              <span className="px-2 py-0.5 text-xs bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
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

          {/* Empty state when no data and no error */}
          {!revenueData && !loading && !error && (
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