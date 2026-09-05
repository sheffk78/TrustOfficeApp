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

// Official brand marks — Google Drive four-color triangle (Google brand asset, viewBox 0 0 87.3 78),
// Dropbox official glyph + OneDrive official cloud (Simple Icons, CC0, viewBox 0 0 24 24).
function DriveIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 87.3 78" xmlns="http://www.w3.org/2000/svg">
      <path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z" fill="#0066da"/>
      <path d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0 -1.2 4.5h27.5z" fill="#00ac47"/>
      <path d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.502l5.852 11.5z" fill="#ea4335"/>
      <path d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z" fill="#00832d"/>
      <path d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z" fill="#2684fc"/>
      <path d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z" fill="#ffba00"/>
    </svg>
  );
}

function DropboxIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 1.807L0 5.629l6 3.822 6.001-3.822L6 1.807zM18 1.807l-6 3.822 6 3.822 6-3.822-6-3.822zM0 13.274l6 3.822 6.001-3.822L6 9.452l-6 3.822zM18 9.452l-6 3.822 6 3.822 6-3.822-6-3.822zM6 18.371l6.001 3.822 6-3.822-6-3.822L6 18.371z"/>
    </svg>
  );
}

function OneDriveIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <path d="M19.453 9.95q.961.058 1.787.468.826.41 1.442 1.066.615.657.966 1.512.352.856.352 1.816 0 1.008-.387 1.893-.386.885-1.049 1.547-.662.662-1.546 1.049-.885.387-1.893.387H6q-1.242 0-2.332-.475-1.09-.475-1.904-1.29-.815-.814-1.29-1.903Q0 14.93 0 13.688q0-.985.31-1.887.311-.903.862-1.658.55-.756 1.324-1.325.774-.568 1.711-.861.434-.129.85-.187.416-.06.861-.082h.012q.515-.786 1.207-1.413.691-.627 1.5-1.066.808-.44 1.705-.668.896-.229 1.845-.229 1.278 0 2.456.417 1.177.416 2.144 1.16.967.744 1.658 1.78.692 1.038 1.008 2.28zm-7.265-4.137q-1.325 0-2.52.544-1.195.545-2.04 1.565.446.117.85.299.405.181.792.416l4.78 2.86 2.731-1.15q.27-.117.545-.204.276-.088.58-.147-.293-.937-.855-1.705-.563-.768-1.319-1.318-.755-.551-1.658-.856-.902-.304-1.886-.304zM2.414 16.395l9.914-4.184-3.832-2.297q-.586-.351-1.23-.539-.645-.188-1.325-.188-.914 0-1.722.364-.809.363-1.412.978-.604.616-.955 1.436-.352.82-.352 1.723 0 .703.234 1.423.235.721.68 1.284zm16.711 1.793q.563 0 1.078-.176.516-.176.961-.516l-7.23-4.324-10.301 4.336q.527.328 1.13.504.604.175 1.237.175zm3.012-1.852q.363-.727.363-1.523 0-.774-.293-1.407t-.791-1.072q-.498-.44-1.166-.68-.668-.24-1.406-.24-.422 0-.838.1t-.815.252q-.398.152-.785.334-.386.181-.761.345Z"/>
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