import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import PageHelpButton from '@/components/PageHelpButton';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import {
  Shield, AlertTriangle, AlertOctagon, AlertCircle,
  CheckCircle2, ArrowUpRight, Activity
} from 'lucide-react';

import { SEVERITY_STYLES } from '@/utils/severityStyles';
import ComplianceSummaryCard from '@/components/ComplianceSummaryCard';

export default function RiskDashboardPage() {
  const { selectedTrust } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterModule, setFilterModule] = useState('');

  useEffect(() => {
    if (selectedTrust) loadData();
  }, [selectedTrust]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}/risk-dashboard`);
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Failed');
      setData(d);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredRisks = () => {
    if (!data) return [];
    let risks = data.risks || [];
    if (filterSeverity) risks = risks.filter(r => r.severity === filterSeverity);
    if (filterModule) risks = risks.filter(r => r.module === filterModule);
    return risks;
  };

  const getColor = (a) => {
    switch (a) {
      case 'critical': return 'text-red-700';
      case 'elevated': return 'text-warning';
      case 'caution': return 'text-slate-700';
      case 'healthy': return 'text-emerald-700';
      default: return 'text-slate-700';
    }
  };

  const getBg = (a) => {
    switch (a) {
      case 'critical': return 'bg-red-100 border-red-200';
      case 'elevated': return 'bg-warning/10 border-warning/20';
      case 'caution': return 'bg-slate-100 border-slate-200';
      case 'healthy': return 'bg-emerald-100 border-emerald-200';
      default: return 'bg-slate-100 border-slate-200';
    }
  };

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <div className="md:pl-64 pb-20 md:pb-0">
          <div className="pt-16 md:pt-8 ml-4 mr-4">
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded">
              <Shield className="w-12 h-12 text-slate-400 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-neutral-600">Choose a trust to view the Risk Dashboard.</p>
            </div>
          </div>
        </div>
        <MobileBottomNav />
      </div>
    );
  }

  const assessment = data?.assessment || 'healthy';
  const label = data?.assessment_label || 'Low Risk';

  return (
    <div className="min-h-screen bg-subtle-bg">
      <Sidebar />
      <div className="md:pl-64 pb-20 md:pb-0 mobile-layout-offset">
        <div className="pt-16 md:pt-8 ml-4 mr-4">

          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Risk Dashboard</h1>
              <p className="page-subtitle">Monitor trust risks, compliance gaps, and alerts — review flagged items and take corrective action</p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Monitor trust risks, compliance gaps, and alerts across all modules' },
                  { text: 'Review flagged items and take corrective action' },
                  { text: 'Track high, medium, and low risk items by category' },
                ]}
                taPrompt="Walk me through the Risk Dashboard and how to address flagged risks"
                contextAlerts={data?.high_count > 0 ? [
                  { text: `You have ${data.high_count} high-severity risk(s). Want help prioritizing?`, prompt: `I have ${data.high_count} high-severity risks on my Risk Dashboard. Help me prioritize which to address first.` }
                ] : []}
              />
              <Button variant="outline" onClick={loadData} disabled={loading}>
                <Activity className="w-4 h-4 mr-2"/>
                Refresh
              </Button>
            </div>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-16 bg-white border border-neutral-200 rounded animate-pulse"/>)}
            </div>
          ) : (
            <>
              {/* Compliance Summary */}
              {data?.compliance_summary && (
                <ComplianceSummaryCard
                  score={data.compliance_summary.score}
                  alertActive={data.compliance_summary.alert_active}
                  nextDeadline={data.compliance_summary.next_deadline}
                />
              )}

              {/* Overall Assessment */}
              <Card className={"mb-6 border " + getBg(assessment)}>
                <CardContent className="p-5 flex items-center gap-4">
                  {assessment === 'healthy' ? (
                    <CheckCircle2 className="w-10 h-10 text-emerald-600" />
                  ) : (
                    <AlertTriangle className="w-10 h-10 text-warning" />
                  )}
                  <div>
                    <p className={"text-xs font-mono uppercase tracking-wider " + getColor(assessment)}>Overall Risk Assessment</p>
                    <p className={"text-xl font-bold " + getColor(assessment)}>{label}</p>
                    <p className="text-sm opacity-80">
                      {data?.risk_count || 0} item(s) across {data ? Object.keys(data.by_module).length : 0} module(s)
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Summary Cards */}
              {data && (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
                  <Card><CardContent className="p-3 text-center">
                    <p className="text-2xl font-bold text-navy">{data.risk_count}</p>
                    <p className="text-[10px] text-neutral-500 uppercase">Total Risks</p>
                  </CardContent></Card>
                  <Card><CardContent className="p-3 text-center">
                    <p className="text-2xl font-bold text-red-600">{data.high_count}</p>
                    <p className="text-[10px] text-neutral-500 uppercase">High</p>
                  </CardContent></Card>
                  <Card><CardContent className="p-3 text-center">
                    <p className="text-2xl font-bold text-warning">{data.medium_count}</p>
                    <p className="text-[10px] text-neutral-500 uppercase">Medium</p>
                  </CardContent></Card>
                  <Card><CardContent className="p-3 text-center">
                    <p className="text-2xl font-bold text-slate-500">{data.low_count}</p>
                    <p className="text-[10px] text-neutral-500 uppercase">Low</p>
                  </CardContent></Card>
                  {Object.entries(data.by_module).map(([mod, entries]) => (
                    <Card key={mod}><CardContent className="p-3 text-center cursor-pointer hover:bg-navy/5" onClick={() => setFilterModule(filterModule === mod ? '' : mod)}>
                      <p className="text-lg font-bold text-navy">{entries.length}</p>
                      <p className="text-[10px] text-neutral-500">{mod}</p>
                    </CardContent></Card>
                  ))}
                </div>
              )}

              {/* Filters */}
              <div className="flex gap-2 mb-4">
                {['high', 'medium', 'low'].map((sev) => (
                  <button
                    key={sev}
                    onClick={() => setFilterSeverity(filterSeverity === sev ? '' : sev)}
                    className={"px-3 py-1.5 text-xs font-mono uppercase rounded border transition-colors " + (filterSeverity === sev ? SEVERITY_STYLES[sev].badge : 'border-neutral-200 text-neutral-500 hover:border-neutral-400')}
                  >
                    {sev}
                  </button>
                ))}
                {(filterSeverity || filterModule) && (
                  <button onClick={() => { setFilterSeverity(''); setFilterModule(''); }} className="px-3 py-1.5 text-xs text-neutral-500 hover:text-navy">Clear</button>
                )}
              </div>

              {/* Risk List */}
              <div className="space-y-3">
                {filteredRisks().length === 0 && (data?.risk_count || 0) === 0 ? (
                  <div className="bg-emerald-50 border border-emerald-200 p-12 text-center rounded">
                    <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto mb-3"/>
                    <p className="text-lg font-semibold text-emerald-800">All Clear</p>
                    <p className="text-sm text-emerald-700">No risk items detected. Your trust governance is in good shape.</p>
                  </div>
                ) : filteredRisks().length === 0 ? (
                  <p className="text-center text-sm text-neutral-500 py-8">No items match the selected filters.</p>
                ) : (
                  filteredRisks().map((r, i) => {
                    const style = SEVERITY_STYLES[r.severity] || SEVERITY_STYLES.low;
                    const Icon = r.severity === 'high' ? AlertOctagon : r.severity === 'medium' ? AlertTriangle : AlertCircle;
                    return (
                      <div key={i} className={"flex items-start gap-3 bg-white border rounded p-4 " + style.border}>
                        <div className={"w-9 h-9 flex items-center justify-center flex-shrink-0 rounded " + style.bg}>
                          <Icon className={"w-4 h-4 " + style.icon} />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-semibold text-navy text-sm">{r.title}</h3>
                            <span className={"font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded " + style.badge}>
                              {style.label}
                            </span>
                          </div>
                          <p className="text-sm text-neutral-600 mb-2">{r.detail}</p>
                          <div className="flex items-center gap-3">
                            <p className="text-xs text-neutral-500">Action: {r.action}</p>
                            <Link to={r.deeplink} className="text-xs text-navy hover:text-navy/70 flex items-center gap-1">
                              <ArrowUpRight className="w-3 h-3" />
                              Go to {r.module}
                            </Link>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          )}
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}
