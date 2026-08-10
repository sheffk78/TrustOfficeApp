import { MessageSquare, RefreshCw, ChevronLeft, ChevronRight, Search, Inbox } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { formatLastActive } from './helpers';

const SENTIMENT_STYLES = {
  positive: 'bg-success/10 text-success',
  neutral: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  negative: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const STATUS_STYLES = {
  open: 'bg-warning/10 text-warning',
  pending: 'bg-blue-100 text-blue-800',
  resolved: 'bg-success/10 text-success',
};

function getSentimentClass(s) {
  return SENTIMENT_STYLES[s] || SENTIMENT_STYLES.neutral;
}

function getStatusClass(s) {
  return STATUS_STYLES[s] || 'bg-gray-100 text-gray-700';
}

function formatSource(source) {
  if (!source) return null;
  return source.replace(/-/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
}

export function ConversationsTab({
  conversations, loading, total, page, limit,
  statusFilter, sentimentFilter, search,
  onStatusFilterChange, onSentimentFilterChange, onSearchChange,
  onRefresh, onPrevPage, onNextPage,
}) {
  const start = total === 0 ? 0 : (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);

  return (
    <div className="card-trust">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="font-serif text-xl text-navy dark:text-white">Conversations</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Who's talking to TrustOffice, about what, and where they came from.
          </p>
        </div>
        <Button variant="outline" onClick={onRefresh}>
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-4 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by name or email..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-10 input-trust"
          />
        </div>
        <Select value={statusFilter} onValueChange={onStatusFilterChange}>
          <SelectTrigger className="w-40 input-trust">
            <SelectValue placeholder="All Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sentimentFilter} onValueChange={onSentimentFilterChange}>
          <SelectTrigger className="w-40 input-trust">
            <SelectValue placeholder="All Sentiment" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sentiment</SelectItem>
            <SelectItem value="positive">Positive</SelectItem>
            <SelectItem value="neutral">Neutral</SelectItem>
            <SelectItem value="negative">Negative</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Empty state */}
      {!loading && conversations.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Inbox className="w-12 h-12 text-muted-foreground mb-4" />
          <p className="text-muted-foreground font-medium">No conversations yet</p>
          <p className="text-sm text-muted-foreground mt-1">
            Support interactions will appear here as they're logged.
          </p>
        </div>
      )}

      {/* List */}
      {conversations.length > 0 && (
        <div className="space-y-3">
          {conversations.map((conv) => {
            const last = conv.last_interaction || {};
            const profile = conv.profile_summary || {};
            return (
              <div
                key={conv.contact_id}
                className="border border-navy/10 dark:border-white/10 rounded-lg p-4 hover:bg-navy/[0.02] dark:hover:bg-white/[0.02] transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-navy dark:text-white truncate">
                        {conv.name || conv.email || 'Unknown contact'}
                      </span>
                      {conv.marketing_source && (
                        <Badge variant="outline" className="text-xs">
                          {formatSource(conv.marketing_source)}
                        </Badge>
                      )}
                      {profile.current_phase && (
                        <Badge variant="outline" className="text-xs">
                          {profile.current_phase}
                        </Badge>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground mt-0.5">
                      {conv.email}
                      {conv.organization ? ` · ${conv.organization}` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge className={getStatusClass(conv.last_status)}>
                      {conv.last_status || '—'}
                    </Badge>
                    <Badge className={getSentimentClass(conv.last_sentiment)}>
                      {conv.last_sentiment || '—'}
                    </Badge>
                  </div>
                </div>

                {/* Last interaction summary */}
                {last.summary && (
                  <p className="text-sm text-muted-foreground mt-3 line-clamp-2">
                    {last.summary}
                  </p>
                )}

                {/* Topics */}
                {Array.isArray(last.topics) && last.topics.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {last.topics.slice(0, 4).map((topic) => (
                      <span
                        key={topic}
                        className="text-xs px-2 py-0.5 rounded-full bg-navy/5 dark:bg-white/10 text-navy dark:text-white"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                )}

                {/* Footer meta */}
                <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <MessageSquare className="w-3.5 h-3.5" />
                    {conv.interaction_count} interaction{conv.interaction_count !== 1 ? 's' : ''}
                  </span>
                  <span>{last.created_at ? formatLastActive(last.created_at) : ''}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {total > 0 && (
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-navy/10 dark:border-white/10">
          <span className="text-sm text-muted-foreground">
            Showing {start}–{end} of {total}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onPrevPage} disabled={page <= 1}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={onNextPage} disabled={end >= total}>
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
