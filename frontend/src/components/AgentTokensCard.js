// AgentTokensCard (JOB-20261018-TO-AGENT-BRIDGE, phase 1 completion).
//
// Token self-serve for the read-only MCP bridge: customers issue, list, and
// revoke per-agent access tokens (Settings > AI Agents). The bridge endpoint
// (`POST /api/mcp`, JSON-RPC) was live in prod; this card finishes the
// self-serve half so a customer can connect their own AI agent without
// operator involvement.
//
// Contract (backend/routers/mcp_bridge.py):
//  - GET  /api/mcp/tokens          -> { tokens: [{token_id, agent_name,
//      token_hint, scope, created_at, last_used_at, call_count}] }
//  - POST /api/mcp/tokens {agent_name} -> { token (shown ONCE), token_id,
//      agent_name, scope, note }
//  - DELETE /api/mcp/tokens/{id}   -> { revoked: true, token_id }
//
// The raw token is displayed once with a copy button; only its hash is ever
// stored server-side. Copy mirrors the TwoFactorCard clipboard convention.

import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { fetchWithAuth, getErrorMessage } from '@/utils/api';
import { showError } from '@/utils/errors';
import { toast } from 'sonner';
import { Bot, Copy, Plus, Trash2, BotOff } from 'lucide-react';

// ASCII-only relative-time formatter, same conventions as DevicesSessionsCard.
function relativeTime(iso) {
  if (!iso) return 'never used';
  const then = new Date(iso);
  if (isNaN(then.getTime())) return 'unknown';
  const diff = Date.now() - then.getTime();
  if (diff < 0) return 'just now';
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`;
  return then.toLocaleDateString();
}

export default function AgentTokensCard() {
  const [tokens, setTokens] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [agentName, setAgentName] = useState('');
  const [creating, setCreating] = useState(false);
  const [issued, setIssued] = useState(null); // { token, token_id, agent_name } until dismissed
  const [copied, setCopied] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [confirmRevoke, setConfirmRevoke] = useState(null); // token_id pending revoke

  const load = useCallback(async () => {
    try {
      const res = await fetchWithAuth('/mcp/tokens');
      if (!res.ok) throw res;
      const data = await res.json();
      setTokens(data.tokens || []);
      setError(null);
    } catch (err) {
      setError(await getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (e) => {
    e.preventDefault();
    const name = agentName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const res = await fetchWithAuth('/mcp/tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_name: name }),
      });
      if (!res.ok) throw res;
      const data = await res.json();
      setIssued(data);
      setAgentName('');
      setCopied(false);
      toast.success('Agent token issued — copy it now, it is shown only once');
      load();
    } catch (err) {
      showError(toast, err, { operation: 'create-agent-token', page: 'Settings' });
    } finally {
      setCreating(false);
    }
  };

  const copyToken = async () => {
    try {
      await navigator.clipboard.writeText(issued.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
      toast.success('Copied to clipboard');
    } catch (err) {
      showError(toast, err, { operation: 'copy', page: 'Settings' });
    }
  };

  const handleRevoke = async (token_id) => {
    setBusyId(token_id);
    setConfirmRevoke(null);
    try {
      const res = await fetchWithAuth(`/mcp/tokens/${encodeURIComponent(token_id)}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw res;
      toast.success('Agent token revoked — that agent can no longer connect');
      load();
    } catch (err) {
      showError(toast, err, { operation: 'revoke-agent-token', page: 'Settings' });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="p-4 border border-navy/10" data-testid="agent-tokens-card">
      <div className="w-full">
        <div className="flex items-center gap-2 mb-1">
          <Bot className="w-5 h-5 text-navy" />
          <p className="font-medium text-navy">AI agents</p>
        </div>
        <p className="text-sm text-muted-foreground mb-3">
          Connect your own AI assistant (Claude, ChatGPT, or any MCP-capable agent)
          to read your trust calendar, documents, and summaries securely.
          Read-only: agents can view but never change anything. Each token works
          for one agent and can be revoked instantly.
        </p>

        {issued && (
          <div className="mb-3 p-3 border border-navy/20 bg-cream/60" data-testid="agent-token-issued">
            <p className="font-medium text-navy text-sm mb-1">
              Token for &ldquo;{issued.agent_name}&rdquo; — shown only once:
            </p>
            <div className="flex items-center gap-2">
              <code
                className="flex-1 p-2 text-xs bg-background border border-navy/10 break-all select-all"
                data-testid="agent-token-raw"
              >
                {issued.token}
              </code>
              <Button variant="outline" size="sm" onClick={copyToken} data-testid="agent-token-copy">
                <Copy className="w-4 h-4 mr-1" />
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
            <div className="flex items-center justify-between mt-2">
              <p className="text-xs text-muted-foreground">
                Store it in your agent&rsquo;s settings now. If you lose it, revoke and issue a new one.
              </p>
              <Button variant="ghost" size="sm" onClick={() => setIssued(null)} data-testid="agent-token-dismiss">
                Done
              </Button>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-3 p-3 border border-red-300 bg-red-50 text-sm text-red-700" role="alert" data-testid="agent-tokens-error">
            {error}
            <button type="button" className="ml-2 underline" onClick={load} data-testid="agent-tokens-retry">
              Retry
            </button>
          </div>
        )}

        {loading && (
          <p className="text-sm text-muted-foreground" data-testid="agent-tokens-loading">
            Loading connected agents...
          </p>
        )}

        {!loading && !error && tokens.length === 0 && !issued && (
          <p className="text-sm text-muted-foreground mb-3" data-testid="agent-tokens-empty">
            No agents connected yet. Name your agent below to get its access token.
          </p>
        )}

        {!loading && !error && tokens.length > 0 && (
          <ul className="space-y-2 mb-3" data-testid="agent-tokens-list">
            {tokens.map((t) => (
              <li
                key={t.token_id}
                className="flex items-center justify-between p-3 border border-navy/10"
                data-testid="agent-token-row"
              >
                <div className="min-w-0">
                  <p className="font-medium text-navy truncate">
                    {t.agent_name}
                    <span className="ml-2 text-xs text-muted-foreground font-normal">•••{t.token_hint}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Added {relativeTime(t.created_at)} · last used {relativeTime(t.last_used_at)} ·
                    {' '}{t.call_count ?? 0} read{t.call_count === 1 ? '' : 's'}
                    {t.expires_at ? ` · expires ${relativeTime(t.expires_at)}` : ''}
                    {t.rate_limit ? ` · ${t.rate_limit}/hour` : ''}
                  </p>
                </div>
                {confirmRevoke === t.token_id ? (
                  <div className="flex items-center gap-2 shrink-0" data-testid="agent-token-confirm">
                    <span className="text-xs text-red-700">Revoke access?</span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-red-300 text-red-700"
                      onClick={() => handleRevoke(t.token_id)}
                      disabled={busyId === t.token_id}
                      data-testid="agent-token-revoke-yes"
                    >
                      {busyId === t.token_id ? 'Revoking...' : 'Yes, revoke'}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setConfirmRevoke(null)} data-testid="agent-token-revoke-no">
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmRevoke(t.token_id)}
                    disabled={busyId === t.token_id}
                    data-testid="agent-token-revoke"
                  >
                    <Trash2 className="w-4 h-4 mr-1" />
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}

        {!issued && (
          <form onSubmit={handleCreate} className="flex items-center gap-2" data-testid="agent-token-form">
            <input
              type="text"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              maxLength={80}
              placeholder="Agent name (e.g. Claude, Jarvis)"
              className="flex-1 p-2 border border-navy/10 bg-background text-sm"
              data-testid="agent-name-input"
              aria-label="Agent name"
            />
            <Button
              type="submit"
              size="sm"
              disabled={creating || !agentName.trim()}
              data-testid="agent-token-create"
            >
              <Plus className="w-4 h-4 mr-1" />
              {creating ? 'Issuing...' : 'Connect agent'}
            </Button>
          </form>
        )}
        {issued && (
          <p className="text-xs text-muted-foreground flex items-center gap-1">
            <BotOff className="w-3 h-3" /> One token per agent — issue another after dismissing this one.
          </p>
        )}
      </div>
    </div>
  );
}