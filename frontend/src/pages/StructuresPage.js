import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { TrialBanner } from '@/components/TrialBanner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { fetchWithAuth } from '@/utils/api';
import { 
  Building2, 
  Plus, 
  Landmark,
  Building,
  ChevronRight,
  GitBranch,
  ArrowRight,
  Trash2,
  X,
  Loader2
} from 'lucide-react';
import { toast } from 'sonner';

const ENTITY_TYPES = [
  { value: 'Trust', label: 'Trust', icon: Landmark },
  { value: 'Holding LLC', label: 'Holding LLC', icon: Building2 },
  { value: 'Operating LLC', label: 'Operating LLC', icon: Building }
];

const RELATIONSHIP_TYPES = [
  { value: 'owns', label: 'Owns' },
  { value: 'controls', label: 'Controls' },
  { value: 'receives_distributions_from', label: 'Receives Distributions From' },
  { value: 'pays_compensation_to', label: 'Pays Compensation To' }
];

export default function StructuresPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTrust } = useAuth();
  
  // Tab state from URL
  const activeTab = searchParams.get('tab') || 'entities';
  
  // Data state
  const [entities, setEntities] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Modal states
  const [showEntityModal, setShowEntityModal] = useState(false);
  const [showRelationshipModal, setShowRelationshipModal] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  
  // Form states
  const [newEntity, setNewEntity] = useState({
    name: '',
    entity_type: 'Trust',
    legal_name: '',
    governing_law: ''
  });
  const [newRelationship, setNewRelationship] = useState({
    parent_entity_id: '',
    child_entity_id: '',
    relationship_type: 'owns',
    ownership_percentage: '',
    notes: ''
  });

  // Load data
  const loadData = useCallback(async () => {
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
  }, [selectedTrust]);

  useEffect(() => {
    if (selectedTrust) {
      loadData();
    }
  }, [selectedTrust, loadData]);

  // Tab change handler - updates URL
  const handleTabChange = (value) => {
    setSearchParams({ tab: value });
  };

  // Entity CRUD
  const handleCreateEntity = async () => {
    if (!selectedTrust || !newEntity.name) {
      toast.error('Entity name is required');
      return;
    }
    setFormLoading(true);
    try {
      const response = await fetchWithAuth('/entities', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          ...newEntity
        })
      });
      if (response.ok) {
        toast.success('Entity created');
        setShowEntityModal(false);
        setNewEntity({ name: '', entity_type: 'Trust', legal_name: '', governing_law: '' });
        loadData();
      } else {
        const error = await response.json().catch(() => ({}));
        toast.error(error.detail || 'Failed to create entity');
      }
    } catch (error) {
      toast.error('Failed to create entity');
    } finally {
      setFormLoading(false);
    }
  };

  // Relationship CRUD
  const handleCreateRelationship = async () => {
    if (!selectedTrust || !newRelationship.parent_entity_id || !newRelationship.child_entity_id) {
      toast.error('Please select both entities');
      return;
    }
    if (newRelationship.parent_entity_id === newRelationship.child_entity_id) {
      toast.error('Cannot create relationship with same entity');
      return;
    }
    setFormLoading(true);
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
        setShowRelationshipModal(false);
        setNewRelationship({
          parent_entity_id: '',
          child_entity_id: '',
          relationship_type: 'owns',
          ownership_percentage: '',
          notes: ''
        });
        loadData();
      } else {
        const error = await response.json().catch(() => ({}));
        toast.error(error.detail || 'Failed to create relationship');
      }
    } catch (error) {
      toast.error('Failed to create relationship');
    } finally {
      setFormLoading(false);
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

  // Helper functions
  const getEntityIcon = (type) => {
    switch (type) {
      case 'Trust': return <Landmark className="w-5 h-5" />;
      case 'Holding LLC': return <Building2 className="w-5 h-5" />;
      case 'Operating LLC': return <Building className="w-5 h-5" />;
      default: return <Building2 className="w-5 h-5" />;
    }
  };

  const getEntityColor = (type) => {
    switch (type) {
      case 'Trust': return 'bg-navy/10 text-navy';
      case 'Holding LLC': return 'bg-gold/20 text-gold';
      case 'Operating LLC': return 'bg-success/20 text-success';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const getEntityName = (entityId) => {
    const entity = entities.find(e => e.entity_id === entityId);
    return entity?.name || 'Unknown';
  };

  const getEntityById = (entityId) => {
    return entities.find(e => e.entity_id === entityId);
  };

  const formatRelationshipType = (type) => {
    return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  // Tree building for hierarchy
  const buildTree = () => {
    if (entities.length === 0) return [];
    const childIds = new Set(relationships.map(r => r.child_entity_id));
    const roots = entities.filter(e => !childIds.has(e.entity_id));
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
          <div className={`w-8 h-8 flex items-center justify-center ${getEntityColor(entity.entity_type)}`}>
            {getEntityIcon(entity.entity_type)}
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
    <div className="main-layout" data-testid="structures-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <TrialBanner location="structures" />
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between mb-6">
            <div>
              <h1 className="page-title">Structures</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'} • Entities & Relationships
              </p>
            </div>
          </div>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
            <div className="flex items-center justify-between mb-6">
              <TabsList className="grid w-full max-w-xs grid-cols-2">
                <TabsTrigger value="entities" data-testid="tab-entities">
                  <Building2 className="w-4 h-4 mr-2" /> Entities
                </TabsTrigger>
                <TabsTrigger value="hierarchy" data-testid="tab-hierarchy">
                  <GitBranch className="w-4 h-4 mr-2" /> Hierarchy
                </TabsTrigger>
              </TabsList>
              
              {/* Action button changes based on tab */}
              {activeTab === 'entities' ? (
                <Button 
                  onClick={() => setShowEntityModal(true)} 
                  className="btn-primary"
                  data-testid="create-entity-btn"
                >
                  <Plus className="w-4 h-4 mr-2" /> New Entity
                </Button>
              ) : (
                <Button 
                  onClick={() => setShowRelationshipModal(true)} 
                  className="btn-primary"
                  disabled={entities.length < 2}
                  data-testid="add-relationship-btn"
                >
                  <Plus className="w-4 h-4 mr-2" /> Add Relationship
                </Button>
              )}
            </div>

            {/* Entities Tab */}
            <TabsContent value="entities">
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
              ) : entities.length === 0 ? (
                <div className="card-trust text-center py-12" data-testid="entities-empty-state">
                  <Building2 className="w-12 h-12 text-navy/30 mx-auto mb-4" />
                  <h3 className="font-serif text-xl text-navy mb-2">No Entities Yet</h3>
                  <p className="text-muted-foreground mb-4">
                    Add your first trust or LLC to get started
                  </p>
                  <Button onClick={() => setShowEntityModal(true)} className="btn-secondary">
                    Create Entity
                  </Button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {entities.map(entity => (
                    <div 
                      key={entity.entity_id}
                      onClick={() => navigate(`/entities/${entity.entity_id}`)}
                      className="card-trust hover:border-navy/30 cursor-pointer transition-colors group"
                      data-testid={`entity-card-${entity.entity_id}`}
                    >
                      <div className="flex items-start justify-between mb-4">
                        <div className={`w-12 h-12 flex items-center justify-center ${getEntityColor(entity.entity_type)}`}>
                          {getEntityIcon(entity.entity_type)}
                        </div>
                        <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-navy transition-colors" />
                      </div>
                      
                      <h3 className="font-serif text-lg text-navy mb-1">{entity.name}</h3>
                      <p className="font-mono text-xs text-muted-foreground uppercase tracking-widest mb-3">
                        {entity.entity_type}
                      </p>
                      
                      {entity.legal_name && (
                        <p className="text-sm text-muted-foreground truncate">
                          {entity.legal_name}
                        </p>
                      )}
                      
                      <div className="mt-4 pt-4 border-t border-navy/10 flex items-center gap-4">
                        {entity.governing_law && (
                          <span className="badge-trust">{entity.governing_law}</span>
                        )}
                        {entity.ein && (
                          <span className="font-mono text-xs text-muted-foreground">
                            EIN: {entity.ein}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Hierarchy Tab */}
            <TabsContent value="hierarchy">
              {loading ? (
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
              ) : entities.length === 0 ? (
                <div className="card-trust text-center py-12" data-testid="hierarchy-empty-state">
                  <GitBranch className="w-12 h-12 text-navy/30 mx-auto mb-4" />
                  <h3 className="font-serif text-xl text-navy mb-2">No Entities to Show</h3>
                  <p className="text-muted-foreground mb-4">
                    Create entities first, then define their relationships
                  </p>
                  <Button onClick={() => handleTabChange('entities')} className="btn-secondary">
                    Go to Entities
                  </Button>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Hierarchy Tree */}
                  <div className="card-trust">
                    <h2 className="font-serif text-lg text-navy mb-4 flex items-center gap-2">
                      <GitBranch className="w-5 h-5" /> Hierarchy Tree
                    </h2>
                    {rootEntities.length === 0 ? (
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
                    <h2 className="font-serif text-lg text-navy mb-4 flex items-center gap-2">
                      <ArrowRight className="w-5 h-5" /> Relationships
                    </h2>
                    {relationships.length === 0 ? (
                      <div className="text-center py-8">
                        <p className="text-muted-foreground mb-4">No relationships defined yet</p>
                        <Button 
                          onClick={() => setShowRelationshipModal(true)} 
                          className="btn-secondary"
                          disabled={entities.length < 2}
                        >
                          Add First Relationship
                        </Button>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {relationships.map(rel => {
                          const parent = getEntityById(rel.parent_entity_id);
                          const child = getEntityById(rel.child_entity_id);
                          return (
                            <div 
                              key={rel.relationship_id}
                              className="p-3 border border-navy/10 hover:border-navy/20 transition-colors"
                            >
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
                                  onClick={() => handleDeleteRelationship(rel.relationship_id)}
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
                        })}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </main>
      <MobileBottomNav />

      {/* Create Entity Modal */}
      <Dialog open={showEntityModal} onOpenChange={setShowEntityModal}>
        <DialogContent className="sm:max-w-md" data-testid="entity-modal">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-navy">Create New Entity</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label className="label-trust">Entity Name *</Label>
              <Input
                value={newEntity.name}
                onChange={(e) => setNewEntity({ ...newEntity, name: e.target.value })}
                placeholder="e.g., Smith Family Trust"
                className="input-trust mt-1"
                data-testid="entity-name"
              />
            </div>
            <div>
              <Label className="label-trust">Entity Type</Label>
              <Select value={newEntity.entity_type} onValueChange={(v) => setNewEntity({ ...newEntity, entity_type: v })}>
                <SelectTrigger className="input-trust mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ENTITY_TYPES.map(t => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-trust">Legal Name (Optional)</Label>
              <Input
                value={newEntity.legal_name}
                onChange={(e) => setNewEntity({ ...newEntity, legal_name: e.target.value })}
                placeholder="Full legal name if different"
                className="input-trust mt-1"
              />
            </div>
            <div>
              <Label className="label-trust">Governing Law / Jurisdiction</Label>
              <Input
                value={newEntity.governing_law}
                onChange={(e) => setNewEntity({ ...newEntity, governing_law: e.target.value })}
                placeholder="e.g., Delaware, California"
                className="input-trust mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEntityModal(false)} className="btn-secondary">
              Cancel
            </Button>
            <Button onClick={handleCreateEntity} disabled={formLoading} className="btn-primary" data-testid="submit-entity-btn">
              {formLoading && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Create Entity
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Relationship Modal */}
      <Dialog open={showRelationshipModal} onOpenChange={setShowRelationshipModal}>
        <DialogContent className="sm:max-w-md" data-testid="relationship-modal">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-navy">Add Relationship</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label className="label-trust">Parent Entity *</Label>
              <Select value={newRelationship.parent_entity_id} onValueChange={(v) => setNewRelationship({ ...newRelationship, parent_entity_id: v })}>
                <SelectTrigger className="input-trust mt-1">
                  <SelectValue placeholder="Select parent entity" />
                </SelectTrigger>
                <SelectContent>
                  {entities.map(e => (
                    <SelectItem key={e.entity_id} value={e.entity_id}>
                      {e.name} ({e.entity_type})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-trust">Relationship Type</Label>
              <Select value={newRelationship.relationship_type} onValueChange={(v) => setNewRelationship({ ...newRelationship, relationship_type: v })}>
                <SelectTrigger className="input-trust mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RELATIONSHIP_TYPES.map(t => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-trust">Child Entity *</Label>
              <Select value={newRelationship.child_entity_id} onValueChange={(v) => setNewRelationship({ ...newRelationship, child_entity_id: v })}>
                <SelectTrigger className="input-trust mt-1">
                  <SelectValue placeholder="Select child entity" />
                </SelectTrigger>
                <SelectContent>
                  {entities
                    .filter(e => e.entity_id !== newRelationship.parent_entity_id)
                    .map(e => (
                      <SelectItem key={e.entity_id} value={e.entity_id}>
                        {e.name} ({e.entity_type})
                      </SelectItem>
                    ))
                  }
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-trust">Ownership Percentage (Optional)</Label>
              <Input
                type="number"
                value={newRelationship.ownership_percentage}
                onChange={(e) => setNewRelationship({ ...newRelationship, ownership_percentage: e.target.value })}
                placeholder="e.g., 100"
                className="input-trust mt-1"
                min="0"
                max="100"
              />
            </div>
            <div>
              <Label className="label-trust">Notes (Optional)</Label>
              <Textarea
                value={newRelationship.notes}
                onChange={(e) => setNewRelationship({ ...newRelationship, notes: e.target.value })}
                placeholder="Any additional notes..."
                className="input-trust mt-1"
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRelationshipModal(false)} className="btn-secondary">
              Cancel
            </Button>
            <Button onClick={handleCreateRelationship} disabled={formLoading} className="btn-primary" data-testid="submit-relationship-btn">
              {formLoading && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Add Relationship
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
