import { useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import { RefreshCw, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import PageHelpButton from '@/components/PageHelpButton';
import { toast } from 'sonner';

import { PAGE_SIZE } from './audit-trail/constants';
import { useAuditTrail } from './audit-trail/useAuditTrail';
import EventItem from './audit-trail/EventItem';
import FilterBar from './audit-trail/FilterBar';
import StatsGrid from './audit-trail/StatsGrid';
import Pagination from './audit-trail/Pagination';
import { LoadingState, NoTrustState, EmptyState } from './audit-trail/PageStates';

export default function AuditTrailPage() {
  const { selectedTrust } = useAuth();
  const { events, loading, filter, setFilter, page, setPage, totalPages, loadAuditTrail } =
    useAuditTrail(selectedTrust);
  const [downloading, setDownloading] = useState(false);

  const handleExport = async () => {
    if (!selectedTrust) return;
    setDownloading(true);
    try {
      const res = await fetchWithAuth(
        `/exports/audit-defense/${selectedTrust.trust_id}?days=365`,
      );
      if (!res.ok) throw new Error('Failed to generate report');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_defense_${selectedTrust.trust_id}_${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('Audit Defense Report downloaded');
    } catch (e) {
      toast.error(e.message || 'Failed to generate report');
    } finally {
      setDownloading(false);
    }
  };

  const handleFilterChange = (value) => {
    setFilter(value);
    setPage(1);
  };

  if (loading) return <LoadingState />;
  if (!selectedTrust) return <NoTrustState />;

  const paginatedEvents = events.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content mobile-layout-offset">
        <div className="page-container max-w-4xl mx-auto space-y-6">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Audit Trail</h1>
              <p className="page-subtitle">
                View a complete log of all trust administration actions — track changes,
                access, and decisions for compliance
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'View a complete log of all trust administration actions' },
                  { text: 'Track changes, access, and decisions for compliance and transparency' },
                  { text: 'Filter events by type to focus on minutes, distributions, or alerts' },
                  { text: 'Export a court-ready Audit Defense PDF with the Export button' },
                ]}
                taPrompt="Walk me through the Audit Trail and what gets logged"
                contextAlerts={
                  events.length < 5
                    ? [
                        {
                          text: 'Your audit trail is sparse. Regular activity (minutes, distributions) builds a stronger compliance record.',
                          prompt: 'What should I be doing to build a strong audit trail for my trust?',
                        },
                      ]
                    : []
                }
              />
              <Button variant="outline" size="sm" onClick={loadAuditTrail}>
                <RefreshCw className="w-4 h-4 mr-1" /> Refresh
              </Button>
              <Button variant="outline" size="sm" onClick={handleExport} disabled={downloading}>
                <Download className="w-4 h-4 mr-1" /> {downloading ? 'Generating...' : 'Export'}
              </Button>
            </div>
          </div>

          {/* Stats */}
          <StatsGrid events={events} />

          {/* Filters */}
          <FilterBar filter={filter} onChange={handleFilterChange} />

          {/* Timeline */}
          {paginatedEvents.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="space-y-2">
              {paginatedEvents.map((event, idx) => (
                <EventItem key={event.id || idx} event={event} idx={idx} />
              ))}
            </div>
          )}

          {/* Pagination */}
          <Pagination page={page} totalPages={totalPages} onChange={setPage} />
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}