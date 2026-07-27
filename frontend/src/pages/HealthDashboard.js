import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import PageHelpButton from '@/components/PageHelpButton';
import HealthScoreDisplay from '@/components/HealthScoreDisplay';
import HealthTrendChart from '@/components/HealthTrendChart';
import EducationalPanel from '@/components/EducationalPanel';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  Shield,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';

const RANGE_OPTIONS = [30, 60, 90];

const severityBadge = (severity) => {
  const s = (severity || '').toLowerCase();
  if (s === 'critical') return 'bg-error/10 text-error border-error/20';
  if (s === 'high') return 'bg-orange-500/10 text-orange-600 border-orange-500/20';
  if (s === 'medium') return 'bg-warning/10 text-warning border-warning/20';
  return 'bg-muted text-muted-foreground border-border';
};

const getScoreTextClass = (score) => {
  if (score >= 96) return 'text-success';
  if (score >= 72) return 'text-warning';
  return 'text-error';
};

export default function HealthDashboard() {
  const { selectedTrust } = useAuth();
  const [health, setHealth] = useState(null);
  const [trend, setTrend] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(90);

  const loadHealth = useCallback(async () => {
    if (!selectedTrust) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      // Current health — try dedicated endpoint, fall back to governance
      let healthData = null;
      const healthRes = await fetchWithAuth(`/health/${selectedTrust.trust_id}/current`);
      if (healthRes.ok) {
        healthData = await healthRes.json();
      } else {
        const govRes = await fetchWithAuth(`/governance/${selectedTrust.trust_id}`);
        if (govRes.ok) {
          healthData = await govRes.json();
        }
      }
      setHealth(healthData);

      // Trend
      const trendRes = await fetchWithAuth(`/health/${selectedTrust.trust_id}/trend?days=${days}`);
      if (trendRes.ok) {
        const t = await trendRes.json();
        setTrend(t.trend || t.history || []);
      } else {
        // Fall back to governance history
        const histRes = await fetchWithAuth(`/governance/${selectedTrust.trust_id}/history?days=${days}`);
        if (histRes.ok) {
          const h = await histRes.json();
          setTrend(h.history || []);
        } else {
          setTrend([]);
        }
      }

      // Alerts / risk findings
      const alertsRes = await fetchWithAuth(`/health/${selectedTrust.trust_id}/alerts`);
      if (alertsRes.ok) {
        const a = await alertsRes.json();
        setAlerts(a.alerts || a.risk_findings || a || []);
      } else {
        setAlerts(healthData?.risk_findings || []);
      }
    } catch (error) {
      showError(error);
    } finally {
      setLoading(false);
    }
  }, [selectedTrust, days]);

  useEffect(() => {
    loadHealth();
  }, [loadHealth]);

  const score = health?.total_score ?? health?.health_score ?? 0;
  const maxScore = health?.max_score || 115;
  const criteria = health?.criteria || [];
  const riskFindings = alerts.length > 0 ? alerts : (health?.risk_findings || []);

  const getTrendDelta = () => {
    if (trend.length < 2) return { direction: 'stable', change: 0 };
    const first = trend[0].score;
    const last = trend[trend.length - 1].score;
    const change = last - first;
    return {
      direction: change > 0 ? 'up' : change < 0 ? 'down' : 'stable',
      change: Math.abs(change),
    };
  };
  const delta = getTrendDelta();

  return (
    <div className="main-layout" data-testid="health-dashboard-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Health Score</h1>
              <p className="page-subtitle">
                Detailed breakdown of {selectedTrust?.trust_name || 'trust'} health, risk findings, and score history
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'View your trust health score broken down by criterion' },
                  { text: 'Track score changes over 30, 60, or 90 days' },
                  { text: 'Review risk findings ranked by severity and take action' },
                ]}
                taPrompt="Explain my trust health score and what I can do to improve it"
              />
              <Button
                onClick={loadHealth}
                variant="outline"
                className="btn-secondary"
                data-testid="refresh-health-btn"
              >
                <RefreshCw className="w-4 h-4 mr-2" />
                Refresh
              </Button>
            </div>
          </div>

          {!selectedTrust ? (
            <div className="card-trust p-8 text-center text-muted-foreground">
              <Shield className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>Select a trust to view its health score.</p>
            </div>
          ) : loading ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 card-trust"><div className="skeleton h-64 w-full"></div></div>
              <div className="card-trust"><div className="skeleton h-64 w-full"></div></div>
            </div>
          ) : (
            <>
              {/* Score + Criteria */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                <div className="lg:col-span-2 card-trust corner-mark">
                  <div className="flex flex-col md:flex-row items-center gap-8">
                    <div className="text-center">
                      <HealthScoreDisplay score={score} maxScore={maxScore} size="lg" />
                      <div className="mt-4 flex items-center justify-center gap-2">
                        {delta.direction === 'up' ? (
                          <TrendingUp className="w-4 h-4 text-success" />
                        ) : delta.direction === 'down' ? (
                          <TrendingDown className="w-4 h-4 text-error" />
                        ) : null}
                        <span
                          className={`font-mono text-sm ${
                            delta.direction === 'up'
                              ? 'text-success'
                              : delta.direction === 'down'
                              ? 'text-error'
                              : 'text-muted-foreground'
                          }`}
                        >
                          {delta.direction === 'stable'
                            ? 'Stable'
                            : `${delta.direction === 'up' ? '+' : '-'}${delta.change} pts (${days}d)`}
                        </span>
                      </div>
                    </div>

                    <div className="flex-1 w-full">
                      <h3 className="font-serif text-lg text-navy mb-4">Score Breakdown</h3>
                      {criteria.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No criteria data available.</p>
                      ) : (
                        <div className="space-y-3">
                          {criteria.map((c, i) => (
                            <div
                              key={i}
                              className={`flex items-center justify-between p-3 border ${
                                c.achieved ? 'border-success/30 bg-success/5' : 'border-navy/10'
                              }`}
                              data-testid={`criterion-${i}`}
                            >
                              <div className="flex items-center gap-3">
                                {c.achieved ? (
                                  <CheckCircle2 className="w-5 h-5 text-success flex-shrink-0" />
                                ) : (
                                  <XCircle className="w-5 h-5 text-error/60 flex-shrink-0" />
                                )}
                                <div>
                                  <p
                                    className={`font-medium text-sm ${
                                      c.achieved ? 'text-navy' : 'text-muted-foreground'
                                    }`}
                                  >
                                    {c.name}
                                  </p>
                                  <p className="text-xs text-muted-foreground">{c.description}</p>
                                </div>
                              </div>
                              <span
                                className={`font-mono text-lg ${
                                  c.achieved ? 'text-success' : 'text-muted-foreground'
                                }`}
                              >
                                {c.points}/{c.max_points}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Trend chart card */}
                <div className="card-trust">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-serif text-lg text-navy">Score Trend</h3>
                    <div className="flex gap-1">
                      {RANGE_OPTIONS.map((d) => (
                        <button
                          key={d}
                          onClick={() => setDays(d)}
                          className={`px-2 py-1 text-xs font-mono border transition-colors ${
                            days === d
                              ? 'bg-navy text-cream border-navy'
                              : 'border-navy/20 text-muted-foreground hover:border-navy/40'
                          }`}
                          data-testid={`range-${d}`}
                        >
                          {d}d
                        </button>
                      ))}
                    </div>
                  </div>
                  <HealthTrendChart data={trend} height={220} width={600} maxScore={maxScore} />
                  <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      Zone:{' '}
                      <span className={`font-medium ${getScoreTextClass(score)}`}>
                        {score >= 96 ? 'Healthy' : score >= 72 ? 'At Risk' : 'Critical'}
                      </span>
                    </span>
                    <span className="font-mono">{trend.length} data points</span>
                  </div>
                </div>
              </div>

              {/* Risk Findings */}
              <div className="card-trust">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-serif text-lg text-navy flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-warning" />
                    Risk Findings
                  </h3>
                  <Badge variant="outline" className="font-mono">
                    {riskFindings.length}
                  </Badge>
                </div>
                {riskFindings.length === 0 ? (
                  <div className="p-6 text-center text-muted-foreground">
                    <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-success" />
                    <p className="text-sm">No active risk findings. This trust is in good standing.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {riskFindings.map((finding, i) => (
                      <div
                        key={finding.id || i}
                        className="flex items-start justify-between gap-4 p-4 border border-navy/10"
                        data-testid={`risk-finding-${i}`}
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span
                              className={`inline-block px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider border ${severityBadge(
                                finding.severity
                              )}`}
                            >
                              {finding.severity || 'low'}
                            </span>
                            <h4 className="font-medium text-sm text-navy">{finding.title}</h4>
                          </div>
                          <p className="text-xs text-muted-foreground">{finding.detail || finding.description}</p>
                        </div>
                        {finding.action_link && (
                          <Link
                            to={finding.action_link}
                            className="flex items-center gap-1 text-xs text-navy hover:underline flex-shrink-0"
                          >
                            Take action
                            <ArrowRight className="w-3 h-3" />
                          </Link>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Educational Resources */}
              <div className="mt-8">
                <EducationalPanel trustId={selectedTrust?.trust_id} healthScore={score} />
              </div>
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
