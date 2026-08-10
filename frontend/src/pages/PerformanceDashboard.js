import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import { showError } from '@/utils/errors';
import { toast } from 'sonner';
import PageHelpButton from '@/components/PageHelpButton';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from 'recharts';
import {
  LayoutDashboard,
  FilePen,
  Send,
  Shield,
  TrendingUp,
  Clock,
  Activity,
  RefreshCw,
  ChevronRight,
  ArrowUpRight,
  ArrowDownRight,
  AlertTriangle,
  BarChart3,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

const COLORS = ['#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];
const CHART_COLORS = {
  minutes: '#0ea5e9',
  distributions: '#10b981',
  approved: '#f59e0b',
};

export default function PerformanceDashboard() {
  const { user, selectedTrust } = useAuth();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [trends, setTrends] = useState(null);
  const [activities, setActivities] = useState(null);
  const [benchmarks, setBenchmarks] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [benchmarkView, setBenchmarkView] = useState('distribution');

  const loadData = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);

    try {
      // Load all performance data in parallel
      const [summaryRes, trendsRes, activityRes, benchmarksRes] = await Promise.all([
        fetchWithAuth('/performance/summary'),
        fetchWithAuth('/performance/trends?months=6'),
        fetchWithAuth('/performance/recent-activity?limit=20'),
        fetchWithAuth('/performance/benchmarks'),
      ]);

      if (!summaryRes.ok) throw new Error('Failed to load summary');
      if (!trendsRes.ok) throw new Error('Failed to load trends');
      if (!activityRes.ok) throw new Error('Failed to load activity');
      if (!benchmarksRes.ok) throw new Error('Failed to load benchmarks');

      const summaryData = await summaryRes.json();
      const trendsData = await trendsRes.json();
      const activityData = await activityRes.json();
      const benchmarksData = await benchmarksRes.json();

      setSummary(summaryData);
      setTrends(trendsData);
      setActivities(activityData);
      setBenchmarks(benchmarksData);
    } catch (err) {
      console.error('Failed to load performance data:', err);
      setError(err.message || 'Failed to load performance data');
      showError(toast, err, { operation: 'load_performance', page: 'PerformanceDashboard' });
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = () => {
    loadData();
  };

  // Loading skeleton
  if (loading && !summary) {
    return (
      <div className="min-h-screen bg-background flex">
        <Sidebar />
        <main className="flex-1 p-4 lg:p-8 lg:ml-64 pb-24 lg:pb-8">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center gap-3 mb-8">
              <LayoutDashboard className="w-8 h-8 text-navy animate-pulse" />
              <div className="h-8 w-48 bg-navy/10 animate-pulse rounded"></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="card-trust p-6">
                  <div className="h-4 w-24 bg-navy/10 animate-pulse rounded mb-3"></div>
                  <div className="h-10 w-20 bg-navy/10 animate-pulse rounded"></div>
                </div>
              ))}
            </div>
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="card-trust p-6">
                  <div className="h-4 w-32 bg-navy/10 animate-pulse rounded mb-4"></div>
                  <div className="h-48 bg-navy/5 animate-pulse rounded"></div>
                </div>
              ))}
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  // Error state
  if (error && !summary) {
    return (
      <div className="min-h-screen bg-background flex">
        <Sidebar />
        <main className="flex-1 p-4 lg:p-8 lg:ml-64 pb-24 lg:pb-8">
          <div className="max-w-7xl mx-auto text-center py-20">
            <AlertTriangle className="w-16 h-16 mx-auto mb-6 text-rust" />
            <h1 className="font-serif text-3xl text-navy dark:text-white mb-4">
              Failed to Load Performance Data
            </h1>
            <p className="text-muted-foreground mb-6">{error}</p>
            <Button onClick={handleRefresh} className="btn-primary">
              <RefreshCw className="w-4 h-4 mr-2" />
              Try Again
            </Button>
          </div>
          <MobileBottomNav />
        </main>
        <Sidebar />
      </div>
    );
  }

  // Activity type icon map
  const activityTypeIcons = {
    minutes: <FilePen className="w-4 h-4" />,
    distribution: <Send className="w-4 h-4" />,
    task: <Activity className="w-4 h-4" />,
  };

  const activityActionLabels = {
    minutes_created: 'Created minutes',
    minutes_drafted: 'Drafted minutes',
    distribution_approved: 'Approved distribution',
    distribution_reviewed: 'Reviewed distribution',
    distribution_created: 'Created distribution',
    task_completed: 'Completed task',
    task_created: 'Created task',
  };

  const activityStatusColors = {
    finalized: 'bg-success/10 text-success',
    draft: 'bg-muted text-muted-foreground',
    review: 'bg-warning/10 text-warning',
    approved: 'bg-success/10 text-success',
    declined: 'bg-error/10 text-error',
    completed: 'bg-success/10 text-success',
    upcoming: 'bg-muted text-muted-foreground',
    pending: 'bg-warning/10 text-warning',
  };

  // Format helpers
  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return dateStr;
    }
  };

  // ===== KPI CARDS =====
  const kpiCards = [
    {
      title: 'Trusts Managed',
      value: summary?.trusts_managed || 0,
      icon: LayoutDashboard,
      color: 'text-navy',
      bgColor: 'bg-navy/10',
    },
    {
      title: 'Minutes Created',
      value: summary?.minutes_created || 0,
      icon: FilePen,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
    },
    {
      title: 'Distributions Processed',
      value: summary?.distributions_processed || 0,
      icon: Send,
      color: 'text-green-600',
      bgColor: 'bg-green-600/10',
    },
    {
      title: 'Compliance Score',
      value: (summary?.compliance_score || 0) + '/100',
      icon: Shield,
      color: 'text-purple-600',
      bgColor: 'bg-purple-600/10',
    },
  ];

  // ===== DISTRIBUTION STATUS BREAKDOWN =====
  const distributionStatusData = summary?.distribution_status_breakdown
    ? Object.entries(summary.distribution_status_breakdown).map(([status, count]) => ({
        status,
        count,
      }))
    : [];

  // ===== TREND CHART DATA =====
  const trendData = trends?.trends || [];

  // ===== BENCHMARK DATA =====
  const platformStats = benchmarks?.platform_stats || {};
  const monthlyTrends = benchmarks?.monthly_trends || [];

  // Toggle for benchmark chart

  const benchmarkChartData = benchmarkView === 'distribution'
    ? monthlyTrends.map((m) => ({
        month: m.month,
        Total: m.distributions_total,
        Approved: m.distributions_approved,
      }))
    : monthlyTrends.map((m) => ({
        month: m.month,
        Minutes: m.minutes,
      }));

  // ===== ACTIVITY FEED =====
  const recentActivities = activities?.activities || [];

  return (
    <div className="min-h-screen bg-background flex" data-testid="performance-page">
      <Sidebar />
      <main className="flex-1 p-4 lg:p-8 lg:ml-64 pb-24 lg:pb-8">
        <div className="max-w-7xl mx-auto">
          {/* Page Header */}
          <div className="page-header flex items-start justify-between">
            <div>
              <h1 className="page-title flex items-center gap-3">
                <BarChart3 className="w-8 h-8 text-navy dark:text-white" />
                Performance Dashboard
              </h1>
              <p className="page-subtitle">
                Key performance metrics for your trusts — minutes, distributions, compliance, and trends
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'View aggregated KPIs across all your managed trusts' },
                  { text: 'Track monthly trends in minutes creation and distributions' },
                  { text: 'Monitor recent activity across all trusts in one feed' },
                  { text: 'Compare your performance against platform-wide benchmarks' },
                ]}
                taPrompt="Walk me through the Performance Dashboard and what each section shows"
              />
              <button
                onClick={handleRefresh}
                className="btn-primary flex items-center gap-2"
                disabled={loading}
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {/* Trust Selector Note */}
          {summary?.trusts?.length === 0 && (
            <div className="card-trust p-6 mb-6 border-l-4 border-l-gold bg-gold/5">
              <p className="text-sm text-navy">
                📋 No trusts found. Create your first trust on the{' '}
                <a href="/onboarding" className="underline font-medium">onboarding page</a> to start tracking performance.
              </p>
            </div>
          )}

          {/* ===== KPI CARDS ===== */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            {kpiCards.map((kpi, idx) => (
              <Card
                key={idx}
                className="card-trust border-0 shadow-sm overflow-hidden group"
                data-testid={`kpi-${kpi.title.toLowerCase().replace(/\s+/g, '-')}`}
              >
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <div className={`w-10 h-10 rounded-lg ${kpi.bgColor} flex items-center justify-center`}>
                    <kpi.icon className={`w-5 h-5 ${kpi.color}`} />
                  </div>
                  <Badge variant="secondary" className="text-xs font-mono">
                    {activeTab === 'overview' ? 'Current' : '6mo'}
                  </Badge>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold text-navy dark:text-white tabular-nums">
                    {kpi.value}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">{kpi.title}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* ===== DISTRIBUTION STATUS BREAKDOWN ===== */}
          {distributionStatusData.length > 0 && (
            <Card className="card-trust mb-8 border-0 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Send className="w-4 h-4 text-navy" />
                  Distribution Status Breakdown
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-3">
                  {distributionStatusData.map((item) => (
                    <div
                      key={item.status}
                      className="flex items-center gap-2 p-3 rounded-lg bg-navy/5 dark:bg-white/5 min-w-[120px]"
                    >
                      <div
                        className={`w-3 h-3 rounded-full ${
                          item.status === 'approved'
                            ? 'bg-green-500'
                            : item.status === 'review' || item.status === 'pending'
                            ? 'bg-warning'
                            : item.status === 'declined'
                            ? 'bg-error'
                            : 'bg-muted-foreground'
                        }`}
                      />
                      <span className="text-sm font-medium capitalize text-navy dark:text-white">
                        {item.status}
                      </span>
                      <span className="text-sm font-mono text-muted-foreground">
                        {item.count}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* ===== TREND CHARTS ===== */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {/* Monthly Trends — Minutes & Distributions */}
            <Card className="card-trust border-0 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <TrendingUp className="w-4 h-4 text-navy" />
                  Monthly Trends (Last 6 Months)
                </CardTitle>
              </CardHeader>
              <CardContent>
                {trendData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={trendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0 dark:#334155" />
                      <XAxis
                        dataKey="month"
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        axisLine={{ stroke: '#cbd5e1' }}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        axisLine={{ stroke: '#cbd5e1' }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #334155',
                          borderRadius: '8px',
                          color: '#f1f5f9',
                        }}
                      />
                      <Bar dataKey="minutes_created" fill={CHART_COLORS.minutes} radius={[4, 4, 0, 0]} name="Minutes" />
                      <Bar dataKey="distributions_processed" fill={CHART_COLORS.distributions} radius={[4, 4, 0, 0]} name="Distributions" />
                      <Bar dataKey="distributions_approved" fill={CHART_COLORS.approved} radius={[4, 4, 0, 0]} name="Approved" />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="text-center py-10 text-muted-foreground">
                    <TrendingUp className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p>No trend data available yet</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Compliance by Trust */}
            <Card className="card-trust border-0 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Shield className="w-4 h-4 text-navy" />
                  Compliance Score by Trust
                </CardTitle>
              </CardHeader>
              <CardContent>
                {summary?.trusts?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart
                      data={summary.trusts}
                      margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
                      barSize={32}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0 dark:#334155" />
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 10, fill: '#64748b' }}
                        axisLine={{ stroke: '#cbd5e1' }}
                        interval={0}
                        angle={-15}
                        textAnchor="end"
                        height={60}
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        axisLine={{ stroke: '#cbd5e1' }}
                        tickFormatter={(v) => v + '%'}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #334155',
                          borderRadius: '8px',
                          color: '#f1f5f9',
                        }}
                        formatter={(value) => [`${value}%`, 'Compliance Score']}
                      />
                      <Bar dataKey="compliance_score" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="Compliance" />
                      <Bar dataKey="minutes_count" fill="#0ea5e9" radius={[4, 4, 0, 0]} name="Minutes" opacity={0.6} />
                      <Bar dataKey="distributions_count" fill="#10b981" radius={[4, 4, 0, 0]} name="Distributions" opacity={0.6} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="text-center py-10 text-muted-foreground">
                    <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p>No trust compliance data available</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* ===== BENCHMARKS ===== */}
          <Card className="card-trust mb-8 border-0 shadow-sm">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <Activity className="w-4 h-4 text-navy" />
                Platform Benchmarks
              </CardTitle>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  variant={benchmarkView === 'distribution' ? 'default' : 'outline'}
                  onClick={() => setBenchmarkView('distribution')}
                  className="text-xs"
                >
                  Distributions
                </Button>
                <Button
                  size="sm"
                  variant={benchmarkView === 'minutes' ? 'default' : 'outline'}
                  onClick={() => setBenchmarkView('minutes')}
                  className="text-xs"
                >
                  Minutes
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {/* Platform Stats Summary */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="p-3 rounded-lg bg-navy/5 dark:bg-white/5">
                  <p className="text-xs text-muted-foreground mb-1">Total Minutes (6mo)</p>
                  <p className="text-lg font-bold text-navy dark:text-white">
                    {platformStats.total_minutes_6mo || 0}
                  </p>
                </div>
                <div className="p-3 rounded-lg bg-navy/5 dark:bg-white/5">
                  <p className="text-xs text-muted-foreground mb-1">Total Distributions (6mo)</p>
                  <p className="text-lg font-bold text-navy dark:text-white">
                    {platformStats.total_distributions_6mo || 0}
                  </p>
                </div>
                <div className="p-3 rounded-lg bg-navy/5 dark:bg-white/5">
                  <p className="text-xs text-muted-foreground mb-1">Distribution Value (6mo)</p>
                  <p className="text-lg font-bold text-gold">
                    ${(platformStats.total_distribution_amount_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </p>
                </div>
                <div className="p-3 rounded-lg bg-navy/5 dark:bg-white/5">
                  <p className="text-xs text-muted-foreground mb-1">Platform Approval Rate</p>
                  <p className="text-lg font-bold text-success">
                    {platformStats.approval_rate || 0}%
                  </p>
                </div>
              </div>

              {/* Benchmark Trend Chart */}
              {monthlyTrends.length > 0 ? (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={benchmarkChartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0 dark:#334155" />
                    <XAxis
                      dataKey="month"
                      tick={{ fontSize: 11, fill: '#64748b' }}
                      axisLine={{ stroke: '#cbd5e1' }}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: '#64748b' }}
                      axisLine={{ stroke: '#cbd5e1' }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        border: '1px solid #334155',
                        borderRadius: '8px',
                        color: '#f1f5f9',
                      }}
                    />
                    {benchmarkView === 'distribution' ? (
                      <>
                        <Line
                          type="monotone"
                          dataKey="Total"
                          stroke={CHART_COLORS.distributions}
                          strokeWidth={2}
                          dot={{ r: 4 }}
                          activeDot={{ r: 6 }}
                        />
                        <Line
                          type="monotone"
                          dataKey="Approved"
                          stroke={CHART_COLORS.approved}
                          strokeWidth={2}
                          dot={{ r: 4 }}
                          activeDot={{ r: 6 }}
                        />
                      </>
                    ) : (
                      <Line
                        type="monotone"
                        dataKey="Minutes"
                        stroke={CHART_COLORS.minutes}
                        strokeWidth={2}
                        dot={{ r: 4 }}
                        activeDot={{ r: 6 }}
                      />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p>No benchmark data available yet</p>
                </div>
              )}

              {/* Trust Distribution */}
              {benchmarks?.trust_distribution?.length > 0 && (
                <>
                  <h3 className="font-medium text-navy dark:text-white mb-3 mt-6">Trust Distribution</h3>
                  <div className="flex flex-wrap gap-3">
                    {benchmarks.trust_distribution.map((item, idx) => (
                      <div
                        key={idx}
                        className="flex items-center gap-2 p-2 rounded-lg bg-navy/5 dark:bg-white/5 text-sm"
                      >
                        <span className="text-muted-foreground">{item.trusts_count} trust{item.trusts_count !== 1 ? 's' : ''}:</span>
                        <span className="font-mono font-medium text-navy dark:text-white">{item.users_count}</span>
                        <span className="text-muted-foreground">users</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* ===== RECENT ACTIVITY FEED ===== */}
          <Card className="card-trust border-0 shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Clock className="w-4 h-4 text-navy" />
                Recent Activity
              </CardTitle>
            </CardHeader>
            <CardContent>
              {recentActivities.length > 0 ? (
                <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2">
                  {recentActivities.map((activity, idx) => (
                    <div
                      key={activity.id || idx}
                      className="flex items-start gap-3 p-3 rounded-lg hover:bg-navy/5 dark:hover:bg-white/5 transition-colors border border-transparent hover:border-navy/10"
                    >
                      <div
                        className={`p-2 rounded-lg ${activityStatusColors[activity.status] || 'bg-muted/10'} shrink-0`}
                      >
                        {activityTypeIcons[activity.type] || <Activity className="w-4 h-4" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-navy dark:text-white truncate">
                          {activity.description}
                        </p>
                        {activity.trust_name && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {activity.trust_name}
                          </p>
                        )}
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-xs text-muted-foreground">
                          {formatDate(activity.date)}
                        </p>
                        <Badge
                          variant="secondary"
                          className={`text-[10px] mt-1 ${activityStatusColors[activity.status] || 'bg-muted'}`}
                        >
                          {activityActionLabels[activity.action] || activity.action}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-10 text-muted-foreground">
                  <Clock className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p>No recent activity</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}