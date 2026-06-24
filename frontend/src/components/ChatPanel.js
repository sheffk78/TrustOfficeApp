import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Paperclip, Loader2, AlertCircle, X } from 'lucide-react';
import MessageBubble from './MessageBubble';

const QUICK_CHIPS = [
  { label: 'Check Deadlines', message: 'What deadlines are coming up for my trust?' },
  { label: 'Trust Health', message: 'How healthy is my trust right now?' },
  { label: "What's Next", message: 'What should I do next for my trust?' },
  { label: 'Log Minutes', message: 'Help me log minutes for a recent meeting' },
];

const GREETING_MESSAGE = {
  id: 'greeting',
  role: 'assistant',
  content: "Hi! I'm your Trust Assistant. Ask me about your trust, deadlines, or what to do next.",
  timestamp: new Date().toISOString(),
  action_cards: [],
  video_cards: [],
  citations: [],
  caveat: null,
};

const ChatPanel = ({
  messages,
  loading,
  error,
  onSendMessage,
  onClearError,
  onActionApprove,
  onActionEdit,
  onActionDiscard,
  onVideoClick,
  loadingConversation,
}) => {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const textareaRef = useRef(null);
  const prevMessageCountRef = useRef(0);

  // Auto-scroll to bottom on new messages — uses container scrollTop, not scrollIntoView
  // This prevents the page-level scroll jump that was disrupting conversation visibility
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const messageCount = messages.length;
    // Only auto-scroll when new messages arrive (not on every render)
    if (messageCount > prevMessageCountRef.current) {
      // Use requestAnimationFrame to ensure DOM has updated
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    }
    prevMessageCountRef.current = messageCount;
  }, [messages]);

  // Also scroll on loading state changes (e.g. when loading finishes and response appears)
  useEffect(() => {
    if (!loading && messages.length > 0) {
      const container = messagesContainerRef.current;
      if (container) {
        requestAnimationFrame(() => {
          container.scrollTop = container.scrollHeight;
        });
      }
    }
  }, [loading]);

  // Auto-resize textarea as user types
  const autoResizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 240) + 'px';
  }, []);

  const handleSend = () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    // Reset textarea height after send
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    onSendMessage(text);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (e) => {
    setInput(e.target.value);
    autoResizeTextarea();
  };

  const handleChipClick = (message) => {
    if (loading) return;
    onSendMessage(message);
  };

  const displayMessages = [GREETING_MESSAGE, ...messages];

  return (
    <div className="chat-panel flex flex-col h-full">
      {/* Error banner */}
      {error && (
        <div className="bg-rust/10 border-b border-rust/20 px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-4 h-4 text-rust flex-shrink-0" />
          <p className="flex-1 text-xs text-rust">{error}</p>
          <button
            onClick={onClearError}
            className="text-rust hover:text-rust/70 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Messages area — scrollable, constrained */}
      <div className="chat-messages flex-1 overflow-y-auto px-6 py-4" ref={messagesContainerRef}>
        <div className="max-w-3xl mx-auto">
          {loadingConversation ? (
            <div className="flex justify-center py-12">
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                <span className="text-xs text-muted-foreground">Loading conversation...</span>
              </div>
            </div>
          ) : (
            <>
              {displayMessages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onActionApprove={onActionApprove}
                  onActionEdit={onActionEdit}
                  onActionDiscard={onActionDiscard}
                  onVideoClick={onVideoClick}
                />
              ))}

              {/* Loading indicator */}
              {loading && (
                <div className="flex justify-start mb-4">
                  <div className="message-bubble-ai border border-navy/5 flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">Thinking...</span>
                  </div>
                </div>
              )}
            </>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Quick-action chips */}
      <div className="px-6 pb-2 pt-1">
        <div className="max-w-3xl mx-auto flex flex-wrap gap-2">
          {QUICK_CHIPS.map((chip) => (
            <button
              key={chip.label}
              onClick={() => handleChipClick(chip.message)}
              disabled={loading}
              className="text-[10px] uppercase tracking-wider px-3 py-1.5 border border-navy/10 bg-navy/5 text-navy hover:bg-gold/10 hover:border-gold/30 hover:text-gold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      {/* Input bar — always visible */}
      <div className="chat-input-bar border-t border-navy/10 bg-background">
        <div className="w-full flex items-end gap-3">
          <button
            className="p-2 text-muted-foreground hover:text-navy hover:bg-navy/5 transition-colors flex-shrink-0 mb-1"
            title="Attach file"
          >
            <Paperclip className="w-5 h-5" />
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your trust..."
            disabled={loading}
            rows={1}
            className="input-trust flex-1 placeholder:text-muted-foreground/50 disabled:opacity-50 resize-none overflow-y-hidden py-3 leading-6 min-h-[48px] max-h-[240px]"
            style={{ height: 'auto' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="btn-primary p-2 flex-shrink-0 mb-1"
            title="Send message"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;
