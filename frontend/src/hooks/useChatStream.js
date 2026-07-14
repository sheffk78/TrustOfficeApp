import { useState, useCallback, useRef, useEffect } from 'react';
import { fetchWithAuth, getErrorMessage } from '@/utils/api';

/**
 * Parse SSE events from a ReadableStream reader.
 * Handles \r\n and \n line endings, multi-line data fields, and event types.
 * This is a standalone function, not recreated per render.
 */
async function parseSSEStream(reader, onEvent) {
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Split on double newline (SSE event delimiter).
    // Handle both \n\n and \r\n\r\n since HTTP responses may use either.
    // Normalize \r\n to \n first so we only need to split on \n\n.
    const normalized = buffer.replace(/\r\n/g, '\n');
    const events = normalized.split('\n\n');
    buffer = events.pop() || ''; // Keep incomplete event in buffer

    for (const eventStr of events) {
      if (!eventStr.trim()) continue;

      let eventType = 'message';
      let dataStr = '';

      for (const line of eventStr.split('\n')) {
        // Handle lines that may have trailing \r
        const cleanLine = line.replace(/\r$/, '');
        if (cleanLine.startsWith('event: ')) {
          eventType = cleanLine.slice(7).trim();
        } else if (cleanLine.startsWith('data: ')) {
          dataStr += cleanLine.slice(6);
        }
      }

      if (dataStr) {
        try {
          const data = JSON.parse(dataStr);
          onEvent(eventType, data);
        } catch (e) {
          console.warn('[useChatStream] Failed to parse SSE data:', dataStr, e);
        }
      }
    }
  }
}

export const useChatStream = () => {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [conversationId, setConversationId] = useState(null);
  const [trustContext, setTrustContext] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamPhase, setStreamPhase] = useState(null); // 'thinking' | 'generating' | null
  const [isReconnecting, setIsReconnecting] = useState(false);
  const abortRef = useRef(null);
  const onDoneCallbackRef = useRef(null);

  // Refs for values needed in event handlers (avoids stale closures)
  const isStreamingRef = useRef(false);
  const lastUserMessageRef = useRef(null); // { text, conversationId, messages, onDone }
  const retryCountRef = useRef(0);
  const lastAssistantMessageIdRef = useRef(null);

  // Keep isStreamingRef in sync with isStreaming state
  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  // ─── Screen Wake Lock during AI streaming ─────────────────────────
  // Prevents mobile screens from sleeping during long AI responses.
  // Requires HTTPS (secure context). Failures are non-fatal.
  useEffect(() => {
    let wakeLock = null;

    const requestWakeLock = async () => {
      if ('wakeLock' in navigator && isStreaming) {
        try {
          wakeLock = await navigator.wakeLock.request('screen');
        } catch (err) {
          // Wake Lock not available or denied — non-fatal
          console.warn('[useChatStream] Wake Lock request failed:', err);
        }
      }
    };

    requestWakeLock();

    return () => {
      if (wakeLock) {
        wakeLock.release().catch(() => {});
        wakeLock = null;
      }
    };
  }, [isStreaming]);

  // ─── Core stream function (shared by sendMessage and retry) ─────────
  const _streamMessage = useCallback(async ({
    text,
    currentConversationId = null,
    currentMessages = [],
    onDone = null,
    isRetry = false,
    assistantMessageId = null,
  }) => {
    if (!text.trim()) return null;

    onDoneCallbackRef.current = onDone;

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };

    let updatedMessages;
    let assistantId = assistantMessageId || `ai-${Date.now()}`;

    if (isRetry) {
      // Retry: remove the interrupted assistant placeholder and the last user message,
      // then re-append them so the UI shows a fresh attempt.
      updatedMessages = currentMessages.filter(
        msg => msg.id !== assistantId && msg.id !== userMessage.id
      );
      updatedMessages = [...updatedMessages, userMessage];
      setIsReconnecting(true);
    } else {
      updatedMessages = [...currentMessages, userMessage];
    }

    setMessages(updatedMessages);
    setLoading(true);
    setIsStreaming(true);
    setStreamPhase('thinking');
    setError(null);

    const controller = new AbortController();
    abortRef.current = controller;

    // Create a placeholder assistant message that we'll update as tokens stream in
    const placeholderAssistant = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      action_cards: [],
      video_cards: [],
      citations: [],
      caveat: null,
      isStreaming: true,
    };

    setMessages(prev => [...prev, placeholderAssistant]);
    lastAssistantMessageIdRef.current = assistantId;

    // Track whether we've received the 'done' event
    let doneReceived = false;
    let streamEnded = false;
    let newConvId = null;

    try {
      const body = {
        message: text,
      };
      if (currentConversationId || conversationId) {
        body.conversation_id = currentConversationId || conversationId;
      }

      const response = await fetchWithAuth('/ai/chat/stream', {
        method: 'POST',
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errMsg = await getErrorMessage(response);
        throw new Error(errMsg);
      }

      // Read the SSE stream
      const reader = response.body.getReader();
      let fullText = '';
      let actionCardData = null;
      let citationNote = null;
      let unknownNote = null;
      let caveatText = null;

      await parseSSEStream(reader, (eventType, data) => {
        switch (eventType) {
          case 'meta':
            newConvId = data.conversation_id;
            if (newConvId) {
              setConversationId(newConvId);
            }
            break;

          case 'status':
            // Backend tells us what phase it's in (thinking, generating, etc.)
            setStreamPhase(data.phase || 'thinking');
            break;

          case 'token':
            fullText += data.text;
            setStreamPhase('generating');
            // Update the assistant message content incrementally
            setMessages(prev => prev.map(msg => {
              if (msg.id !== assistantId) return msg;
              return { ...msg, content: fullText };
            }));
            break;

          case 'done':
            doneReceived = true;
            actionCardData = data.action_card;
            citationNote = data.citation_note;
            unknownNote = data.unknown_note;
            caveatText = data.caveat;

            // Finalize the assistant message with metadata
            const actionCards = actionCardData ? [{
              id: `action-${Date.now()}`,
              type: actionCardData.type || '',
              data: actionCardData.data || {},
              status: actionCardData.confirmation_status || 'pending',
              requires_confirmation: actionCardData.requires_confirmation ?? true,
              warning: actionCardData.warning_summary || null,
              title: _deriveTitle(actionCardData),
              summary: _deriveSummary(actionCardData),
              amount: actionCardData.data?.amount || null,
              message_index: null,
            }] : [];

            const citations = _buildCitations(citationNote, unknownNote);

            setMessages(prev => {
              const updated = prev.map(msg => {
                if (msg.id !== assistantId) return msg;
                const finalActionCards = actionCards.map(card => ({
                  ...card,
                  message_index: prev.indexOf(msg),
                }));
                return {
                  ...msg,
                  content: fullText,
                  action_cards: finalActionCards,
                  citations,
                  caveat: caveatText,
                  isStreaming: false,
                };
              });
              return updated;
            });

            // Call the onDone callback if provided (e.g., to refresh conversation list)
            if (onDoneCallbackRef.current) {
              try {
                onDoneCallbackRef.current({ conversationId: newConvId, isNew: data.is_new });
              } catch (e) {
                // Ignore callback errors
              }
              onDoneCallbackRef.current = null;
            }
            break;

          case 'error':
            setError(data.message || 'An error occurred during streaming');
            // Finalize the placeholder
            setMessages(prev => prev.map(msg => {
              if (msg.id !== assistantId) return msg;
              if (!fullText) {
                return {
                  ...msg,
                  content: 'I encountered an error while generating this response. Please try again.',
                  isStreaming: false,
                };
              }
              return { ...msg, isStreaming: false };
            }));
            break;
        }
      });

      streamEnded = true;

      // Safety net: if the stream ended but we never got a 'done' event,
      // the connection likely dropped. Attempt reconnection.
      if (!doneReceived) {
        console.warn('[useChatStream] Stream ended without done event');

        // Try polling for a completed response first, then retry if needed.
        // Only attempt reconnection if we haven't exceeded max retries.
        if (retryCountRef.current < 2 && lastUserMessageRef.current) {
          const convIdToPoll = newConvId || currentConversationId || conversationId;

          // First, try polling the "latest response" endpoint to see if the
          // backend already finished generating while we were disconnected.
          let pollSuccess = false;
          if (convIdToPoll) {
            try {
              const pollResp = await fetchWithAuth(
                `/ai/chat/conversations/${convIdToPoll}/latest`,
                { method: 'GET' }
              );
              if (pollResp.ok) {
                const pollData = await pollResp.json();
                // Check if the latest assistant response is complete
                if (pollData && pollData.role === 'assistant' && pollData.content && !pollData.is_streaming) {
                  // The response completed while we were disconnected — display it.
                  const pollActionCard = pollData.action_card || null;
                  const pollActionCards = pollActionCard ? [{
                    id: `action-${Date.now()}`,
                    type: pollActionCard.type || '',
                    data: pollActionCard.data || {},
                    status: pollActionCard.confirmation_status || 'pending',
                    requires_confirmation: pollActionCard.requires_confirmation ?? true,
                    warning: pollActionCard.warning_summary || null,
                    title: _deriveTitle(pollActionCard),
                    summary: _deriveSummary(pollActionCard),
                    amount: pollActionCard.data?.amount || null,
                    message_index: null,
                  }] : [];
                  const pollCitations = _buildCitations(pollData.citation_note, pollData.unknown_note);

                  setMessages(prev => prev.map(msg => {
                    if (msg.id !== assistantId) return msg;
                    return {
                      ...msg,
                      content: pollData.content,
                      action_cards: pollActionCards,
                      citations: pollCitations,
                      caveat: pollData.caveat || null,
                      isStreaming: false,
                    };
                  }));

                  pollSuccess = true;
                  console.info('[useChatStream] Recovered completed response via polling fallback');
                }
              }
            } catch (pollErr) {
              console.warn('[useChatStream] Polling fallback failed:', pollErr);
            }
          }

          if (!pollSuccess) {
            // Response wasn't complete — retry the original message.
            retryCountRef.current += 1;
            console.info(`[useChatStream] Auto-retrying (attempt ${retryCountRef.current}/2)`);

            // Remove the interrupted assistant placeholder
            setMessages(prev => prev.filter(msg => msg.id !== assistantId));

            // Read the latest message list from state for the retry
            const latestMessages = await new Promise(resolve => {
              setMessages(prev => resolve(prev));
            });

            const lastMsg = lastUserMessageRef.current;
            return _streamMessage({
              text: lastMsg.text,
              currentConversationId: newConvId || lastMsg.conversationId,
              currentMessages: latestMessages,
              onDone: lastMsg.onDone,
              isRetry: true,
              assistantMessageId: null, // new placeholder for the retry
            });
          }
        } else {
          // Max retries exceeded or no last message — finalize with error text
          setMessages(prev => prev.map(msg => {
            if (msg.id !== assistantId) return msg;
            return {
              ...msg,
              isStreaming: false,
              content: fullText || 'The connection was interrupted. Please try again.',
            };
          }));
        }
      }

      return { conversationId: newConvId, messages: [...updatedMessages, { id: assistantId, content: '' }] };
    } catch (err) {
      if (err.name === 'AbortError') {
        // User stopped the generation — keep partial response
        setMessages(prev => prev.map(msg => {
          if (msg.id !== assistantId) return msg;
          return {
            ...msg,
            isStreaming: false,
            content: msg.content + (msg.content ? '\n\n*[Stopped]*' : '*[Stopped]*'),
          };
        }));
      } else {
        console.error('[useChatStream] Error:', err);
        setError(err.message || 'Failed to send message');
        // Clean up placeholder
        setMessages(prev => prev.map(msg => {
          if (msg.id !== assistantId) return msg;
          if (!msg.content) {
            return {
              ...msg,
              content: 'I encountered an error. Please try again.',
              isStreaming: false,
            };
          }
          return { ...msg, isStreaming: false };
        }));
      }
      return null;
    } finally {
      setLoading(false);
      setIsStreaming(false);
      setStreamPhase(null);
      setIsReconnecting(false);
      abortRef.current = null;
      onDoneCallbackRef.current = null;
      // Reset retry counter when we exit the streaming flow (success, abort, or error)
      retryCountRef.current = 0;
      lastAssistantMessageIdRef.current = null;
    }
  }, [conversationId]);

  // ─── sendMessage (public wrapper around _streamMessage) ───────────
  // Stores the last user message so retry/visibility handlers can re-send it.
  const sendMessage = useCallback(async (text, currentConversationId = null, currentMessages = [], onDone = null) => {
    // Store for potential retry on connection drop
    lastUserMessageRef.current = {
      text,
      conversationId: currentConversationId,
      onDone,
    };
    retryCountRef.current = 0; // fresh request — reset retry counter

    return _streamMessage({
      text,
      currentConversationId,
      currentMessages,
      onDone,
      isRetry: false,
    });
  }, [_streamMessage]);

  // ─── handleRetry (used by visibilitychange handler) ───────────────
  // Aborts any in-flight request, removes the interrupted assistant placeholder,
  // and re-sends the last user message.
  const handleRetry = useCallback(async () => {
    if (!lastUserMessageRef.current) return;
    if (retryCountRef.current >= 2) return;

    // Abort any lingering fetch
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch (e) { /* ignore */ }
      abortRef.current = null;
    }

    // Remove the interrupted assistant placeholder if it exists
    if (lastAssistantMessageIdRef.current) {
      setMessages(prev => prev.filter(msg => msg.id !== lastAssistantMessageIdRef.current));
    }

    retryCountRef.current += 1;
    const lastMsg = lastUserMessageRef.current;

    // Read the latest messages from state
    const latestMessages = await new Promise(resolve => {
      setMessages(prev => resolve(prev));
    });

    return _streamMessage({
      text: lastMsg.text,
      currentConversationId: lastMsg.conversationId,
      currentMessages: latestMessages,
      onDone: lastMsg.onDone,
      isRetry: true,
    });
  }, [_streamMessage]);

  // ─── visibilitychange handler with auto-retry ────────────────────
  // When the page becomes visible again while a stream was in progress
  // but appears to have dropped, automatically retry the last user message.
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Check if we were streaming and the connection may have dropped
        if (isStreamingRef.current && lastUserMessageRef.current) {
          // The stream likely dropped while backgrounded.
          // Wait a moment for any pending reads to resolve, then check state.
          setTimeout(() => {
            if (isStreamingRef.current && lastUserMessageRef.current) {
              // Still streaming but connection dropped — retry
              console.info('[useChatStream] Tab became visible mid-stream, attempting auto-retry');
              handleRetry();
            }
          }, 1000);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [handleRetry]);

  const stopStreaming = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
  }, []);

  const loadConversation = useCallback((conv) => {
    setConversationId(conv.conversation_id);
    // Transform backend conversation messages to frontend format
    const formattedMessages = (conv.messages || []).map((msg, index) => {
      const actionCard = msg.action_card || null;
      const actionCards = actionCard ? [{
        id: `action-${index}`,
        type: actionCard.type || '',
        data: actionCard.data || {},
        status: actionCard.confirmation_status || 'pending',
        requires_confirmation: actionCard.requires_confirmation ?? true,
        warning: actionCard.warning_summary || null,
        title: _deriveTitle(actionCard),
        summary: _deriveSummary(actionCard),
        amount: actionCard.data?.amount || null,
        message_index: index,
      }] : [];

      return {
        id: msg.id || `msg-${index}`,
        role: msg.role,
        content: msg.content || '',
        timestamp: msg.timestamp || '',
        action_cards: actionCards,
        video_cards: msg.video_cards || [],
        citations: _buildCitations(msg.citation_note, msg.unknown_note),
        caveat: msg.caveat || null,
      };
    });
    setMessages(formattedMessages);
    setTrustContext(conv.trust_context_summary || null);
    setError(null);
  }, []);

  const resetConversation = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    setConversationId(null);
    setMessages([]);
    setTrustContext(null);
    setError(null);
    setStreamPhase(null);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    messages,
    loading,
    error,
    conversationId,
    trustContext,
    isStreaming,
    streamPhase,
    isReconnecting,
    sendMessage,
    stopStreaming,
    loadConversation,
    resetConversation,
    clearError,
    setMessages,
  };
};

// Helper: derive a short title from action card data
function _deriveTitle(actionCard) {
  if (!actionCard || !actionCard.data) return '';
  const d = actionCard.data;
  const type = actionCard.type || '';
  if (type.includes('class_beneficiary_removal')) return `Remove Class: ${d.class_type || 'Class'}`;
  if (type.includes('class_beneficiary')) return `Class Beneficiary: ${d.class_type || 'Class'}`;
  if (type.includes('certificate')) return `Certificate Email: ${d.beneficiary_name || 'Beneficiary'}`;
  if (type.includes('distribution')) return `Distribution: $${(d.amount || 0).toLocaleString()} to ${d.beneficiary_name || 'beneficiary'}`;
  if (type.includes('asset')) return `New Asset: ${d.description || d.asset_type || 'Asset'}`;
  if (type.includes('minutes')) return `Minutes: ${d.minutes_type || 'Meeting'} — ${d.meeting_date || ''}`;
  if (type.includes('beneficiary')) return `Add Beneficiary: ${d.name || 'New Beneficiary'}`;
  return '';
}

// Helper: derive a summary from action card data
function _deriveSummary(actionCard) {
  if (!actionCard || !actionCard.data) return '';
  const d = actionCard.data;
  const type = actionCard.type || '';
  if (type.includes('class_beneficiary_removal')) return `Remove ${d.class_type || 'class'} beneficiary designation`;
  if (type.includes('class_beneficiary')) return `${d.class_type || 'Class'}${d.percentage ? ` — ${d.percentage}% allocation` : ''}${d.description ? `: ${d.description}` : ''}`;
  if (type.includes('certificate')) return `Email certificate to ${d.beneficiary_name || 'beneficiary'}${d.email ? ` at ${d.email}` : ' (using email on file)'}`;
  if (type.includes('distribution')) return `${d.purpose || 'Distribution'} of $${(d.amount || 0).toLocaleString()} to ${d.beneficiary_name || 'beneficiary'} on ${d.date || 'TBD'}`;
  if (type.includes('asset')) return `${d.asset_type || 'Asset'}: ${d.description || ''} (Value: $${(d.value || 0).toLocaleString()})`;
  if (type.includes('minutes')) return `${d.minutes_type || ''} meeting on ${d.meeting_date || 'TBD'} with ${(d.participants || []).join(', ') || 'participants TBD'}`;
  if (type.includes('beneficiary')) return `${d.name || 'Beneficiary'}${d.allocation_pct ? ` — ${d.allocation_pct}% allocation` : ''}`;
  return JSON.stringify(d).slice(0, 100);
}

// Helper: build citations array from backend fields
function _buildCitations(citationNote, unknownNote) {
  const citations = [];
  if (citationNote) {
    citations.push({ source: citationNote, relevance: 'What this answer is based on' });
  }
  if (unknownNote) {
    citations.push({ source: unknownNote, relevance: 'What is uncertain' });
  }
  return citations.length > 0 ? citations : [];
}