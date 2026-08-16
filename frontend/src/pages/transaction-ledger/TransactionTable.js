/**
 * Transaction table — presentational component.
 *
 * All state (selection, loading, filters) is owned by the parent and passed in
 * via props. This component only renders rows and forwards user actions.
 */
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  ArrowUpRight, ArrowDownLeft, FileSpreadsheet, Trash2, Edit2,
  Loader2, AlertTriangle, Link2, FileText, Building2,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { classificationColors } from './constants';

const safeFormat = (isoDate) => {
  if (!isoDate) return '—';
  try { return format(parseISO(isoDate), 'MMM d, yyyy'); } catch { return String(isoDate); }
};

export default function TransactionTable({
  loading,
  entities,
  filtered,
  total,
  selectedIds,
  thresholdAlertByTxn,
  onToggleSelect,
  onToggleSelectAll,
  onEdit,
  onDelete,
  onLinkMinutes,
  onNavigateToEntities,
}) {
  if (loading) {
    return (
      <div className="border border-border overflow-hidden bg-card">
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (entities.length === 0) {
    return (
      <div className="border border-border overflow-hidden bg-card">
        <div className="card-trust p-12 flex flex-col items-center justify-center text-center">
          <Building2 className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-muted-foreground font-medium">No entities yet</p>
          <p className="text-sm text-muted-foreground/70 mt-1 mb-4">
            Add a trust entity to start recording transactions.
          </p>
          <Button onClick={onNavigateToEntities} className="btn-primary">
            <Building2 className="w-4 h-4 mr-2" /> Add Entity
          </Button>
        </div>
      </div>
    );
  }

  if (filtered.length === 0) {
    return (
      <div className="border border-border overflow-hidden bg-card">
        <div className="text-center py-16 px-4">
          <FileSpreadsheet className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-muted-foreground font-medium">No transactions yet</p>
          <p className="text-sm text-muted-foreground/70 mt-1">
            Add transactions manually or import a bank statement CSV
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-border overflow-hidden bg-card">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="p-3 text-left w-10">
                <Checkbox
                  checked={selectedIds.size === filtered.length && filtered.length > 0}
                  onCheckedChange={onToggleSelectAll}
                  data-testid="select-all-checkbox"
                />
              </th>
              <th className="p-3 text-left font-medium text-muted-foreground">Date</th>
              <th className="p-3 text-left font-medium text-muted-foreground">Entity</th>
              <th className="p-3 text-right font-medium text-muted-foreground">Amount</th>
              <th className="p-3 text-left font-medium text-muted-foreground">From / To</th>
              <th className="p-3 text-left font-medium text-muted-foreground">Classification</th>
              <th className="p-3 text-left font-medium text-muted-foreground">Memo</th>
              <th className="p-3 text-center font-medium text-muted-foreground w-32">Threshold</th>
              <th className="p-3 text-center font-medium text-muted-foreground w-24">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t) => (
              <tr
                key={t.transaction_id}
                className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                data-testid={`transaction-row-${t.transaction_id}`}
              >
                <td className="p-3">
                  <Checkbox
                    checked={selectedIds.has(t.transaction_id)}
                    onCheckedChange={() => onToggleSelect(t.transaction_id)}
                  />
                </td>
                <td className="p-3 whitespace-nowrap text-foreground">{safeFormat(t.date)}</td>
                <td className="p-3 text-foreground whitespace-nowrap">{t.entity_name}</td>
                <td className="p-3 text-right whitespace-nowrap font-medium">
                  <span className={t.direction === 'inflow' ? 'text-success' : 'text-error'}>
                    {t.direction === 'inflow' ? '+' : '-'}$
                    {t.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </span>
                </td>
                <td className="p-3 text-muted-foreground text-xs max-w-[160px] truncate">
                  {t.direction === 'outflow' ? (
                    <span>{t.source_account} <ArrowUpRight className="w-3 h-3 inline" /> {t.destination_account}</span>
                  ) : (
                    <span>{t.source_account} <ArrowDownLeft className="w-3 h-3 inline" /> {t.destination_account}</span>
                  )}
                </td>
                <td className="p-3">
                  <span className={`inline-block px-2 py-0.5 text-xs font-medium ${classificationColors[t.governance_classification] || 'bg-muted text-muted-foreground'}`}>
                    {t.governance_classification}
                  </span>
                </td>
                <td className="p-3 text-muted-foreground text-xs max-w-[200px] truncate">{t.purpose_memo}</td>
                <td className="p-3 text-center">
                  {(() => {
                    const alert = thresholdAlertByTxn.get(t.transaction_id);
                    if (t.linked_minutes_id) {
                      return (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-success/10 text-success" title="Linked to minutes">
                          <FileText className="w-3 h-3" /> Linked
                        </span>
                      );
                    }
                    if (alert) {
                      return (
                        <div className="flex flex-col items-center gap-1">
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-warning/10 text-warning" title={alert.description}>
                            <AlertTriangle className="w-3 h-3" /> Exceeded
                          </span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-1.5 text-xs text-navy hover:text-navy/70"
                            onClick={() => onLinkMinutes(t)}
                            data-testid={`link-minutes-${t.transaction_id}`}
                          >
                            <Link2 className="w-3 h-3 mr-1" /> Link Minutes
                          </Button>
                        </div>
                      );
                    }
                    return null;
                  })()}
                </td>
                <td className="p-3 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <Button variant="ghost" size="sm" onClick={() => onEdit(t)} data-testid={`edit-txn-${t.transaction_id}`}>
                      <Edit2 className="w-4 h-4 text-muted-foreground hover:text-navy" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => onDelete(t.transaction_id)} data-testid={`delete-txn-${t.transaction_id}`}>
                      <Trash2 className="w-4 h-4 text-muted-foreground hover:text-error" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}