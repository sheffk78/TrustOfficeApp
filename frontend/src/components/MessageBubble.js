import React, { useState, memo } from 'react';
import { ChevronDown, ChevronUp, AlertTriangle, Copy, Check } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ActionCard from './ActionCard';
import VideoCard from './VideoCard';

const TypingCursor = () => (
  <span className="typing-cursor" aria-hidden="true" />
);

const CopyButton = ({ text }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error('Copy failed:', err);
      }
      document.body.removeChild(textarea);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="copy-btn flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-muted-foreground/40 hover:text-navy transition-colors"
      title="Copy to clipboard"
    >
      {copied ? (
        <>
          <Check className="w-3 h-3" />
          <span>Copied</span>
        </>
      ) : (
        <>
          <Copy className="w-3 h-3" />
          <span>Copy</span>
        </>
      )}
    </button>
  );
};

// Avatar for AI and user
const Avatar = ({ role }) => {
  const isAI = role === 'assistant';
  return (
    <div className={`chat-avatar ${isAI ? 'chat-avatar-ai' : 'chat-avatar-user'}`}>
      {isAI ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z" />
          <path d="M12 6v6l4 2" />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      )}
    </div>
  );
};

const MessageBubble = ({ message, onActionApprove, onActionEdit, onActionDiscard, onVideoClick }) => {
  const isUser = message.role === 'user';
  const [citationsExpanded, setCitationsExpanded] = useState(false);
  const isStreaming = message.isStreaming;

  return (
    <div className={`chat-message-row ${isUser ? 'chat-message-user' : 'chat-message-ai'}`}>
      {/* Avatar */}
      <Avatar role={message.role} />

      {/* Message bubble */}
      <div className={`chat-bubble ${isUser ? 'chat-bubble-user' : 'chat-bubble-ai'} ${isStreaming ? 'chat-bubble-streaming' : ''}`}>
        {/* Message content */}
        <div className="chat-content">
          {isUser ? (
            <div className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
              {message.content}
            </div>
          ) : (
            <>
              <div className="markdown-body text-sm leading-relaxed text-foreground">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content || ''}
                </ReactMarkdown>
                {isStreaming && <TypingCursor />}
              </div>
              {/* Show subtle "generating..." indicator when streaming and no content yet */}
              {isStreaming && !message.content && (
                <div className="flex items-center gap-1.5 py-1">
                  <span className="typing-dot" />
                  <span className="typing-dot" style={{ animationDelay: '0.15s' }} />
                  <span className="typing-dot" style={{ animationDelay: '0.3s' }} />
                </div>
              )}
            </>
          )}
        </div>

        {/* Action cards */}
        {message.action_cards?.length > 0 && !isStreaming && (
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
        {message.video_cards?.length > 0 && !isStreaming && (
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
        {message.citations?.length > 0 && !isStreaming && (
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
        {message.caveat && !isStreaming && (
          <div className="mt-2 flex items-start gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-warning flex-shrink-0 mt-0.5" />
            <p className="font-mono text-[11px] text-warning/70 leading-relaxed">{message.caveat}</p>
          </div>
        )}

        {/* Footer: timestamp + copy (only for AI, not while streaming) */}
        {!isStreaming && (
          <div className="flex items-center justify-between mt-2">
            <p className="font-mono text-[10px] text-muted-foreground/40">
              {message.timestamp
                ? new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                : ''}
            </p>
            {!isUser && message.content && <CopyButton text={message.content} />}
          </div>
        )}
      </div>
    </div>
  );
};

export default memo(MessageBubble);