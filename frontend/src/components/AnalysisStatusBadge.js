import { useState, useEffect, useRef } from 'react';
import { fetchWithAuth } from '@/utils/api';
import { CheckCircle2, Loader2, AlertTriangle, FileSearch, RotateCw } from 'lucide-react';

/**
 * Small badge showing trust document analysis status on Vault document cards.
 * Only renders for trust_instrument and amendment category documents.
 * Queries by doc_id so each document shows its own status (not trust-level).
 * Polls while status is pending/analyzing. Shows error message and retry button on failure.
 */
export default function AnalysisStatusBadge({ trustId, docId, category }) {
  const [status, setStatus] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [retrying, setRetrying] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    if (category === 'trust_instrument' || category === 'amendment') {
      loadStatus();
    }
    return () => {
      if (pollRef.current) {
        clearTimeout(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [trustId, docId, category]);

  const loadStatus = async () => {
    try {
      const res = await fetchWithAuth(
        `/trusts/${trustId}/document-analysis/status?doc_id=${docId}`
      );
      if (res.ok) {
        const data = await res.json();
        setStatus(data.status);
        setErrorMessage(data.error_message || null);

        // Poll while pending or analyzing (every 5s, up to 2 minutes)
        if (data.status === 'pending' || data.status === 'analyzing') {
          pollRef.current = setTimeout(loadStatus, 5000);
        }
      }
    } catch (e) {
      // Silent
    }
  };

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const res = await fetchWithAuth(
        `/trusts/${trustId}/document-analysis/reanalyze`,
        { method: 'POST' }
      );
      if (res.ok) {
        setStatus('pending');
        setErrorMessage(null);
        // Start polling again
        pollRef.current = setTimeout(loadStatus, 5000);
      }
    } catch (e) {
      // Silent
    } finally {
      setRetrying(false);
    }
  };

  if (category !== 'trust_instrument' && category !== 'amendment') {
    return null;
  }

  if (status === 'complete') {
    return (
      <span className="inline-flex items-center gap-1 text-xs bg-success/10 text-success px-2 py-0.5 font-medium">
        <CheckCircle2 className="w-3 h-3" />
        Analyzed
      </span>
    );
  }

  if (status === 'pending' || status === 'analyzing') {
    return (
      <span className="inline-flex items-center gap-1 text-xs bg-gold/10 text-gold px-2 py-0.5 font-medium">
        <Loader2 className="w-3 h-3 animate-spin" />
        Analyzing...
      </span>
    );
  }

  if (status === 'failed') {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-1">
          <span className="inline-flex items-center gap-1 text-xs bg-error/10 text-error px-2 py-0.5 font-medium">
            <AlertTriangle className="w-3 h-3" />
            Analysis failed
          </span>
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="inline-flex items-center gap-1 text-xs text-navy hover:text-navy/70 px-1.5 py-0.5 font-medium disabled:opacity-50"
            title="Retry analysis"
          >
            <RotateCw className={`w-3 h-3 ${retrying ? 'animate-spin' : ''}`} />
            Retry
          </button>
        </div>
        {errorMessage && (
          <p className="text-[10px] text-neutral-500 leading-tight px-2">
            {errorMessage}
          </p>
        )}
      </div>
    );
  }

  // No analysis yet — show subtle hint
  if (status === 'none') {
    return (
      <span className="inline-flex items-center gap-1 text-xs bg-navy/5 text-navy/40 px-2 py-0.5 font-medium">
        <FileSearch className="w-3 h-3" />
        Not analyzed
      </span>
    );
  }

  return null;
}