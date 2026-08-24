import React, { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';
import {
  ChevronLeft,
  ChevronRight,
  Shield,
  Calendar,
  MessageSquare,
  Loader2,
  CheckCircle2,
  Circle,
  XCircle,
  ArrowRight,
  Plus,
} from 'lucide-react';
import ChatHistoryList from './ChatHistoryList';

// Map criterion names to actionable suggestions and chat prompts
const CRITERION_SUGGESTIONS = {
  'Quarterly Minutes': {
    label: 'Log quarterly minutes',
    prompt: 'Help me create minutes for this quarter',
  },
  'Task Compliance': {
    label: 'Review overdue tasks',
    prompt: 'What governance tasks are overdue and how do I complete them?',
  },
  'Compensation Alignment': {
    label: 'Set up compensation plan',
    prompt: 'Help me set up a compensation plan for trustee fees',
  },
  'Distribution Documentation': {
    label: 'Document distributions',
    prompt: 'Help me document a trust distribution',
  },
  'Annual Review': {
    label: 'Complete annual review',
    prompt: 'Help me complete the annual trust review',
  },
  'Asset Valuation Freshness': {
    label: 'Update asset valuations',
    prompt: 'Help me update the values of my Schedule A assets',
    action: '/schedule-a'
  },
};

const SnapshotColumn = ({ collapsed, onToggle, onConversationSelect, conversations, conversationsLoading, onConversationDelete, onSendSuggestion, conversationId, onNewChat }) => {
  const { selectedTrust } = useAuth();
  const [healthData, setHealthData] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [criteria, setCriteria] = useState([]);
  const [upcomingDeadlines, setUpcomingDeadlines] = useState([]);
  const [pendingTasks, setPendingTasks] = useState([]);

  useEffect(() => {
    if (!selectedTrust?.trust_id) return;
    const fetchHealth = async () => {
      setHealthLoading(true);
      try {
        // Fetch governance health score
        const healthResponse = await fetchWithAuth(`/governance/${selectedTrust.trust_id}`);
        if (healthResponse.ok) {
          const healthJson = await healthResponse.json();
          setHealthData(healthJson);
          setCriteria(healthJson.criteria || []);
        }

        // Fetch upcoming tax deadlines
        try {
          const deadlinesResponse = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/tax-calendar/upcoming?days=90`);
          if (deadlinesResponse.ok) {
            const deadlinesJson = await deadlinesResponse.json();
            setUpcomingDeadlines(deadlinesJson.upcoming || []);
          }
        } catch (e) {
          console.error('[SnapshotColumn] Failed to fetch deadlines:', e);
        }

        // Fetch pending governance tasks for the suggestions panel
        try {
          const tasksResponse = await fetchWithAuth(`/tasks?trust_id=${selectedTrust.trust_id}&status=pending`);
          if (tasksResponse.ok) {
            const tasksJson = await tasksResponse.json();
            setPendingTasks(Array.isArray(tasksJson) ? tasksJson : (tasksJson.tasks || []));
          }
        } catch (e) {
          console.error('[SnapshotColumn] Failed to fetch tasks:', e);
        }
      } catch (err) {
        console.error('[SnapshotColumn] Failed to fetch health:', err);
      } finally {
        setHealthLoading(false);
      }
    };
    fetchHealth();
  }, [selectedTrust?.trust_id]);

  // Brand-consistent color functions using gold/navy/rust tokens
  const scoreColor = (score) => {
    if (score >= 96) return 'text-gold';
    if (score >= 72) return 'text-gold/80';
    return 'text-rust';
  };

  const scoreBarColor = (score) => {
    if (score >= 96) return 'bg-gold';
    if (score >= 72) return 'bg-gold/60';
    return 'bg-rust';
  };

  // Check if a criterion has a suggestion (for clickable affordance)
  const getSuggestion = (criterionName) => CRITERION_SUGGESTIONS[criterionName];

  if (collapsed) {
    return (
      <div className="snapshot-column collapsed flex flex-col items-center py-4 bg-background">
        <button
          onClick={onToggle}
          className="p-2 text-muted-foreground hover:text-navy hover:bg-navy/5 transition-colors"
          title="Expand sidebar"
          aria-label="Expand snapshot sidebar"
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
    <div className="snapshot-column flex flex-col bg-background border-r border-navy/10 dark:border-white/10">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-navy/10 dark:border-white/10">
        <span className="label-trust">Overview</span>
        <button
          onClick={onToggle}
          className="p-1 text-muted-foreground hover:text-navy hover:bg-navy/5 transition-colors"
          title="Collapse sidebar"
          aria-label="Collapse snapshot sidebar"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* ── Navigation block: New Conversation + Chat History ── */}
        {onNewChat && (
          <div className="px-3 pt-3">
            <button
              onClick={onNewChat}
              className="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-xs font-mono font-medium text-navy dark:text-white hover:bg-navy/5 dark:hover:bg-white/5 active:bg-navy/10 transition-colors border border-navy/15 dark:border-white/15"
              title="Start new conversation"
              aria-label="Start new conversation"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Conversation</span>
            </button>
          </div>
        )}

        {/* Chat History — no card wrapper, just a hairline divider */}
        <div className="px-3 pt-3 pb-3 border-b border-navy/10 dark:border-white/10">
          <div className="flex items-center gap-2 mb-2 px-1">
            <MessageSquare className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="label-trust text-[10px]">Chat History</span>
          </div>
          <ChatHistoryList
            conversations={conversations}
            loading={conversationsLoading}
            onSelect={onConversationSelect}
            onDelete={onConversationDelete}
            activeConversationId={conversationId}
          />
        </div>

        {/* ── Data block: Trust Health (with merged Opportunities) + Deadlines ── */}

        {/* Trust Health Score — with clickable unmet criteria (merged Opportunities) */}
        <div className="card-trust m-3 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-muted-foreground" />
            <span className="label-trust">Defensibility Score</span>
          </div>
          {healthLoading ? (
            <div className="flex items-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Loading...</span>
            </div>
          ) : healthData ? (
            <>
              <div className="flex items-baseline gap-1 mb-2">
                <span className={`font-serif text-4xl font-bold ${scoreColor(healthData.total_score ?? 0)}`}>
                  {healthData.total_score ?? '—'}
                </span>
                <span className="text-xs text-muted-foreground">/{healthData.max_score || 115}</span>
              </div>
              {/* Score bar */}
              <div className="w-full h-2 bg-navy/10 dark:bg-white/10 mb-3">
                <div
                  className={`h-full ${scoreBarColor(healthData.total_score ?? 0)} transition-all duration-500`}
                  style={{ width: `${Math.min(100, ((healthData.total_score ?? 0) / (healthData.max_score || 115)) * 100)}%` }}
                />
              </div>
              {/* Criteria breakdown — unmet rows are now clickable (merged Opportunities) */}
              <div className="space-y-1.5">
                {criteria.map((c) => {
                  const suggestion = !c.achieved && !c.no_data ? getSuggestion(c.name) : null;
                  const isClickable = suggestion && onSendSuggestion;
                  return (
                    <button
                      key={c.name}
                      onClick={() => isClickable && onSendSuggestion(suggestion.prompt)}
                      disabled={!isClickable}
                      className={`w-full flex items-center gap-2 text-left transition-colors ${
                        isClickable
                          ? 'hover:bg-gold/5 cursor-pointer group -mx-1 px-1'
                          : 'cursor-default'
                      }`}
                      title={isClickable ? suggestion.label : undefined}
                    >
                      {c.achieved ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-gold flex-shrink-0" />
                      ) : c.no_data ? (
                        <Circle className="w-3.5 h-3.5 text-muted-foreground/40 flex-shrink-0" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 text-rust/70 flex-shrink-0" />
                      )}
                      <span className={`text-xs flex-1 truncate ${c.achieved ? 'text-foreground' : 'text-muted-foreground'} ${isClickable ? 'group-hover:text-navy dark:group-hover:text-white' : ''}`}>
                        {c.name}
                      </span>
                      {isClickable && (
                        <ArrowRight className="w-3 h-3 text-gold flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                      )}
                      <span className={`text-[10px] ${c.achieved ? 'text-gold' : 'text-muted-foreground'}`}>
                        {c.points}/{c.max_points}
                      </span>
                    </button>
                  );
                })}
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No score available</p>
          )}
        </div>

        {/* Upcoming Deadlines */}
        <div className="card-trust m-3 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Calendar className="w-4 h-4 text-muted-foreground" />
            <span className="label-trust">Upcoming Deadlines</span>
          </div>
          {upcomingDeadlines.length > 0 ? (
            <div className="space-y-1.5">
              {upcomingDeadlines.slice(0, 4).map((dl, i) => {
                const isOverdue = dl.is_overdue || (dl.days_remaining != null && dl.days_remaining < 0);
                const daysLeft = dl.days_remaining != null ? dl.days_remaining : null;
                return (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-xs text-foreground truncate">{dl.filing_type || dl.title || dl.name}</span>
                    <span className={`text-[10px] flex-shrink-0 ml-2 ${isOverdue ? 'text-rust font-bold' : daysLeft != null && daysLeft <= 14 ? 'text-gold/80' : 'text-muted-foreground'}`}>
                      {dl.due_date
                        ? new Date(dl.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                        : ''}
                      {daysLeft != null && (
                        <span className="ml-1">
                          ({isOverdue ? 'overdue' : daysLeft === 0 ? 'today' : `${daysLeft}d`})
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : pendingTasks.length > 0 ? (
            // Fallback: show pending governance tasks if no tax deadlines
            <div className="space-y-1.5">
              {pendingTasks.slice(0, 3).map((task, i) => (
                <div key={i} className="flex items-center justify-between">
                  <span className="text-xs text-foreground truncate">
                    {task.title || task.task_type || task.description || 'Task'}
                  </span>
                  {task.due_date && (
                    <span className="text-[10px] text-muted-foreground flex-shrink-0 ml-2">
                      {new Date(task.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-2 py-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-gold" />
              <p className="text-xs text-muted-foreground">No upcoming deadlines</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SnapshotColumn;