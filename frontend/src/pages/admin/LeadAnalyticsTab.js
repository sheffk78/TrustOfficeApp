import { BarChart3, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FUNNEL_STAGES } from './helpers';

export function LeadAnalyticsTab({ leadAnalytics, leadAnalyticsLoading, onRefresh }) {
  return (
    <div className="card-trust p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-serif text-xl text-navy dark:text-white">Lead Analytics</h2>
        <Button variant="outline" onClick={onRefresh}>
          <RefreshCw className={`w-4 h-4 ${leadAnalyticsLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {leadAnalyticsLoading && !leadAnalytics ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-8 h-8 animate-spin text-navy dark:text-white" />
        </div>
      ) : leadAnalytics ? (
        <div className="space-y-6">
          {/* Funnel Overview */}
          <div>
            <h3 className="font-medium text-navy dark:text-white mb-3">Funnel</h3>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              {FUNNEL_STAGES.map((s) => (
                <div key={s.key} className="p-3 border border-navy/10 dark:border-white/10 rounded text-center">
                  <div className={`w-3 h-3 rounded-full ${s.color} mx-auto mb-1`} />
                  <p className="text-lg font-bold text-navy dark:text-white">{leadAnalytics.funnel?.[s.key] || 0}</p>
                  <p className="text-xs text-muted-foreground">{s.label}</p>
                </div>
              ))}
              <div className="p-3 border border-navy/10 dark:border-white/10 rounded text-center">
                <p className="text-lg font-bold text-navy dark:text-white">{leadAnalytics.total_leads || 0}</p>
                <p className="text-xs text-muted-foreground">Total</p>
              </div>
            </div>
          </div>

          {/* Conversion Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 border border-navy/10 dark:border-white/10 rounded">
              <p className="text-xs text-muted-foreground mb-1">Total Converted</p>
              <p className="text-2xl font-bold text-success">{leadAnalytics.total_converted || 0}</p>
            </div>
            <div className="p-4 border border-navy/10 dark:border-white/10 rounded">
              <p className="text-xs text-muted-foreground mb-1">Avg Time to Convert</p>
              <p className="text-2xl font-bold text-navy dark:text-white">
                {leadAnalytics.avg_time_to_convert_days !== null ? `${leadAnalytics.avg_time_to_convert_days} days` : '—'}
              </p>
            </div>
            <div className="p-4 border border-navy/10 dark:border-white/10 rounded">
              <p className="text-xs text-muted-foreground mb-1">Median Time to Convert</p>
              <p className="text-2xl font-bold text-navy dark:text-white">
                {leadAnalytics.median_time_to_convert_days !== null ? `${leadAnalytics.median_time_to_convert_days} days` : '—'}
              </p>
            </div>
          </div>

          {/* Conversion by Source */}
          <div>
            <h3 className="font-medium text-navy dark:text-white mb-3">Conversion Rate by Source</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-navy/10 dark:border-white/10">
                    <th className="text-left py-2 px-3 text-sm font-medium text-muted-foreground">Source</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Total</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Converted</th>
                    <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {leadAnalytics.source_stats?.map((s) => (
                    <tr key={s.source} className="border-b border-navy/5 dark:border-white/5">
                      <td className="py-2 px-3 text-sm text-navy dark:text-white">{s.source}</td>
                      <td className="py-2 px-3 text-sm text-right text-muted-foreground">{s.total}</td>
                      <td className="py-2 px-3 text-sm text-right text-success">{s.converted}</td>
                      <td className="py-2 px-3 text-sm text-right font-mono">{s.conversion_rate}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* 30-Day Trend */}
          <div>
            <h3 className="font-medium text-navy dark:text-white mb-3">Leads Per Day (Last 30 Days)</h3>
            {leadAnalytics.trend?.length > 0 ? (
              <div className="space-y-1">
                {leadAnalytics.trend.map((day) => {
                  const maxCount = Math.max(...leadAnalytics.trend.map(d => d.count), 1);
                  return (
                    <div key={day.date} className="flex items-center gap-3">
                      <span className="text-xs font-mono text-muted-foreground w-24 shrink-0">
                        {new Date(day.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      </span>
                      <div className="flex-1 bg-navy/5 dark:bg-white/5 h-6 relative overflow-hidden">
                        <div
                          className="h-full bg-gold/70 transition-all duration-300"
                          style={{ width: `${(day.count / maxCount) * 100}%` }}
                        />
                      </div>
                      <span className="text-sm font-mono text-navy dark:text-white w-8 text-right shrink-0">
                        {day.count}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No lead data in the last 30 days</p>
            )}
          </div>
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>Click refresh to load lead analytics</p>
        </div>
      )}
    </div>
  );
}
