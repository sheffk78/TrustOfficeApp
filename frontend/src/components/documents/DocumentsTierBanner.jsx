import { useSearchParams } from 'react-router-dom';
import { FolderOpen, NotebookTabs, Cloud } from 'lucide-react';

// DocumentsTierBanner Ã¢ÂÂ three-tier structure strip shown at the top of the
// Documents section (above the Vault/Templates/Record Book tabs).
//   1. TrustOffice (this vault)        Ã¢ÂÂ current view
//   2. Printed Record Book (binder)    Ã¢ÂÂ links to the Record Book tab
//   3. Your own cloud backup           Ã¢ÂÂ jumps to the backup section in the vault
export default function DocumentsTierBanner() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'vault';

  const goToTab = (newTab) => {
    setSearchParams({ tab: newTab });
  };

  // "Your own cloud backup" jumps to the vault tab with ?focus=backup so the
  // VaultPage scrolls to + highlights the cloud-backup card.
  const goToBackup = () => {
    setSearchParams({ tab: 'vault', focus: 'backup' });
  };

  const Item = ({ index, icon: Icon, label, onClick, active }) => (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
        active
          ? 'bg-navy/10 text-navy font-medium'
          : 'text-muted-foreground hover:text-navy hover:bg-navy/5'
      }`}
      data-testid={`tier-banner-${index}`}
    >
      <span className="flex items-center justify-center w-5 h-5 rounded-full bg-navy/10 text-navy text-xs font-mono">
        {index}
      </span>
      <Icon className="w-4 h-4" />
      <span>{label}</span>
    </button>
  );

  return (
    <div
      className="mb-6 p-3 border border-navy/15 bg-navy/5 rounded-lg flex flex-wrap items-center gap-2"
      data-testid="documents-tier-banner"
    >
      <Item
        index={1}
        icon={FolderOpen}
        label="TrustOffice (this vault)"
        active={tab === 'vault'}
        onClick={() => goToTab('vault')}
      />
      <span className="text-navy/30 mx-1">ÃÂ·</span>
      <Item
        index={2}
        icon={NotebookTabs}
        label="Printed Record Book"
        active={tab === 'binder'}
        onClick={() => goToTab('binder')}
      />
      <span className="text-navy/30 mx-1">ÃÂ·</span>
      <Item
        index={3}
        icon={Cloud}
        label="Your own cloud backup"
        active={false}
        onClick={goToBackup}
      />
    </div>
  );
}
