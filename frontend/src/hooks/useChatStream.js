import { useState, useCallback, useRef, useEffect } from 'react';
import { fetchWithAuth, getErrorMessage } from '@/utils/api';
import { reportErrorToBackend } from '@/utils/errors';

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
    // Normalize \r\n to \n first so we only need to split on \n\n.
    const normalized = buffer.replace(/\r\n/g, '\n');
    const events = normalized.split('\n\n');
    buffer = events.pop() || ''; // Keep incomplete event in buffer

    for (const eventStr of events) {
      if (!eventStr.trim()) continue;

      let eventType = 'message';
      let dataStr = '';

      for (const line of eventStr.split('\n')) {
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

// ─── Extracted helpers (module-scope, not recreated per render) ──────

/**
 * Build an action cards array from a backend action card object.
 * Shared by stream 'done' handler, polling fallback, and loadConversation.
 */
function buildActionCards(actionCardData) {
  if (!actionCardData) return [];
  return [{
    id: `action-${Date.now()}`,
    type: actionCardData.type || '',
    data: actionCardData.data || {},
    status: actionCardData.confirmation_status || 'pending',
    requires_confirmation: actionCardData.requires_confirmation ?? true,
    warning: actionCardData.warning_summary || null,
    title: deriveTitle(actionCardData),
    summary: deriveSummary(actionCardData),
    amount: actionCardData.data?.amount || null,
    message_index: null,
  }];
}

/**
 * Build citations array from backend citation/unknown note fields.
 */
function buildCitationsFromNotes(citationNote, unknownNote) {
  const citations = [];
  if (citationNote) {
    citations.push({ source: citationNote, relevance: 'What this answer is based on' });
  }
  if (unknownNote) {
    citations.push({ source: unknownNote, relevance: 'What is uncertain' });
  }
  return citations;
}

/**
 * Finalize the streaming assistant placeholder by applying updates.
 * If content is empty, substitute a fallback message.
 */
function finalizePlaceholder(setMessages, assistantId, updates) {
  setMessages(prev => prev.map(msg => {
    if (msg.id !== assistantId) return msg;
    return { ...msg, ...updates, isStreaming: false };
  }));
}

/**
 * Read the latest messages from React state (via the functional updater trick).
 */
function readLatestMessages(setMessages) {
  return new Promise(resolve => {
    setMessages(prev => resolve(prev));
  });
}

/**
 * Attempt to recover a completed response by polling the "latest response" endpoint.
 * Returns true if a completed response was found and applied, false otherwise.
 */
async function pollForCompletedResponse({ convIdToPoll, assistantId, setMessages }) {
  if (!convIdToPoll) return false;
  try {
    const pollResp = await fetchWithAuth(
      `/ai/chat/conversations/${convIdToPoll}/latest`,
      { method: 'GET' }
    );
    if (!pollResp.ok) return false;

    const pollData = await pollResp.json();
    const isCompleteResponse =
      pollData && pollData.role === 'assistant' &&
      pollData.content && !pollData.is_streaming;
    if (!isCompleteResponse) return false;

    const pollActionCards = buildActionCards(pollData.action_card || null);
    const pollCitations = buildCitationsFromNotes(pollData.citation_note, pollData.unknown_note);

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

    console.info('[useChatStream] Recovered completed response via polling fallback');
    return true;
  } catch (pollErr) {
    console.warn('[useChatStream] Polling fallback failed:', pollErr);
    return false;
  }
}

// ─── Stream event handler factory ───────────────────────────────────
// Builds the (eventType, data) => void callback passed to parseSSEStream.
// Encapsulates the meta/status/token/done/error switch so the streaming
// function body stays flat. Returns { onEvent, getFullText, getDoneReceived }.

function createStreamEventHandler({
  assistantId,
  setMessages,
  setStreamPhase,
  setError,
  onDoneCallbackRef,
  getNewConvId,
}) {
  let fullText = '';
  let doneReceived = false;

  const onEvent = (eventType, data) => {
    switch (eventType) {
      case 'status':
        setStreamPhase(data.phase || 'thinking');
        break;

      case 'token':
        fullText += data.text;
        setStreamPhase('generating');
        setMessages(prev => prev.map(msg => {
          if (msg.id !== assistantId) return msg;
          return { ...msg, content: fullText };
        }));
        break;

      case 'done':
        doneReceived = true;
        handleDoneEvent({ data, assistantId, fullText, setMessages, onDoneCallbackRef, newConvId: getNewConvId() });
        break;

      case 'error':
        setError(data.message || 'An error occurred during streaming');
        finalizePlaceholder(setMessages, assistantId, {
          content: fullText || 'I encountered an error while generating this response. Please try again.',
        });
        break;
    }
  };

  return {
    onEvent,
    getFullText: () => fullText,
    getDoneReceived: () => doneReceived,
  };
}

function handleDoneEvent({ data, assistantId, fullText, setMessages, onDoneCallbackRef, newConvId }) {
  const actionCards = buildActionCards(data.action_card);
  const citations = buildCitationsFromNotes(data.citation_note, data.unknown_note);

  setMessages(prev => {
    const targetIndex = prev.findIndex(msg => msg.id === assistantId);
    if (targetIndex === -1) return prev;
    const msg = prev[targetIndex];
    const finalActionCards = actionCards.map(card => ({
      ...card,
      message_index: targetIndex,
    }));
    return [
      ...prev.slice(0, targetIndex),
      {
        ...msg,
        content: fullText,
        action_cards: finalActionCards,
        citations,
        caveat: data.caveat,
        isStreaming: false,
      },
      ...prev.slice(targetIndex + 1),
    ];
  });

  if (onDoneCallbackRef.current) {
    try {
      onDoneCallbackRef.current({ conversationId: newConvId, isNew: data.is_new });
    } catch (e) {
      // Ignore callback errors
    }
    onDoneCallbackRef.current = null;
  }
}

// ─── Reconnection fallback (extracted from the streaming function) ────
// Handles the "stream ended without done event" recovery path.
async function handleReconnectionFallback({
  doneReceived, fullText, newConvId, currentConversationId, conversationId,
  assistantId, setMessages, retryCountRef, lastUserMessageRef, readLatest,
  streamMessage,
}) {
  const canRetry = retryCountRef.current < 2 && lastUserMessageRef.current;
  if (doneReceived) return;

  if (!canRetry) {
    // Max retries exceeded or no last message — finalize with error text
    finalizePlaceholder(setMessages, assistantId, {
      content: fullText || 'The connection was interrupted. Please try again.',
    });
    return;
  }

  console.warn('[useChatStream] Stream ended without done event');
  const convIdToPoll = newConvId || currentConversationId || conversationId;

  const pollSuccess = await pollForCompletedResponse({ convIdToPoll, assistantId, setMessages });
  if (pollSuccess) return;

  // Response wasn't complete — retry the original message.
  retryCountRef.current += 1;
  console.info(`[useChatStream] Auto-retrying (attempt ${retryCountRef.current}/2)`);

  setMessages(prev => prev.filter(msg => msg.id !== assistantId));
  const latestMessages = await readLatest(setMessages);

  const lastMsg = lastUserMessageRef.current;
  return streamMessage({
    text: lastMsg.text,
    currentConversationId: newConvId || lastMsg.conversationId,
    currentMessages: latestMessages,
    onDone: lastMsg.onDone,
    isRetry: true,
    assistantMessageId: null,
  });
}

// ─── Error catch handler (extracted from the streaming function) ────
function handleStreamError({ err, assistantId, setMessages, setError }) {
  const isAbort = err.name === 'AbortError';
  if (isAbort) {
    setMessages(prev => prev.map(msg => {
      if (msg.id !== assistantId) return msg;
      return {
        ...msg,
        isStreaming: false,
        content: msg.content + (msg.content ? '\n\n*[Stopped]*' : '*[Stopped]*'),
      };
    }));
    return;
  }
  console.error('[useChatStream] Error:', err);
  reportErrorToBackend(err, { operation: 'chat_stream', page: window.location.pathname, severity: 'major' });
  setError(err.message || 'Failed to send message');
  setMessages(prev => prev.map(msg => {
    if (msg.id !== assistantId) return msg;
    if (!msg.content) {
      return { ...msg, content: 'I encountered an error. Please try again.', isStreaming: false };
    }
    return { ...msg, isStreaming: false };
  }));
}

// ─── Action card title/summary derivation (config-driven) ────────────
const TITLE_RULES = [
  { match: 'class_beneficiary_removal', fmt: d => `Remove Class: ${d.class_type || 'Class'}` },
  { match: 'class_beneficiary', fmt: d => `Class Beneficiary: ${d.class_type || 'Class'}` },
  { match: 'certificate', fmt: d => `Certificate Email: ${d.beneficiary_name || 'Beneficiary'}` },
  { match: 'distribution', fmt: d => `Distribution: $${(d.amount || 0).toLocaleString()} to ${d.beneficiary_name || 'beneficiary'}` },
  { match: 'asset', fmt: d => `New Asset: ${d.description || d.asset_type || 'Asset'}` },
  { match: 'minutes', fmt: d => `Minutes: ${d.minutes_type || 'Meeting'} — ${d.meeting_date || ''}` },
  { match: 'beneficiary', fmt: d => `Add Beneficiary: ${d.name || 'New Beneficiary'}` },
];

const SUMMARY_RULES = [
  { match: 'class_beneficiary_removal', fmt: d => `Remove ${d.class_type || 'class'} beneficiary designation` },
  { match: 'class_beneficiary', fmt: d => `${d.class_type || 'Class'}${d.percentage ? ` — ${d.percentage}% allocation` : ''}${d.description ? `: ${d.description}` : ''}` },
  { match: 'certificate', fmt: d => `Email certificate to ${d.beneficiary_name || 'beneficiary'}${d.email ? ` at ${d.email}` : ' (using email on file)'}` },
  { match: 'distribution', fmt: d => `${d.purpose || 'Distribution'} of $${(d.amount || 0).toLocaleString()} to ${d.beneficiary_name || 'beneficiary'} on ${d.date || 'TBD'}` },
  { match: 'asset', fmt: d => `${d.asset_type || 'Asset'}: ${d.description || ''} (Value: $${(d.value || 0).toLocaleString()})` },
  { match: 'minutes', fmt: d => `${d.minutes_type || ''} meeting on ${d.meeting_date || 'TBD'} with ${(d.participants || []).join(', ') || 'participants TBD'}` },
  { match: 'beneficiary', fmt: d => `${d.name || 'Beneficiary'}${d.allocation_pct ? ` — ${d.allocation_pct}% allocation` : ''}` },
];

function deriveTitle(actionCard) {
  if (!actionCard || !actionCard.data) return '';
  const type = actionCard.type || '';
  for (const rule of TITLE_RULES) {
    if (type.includes(rule.match)) return rule.fmt(actionCard.data);
  }
  return '';
}

function deriveSummary(actionCard) {
  if (!actionCard || !actionCard.data) return '';
  const type = actionCard.type || '';
  for (const rule of SUMMARY_RULES) {
    if (type.includes(rule.match)) return rule.fmt(actionCard.data);
  }
  return JSON.stringify(actionCard.data).slice(0, 100);
}

export const useChatStream = () => {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [conversationId, setConversationId] = useState(null);
  const [trustContext, setTrustContext] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamPhase, setStreamPhase] = useState(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [wasAutoThreaded, setWasAutoThreaded] = useState(false);
  const abortRef = useRef(null);
  const onDoneCallbackRef = useRef(null);

  // Refs for values needed in event handlers (avoids stale closures)
  const isStreamingRef = useRef(false);
  const lastUserMessageRef = useRef(null);
  const retryCountRef = useRef(0);
  const lastAssistantMessageIdRef = useRef(null);
  const sentConversationIdRef = useRef(null);

  // Keep isStreamingRef in sync with isStreaming state
  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  // ─── Screen Wake Lock during AI streaming ─────────────────────────
  useEffect(() => {
    let wakeLock = null;
    const requestWakeLock = async () => {
      if ('wakeLock' in navigator && isStreaming) {
        try {
          wakeLock = await navigator.wakeLock.request('screen');
        } catch (err) {
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

    // Reset auto-thread flag for this new send
    setWasAutoThreaded(false);
    onDoneCallbackRef.current = onDone;

    // Track the conversation ID being sent so we can detect auto-threading
    const sentConvId = currentConversationId || conversationId || null;
    sentConversationIdRef.current = sentConvId;

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };

    let assistantId = assistantMessageId || `ai-${Date.now()}`;
    let updatedMessages;

    if (isRetry) {
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

    let newConvId = null;
    const getNewConvId = () => newConvId;

    const eventHandler = createStreamEventHandler({
      assistantId,
      setMessages,
      setStreamPhase,
      setError,
      onDoneCallbackRef,
      getNewConvId,
    });

    try {
      const body = { message: text };
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

      const reader = response.body.getReader();

      // Handle 'meta' events here to capture newConvId locally (needed by
      // both the done handler and the reconnection fallback); delegate the
      // remaining event types to the extracted event handler.
      const wrappedOnEvent = (eventType, data) => {
        if (eventType === 'meta') {
          newConvId = data.conversation_id;
          if (newConvId) {
            setConversationId(newConvId);
            // Detect auto-threading: backend returned a different conversation_id
            const sentId = sentConversationIdRef.current;
            if (sentId && newConvId !== sentId) {
              setWasAutoThreaded(true);
            }
          }
          return;
        }
        eventHandler.onEvent(eventType, data);
      };

      await parseSSEStream(reader, wrappedOnEvent);

      // Safety net: if the stream ended but we never got a 'done' event,
      // the connection likely dropped. Attempt reconnection.
      await handleReconnectionFallback({
        doneReceived: eventHandler.getDoneReceived(),
        fullText: eventHandler.getFullText(),
        newConvId,
        currentConversationId,
        conversationId,
        assistantId,
        setMessages,
        retryCountRef,
        lastUserMessageRef,
        readLatest: readLatestMessages,
        streamMessage: _streamMessage,
      });

      return { conversationId: newConvId, messages: [...updatedMessages, { id: assistantId, content: '' }] };
    } catch (err) {
      handleStreamError({ err, assistantId, setMessages, setError });
      return null;
    } finally {
      setLoading(false);
      setIsStreaming(false);
      setStreamPhase(null);
      setIsReconnecting(false);
      abortRef.current = null;
      onDoneCallbackRef.current = null;
      retryCountRef.current = 0;
      lastAssistantMessageIdRef.current = null;
    }
  }, [conversationId]);

  // ─── sendMessage (public wrapper around _streamMessage) ───────────
  const sendMessage = useCallback(async (text, currentConversationId = null, currentMessages = [], onDone = null) => {
    lastUserMessageRef.current = { text, conversationId: currentConversationId, onDone };
    retryCountRef.current = 0;
    return _streamMessage({ text, currentConversationId, currentMessages, onDone, isRetry: false });
  }, [_streamMessage]);

  // ─── handleRetry (used by visibilitychange handler) ───────────────
  const handleRetry = useCallback(async () => {
    if (!lastUserMessageRef.current) return;
    if (retryCountRef.current >= 2) return;

    if (abortRef.current) {
      try { abortRef.current.abort(); } catch (e) { /* ignore */ }
      abortRef.current = null;
    }

    if (lastAssistantMessageIdRef.current) {
      setMessages(prev => prev.filter(msg => msg.id !== lastAssistantMessageIdRef.current));
    }

    retryCountRef.current += 1;
    const lastMsg = lastUserMessageRef.current;
    const latestMessages = await readLatestMessages(setMessages);

    return _streamMessage({
      text: lastMsg.text,
      currentConversationId: lastMsg.conversationId,
      currentMessages: latestMessages,
      onDone: lastMsg.onDone,
      isRetry: true,
    });
  }, [_streamMessage]);

  // ─── visibilitychange handler with auto-retry ────────────────────
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        if (isStreamingRef.current && lastUserMessageRef.current) {
          setTimeout(() => {
            if (isStreamingRef.current && lastUserMessageRef.current) {
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
    if (abortRef.current) abortRef.current.abort();
  }, []);

  const loadConversation = useCallback((conv) => {
    setConversationId(conv.conversation_id);
    const formattedMessages = (conv.messages || []).map((msg, index) => {
      const actionCards = buildActionCards(msg.action_card || null);
      return {
        id: msg.id || `msg-${index}`,
        role: msg.role,
        content: msg.content || '',
        timestamp: msg.timestamp || '',
        action_cards: actionCards.map(card => ({ ...card, message_index: index })),
        video_cards: msg.video_cards || [],
        citations: buildCitationsFromNotes(msg.citation_note, msg.unknown_note),
        caveat: msg.caveat || null,
      };
    });
    setMessages(formattedMessages);
    setTrustContext(conv.trust_context_summary || null);
    setError(null);
  }, []);

  const resetConversation = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    setConversationId(null);
    setMessages([]);
    setTrustContext(null);
    setError(null);
    setStreamPhase(null);
    setWasAutoThreaded(false);
  }, []);

  const clearError = useCallback(() => setError(null), []);

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
    clearAutoThreadFlag,
    setMessages,
  };
};