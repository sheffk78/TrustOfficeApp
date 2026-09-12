import { ShieldCheck } from 'lucide-react';

// DissolvedTrustBanner ÃÂ¢ÃÂÃÂ persistent banner shown on trust-scoped pages when the
// selected trust has been dissolved and archived (read-only records preserved).
//
// Reads `trust.status === 'dissolved_archived'` and `trust.dissolved_on`.
// Renders nothing if the trust is not dissolved (or no trust selected).
// Edit affordances are hidden via the existing permission pattern (the pages
// gate writes on `!isDissolved`), so this banner simply communicates state.
export default function DissolvedTrustBanner({ trust }) {
  if (!trust || trust.status !== 'dissolved_archived') return null;

  const formatDate = (iso) => {
    if (!iso) return null;
    try {
      return new Date(iso).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    } catch {
      return null;
    }
  };

  const dateLabel = formatDate(trust.dissolved_on);

  return (
    <div
      className="mb-6 p-4 border border-navy/20 bg-navy/5 rounded-lg flex items-start gap-3"
      data-testid="dissolved-trust-banner"
      role="status"
    >
      <ShieldCheck className="w-5 h-5 text-navy flex-shrink-0 mt-0.5" />
      <div>
        <p className="font-medium text-navy">
          {dateLabel
            ? `Dissolved ${dateLabel} ÃÂ¢ÃÂÃÂ records preserved read-only`
            : 'Dissolved ÃÂ¢ÃÂÃÂ records preserved read-only'}
        </p>
        <p className="text-sm text-muted-foreground mt-0.5">
          This trust has been dissolved and archived. Its records are preserved and viewable, but
          can no longer be edited.
        </p>
      </div>
    </div>
  );
}

// Helper predicate consumed by trust-scoped pages to hide edit affordances.
export const isTrustDissolved = (trust) =>
  Boolean(trust && trust.status === 'dissolved_archived');
