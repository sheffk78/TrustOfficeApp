/**
 * InvestmentsPage with Tabs — wraps InvestmentsPage and PerformanceDashboard
 * Tab state driven by ?tab= URL param (holdings | performance)
 */
import { useSearchParams } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import InvestmentsPage from '@/pages/InvestmentsPage';
import PerformanceDashboard from '@/pages/PerformanceDashboard';
import { TrendingUp, BarChart3 } from 'lucide-react';

export default function InvestmentsTabbed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'holdings';

  const handleTabChange = (newTab) => {
    setSearchParams({ tab: newTab });
  };

  return (
    <div className="flex min-h-screen bg-subtle-bg">
      <Sidebar />
      <div className="flex-1 flex flex-col lg:ml-0">
        <main className="flex-1 overflow-y-auto pb-20 lg:pb-0">
          <div className="page-container">
            <Tabs value={tab} onValueChange={handleTabChange}>
              <TabsList className="mb-6">
                <TabsTrigger value="holdings" className="flex items-center gap-2">
                  <TrendingUp className="w-4 h-4" />
                  Holdings
                </TabsTrigger>
                <TabsTrigger value="performance" className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4" />
                  Performance
                </TabsTrigger>
              </TabsList>
              <TabsContent value="holdings">
                <InvestmentsPage />
              </TabsContent>
              <TabsContent value="performance">
                <PerformanceDashboard />
              </TabsContent>
            </Tabs>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    </div>
  );
}