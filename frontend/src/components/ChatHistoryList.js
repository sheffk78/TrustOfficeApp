import React from 'react';
import { MessageSquare, Trash2, Clock } from 'lucide-react';

const formatRelativeTime = (timestamp) => {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHrs = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHrs < 24) return `${diffHrs}h ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const ChatHistoryList = ({ conversations, loading, onSelect, onDelete }) => {
  if (loading) {
    return (
      <div className="space-y-2 p-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="p-3 border border-navy/5">
            <div className="skeleton h-4 w-3/4 mb-2" />
            <div className="skeleton h-3 w-1/2" />
          </div>
        ))}
      </div>
    );
  }

  if (!conversations || conversations.length === 0) {
    return (
      <div className="p-4 text-center">
        <MessageSquare className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
        <p className="font-mono text-xs text-muted-foreground">
          Your conversations will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-1 p-2">
      {conversations.map((conv) => (
        <div
          key={conv.conversation_id}
          className="group flex items-start gap-2 p-2.5 border border-transparent hover:border-navy/10 hover:bg-navy/5 cursor-pointer transition-colors"
          onClick={() => onSelect?.(conv)}
        >
          <div className="flex-1 min-w-0">
            <p className="font-mono text-xs font-medium text-foreground truncate">
              {conv.title || 'Untitled Conversation'}
            </p>
            {conv.last_message && (
              <p className="font-mono text-[11px] text-muted-foreground truncate mt-0.5">
                {conv.last_message.length > 60
                  ? conv.last_message.substring(0, 60) + '…'
                  : conv.last_message}
              </p>
            )}
            <div className="flex items-center gap-1 mt-1">
              <Clock className="w-3 h-3 text-muted-foreground/50" />
              <span className="font-mono text-[10px] text-muted-foreground/60">
                {formatRelativeTime(conv.updated_at || conv.created_at)}
              </span>
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete?.(conv.conversation_id);
            }}
            className="opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-rust transition-all flex-shrink-0"
            title="Delete conversation"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
};

export default ChatHistoryList;