import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { fetchWithAuth } from '@/utils/api';
import { showError } from '@/utils/errors';
import { toast } from 'sonner';
import { format, parseISO } from 'date-fns';
import {
  Mail, Search, Copy, Check, Inbox, Clock, Users,
  ArrowLeft, MessageSquare,
} from 'lucide-react';
import PageHelpButton from '@/components/PageHelpButton';

const POLL_INTERVAL_MS = 30000;

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

// ── Trust Email Card ─────────────────────────────────────────────────────────

function TrustEmailCard({ trustId, trustName }) {
  const [copied, setCopied] = useState(false);

  // Generate a deterministic-looking email address based on trust ID
  const emailAlias = trustId
    ? `${trustId.replace(/[^a-z0-9]/gi, '').toLowerCase().slice(0, 12)}@trustoffice.app`
    : 'messages@trustoffice.app';

  const handleCopy = () => {
    navigator.clipboard.writeText(emailAlias).then(() => {
      setCopied(true);
      toast.success('Email address copied');
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="card-trust p-6 mb-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Inbox className="w-4 h-4 text-gold" />
            <h2 className="font-serif text-lg text-navy">Trust Message Archive</h2>
            <Badge variant="outline" className="font-mono text-[10px] uppercase tracking-wider text-gold border-gold/30">
              Coming Soon
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mb-3 max-w-2xl">
            CC or BCC this address on any email conversation with beneficiaries, advisors, or attorneys.
            Messages are automatically archived here, creating a searchable record of all trust-related communications.
          </p>
          <div className="flex items-center gap-2">
            <code className="font-mono text-sm text-navy bg-muted px-3 py-1.5 border border-border">
              {emailAlias}
            </code>
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopy}
              className="flex items-center gap-1.5"
            >
              {copied ? (
                <><Check className="w-3.5 h-3.5 text-gold" /> Copied</>
              ) : (
                <><Copy className="w-3.5 h-3.5" /> Copy</>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Conversation Item ────────────────────────────────────────────────────────

function ConversationItem({ conv, userId, isActive, onClick }) {
  const otherParticipants = conv.participants?.filter(
    (p) => p.user_id !== userId,
  ) || [];
  const namesStr = otherParticipants.map((p) => p.name).join(', ');
  const lastMsgAt = conv.last_message_at
    ? formatRelativeTime(conv.last_message_at)
    : '';
  const senderIsMe = conv.last_message_sender_id === userId;

  return (
    <button
      onClick={onClick}
      className={`w-full p-3 flex items-start gap-3 hover:bg-muted/50 transition-colors text-left border-b border-border last:border-b-0 ${
        isActive ? 'bg-muted/30' : ''
      }`}
    >
      <div className="flex -space-x-2 flex-shrink-0">
        {otherParticipants.length === 1 ? (
          <Avatar className="w-9 h-9 border border-border">
            <AvatarImage src={otherParticipants[0]?.picture || undefined} alt={otherParticipants[0]?.name} />
            <AvatarFallback className="font-mono text-xs text-navy bg-navy/5">
              {otherParticipants[0]?.name?.charAt(0) || '?'}
            </AvatarFallback>
          </Avatar>
        ) : (
          <div className="w-9 h-9 border border-border flex items-center justify-center bg-navy/5">
            <Users className="w-4 h-4 text-navy" />
          </div>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-sm font-medium text-navy truncate">
            {namesStr || 'Unknown'}
          </span>
          {lastMsgAt && (
            <span className="text-[10px] font-mono text-muted-foreground flex-shrink-0 ml-2">
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
            <Badge className="flex-shrink-0 ml-1 font-mono text-[10px]">
              {conv.unread_count}
            </Badge>
          )}
        </div>
      </div>
    </button>
  );
}

// ── Message Bubble ───────────────────────────────────────────────────────────

function MessageBubble({ msg, isSent, senderName }) {
  return (
    <div className={`flex ${isSent ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[75%] px-4 py-2.5 border ${
          isSent
            ? 'bg-navy text-white border-navy'
            : 'bg-white text-navy border-border'
        }`}
      >
        <div className="flex items-center gap-2 mb-0.5">
          {!isSent && (
            <span className="text-[10px] font-medium text-gold font-mono">
              {senderName}
            </span>
          )}
          <span
            className={`text-[9px] font-mono ${
              isSent ? 'text-white/50' : 'text-muted-foreground'
            }`}
          >
            {formatTime(msg.created_at)}
          </span>
          {isSent && msg.read_by && msg.read_by.includes(msg.sender_id) && (
            <Check className="w-3 h-3 text-gold/70" />
          )}
        </div>
        <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
          {msg.body}
        </p>
      </div>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function MessagingPage() {
  const { user, selectedTrust } = useAuth();
  const userId = user?.user_id;

  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  const pollTimerRef = useRef(null);

  const loadConversations = useCallback(async () => {
    if (!userId) return;
    try {
      const res = await fetchWithAuth('/messaging/conversations');
      if (!res.ok) throw new Error('Failed to load conversations');
      const data = await res.json();
      setConversations(data.conversations || []);
      if (!activeConvId && data.conversations?.length > 0) {
        setActiveConvId(data.conversations[0].conversation_id);
      }
    } catch (e) {
      showError(toast, e, { operation: 'load_conversations', page: 'Messaging' });
    } finally {
      setLoading(false);
    }
  }, [userId, activeConvId]);

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

  const markRead = useCallback(async (convId) => {
    try {
      await fetchWithAuth(`/messaging/conversations/${convId}/read`, { method: 'PATCH' });
      setConversations((prev) =>
        prev.map((c) =>
          c.conversation_id === convId ? { ...c, unread_count: 0 } : c,
        ),
      );
    } catch {
      // non-fatal
    }
  }, []);

  const selectConversation = useCallback((conv) => {
    setActiveConvId(conv.conversation_id);
    setMessages([]);
    loadMessages(conv.conversation_id);
    if (conv.unread_count > 0) markRead(conv.conversation_id);
  }, [loadMessages, markRead]);

  // Polling
  useEffect(() => {
    if (!userId) return;
    loadConversations();
    pollTimerRef.current = setInterval(() => {
      loadConversations();
      if (activeConvId) loadMessages(activeConvId);
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [userId, loadConversations, activeConvId, loadMessages]);

  useEffect(() => {
    if (activeConvId) {
      loadMessages(activeConvId);
      const conv = conversations.find((c) => c.conversation_id === activeConvId);
      if (conv?.unread_count > 0) markRead(activeConvId);
    }
  }, [activeConvId, loadMessages, conversations, markRead]);

  // Filter conversations by search
  const filteredConversations = conversations.filter((conv) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const otherParticipants = conv.participants?.filter((p) => p.user_id !== userId) || [];
    const names = otherParticipants.map((p) => p.name).join(' ').toLowerCase();
    const lastMsg = (conv.last_message || '').toLowerCase();
    return names.includes(q) || lastMsg.includes(q);
  });

  const activeConversation = conversations.find((c) => c.conversation_id === activeConvId);

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
                Archive and search trust-related email conversations
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'CC or BCC your trust email address on any conversation to archive it here' },
                  { text: 'Search across all archived messages by sender, subject, or content' },
                  { text: 'Messages sync automatically every 30 seconds' },
                ]}
                taPrompt="How does the message archive work?"
              />
            </div>
          </div>

          {/* Trust Email Address Card */}
          <TrustEmailCard trustId={selectedTrust?.trust_id} trustName={selectedTrust?.name} />

          {/* Search Bar */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search archived messages..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          {loading ? (
            <div className="flex items-center justify-center pt-20">
              <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin" />
            </div>
          ) : conversations.length === 0 ? (
            /* Empty State */
            <div className="card-trust p-12 flex flex-col items-center justify-center text-center">
              <Mail className="w-12 h-12 text-muted-foreground/30 mb-4" />
              <h3 className="font-serif text-xl text-navy mb-2">No archived messages yet</h3>
              <p className="text-sm text-muted-foreground max-w-md">
                Once you start CC-ing your trust email address on conversations,
                they'll appear here as a searchable archive. This creates a permanent
                record of all trust-related communications with beneficiaries, advisors,
                and attorneys.
              </p>
            </div>
          ) : (
            /* Two-Panel Layout */
            <div className="grid grid-cols-12 gap-4 h-[calc(100vh-24rem)] min-h-[400px]">
              {/* Conversation List (Left) */}
              <div className="col-span-4 lg:col-span-5 border border-border flex flex-col bg-white overflow-hidden">
                <div className="p-3 border-b border-border flex items-center justify-between">
                  <h3 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Archived Conversations
                  </h3>
                  <Badge variant="secondary" className="font-mono text-[10px]">
                    {filteredConversations.length}
                  </Badge>
                </div>
                <ScrollArea className="flex-1">
                  {filteredConversations.length === 0 && searchQuery ? (
                    <div className="flex flex-col items-center justify-center h-full p-6 text-center">
                      <Search className="w-8 h-8 text-muted-foreground/30 mb-2" />
                      <p className="text-sm text-muted-foreground">No matches found</p>
                    </div>
                  ) : (
                    filteredConversations.map((conv) => (
                      <ConversationItem
                        key={conv.conversation_id}
                        conv={conv}
                        userId={userId}
                        isActive={conv.conversation_id === activeConvId}
                        onClick={() => selectConversation(conv)}
                      />
                    ))
                  )}
                </ScrollArea>
              </div>

              {/* Message Detail (Right) */}
              <div className="col-span-8 lg:col-span-7 border border-border flex flex-col bg-white overflow-hidden">
                {/* Thread Header */}
                <div className="p-3 border-b border-border flex items-center justify-between flex-shrink-0">
                  {activeConversation ? (
                    <div className="flex items-center gap-2">
                      <div>
                        <h3 className="font-serif text-sm text-navy">
                          {activeConversation.participants
                            ?.filter((p) => p.user_id !== userId)
                            .map((p) => p.name)
                            .join(', ') || 'Unknown'}
                        </h3>
                        <p className="text-[10px] font-mono text-muted-foreground">
                          {activeConversation.participants?.length || 0} participant{activeConversation.participants?.length !== 1 ? 's' : ''}
                          {' · '}{messages.length} message{messages.length !== 1 ? 's' : ''}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">Select a conversation to view messages</p>
                  )}
                </div>

                {/* Messages */}
                <ScrollArea className="flex-1 p-4 space-y-4">
                  {activeConversation ? (
                    messages.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full">
                        <MessageSquare className="w-10 h-10 text-muted-foreground/30 mb-2" />
                        <p className="text-sm text-muted-foreground">No messages in this conversation yet</p>
                      </div>
                    ) : (
                      messages.map((msg) => {
                        const isSent = msg.sender_id === userId;
                        const sender = activeConversation.participants?.find(
                          (p) => p.user_id === msg.sender_id,
                        );
                        return (
                          <MessageBubble
                            key={msg.message_id}
                            msg={msg}
                            isSent={isSent}
                            senderName={sender?.name || 'Unknown'}
                          />
                        );
                      })
                    )
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full">
                      <Mail className="w-10 h-10 text-muted-foreground/20 mb-2" />
                      <p className="text-sm text-muted-foreground text-center">
                        Select a conversation from the list to view messages
                      </p>
                    </div>
                  )}
                </ScrollArea>
              </div>
            </div>
          )}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}