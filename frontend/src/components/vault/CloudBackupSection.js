import { useState, useEffect, useCallback } from 'react';
import { Cloud, HardDrive, RefreshCw, CheckCircle2, AlertCircle, Loader2, CloudUpload, X, ExternalLink } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';

const PROVIDER_LABELS = {
  google_drive: 'Google Drive',
  dropbox: 'Dropbox',
  onedrive: 'OneDrive',
};

const PROVIDER_ICONS = {
  google_drive: DriveIcon,
  dropbox: DropboxIcon,
  onedrive: OneDriveIcon,
};

function DriveIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M9.5 14.5L4 5h6l4 7" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
      <path d="M14 19H4l3-5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
      <path d="M18 5h6l-5 9" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
      <path d="M9 14.5h11" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  );
}

function DropboxIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M7 2L2 6l5 4 5-4-5-4z" fill="currentColor"/>
      <path d="M12 6l5 4 5-4-5-4-5 4z" fill="currentColor"/>
      <path d="M2 6v5l5 4v-5L2 6z" fill="currentColor" opacity="0.7"/>
      <path d="M17 10v5l5-4V6l-5 4z" fill="currentColor" opacity="0.7"/>
      <path d="M7 15l5 4 5-4-5-4-5 4z" fill="currentColor" opacity="0.5"/>
    </svg>
  );
}

function OneDriveIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M8 8a4 4 0 014-4 4 4 0 014 4M16 8a3 3 0 013 3 3 3 0 010 6H7a3 3 0 010-6" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  );
}

export default function CloudBackupSection({ selectedTrust }) {
  const [connections, setConnections] = useState([]);
  const [stats, setStats] = useState({ total_documents: 0, backed_up_documents: 0 });
  const [loading, setLoading] = useState(true);
  const [backupRunning, setBackupRunning] = useState(false);
  const [showConnectModal, setShowConnectModal] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const resp = await fetchWithAuth('/backup/status');
      if (resp.ok) {
        const data = await resp.json();
        setConnections(data.connections || []);
        setStats(data.stats || { total_documents: 0, backed_up_documents: 0 });
      }
    } catch (e) {
      console.error('Failed to load backup status:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    // Check for OAuth callback success
    const params = new URLSearchParams(window.location.search);
    if (params.get('backup_connected') === 'true') {
      toast.success('Cloud backup connected successfully!');
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const connectProvider = async (provider) => {
    try {
      const resp = await fetchWithAuth(`/backup/oauth/connect?provider=${provider}`);
      if (resp.ok) {
        const { auth_url } = await resp.json();
        window.location.href = auth_url;
      } else {
        const data = await resp.json();
        toast.error(data.detail || 'Failed to connect');
      }
    } catch (e) {
      toast.error('Connection failed. Please try again.');
    }
  };

  const triggerBackup = async () => {
    setBackupRunning(true);
    try {
      const resp = await fetchWithAuth('/backup/trigger', { method: 'POST' });
      if (resp.ok) {
        const data = await resp.json();
        toast.success(data.message || `Backup complete: ${data.result.backed_up} files backed up`);
        loadStatus();
      } else {
        const data = await resp.json();
        toast.error(data.detail || 'Backup failed');
      }
    } catch (e) {
      toast.error('Backup failed. Please try again.');
    } finally {
      setBackupRunning(false);
    }
  };

  const disconnect = async (provider) => {
    if (!confirm(`Disconnect ${PROVIDER_LABELS[provider]}? Your files will remain in your cloud storage.`)) return;
    try {
      const resp = await fetchWithAuth(`/backup/disconnect?provider=${provider}`, { method: 'DELETE' });
      if (resp.ok) {
        toast.success('Cloud backup disconnected');
        loadStatus();
      } else {
        toast.error('Failed to disconnect');
      }
    } catch (e) {
      toast.error('Failed to disconnect');
    }
  };

  const formatDate = (isoStr) => {
    if (!isoStr) return 'Never';
    try {
      return new Date(isoStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
    } catch {
      return 'Unknown';
    }
  };

  const formatStatus = (conn) => {
    if (conn.last_backup_status === 'in_progress') return { icon: Loader2, text: 'Backup in progress...', color: 'text-blue-500', spin: true };
    if (conn.last_backup_status === 'success') return { icon: CheckCircle2, text: `${conn.last_backup_doc_count || 0} files backed up`, color: 'text-green-600', spin: false };
    if (conn.last_backup_status === 'partial') return { icon: AlertCircle, text: `Partial: ${conn.last_backup_doc_count || 0} backed up, some failed`, color: 'text-amber-600', spin: false };
    if (conn.last_backup_status === 'failed') return { icon: AlertCircle, text: conn.last_backup_error || 'Backup failed', color: 'text-red-500', spin: false };
    if (conn.last_backup_status === 'connected') return { icon: CheckCircle2, text: 'Connected — first backup pending', color: 'text-blue-500', spin: false };
    return { icon: Cloud, text: 'Ready', color: 'text-gray-500', spin: false };
  };

  if (loading) {
    return (
      <div className="card-trust p-6 mb-6 animate-pulse">
        <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
        <div className="h-10 bg-gray-200 rounded w-1/2"></div>
      </div>
    );
  }

  return (
    <div className="card-trust p-6 mb-6">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <CloudUpload className="w-5 h-5 text-navy" />
        <h3 className="text-lg font-semibold text-navy">Cloud Backup</h3>
      </div>

      {/* Connected providers */}
      {connections.length > 0 ? (
        <div className="space-y-4">
          {connections.map((conn) => {
            const StatusIcon = formatStatus(conn).icon;
            const ProviderIcon = PROVIDER_ICONS[conn.provider] || Cloud;
            const status = formatStatus(conn);
            return (
              <div key={conn.provider} className="border border-gray-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <ProviderIcon className="w-5 h-5 text-navy" />
                    <span className="font-medium text-navy">{PROVIDER_LABELS[conn.provider]}</span>
                    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">Connected</span>
                  </div>
                  <button
                    onClick={() => disconnect(conn.provider)}
                    className="text-xs text-gray-400 hover:text-red-500 transition-colors"
                    data-testid={`disconnect-${conn.provider}`}
                  >
                    Disconnect
                  </button>
                </div>

                <div className="flex items-center gap-2 text-sm text-gray-600 mb-3">
                  <StatusIcon className={`w-4 h-4 ${status.color} ${status.spin ? 'animate-spin' : ''}`} />
                  <span className={status.color}>{status.text}</span>
                  <span className="text-gray-400">·</span>
                  <span>Last backup: {formatDate(conn.last_backup_at)}</span>
                </div>

                {/* Stats bar */}
                <div className="flex items-center gap-4 text-xs text-gray-500 mb-3">
                  <span>
                    {stats.backed_up_documents} of {stats.total_documents} documents backed up
                  </span>
                </div>

                {/* Progress bar */}
                {stats.total_documents > 0 && (
                  <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden mb-3">
                    <div
                      className="h-full bg-green-500 transition-all"
                      style={{ width: `${(stats.backed_up_documents / stats.total_documents) * 100}%` }}
                    />
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2">
                  <button
                    onClick={triggerBackup}
                    disabled={backupRunning}
                    className="btn-primary text-sm px-4 py-2 flex items-center gap-2 disabled:opacity-50"
                    data-testid="backup-now-btn"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${backupRunning ? 'animate-spin' : ''}`} />
                    {backupRunning ? 'Backing up...' : 'Back Up Now'}
                  </button>
                  <div className="text-xs text-gray-400 flex items-center gap-1">
                    <span>Weekly auto-backup: Sundays 2 AM UTC</span>
                  </div>
                </div>
              </div>
            );
          })}

          {/* Add another provider */}
          <button
            onClick={() => setShowConnectModal(true)}
            className="text-sm text-navy hover:underline flex items-center gap-1"
          >
            <HardDrive className="w-4 h-4" />
            Connect another provider
          </button>
        </div>
      ) : (
        /* Not connected — show connect options */
        <div>
          <p className="text-sm text-gray-500 mb-4">
            Automatically back up your vault documents to your own cloud storage account.
            Files are organized by category and backed up weekly.
          </p>
          <div className="flex flex-wrap gap-3">
            {Object.entries(PROVIDER_LABELS).map(([key, label]) => {
              const Icon = PROVIDER_ICONS[key];
              return (
                <button
                  key={key}
                  onClick={() => connectProvider(key)}
                  className="border border-gray-200 rounded-lg px-4 py-3 hover:border-navy hover:bg-navy/5 transition-all flex items-center gap-2 group"
                  data-testid={`connect-${key}`}
                >
                  <Icon className="w-5 h-5 text-gray-600 group-hover:text-navy" />
                  <span className="text-sm font-medium text-gray-700 group-hover:text-navy">
                    Connect {label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Info note */}
      <div className="mt-4 flex items-start gap-2 text-xs text-gray-400">
        <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
        <span>
          Your cloud credentials are never stored — we use secure OAuth tokens.
          Only files created by TrustOffice are accessible to us. Your data stays yours.
        </span>
      </div>
    </div>
  );
}