import { Building2 } from 'lucide-react';

const ENTITY_STYLES = {
  Trust: { icon: 'landmark', color: 'bg-navy/10 text-navy' },
  'Holding LLC': { icon: 'building2', color: 'bg-gold/20 text-gold' },
  'Operating LLC': { icon: 'building', color: 'bg-success/20 text-success' },
};

export function getEntityColor(type) {
  return ENTITY_STYLES[type]?.color || 'bg-muted text-muted-foreground';
}

export function formatRelationshipType(type) {
  return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function buildTree(entities, relationships) {
  if (entities.length === 0) return [];
  const childIds = new Set(relationships.map(r => r.child_entity_id));
  const roots = entities.filter(e => !childIds.has(e.entity_id));
  if (roots.length === 0 && entities.length > 0) {
    return [entities[0]];
  }
  return roots;
}

export function getChildren(entityId, entities, relationships) {
  return relationships
    .filter(r => r.parent_entity_id === entityId)
    .map(r => ({
      relationship: r,
      entity: entities.find(e => e.entity_id === r.child_entity_id)
    }))
    .filter(item => item.entity);
}

export function detectCrossTrustRelationships(relationships, entities) {
  return relationships.some(rel => {
    const parent = entities.find(e => e.entity_id === rel.parent_entity_id);
    const child = entities.find(e => e.entity_id === rel.child_entity_id);
    return parent && child && parent.trust_id !== child.trust_id;
  });
}

export function groupRootsByTrust(rootEntities) {
  const groups = {};
  rootEntities.forEach(entity => {
    const tid = entity.trust_id || 'unknown';
    if (!groups[tid]) groups[tid] = [];
    groups[tid].push(entity);
  });
  return groups;
}

export function filterEntitiesBySearch(entities, search) {
  if (!search.trim()) return entities;
  const query = search.toLowerCase().trim();
  return entities.filter(e => e.name?.toLowerCase().includes(query));
}