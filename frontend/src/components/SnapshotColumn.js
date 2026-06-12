import React, { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth, getErrorMessage } from '@/utils/api';
import {
  ChevronLeft,
  ChevronRight,
  Shield,
  Calendar,
  AlertCircle,
  Users,
  MessageSquare,
  Loader2,
} from 'lucide-react';
import ChatHistoryList from './ChatHistoryList';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';
const API = `${BACKEND_URL}/api`;

const SnapshotColumn = ({ collapsed, onToggle, onConversationSelect, conversations, conversationsLoading, onConversationDelete }) => {
  const { selectedTrust } = useAuth();
  const [healthData, setHealthData] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);

  useEffect(() => {
    if (!selectedTrust?.trust_id) return;
    const fetchHealth = async () => {
      setHealthLoading(true);
      try {
        const response = await fetchWithAuth(`/governance/health?trust_id=${selectedTrust.trust_id}`);
        if (response.ok) {
          const data = await response.json();
          setHealthData(data);
        }
      } catch (err) {
        console.error('[SnapshotColumn] Failed to fetch health:', err);
      } finally {
        setHealthLoading(false);
      }
    };
    fetchHealth();
  }, [selectedTrust?.trust_id]);

  const scoreColor = (score) => {
    if (score >= 80) return 'text-gold';
    if (score >= 60) return 'text-amber-500';
    return 'text-rust';
  };

  if (collapsed) {
    return (
      <div className="snapshot-column collapsed flex flex-col items-center py-4 bg-white border-r border-navy/10">
        <button
          onClick={onToggle}
          className="p-2 text-muted-foreground hover:text-navy hover:bg-navy/5 transition-colors"
          title="Expand sidebar"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
        <div className="mt-4 flex flex-col items-center gap-3">
          <Shield className="w-5 h-5 text-muted-foreground/40" />
          <MessageSquare className="w-5 h-5 text-muted-foreground/40" />
        </div>
      </div>
    );
  }

  return (
    <div className="snapshot-column flex flex-col bg-white border-r border-navy/10">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-navy/10">
        <h2 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Snapshot
        </h2>
        <button
          onClick={onToggle}
          className="p-1 text-muted-foreground hover:text-navy hover:bg-navy/5 transition-colors"
          title="Collapse sidebar"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Defensibility Score */}
        <div className="p-4 border-b border-navy/10">
          <div className="flex items-center gap-2 mb-2">
            <Shield className="w-4 h-4 text-muted-foreground" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Defensibility Score
            </span>
          </div>
          {healthLoading ? (
            <div className="flex items-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              <span className="font-mono text-xs text-muted-foreground">Loading...</span>
            </div>
          ) : healthData ? (
            <div className="flex items-baseline gap-1">
              <span className={`font-serif text-4xl font-bold ${scoreColor(healthData.score || healthData.defensibility_score || 0)}`}>
                {healthData.score || healthData.defensibility_score || '—'}
              </span>
              <span className="font-mono text-xs text-muted-foreground">/100</span>
            </div>
          ) : (
            <p className="font-mono text-xs text-muted-foreground">No score available</p>
          )}
        </div>

        {/* Upcoming Deadlines */}
        <div className="p-4 border-b border-navy/10">
          <div className="flex items-center gap-2 mb-2">
            <Calendar className="w-4 h-4 text-muted-foreground" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Upcoming Deadlines
            </span>
          </div>
          {healthData?.upcoming_deadlines?.length > 0 ? (
            <div className="space-y-1.5">
              {healthData.upcoming_deadlines.slice(0, 3).map((dl, i) => (
                <div key={i} className="flex items-center justify-between">
                  <span className="font-mono text-xs text-foreground truncate">{dl.title || dl.name}</span>
                  <span className="font-mono text-[10px] text-muted-foreground flex-shrink-0 ml-2">
                    {dl.due_date ? new Date(dl.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="font-mono text-xs text-muted-foreground">No upcoming deadlines</p>
          )}
        </div>

        {/* Pending Items */}
        <div className="p-4 border-b border-navy/10">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="w-4 h-4 text-muted-foreground" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Pending Items
            </span>
          </div>
          <span className="font-mono text-lg font-bold text-foreground">
            {healthData?.pending_items ?? healthData?.pending_count ?? '—'}
          </span>
        </div>

        {/* Active Beneficiaries */}
        <div className="p-4 border-b border-navy/10">
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-4 h-4 text-muted-foreground" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Beneficiaries
            </span>
          </div>
          <span className="font-mono text-lg font-bold text-foreground">
            {healthData?.beneficiary_count ?? healthData?.active_beneficiaries ?? '—'}
          </span>
        </div>

        {/* Chat History */}
        <div className="p-2">
          <div className="flex items-center gap-2 px-2 py-2">
            <MessageSquare className="w-4 h-4 text-muted-foreground" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Chat History
            </span>
          </div>
          <ChatHistoryList
            conversations={conversations}
            loading={conversationsLoading}
            onSelect={onConversationSelect}
            onDelete={onConversationDelete}
          />
        </div>
      </div>
    </div>
  );
};

export default SnapshotColumn;