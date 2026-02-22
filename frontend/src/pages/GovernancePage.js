import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { 
  Shield,
  Calendar,
  FileText,
  Clock,
  TrendingUp,
  TrendingDown,
  AlertCircle
} from 'lucide-react';
import { format, parseISO, differenceInDays } from 'date-fns';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function GovernancePage() {
  const { selectedTrust } = useAuth();
  const [governance, setGovernance] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (selectedTrust) {
      loadGovernanceData();
    }
  }, [selectedTrust]);

  const loadGovernanceData = async () => {
    if (!selectedTrust) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${API}/governance/${selectedTrust.trust_id}`, {
        credentials: 'include'
      });
      if (response.ok) {
        setGovernance(await response.json());
      }
    } catch (error) {
      console.error('Failed to load governance data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getScoreColor = (score) => {
    if (score >= 70) return 'text-success';
    if (score >= 40) return 'text-warning';
    return 'text-error';
  };

  const getScoreBgColor = (score) => {
    if (score >= 70) return 'bg-success/10 border-success/30';
    if (score >= 40) return 'bg-warning/10 border-warning/30';
    return 'bg-error/10 border-error/30';
  };

  const getStatusLabel = (status) => {
    switch (status) {
      case 'good': return 'Healthy';
      case 'warning': return 'Needs Attention';
      case 'critical': return 'Critical';
      default: return status;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Never';
    try {
      return format(parseISO(dateString), 'MMM d, yyyy');
    } catch {
      return dateString;
    }
  };

  const getDaysSince = (dateString) => {
    if (!dateString) return null;
    try {
      return differenceInDays(new Date(), parseISO(dateString));
    } catch {
      return null;
    }
  };

  const getRecommendations = () => {
    if (!governance) return [];
    
    const recs = [];
    
    if (governance.meeting_recency_score < 50) {
      recs.push({
        type: 'warning',
        title: 'Schedule a Review Meeting',
        description: 'Your last recorded meeting was over 60 days ago. Regular meetings help maintain governance health.'
      });
    }
    
    if (governance.decisions_count_score < 30) {
      recs.push({
        type: 'info',
        title: 'Document Your Decisions',
        description: 'Recording decisions helps create an audit trail and demonstrates proper trust management.'
      });
    }
    
    if (governance.pending_reviews_score < 75) {
      recs.push({
        type: 'warning',
        title: 'Review Pending Items',
        description: `You have ${governance.pending_reviews} items pending review. Timely reviews show active trust management.`
      });
    }
    
    if (governance.overall_score >= 70) {
      recs.push({
        type: 'success',
        title: 'Great Governance',
        description: 'Your trust governance is in good standing. Keep up the excellent record-keeping!'
      });
    }
    
    return recs;
  };

  return (
    <div className="main-layout" data-testid="governance-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header">
            <h1 className="page-title">Governance Health</h1>
            <p className="page-subtitle">
              {selectedTrust?.name || 'Select a trust'}
            </p>
          </div>

          {loading ? (
            <div className="card-grid">
              {[1, 2, 3].map((i) => (
                <div key={i} className="card-trust">
                  <div className="skeleton h-6 w-32 mb-4"></div>
                  <div className="skeleton h-20 w-full"></div>
                </div>
              ))}
            </div>
          ) : (
            <>
              {/* Main Score Card */}
              <div className="card-trust corner-mark mb-8">
                <div className="flex flex-col lg:flex-row items-center gap-8">
                  {/* Score Circle */}
                  <div className="text-center">
                    <div className={`score-circle ${getScoreBgColor(governance?.overall_score || 0)}`}>
                      <span className={`score-indicator ${getScoreColor(governance?.overall_score || 0)}`}>
                        {governance?.overall_score || 0}
                      </span>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
                        Overall Score
                      </span>
                    </div>
                    <div className="mt-4">
                      <span className={`badge-trust ${
                        governance?.status === 'good' ? 'badge-success' :
                        governance?.status === 'warning' ? 'badge-warning' : 'badge-error'
                      }`}>
                        {getStatusLabel(governance?.status)}
                      </span>
                    </div>
                  </div>

                  {/* Score Breakdown */}
                  <div className="flex-1 w-full lg:w-auto">
                    <h3 className="font-serif text-xl text-navy mb-6">Score Breakdown</h3>
                    
                    <div className="space-y-6">
                      {/* Meeting Recency */}
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Calendar className="w-4 h-4 text-navy" />
                            <span className="text-sm font-medium">Meeting Recency</span>
                          </div>
                          <span className={`font-mono text-sm font-bold ${getScoreColor(governance?.meeting_recency_score || 0)}`}>
                            {governance?.meeting_recency_score || 0}/100
                          </span>
                        </div>
                        <div className="h-3 bg-navy/10">
                          <div 
                            className={`h-full ${
                              (governance?.meeting_recency_score || 0) >= 70 ? 'bg-success' :
                              (governance?.meeting_recency_score || 0) >= 40 ? 'bg-warning' : 'bg-error'
                            }`}
                            style={{ width: `${governance?.meeting_recency_score || 0}%` }}
                          ></div>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          Last meeting: {formatDate(governance?.last_meeting_date)}
                          {governance?.last_meeting_date && (
                            <span className="ml-2 font-mono">
                              ({getDaysSince(governance?.last_meeting_date)} days ago)
                            </span>
                          )}
                        </p>
                      </div>

                      {/* Decisions Count */}
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-gold" />
                            <span className="text-sm font-medium">Decisions Documented (90 days)</span>
                          </div>
                          <span className={`font-mono text-sm font-bold ${getScoreColor(governance?.decisions_count_score || 0)}`}>
                            {governance?.decisions_count_score || 0}/100
                          </span>
                        </div>
                        <div className="h-3 bg-navy/10">
                          <div 
                            className={`h-full ${
                              (governance?.decisions_count_score || 0) >= 70 ? 'bg-success' :
                              (governance?.decisions_count_score || 0) >= 40 ? 'bg-warning' : 'bg-error'
                            }`}
                            style={{ width: `${governance?.decisions_count_score || 0}%` }}
                          ></div>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          Total decisions: <span className="font-mono">{governance?.total_decisions || 0}</span>
                        </p>
                      </div>

                      {/* Pending Reviews */}
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Clock className="w-4 h-4 text-muted-foreground" />
                            <span className="text-sm font-medium">Pending Review Items</span>
                          </div>
                          <span className={`font-mono text-sm font-bold ${getScoreColor(governance?.pending_reviews_score || 0)}`}>
                            {governance?.pending_reviews_score || 0}/100
                          </span>
                        </div>
                        <div className="h-3 bg-navy/10">
                          <div 
                            className={`h-full ${
                              (governance?.pending_reviews_score || 0) >= 70 ? 'bg-success' :
                              (governance?.pending_reviews_score || 0) >= 40 ? 'bg-warning' : 'bg-error'
                            }`}
                            style={{ width: `${governance?.pending_reviews_score || 0}%` }}
                          ></div>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          Pending: <span className="font-mono">{governance?.pending_reviews || 0}</span> items
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Recommendations */}
              <div className="card-trust">
                <h3 className="font-serif text-xl text-navy mb-6">Recommendations</h3>
                
                <div className="space-y-4">
                  {getRecommendations().map((rec, index) => (
                    <div 
                      key={index}
                      className={`p-4 border flex items-start gap-4 ${
                        rec.type === 'success' ? 'bg-success/5 border-success/20' :
                        rec.type === 'warning' ? 'bg-warning/5 border-warning/20' :
                        rec.type === 'info' ? 'bg-info/5 border-info/20' :
                        'bg-error/5 border-error/20'
                      }`}
                    >
                      <div className={`w-8 h-8 flex items-center justify-center flex-shrink-0 ${
                        rec.type === 'success' ? 'bg-success/20' :
                        rec.type === 'warning' ? 'bg-warning/20' :
                        rec.type === 'info' ? 'bg-info/20' :
                        'bg-error/20'
                      }`}>
                        {rec.type === 'success' ? (
                          <TrendingUp className={`w-4 h-4 text-success`} />
                        ) : rec.type === 'warning' ? (
                          <AlertCircle className={`w-4 h-4 text-warning`} />
                        ) : rec.type === 'info' ? (
                          <FileText className={`w-4 h-4 text-info`} />
                        ) : (
                          <TrendingDown className={`w-4 h-4 text-error`} />
                        )}
                      </div>
                      <div>
                        <h4 className="font-medium text-navy">{rec.title}</h4>
                        <p className="text-sm text-muted-foreground mt-1">{rec.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Scoring Guide */}
              <div className="card-trust mt-8">
                <h3 className="font-serif text-xl text-navy mb-6">How Scoring Works</h3>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <Calendar className="w-5 h-5 text-navy" />
                      <h4 className="font-medium">Meeting Recency (40%)</h4>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Based on days since your last recorded meeting. Recent meetings score higher.
                    </p>
                    <ul className="mt-3 space-y-1 text-xs font-mono text-muted-foreground">
                      <li>0-30 days: 100 points</li>
                      <li>31-60 days: 75 points</li>
                      <li>61-90 days: 50 points</li>
                      <li>91+ days: 25-0 points</li>
                    </ul>
                  </div>

                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <FileText className="w-5 h-5 text-gold" />
                      <h4 className="font-medium">Decisions (35%)</h4>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Based on documented decisions in the last 90 days. More documentation scores higher.
                    </p>
                    <ul className="mt-3 space-y-1 text-xs font-mono text-muted-foreground">
                      <li>10+ decisions: 100 points</li>
                      <li>5-9 decisions: 50-90 points</li>
                      <li>1-4 decisions: 10-40 points</li>
                      <li>0 decisions: 0 points</li>
                    </ul>
                  </div>

                  <div className="p-4 border border-navy/10">
                    <div className="flex items-center gap-2 mb-2">
                      <Clock className="w-5 h-5 text-muted-foreground" />
                      <h4 className="font-medium">Pending Reviews (25%)</h4>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Based on unreviewed distributions and expenses. Fewer pending items score higher.
                    </p>
                    <ul className="mt-3 space-y-1 text-xs font-mono text-muted-foreground">
                      <li>0 pending: 100 points</li>
                      <li>1-2 pending: 75 points</li>
                      <li>3-5 pending: 50 points</li>
                      <li>6+ pending: 25 points</li>
                    </ul>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
