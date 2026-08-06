import { ArrowRightLeft, TrendingUp, History } from 'lucide-react';
import { formatDate } from './constants';

// ========== TRANSFERS TAB ==========
export function TransfersTab({ overviewData }) {
  return (
    <div className="card-trust overflow-hidden">
      <div className="p-4 border-b border-border flex items-center gap-2">
        <History className="w-4 h-4 text-navy dark:text-gold" />
        <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Transfer History</h2>
      </div>

      {!overviewData?.recent_transfers?.length ? (
        <div className="p-8 text-center">
          <ArrowRightLeft className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
          <p className="text-muted-foreground">No transfers recorded yet</p>
          <p className="text-sm text-muted-foreground mt-2">Transfers will appear here when units are moved between holders</p>
        </div>
      ) : (
        <div className="divide-y divide-border">
          {overviewData.recent_transfers.map((transfer) => (
            <div key={transfer.transfer_id} className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 bg-gold/10 dark:bg-gold/20 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-gold" />
                </div>
                <div>
                  <p className="font-medium text-navy dark:text-foreground">
                    {transfer.from_holder ? (
                      <>{transfer.from_holder} → {transfer.to_holder}</>
                    ) : (
                      <>New issuance to {transfer.to_holder}</>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">{transfer.reason || 'No reason specified'}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="font-mono text-navy dark:text-foreground">{transfer.units} units</p>
                <p className="text-xs text-muted-foreground font-mono">{formatDate(transfer.created_at)}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default TransfersTab;