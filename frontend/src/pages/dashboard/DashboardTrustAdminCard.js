import { useState, useEffect } from 'react';
import { Calendar } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';

/**
 * Trust Administration Service card.
 * Shows ONLY for users entitled to the service (purchased or gifted free
 * quarter): a calm scheduling card linking to Kenneth's live calendar.
 * Returns null for everyone else — never upsells, never urgencies.
 * Source of truth: GET /api/trust-admin-service/scheduling.
 */
export function DashboardTrustAdminCard() {
  const [state, setState] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchWithAuth('/api/trust-admin-service/scheduling');
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) setState(data);
      } catch {
        /* card stays hidden on any failure — it is a perk, not a notice */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (!state || !state.entitled || !state.scheduling_url) return null;

  return (
    <div className="card-trust" data-testid="trust-admin-card">
      <div className="flex items-center justify-between mb-4">
        <p className="label-trust">Trust Administration Service</p>
        <Calendar className="w-4 h-4 text-gold" />
      </div>
      <h3 className="font-serif text-xl text-navy mb-2">Schedule with Kenneth</h3>
      <p className="text-sm text-muted-foreground mb-5">
        Your service includes time with Kenneth to work through administration,
        records, and governance questions. Pick a time that suits you.
      </p>
      <a
        href={state.scheduling_url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-block px-5 py-2.5 bg-gold text-navy text-sm font-medium hover:bg-gold/90 transition-colors"
        data-testid="trust-admin-schedule-cta"
      >
        Schedule a conversation
      </a>
    </div>
  );
}