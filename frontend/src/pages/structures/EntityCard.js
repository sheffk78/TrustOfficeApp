import { ChevronRight } from 'lucide-react';

export function EntityCard({ entity, viewMode, getTrustName, getEntityColor, getEntityIcon, onClick }) {
  return (
    <div
      key={entity.entity_id}
      onClick={onClick}
      className="card-trust hover:border-navy/30 cursor-pointer transition-colors group"
      data-testid={`entity-card-${entity.entity_id}`}
    >
      <div className="flex items-start justify-between mb-4">
        <div className={`w-12 h-12 flex items-center justify-center ${getEntityColor(entity.entity_type)}`}>
          {getEntityIcon(entity.entity_type)}
        </div>
        <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-navy transition-colors" />
      </div>

      {viewMode === 'all-trusts' && entity.trust_id && (
        <span
          className="inline-block text-[10px] font-medium px-2 py-0.5 rounded-full bg-navy/10 text-navy mb-2"
          data-testid={`trust-badge-${entity.entity_id}`}
        >
          {getTrustName(entity.trust_id)}
        </span>
      )}

      <h3 className="font-serif text-lg text-navy mb-1">{entity.name}</h3>
      <p className="font-mono text-xs text-muted-foreground uppercase tracking-widest mb-3">
        {entity.entity_type}
      </p>

      {entity.legal_name && (
        <p className="text-sm text-muted-foreground truncate">{entity.legal_name}</p>
      )}

      <div className="mt-4 pt-4 border-t border-navy/10 flex items-center gap-4">
        {entity.governing_law && (
          <span className="badge-trust">{entity.governing_law}</span>
        )}
        {entity.ein && (
          <span className="font-mono text-xs text-muted-foreground">EIN: {entity.ein}</span>
        )}
      </div>

      {entity.trustee_names && (
        <div className="mt-3 pt-3 border-t border-navy/10">
          <p className="text-xs text-muted-foreground uppercase tracking-widest mb-1">Trustees</p>
          <p className="text-sm text-navy">{entity.trustee_names}</p>
        </div>
      )}
    </div>
  );
}