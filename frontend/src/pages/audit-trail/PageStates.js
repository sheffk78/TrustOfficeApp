import { RefreshCw, FileText, Clock } from 'lucide-react';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';

export function LoadingState() {
  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content mobile-layout-offset">
        <div className="page-container flex items-center justify-center py-20">
          <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}

export function NoTrustState() {
  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content mobile-layout-offset">
        <div className="page-container">
          <div className="card-trust p-12 flex flex-col items-center justify-center">
            <FileText className="w-12 h-12 text-muted-foreground/60 mb-3" />
            <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
            <p className="text-sm text-muted-foreground">
              Choose a trust to view the audit trail.
            </p>
          </div>
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}

export function EmptyState() {
  return (
    <div className="card-trust text-center py-12">
      <Clock className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
      <h3 className="font-serif text-lg text-navy mb-2">No Audit Events</h3>
      <p className="text-sm text-muted-foreground">
        Actions taken on this trust will appear here as a permanent record.
      </p>
    </div>
  );
}