import React, { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';
import {
  ChevronLeft,
  ChevronRight,
  Shield,
  Calendar,
  AlertCircle,
  MessageSquare,
  Loader2,
  CheckCircle2,
  Circle,
  XCircle,
  Sparkles,
  ArrowRight,
  Lightbulb,
  Clock,
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

const SnapshotColumn = ({ collapsed, onToggle, onConversationSelect, conversations, conversationsLoading, onConversationDelete, onSendSuggestion }) => {
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

  const unmetCriteria = criteria.filter(c => !c.achieved && !c.no_data);
  const noDataCriteria = criteria.filter(c => c.no_data);

  if (collapsed) {
    return (
      <div className="snapshot-column collapsed flex flex-col items-center py-4 bg-background">
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
    <div className="snapshot-column flex flex-col bg-background border-r border-navy/10 dark:border-white/10">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-navy/10 dark:border-white/10">
        <span className="label-trust">Trust Health</span>
        <button
          onClick={onToggle}
          className="p-1 text-muted-foreground hover:text-navy hover:bg-navy/5 transition-colors"
          title="Collapse sidebar"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Trust Health Score with Criteria Breakdown */}
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
              {/* Criteria breakdown */}
              <div className="space-y-1.5">
                {criteria.map((c) => (
                  <div key={c.name} className="flex items-center gap-2">
                    {c.achieved ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-gold flex-shrink-0" />
                    ) : c.no_data ? (
                      <Circle className="w-3.5 h-3.5 text-muted-foreground/40 flex-shrink-0" />
                    ) : (
                      <XCircle className="w-3.5 h-3.5 text-rust/70 flex-shrink-0" />
                    )}
                    <span className={`text-xs ${c.achieved ? 'text-foreground' : 'text-muted-foreground'} flex-1 truncate`}>
                      {c.name}
                    </span>
                    <span className={`text-[10px] ${c.achieved ? 'text-gold' : 'text-muted-foreground'}`}>
                      {c.points}/{c.max_points}
                    </span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No score available</p>
          )}
        </div>

        {/* Opportunities to Improve */}
        {(unmetCriteria.length > 0 || noDataCriteria.length > 0) && (
          <div className="card-trust m-3 p-4">
            <div className="flex items-center gap-2 mb-3">
              <Lightbulb className="w-4 h-4 text-gold" />
              <span className="label-trust">Opportunities</span>
            </div>
            <div className="space-y-2">
              {[...unmetCriteria, ...noDataCriteria].slice(0, 4).map((c) => {
                const suggestion = CRITERION_SUGGESTIONS[c.name];
                return (
                  <button
                    key={c.name}
                    onClick={() => suggestion && onSendSuggestion?.(suggestion.prompt)}
                    className="w-full text-left flex items-center gap-2 px-2.5 py-2 bg-navy/5 dark:bg-white/5 hover:bg-navy/10 dark:hover:bg-white/10 transition-colors group"
                    disabled={!suggestion || !onSendSuggestion}
                  >
                    <ArrowRight className="w-3 h-3 text-gold flex-shrink-0 opacity-60 group-hover:opacity-100 transition-opacity" />
                    <span className="text-xs text-foreground group-hover:text-navy dark:group-hover:text-white transition-colors flex-1">
                      {suggestion ? suggestion.label : c.description}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

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

        {/* Smart Suggestions */}
        <div className="card-trust m-3 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-gold" />
            <span className="label-trust">Ask the Assistant</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[
              { label: 'What should I do next?', prompt: 'What are the most important things I should do for my trust right now?' },
              { label: 'Review my health score', prompt: 'Explain my trust health score and how to improve it' },
              { label: 'Upcoming deadlines', prompt: 'What deadlines and tasks are coming up for my trust?' },
              { label: 'Help with minutes', prompt: 'Help me create minutes for this quarter' },
            ].map((suggestion) => (
              <button
                key={suggestion.label}
                onClick={() => onSendSuggestion?.(suggestion.prompt)}
                className="px-2.5 py-1.5 text-xs border border-navy/20 dark:border-white/20 text-navy dark:text-white/80 hover:bg-navy/10 dark:hover:bg-white/10 transition-colors"
                disabled={!onSendSuggestion}
              >
                {suggestion.label}
              </button>
            ))}
          </div>
        </div>

        {/* Chat History */}
        <div className="card-trust m-3 p-4">
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare className="w-4 h-4 text-muted-foreground" />
            <span className="label-trust">Chat History</span>
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