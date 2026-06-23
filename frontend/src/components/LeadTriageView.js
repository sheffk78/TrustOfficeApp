import { useState, useEffect, useCallback } from 'react';
import { Target, Phone, AlertTriangle, Trophy, RefreshCw, Mail, Eye } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';
import { Badge } from '@/components/ui/badge';

function relativeTime(isoString) {
  if (!isoString) return '';
  const now = new Date();
  const date = new Date(isoString);
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays === 1) return 'Yesterday';
  return `${diffDays}d ago`;
}

function ScoreBar({ score }) {
  const color = score >= 70 ? 'bg-success' : score >= 40 ? 'bg-warning' : 'bg-rust';
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-12 h-1.5 bg-navy/10">
        <div className={`h-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-[10px] font-mono text-navy/50">{score}</span>
    </div>
  );
}

function StageBadge({ stage }) {
  const styles = {
    new: 'bg-blue-100 text-blue-800',
    engaged: 'bg-purple-100 text-purple-800',
    warm: 'bg-warning/10 text-warning',
    converted: 'bg-success/10 text-success',
    lost: 'bg-gray-100 text-gray-800',
  };
  return (
    <span className={`px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider ${styles[stage] || styles.lost}`}>
      {stage}
    </span>
  );
}

export default function LeadTriageView({ onViewLead, onFollowUp }) {
  const [triage, setTriage] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchTriage = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth('/admin/notifications/triage');
      if (res.ok) {
        const data = await res.json();
        setTriage(data);
      }
    } catch (e) {
      console.error('Failed to fetch triage:', e);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchTriage();
  }, [fetchTriage]);

  if (loading && !triage) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="w-8 h-8 animate-spin text-navy" />
      </div>
    );
  }

  if (!triage) {
    return <p className="text-center text-muted-foreground py-8">Failed to load triage data</p>;
  }

  const renderLeadCard = (lead) => (
    <div
      key={lead.lead_id}
      className="flex items-center justify-between p-2.5 border-b border-navy/5 last:border-b-0 hover:bg-navy/5 cursor-pointer transition-colors"
      onClick={() => onViewLead && onViewLead(lead.lead_id)}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-navy truncate">{lead.name || 'Unknown'}</span>
          <StageBadge stage={lead.stage} />
        </div>
        <p className="text-xs text-navy/60 truncate mt-0.5">{lead.email}</p>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[10px] text-navy/40 font-mono">{lead.source || '—'}</span>
          <ScoreBar score={lead.score || 0} />
        </div>
      </div>
      <div className="flex items-center gap-1 ml-2 flex-shrink-0">
        <button
          onClick={(e) => { e.stopPropagation(); onFollowUp && onFollowUp(lead); }}
          className="p-1.5 text-navy/40 hover:text-gold transition-colors"
          title="Send follow-up email"
        >
          <Mail className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onViewLead && onViewLead(lead.lead_id); }}
          className="p-1.5 text-navy/40 hover:text-navy transition-colors"
          title="View details"
        >
          <Eye className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );

  return (
    <div>
      {/* Summary bar */}
      <div className="flex items-center gap-4 mb-4 text-sm text-navy/60">
        <span className="flex items-center gap-1">
          <span className="font-medium text-navy">{triage.new_today_count || 0}</span> new today
        </span>
        <span className="flex items-center gap-1">
          <span className="font-medium text-navy">{triage.booked_calls_count || 0}</span> booked calls
        </span>
        <span className="flex items-center gap-1">
          <span className="font-medium text-navy">{triage.needs_followup_count || 0}</span> need follow-up
        </span>
        <span className="flex items-center gap-1">
          <span className="font-medium text-navy">{triage.total_leads || 0}</span> total leads
        </span>
        <button onClick={fetchTriage} className="ml-auto p-1 text-navy/40 hover:text-navy transition-colors">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* 2x2 Grid */}
      <div className="grid grid-cols-2 gap-4">
        {/* New Today */}
        <div className="card-trust">
          <div className="flex items-center gap-2 mb-3">
            <Target className="w-4 h-4 text-navy" />
            <span className="label-trust">New Today</span>
            <span className="ml-auto text-xs text-navy/40 font-mono">{triage.new_today_count}</span>
          </div>
          {triage.new_today && triage.new_today.length > 0 ? (
            <div className="divide-y divide-navy/5">
              {triage.new_today.map(renderLeadCard)}
            </div>
          ) : (
            <p className="text-xs text-navy/40 py-4 text-center">No new leads today</p>
          )}
        </div>

        {/* Booked Calls */}
        <div className="card-trust">
          <div className="flex items-center gap-2 mb-3">
            <Phone className="w-4 h-4 text-gold" />
            <span className="label-trust">Booked Calls</span>
            <span className="ml-auto text-xs text-navy/40 font-mono">{triage.booked_calls_count}</span>
          </div>
          {triage.booked_calls && triage.booked_calls.length > 0 ? (
            <div className="divide-y divide-navy/5">
              {triage.booked_calls.map(renderLeadCard)}
            </div>
          ) : (
            <p className="text-xs text-navy/40 py-4 text-center">No upcoming calls</p>
          )}
        </div>

        {/* Needs Follow-Up */}
        <div className="card-trust">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-rust" />
            <span className="label-trust">Needs Follow-Up</span>
            <span className="ml-auto text-xs text-navy/40 font-mono">{triage.needs_followup_count}</span>
          </div>
          {triage.needs_followup && triage.needs_followup.length > 0 ? (
            <div className="divide-y divide-navy/5">
              {triage.needs_followup.map(renderLeadCard)}
            </div>
          ) : (
            <p className="text-xs text-navy/40 py-4 text-center">All caught up!</p>
          )}
        </div>

        {/* Recent Wins */}
        <div className="card-trust">
          <div className="flex items-center gap-2 mb-3">
            <Trophy className="w-4 h-4 text-success" />
            <span className="label-trust">Recent Wins</span>
            <span className="ml-auto text-xs text-navy/40 font-mono">{triage.recent_conversions?.length || 0}</span>
          </div>
          {triage.recent_conversions && triage.recent_conversions.length > 0 ? (
            <div className="divide-y divide-navy/5">
              {triage.recent_conversions.map(renderLeadCard)}
            </div>
          ) : (
            <p className="text-xs text-navy/40 py-4 text-center">No recent conversions</p>
          )}
        </div>
      </div>
    </div>
  );
}
