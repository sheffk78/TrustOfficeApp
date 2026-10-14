/**
 * HealthComplianceTabbed — wraps GovernancePage, RiskDashboardPage, StateCompliancePage
 * Tab state driven by ?tab= URL param (overview | risk | state)
 * Route: /governance (the existing route, now with tabs)
 */
import { useSearchParams } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import GovernancePage from '@/pages/GovernancePage';
import RiskDashboardPage from '@/pages/RiskDashboardPage';
import StateCompliancePage from '@/pages/StateCompliancePage';
import { HeartPulse, Activity, MapPin } from 'lucide-react';
import PageHeader from '@/components/PageHeader';

export default function HealthComplianceTabbed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'overview';

  const handleTabChange = (newTab) => {
    setSearchParams({ tab: newTab });
  };

  return (
    <div className="main-layout">
      <Sidebar />
      <div className="main-content dot-grid">
        <div className="page-container">
          <PageHeader
            title="Governance"
            subtitle="Monitor trust health, compliance risk, and state-by-state requirements"
            help={{
              items: [
                { text: 'Overview tracks your trust health score across 8 criteria' },
                { text: 'Risk lists open compliance items that need action' },
                { text: 'State shows filing requirements for your trust\'s governing state' },
              ],
              taPrompt: 'Walk me through the Governance pages and what each tab shows',
            }}
          />
            <Tabs value={tab} onValueChange={handleTabChange}>
              <TabsList className="mb-6">
                <TabsTrigger value="overview" className="flex items-center gap-2">
                  <HeartPulse className="w-4 h-4" />
                  Overview
                </TabsTrigger>
                <TabsTrigger value="risk" className="flex items-center gap-2">
                  <Activity className="w-4 h-4" />
                  Risk
                </TabsTrigger>
                <TabsTrigger value="state" className="flex items-center gap-2">
                  <MapPin className="w-4 h-4" />
                  State
                </TabsTrigger>
              </TabsList>
              <TabsContent value="overview">
                <GovernancePage />
              </TabsContent>
              <TabsContent value="risk">
                <RiskDashboardPage />
              </TabsContent>
              <TabsContent value="state">
                <StateCompliancePage />
              </TabsContent>
            </Tabs>
          </div>
        <MobileBottomNav />
      </div>
    </div>
  );
}