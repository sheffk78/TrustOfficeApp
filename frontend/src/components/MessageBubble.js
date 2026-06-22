import React, { useState } from 'react';
import { ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react';
import ActionCard from './ActionCard';
import VideoCard from './VideoCard';

const MessageBubble = ({ message, onActionApprove, onActionEdit, onActionDiscard, onVideoClick }) => {
  const isUser = message.role === 'user';
  const [citationsExpanded, setCitationsExpanded] = useState(false);

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[80%] ${
          isUser
            ? 'message-bubble-user border border-navy/10'
            : 'message-bubble-ai border border-navy/5'
        }`}
      >
        {/* Message content */}
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
          {message.content}
        </div>

        {/* Action cards */}
        {message.action_cards?.length > 0 && (
          <div className="mt-3 space-y-2">
            {message.action_cards.map((card, i) => (
              <ActionCard
                key={card.id || `action-${i}`}
                card={card}
                onApprove={onActionApprove}
                onEdit={onActionEdit}
                onDiscard={onActionDiscard}
                disabled={card.status === 'approved' || card.status === 'discarded'}
              />
            ))}
          </div>
        )}

        {/* Video cards */}
        {message.video_cards?.length > 0 && (
          <div className="mt-3 space-y-2">
            {message.video_cards.map((card, i) => (
              <VideoCard
                key={card.id || `video-${i}`}
                card={card}
                onClick={onVideoClick}
              />
            ))}
          </div>
        )}

        {/* Citations */}
        {message.citations?.length > 0 && (
          <div className="mt-3 border-t border-navy/5 pt-2">
            <button
              onClick={() => setCitationsExpanded(!citationsExpanded)}
              className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground hover:text-navy transition-colors"
            >
              {citationsExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              What I'm basing this on...
            </button>
            {citationsExpanded && (
              <div className="mt-1 space-y-1">
                {message.citations.map((citation, i) => (
                  <p key={i} className="font-mono text-[11px] text-muted-foreground leading-relaxed">
                    • {citation.source || citation}{citation.relevance ? ` — ${citation.relevance}` : ''}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Caveat */}
        {message.caveat && (
          <div className="mt-2 flex items-start gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-warning flex-shrink-0 mt-0.5" />
            <p className="font-mono text-[11px] text-warning/70 leading-relaxed">{message.caveat}</p>
          </div>
        )}

        {/* Timestamp */}
        <p className="mt-2 font-mono text-[10px] text-muted-foreground/50">
          {message.timestamp
            ? new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : ''}
        </p>
      </div>
    </div>
  );
};

export default MessageBubble;