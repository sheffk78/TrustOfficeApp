import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import {
  Card, CardContent, CardHeader, CardTitle
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { fetchWithAuth } from '@/utils/api';
import { showError } from '@/utils/errors';
import { toast } from 'sonner';
import { format, parseISO } from 'date-fns';
import {
  MessageSquare, Send, Search, Plus, User, Users, Clock,
  ChevronDown, Circle, Check
} from 'lucide-react';
import PageHelpButton from '@/components/PageHelpButton';

const POLL_INTERVAL_MS = 15000;

// ── Helpers ──────────────────────────────────────────────────────────────────

const formatTime = (dateStr) => {
  if (!dateStr) return '';
  try {
    const parsed = parseISO(dateStr);
    if (isNaN(parsed.getTime())) return dateStr;
    return format(parsed, 'MMM d, yyyy h:mm a');
  } catch {
    return dateStr;
  }
};

const formatRelativeTime = (dateStr) => {
  if (!dateStr) return '';
  try {
    const parsed = parseISO(dateStr);
    if (isNaN(parsed.getTime())) return '';
    const diff = Date.now() - parsed.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return format(parsed, 'MMM d');
  } catch {
    return '';
  }
};


// ── Main Component ───────────────────────────────────────────────────────────

export default function MessagingPage() {
  const { user } = useAuth();
  const userId = user?.user_id;

  // ── State ──
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  // New conversation modal
  const [showNewConv, setShowNewConv] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedRecipients, setSelectedRecipients] = useState([]);

  // Polling ref
  const pollTimerRef = useRef(null);

  // ── Load conversations ──
  const loadConversations = useCallback(async () => {
    if (!userId) return;
    try {
      const res = await fetchWithAuth('/messaging/conversations');
      if (!res.ok) throw new Error('Failed to load conversations');
      const data = await res.json();
      setConversations(data.conversations || []);

      // If no active conversation is set, pick the first one
      if (!activeConvId && data.conversations?.length > 0) {
        setActiveConvId(data.conversations[0].conversation_id);
      }
    } catch (e) {
      showError(toast, e, { operation: 'load_conversations', page: 'Messaging' });
    } finally {
      setLoading(false);
    }
  }, [userId, activeConvId]);

  // ── Load messages for active conversation ──
  const loadMessages = useCallback(async (convId) => {
    if (!convId) return;
    try {
      const res = await fetchWithAuth(`/messaging/conversations/${convId}/messages`);
      if (!res.ok) throw new Error('Failed to load messages');
      const data = await res.json();
      setMessages(data.messages || []);
    } catch (e) {
      showError(toast, e, { operation: 'load_messages', page: 'Messaging' });
    }
  }, []);

  // ── Send message ──
  const sendMessage = useCallback(async () => {
    if (!activeConvId || !inputText.trim() || sending) return;
    setSending(true);
    try {
      const res = await fetchWithAuth(
        `/messaging/conversations/${activeConvId}/messages`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ body: inputText.trim() }),
        },
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to send message');
      }
      setInputText('');
      // Reload messages to pick up the new one
      await loadMessages(activeConvId);
      // Refresh conversation list for updated timestamp / unread counts
      await loadConversations();
    } catch (e) {
      showError(toast, e, { operation: 'send_message', page: 'Messaging' });
    } finally {
      setSending(false);
    }
  }, [activeConvId, inputText, sending, loadMessages, loadConversations]);

  // ── Mark conversation read ──
  const markRead = useCallback(
    async (convId) => {
      try {
        await fetchWithAuth(`/messaging/conversations/${convId}/read`, {
          method: 'PATCH',
        });
        // Update local unread count to 0
        setConversations((prev) =>
          prev.map((c) =>
            c.conversation_id === convId ? { ...c, unread_count: 0 } : c,
          ),
        );
      } catch (e) {
        // non-fatal, will retry on next poll
      }
    },
    [],
  );

  // ── Select conversation ──
  const selectConversation = useCallback(
    (conv) => {
      setActiveConvId(conv.conversation_id);
      setMessages([]);
      loadMessages(conv.conversation_id);
      if (conv.unread_count > 0) {
        markRead(conv.conversation_id);
      }
    },
    [loadMessages, markRead],
  );

  // ── Search users for new conversation ──
  const searchUsers = useCallback(async (q) => {
    setSearchQuery(q);
    if (!q || q.length < 2) {
      setSearchResults([]);
      return;
    }
    try {
      const res = await fetchWithAuth(`/users?name_search=${encodeURIComponent(q)}`);
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.users || data || []);
      }
    } catch (e) {
      showError(toast, e, { operation: 'search_users', page: 'Messaging' });
    }
  }, []);

  // ── Create conversation ──
  const createConversation = useCallback(async () => {
    if (selectedRecipients.length === 0) return;
    try {
      const res = await fetchWithAuth('/messaging/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ participants: selectedRecipients }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to create conversation');
      }
      const data = await res.json();
      toast.success('Conversation created');
      setShowNewConv(false);
      setSelectedRecipients([]);
      setSearchQuery('');
      setSearchResults([]);
      // Refresh and select new conversation
      await loadConversations();
      if (data.conversation_id) {
        setActiveConvId(data.conversation_id);
        setMessages([]);
        loadMessages(data.conversation_id);
      }
    } catch (e) {
      showError(toast, e, { operation: 'create_conversation', page: 'Messaging' });
    }
  }, [selectedRecipients, loadConversations, loadMessages]);

  // ── Add/remove recipient in new conversation modal ──
  const toggleRecipient = (userId) => {
    setSelectedRecipients((prev) =>
      prev.includes(userId)
        ? prev.filter((id) => id !== userId)
        : [...prev, userId],
    );
  };

  // ── Polling for new messages ──
  useEffect(() => {
    if (!userId) return;
    // Initial load
    loadConversations();

    // Set up polling
    pollTimerRef.current = setInterval(() => {
      loadConversations();
      if (activeConvId) {
        loadMessages(activeConvId);
      }
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, [userId, loadConversations, activeConvId, loadMessages]);

  // ── Reload messages when active conversation changes ──
  useEffect(() => {
    if (activeConvId) {
      loadMessages(activeConvId);
      // Mark as read on switch
      const conv = conversations.find((c) => c.conversation_id === activeConvId);
      if (conv?.unread_count > 0) {
        markRead(activeConvId);
      }
    }
  }, [activeConvId, loadMessages, conversations, markRead]);

  // ── Render ──
  const activeConversation = conversations.find(
    (c) => c.conversation_id === activeConvId,
  );

  return (
    <div className="main-layout">
      <Sidebar />
      <div className="main-content dot-grid mobile-layout-offset">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Messages</h1>
              <p className="page-subtitle">
                In-platform messaging with trustees, beneficiaries, advisors, and
                administrators
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Send and receive messages with other TrustOffice users' },
                  { text: 'Create group conversations with multiple participants' },
                  { text: 'Messages are polled automatically every 15 seconds' },
                ]}
                taPrompt="Walk me through the messaging system and how to send a message"
              />
              <Button
                className="btn-primary"
                onClick={() => setShowNewConv(true)}
              >
                <Plus className="w-4 h-4 mr-2" />
                New Message
              </Button>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center pt-20">
              <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin rounded-full" />
            </div>
          ) : (
            <div className="grid grid-cols-12 gap-4 h-[calc(100vh-16rem)] min-h-[500px]">
              {/* ── Conversation List (Left Panel) ── */}
              <div className="col-span-4 border border-white/10 rounded-lg overflow-hidden flex flex-col bg-[#0a0e1a]">
                <div className="p-3 border-b border-white/10 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white">Conversations</h3>
                  <Badge variant="secondary">{conversations.length}</Badge>
                </div>
                <ScrollArea className="flex-1">
                  {conversations.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full p-6 text-center">
                      <MessageSquare className="w-10 h-10 text-muted-foreground/30 mb-3" />
                      <p className="text-sm text-muted-foreground">
                        No conversations yet
                      </p>
                      <p className="text-xs text-muted-foreground/70 mt-1 max-w-xs">
                        Message trustees, beneficiaries, and advisors connected to your trust
                      </p>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="mt-3"
                        onClick={() => setShowNewConv(true)}
                      >
                        <Plus className="w-3.5 h-3.5 mr-1.5" />
                        Start a Conversation
                      </Button>
                    </div>
                  ) : (
                    conversations.map((conv) => {
                      const otherParticipants = conv.participants.filter(
                        (p) => p.user_id !== userId,
                      );
                      const namesStr = otherParticipants
                        .map((p) => p.name)
                        .join(', ');
                      const isActive = conv.conversation_id === activeConvId;
                      const lastMsgAt = conv.last_message_at
                        ? formatRelativeTime(conv.last_message_at)
                        : '';
                      const senderId = conv.last_message_sender_id;
                      const senderIsMe = senderId === userId;

                      return (
                        <button
                          key={conv.conversation_id}
                          onClick={() => selectConversation(conv)}
                          className={`w-full p-3 flex items-start gap-3 hover:bg-white/5 transition-colors text-left border-b border-white/5 last:border-b-0 ${
                            isActive ? 'bg-white/10' : ''
                          }`}
                        >
                          {/* Avatars */}
                          <div className="flex -space-x-2 flex-shrink-0">
                            {otherParticipants.length === 1 ? (
                              <Avatar className="w-9 h-9 border-2 border-white/20">
                                <AvatarImage
                                  src={
                                    otherParticipants[0]?.picture || undefined
                                  }
                                  alt={otherParticipants[0]?.name}
                                />
                                <AvatarFallback>
                                  {otherParticipants[0]?.name?.charAt(0) || '?'}
                                </AvatarFallback>
                              </Avatar>
                            ) : (
                              <div className="w-9 h-9 rounded-full bg-navy flex items-center justify-center border-2 border-white/20 text-[10px] font-bold text-gold">
                                <Users className="w-4 h-4" />
                              </div>
                            )}
                          </div>

                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-sm font-medium text-white truncate">
                                {namesStr || 'Unknown'}
                              </span>
                              {lastMsgAt && (
                                <span className="text-[10px] text-muted-foreground flex-shrink-0 ml-2">
                                  {lastMsgAt}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[11px] text-muted-foreground truncate">
                                {conv.last_message
                                  ? senderIsMe
                                    ? `You: ${conv.last_message}`
                                    : conv.last_message
                                  : 'No messages yet'}
                              </span>
                              {conv.unread_count > 0 && (
                                <Badge
                                  variant="default"
                                  className="flex-shrink-0 ml-1"
                                >
                                  {conv.unread_count}
                                </Badge>
                              )}
                            </div>
                          </div>
                        </button>
                      );
                    })
                  )}
                </ScrollArea>
              </div>

              {/* ── Message Thread (Right Panel) ── */}
              <div className="col-span-8 border border-white/10 rounded-lg overflow-hidden flex flex-column bg-[#0a0e1a]">
                {/* Thread Header */}
                <div className="p-3 border-b border-white/10 flex items-center justify-between flex-shrink-0">
                  {activeConversation ? (
                    <>
                      <div className="flex items-center gap-2">
                        <Avatar className="w-8 h-8">
                          <AvatarFallback>
                            <Users className="w-3.5 h-3.5" />
                          </AvatarFallback>
                        </Avatar>
                        <div>
                          <h3 className="text-sm font-semibold text-white">
                            {activeConversation.participants
                              .filter((p) => p.user_id !== userId)
                              .map((p) => p.name)
                              .join(', ') || 'Unknown'}
                          </h3>
                          <p className="text-[10px] text-muted-foreground">
                            {activeConversation.participants.length} participant
                            {activeConversation.participants.length !== 1
                              ? 's'
                              : ''}
                          </p>
                        </div>
                      </div>
                      <div className="flex gap-1">
                        <Badge variant="secondary">
                          {messages.length} messages
                        </Badge>
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Select a conversation to view messages
                    </p>
                  )}
                </div>

                {/* Messages */}
                <ScrollArea className="flex-1 p-4 space-y-4">
                  {activeConversation ? (
                    messages.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full">
                        <MessageSquare className="w-10 h-10 text-muted-foreground/30 mb-2" />
                        <p className="text-sm text-muted-foreground">
                          No messages yet. Start the conversation!
                        </p>
                      </div>
                    ) : (
                      messages.map((msg) => {
                        const isSent = msg.sender_id === userId;
                        return (
                          <div
                            key={msg.message_id}
                            className={`flex ${isSent ? 'justify-end' : 'justify-start'}`}
                          >
                            <div
                              className={`max-w-[75%] rounded-lg px-4 py-2.5 shadow-sm ${
                                isSent
                                  ? 'bg-navy text-white border border-white/10'
                                  : 'bg-white/5 text-white border border-white/5'
                              }`}
                            >
                              <div className="flex items-center gap-2 mb-0.5">
                                {!isSent && (
                                  <span className="text-[10px] font-medium text-gold">
                                    {(() => {
                                      const p =
                                        activeConversation.participants.find(
                                          (p) => p.user_id === msg.sender_id,
                                        );
                                      return p?.name || 'Unknown';
                                    })()}
                                  </span>
                                )}
                                <span
                                  className={`text-[9px] ${
                                    isSent
                                      ? 'text-white/50'
                                      : 'text-muted-foreground'
                                  }`}
                                >
                                  {formatTime(msg.created_at)}
                                </span>
                                {isSent &&
                                  msg.read_by &&
                                  msg.read_by.includes(userId) && (
                                    <Check className="w-3 h-3 text-gold/70" />
                                  )}
                              </div>
                              <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
                                {msg.body}
                              </p>
                            </div>
                          </div>
                        );
                      })
                    )
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full">
                      <Circle className="w-10 h-10 text-muted-foreground/20 mb-2" />
                      <p className="text-sm text-muted-foreground text-center">
                        Select a conversation from the list to view messages
                      </p>
                    </div>
                  )}
                </ScrollArea>

                {/* Message Input */}
                {activeConversation && (
                  <div className="p-3 border-t border-white/10 flex-shrink-0">
                    <div className="flex items-end gap-2">
                      <Textarea
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        placeholder="Type a message..."
                        className="flex-1 resize-none"
                        rows={1}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            sendMessage();
                          }
                        }}
                      />
                      <Button
                        className="btn-primary flex-shrink-0"
                        onClick={sendMessage}
                        disabled={sending || !inputText.trim()}
                      >
                        <Send className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      <MobileBottomNav />

      {/* ── New Conversation Modal ── */}
      {showNewConv && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/50">
          <div className="bg-navy border border-white/20 rounded-lg w-full max-w-lg mx-4 shadow-xl">
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">
                New Conversation
              </h3>
              <button
                onClick={() => {
                  setShowNewConv(false);
                  setSelectedRecipients([]);
                  setSearchQuery('');
                  setSearchResults([]);
                }}
                className="text-muted-foreground hover:text-white transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="p-4 border-b border-white/10">
              <label className="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1 block">
                Search users
              </label>
              <Input
                placeholder="Type name to search..."
                value={searchQuery}
                onChange={(e) => searchUsers(e.target.value)}
                autoFocus
              />
              {searchResults.length > 0 && (
                <ScrollArea className="h-40 mt-2 border border-white/10 rounded-md overflow-y-auto">
                  {searchResults.map((u) => (
                    <button
                      key={u.user_id}
                      onClick={() => toggleRecipient(u.user_id)}
                      className={`w-full p-2 flex items-center gap-3 hover:bg-white/10 transition-colors ${
                        selectedRecipients.includes(u.user_id)
                          ? 'bg-gold/20'
                          : ''
                      }`}
                    >
                      <Avatar className="w-7 h-7 flex-shrink-0">
                        {u.picture ? (
                          <AvatarImage
                            src={u.picture}
                            alt={u.name}
                          />
                        ) : null}
                        <AvatarFallback className="text-[10px]">
                          {u.name?.charAt(0) || '?'}
                        </AvatarFallback>
                      </Avatar>
                      <span className="text-sm text-white">
                        {u.name}
                      </span>
                      {selectedRecipients.includes(u.user_id) && (
                        <Check className="w-3.5 h-3.5 text-gold ml-auto" />
                      )}
                    </button>
                  ))}
                </ScrollArea>
              )}
              {searchResults.length === 0 && searchQuery && (
                <p className="text-xs text-muted-foreground mt-2 text-center">
                  No matching users found
                </p>
              )}
            </div>

            {/* Selected recipients */}
            {selectedRecipients.length > 0 && (
              <div className="p-3 border-b border-white/10">
                <label className="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-1 block">
                  Recipients ({selectedRecipients.length})
                </label>
                <ScrollArea className="h-16 mt-1">
                  <div className="flex flex-wrap gap-2">
                    {selectedRecipients.map((uid) => {
                      const u = searchResults.find((r) => r.user_id === uid);
                      const name = u?.name || uid;
                      return (
                        <Badge key={uid} variant="default" className="flex items-center gap-1">
                          <span className="text-[10px]">{name}</span>
                          <button
                            onClick={() => toggleRecipient(uid)}
                            className="ml-1 hover:text-destructive"
                          >
                            ✕
                          </button>
                        </Badge>
                      );
                    })}
                    {!searchResults.some((u) =>
                      selectedRecipients.includes(u.user_id),
                    ) &&
                      selectedRecipients.map((uid) => (
                        <Badge key={uid} variant="secondary" className="text-[10px]">
                          {uid}
                        </Badge>
                      ))}
                  </div>
                </ScrollArea>
              </div>
            )}

            {/* Actions */}
            <div className="p-4 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setShowNewConv(false);
                  setSelectedRecipients([]);
                  setSearchQuery('');
                  setSearchResults([]);
                }}
              >
                Cancel
              </Button>
              <Button
                className="btn-primary"
                onClick={createConversation}
                disabled={selectedRecipients.length === 0}
              >
                <Send className="w-3.5 h-3.5 mr-1.5" />
                Create
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}