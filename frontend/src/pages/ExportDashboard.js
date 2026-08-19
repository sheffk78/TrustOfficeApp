import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import PageHelpButton from '@/components/PageHelpButton';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { safeFormatDate } from '@/utils/safeDate';
import {
  Download,
  Archive,
  RefreshCw,
  Shield,
  FileJson,
  FileArchive,
  Users,
} from 'lucide-react';

function formatBytes(bytes) {
  if (bytes == null || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export default function ExportDashboard() {
  const { selectedTrust, isReadOnly } = useAuth();
  const [format, setFormat] = useState('json');
  const [exportingTrust, setExportingTrust] = useState(false);
  const [exportingClient, setExportingClient] = useState(false);
  const [archives, setArchives] = useState([]);
  const [loadingArchives, setLoadingArchives] = useState(true);
  const [creatingArchive, setCreatingArchive] = useState(false);
  const [clientId, setClientId] = useState(null);

  // Derive client_id from selectedTrust if available
  useEffect(() => {
    if (selectedTrust?.client_id) {
      setClientId(selectedTrust.client_id);
    } else {
      setClientId(null);
    }
  }, [selectedTrust]);

  const loadArchives = useCallback(async () => {
    if (!selectedTrust) {
      setLoadingArchives(false);
      return;
    }
    setLoadingArchives(true);
    try {
      const res = await fetchWithAuth(`/exports/trust/${selectedTrust.trust_id}/archives`);
      if (res.ok) {
        const data = await res.json();
        setArchives(data.archives || data || []);
      } else {
        setArchives([]);
      }
    } catch (error) {
      showError(toast, error, { operation: 'load_archives', page: 'ExportDashboard' });
    } finally {
      setLoadingArchives(false);
    }
  }, [selectedTrust]);

  useEffect(() => {
    loadArchives();
  }, [loadArchives]);

  const triggerDownload = async (res, fallbackName) => {
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const disposition = res.headers.get('Content-Disposition');
    const match = disposition && disposition.match(/filename="?([^";]+)"?/);
    a.download = match ? match[1] : fallbackName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleExportTrust = async () => {
    if (!selectedTrust) return;
    setExportingTrust(true);
    try {
      const res = await fetchWithAuth(`/exports/trust/${selectedTrust.trust_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Export failed');
      }
      await triggerDownload(
        res,
        `trust-export-${selectedTrust.trust_name || selectedTrust.trust_id}.${format}`
      );
      toast.success('Trust data exported successfully');
    } catch (error) {
      showError(toast, error, { operation: 'export_trust', page: 'ExportDashboard' });
    } finally {
      setExportingTrust(false);
    }
  };

  const handleExportClient = async () => {
    if (!clientId) return;
    setExportingClient(true);
    try {
      const res = await fetchWithAuth(`/exports/client/${clientId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Client export failed');
      }
      await triggerDownload(res, `client-export-${clientId}.${format}`);
      toast.success('Client data exported successfully');
    } catch (error) {
      showError(toast, error, { operation: 'export_client', page: 'ExportDashboard' });
    } finally {
      setExportingClient(false);
    }
  };

  const handleCreateArchive = async () => {
    if (!selectedTrust) return;
    setCreatingArchive(true);
    try {
      const res = await fetchWithAuth(`/exports/trust/${selectedTrust.trust_id}/archive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Archive creation failed');
      }
      toast.success('Archive created successfully');
      await loadArchives();
    } catch (error) {
      showError(toast, error, { operation: 'create_archive', page: 'ExportDashboard' });
    } finally {
      setCreatingArchive(false);
    }
  };

  const handleDownloadArchive = async (archive) => {
    try {
      const res = await fetchWithAuth(`/exports/archive/${archive.archive_id}/download`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Archive download failed');
      }
      await triggerDownload(res, `archive-${archive.archive_id}.zip`);
    } catch (error) {
      showError(toast, error, { operation: 'download_archive', page: 'ExportDashboard' });
    }
  };

  return (
    <div className="main-layout" data-testid="export-dashboard-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Export &amp; Archive</h1>
              <p className="page-subtitle">
                Export trust data and create full archive backups for{' '}
                {selectedTrust?.trust_name || 'your trust'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Export trust data as JSON or ZIP' },
                  { text: 'Create a comprehensive archive including vault files' },
                  { text: 'Download previous archives at any time' },
                ]}
                taPrompt="How do I export my trust data and create backups?"
              />
              <Button
                onClick={loadArchives}
                variant="outline"
                className="btn-secondary"
                disabled={loadingArchives}
                data-testid="refresh-archives-btn"
              >
                <RefreshCw className={`w-4 h-4 mr-2 ${loadingArchives ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </div>
          </div>

          {!selectedTrust ? (
            <div className="card-trust p-8 text-center text-muted-foreground">
              <Shield className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>Select a trust to export data or create archives.</p>
            </div>
          ) : (
            <>
              {/* Export Data Section */}
              <div className="card-trust mb-8">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-navy/10 flex items-center justify-center">
                      <Download className="w-5 h-5 text-navy" />
                    </div>
                    <div>
                      <h3 className="font-serif text-lg text-navy">Export Data</h3>
                      <p className="text-sm text-muted-foreground">
                        Download trust details, entities, beneficiaries, minutes, meetings, deadlines, tasks, distributions, compensation, and expenses
                      </p>
                    </div>
                  </div>
                </div>

                {/* Format selector */}
                <div className="flex items-center gap-4 mb-4">
                  <span className="text-sm font-medium text-navy">Format:</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setFormat('json')}
                      className={`flex items-center gap-2 px-3 py-1.5 text-xs font-mono border transition-colors ${
                        format === 'json'
                          ? 'bg-navy text-cream border-navy'
                          : 'border-navy/20 text-muted-foreground hover:border-navy/40'
                      }`}
                      data-testid="format-json"
                    >
                      <FileJson className="w-3 h-3" />
                      JSON
                    </button>
                    <button
                      onClick={() => setFormat('zip')}
                      className={`flex items-center gap-2 px-3 py-1.5 text-xs font-mono border transition-colors ${
                        format === 'zip'
                          ? 'bg-navy text-cream border-navy'
                          : 'border-navy/20 text-muted-foreground hover:border-navy/40'
                      }`}
                      data-testid="format-zip"
                    >
                      <FileArchive className="w-3 h-3" />
                      ZIP
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-3 flex-wrap">
                  <Button
                    onClick={handleExportTrust}
                    disabled={exportingTrust || isReadOnly}
                    className="btn-primary"
                    data-testid="export-trust-btn"
                  >
                    {exportingTrust ? (
                      <>
                        <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        Exporting...
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4 mr-2" />
                        Export Trust Data
                      </>
                    )}
                  </Button>
                  {clientId && (
                    <Button
                      onClick={handleExportClient}
                      disabled={exportingClient || isReadOnly}
                      variant="outline"
                      className="btn-secondary"
                      data-testid="export-client-btn"
                    >
                      {exportingClient ? (
                        <>
                          <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                          Exporting...
                        </>
                      ) : (
                        <>
                          <Users className="w-4 h-4 mr-2" />
                          Export Client Data
                        </>
                      )}
                    </Button>
                  )}
                </div>
              </div>

              {/* Archive Backups Section */}
              <div className="card-trust">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-navy/10 flex items-center justify-center">
                      <Archive className="w-5 h-5 text-navy" />
                    </div>
                    <div>
                      <h3 className="font-serif text-lg text-navy">Archive Backups</h3>
                      <p className="text-sm text-muted-foreground">
                        Comprehensive ZIP archives including all trust data and vault files
                      </p>
                    </div>
                  </div>
                  <Button
                    onClick={handleCreateArchive}
                    disabled={creatingArchive || isReadOnly}
                    className="btn-primary"
                    data-testid="create-archive-btn"
                  >
                    {creatingArchive ? (
                      <>
                        <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        Creating archive...
                      </>
                    ) : (
                      <>
                        <Archive className="w-4 h-4 mr-2" />
                        Create Archive
                      </>
                    )}
                  </Button>
                </div>

                {loadingArchives ? (
                  <div className="skeleton h-32 w-full"></div>
                ) : archives.length === 0 ? (
                  <div className="p-6 text-center text-muted-foreground">
                    <Archive className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    <p className="text-sm">No archives created yet. Click &quot;Create Archive&quot; to make your first backup.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {archives.map((archive) => (
                      <div
                        key={archive.archive_id}
                        className="flex items-center justify-between p-4 border border-navy/10"
                        data-testid={`archive-${archive.archive_id}`}
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 bg-navy/10 flex items-center justify-center">
                            <Archive className="w-5 h-5 text-navy" />
                          </div>
                          <div>
                            <p className="font-medium text-sm text-navy">
                              Archive &middot; {safeFormatDate(archive.created_at, 'MMM d, yyyy h:mm a')}
                            </p>
                            <p className="text-xs text-muted-foreground font-mono">
                              {formatBytes(archive.size_bytes)}
                            </p>
                          </div>
                        </div>
                        <Button
                          onClick={() => handleDownloadArchive(archive)}
                          size="sm"
                          variant="outline"
                          className="btn-secondary"
                          data-testid={`download-archive-${archive.archive_id}`}
                        >
                          <Download className="w-3 h-3 mr-1" />
                          Download
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
