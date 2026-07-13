import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import SnapshotColumn from '@/components/SnapshotColumn';
import ChatPanel from '@/components/ChatPanel';
import ActionEditModal from '@/components/ActionEditModal';
import { useChatStream } from '@/hooks/useChatStream';
import { useChatHistory } from '@/hooks/useChatHistory';
import PageHelpButton from '@/components/PageHelpButton';
import { toast } from 'sonner';

const COLLAPSED_KEY = 'trust_assistant_snapshot_collapsed';

const TrustAssistantPage = () => {
  const { selectedTrust } = useAuth();
  const [searchParams] = useSearchParams();
  const sentPrompts = useRef(new Set());

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
    isStreaming,
    streamPhase,
    sendMessage,
    stopStreaming,
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

  // Edit modal state
  const [editingCard, setEditingCard] = useState(null);

  // Conversation switching loading state
  const [loadingConversation, setLoadingConversation] = useState(false);

  // Load conversations on mount
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Auto-send ?prompt= query parameter — fires even if arriving on an open conversation,
  // as long as this exact prompt hasn't been sent yet in this page session.
  useEffect(() => {
    const prompt = searchParams.get('prompt');
    if (prompt && !sentPrompts.current.has(prompt) && !loading) {
      sentPrompts.current.add(prompt);
      sendMessage(prompt, conversationId, messages, () => {
        fetchConversations();
      });
    }
  }, [searchParams, messages, loading, sendMessage, conversationId, fetchConversations]);

  // Handle sending a message through the chat
  const handleSendMessage = useCallback(async (text) => {
    await sendMessage(text, conversationId, messages, () => {
      // Refresh conversation list after streaming completes
      fetchConversations();
    });
  }, [sendMessage, conversationId, messages, fetchConversations]);

  // Handle selecting a conversation from history
  const handleConversationSelect = useCallback(async (conv) => {
    setLoadingConversation(true);
    try {
      const fullConv = await getConversation(conv.conversation_id || conv.id);
      loadConversation(fullConv);
    } catch (err) {
      console.error('[TrustAssistant] Failed to load conversation:', err);
    } finally {
      setLoadingConversation(false);
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
      toast.error('Failed to approve action: ' + (err.message || 'Please try again'));
    }
  }, [confirmAction, conversationId, setMessages]);

  // Handle action edit — opens the edit modal
  const handleActionEdit = useCallback((card) => {
    setEditingCard(card);
  }, []);

  // Handle save from edit modal — calls confirmAction with action='edit' and editedData
  const handleActionEditSave = useCallback(async (card, editedData) => {
    if (!conversationId || card.message_index == null) {
      console.warn('[TrustAssistant] Cannot edit: missing conversationId or message_index');
      setEditingCard(null);
      return;
    }
    try {
      await confirmAction(conversationId, card.message_index, 'edit', editedData);
      // Update local state to reflect the edited data
      setMessages(prev => prev.map((msg, idx) => {
        if (idx !== card.message_index) return msg;
        return {
          ...msg,
          action_cards: (msg.action_cards || []).map(ac =>
            ac.id === card.id
              ? {
                  ...ac,
                  data: { ...(ac.data || {}), ...editedData },
                  status: 'pending',
                }
              : ac
          ),
        };
      }));
    } catch (err) {
      console.error('[TrustAssistant] Action edit error:', err);
      toast.error('Failed to edit action: ' + (err.message || 'Please try again'));
    } finally {
      setEditingCard(null);
    }
  }, [confirmAction, conversationId, setMessages]);

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
      toast.error('Failed to discard action: ' + (err.message || 'Please try again'));
    }
  }, [confirmAction, conversationId, setMessages]);

  // Video card click handler placeholder
  const handleVideoClick = useCallback((card) => {
    toast.info('Video playback coming soon');
  }, []);

  // Start a new chat — resets conversation state
  const handleNewChat = useCallback(() => {
    resetConversation();
    // Refocus the textarea
    const textarea = document.querySelector('.input-trust');
    if (textarea) textarea.focus();
  }, [resetConversation]);

  // Handle file uploaded to vault from chat
  const handleFileUploaded = useCallback((result) => {
    // Add a system message to the chat confirming the upload
    const categoryLabel = result.category
      ? result.category.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
      : 'Documents';
    const confirmationMessage = {
      id: `upload-${Date.now()}`,
      role: 'assistant',
      content: `**Document uploaded to vault.**\n\n**${result.title}** has been saved to ${categoryLabel}. You can view and manage it in the [Vault](/vault).\n\nIs there anything you'd like me to help you with regarding this document?`,
      timestamp: new Date().toISOString(),
      action_cards: [],
      video_cards: [],
      citations: [],
      caveat: null,
    };
    setMessages(prev => [...prev, confirmationMessage]);
  }, [setMessages]);

  return (
    <div className="main-layout" data-testid="trust-assistant-page">
      <Sidebar />
      <main className="main-content dot-grid flex flex-col">
        <div className="page-container flex flex-col flex-1 min-h-0">
          {/* Page header */}
          <div className="page-header flex items-start justify-between">
            <div>
              <h1 className="page-title">Trust Assistant</h1>
              <p className="page-subtitle">
                Ask questions, draft minutes, manage distributions, and get trust administration guidance — powered by AI
              </p>
            </div>
            <PageHelpButton
              items={[
                { text: 'Ask questions about trust administration in plain language' },
                { text: 'Draft minutes, manage distributions, and execute trust actions' },
                { text: 'Get guidance on fiduciary duties, deadlines, and best practices' },
              ]}
              taPrompt="What can I ask you to help me with?"
            />
          </div>
          <div className="trust-assistant-layout">
            {/* Snapshot column */}
            <SnapshotColumn
            collapsed={snapshotCollapsed}
            onToggle={handleToggleSnapshot}
            conversations={conversations}
            conversationsLoading={conversationsLoading}
            onConversationSelect={handleConversationSelect}
            onConversationDelete={handleConversationDelete}
            onSendSuggestion={handleSendMessage}
          />

          {/* Chat panel */}
          <div className="flex-1 flex flex-col min-h-0">
            <ChatPanel
              messages={messages}
              loading={loading}
              error={error}
              isStreaming={isStreaming}
              streamPhase={streamPhase}
              onSendMessage={handleSendMessage}
              onStopStreaming={stopStreaming}
              onClearError={clearError}
              onNewChat={handleNewChat}
              onActionApprove={handleActionApprove}
              onActionEdit={handleActionEdit}
              onActionDiscard={handleActionDiscard}
              onVideoClick={handleVideoClick}
              loadingConversation={loadingConversation}
              trustId={selectedTrust?.trust_id}
              onFileUploaded={handleFileUploaded}
            />
          </div>
        </div>
      </div>
      </main>
      <MobileBottomNav />

      {/* Edit modal overlay */}
      {editingCard && (
        <ActionEditModal
          card={editingCard}
          onSave={handleActionEditSave}
          onCancel={() => setEditingCard(null)}
        />
      )}
    </div>
  );
};

export default TrustAssistantPage;