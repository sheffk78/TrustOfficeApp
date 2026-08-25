/**
 * BenevolenceTabbed — wraps BenevolencePage and BenevolencePolicyPage
 * Tab state driven by ?tab= URL param (distributions | policy)
 */
import { useSearchParams } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import BenevolencePage from '@/pages/BenevolencePage';
import BenevolencePolicyPage from '@/pages/BenevolencePolicyPage';
import { HeartHandshake, FileText } from 'lucide-react';

export default function BenevolenceTabbed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'distributions';

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
                <TabsTrigger value="distributions" className="flex items-center gap-2">
                  <HeartHandshake className="w-4 h-4" />
                  Distributions
                </TabsTrigger>
                <TabsTrigger value="policy" className="flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Policy
                </TabsTrigger>
              </TabsList>
              <TabsContent value="distributions">
                <BenevolencePage />
              </TabsContent>
              <TabsContent value="policy">
                <BenevolencePolicyPage />
              </TabsContent>
            </Tabs>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    </div>
  );
}