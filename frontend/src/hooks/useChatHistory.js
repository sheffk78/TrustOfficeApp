import { useState, useCallback, useEffect } from 'react';
import { fetchWithAuth, getErrorMessage } from '@/utils/api';

export const useChatHistory = () => {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchConversations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchWithAuth('/ai/chat/conversations');
      if (!response.ok) {
        const errMsg = await getErrorMessage(response);
        throw new Error(errMsg);
      }
      const data = await response.json();
      setConversations(Array.isArray(data) ? data : data.conversations || []);
    } catch (err) {
      console.error('[useChatHistory] fetchConversations error:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const getConversation = useCallback(async (id) => {
    try {
      const response = await fetchWithAuth(`/ai/chat/conversations/${id}`);
      if (!response.ok) {
        const errMsg = await getErrorMessage(response);
        throw new Error(errMsg);
      }
      return await response.json();
    } catch (err) {
      console.error('[useChatHistory] getConversation error:', err);
      throw err;
    }
  }, []);

  const deleteConversation = useCallback(async (id) => {
    try {
      const response = await fetchWithAuth(`/ai/chat/conversations/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errMsg = await getErrorMessage(response);
        throw new Error(errMsg);
      }
      setConversations(prev => prev.filter(c => c.conversation_id !== id));
      return true;
    } catch (err) {
      console.error('[useChatHistory] deleteConversation error:', err);
      throw err;
    }
  }, []);

  const confirmAction = useCallback(async (conversationId, messageIndex, action, editedData = null) => {
    try {
      const body = { action };
      if (editedData) {
        body.edited_data = editedData;
      }
      const response = await fetchWithAuth(
        `/ai/chat/actions/${conversationId}/${messageIndex}/confirm`,
        {
          method: 'POST',
          body: JSON.stringify(body),
        }
      );
      if (!response.ok) {
        const errMsg = await getErrorMessage(response);
        throw new Error(errMsg);
      }
      return await response.json();
    } catch (err) {
      console.error('[useChatHistory] confirmAction error:', err);
      throw err;
    }
  }, []);

  return {
    conversations,
    loading,
    error,
    fetchConversations,
    getConversation,
    deleteConversation,
    confirmAction,
  };
};