import { ChevronRight, Trash2, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatRelationshipType } from './helpers';

export function RelationshipItem({ rel, getEntityById, getEntityColor, getEntityIcon, onDelete }) {
  const parent = getEntityById(rel.parent_entity_id);
  const child = getEntityById(rel.child_entity_id);

  return (
    <div key={rel.relationship_id} className="p-3 border border-navy/10 hover:border-navy/20 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <div className={`w-6 h-6 flex items-center justify-center flex-shrink-0 ${getEntityColor(parent?.entity_type)}`}>
            {getEntityIcon(parent?.entity_type)}
          </div>
          <span className="font-medium text-navy truncate">{parent?.name}</span>
          <ArrowRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
          <div className={`w-6 h-6 flex items-center justify-center flex-shrink-0 ${getEntityColor(child?.entity_type)}`}>
            {getEntityIcon(child?.entity_type)}
          </div>
          <span className="font-medium text-navy truncate">{child?.name}</span>
        </div>
        <Button
          onClick={onDelete}
          variant="ghost"
          size="sm"
          className="text-error hover:text-error hover:bg-error/10 flex-shrink-0"
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      </div>
      <div className="mt-2 flex items-center gap-2 text-sm">
        <span className="font-mono text-xs text-muted-foreground">
          {formatRelationshipType(rel.relationship_type)}
        </span>
        {rel.ownership_percentage && (
          <span className="badge-trust">{rel.ownership_percentage}%</span>
        )}
        {rel.notes && (
          <span className="text-muted-foreground truncate">{rel.notes}</span>
        )}
      </div>
    </div>
  );
}