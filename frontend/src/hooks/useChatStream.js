import { useState, useCallback, useRef } from 'react';
import { fetchWithAuth, getErrorMessage } from '@/utils/api';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';
const API = `${BACKEND_URL}/api`;

export const useChatStream = () => {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [conversationId, setConversationId] = useState(null);
  const [trustContext, setTrustContext] = useState(null);
  const abortRef = useRef(null);

  const sendMessage = useCallback(async (text, currentConversationId = null, currentMessages = []) => {
    if (!text.trim()) return;

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
    setError(null);

    try {
      const body = {
        message: text,
      };
      if (currentConversationId || conversationId) {
        body.conversation_id = currentConversationId || conversationId;
      }

      const response = await fetchWithAuth('/ai/chat', {
        method: 'POST',
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errMsg = await getErrorMessage(response);
        throw new Error(errMsg);
      }

      const data = await response.json();

      // Update conversation id if new
      if (data.conversation_id && !conversationId) {
        setConversationId(data.conversation_id);
      }

      // Update trust context if returned
      if (data.trust_context_summary) {
        setTrustContext(data.trust_context_summary);
      }

      // Add AI response
      const aiMessage = {
        id: data.message_id || `ai-${Date.now()}`,
        role: 'assistant',
        content: data.response || data.message || '',
        timestamp: new Date().toISOString(),
        action_cards: data.action_cards || [],
        video_cards: data.video_cards || [],
        citations: data.citations || [],
        caveat: data.caveat || null,
      };

      setMessages(prev => [...prev, aiMessage]);
      return { conversationId: data.conversation_id || conversationId, messages: [...updatedMessages, aiMessage] };
    } catch (err) {
      console.error('[useChatStream] Error:', err);
      setError(err.message || 'Failed to send message');
      return null;
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  const loadConversation = useCallback((conv) => {
    setConversationId(conv.conversation_id);
    setMessages(conv.messages || []);
    setTrustContext(conv.trust_context_summary || null);
    setError(null);
  }, []);

  const resetConversation = useCallback(() => {
    setConversationId(null);
    setMessages([]);
    setTrustContext(null);
    setError(null);
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
    sendMessage,
    loadConversation,
    resetConversation,
    clearError,
    setMessages,
  };
};