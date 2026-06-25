import { useState, useEffect } from 'react';
import { fetchWithAuth } from '@/utils/api';
import { CheckCircle2, Loader2, AlertTriangle, FileSearch } from 'lucide-react';

/**
 * Small badge showing trust document analysis status on Vault document cards.
 * Only renders for trust_instrument and amendment category documents.
 */
export default function AnalysisStatusBadge({ trustId, docId, category }) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (category === 'trust_instrument' || category === 'amendment') {
      loadStatus();
    }
  }, [trustId, category]);

  const loadStatus = async () => {
    try {
      const res = await fetchWithAuth(`/trusts/${trustId}/document-analysis/status`);
      if (res.ok) {
        const data = await res.json();
        setStatus(data.status);
      }
    } catch (e) {
      // Silent
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
      <span className="inline-flex items-center gap-1 text-xs bg-error/10 text-error px-2 py-0.5 font-medium">
        <AlertTriangle className="w-3 h-3" />
        Analysis failed
      </span>
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