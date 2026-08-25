import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import { fetchWithAuth } from '@/utils/api';
import {
  Mail, Copy, Check, Loader2, Lock, ArrowUpCircle,
  Inbox, Clock, ChevronDown, ChevronUp,
} from 'lucide-react';

const API_BASE = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

/**
 * EmailArchiveCard — BCC email capture settings card.
 *
 * Shows per-trust archive address, enable/disable toggle, and instructions.
 * Tier-gated: only Estate and Advisor plans can enable.
 * Trustee plan shows an upgrade prompt.
 *
 * Props:
 *   trustId: string — the selected trust's ID
 *   trustName: string — the selected trust's name
 */
export default function EmailArchiveCard({ trustId, trustName }) {
  const { subscription } = useAuth();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [copied, setCopied] = useState(false);

  const planType = subscription?.plan_type || 'forever_free';
  const eligible = planType === 'estate' || planType === 'advisor';

  useEffect(() => {
    if (!trustId) return;
    loadStatus();
  }, [trustId]);

  async function loadStatus() {
    setLoading(true);
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/trusts/${trustId}/email-archive/status`);
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (e) {
      // Silently fail — card just shows loading state
    } finally {
      setLoading(false);
    }
  }

  async function handleEnable() {
    setToggling(true);
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/trusts/${trustId}/email-archive/enable`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
        toast.success('Email Archive enabled');
      } else {
        const err = await res.json();
        if (res.status === 403) {
          toast.error('Upgrade to Estate or Advisor plan to enable Email Archive');
        } else {
          showError(err);
        }
      }
    } catch (e) {
      showError(e);
    } finally {
      setToggling(false);
    }
  }

  async function handleDisable() {
    setToggling(true);
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/trusts/${trustId}/email-archive/disable`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
        toast.success('Email Archive disabled');
      } else {
        const err = await res.json();
        showError(err);
      }
    } catch (e) {
      showError(e);
    } finally {
      setToggling(false);
    }
  }

  async function copyAddress() {
    if (status?.full_address) {
      try {
        await navigator.clipboard.writeText(status.full_address);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
        toast.success('Address copied to clipboard');
      } catch {
        toast.error('Failed to copy — select and copy manually');
      }
    }
  }

  // ── Render ─────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="rounded-lg border border-border p-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading Email Archive...</span>
        </div>
      </div>
    );
  }

  // Not eligible (Trustee plan)
  if (!eligible) {
    return (
      <div className="rounded-lg border border-border p-6 bg-muted/30">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center flex-shrink-0">
            <Lock className="w-5 h-5 text-amber-600" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-foreground flex items-center gap-2">
              Email Archive
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              Automatically capture emails to beneficiaries by BCCing a unique archive address.
            </p>
            <div className="mt-3 rounded-md bg-amber-50 border border-amber-200 px-3 py-2">
              <p className="text-sm text-amber-800">
                Available on <strong>Estate ($149/mo)</strong> and <strong>Advisor ($399/mo)</strong> plans.
                Your current plan: <span className="capitalize">{planType}</span>.
              </p>
            </div>
            <Button
              className="mt-3"
              size="sm"
              onClick={() => {
                window.location.href = '/settings?tab=billing';
              }}
            >
              <ArrowUpCircle className="w-4 h-4 mr-1.5" />
              Upgrade to Enable
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Eligible but not yet enabled
  if (!status?.enabled) {
    return (
      <div className="rounded-lg border border-border p-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
            <Inbox className="w-5 h-5 text-blue-600" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-foreground">Email Archive</h3>
            <p className="text-sm text-muted-foreground mt-1">
              BCC a unique email address on emails to beneficiaries to automatically log them
              in your Communications Log. No manual entry needed.
            </p>
            <Button
              className="mt-3"
              size="sm"
              onClick={handleEnable}
              disabled={toggling}
            >
              {toggling ? (
                <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Enabling...</>
              ) : (
                <>Enable Email Archive</>
              )}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Enabled — show address and instructions
  return (
    <div className="rounded-lg border border-border p-6">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-green-50 flex items-center justify-center flex-shrink-0">
          <Mail className="w-5 h-5 text-green-600" />
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-foreground">Email Archive</h3>
            <span className="text-xs text-green-600 font-medium flex items-center gap-1">
              <Check className="w-3.5 h-3.5" /> Active
            </span>
          </div>

          <p className="text-sm text-muted-foreground mt-1 mb-3">
            BCC this address on emails to beneficiaries to auto-log them:
          </p>

          {/* Address display with copy button */}
          <div className="flex items-center gap-2">
            <div className="flex-1 rounded-md bg-muted border border-border px-3 py-2 font-mono text-sm select-all">
              {status.full_address}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={copyAddress}
              className="flex-shrink-0"
            >
              {copied ? (
                <><Check className="w-4 h-4 mr-1" /> Copied</>
              ) : (
                <><Copy className="w-4 h-4 mr-1" /> Copy</>
              )}
            </Button>
          </div>

          {/* Instructions */}
          <div className="mt-3 rounded-md bg-blue-50 border border-blue-100 px-3 py-2">
            <p className="text-xs text-blue-800">
              <strong>How to use:</strong> When composing an email to a beneficiary, add
              <code className="mx-1 px-1 bg-blue-100 rounded font-mono text-xs">{status.full_address}</code>
              to the BCC field. The email will appear in your Communications Log automatically.
            </p>
          </div>

          {status.enabled_at && (
            <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Enabled {new Date(status.enabled_at).toLocaleDateString()}
            </p>
          )}

          {/* Disable button */}
          <button
            className="mt-3 text-xs text-muted-foreground hover:text-destructive transition-colors"
            onClick={handleDisable}
            disabled={toggling}
          >
            {toggling ? 'Disabling...' : 'Disable Email Archive'}
          </button>
        </div>
      </div>
    </div>
  );
}