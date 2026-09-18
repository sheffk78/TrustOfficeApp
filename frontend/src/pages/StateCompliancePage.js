import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import InfoTooltip from '@/components/InfoTooltip';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  MapPin, AlertTriangle, Shield, CheckCircle2, Clock,
  FileText, ChevronRight, BookOpen, Scale, Gavel, Send, Download,
  ChevronDown, ChevronUp, HelpCircle
} from 'lucide-react';

import { SEVERITY_STYLES_FLAT as SEVERITY_STYLES } from '@/utils/severityStyles';

const CATEGORY_ICONS = {
  utc_gap: Scale,
  utc_partial: Scale,
  notice: FileText,
  accounting: Clock,
  spendthrift: Shield,
};

const JARGON_TOOLTIPS = {
  utc_gap: 'The Uniform Trust Code is a model law that standardizes trust rules. States that adopt it give trustees clearer guidelines and more predictable outcomes.',
  utc_partial: 'The Uniform Trust Code is a model law that standardizes trust rules. States that adopt it give trustees clearer guidelines and more predictable outcomes.',
  notice: 'Most states require trustees to notify beneficiaries at least annually about trust status, assets, and administration. Some states require more frequent updates.',
  accounting: 'An accounting is a formal financial report to beneficiaries showing income, expenses, distributions, and remaining assets. Some states require it annually, others only on demand.',
  spendthrift: 'A spendthrift clause prevents beneficiaries\' creditors from reaching trust assets before they\'re distributed.',
};

const CATEGORY_PLAIN_ENGLISH = {
  utc_gap: 'Your state uses older trust laws instead of the modern Uniform Trust Code',
  utc_partial: 'Your state partially adopted the Uniform Trust Code',
  notice: 'Your state requires you to keep beneficiaries informed on a schedule',
  accounting: 'Your state requires you to send regular financial reports to beneficiaries',
  spendthrift: 'Your state does not automatically protect trust assets from creditors',
};

// Deterministic mapper: requirement topic -> deep guide section heading.
// Priority order mirrors the section hierarchy in the state guides.
export function getSectionForRequirement(req) {
  const title = (req.title || '').toLowerCase();
  const description = (req.description || '').toLowerCase();
  const combined = `${title} ${description}`;

  if (/\b(court|removal|judge|judicial|supervision)\b/.test(combined)) {
    return 'Court Supervision';
  }
  if (/\bnotice\b/.test(combined)) {
    return 'Beneficiary Notice Requirements';
  }
  if (/\bincome tax\b/.test(combined)) {
    return 'State Income Tax on Trusts';
  }
  if (/\bfil(e|ing)s?\b|\breturns?\b/.test(combined)) {
    return 'Filing Requirements';
  }
  if (/\btaxes\b|\btax\b/.test(combined)) {
    return 'State Income Tax on Trusts';
  }
  return 'Key State-Specific Rules';
}

// Extract the markdown content of a ## section from a full guide markdown.
// Case-insensitive heading match; returns null when the heading is absent
// (caller falls back to showing the whole guide).
export function extractSectionFromMarkdown(markdown, sectionHeading) {
  if (!markdown || !sectionHeading) return null;
  const lines = markdown.split('\n');
  const target = String(sectionHeading).trim().toLowerCase();
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (start === -1) {
      // Heading line: '## <title>' — compare case-insensitively.
      if (/^##\s+/.test(trimmed) && trimmed.replace(/^##\s+/, '').trim().toLowerCase() === target) {
        start = i;
      }
    } else if (/^##\s+/.test(trimmed)) {
      // Next ## heading ends the section.
      return lines.slice(start + 1, i).join('\n').trim() || null;
    }
  }
  if (start !== -1) {
    return lines.slice(start + 1).join('\n').trim() || null;
  }
  return null;
}

function DeadlineRow({ label, lastSent, nextDue, onMarkSent }) {
  const overdue = nextDue && new Date(nextDue) < new Date();
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <div className="text-right">
        {nextDue ? (
          <span className={overdue ? 'text-destructive font-medium' : 'text-navy'}>
            {overdue ? 'Overdue: ' : 'Due: '}{new Date(nextDue).toLocaleDateString()}
          </span>
        ) : (
          <span className="text-muted-foreground/70">Not scheduled</span>
        )}
        {lastSent && (
          <p className="text-xs text-muted-foreground/70">Last: {new Date(lastSent).toLocaleDateString()}</p>
        )}
        <button onClick={onMarkSent} className="text-xs text-gold hover:underline ml-2">Mark as sent</button>
      </div>
    </div>
  );
}

export default function StateCompliancePage() {
  const { selectedTrust } = useAuth();
  const [loading, setLoading] = useState(true);
  const [stateData, setStateData] = useState(null);
  const [requirements, setRequirements] = useState([]);
  const [coverage, setCoverage] = useState('covered');
  const [deepGuide, setDeepGuide] = useState(null);
  const [guideExpanded, setGuideExpanded] = useState(false);
  const [guideMarkdown, setGuideMarkdown] = useState(null);
  // Per-requirement guidance: tracks which requirement row is expanded
  // and caches the extracted section markdown for that row.
  const [guidanceExpanded, setGuidanceExpanded] = useState(null);
  const [guidanceSectionContent, setGuidanceSectionContent] = useState(null);
  const [guidanceWholeGuide, setGuidanceWholeGuide] = useState(null);
  const [guidanceLoading, setGuidanceLoading] = useState(false);

  useEffect(() => {
    if (selectedTrust) loadData();
  }, [selectedTrust]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [complianceRes, reqRes, deepRes] = await Promise.all([
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/state-compliance`),
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/state-compliance/requirements`),
        fetchWithAuth('/state-compliance/deep-knowledge'),
      ]);
      const cData = await complianceRes.json();
      if (!complianceRes.ok) throw new Error(cData.detail || 'Failed to load');
      setStateData(cData);

      const rData = await reqRes.json();
      if (reqRes.ok) {
        setRequirements(rData.requirements || []);
        setCoverage(rData.coverage || 'covered');
      } else {
        setRequirements([]);
        setCoverage('uncovered');
      }

      // Deep-dive guide for the trust's state (optional — render nothing when
      // the API has no entry for this state_code).
      const dData = await deepRes.json();
      const trustState = (cData?.state_code || selectedTrust.state_code || '').toUpperCase();
      const entry = Array.isArray(dData)
        ? dData.find((g) => g.state_code === trustState)
        : null;
      setDeepGuide(entry || null);
      setGuideExpanded(false);
      setGuideMarkdown(null);
      // Reset per-requirement guidance when data reloads.
      setGuidanceExpanded(null);
      setGuidanceSectionContent(null);
      setGuidanceWholeGuide(null);
    } catch (e) {
      showError(toast, e, { operation: 'load_state_compliance', page: 'StateCompliance' });
    } finally {
      setLoading(false);
    }
  };

  const markNoticeSent = async () => {
    try {
      await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/state-compliance`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notice_last_sent: new Date().toISOString() }),
      });
      toast.success('Beneficiary notice marked as sent');
      loadData();
    } catch (e) {
      showError(toast, e, { operation: 'mark_notice_sent', page: 'StateCompliance' });
    }
  };

  const markAccountingSent = async () => {
    try {
      await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/state-compliance`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accounting_last_sent: new Date().toISOString() }),
      });
      toast.success('Accounting marked as sent');
      loadData();
    } catch (e) {
      showError(toast, e, { operation: 'mark_accounting_sent', page: 'StateCompliance' });
    }
  };

  // Toggle per-requirement state guidance: fetch the deep guide for the
  // trust's state (if not already loaded), extract the relevant section,
  // and expand it inline below the requirement row.
  const toggleGuidance = async (req, index) => {
    if (guidanceExpanded === index) {
      setGuidanceExpanded(null);
      setGuidanceSectionContent(null);
      setGuidanceWholeGuide(null);
      return;
    }
    setGuidanceExpanded(index);
    setGuidanceSectionContent(null);
    setGuidanceWholeGuide(null);

    // Ensure the deep guide markdown is loaded for this state.
    let md = guideMarkdown;
    if (!md && deepGuide) {
      setGuidanceLoading(true);
      try {
        const res = await fetchWithAuth(`/state-compliance/deep-knowledge/${deepGuide.state_code}`);
        const data = await res.json();
        if (res.ok) {
          md = data.markdown || '';
          setGuideMarkdown(md);
        }
      } catch {
        md = '';
      } finally {
        setGuidanceLoading(false);
      }
    }

    const section = getSectionForRequirement(req);
    const sectionContent = extractSectionFromMarkdown(md || '', section);
    setGuidanceSectionContent(sectionContent);
    // Graceful fallback: when the state's guide lacks the mapped section
    // heading, show the whole guide instead of an empty panel.
    setGuidanceWholeGuide(sectionContent ? null : (md || ''));
  };

  // Helper: trustee name(s) from the selected trust (array or comma string).
  const getTrusteeNames = () => {
    const raw = selectedTrust?.trustees;
    if (Array.isArray(raw)) return raw.filter(Boolean).join(', ');
    if (typeof raw === 'string' && raw.trim()) return raw.trim();
    return '';
  };

  const todayIso = () => new Date().toISOString().slice(0, 10);

  // Act 1: generate the state-required periodic beneficiary notice (creates the
  // doc, downloads the PDF; the backend records notice_last_sent/next_due).
  const [generatingNotice, setGeneratingNotice] = useState(false);
  const [noticeResult, setNoticeResult] = useState(null);
  const generateBeneficiaryNotice = async () => {
    setGeneratingNotice(true);
    setNoticeResult(null);
    try {
      const res = await fetchWithAuth('/minutes-templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          template_type: 'beneficiary_periodic_notice',
          template_data: {
            notice_date: todayIso(),
            trustee_name: getTrusteeNames(),
          },
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to generate notice');
      setNoticeResult({ minutesId: data.minutes_id, pdfReady: false });
      toast.success('Beneficiary notice generated — notice recorded as sent');
      loadData();
    } catch (e) {
      showError(toast, e, { operation: 'generate_beneficiary_notice', page: 'StateCompliance' });
    } finally {
      setGeneratingNotice(false);
    }
  };

  const downloadNoticePdf = async () => {
    if (!noticeResult?.minutesId) return;
    try {
      const response = await fetchWithAuth(`/minutes-templates/${noticeResult.minutesId}/pdf`);
      if (response.ok) {
        const data = await response.json();
        const link = document.createElement('a');
        link.href = `data:application/pdf;base64,${data.pdf_base64}`;
        link.download = data.filename || 'beneficiary_periodic_notice.pdf';
        link.click();
        setNoticeResult((prev) => ({ ...prev, pdfReady: true }));
        toast.success('Notice PDF downloaded');
      } else {
        showError(toast, new Error('Failed to download notice PDF'), { operation: 'download_notice_pdf', page: 'StateCompliance' });
      }
    } catch (e) {
      showError(toast, e, { operation: 'download_notice_pdf', page: 'StateCompliance' });
    }
  };

  // Act 2: generate the annual accounting report (creates the PDF; the backend
  // records accounting_last_sent/accounting_next_due).
  const [generatingAccounting, setGeneratingAccounting] = useState(false);
  const [accountingResult, setAccountingResult] = useState(null);

  // Delivery log: derived from the state-compliance record the page already
  // loads (compliance.documents_log); refetched via loadData() after actions.
  const deliveryLog = stateData?.compliance?.documents_log || [];

  const markDocumentSent = async (docId) => {
    try {
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/state-compliance/documents-log`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId, action: 'mark_sent' }),
      });
      if (res.ok) {
        await loadData();
        toast.success('Marked as sent');
      }
    } catch {
      toast.error('Failed to update delivery status');
    }
  };

  const markDocumentDelivered = async (docId) => {
    try {
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/state-compliance/documents-log`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId, action: 'mark_delivered' }),
      });
      if (res.ok) {
        await loadData();
        toast.success('Marked as delivered');
      }
    } catch {
      toast.error('Failed to update delivery status');
    }
  };
  const generateAnnualAccounting = async () => {
    setGeneratingAccounting(true);
    setAccountingResult(null);
    try {
      const res = await fetchWithAuth(`/beneficiary-reports/${selectedTrust.trust_id}/generate`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to generate accounting');
      setAccountingResult({
        reportId: data.report_id || data.doc_id,
        downloadUrl: `/beneficiary-reports/${selectedTrust.trust_id}/${data.report_id || data.doc_id}/download`,
      });
      toast.success('Annual accounting generated — accounting recorded as sent');
      loadData();
    } catch (e) {
      showError(toast, e, { operation: 'generate_annual_accounting', page: 'StateCompliance' });
    } finally {
      setGeneratingAccounting(false);
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content mobile-layout-offset">
          <div className="page-container">
            <div className="card-trust border border-border p-12 flex flex-col items-center justify-center rounded">
              <MapPin className="w-12 h-12 text-muted-foreground/60 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to view state compliance requirements.</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  const profile = stateData?.profile;
  const compliance = stateData?.compliance;

  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content mobile-layout-offset">
        <div className="page-container">

          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">State Compliance</h1>
              <p className="page-subtitle">Review state-specific trust requirements — UTC adoption status, fiduciary standards, and beneficiary notification rules</p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'Review state-specific trust requirements for your jurisdiction' },
                  { text: 'Check UTC adoption status, fiduciary standards, and notification rules' },
                  { text: 'Ensure your trust administration complies with local law' },
                ]}
                taPrompt="Walk me through the State Compliance page for my state"
                contextAlerts={compliance?.alert_active ? [
                  { text: compliance.alert_reason || 'Compliance alert active', prompt: `My state compliance alert says: ${compliance.alert_reason}. What should I do?` }
                ] : []}
              />
              <Link to="/settings">
                <Button variant="outline">Edit Trust Profile</Button>
              </Link>
            </div>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-24 card-trust border border-border rounded animate-pulse"/>)}
            </div>
          ) : !stateData?.state_code ? (
            <Card className="border border-border">
              <CardContent className="p-12 flex flex-col items-center text-center">
                <MapPin className="w-12 h-12 text-muted-foreground/50 mb-3"/>
                <h2 className="font-serif text-xl text-navy mb-2">No state set</h2>
                <p className="text-sm text-muted-foreground mb-4 max-w-md">
                  Set your trust's state jurisdiction to see compliance requirements like UTC adoption, notice rules, and accounting frequency.
                </p>
                <Link to="/settings">
                  <Button>Set Trust State</Button>
                </Link>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-6">
              {/* State Summary Card */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="border border-border">
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3 mb-2">
                      <MapPin className="w-5 h-5 text-navy"/>
                      <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">State</p>
                    </div>
                    <p className="text-xl font-bold text-navy">{profile?.state_name || stateData?.state_code}</p>
                  </CardContent>
                </Card>

                <Card className="border border-border">
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3 mb-2">
                      <BookOpen className="w-5 h-5 text-navy"/>
                      <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">UTC Adoption</p>
                    </div>
                    <p className="text-xl font-bold text-navy">
                      {profile?.utc_adopted === 'full' ? 'Full' : profile?.utc_adopted === 'partial' ? 'Partial' : 'Not Adopted'}
                    </p>
                    {profile?.utc_adoption_date && (
                      <p className="text-xs text-muted-foreground mt-1">As of {profile.utc_adoption_date}</p>
                    )}
                    <div className="mt-1">
                      <InfoTooltip text="The Uniform Trust Code is a model law that standardizes trust rules. States that adopt it give trustees clearer guidelines and more predictable outcomes." />
                    </div>
                  </CardContent>
                </Card>

                <Card className="border border-border">
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3 mb-2">
                      <Gavel className="w-5 h-5 text-navy"/>
                      <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Trustee Removal</p>
                    </div>
                    <p className="text-sm font-medium text-navy capitalize">{profile?.trustee_removal_standard}</p>
                    <div className="mt-1">
                      <InfoTooltip text="The legal standard required to remove a trustee. 'Breach of trust' is harder to prove than 'reasonable grounds.'" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Compliance Status Cards */}
              {compliance && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Compliance Score Card */}
                  <Card className="border border-border">
                    <CardContent className="p-5">
                      <div className="flex items-center justify-between mb-3">
                        <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Compliance Score</p>
                        <span className={`text-2xl font-bold ${compliance.compliance_score >= 80 ? 'text-success' : compliance.compliance_score >= 50 ? 'text-warning' : 'text-destructive'}`}>
                          {compliance.compliance_score}
                        </span>
                      </div>
                      {compliance.alert_active && (
                        <div className="flex items-center gap-2 text-sm text-destructive">
                          <AlertTriangle className="w-4 h-4" />
                          {compliance.alert_reason || 'Compliance alert active'}
                        </div>
                      )}
                      {!compliance.alert_active && (
                        <p className="text-sm text-muted-foreground">
                          {compliance.compliance_score >= 80 ? 'On track' : compliance.compliance_score >= 50 ? 'Needs attention' : 'Critical, take action'}
                        </p>
                      )}
                    </CardContent>
                  </Card>

                  {/* Deadline Tracking Card */}
                  <Card className="border border-border">
                    <CardContent className="p-5 space-y-2">
                      <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground mb-2">Deadline Tracking</p>
                      <DeadlineRow label="Beneficiary Notice" lastSent={compliance.notice_last_sent} nextDue={compliance.notice_next_due} onMarkSent={markNoticeSent} />
                      <DeadlineRow label="Accounting" lastSent={compliance.accounting_last_sent} nextDue={compliance.accounting_next_due} onMarkSent={markAccountingSent} />

                      {/* Do-the-act actions */}
                      <div className="pt-3 mt-3 border-t border-border space-y-2">
                        <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Take Action</p>
                        <div className="grid grid-cols-1 gap-2">
                          <Button
                            onClick={generateBeneficiaryNotice}
                            disabled={generatingNotice}
                            className="w-full justify-start gap-2"
                            variant="outline"
                          >
                            <Send className="w-4 h-4 text-gold" />
                            {generatingNotice ? 'Generating…' : 'Generate Beneficiary Notice'}
                          </Button>
                          {noticeResult?.minutesId && (
                            <div className="flex items-center justify-between gap-2 p-2 bg-success/5 border border-success/20 rounded">
                              <span className="text-xs text-success flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3" />
                                Notice recorded — last sent updated
                              </span>
                              <button onClick={downloadNoticePdf} className="text-xs text-gold hover:underline flex items-center gap-1">
                                <Download className="w-3 h-3" />
                                Download PDF
                              </button>
                            </div>
                          )}
                          <Button
                            onClick={generateAnnualAccounting}
                            disabled={generatingAccounting}
                            className="w-full justify-start gap-2"
                            variant="outline"
                          >
                            <FileText className="w-4 h-4 text-gold" />
                            {generatingAccounting ? 'Generating…' : 'Generate Annual Accounting'}
                          </Button>
                          {accountingResult?.downloadUrl && (
                            <div className="flex items-center justify-between gap-2 p-2 bg-success/5 border border-success/20 rounded">
                              <span className="text-xs text-success flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3" />
                                Accounting recorded — last sent updated
                              </span>
                              <a href={accountingResult.downloadUrl} className="text-xs text-gold hover:underline flex items-center gap-1" download>
                                <Download className="w-3 h-3" />
                                Download PDF
                              </a>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Delivery Log */}
                      <div className="pt-3 mt-3 border-t border-border space-y-2">
                        <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                          Delivery Log
                          <InfoTooltip text="Track generated notices and accounting documents through delivery: Generated → Sent → Delivered." />
                        </p>
                        {deliveryLog.length === 0 && (
                          <p className="text-xs text-muted-foreground">No documents logged yet. Generate a notice or accounting to start tracking.</p>
                        )}
                        {deliveryLog.map((entry) => (
                          <div key={entry.doc_id} className="flex items-center justify-between gap-2 p-2 bg-muted/30 border border-border rounded text-xs">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="font-medium text-navy truncate">{entry.kind === 'accounting' ? 'Annual Accounting' : 'Beneficiary Notice'}</span>
                              <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${entry.delivered_at ? 'bg-success' : entry.sent_at ? 'bg-gold' : 'bg-muted-foreground/40'}`} />
                            </div>
                            <div className="flex items-center gap-1 flex-shrink-0">
                              {!entry.sent_at && (
                                <button onClick={() => markDocumentSent(entry.doc_id)} className="text-gold hover:underline whitespace-nowrap">Mark sent</button>
                              )}
                              {!entry.delivered_at && entry.sent_at && (
                                <button onClick={() => markDocumentDelivered(entry.doc_id)} className="text-gold hover:underline whitespace-nowrap">Mark delivered</button>
                              )}
                              {entry.delivered_at && (
                                <span className="text-success whitespace-nowrap">Delivered</span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Requirements List */}
              <Card className="border border-border">
                <CardHeader>
                  <CardTitle className="font-serif text-lg text-navy flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-gold"/>
                    Actionable Requirements
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-6 pt-0">
                  {requirements.length === 0 ? (
                    coverage === 'uncovered' ? (
                      <div className="flex items-center gap-3 p-4 bg-info/5 border border-info/20 rounded">
                        <InfoTooltip text="The Uniform Trust Code is a model law that standardizes trust rules." />
                        <p className="text-sm text-info">
                          We don't have {profile?.state_name || stateData?.state_code} requirements in our library yet.
                          General fiduciary duties still apply — see the Risk Dashboard for guidance.
                        </p>
                      </div>
                    ) : (
                      <div className="flex items-center gap-3 p-4 bg-success/5 border border-success/20 rounded">
                        <CheckCircle2 className="w-5 h-5 text-success"/>
                        <p className="text-sm text-success">All compliance requirements are satisfied for {profile?.state_name}.</p>
                      </div>
                    )
                  ) : (
                    <div className="space-y-4">
                      {requirements.map((req, i) => {
                        const Icon = CATEGORY_ICONS[req.category] || Shield;
                        return (
                          <div key={i}>
                            <div className="flex gap-4 p-4 card-trust border border-border rounded">
                            <div className={`w-10 h-10 flex items-center justify-center flex-shrink-0 rounded ${
                              req.severity === 'high' ? 'bg-destructive/10 text-destructive' :
                              req.severity === 'medium' ? 'bg-warning/10 text-warning' :
                              'bg-subtle-bg text-muted-foreground'
                            }`}>
                              <Icon className="w-5 h-5"/>
                            </div>
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <h3 className="font-semibold text-navy text-sm">{req.title}</h3>
                                {JARGON_TOOLTIPS[req.category] && (
                                  <InfoTooltip text={JARGON_TOOLTIPS[req.category]} />
                                )}
                                <span className={`font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${SEVERITY_STYLES[req.severity]}`}>
                                  {req.severity}
                                </span>
                              </div>
                              {CATEGORY_PLAIN_ENGLISH[req.category] && (
                                <p className="text-xs text-muted-foreground/70 italic mb-1">{CATEGORY_PLAIN_ENGLISH[req.category]}</p>
                              )}
                              <p className="text-sm text-muted-foreground mb-2">{req.description}</p>
                              <p className="text-xs text-muted-foreground flex items-center gap-1">
                                <ChevronRight className="w-3 h-3"/>
                                {req.action}
                              </p>
                              {deepGuide && (
                                <button
                                  onClick={() => toggleGuidance(req, i)}
                                  className="mt-2 text-xs text-gold hover:underline flex items-center gap-1"
                                  data-testid={`guidance-toggle-${i}`}
                                  aria-expanded={guidanceExpanded === i}
                                >
                                  <HelpCircle className="w-3 h-3"/>
                                  {guidanceExpanded === i ? 'Hide state guidance' : 'State guidance'}
                                </button>
                              )}
                            </div>
                          </div>
                          {guidanceExpanded === i && (
                            <div className="mt-2 ml-14 p-4 border border-border rounded bg-subtle-bg" data-testid={`guidance-section-${i}`}>
                              {guidanceLoading && (
                                <p className="text-xs text-muted-foreground">Loading guidance…</p>
                              )}
                              {!guidanceLoading && guidanceSectionContent && (
                                <div>
                                  <div className="prose prose-navy max-w-none text-sm">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                      {guidanceSectionContent}
                                    </ReactMarkdown>
                                  </div>
                                  <button
                                    onClick={() => { setGuideExpanded(true); setGuidanceExpanded(null); }}
                                    className="text-gold hover:underline text-xs mt-2"
                                    data-testid={`guidance-full-guide-${i}`}
                                  >
                                    Read full guide
                                  </button>
                                </div>
                              )}
                              {!guidanceLoading && !guidanceSectionContent && (
                                <div>
                                  <p className="text-xs text-muted-foreground mb-2">
                                    Exact section not found in this state's guide — showing the full guide:
                                  </p>
                                  <div className="prose prose-navy max-w-none text-sm">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                      {guidanceWholeGuide || ''}
                                    </ReactMarkdown>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Deep Dive — per-state trust compliance guide (rendered only
                  when a knowledge file exists for the trust's state) */}
              {deepGuide && (
                <Card className="border border-border" data-testid="deep-dive-card">
                  <CardHeader>
                    <CardTitle className="font-serif text-lg text-navy flex items-center gap-2">
                      <BookOpen className="w-5 h-5 text-gold"/>
                      Deep Dive — {deepGuide.state_name} Trust Compliance
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-6 pt-0">
                    {!guideExpanded && (
                      <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
                        {deepGuide.summary}
                      </p>
                    )}
                    {guideExpanded && (
                      <div className="p-6 md:p-8 prose prose-navy max-w-none border border-border rounded mb-4">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {guideMarkdown ?? deepGuide.markdown ?? ''}
                        </ReactMarkdown>
                      </div>
                    )}
                    <button
                      onClick={async () => {
                        const next = !guideExpanded;
                        setGuideExpanded(next);
                        // Full markdown lives on the detail endpoint, not the
                        // list entry — fetch it the first time the guide is
                        // expanded (deep-dive contract: list = summaries).
                        if (next && !guideMarkdown) {
                          try {
                            const res = await fetchWithAuth(`/state-compliance/deep-knowledge/${deepGuide.state_code}`);
                            const data = await res.json();
                            if (res.ok) setGuideMarkdown(data.markdown || '');
                            else setGuideMarkdown('');
                          } catch {
                            setGuideMarkdown('');
                          }
                        }
                      }}
                      className="text-xs text-gold hover:underline flex items-center gap-1"
                      data-testid="deep-dive-toggle"
                      aria-expanded={guideExpanded}
                    >
                      {guideExpanded ? <ChevronUp className="w-3 h-3"/> : <ChevronDown className="w-3 h-3"/>}
                      {guideExpanded ? 'Show less' : 'Read the full guide'}
                    </button>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}