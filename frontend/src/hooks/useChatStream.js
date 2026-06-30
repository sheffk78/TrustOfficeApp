import { useState, useCallback, useRef } from 'react';
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
  const abortRef = useRef(null);
  const onDoneCallbackRef = useRef(null);

  const sendMessage = useCallback(async (text, currentConversationId = null, currentMessages = [], onDone = null) => {
    if (!text.trim()) return;

    // Store the onDone callback for when the 'done' event arrives
    onDoneCallbackRef.current = onDone;

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };

    // Append user message immediately
    const updatedMessages = [...currentMessages, userMessage];
    setMessages(updatedMessages);
    setLoading(true);
    setIsStreaming(true);
    setStreamPhase('thinking');
    setError(null);

    // Create abort controller for this request
    const controller = new AbortController();
    abortRef.current = controller;

    // Create a placeholder assistant message that we'll update as tokens stream in
    const assistantMessageId = `ai-${Date.now()}`;
    const placeholderAssistant = {
      id: assistantMessageId,
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

    // Track whether we've received the 'done' event
    let doneReceived = false;
    let streamEnded = false;

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
      let newConvId = null;
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
              if (msg.id !== assistantMessageId) return msg;
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
                if (msg.id !== assistantMessageId) return msg;
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
              if (msg.id !== assistantMessageId) return msg;
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

      // Safety net: if the stream ended but we never got a 'done' event
      // (e.g., connection dropped), finalize the message anyway
      if (!doneReceived) {
        console.warn('[useChatStream] Stream ended without done event, finalizing');
        setMessages(prev => prev.map(msg => {
          if (msg.id !== assistantMessageId) return msg;
          return {
            ...msg,
            isStreaming: false,
            content: fullText || 'The connection was interrupted. Please try again.',
          };
        }));
      }

      return { conversationId: newConvId, messages: [...updatedMessages, { id: assistantMessageId, content: fullText }] };
    } catch (err) {
      if (err.name === 'AbortError') {
        // User stopped the generation — keep partial response
        setMessages(prev => prev.map(msg => {
          if (msg.id !== assistantMessageId) return msg;
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
          if (msg.id !== assistantMessageId) return msg;
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
      abortRef.current = null;
      onDoneCallbackRef.current = null;
    }
  }, [conversationId]);

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