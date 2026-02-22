import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { 
  GitBranch, 
  Plus, 
  ArrowRight,
  Trash2,
  X,
  Landmark,
  Building2,
  Building
} from 'lucide-react';
import { toast } from 'sonner';

const RELATIONSHIP_TYPES = [
  { value: 'owns', label: 'Owns' },
  { value: 'controls', label: 'Controls' },
  { value: 'receives_distributions_from', label: 'Receives Distributions From' },
  { value: 'pays_compensation_to', label: 'Pays Compensation To' }
];

export default function StructurePage() {
  const { selectedTrust } = useAuth();
  const [entities, setEntities] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newRelationship, setNewRelationship] = useState({
    parent_entity_id: '',
    child_entity_id: '',
    relationship_type: 'owns',
    ownership_percentage: '',
    notes: ''
  });

  useEffect(() => {
    if (selectedTrust) {
      loadData();
    }
  }, [selectedTrust]);

  const loadData = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const [entitiesRes, relsRes] = await Promise.all([
        fetchWithAuth(`/entities?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/entity-relationships?trust_id=${selectedTrust.trust_id}`)
      ]);
      
      if (entitiesRes.ok) setEntities(await entitiesRes.json());
      if (relsRes.ok) setRelationships(await relsRes.json());
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRelationship = async () => {
    if (!selectedTrust || !newRelationship.parent_entity_id || !newRelationship.child_entity_id) {
      toast.error('Please select both entities');
      return;
    }
    if (newRelationship.parent_entity_id === newRelationship.child_entity_id) {
      toast.error('Cannot create relationship with same entity');
      return;
    }
    try {
      const payload = {
        trust_id: selectedTrust.trust_id,
        ...newRelationship,
        ownership_percentage: newRelationship.ownership_percentage 
          ? parseFloat(newRelationship.ownership_percentage) 
          : null
      };
      const response = await fetchWithAuth('/entity-relationships', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      if (response.ok) {
        toast.success('Relationship created');
        setShowModal(false);
        setNewRelationship({
          parent_entity_id: '',
          child_entity_id: '',
          relationship_type: 'owns',
          ownership_percentage: '',
          notes: ''
        });
        loadData();
      }
    } catch (error) {
      toast.error('Failed to create relationship');
    }
  };

  const handleDeleteRelationship = async (relationshipId) => {
    if (!confirm('Delete this relationship?')) return;
    try {
      const response = await fetchWithAuth(`/entity-relationships/${relationshipId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        toast.success('Relationship deleted');
        loadData();
      }
    } catch (error) {
      toast.error('Failed to delete relationship');
    }
  };

  const getEntityName = (entityId) => {
    const entity = entities.find(e => e.entity_id === entityId);
    return entity?.name || 'Unknown';
  };

  const getEntityIcon = (entityId) => {
    const entity = entities.find(e => e.entity_id === entityId);
    switch (entity?.entity_type) {
      case 'Trust': return <Landmark className="w-4 h-4" />;
      case 'Holding LLC': return <Building2 className="w-4 h-4" />;
      case 'Operating LLC': return <Building className="w-4 h-4" />;
      default: return <Building2 className="w-4 h-4" />;
    }
  };

  const formatRelationshipType = (type) => {
    return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  // Build a simple tree view
  const buildTree = () => {
    if (entities.length === 0) return [];
    
    // Find root entities (those that are not children of any relationship)
    const childIds = new Set(relationships.map(r => r.child_entity_id));
    const roots = entities.filter(e => !childIds.has(e.entity_id));
    
    // If no roots, use first entity
    if (roots.length === 0 && entities.length > 0) {
      return [entities[0]];
    }
    
    return roots;
  };

  const getChildren = (entityId) => {
    return relationships
      .filter(r => r.parent_entity_id === entityId)
      .map(r => ({
        relationship: r,
        entity: entities.find(e => e.entity_id === r.child_entity_id)
      }))
      .filter(item => item.entity);
  };

  const renderTreeNode = (entity, level = 0) => {
    const children = getChildren(entity.entity_id);
    
    return (
      <div key={entity.entity_id} className={`${level > 0 ? 'ml-8 border-l border-navy/20 pl-4' : ''}`}>
        <div className="flex items-center gap-3 py-2">
          <div className="w-8 h-8 bg-navy/10 flex items-center justify-center text-navy">
            {getEntityIcon(entity.entity_id)}
          </div>
          <div>
            <p className="font-medium text-navy">{entity.name}</p>
            <p className="font-mono text-xs text-muted-foreground">{entity.entity_type}</p>
          </div>
        </div>
        {children.map(({ relationship, entity: childEntity }) => (
          <div key={relationship.relationship_id}>
            <div className="ml-4 flex items-center gap-2 py-1 text-sm text-muted-foreground">
              <ArrowRight className="w-3 h-3" />
              <span className="font-mono text-xs">{formatRelationshipType(relationship.relationship_type)}</span>
              {relationship.ownership_percentage && (
                <span className="badge-trust">{relationship.ownership_percentage}%</span>
              )}
            </div>
            {renderTreeNode(childEntity, level + 1)}
          </div>
        ))}
      </div>
    );
  };

  const rootEntities = buildTree();

  return (
    <div className="main-layout" data-testid="structure-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Entity Structure</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'} • Ownership & Relationships
              </p>
            </div>
            <Button 
              onClick={() => setShowModal(true)} 
              className="btn-primary"
              disabled={entities.length < 2}
              data-testid="add-relationship-btn"
            >
              <Plus className="w-4 h-4 mr-2" /> Add Relationship
            </Button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Hierarchy View */}
            <div className="card-trust">
              <h2 className="font-serif text-lg text-navy mb-4">Hierarchy</h2>
              {loading ? (
                <div className="space-y-4">
                  <div className="skeleton h-10 w-full"></div>
                  <div className="skeleton h-10 w-3/4 ml-8"></div>
                </div>
              ) : entities.length === 0 ? (
                <div className="text-center py-8">
                  <GitBranch className="w-8 h-8 text-navy/30 mx-auto mb-2" />
                  <p className="text-muted-foreground">No entities yet</p>
                </div>
              ) : rootEntities.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-muted-foreground">All entities are linked</p>
                  {entities.map(e => renderTreeNode(e))}
                </div>
              ) : (
                <div className="space-y-2">
                  {rootEntities.map(entity => renderTreeNode(entity))}
                </div>
              )}
            </div>

            {/* Relationships Table */}
            <div className="card-trust">
              <h2 className="font-serif text-lg text-navy mb-4">Relationships</h2>
              {loading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="skeleton h-16 w-full"></div>
                  ))}
                </div>
              ) : relationships.length === 0 ? (
                <div className="text-center py-8">
                  <GitBranch className="w-8 h-8 text-navy/30 mx-auto mb-2" />
                  <p className="text-muted-foreground">No relationships defined</p>
                  {entities.length >= 2 && (
                    <Button onClick={() => setShowModal(true)} className="btn-secondary mt-4">
                      Add First Relationship
                    </Button>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  {relationships.map(rel => (
                    <div 
                      key={rel.relationship_id}
                      className="p-4 border border-navy/10 flex items-center justify-between"
                      data-testid={`relationship-${rel.relationship_id}`}
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2">
                          {getEntityIcon(rel.parent_entity_id)}
                          <span className="font-medium text-sm">{getEntityName(rel.parent_entity_id)}</span>
                        </div>
                        <div className="flex items-center gap-2 px-3">
                          <ArrowRight className="w-4 h-4 text-muted-foreground" />
                          <span className="font-mono text-xs text-muted-foreground">
                            {formatRelationshipType(rel.relationship_type)}
                          </span>
                          {rel.ownership_percentage && (
                            <span className="badge-trust">{rel.ownership_percentage}%</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {getEntityIcon(rel.child_entity_id)}
                          <span className="font-medium text-sm">{getEntityName(rel.child_entity_id)}</span>
                        </div>
                      </div>
                      <Button
                        onClick={() => handleDeleteRelationship(rel.relationship_id)}
                        variant="ghost"
                        size="sm"
                        className="text-error hover:text-error hover:bg-error/10"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Create Relationship Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white p-6 w-full max-w-md corner-mark" data-testid="add-relationship-modal">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-serif text-xl text-navy">Add Relationship</h2>
              <button onClick={() => setShowModal(false)} className="text-navy hover:text-gold">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="label-trust mb-2 block">From Entity</label>
                <select
                  value={newRelationship.parent_entity_id}
                  onChange={(e) => setNewRelationship({ ...newRelationship, parent_entity_id: e.target.value })}
                  className="input-trust w-full"
                  data-testid="parent-entity-select"
                >
                  <option value="">Select entity...</option>
                  {entities.map(e => (
                    <option key={e.entity_id} value={e.entity_id}>{e.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label-trust mb-2 block">Relationship Type</label>
                <select
                  value={newRelationship.relationship_type}
                  onChange={(e) => setNewRelationship({ ...newRelationship, relationship_type: e.target.value })}
                  className="input-trust w-full"
                  data-testid="relationship-type-select"
                >
                  {RELATIONSHIP_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label-trust mb-2 block">To Entity</label>
                <select
                  value={newRelationship.child_entity_id}
                  onChange={(e) => setNewRelationship({ ...newRelationship, child_entity_id: e.target.value })}
                  className="input-trust w-full"
                  data-testid="child-entity-select"
                >
                  <option value="">Select entity...</option>
                  {entities.map(e => (
                    <option key={e.entity_id} value={e.entity_id}>{e.name}</option>
                  ))}
                </select>
              </div>

              {newRelationship.relationship_type === 'owns' && (
                <div>
                  <label className="label-trust mb-2 block">Ownership Percentage</label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={newRelationship.ownership_percentage}
                    onChange={(e) => setNewRelationship({ ...newRelationship, ownership_percentage: e.target.value })}
                    placeholder="e.g., 100"
                    className="input-trust w-full"
                    data-testid="ownership-percentage"
                  />
                </div>
              )}

              <div>
                <label className="label-trust mb-2 block">Notes (Optional)</label>
                <input
                  value={newRelationship.notes}
                  onChange={(e) => setNewRelationship({ ...newRelationship, notes: e.target.value })}
                  placeholder="Add notes..."
                  className="input-trust w-full"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <Button onClick={() => setShowModal(false)} variant="outline" className="flex-1 btn-secondary">
                  Cancel
                </Button>
                <Button onClick={handleCreateRelationship} className="flex-1 btn-primary" data-testid="submit-relationship-btn">
                  Add Relationship
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
