import { Button, Input, PageHelpButton } from '@/utils/sharedImports';
import { Building2, Plus, Layers, Search, Loader2 } from 'lucide-react';
import { EntityCard } from './EntityCard';
import { getEntityIcon } from './TreeNode';
import { getEntityColor, filterEntitiesBySearch } from './helpers';
import { useMemo } from 'react';

/**
 * Entities tab content for StructuresPage.
 * Contains search bar + entity grid + load-more button.
 */
export const EntitiesTab = ({
  entities,
  loading,
  entitySearch,
  setEntitySearch,
  entitiesTotal,
  loadingMoreEntities,
  handleLoadMoreEntities,
  viewMode,
  getTrustName,
  navigate,
  onCreateEntity,
}) => {
  const filteredEntities = useMemo(
    () => filterEntitiesBySearch(entities, entitySearch),
    [entities, entitySearch]
  );

  return (
    <>
      {/* Search bar */}
      <div className="mb-4 relative">
        <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
        <Input
          value={entitySearch}
          onChange={(e) => setEntitySearch(e.target.value)}
          placeholder="Search entities by name..."
          className="pl-9 input-trust max-w-md"
          data-testid="entity-search"
        />
      </div>

      {/* Loading state */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map(i => (
            <div key={i} className="card-trust">
              <div className="skeleton h-12 w-12 mb-4"></div>
              <div className="skeleton h-6 w-32 mb-2"></div>
              <div className="skeleton h-4 w-24"></div>
            </div>
          ))}
        </div>
      ) : filteredEntities.length === 0 ? (
        /* Empty state */
        <div className="card-trust text-center py-12" data-testid="entities-empty-state">
          <Building2 className="w-12 h-12 text-navy/30 mx-auto mb-4" />
          <h3 className="font-serif text-xl text-navy mb-2">
            {entitySearch ? 'No Matching Entities' : 'No Entities Yet'}
          </h3>
          <p className="text-muted-foreground mb-4">
            {entitySearch ? 'Try a different search term' : 'Add your first trust or LLC to get started'}
          </p>
          {!entitySearch && (
            <Button onClick={onCreateEntity} className="btn-secondary">Create Entity</Button>
          )}
        </div>
      ) : (
        /* Entity grid */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredEntities.map(entity => (
            <EntityCard
              key={entity.entity_id}
              entity={entity}
              viewMode={viewMode}
              getTrustName={getTrustName}
              getEntityColor={getEntityColor}
              getEntityIcon={getEntityIcon}
              onClick={() => navigate(`/entities/${entity.entity_id}`)}
            />
          ))}
        </div>
      )}

      {/* Load more button */}
      {filteredEntities.length > 0 && filteredEntities.length < entitiesTotal && !entitySearch && (
        <div className="flex justify-center mt-6">
          <Button onClick={handleLoadMoreEntities} disabled={loadingMoreEntities} className="btn-secondary" data-testid="load-more-entities">
            {loadingMoreEntities ? 'Loading...' : `Load More (${entitiesTotal - entities.length} remaining)`}
          </Button>
        </div>
      )}
    </>
  );
};