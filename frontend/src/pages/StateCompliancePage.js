import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import {
  MapPin, AlertTriangle, Shield, CheckCircle2, Clock,
  FileText, ChevronRight, BookOpen, Scale, Gavel
} from 'lucide-react';

const SEVERITY_STYLES = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
};

const CATEGORY_ICONS = {
  utc_gap: Scale,
  utc_partial: Scale,
  notice: FileText,
  accounting: Clock,
  spendthrift: Shield,
};

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
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <div className="md:pl-64 pb-20 md:pb-0">
          <div className="pt-16 md:pt-8 ml-4 mr-4">
            <div className="bg-white border border-neutral-200 p-12 flex flex-col items-center justify-center rounded-lg">
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
          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6 gap-4">
            <div>
              <h1 className="text-2xl font-bold text-navy flex items-center gap-2">
                <Shield className="w-6 h-6 text-navy"/>
                State Compliance
              </h1>
              <p className="text-sm text-neutral-600 mt-1">
                Jurisdiction rules for <span className="font-semibold">{selectedTrust.name}</span>
              </p>
            </div>
            <Link to="/settings">
              <Button variant="outline">Edit Trust Profile</Button>
            </Link>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-24 bg-white border border-neutral-200 rounded-lg animate-pulse"/>)}
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
                  </CardContent>
                </Card>

                <Card className="border border-neutral-200">
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3 mb-2">
                      <Gavel className="w-5 h-5 text-navy"/>
                      <p className="text-xs font-mono uppercase tracking-wider text-neutral-500">Trustee Removal</p>
                    </div>
                    <p className="text-sm font-medium text-navy capitalize">{profile?.trustee_removal_standard}</p>
                  </CardContent>
                </Card>
              </div>

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
                          <div key={i} className="flex gap-4 p-4 bg-white border border-neutral-200 rounded-lg">
                            <div className={`w-10 h-10 flex items-center justify-center flex-shrink-0 rounded ${
                              req.severity === 'high' ? 'bg-red-100 text-red-600' :
                              req.severity === 'medium' ? 'bg-amber-100 text-amber-600' :
                              'bg-slate-100 text-slate-500'
                            }`}>
                              <Icon className="w-5 h-5"/>
                            </div>
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <h3 className="font-semibold text-navy text-sm">{req.title}</h3>
                                <span className={`font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${SEVERITY_STYLES[req.severity]}`}>
                                  {req.severity}
                                </span>
                              </div>
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
