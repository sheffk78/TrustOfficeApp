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

export default function HealthComplianceTabbed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'overview';

  const handleTabChange = (newTab) => {
    setSearchParams({ tab: newTab });
  };

  return (
    <div className="flex min-h-screen bg-subtle-bg">
      <Sidebar />
      <div className="flex-1 flex flex-col lg:ml-0">
        <main className="flex-1 overflow-y-auto pb-20 lg:pb-0">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
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
        </main>
        <MobileBottomNav />
      </div>
    </div>
  );
}