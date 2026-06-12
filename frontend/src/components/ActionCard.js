import React from 'react';
import { Check, Pencil, X, AlertTriangle, FileText, DollarSign, Building2, Users } from 'lucide-react';

const TYPE_CONFIG = {
  minutes: { icon: FileText, label: 'Minutes', color: 'bg-navy/10 text-navy' },
  distribution: { icon: DollarSign, label: 'Distribution', color: 'bg-gold/10 text-gold' },
  asset: { icon: Building2, label: 'Asset', color: 'bg-blue-500/10 text-blue-600' },
  beneficiary: { icon: Users, label: 'Beneficiary', color: 'bg-emerald-500/10 text-emerald-600' },
};

const ActionCard = ({ card, onApprove, onEdit, onDiscard, disabled }) => {
  const config = TYPE_CONFIG[card.type] || TYPE_CONFIG.minutes;
  const Icon = config.icon;
  const isDisabled = disabled || card.status === 'approved' || card.status === 'discarded';

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
        {card.status === 'approved' && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider border border-gold text-gold bg-gold/5">
            Approved
          </span>
        )}
        {card.status === 'discarded' && (
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
      </div>

      {/* Warning callout */}
      {card.warning && (
        <div className="bg-rust/5 border border-rust/20 p-3 mb-3 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-rust flex-shrink-0 mt-0.5" />
          <p className="font-mono text-xs text-rust">{card.warning}</p>
        </div>
      )}

      {/* Action buttons */}
      {!isDisabled && (
        <div className="flex items-center gap-2 pt-2 border-t border-navy/10">
          <button
            onClick={() => onApprove?.(card)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider bg-gold/10 text-gold border border-gold/30 hover:bg-gold hover:text-navy transition-colors"
            title="Approve"
          >
            <Check className="w-3.5 h-3.5" />
            Approve
          </button>
          <button
            onClick={() => onEdit?.(card)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider bg-navy/5 text-navy border border-navy/20 hover:bg-navy/10 transition-colors"
            title="Edit"
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
    </div>
  );
};

export default ActionCard;