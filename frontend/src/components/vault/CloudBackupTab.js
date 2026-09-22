import { Cloud } from 'lucide-react';
import CloudBackupSection from '@/components/vault/CloudBackupSection';

/**
 * CloudBackupTab — content for the "Cloud Backup" tab (Option A nav
 * consolidation, 2026-09-22). Renders the backup section with a page
 * heading. The Vault tab keeps its inline backup card (unchanged); this
 * tab gives backup a first-class destination. Deep links:
 *   /vault?tab=backup          -> this tab
 *   /vault?tab=vault&focus=backup -> scroll+highlight card inside Vault (unchanged)
 */
export default function CloudBackupTab({ selectedTrust }) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-navy/8">
          <Cloud className="w-5 h-5 text-navy" />
        </div>
        <div>
          <h1 className="page-title">Cloud Backup</h1>
          <p className="text-sm text-muted-foreground">
            Copy your trust documents to your own Google Drive, Dropbox, OneDrive, or Proton Drive —
            you keep a copy you control, outside TrustOffice.
          </p>
        </div>
      </div>
      <CloudBackupSection selectedTrust={selectedTrust} />
    </div>
  );
}
