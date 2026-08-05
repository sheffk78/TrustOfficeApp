import { Landmark, Building2, Building, GitBranch, ArrowRight } from 'lucide-react';
import { formatRelationshipType } from './helpers';

const ENTITY_ICONS = {
  'Trust': Landmark,
  'Holding LLC': Building2,
  'Operating LLC': Building,
};

export function getEntityIcon(type) {
  const Icon = ENTITY_ICONS[type] || Building2;
  return <Icon className="w-5 h-5" />;
}

export function TreeNode({ entity, level, visited, getChildren, getEntityColor, getEntityIcon }) {
  // Cycle detection
  if (visited.has(entity.entity_id)) return null;
  const nextVisited = new Set(visited);
  nextVisited.add(entity.entity_id);

  const children = getChildren(entity.entity_id);

  return (
    <div key={entity.entity_id} className={`${level > 0 ? 'ml-8 border-l border-navy/20 pl-4' : ''}`}>
      <div className="flex items-center gap-3 py-2">
        <div className={`w-8 h-8 flex items-center justify-center ${getEntityColor(entity.entity_type)}`}>
          {getEntityIcon(entity.entity_type)}
        </div>
        <div>
          <p className="font-medium text-navy">{entity.name}</p>
          <p className="font-mono text-xs text-muted-foreground">{entity.entity_type}</p>
        </div>
      </div>
      {children.map(({ relationship, entity: childEntity }) => {
        const isTrustToTrustEdge = entity.entity_type === 'Trust' && childEntity.entity_type === 'Trust';
        const edgeLabel = isTrustToTrustEdge && relationship.relationship_type === 'receives_distributions_from'
          ? 'Beneficiary (100%)'
          : formatRelationshipType(relationship.relationship_type);
        return (
          <div key={relationship.relationship_id}>
            <div className={`ml-4 flex items-center gap-2 py-1 text-sm ${isTrustToTrustEdge ? 'text-purple-600' : 'text-muted-foreground'}`}>
              {isTrustToTrustEdge ? (
                <GitBranch className="w-3 h-3" />
              ) : (
                <ArrowRight className="w-3 h-3" />
              )}
              <span className={`font-mono text-xs ${isTrustToTrustEdge ? 'font-semibold' : ''}`}>{edgeLabel}</span>
              {relationship.ownership_percentage && !isTrustToTrustEdge && (
                <span className="badge-trust">{relationship.ownership_percentage}%</span>
              )}
            </div>
            <TreeNode
              entity={childEntity}
              level={level + 1}
              visited={nextVisited}
              getChildren={getChildren}
              getEntityColor={getEntityColor}
              getEntityIcon={getEntityIcon}
            />
          </div>
        );
      })}
    </div>
  );
}