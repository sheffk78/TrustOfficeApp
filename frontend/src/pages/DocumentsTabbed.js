/**
 * DocumentsTabbed — wraps VaultPage, TrustAdminKitsPage, PrintableBinderPage,
 * CloudBackupTab. Option A nav consolidation (2026-09-22): the old 3-tier
 * banner was removed — one tab bar, each tab self-explanatory.
 * Tab state driven by ?tab= URL param (vault | templates | binder | backup)
 * Route: /vault (the existing route, now with tabs)
 */
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import VaultPage from '@/pages/VaultPage';
import TrustAdminKitsPage from '@/pages/TrustAdminKitsPage';
import PrintableBinderPage from '@/pages/PrintableBinderPage';
import CloudBackupTab from '@/components/vault/CloudBackupTab';
import DissolvedTrustBanner from '@/components/trust/DissolvedTrustBanner';
import { FolderOpen, Briefcase, NotebookTabs, Cloud } from 'lucide-react';

export default function DocumentsTabbed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'vault';
  const { selectedTrust } = useAuth();

  const handleTabChange = (newTab) => {
    setSearchParams({ tab: newTab });
  };

  return (
    <div className="main-layout">
      <Sidebar />
      <div className="main-content dot-dot">
        <div className="page-container">
          <DissolvedTrustBanner trust={selectedTrust} />
          <Tabs value={tab} onValueChange={handleTabChange}>
              <TabsList className="mb-6">
                <TabsTrigger value="vault" className="flex items-center gap-2">
                  <FolderOpen className="w-4 h-4" />
                  Vault
                </TabsTrigger>
                <TabsTrigger value="binder" className="flex items-center gap-2">
                  <NotebookTabs className="w-4 h-4" />
                  Record Book
                </TabsTrigger>
                <TabsTrigger value="templates" className="flex items-center gap-2">
                  <Briefcase className="w-4 h-4" />
                  Templates
                </TabsTrigger>
                <TabsTrigger value="backup" className="flex items-center gap-2">
                  <Cloud className="w-4 h-4" />
                  Cloud Backup
                </TabsTrigger>
              </TabsList>
              <TabsContent value="vault">
                <VaultPage />
              </TabsContent>
              <TabsContent value="binder">
                <PrintableBinderPage />
              </TabsContent>
              <TabsContent value="templates">
                <TrustAdminKitsPage />
              </TabsContent>
              <TabsContent value="backup">
                <CloudBackupTab selectedTrust={selectedTrust} />
              </TabsContent>
          </Tabs>
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}