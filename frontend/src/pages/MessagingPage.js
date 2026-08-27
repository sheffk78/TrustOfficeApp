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
  ArrowLeft, MessageSquare, Loader2, Lock, ArrowUpCircle,
} from 'lucide-react';
import PageHelpButton from '@/components/PageHelpButton';

const POLL_INTERVAL_MS = 30000;
const API_BASE = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

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

// ── Trust Email Card (real API) ──────────────────────────────────────────────

function TrustEmailCard({ trustId, trustName }) {
  const { subscription } = useAuth();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);
  const [copied, setCopied] = useState(false);

  const planType = subscription?.plan_type || 'forever_free';
  const eligible = planType === 'estate' || planType === 'advisor';

  useEffect(() => {
    if (!trustId) { setLoading(false); return; }
    loadStatus();
  }, [trustId]);

  async function loadStatus() {
    setLoading(true);
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/trusts/${trustId}/email-archive/status`);
      if (res.ok) setStatus(await res.json());
    } catch { /* silent */ }
    finally { setLoading(false); }
  }

  async function handleEnable() {
    setToggling(true);
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/trusts/${trustId}/email-archive/enable`, { method: 'POST' });
      if (res.ok) { setStatus(await res.json()); toast.success('Email Archive enabled'); }
      else if (res.status === 403) { toast.error('Upgrade to Estate or Advisor plan to enable Email Archive'); }
      else { const e = await res.json(); showError(toast, e); }
    } catch (e) { showError(toast, e); }
    finally { setToggling(false); }
  }

  const handleCopy = () => {
    if (status?.full_address) {
      navigator.clipboard.writeText(status.full_address).then(() => {
        setCopied(true);
        toast.success('Address copied');
        setTimeout(() => setCopied(false), 2000);
      });
    }
  };

  if (loading) {
    return (
      <div className="card-trust p-6 mb-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> <span className="text-sm">Loading...</span>
        </div>
      </div>
    );
  }

  // Not eligible (Trustee plan)
  if (!eligible) {
    return (
      <div className="card-trust p-6 mb-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center flex-shrink-0">
            <Lock className="w-5 h-5 text-amber-600" />
          </div>
          <div className="flex-1">
            <h2 className="font-serif text-lg text-navy mb-1">Email Archive</h2>
            <p className="text-sm text-muted-foreground mb-3 max-w-2xl">
              BCC a unique email address on emails to beneficiaries to automatically log them here.
            </p>
            <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 inline-block">
              <p className="text-sm text-amber-800">
                Available on <strong>Estate ($149/mo)</strong> and <strong>Advisor ($399/mo)</strong> plans.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Eligible but not enabled
  if (!status?.enabled) {
    return (
      <div className="card-trust p-6 mb-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
            <Inbox className="w-5 h-5 text-blue-600" />
          </div>
          <div className="flex-1">
            <h2 className="font-serif text-lg text-navy mb-1">Email Archive</h2>
            <p className="text-sm text-muted-foreground mb-3 max-w-2xl">
              BCC a unique email address on emails to beneficiaries to automatically log them in your Communications Log.
            </p>
            <Button size="sm" onClick={handleEnable} disabled={toggling}>
              {toggling ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Enabling...</> : 'Enable Email Archive'}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Enabled — show address
  return (
    <div className="card-trust p-6 mb-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Mail className="w-4 h-4 text-green-600" />
            <h2 className="font-serif text-lg text-navy">Trust Email Archive</h2>
            <Badge variant="outline" className="font-mono text-[10px] uppercase tracking-wider text-green-600 border-green-600/30">
              Active
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mb-3 max-w-2xl">
            BCC this address on emails to beneficiaries to auto-log them here.
          </p>
          <div className="flex items-center gap-2">
            <code className="font-mono text-sm text-navy bg-muted px-3 py-1.5 border border-border select-all">
              {status.full_address}
            </code>
            <Button variant="outline" size="sm" onClick={handleCopy} className="flex items-center gap-1.5">
              {copied ? <><Check className="w-3.5 h-3.5 text-green-600" /> Copied</> : <><Copy className="w-3.5 h-3.5" /> Copy</>}
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

// ── Communications Log Item (BCC-captured emails) ─────────────────────────────

function CommunicationItem({ comm, onClick, isActive }) {
  return (
    <button
      onClick={onClick}
      className={`w-full p-3 flex items-start gap-3 hover:bg-muted/50 transition-colors text-left border-b border-border last:border-b-0 ${
        isActive ? 'bg-muted/30' : ''
      }`}
    >
      <div className="w-9 h-9 border border-border flex items-center justify-center bg-navy/5 flex-shrink-0">
        <Mail className="w-4 h-4 text-navy" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-sm font-medium text-navy truncate">
            {comm.subject || '(no subject)'}
          </span>
          {comm.created_at && (
            <span className="text-[10px] font-mono text-muted-foreground flex-shrink-0 ml-2">
              {formatRelativeTime(comm.created_at)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground truncate">
            {comm.source_email_from || comm.parties?.[0]?.name || ''}
          </span>
          {comm.source === 'bcc_capture' && (
            <Badge variant="outline" className="flex-shrink-0 font-mono text-[9px] uppercase tracking-wider text-green-600 border-green-600/30 px-1 py-0">
              BCC
            </Badge>
          )}
        </div>
      </div>
    </button>
  );
}

function CommunicationDetail({ comm }) {
  if (!comm) return null;
  return (
    <div className="p-4 space-y-3">
      <div>
        <h3 className="font-serif text-base text-navy mb-1">{comm.subject || '(no subject)'}</h3>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {comm.source === 'bcc_capture' && (
            <Badge variant="outline" className="font-mono text-[9px] uppercase tracking-wider text-green-600 border-green-600/30">
              BCC Captured
            </Badge>
          )}
          <span className="font-mono">{formatTime(comm.created_at)}</span>
        </div>
      </div>
      <div className="text-sm text-muted-foreground space-y-1">
        {comm.source_email_from && (
          <p><span className="font-medium text-navy">From:</span> {comm.source_email_from}</p>
        )}
        {comm.source_email_to?.length > 0 && (
          <p><span className="font-medium text-navy">To:</span> {comm.source_email_to.join(', ')}</p>
        )}
      </div>
      <div className="border-t border-border pt-3">
        <p className="text-sm text-navy whitespace-pre-wrap break-words">{comm.content || '(empty body)'}</p>
      </div>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function MessagingPage() {
  const { user, selectedTrust } = useAuth();
  const userId = user?.user_id;

  const [viewMode, setViewMode] = useState('conversations'); // 'conversations' | 'log'
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Communications log state
  const [comms, setComms] = useState([]);
  const [commsLoading, setCommsLoading] = useState(false);
  const [activeCommId, setActiveCommId] = useState(null);
  const [commsFilter, setCommsFilter] = useState(''); // '', 'bcc_capture', 'manual'

  const pollTimerRef = useRef(null);

  const loadComms = useCallback(async () => {
    if (!selectedTrust?.trust_id) return;
    setCommsLoading(true);
    try {
      let url = `${API_BASE}/api/trusts/${selectedTrust.trust_id}/communications?limit=100`;
      if (commsFilter) url += `&source=${commsFilter}`;
      const res = await fetchWithAuth(url);
      if (res.ok) {
        const data = await res.json();
        setComms(data.items || []);
      }
    } catch { /* silent */ }
    finally { setCommsLoading(false); }
  }, [selectedTrust?.trust_id, commsFilter]);

  useEffect(() => {
    if (viewMode === 'log') loadComms();
  }, [viewMode, loadComms]);

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
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
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

          {/* View Mode Toggle */}
          <div className="flex items-center gap-1 mb-4 border border-border rounded-lg p-1 w-fit">
            <button
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${viewMode === 'conversations' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
              onClick={() => setViewMode('conversations')}
            >
              Conversations
            </button>
            <button
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${viewMode === 'log' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
              onClick={() => setViewMode('log')}
            >
              Communications Log
            </button>
          </div>

          {viewMode === 'log' ? (
            /* ── Communications Log View ── */
            <>
              {/* Filter Buttons */}
              <div className="flex items-center gap-2 mb-4">
                {['all', 'bcc_capture', 'manual'].map((f) => (
                  <button
                    key={f}
                    className={`px-3 py-1 text-xs font-medium rounded-md border transition-colors ${
                      (commsFilter === '' ? 'all' : commsFilter) === f
                        ? 'bg-navy text-white border-navy'
                        : 'text-muted-foreground border-border hover:text-navy'
                    }`}
                    onClick={() => setCommsFilter(f === 'all' ? '' : f)}
                  >
                    {f === 'all' ? 'All' : f === 'bcc_capture' ? 'BCC Captured' : 'Manual'}
                  </button>
                ))}
              </div>

              {/* Search Bar */}
              <div className="relative mb-4">
                <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search communications log..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>

              {commsLoading ? (
                <div className="flex items-center justify-center pt-20">
                  <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin" />
                </div>
              ) : comms.length === 0 ? (
                <div className="card-trust p-12 flex flex-col items-center justify-center text-center">
                  <Mail className="w-12 h-12 text-muted-foreground/30 mb-4" />
                  <h3 className="font-serif text-xl text-navy mb-2">No communications logged</h3>
                  <p className="text-sm text-muted-foreground max-w-md">
                    Enable Email Archive above and BCC your trust address on emails to beneficiaries.
                    Captured emails will appear here automatically.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-12 gap-4 h-[calc(100vh-28rem)] min-h-[400px]">
                  <div className="col-span-4 lg:col-span-5 border border-border flex flex-col bg-white overflow-hidden">
                    <div className="p-3 border-b border-border flex items-center justify-between">
                      <h3 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        Communications
                      </h3>
                      <Badge variant="secondary" className="font-mono text-[10px]">
                        {comms.length}
                      </Badge>
                    </div>
                    <ScrollArea className="flex-1">
                      {comms.filter(c => !searchQuery || (c.subject || '').toLowerCase().includes(searchQuery.toLowerCase()) || (c.content || '').toLowerCase().includes(searchQuery.toLowerCase())).map((comm) => (
                        <CommunicationItem
                          key={comm.comm_id}
                          comm={comm}
                          isActive={comm.comm_id === activeCommId}
                          onClick={() => setActiveCommId(comm.comm_id)}
                        />
                      ))}
                    </ScrollArea>
                  </div>
                  <div className="col-span-8 lg:col-span-7 border border-border flex flex-col bg-white overflow-hidden">
                    <ScrollArea className="flex-1">
                      {activeCommId ? (
                        <CommunicationDetail comm={comms.find(c => c.comm_id === activeCommId)} />
                      ) : (
                        <div className="flex flex-col items-center justify-center h-full">
                          <Mail className="w-10 h-10 text-muted-foreground/20 mb-2" />
                          <p className="text-sm text-muted-foreground text-center">
                            Select a communication to view details
                          </p>
                        </div>
                      )}
                    </ScrollArea>
                  </div>
                </div>
              )}
            </>
          ) : (
            /* ── Conversations View (original) ── */
            <>
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
            </>
          )}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}