import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import SnapshotColumn from '@/components/SnapshotColumn';
import ChatPanel from '@/components/ChatPanel';
import { useChatStream } from '@/hooks/useChatStream';
import { useChatHistory } from '@/hooks/useChatHistory';

const COLLAPSED_KEY = 'trust_assistant_snapshot_collapsed';

const TrustAssistantPage = () => {
  const { selectedTrust } = useAuth();

  // Snapshot column collapse state — collapsed by default on revisit
  const [snapshotCollapsed, setSnapshotCollapsed] = useState(() => {
    const stored = localStorage.getItem(COLLAPSED_KEY);
    return stored === 'true'; // collapsed by default on revisit; undefined = expanded on first visit
  });

  const handleToggleSnapshot = useCallback(() => {
    setSnapshotCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(COLLAPSED_KEY, String(next));
      return next;
    });
  }, []);

  // Chat stream
  const {
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
  } = useChatStream();

  // Chat history
  const {
    conversations,
    loading: conversationsLoading,
    fetchConversations,
    getConversation,
    deleteConversation,
    confirmAction,
  } = useChatHistory();

  // Load conversations on mount
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Handle sending a message through the chat
  const handleSendMessage = useCallback(async (text) => {
    await sendMessage(text, conversationId, messages);
  }, [sendMessage, conversationId, messages]);

  // Handle selecting a conversation from history
  const handleConversationSelect = useCallback(async (conv) => {
    try {
      const fullConv = await getConversation(conv.conversation_id || conv.id);
      loadConversation(fullConv);
    } catch (err) {
      console.error('[TrustAssistant] Failed to load conversation:', err);
    }
  }, [getConversation, loadConversation]);

  // Handle deleting a conversation
  const handleConversationDelete = useCallback(async (id) => {
    try {
      await deleteConversation(id);
      // If it's the current conversation, reset
      if (conversationId === id) {
        resetConversation();
      }
    } catch (err) {
      console.error('[TrustAssistant] Failed to delete conversation:', err);
    }
  }, [deleteConversation, conversationId, resetConversation]);

  // Handle action approve — calls confirm endpoint, then updates local message state
  const handleActionApprove = useCallback(async (card) => {
    if (!conversationId || card.message_index == null) {
      console.warn('[TrustAssistant] Cannot approve: missing conversationId or message_index');
      return;
    }
    try {
      const result = await confirmAction(conversationId, card.message_index, 'approve');
      // Update local state to reflect the approved status
      setMessages(prev => prev.map((msg, idx) => {
        if (idx !== card.message_index) return msg;
        return {
          ...msg,
          action_cards: (msg.action_cards || []).map(ac =>
            ac.id === card.id
              ? {
                  ...ac,
                  status: 'approved',
                  execution_result: result?.execution_result || null,
                }
              : ac
          ),
        };
      }));
    } catch (err) {
      console.error('[TrustAssistant] Action approve error:', err);
    }
  }, [confirmAction, conversationId, setMessages]);

  // Handle action edit — sends a follow-up message asking to edit
  const handleActionEdit = useCallback(async (card) => {
    // For now, send a follow-up message. Could be enhanced with an edit modal.
    handleSendMessage(`I'd like to edit the ${card.type || 'action'}: ${card.title || card.summary || 'item'}`);
  }, [handleSendMessage]);

  // Handle action discard — calls confirm endpoint with reject
  const handleActionDiscard = useCallback(async (card) => {
    if (!conversationId || card.message_index == null) {
      console.warn('[TrustAssistant] Cannot discard: missing conversationId or message_index');
      return;
    }
    try {
      await confirmAction(conversationId, card.message_index, 'reject');
      // Update local state to reflect the discarded status
      setMessages(prev => prev.map((msg, idx) => {
        if (idx !== card.message_index) return msg;
        return {
          ...msg,
          action_cards: (msg.action_cards || []).map(ac =>
            ac.id === card.id
              ? { ...ac, status: 'discarded' }
              : ac
          ),
        };
      }));
    } catch (err) {
      console.error('[TrustAssistant] Action discard error:', err);
    }
  }, [confirmAction, conversationId, setMessages]);

  // Video card click handler placeholder
  const handleVideoClick = useCallback((card) => {
    console.log('[TrustAssistant] Video clicked:', card);
  }, []);

  return (
    <div className="trust-assistant-layout" data-testid="trust-assistant-page">
      <Sidebar />
      <main className="main-content">
        <div className="trust-assistant-layout">
          {/* Snapshot column */}
          <SnapshotColumn
            collapsed={snapshotCollapsed}
            onToggle={handleToggleSnapshot}
            conversations={conversations}
            conversationsLoading={conversationsLoading}
            onConversationSelect={handleConversationSelect}
            onConversationDelete={handleConversationDelete}
          />

          {/* Chat panel */}
          <div className="flex-1 flex flex-col min-h-0">
            <ChatPanel
              messages={messages}
              loading={loading}
              error={error}
              onSendMessage={handleSendMessage}
              onClearError={clearError}
              onActionApprove={handleActionApprove}
              onActionEdit={handleActionEdit}
              onActionDiscard={handleActionDiscard}
              onVideoClick={handleVideoClick}
            />
          </div>
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
};

export default TrustAssistantPage;