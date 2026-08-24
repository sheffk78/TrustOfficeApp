import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Paperclip, Loader2, AlertCircle, X, Square, ArrowDown } from 'lucide-react';
import MessageBubble from './MessageBubble';
import FileUploadCard from './FileUploadCard';

const QUICK_CHIPS = [
  { label: 'Check Deadlines', message: 'What deadlines are coming up for my trust?' },
  { label: 'Trust Health', message: 'How healthy is my trust right now?' },
  { label: "What's Next", message: 'What should I do next for my trust?' },
  { label: 'Log Minutes', message: 'Help me log minutes for a recent meeting' },
  { label: 'Contribute Asset', message: 'I want to contribute an asset to the trust' },
  { label: 'Record Payment', message: 'Record a compensation payment to a trustee' },
  { label: 'Log Investment', message: "I need to record a new investment for the trust" },
  { label: 'Money Summary', message: 'Give me a summary of all money activity for my trust' },
];

const ChatPanel = ({
  messages = [],
  loading,
  error,
  isStreaming,
  streamPhase,
  onSendMessage,
  onStopStreaming,
  onClearError,
  onNewChat,
  onActionApprove,
  onActionEdit,
  onActionDiscard,
  onVideoClick,
  loadingConversation,
  trustId,
  onFileUploaded,
}) => {
  const [input, setInput] = useState('');
  const [showUploadCard, setShowUploadCard] = useState(false);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const textareaRef = useRef(null);
  const prevMessageCountRef = useRef(0);
  const prevContentLengthRef = useRef(0);
  const isUserScrolledUpRef = useRef(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  // Track whether user has scrolled up (so we don't auto-scroll while they're reading history)
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    const scrolledUp = distanceFromBottom > 150;
    isUserScrolledUpRef.current = scrolledUp;
    setShowScrollBtn(scrolledUp && messages.length > 2);
  }, [messages.length]);

  // Smooth auto-scroll to bottom on new messages or streaming tokens
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const messageCount = messages.length;
    const lastMsg = messages[messages.length - 1];
    const contentLength = lastMsg?.content?.length || 0;
    const hasNewMessage = messageCount > prevMessageCountRef.current;
    const hasNewContent = contentLength > prevContentLengthRef.current;

    // Auto-scroll if:
    // 1. New message arrived (user or AI), OR
    // 2. Streaming content is growing AND user hasn't scrolled up
    if (hasNewMessage || (hasNewContent && !isUserScrolledUpRef.current)) {
      requestAnimationFrame(() => {
        const targetScroll = container.scrollHeight;
        const currentScroll = container.scrollTop;
        const distance = targetScroll - currentScroll;

        // For small distances (streaming tokens), use smooth scroll
        // For large distances (new message), jump directly
        if (distance > 0 && distance < 300) {
          container.scrollTo({
            top: targetScroll,
            behavior: 'smooth',
          });
        } else if (distance > 0) {
          container.scrollTop = targetScroll;
        }
      });
    }

    prevMessageCountRef.current = messageCount;
    prevContentLengthRef.current = contentLength;
  }, [messages]);

  // Reset scroll tracking when conversation changes
  useEffect(() => {
    isUserScrolledUpRef.current = false;
    setShowScrollBtn(false);
    prevMessageCountRef.current = 0;
    prevContentLengthRef.current = 0;
    // Scroll to top when loading a conversation
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = 0;
    }
  }, [loadingConversation]);

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

  const scrollToBottom = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({
      top: container.scrollHeight,
      behavior: 'smooth',
    });
    isUserScrolledUpRef.current = false;
    setShowScrollBtn(false);
  }, []);

  // Focus textarea on mount and after loading completes
  useEffect(() => {
    if (textareaRef.current && !loading) {
      textareaRef.current.focus();
    }
  }, [loading]);

  // Scroll to bottom when upload card is shown, so it's visible
  useEffect(() => {
    if (showUploadCard) {
      const container = messagesContainerRef.current;
      if (container) {
        requestAnimationFrame(() => {
          container.scrollTo({
            top: container.scrollHeight,
            behavior: 'smooth',
          });
        });
      }
    }
  }, [showUploadCard]);

  const hasUserMessages = messages.some(m => m.role === 'user');
  const showEmptyState = !hasUserMessages && !loading && !loadingConversation;

  // Determine the loading indicator text
  const loadingText = streamPhase === 'thinking' ? 'Thinking...' : 'Generating...';

  return (
    <div className="chat-panel flex flex-col h-full">
      {/* Error banner */}
      {error && (
        <div className="chat-error-banner">
          <AlertCircle className="w-4 h-4 text-rust flex-shrink-0" />
          <p className="flex-1 text-xs text-rust">{error}</p>
          <button
            onClick={onClearError}
            className="text-rust hover:text-rust/70 transition-colors"
            aria-label="Dismiss error"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Messages area — scrollable, constrained */}
      <div
        className="chat-messages"
        ref={messagesContainerRef}
        onScroll={handleScroll}
      >
        <div className="max-w-3xl mx-auto px-1">
          {loadingConversation ? (
            <div className="flex justify-center py-12">
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                <span className="text-xs text-muted-foreground">Loading conversation...</span>
              </div>
            </div>
          ) : showEmptyState ? (
            /* Empty state — welcome line + quick chips (replaces old greeting bubble) */
            <div className="flex flex-col items-center justify-center py-16 px-4">
              <h2 className="font-serif text-2xl text-navy dark:text-white text-center mb-2">
                Trust Assistant
              </h2>
              <p className="font-mono text-xs text-muted-foreground text-center max-w-md mb-8 leading-relaxed">
                Ask about deadlines, minutes, distributions, investments, or your trust's health.
              </p>
              <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                {QUICK_CHIPS.map((chip) => (
                  <button
                    key={chip.label}
                    onClick={() => handleChipClick(chip.message)}
                    className="text-[10px] uppercase tracking-wider px-3 py-1.5 border border-navy/10 bg-navy/5 text-navy hover:bg-gold/10 hover:border-gold/30 hover:text-navy/70 transition-colors dark:border-white/10 dark:bg-white/5 dark:text-white/80 dark:hover:bg-gold/10 dark:hover:border-gold/30"
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onActionApprove={onActionApprove}
                  onActionEdit={onActionEdit}
                  onActionDiscard={onActionDiscard}
                  onVideoClick={onVideoClick}
                />
              ))}

              {/* File upload card — shown when user clicks paperclip */}
              {showUploadCard && trustId && (
                <FileUploadCard
                  trustId={trustId}
                  onUploadComplete={(result) => {
                    setShowUploadCard(false);
                    if (onFileUploaded) onFileUploaded(result);
                  }}
                  onCancel={() => setShowUploadCard(false)}
                />
              )}

              {/* Loading indicator — shown when streaming but no assistant message yet */}
              {loading && !messages.some(m => m.isStreaming) && (
                <div className="chat-message-row chat-message-ai">
                  <div className="chat-avatar chat-avatar-ai">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z" />
                      <path d="M12 6v6l4 2" />
                    </svg>
                  </div>
                  <div className="chat-bubble chat-bubble-ai chat-bubble-streaming">
                    <div className="flex items-center gap-1.5 py-1">
                      <span className="typing-dot" />
                      <span className="typing-dot" style={{ animationDelay: '0.15s' }} />
                      <span className="typing-dot" style={{ animationDelay: '0.3s' }} />
                      <span className="text-[11px] text-muted-foreground ml-1">{loadingText}</span>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Scroll-to-bottom button — appears when user scrolls up during conversation */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="chat-scroll-btn"
          title="Scroll to latest"
          aria-label="Scroll to latest message"
        >
          <ArrowDown className="w-4 h-4" />
        </button>
      )}

      {/* Input bar — always visible */}
      <div className="chat-input-bar">
        <div className="chat-input-wrapper max-w-3xl mx-auto w-full flex items-end gap-2">
          {/* Paperclip — opens file upload card */}
          <button
            onClick={() => setShowUploadCard(!showUploadCard)}
            className={`p-2 transition-colors flex-shrink-0 mb-1 ${showUploadCard ? 'text-gold bg-gold/10' : 'text-muted-foreground hover:text-navy hover:bg-navy/5'}`}
            title={trustId ? "Upload a document to the vault" : "Select a trust first"}
            aria-label={trustId ? "Upload a document to the vault" : "Select a trust first to enable file upload"}
            disabled={loading || !trustId}
          >
            <Paperclip className="w-5 h-5" />
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your trust…"
            disabled={loading}
            rows={1}
            className="input-trust flex-1 placeholder:text-muted-foreground/50 disabled:opacity-50 resize-none overflow-y-auto min-h-[48px] max-h-[240px] transition-[height] duration-100"
            style={{ height: 'auto' }}
          />

          {/* Send / Stop button */}
          {isStreaming ? (
            <button
              onClick={onStopStreaming}
              className="chat-stop-btn flex-shrink-0 mb-1"
              title="Stop generating"
              aria-label="Stop generating response"
            >
              <Square className="w-4 h-4" fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() || loading}
              className="btn-primary p-2 flex-shrink-0 mb-1"
              title="Send message"
              aria-label="Send message"
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;