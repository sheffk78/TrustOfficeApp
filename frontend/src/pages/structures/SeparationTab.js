import { ChevronRight, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EntityCard } from './EntityCard';

const SEP_OVERVIEW_STATS = [
  { key: 'entities', label: 'Entities', getVal: d => d.entities.length },
  { key: 'txns', label: 'Transactions (90d)', getVal: d => d.transaction_summary.total_transactions },
  {
    key: 'alerts', label: 'Active Alerts',
    getVal: d => d.alert_summary.total_active,
    getClass: d => d.alert_summary.total_active > 0 ? 'text-error' : 'text-success',
  },
  {
    key: 'netFlow', label: 'Net Flow (90d)',
    getVal: d => `$${(d.transaction_summary.total_inflows - d.transaction_summary.total_outflows).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
    getClass: d => (d.transaction_summary.total_inflows - d.transaction_summary.total_outflows) >= 0 ? 'text-success' : 'text-error',
  },
];

function AlertBadge({ count, type, label, icon }) {
  if (count <= 0) return null;
  return (
    <span className={`w-6 h-6 rounded-full bg-${type} text-white text-[10px] font-bold flex items-center justify-center`} title={`${count} ${label}`}>
      {count}
    </span>
  );
}

function EntityVolumeBars({ ent }) {
  return (
    <div className="grid grid-cols-3 gap-3 text-center">
      <div>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Inflows</p>
        <p className="text-sm font-semibold text-success">
          ${ent.total_inflows.toLocaleString('en-US', { maximumFractionDigits: 0 })}
        </p>
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Outflows</p>
        <p className="text-sm font-semibold text-error">
          ${ent.total_outflows.toLocaleString('en-US', { maximumFractionDigits: 0 })}
        </p>
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Txns</p>
        <p className="text-sm font-semibold text-foreground">{ent.transaction_count}</p>
      </div>
    </div>
  );
}

export function SeparationTab({ separationData, sepLoading, navigate, getEntityColor, getEntityIcon }) {
  if (sepLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="w-6 h-6 animate-spin text-muted-foreground">⟳</span>
      </div>
    );
  }

  if (!separationData || separationData.entities.length === 0) {
    return (
      <div className="card-trust text-center py-12" data-testid="separation-empty-state">
        <span className="w-12 h-12 text-navy/30 mx-auto mb-4 block">⚠</span>
        <h3 className="font-serif text-xl text-navy mb-2">No Separation Data</h3>
        <p className="text-muted-foreground mb-4">
          Add entities and log transactions to see separation intelligence
        </p>
        <Button onClick={() => navigate('/transactions')} className="btn-secondary">
          Go to Transaction Ledger
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Overview Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {SEP_OVERVIEW_STATS.map(stat => (
          <div key={stat.key} className="rounded border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">{stat.label}</p>
            <p className={`text-2xl font-semibold ${stat.getClass ? stat.getClass(separationData) : 'text-foreground'}`}>
              {stat.getVal(separationData)}
            </p>
          </div>
        ))}
      </div>

      {/* Entity Cards with Separation Data */}
      <div>
        <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider mb-3">Entity Separation Status</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {separationData.entities.map(ent => (
            <div
              key={ent.entity_id}
              onClick={() => navigate(`/entities/${ent.entity_id}`)}
              className="rounded border border-border bg-card p-4 hover:border-navy/40 cursor-pointer transition-all group"
              data-testid={`sep-entity-card-${ent.entity_id}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 flex items-center justify-center ${getEntityColor(ent.entity_type)}`}>
                    {getEntityIcon(ent.entity_type)}
                  </div>
                  <div>
                    <p className="font-medium text-foreground group-hover:text-navy transition-colors">{ent.name}</p>
                    <p className="font-mono text-[10px] text-muted-foreground uppercase">{ent.entity_type}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <AlertBadge count={ent.red_alerts} type="error" label="red alert(s)" />
                  <AlertBadge count={ent.yellow_alerts} type="warning" label="yellow alert(s)" />
                  {ent.total_alerts === 0 && (
                    <span className="w-6 h-6 rounded-full bg-success text-white text-[10px] font-bold flex items-center justify-center" title="No alerts">✓</span>
                  )}
                  <ChevronRight className="w-4 h-4 text-muted-foreground" />
                </div>
              </div>
              <EntityVolumeBars ent={ent} />
            </div>
          ))}
        </div>
      </div>

      {/* Inter-Entity Transfer Flows */}
      {separationData.inter_entity_flows.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider mb-3">Inter-Entity Transfer Flows</h3>
          <div className="rounded border border-border bg-card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="p-3 text-left font-medium text-muted-foreground">From</th>
                  <th className="p-3 text-center font-medium text-muted-foreground w-16"></th>
                  <th className="p-3 text-left font-medium text-muted-foreground">To</th>
                  <th className="p-3 text-right font-medium text-muted-foreground">Total (90d)</th>
                  <th className="p-3 text-right font-medium text-muted-foreground">Count</th>
                </tr>
              </thead>
              <tbody>
                {separationData.inter_entity_flows.map((flow, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="p-3 font-medium text-foreground">{flow.source_entity_name}</td>
                    <td className="p-3 text-center"><ArrowRight className="w-4 h-4 text-muted-foreground mx-auto" /></td>
                    <td className="p-3 font-medium text-foreground">{flow.dest_entity_name}</td>
                    <td className="p-3 text-right font-semibold text-foreground">
                      ${flow.total_amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="p-3 text-right text-muted-foreground">{flow.transaction_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}