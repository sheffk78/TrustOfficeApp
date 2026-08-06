import { Button } from '@/utils/sharedImports';
import { GitBranch, ArrowRight, ChevronRight, ChevronDown, Layers } from 'lucide-react';
import { StructuralMap } from '@/components/StructuralMap';
import { TreeNode, getEntityIcon } from './TreeNode';
import { RelationshipItem } from './RelationshipItem';
import { getEntityColor, getChildren } from './helpers';
import { useMemo } from 'react';

/**
 * Render a flat tree (no trust grouping) — used for per-trust mode
 * and all-trusts-with-cross-relationships mode.
 */
const FlatTree = ({ rootEntities, entities, relationships }) => {
  if (rootEntities.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-muted-foreground">All entities are linked</p>
        {entities.map(e => (
          <TreeNode key={e.entity_id} entity={e} level={0} visited={new Set()}
            getChildren={(eid) => getChildren(eid, entities, relationships)}
            getEntityColor={getEntityColor} getEntityIcon={getEntityIcon} />
        ))}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {rootEntities.map(entity => (
        <TreeNode key={entity.entity_id} entity={entity} level={0} visited={new Set()}
          getChildren={(eid) => getChildren(eid, entities, relationships)}
          getEntityColor={getEntityColor} getEntityIcon={getEntityIcon} />
      ))}
    </div>
  );
};

/**
 * Render tree grouped by trust — used in all-trusts mode when there are
 * no cross-trust relationships.
 */
const GroupedByTrustTree = ({
  groupedRoots,
  getTrustName,
  countEntitiesByTrust,
  collapsedTrustGroups,
  toggleTrustGroup,
  entities,
  relationships,
}) => (
  <div className="space-y-4">
    {Object.entries(groupedRoots).map(([trustId, trustRoots]) => {
      const trustName = getTrustName(trustId === 'unknown' ? null : trustId);
      const entityCount = countEntitiesByTrust(trustId);
      const isCollapsed = collapsedTrustGroups[trustId];
      return (
        <div key={trustId} className="border border-navy/10 rounded-lg overflow-hidden">
          <div
            className="flex items-center gap-2 px-4 py-3 bg-navy/5 cursor-pointer hover:bg-navy/10 transition-colors"
            onClick={() => toggleTrustGroup(trustId)}
            data-testid={`trust-group-header-${trustId}`}
          >
            {isCollapsed ? <ChevronRight className="w-4 h-4 text-navy" /> : <ChevronDown className="w-4 h-4 text-navy" />}
            <Layers className="w-4 h-4 text-navy" />
            <span className="font-medium text-navy">
              {trustName} ({entityCount} {entityCount === 1 ? 'entity' : 'entities'})
            </span>
          </div>
          {!isCollapsed && (
            <div className="p-4 space-y-2">
              {trustRoots.map(entity => (
                <TreeNode
                  key={entity.entity_id}
                  entity={entity}
                  level={0}
                  visited={new Set()}
                  getChildren={(eid) => getChildren(eid, entities, relationships)}
                  getEntityColor={getEntityColor}
                  getEntityIcon={getEntityIcon}
                />
              ))}
            </div>
          )}
        </div>
      );
    })}
  </div>
);

/**
 * Relationships table (right column of hierarchy tab).
 */
const RelationshipsTable = ({ relationships, getEntityById, onAddRelationship, entities }) => {
  if (relationships.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-muted-foreground mb-4">No relationships defined yet</p>
        <Button onClick={onAddRelationship} className="btn-secondary" disabled={entities.length < 2}>
          Add First Relationship
        </Button>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {relationships.map(rel => (
        <RelationshipItem
          key={rel.relationship_id}
          rel={rel}
          getEntityById={getEntityById}
          getEntityColor={getEntityColor}
          getEntityIcon={getEntityIcon}
          onDelete={() => onAddRelationship(rel.relationship_id)}
        />
      ))}
    </div>
  );
};

/**
 * Hierarchy tab content for StructuresPage.
 */
export const HierarchyTab = ({
  loading,
  entities,
  relationships,
  viewMode,
  groupedRoots,
  hasCrossTrustRelationships,
  rootEntities,
  getTrustName,
  countEntitiesByTrust,
  collapsedTrustGroups,
  toggleTrustGroup,
  structuralMapEntities,
  getEntityById,
  onDeleteRelationship,
  onAddRelationship,
}) => {
  if (loading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-trust">
          <div className="skeleton h-6 w-24 mb-4"></div>
          <div className="skeleton h-10 w-full mb-2"></div>
          <div className="skeleton h-10 w-3/4 ml-8"></div>
        </div>
        <div className="card-trust">
          <div className="skeleton h-6 w-32 mb-4"></div>
          <div className="skeleton h-16 w-full mb-2"></div>
          <div className="skeleton h-16 w-full"></div>
        </div>
      </div>
    );
  }

  if (entities.length === 0) {
    return (
      <div className="card-trust text-center py-12" data-testid="hierarchy-empty-state">
        <GitBranch className="w-12 h-12 text-navy/30 mx-auto mb-4" />
        <h3 className="font-serif text-xl text-navy mb-2">No Entities to Show</h3>
        <p className="text-muted-foreground mb-4">Create entities first, then define their relationships</p>
        <Button onClick={() => onDeleteRelationship('entities')} className="btn-secondary">Go to Entities</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Structural Map */}
      <div className="card-trust">
        <h2 className="font-serif text-lg text-navy mb-4 flex items-center gap-2">
          <GitBranch className="w-5 h-5" /> Structural Map
        </h2>
        <StructuralMap entities={structuralMapEntities} relationships={relationships} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Hierarchy Tree */}
        <div className="card-trust">
          <h2 className="font-serif text-lg text-navy mb-4 flex items-center gap-2">
            <GitBranch className="w-5 h-5" /> Hierarchy Tree
          </h2>
          {viewMode === 'all-trusts' && groupedRoots ? (
            <GroupedByTrustTree
              groupedRoots={groupedRoots}
              getTrustName={getTrustName}
              countEntitiesByTrust={countEntitiesByTrust}
              collapsedTrustGroups={collapsedTrustGroups}
              toggleTrustGroup={toggleTrustGroup}
              entities={entities}
              relationships={relationships}
            />
          ) : (
            <FlatTree rootEntities={rootEntities} entities={entities} relationships={relationships} />
          )}
        </div>

        {/* Relationships Table */}
        <div className="card-trust">
          <h2 className="font-serif text-lg text-navy mb-4 flex items-center gap-2">
            <ArrowRight className="w-5 h-5" /> Relationships
          </h2>
          <RelationshipsTable
            relationships={relationships}
            getEntityById={getEntityById}
            onAddRelationship={onAddRelationship}
            entities={entities}
          />
        </div>
      </div>
    </div>
  );
};