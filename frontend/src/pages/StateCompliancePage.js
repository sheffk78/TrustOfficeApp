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
import {
  MapPin, AlertTriangle, Shield, CheckCircle2, Clock,
  FileText, ChevronRight, BookOpen, Scale, Gavel
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

function DeadlineRow({ label, lastSent, nextDue, onMarkSent }) {
  const overdue = nextDue && new Date(nextDue) < new Date();
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-neutral-600">{label}</span>
      <div className="text-right">
        {nextDue ? (
          <span className={overdue ? 'text-red-600 font-medium' : 'text-navy'}>
            {overdue ? 'Overdue: ' : 'Due: '}{new Date(nextDue).toLocaleDateString()}
          </span>
        ) : (
          <span className="text-neutral-400">Not scheduled</span>
        )}
        {lastSent && (
          <p className="text-xs text-neutral-400">Last: {new Date(lastSent).toLocaleDateString()}</p>
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

  useEffect(() => {
    if (selectedTrust) loadData();
  }, [selectedTrust]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [complianceRes, reqRes] = await Promise.all([
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/state-compliance`),
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}/state-compliance/requirements`),
      ]);
      const cData = await complianceRes.json();
      if (!complianceRes.ok) throw new Error(cData.detail || 'Failed to load');
      setStateData(cData);

      const rData = await reqRes.json();
      if (reqRes.ok) setRequirements(rData.requirements || []);
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

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <div className="md:pl-64 pb-20 md:pb-0">
          <div className="pt-16 md:pt-8 ml-4 mr-4">
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded">
              <MapPin className="w-12 h-12 text-slate-400 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-neutral-600">Choose a trust to view state compliance requirements.</p>
            </div>
          </div>
        </div>
        <MobileBottomNav />
      </div>
    );
  }

  const profile = stateData?.profile;
  const compliance = stateData?.compliance;

  return (
    <div className="min-h-screen bg-subtle-bg">
      <Sidebar />
      <div className="md:pl-64 pb-20 md:pb-0">
        <div className="pt-16 md:pt-8 ml-4 mr-4">

          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">State Compliance</h1>
              <p className="page-subtitle">Review state-specific trust requirements — UTC adoption status, fiduciary standards, and beneficiary notification rules</p>
            </div>
            <div className="flex items-center gap-2">
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
              {[1,2,3].map(i => <div key={i} className="h-24 bg-white border border-neutral-200 rounded animate-pulse"/>)}
            </div>
          ) : stateData?.state_code === null ? (
            <Card className="border border-neutral-200">
              <CardContent className="p-12 flex flex-col items-center text-center">
                <MapPin className="w-12 h-12 text-slate-300 mb-3"/>
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
                <Card className="border border-neutral-200">
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3 mb-2">
                      <MapPin className="w-5 h-5 text-navy"/>
                      <p className="text-xs font-mono uppercase tracking-wider text-neutral-500">State</p>
                    </div>
                    <p className="text-xl font-bold text-navy">{profile?.state_name || stateData.state_code}</p>
                  </CardContent>
                </Card>

                <Card className="border border-neutral-200">
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3 mb-2">
                      <BookOpen className="w-5 h-5 text-navy"/>
                      <p className="text-xs font-mono uppercase tracking-wider text-neutral-500">UTC Adoption</p>
                    </div>
                    <p className="text-xl font-bold text-navy">
                      {profile?.utc_adopted === 'full' ? 'Full' : profile?.utc_adopted === 'partial' ? 'Partial' : 'Not Adopted'}
                    </p>
                    {profile?.utc_adoption_date && (
                      <p className="text-xs text-neutral-500 mt-1">As of {profile.utc_adoption_date}</p>
                    )}
                    <div className="mt-1">
                      <InfoTooltip text="The Uniform Trust Code is a model law that standardizes trust rules. States that adopt it give trustees clearer guidelines and more predictable outcomes." />
                    </div>
                  </CardContent>
                </Card>

                <Card className="border border-neutral-200">
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3 mb-2">
                      <Gavel className="w-5 h-5 text-navy"/>
                      <p className="text-xs font-mono uppercase tracking-wider text-neutral-500">Trustee Removal</p>
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
                  <Card className="border border-neutral-200">
                    <CardContent className="p-5">
                      <div className="flex items-center justify-between mb-3">
                        <p className="text-xs font-mono uppercase tracking-wider text-neutral-500">Compliance Score</p>
                        <span className={`text-2xl font-bold ${compliance.compliance_score >= 80 ? 'text-emerald-600' : compliance.compliance_score >= 50 ? 'text-warning' : 'text-red-600'}`}>
                          {compliance.compliance_score}
                        </span>
                      </div>
                      {compliance.alert_active && (
                        <div className="flex items-center gap-2 text-sm text-red-600">
                          <AlertTriangle className="w-4 h-4" />
                          {compliance.alert_reason || 'Compliance alert active'}
                        </div>
                      )}
                      {!compliance.alert_active && (
                        <p className="text-sm text-neutral-500">
                          {compliance.compliance_score >= 80 ? 'On track' : compliance.compliance_score >= 50 ? 'Needs attention' : 'Critical, take action'}
                        </p>
                      )}
                    </CardContent>
                  </Card>

                  {/* Deadline Tracking Card */}
                  <Card className="border border-neutral-200">
                    <CardContent className="p-5 space-y-2">
                      <p className="text-xs font-mono uppercase tracking-wider text-neutral-500 mb-2">Deadline Tracking</p>
                      <DeadlineRow label="Beneficiary Notice" lastSent={compliance.notice_last_sent} nextDue={compliance.notice_next_due} onMarkSent={markNoticeSent} />
                      <DeadlineRow label="Accounting" lastSent={compliance.accounting_last_sent} nextDue={compliance.accounting_next_due} onMarkSent={markAccountingSent} />
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Requirements List */}
              <Card className="border border-neutral-200">
                <CardHeader>
                  <CardTitle className="font-serif text-lg text-navy flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-gold"/>
                    Actionable Requirements
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-6 pt-0">
                  {requirements.length === 0 ? (
                    <div className="flex items-center gap-3 p-4 bg-emerald-50 border border-emerald-100 rounded">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600"/>
                      <p className="text-sm text-emerald-800">All compliance requirements are satisfied for {profile?.state_name}.</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {requirements.map((req, i) => {
                        const Icon = CATEGORY_ICONS[req.category] || Shield;
                        return (
                          <div key={i} className="flex gap-4 p-4 bg-white border border-neutral-200 rounded">
                            <div className={`w-10 h-10 flex items-center justify-center flex-shrink-0 rounded ${
                              req.severity === 'high' ? 'bg-red-100 text-red-600' :
                              req.severity === 'medium' ? 'bg-warning/10 text-warning' :
                              'bg-slate-100 text-slate-500'
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
                                <p className="text-xs text-neutral-400 italic mb-1">{CATEGORY_PLAIN_ENGLISH[req.category]}</p>
                              )}
                              <p className="text-sm text-neutral-600 mb-2">{req.description}</p>
                              <p className="text-xs text-neutral-500 flex items-center gap-1">
                                <ChevronRight className="w-3 h-3"/>
                                {req.action}
                              </p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}
