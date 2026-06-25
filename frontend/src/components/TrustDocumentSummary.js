import { useState, useEffect } from 'react';
import { fetchWithAuth } from '@/utils/api';
import { useAuth } from '@/context/AuthContext';
import {
  FileText, Shield, Users, Calendar, BookOpen,
  AlertTriangle, CheckCircle2, Loader2, RefreshCw,
  ChevronDown, ChevronUp, Gavel, XCircle
} from 'lucide-react';
import { toast } from 'sonner';

export default function TrustDocumentSummary({ trustId }) {
  const { selectedTrust } = useAuth();
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const tid = trustId || selectedTrust?.trust_id;

  useEffect(() => {
    if (tid) loadAnalysis();
  }, [tid]);

  const loadAnalysis = async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/trusts/${tid}/document-analysis`);
      if (res.ok) {
        const data = await res.json();
        setAnalysis(data);
      }
    } catch (e) {
      // Silent fail — component shows empty state
    } finally {
      setLoading(false);
    }
  };

  const handleReanalyze = async () => {
    setReanalyzing(true);
    try {
      const res = await fetchWithAuth(`/trusts/${tid}/document-analysis/reanalyze`, {
        method: 'POST',
      });
      if (res.ok) {
        toast.success('Re-analysis started. This takes about 10 seconds.');
        // Poll for completion
        setTimeout(() => loadAnalysis(), 5000);
        setTimeout(() => loadAnalysis(), 15000);
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to start re-analysis');
      }
    } catch (e) {
      toast.error('Failed to start re-analysis');
    } finally {
      setReanalyzing(false);
    }
  };

  if (loading) {
    return (
      <div className="card-trust p-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">Checking trust document analysis...</span>
        </div>
      </div>
    );
  }

  // No analysis and no document uploaded
  if (analysis?.status === 'none') {
    return (
      <div className="card-trust p-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 bg-navy/5 flex items-center justify-center flex-shrink-0">
            <FileText className="w-5 h-5 text-navy/40" />
          </div>
          <div>
            <p className="label-trust mb-1">Trust Document Intelligence</p>
            <p className="text-sm text-muted-foreground">
              Upload your trust document to the Vault and TrustOffice will automatically extract
              key provisions — distribution standards, trustee powers, removal procedures, and more.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Analysis in progress
  if (analysis?.status === 'pending' || analysis?.status === 'analyzing') {
    return (
      <div className="card-trust p-6">
        <div className="flex items-center gap-3">
          <Loader2 className="w-5 h-5 text-gold animate-spin" />
          <div>
            <p className="label-trust mb-1">Trust Document Analysis</p>
            <p className="text-sm text-muted-foreground">
              Analyzing your trust document — extracting key provisions. This takes about 10 seconds.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Analysis failed
  if (analysis?.status === 'failed') {
    return (
      <div className="card-trust p-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 bg-error/10 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-5 h-5 text-error" />
          </div>
          <div className="flex-1">
            <p className="label-trust mb-1">Trust Document Analysis</p>
            <p className="text-sm text-muted-foreground mb-2">
              {analysis.error_message || 'Analysis failed. You can retry or re-upload your document.'}
            </p>
            <button
              onClick={handleReanalyze}
              disabled={reanalyzing}
              className="text-xs font-mono uppercase tracking-widest text-navy hover:text-gold flex items-center gap-1"
            >
              {reanalyzing ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
              Retry Analysis
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Analysis complete — show extracted fields
  const fields = analysis?.extracted_fields || {};
  const distStd = fields.distribution_standard || {};
  const powers = fields.trustee_powers || [];
  const removal = fields.removal_provisions || {};
  const termination = fields.termination_rules || {};
  const beneficiaries = fields.beneficiary_names || [];
  const trustees = fields.trustee_names || [];

  return (
    <div className="card-trust corner-mark p-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 bg-gold/10 flex items-center justify-center flex-shrink-0">
            <FileText className="w-5 h-5 text-gold" />
          </div>
          <div>
            <p className="label-trust mb-1">Trust Document Intelligence</p>
            <p className="text-xs text-muted-foreground">
              Automatically extracted from your trust document
            </p>
          </div>
        </div>
        <button
          onClick={handleReanalyze}
          disabled={reanalyzing}
          className="text-xs font-mono uppercase tracking-widest text-navy hover:text-gold flex items-center gap-1"
        >
          {reanalyzing ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          Re-analyze
        </button>
      </div>

      {/* Key Fields Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {/* Trust Type */}
        <div className="flex items-start gap-2">
          <Shield className="w-4 h-4 text-navy/40 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest">Trust Type</p>
            <p className="text-sm text-navy capitalize">{fields.trust_type || 'Not found'}</p>
          </div>
        </div>

        {/* Grantor */}
        <div className="flex items-start gap-2">
          <Users className="w-4 h-4 text-navy/40 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest">Grantor</p>
            <p className="text-sm text-navy">{fields.grantor_name || 'Not found'}</p>
          </div>
        </div>

        {/* Formation Date */}
        <div className="flex items-start gap-2">
          <Calendar className="w-4 h-4 text-navy/40 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest">Formation Date</p>
            <p className="text-sm text-navy">{fields.formation_date || 'Not found'}</p>
          </div>
        </div>

        {/* Trustees */}
        <div className="flex items-start gap-2">
          <Users className="w-4 h-4 text-navy/40 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest">Trustee(s)</p>
            <p className="text-sm text-navy">
              {trustees.length > 0 ? trustees.join(', ') : 'Not found'}
            </p>
          </div>
        </div>
      </div>

      {/* Distribution Standard — highlighted */}
      <div className="bg-gold/5 border border-gold/20 p-4 mb-4">
        <div className="flex items-start gap-2">
          <BookOpen className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-xs text-gold font-mono uppercase tracking-widest mb-1">
              Distribution Standard
            </p>
            {distStd.exact_language ? (
              <>
                <p className="text-sm text-navy font-medium italic mb-1">
                  "{distStd.exact_language}"
                </p>
                {distStd.article_reference && (
                  <p className="text-xs text-muted-foreground">
                    {distStd.article_reference} · {distStd.type}
                  </p>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Not found in document</p>
            )}
          </div>
        </div>
      </div>

      {/* Trustee Powers */}
      {powers.length > 0 && (
        <div className="mb-4">
          <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest mb-2">
            Trustee Powers
          </p>
          <div className="space-y-1.5">
            {powers.slice(0, 5).map((power, i) => (
              <div key={i} className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0 mt-0.5" />
                <div>
                  <span className="text-sm text-navy">{power.power}</span>
                  {power.article_reference && (
                    <span className="text-xs text-muted-foreground ml-2">({power.article_reference})</span>
                  )}
                </div>
              </div>
            ))}
            {powers.length > 5 && (
              <p className="text-xs text-muted-foreground ml-6">
                +{powers.length - 5} more powers
              </p>
            )}
          </div>
        </div>
      )}

      {/* Collapsible: Removal & Termination */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="flex items-center gap-1 text-xs font-mono uppercase tracking-widest text-navy hover:text-gold"
      >
        {showDetails ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        Removal & Termination Provisions
      </button>

      {showDetails && (
        <div className="mt-3 space-y-4">
          {/* Removal */}
          <div className="flex items-start gap-2">
            <Gavel className="w-4 h-4 text-navy/40 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest mb-1">
                Trustee Removal
              </p>
              <p className="text-sm text-navy">
                {removal.summary || 'Not found in document'}
              </p>
              {removal.article_reference && (
                <p className="text-xs text-muted-foreground mt-0.5">{removal.article_reference}</p>
              )}
            </div>
          </div>

          {/* Termination */}
          <div className="flex items-start gap-2">
            <XCircle className="w-4 h-4 text-navy/40 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest mb-1">
                Trust Termination
              </p>
              <p className="text-sm text-navy">
                {termination.summary || 'Not found in document'}
              </p>
              {termination.article_reference && (
                <p className="text-xs text-muted-foreground mt-0.5">{termination.article_reference}</p>
              )}
            </div>
          </div>

          {/* Beneficiaries found */}
          {beneficiaries.length > 0 && (
            <div className="flex items-start gap-2">
              <Users className="w-4 h-4 text-navy/40 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-xs text-muted-foreground font-mono uppercase tracking-widest mb-1">
                  Beneficiaries Mentioned
                </p>
                <p className="text-sm text-navy">{beneficiaries.join(', ')}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}