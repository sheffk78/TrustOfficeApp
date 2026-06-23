import { useState, useCallback, useRef } from 'react';
import { fetchWithAuth, getErrorMessage } from '@/utils/api';

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
      const newConvId = data.conversation_id || conversationId;
      if (newConvId && !conversationId) {
        setConversationId(newConvId);
      }

      // Update trust context if returned
      if (data.trust_context_summary) {
        setTrustContext(data.trust_context_summary);
      }

      // Parse the ChatResponse structure:
      // Backend returns: { message: { role, content, action_card, citation_note, unknown_note, caveat, timestamp }, conversation_id, ... }
      const msg = data.message || {};
      const actionCard = msg.action_card || null;

      // Build action_cards array (backend uses singular action_card, frontend expects array)
      const actionCards = actionCard ? [{
        id: `action-${Date.now()}`,
        type: actionCard.type || '',
        data: actionCard.data || {},
        status: actionCard.confirmation_status || 'pending',
        requires_confirmation: actionCard.requires_confirmation ?? true,
        warning: actionCard.warning_summary || null,
        // Derive display fields from action data
        title: _deriveTitle(actionCard),
        summary: _deriveSummary(actionCard),
        amount: actionCard.data?.amount || null,
        message_index: null, // will be set by the message count
      }] : [];

      // Add AI response
      const aiMessage = {
        id: data.message_id || `ai-${Date.now()}`,
        role: 'assistant',
        content: msg.content || data.response || '',
        timestamp: msg.timestamp || new Date().toISOString(),
        action_cards: actionCards,
        video_cards: data.video_cards || [],
        citations: _buildCitations(msg.citation_note, msg.unknown_note),
        caveat: msg.caveat || null,
      };

      // Set message_index on action cards (they belong to this message)
      const totalMessages = updatedMessages.length; // next index will be this
      aiMessage.action_cards.forEach(card => {
        card.message_index = totalMessages;
      });

      setMessages(prev => [...prev, aiMessage]);
      return { conversationId: newConvId, messages: [...updatedMessages, aiMessage] };
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

// Helper: derive a short title from action card data
function _deriveTitle(actionCard) {
  if (!actionCard || !actionCard.data) return '';
  const d = actionCard.data;
  const type = actionCard.type || '';
  if (type.includes('class_beneficiary_removal')) return `Remove Class: ${d.class_type || 'Class'}`;
  if (type.includes('class_beneficiary')) return `Class Beneficiary: ${d.class_type || 'Class'}`;
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