import React, { useState, useRef, useEffect } from 'react';
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
}) => {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    onSendMessage(text);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
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
          <p className="flex-1 font-mono text-xs text-rust">{error}</p>
          <button
            onClick={onClearError}
            className="text-rust hover:text-rust/70 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Messages area */}
      <div className="chat-messages flex-1 overflow-y-auto p-6" ref={messagesContainerRef}>
        <div className="max-w-3xl mx-auto">
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
                <span className="font-mono text-xs text-muted-foreground">Thinking...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Quick-action chips */}
      <div className="quick-chips px-6 pb-2 pt-1">
        <div className="max-w-3xl mx-auto flex flex-wrap gap-2">
          {QUICK_CHIPS.map((chip) => (
            <button
              key={chip.label}
              onClick={() => handleChipClick(chip.message)}
              disabled={loading}
              className="font-mono text-[10px] uppercase tracking-wider px-3 py-1.5 border border-navy/10 bg-navy/5 text-navy hover:bg-gold/10 hover:border-gold/30 hover:text-gold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      {/* Input bar */}
      <div className="chat-input-bar border-t border-navy/10 bg-white">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <button
            className="p-2 text-muted-foreground hover:text-navy hover:bg-navy/5 transition-colors flex-shrink-0"
            title="Attach file"
          >
            <Paperclip className="w-5 h-5" />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your trust..."
            disabled={loading}
            className="flex-1 font-mono text-sm border-0 bg-transparent focus:outline-none focus:ring-0 placeholder:text-muted-foreground/50 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="p-2 bg-navy text-white hover:bg-navy/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
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