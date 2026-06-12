import React from 'react';
import { Check, Pencil, X, AlertTriangle, FileText, DollarSign, Building2, Users, Loader2 } from 'lucide-react';

const TYPE_CONFIG = {
  minutes_preview: { icon: FileText, label: 'Minutes', color: 'bg-navy/10 text-navy' },
  distribution_preview: { icon: DollarSign, label: 'Distribution', color: 'bg-gold/10 text-gold' },
  asset_preview: { icon: Building2, label: 'Asset', color: 'bg-blue-500/10 text-blue-600' },
  beneficiary_preview: { icon: Users, label: 'Beneficiary', color: 'bg-emerald-500/10 text-emerald-600' },
  // Also support short names
  minutes: { icon: FileText, label: 'Minutes', color: 'bg-navy/10 text-navy' },
  distribution: { icon: DollarSign, label: 'Distribution', color: 'bg-gold/10 text-gold' },
  asset: { icon: Building2, label: 'Asset', color: 'bg-blue-500/10 text-blue-600' },
  beneficiary: { icon: Users, label: 'Beneficiary', color: 'bg-emerald-500/10 text-emerald-600' },
};

const ActionCard = ({ card, onApprove, onEdit, onDiscard, disabled }) => {
  const config = TYPE_CONFIG[card.type] || TYPE_CONFIG.minutes;
  const Icon = config.icon;
  const isDisabled = disabled || card.status === 'approved' || card.status === 'discarded';
  const isApproved = card.status === 'approved';
  const isDiscarded = card.status === 'discarded';
  const isExecuting = card.executing;

  return (
    <div className="action-card card-trust relative">
      {/* Corner marks */}
      <div className="corner-mark" />

      {/* Type badge */}
      <div className="flex items-center gap-2 mb-3">
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider border ${config.color}`}>
          <Icon className="w-3 h-3" />
          {config.label}
        </span>
        {isApproved && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider border border-gold text-gold bg-gold/5">
            <Check className="w-3 h-3" />
            Approved
          </span>
        )}
        {isDiscarded && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider border border-muted-foreground text-muted-foreground bg-muted/50">
            Discarded
          </span>
        )}
      </div>

      {/* Data summary */}
      <div className="mb-3">
        {card.title && (
          <p className="font-serif font-semibold text-sm text-foreground mb-1">{card.title}</p>
        )}
        {card.summary && (
          <p className="font-mono text-xs text-muted-foreground leading-relaxed">{card.summary}</p>
        )}
        {card.amount && (
          <p className="font-mono text-sm font-medium text-foreground mt-1">
            {typeof card.amount === 'number' ? `$${card.amount.toLocaleString()}` : card.amount}
          </p>
        )}
        {/* Show extracted data fields if no summary */}
        {!card.summary && card.data && Object.keys(card.data).length > 0 && (
          <div className="mt-2 space-y-1">
            {Object.entries(card.data).slice(0, 5).map(([key, value]) => (
              <div key={key} className="flex items-baseline gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground min-w-[80px]">
                  {key.replace(/_/g, ' ')}
                </span>
                <span className="font-mono text-xs text-foreground">
                  {Array.isArray(value) ? value.join(', ') : String(value)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Warning callout */}
      {card.warning && (
        <div className="bg-rust/5 border border-rust/20 p-3 mb-3 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-rust flex-shrink-0 mt-0.5" />
          <p className="font-mono text-xs text-rust">{card.warning}</p>
        </div>
      )}

      {/* Execution result feedback */}
      {card.execution_result && (
        <div className={`p-3 mb-3 border ${
          card.execution_result.success
            ? 'bg-emerald-50 border-emerald-200'
            : 'bg-rust/5 border-rust/20'
        }`}>
          <p className={`font-mono text-xs ${
            card.execution_result.success ? 'text-emerald-700' : 'text-rust'
          }`}>
            {card.execution_result.success
              ? `✓ Record created (${card.execution_result.endpoint || 'record'}: ${card.execution_result.record_id || ''})`
              : `✗ Failed: ${card.execution_result.error || 'Unknown error'}`
            }
          </p>
        </div>
      )}

      {/* Action buttons */}
      {!isDisabled && !isExecuting && (
        <div className="flex items-center gap-2 pt-2 border-t border-navy/10">
          <button
            onClick={() => onApprove?.(card)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider bg-gold/10 text-gold border border-gold/30 hover:bg-gold hover:text-navy transition-colors"
            title="Approve and create record"
          >
            <Check className="w-3.5 h-3.5" />
            Approve
          </button>
          <button
            onClick={() => onEdit?.(card)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider bg-navy/5 text-navy border border-navy/20 hover:bg-navy/10 transition-colors"
            title="Edit details"
          >
            <Pencil className="w-3.5 h-3.5" />
            Edit
          </button>
          <button
            onClick={() => onDiscard?.(card)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider bg-rust/5 text-rust border border-rust/20 hover:bg-rust hover:text-white transition-colors"
            title="Discard"
          >
            <X className="w-3.5 h-3.5" />
            Discard
          </button>
        </div>
      )}

      {/* Executing state */}
      {isExecuting && (
        <div className="flex items-center gap-2 pt-2 border-t border-navy/10">
          <Loader2 className="w-4 h-4 animate-spin text-gold" />
          <span className="font-mono text-xs text-muted-foreground">Creating record...</span>
        </div>
      )}
    </div>
  );
};

export default ActionCard;