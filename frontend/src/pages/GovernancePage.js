import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import { 
  Shield,
  ArrowUpDown,
  Calendar,
  FileText,
  DollarSign,
  Wallet,
  CheckCircle2,
  Circle,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Info,
  RefreshCw
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { format, parseISO, subDays } from 'date-fns';

export default function GovernancePage() {
  const { selectedTrust } = useAuth();
  const [governance, setGovernance] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (selectedTrust) {
      loadGovernanceData();
    }
  }, [selectedTrust]);

  const loadGovernanceData = async () => {
    if (!selectedTrust) {
      setLoading(false);
      return;
    }
    
    setLoading(true);
    try {
      const [govResponse, histResponse] = await Promise.all([
        fetchWithAuth(`/governance/${selectedTrust.trust_id}`),
        fetchWithAuth(`/governance/${selectedTrust.trust_id}/history?days=30`)
      ]);
      
      if (govResponse.ok) {
        setGovernance(await govResponse.json());
      }
      if (histResponse.ok) {
        setHistory((await histResponse.json()).history || []);
      }
    } catch (error) {
      console.error('Failed to load governance data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getScoreColor = (score) => {
    if (score >= 80) return 'text-success';
    if (score >= 60) return 'text-warning';
    return 'text-error';
  };

  const getScoreBgColor = (score) => {
    if (score >= 80) return 'bg-success';
    if (score >= 60) return 'bg-warning';
    return 'bg-error';
  };

  const getCriterionIcon = (name) => {
    switch (name) {
      case 'Quarterly Minutes': return <FileText className="w-5 h-5" />;
      case 'Task Compliance': return <Calendar className="w-5 h-5" />;
      case 'Compensation Alignment': return <Wallet className="w-5 h-5" />;
      case 'Distribution Documentation': return <DollarSign className="w-5 h-5" />;
      case 'Annual Review': return <TrendingUp className="w-5 h-5" />;
      default: return <Shield className="w-5 h-5" />;
    }
  };

  const formatDate = (dateString) => {
    try {
      return format(parseISO(dateString), 'MMM d');
    } catch {
      return dateString;
    }
  };

  // Calculate chart dimensions
  const chartHeight = 120;
  const chartWidth = 100;
  const maxScore = 100;

  // Generate chart points
  const getChartPoints = () => {
    if (history.length === 0) return '';
    
    const points = history.map((item, index) => {
      const x = (index / (history.length - 1 || 1)) * chartWidth;
      const y = chartHeight - (item.score / maxScore) * chartHeight;
      return `${x},${y}`;
    });
    
    return points.join(' ');
  };

  const getChartArea = () => {
    if (history.length === 0) return '';
    
    const points = history.map((item, index) => {
      const x = (index / (history.length - 1 || 1)) * chartWidth;
      const y = chartHeight - (item.score / maxScore) * chartHeight;
      return `${x},${y}`;
    });
    
    return `0,${chartHeight} ${points.join(' ')} ${chartWidth},${chartHeight}`;
  };

  // Calculate trend
  const getTrend = () => {
    if (history.length < 2) return { direction: 'stable', change: 0 };
    const first = history[0].score;
    const last = history[history.length - 1].score;
    const change = last - first;
    return {
      direction: change > 0 ? 'up' : change < 0 ? 'down' : 'stable',
      change: Math.abs(change)
    };
  };

  const trend = getTrend();

  return (
    <div className="main-layout" data-testid="governance-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Defensibility Score</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'} • 7-Criteria Assessment
              </p>
            </div>
            <Button 
              onClick={loadGovernanceData}
              variant="outline"
              className="btn-secondary"
              data-testid="refresh-score-btn"
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </Button>
          </div>

          {/* Rename Notice Banner */}
          <div className="mb-6 p-3 bg-navy/5 border border-navy/20 rounded flex items-start gap-3" data-testid="rename-notice">
            <Info className="w-4 h-4 text-navy flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-navy">
                We renamed <strong>Governance Health</strong> to <strong>Defensibility Score</strong>. Same score, clearer name — it tracks how well your records would hold up if anyone ever asked.
              </p>
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 card-trust">
                <div className="skeleton h-48 w-full"></div>
              </div>
              <div className="card-trust">
                <div className="skeleton h-48 w-full"></div>
              </div>
            </div>
          ) : (
            <>
              {/* Score Overview + Chart */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* Main Score */}
                <div className="lg:col-span-2 card-trust corner-mark">
                  <div className="flex flex-col md:flex-row items-center gap-8">
                    {/* Score Circle */}
                    <div className="text-center">
                      <div className="score-circle">
                        <span className={`score-indicator ${getScoreColor(governance?.total_score || 0)}`}>
                          {governance?.total_score || 0}
                        </span>
                        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
                          / 100
                        </span>
                      </div>
                      <div className="mt-4 flex items-center justify-center gap-2">
                        {trend.direction === 'up' ? (
                          <TrendingUp className="w-4 h-4 text-success" />
                        ) : trend.direction === 'down' ? (
                          <TrendingDown className="w-4 h-4 text-error" />
                        ) : null}
                        <span className={`font-mono text-sm ${
                          trend.direction === 'up' ? 'text-success' : 
                          trend.direction === 'down' ? 'text-error' : 'text-muted-foreground'
                        }`}>
                          {trend.direction === 'stable' ? 'Stable' : 
                           `${trend.direction === 'up' ? '+' : '-'}${trend.change} pts (30d)`}
                        </span>
                      </div>
                    </div>

                    {/* Criteria List */}
                    <div className="flex-1 w-full">
                      <h3 className="font-serif text-lg text-navy mb-4">7-Criteria Assessment</h3>
                      <div className="space-y-3">
                        {governance?.criteria?.map((criterion, index) => (
                          <div 
                            key={index}
                            className={`flex items-center justify-between p-3 border ${
                              criterion.achieved ? 'border-success/30 bg-success/5' : 'border-navy/10'
                            }`}
                          >
                            <div className="flex items-center gap-3">
                              {criterion.achieved ? (
                                <CheckCircle2 className="w-5 h-5 text-success" />
                              ) : (
                                <Circle className="w-5 h-5 text-navy/30" />
                              )}
                              <div className={`w-8 h-8 flex items-center justify-center ${
                                criterion.achieved ? 'bg-success/20 text-success' : 'bg-navy/10 text-navy/50'
                              }`}>
                                {getCriterionIcon(criterion.name)}
                              </div>
                              <div>
                                <p className={`font-medium text-sm ${criterion.achieved ? 'text-navy' : 'text-muted-foreground'}`}>
                                  {criterion.name}
                                </p>
                                <p className="text-xs text-muted-foreground">{criterion.description}</p>
                              </div>
                            </div>
                            <span className={`font-mono text-lg ${criterion.achieved ? 'text-success' : 'text-muted-foreground'}`}>
                              {criterion.points}/{criterion.max_points}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Historical Chart */}
                <div className="card-trust">
                  <h3 className="font-serif text-lg text-navy mb-4">30-Day Trend</h3>
                  
                  {history.length === 0 ? (
                    <div className="text-center py-8">
                      <TrendingUp className="w-8 h-8 text-navy/30 mx-auto mb-2" />
                      <p className="text-sm text-muted-foreground">No historical data yet</p>
                      <p className="text-xs text-muted-foreground mt-1">Check back after a few days</p>
                    </div>
                  ) : (
                    <>
                      <div className="relative h-32 mb-4" data-testid="health-chart">
                        <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-full" preserveAspectRatio="none">
                          {/* Grid lines */}
                          <line x1="0" y1={chartHeight * 0.2} x2={chartWidth} y2={chartHeight * 0.2} stroke="#e5e7eb" strokeWidth="0.5" />
                          <line x1="0" y1={chartHeight * 0.4} x2={chartWidth} y2={chartHeight * 0.4} stroke="#e5e7eb" strokeWidth="0.5" />
                          <line x1="0" y1={chartHeight * 0.6} x2={chartWidth} y2={chartHeight * 0.6} stroke="#e5e7eb" strokeWidth="0.5" />
                          <line x1="0" y1={chartHeight * 0.8} x2={chartWidth} y2={chartHeight * 0.8} stroke="#e5e7eb" strokeWidth="0.5" />
                          
                          {/* Area fill */}
                          <polygon 
                            points={getChartArea()} 
                            fill="url(#gradient)" 
                            opacity="0.3"
                          />
                          
                          {/* Line */}
                          <polyline 
                            points={getChartPoints()} 
                            fill="none" 
                            stroke="#010079" 
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                          
                          {/* Gradient definition */}
                          <defs>
                            <linearGradient id="gradient" x1="0%" y1="0%" x2="0%" y2="100%">
                              <stop offset="0%" stopColor="#010079" stopOpacity="0.3" />
                              <stop offset="100%" stopColor="#010079" stopOpacity="0" />
                            </linearGradient>
                          </defs>
                          
                          {/* Data points */}
                          {history.map((item, index) => {
                            const x = (index / (history.length - 1 || 1)) * chartWidth;
                            const y = chartHeight - (item.score / maxScore) * chartHeight;
                            return (
                              <circle 
                                key={index}
                                cx={x} 
                                cy={y} 
                                r="3" 
                                fill="#010079"
                              />
                            );
                          })}
                        </svg>
                      </div>
                      
                      {/* Date labels */}
                      <div className="flex justify-between text-xs text-muted-foreground font-mono">
                        {history.length > 0 && (
                          <>
                            <span>{formatDate(history[0]?.date)}</span>
                            {history.length > 2 && <span>{formatDate(history[Math.floor(history.length / 2)]?.date)}</span>}
                            <span>{formatDate(history[history.length - 1]?.date)}</span>
                          </>
                        )}
                      </div>
                      
                      {/* Score labels */}
                      <div className="absolute right-2 top-8 text-[10px] text-muted-foreground font-mono flex flex-col justify-between h-32">
                        <span>100</span>
                        <span>50</span>
                        <span>0</span>
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Scoring Guide */}
              <div className="card-trust">
                <h3 className="font-serif text-xl text-navy mb-6">How Scoring Works</h3>
                
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <FileText className="w-5 h-5 text-navy" />
                      <h4 className="font-medium text-sm">Quarterly Minutes</h4>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">
                      Generate meeting minutes each quarter
                    </p>
                    <span className="badge-trust">15 points</span>
                  </div>

                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <Calendar className="w-5 h-5 text-navy" />
                      <h4 className="font-medium text-sm">Task Compliance</h4>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">
                      Complete governance tasks before due dates
                    </p>
                    <span className="badge-trust">15 points</span>
                  </div>

                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <Wallet className="w-5 h-5 text-navy" />
                      <h4 className="font-medium text-sm">Compensation</h4>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">
                      Stay within approved plan amounts
                    </p>
                    <span className="badge-trust">15 points</span>
                  </div>

                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <DollarSign className="w-5 h-5 text-navy" />
                      <h4 className="font-medium text-sm">Distributions</h4>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">
                      Log and fully document distributions
                    </p>
                    <span className="badge-trust">15 points</span>
                  </div>

                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingUp className="w-5 h-5 text-navy" />
                      <h4 className="font-medium text-sm">Annual Review</h4>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">
                      Complete annual trust review
                    </p>
                    <span className="badge-trust">10 points</span>
                  </div>

                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <ArrowUpDown className="w-5 h-5 text-navy" />
                      <h4 className="font-medium text-sm">Transaction Classification</h4>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">
                      Properly classify ≥90% of trust transactions
                    </p>
                    <span className="badge-trust">15 points</span>
                  </div>

                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <Shield className="w-5 h-5 text-navy" />
                      <h4 className="font-medium text-sm">Separation Alert Health</h4>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">
                      Resolve personal/trust separation alerts promptly
                    </p>
                    <span className="badge-trust">15 points</span>
                  </div>
                </div>

                {/* Color coding guide */}
                <div className="mt-6 pt-6 border-t border-navy/10">
                  <p className="label-trust mb-3">Score Ranges</p>
                  <div className="flex gap-6">
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 bg-success"></div>
                      <span className="text-sm">80-100: Excellent</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 bg-warning"></div>
                      <span className="text-sm">60-79: Needs Attention</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 bg-error"></div>
                      <span className="text-sm">Below 60: Critical</span>
                    </div>
                  </div>
                </div>
              </div>
              {/* Hidden Insights — Manually Restore */}
              <div className="card-trust mt-8">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="font-serif text-xl text-navy">Hidden Recommendations</h3>
                    <p className="text-sm text-muted-foreground">
                      Insights you've dismissed. Restore them to bring them back.
                    </p>
                  </div>
                </div>
                <HiddenInsightsPanel trustId={selectedTrust?.trust_id} />
              </div>
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}

// Sub-component: Hidden Insights Panel (self-contained)
function HiddenInsightsPanel({ trustId }) {
  const [dismissed, setDismissed] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (trustId) loadDismissed();
  }, [trustId]);

  const loadDismissed = async () => {
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/insights/dismissed?trust_id=${trustId}`);
      if (response.ok) {
        const data = await response.json();
        setDismissed(data.dismissed_insights || []);
      }
    } catch (error) {
      console.error('Failed to load dismissed insights:', error);
    } finally {
      setLoading(false);
    }
  };

  const restoreInsight = async (criterionName) => {
    try {
      const response = await fetchWithAuth('/insights/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trust_id: trustId, criterion_name: criterionName })
      });
      if (response.ok) {
        toast.success(`${criterionName} restored`);
        setDismissed(prev => prev.filter(d => d.criterion_name !== criterionName));
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to restore');
      }
    } catch (error) {
      console.error('Failed to restore insight:', error);
      toast.error('Failed to restore recommendation');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <RefreshCw className="w-5 h-5 animate-spin text-gold mr-2" />
        <span className="text-sm text-muted-foreground">Loading hidden recommendations...</span>
      </div>
    );
  }

  if (dismissed.length === 0) {
    return (
      <div className="p-4 bg-success/10 border border-success/20 text-center">
        <p className="text-sm text-success">
          No hidden recommendations. Everything is visible.
        </p>
      </div>
    );
  }

  const INSIGHT_ICONS = {
    'Quarterly Minutes': FileText,
    'Task Compliance': Calendar,
    'Compensation Alignment': Wallet,
    'Distribution Documentation': DollarSign,
    'Annual Review': TrendingUp
  };

  return (
    <div className="space-y-3">
      {dismissed.map((item, index) => {
        const Icon = INSIGHT_ICONS[item.criterion_name] || Shield;
        return (
          <div
            key={index}
            className="flex items-center justify-between p-4 border border-navy/10 bg-navy/5"
            data-testid={`hidden-insight-${index}`}
          >
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-navy/10 flex items-center justify-center">
                <Icon className="w-4 h-4 text-navy" />
              </div>
              <div>
                <p className="font-medium text-sm text-navy">{item.criterion_name}</p>
                <p className="text-xs text-muted-foreground">
                  Dismissed {format(parseISO(item.dismissed_at), 'MMM d, yyyy')}
                </p>
              </div>
            </div>
            <Button
              onClick={() => restoreInsight(item.criterion_name)}
              size="sm"
              variant="outline"
              className="btn-secondary"
              data-testid={`restore-insight-${index}`}
            >
              <RefreshCw className="w-3 h-3 mr-1" />
              Restore
            </Button>
          </div>
        );
      })}
    </div>
  );
}
