/**
 * DocumentsTabbed — wraps VaultPage, TrustAdminKitsPage, PrintableBinderPage
 * Tab state driven by ?tab= URL param (vault | templates | binder)
 * Route: /vault (the existing route, now with tabs)
 */
import { useSearchParams } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import VaultPage from '@/pages/VaultPage';
import TrustAdminKitsPage from '@/pages/TrustAdminKitsPage';
import PrintableBinderPage from '@/pages/PrintableBinderPage';
import { FolderOpen, Briefcase, NotebookTabs } from 'lucide-react';

export default function DocumentsTabbed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'vault';

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
                <TabsTrigger value="vault" className="flex items-center gap-2">
                  <FolderOpen className="w-4 h-4" />
                  Vault
                </TabsTrigger>
                <TabsTrigger value="templates" className="flex items-center gap-2">
                  <Briefcase className="w-4 h-4" />
                  Templates
                </TabsTrigger>
                <TabsTrigger value="binder" className="flex items-center gap-2">
                  <NotebookTabs className="w-4 h-4" />
                  Record Book
                </TabsTrigger>
              </TabsList>
              <TabsContent value="vault">
                <VaultPage />
              </TabsContent>
              <TabsContent value="templates">
                <TrustAdminKitsPage />
              </TabsContent>
              <TabsContent value="binder">
                <PrintableBinderPage />
              </TabsContent>
            </Tabs>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    </div>
  );
}