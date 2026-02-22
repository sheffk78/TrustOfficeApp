import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { 
  Building2, 
  Plus, 
  Landmark,
  Building,
  ChevronRight,
  X
} from 'lucide-react';
import { toast } from 'sonner';

const ENTITY_TYPES = [
  { value: 'Trust', label: 'Trust', icon: Landmark },
  { value: 'Holding LLC', label: 'Holding LLC', icon: Building2 },
  { value: 'Operating LLC', label: 'Operating LLC', icon: Building }
];

export default function EntitiesPage() {
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newEntity, setNewEntity] = useState({
    name: '',
    entity_type: 'Trust',
    legal_name: '',
    governing_law: ''
  });

  useEffect(() => {
    if (selectedTrust) {
      loadEntities();
    }
  }, [selectedTrust]);

  const loadEntities = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/entities?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        setEntities(await response.json());
      }
    } catch (error) {
      console.error('Failed to load entities:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateEntity = async () => {
    if (!selectedTrust || !newEntity.name) {
      toast.error('Entity name is required');
      return;
    }
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
        setShowModal(false);
        setNewEntity({ name: '', entity_type: 'Trust', legal_name: '', governing_law: '' });
        loadEntities();
      }
    } catch (error) {
      toast.error('Failed to create entity');
    }
  };

  const getEntityIcon = (type) => {
    const entityType = ENTITY_TYPES.find(t => t.value === type);
    const Icon = entityType?.icon || Building2;
    return <Icon className="w-6 h-6" />;
  };

  const getEntityColor = (type) => {
    switch (type) {
      case 'Trust': return 'bg-navy/10 text-navy';
      case 'Holding LLC': return 'bg-gold/20 text-gold';
      case 'Operating LLC': return 'bg-success/20 text-success';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  return (
    <div className="main-layout" data-testid="entities-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Entities</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'} • Trusts, LLCs & Legal Structures
              </p>
            </div>
            <Button 
              onClick={() => setShowModal(true)} 
              className="btn-primary"
              data-testid="create-entity-btn"
            >
              <Plus className="w-4 h-4 mr-2" /> New Entity
            </Button>
          </div>

          {/* Entity Grid */}
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
            <div className="card-trust text-center py-12">
              <Building2 className="w-12 h-12 text-navy/30 mx-auto mb-4" />
              <h3 className="font-serif text-xl text-navy mb-2">No Entities Yet</h3>
              <p className="text-muted-foreground mb-4">
                Add your first trust or LLC to get started
              </p>
              <Button onClick={() => setShowModal(true)} className="btn-secondary">
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
        </div>
      </main>

      {/* Create Entity Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white p-6 w-full max-w-md corner-mark" data-testid="create-entity-modal">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-serif text-xl text-navy">Create Entity</h2>
              <button onClick={() => setShowModal(false)} className="text-navy hover:text-gold">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="label-trust mb-2 block">Entity Type</label>
                <div className="grid grid-cols-3 gap-2">
                  {ENTITY_TYPES.map(type => {
                    const Icon = type.icon;
                    return (
                      <button
                        key={type.value}
                        onClick={() => setNewEntity({ ...newEntity, entity_type: type.value })}
                        className={`p-3 border text-center transition-colors ${
                          newEntity.entity_type === type.value 
                            ? 'border-navy bg-navy/5' 
                            : 'border-navy/20 hover:border-navy/40'
                        }`}
                        data-testid={`entity-type-${type.value}`}
                      >
                        <Icon className="w-5 h-5 mx-auto mb-1 text-navy" />
                        <span className="font-mono text-[10px] uppercase tracking-widest">{type.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="label-trust mb-2 block">Display Name *</label>
                <Input
                  value={newEntity.name}
                  onChange={(e) => setNewEntity({ ...newEntity, name: e.target.value })}
                  placeholder="e.g., Smith Family Trust"
                  className="input-trust"
                  data-testid="entity-name"
                />
              </div>

              <div>
                <label className="label-trust mb-2 block">Legal Name</label>
                <Input
                  value={newEntity.legal_name}
                  onChange={(e) => setNewEntity({ ...newEntity, legal_name: e.target.value })}
                  placeholder="e.g., The Smith Family Irrevocable Trust"
                  className="input-trust"
                  data-testid="entity-legal-name"
                />
              </div>

              <div>
                <label className="label-trust mb-2 block">Governing Law / State</label>
                <Input
                  value={newEntity.governing_law}
                  onChange={(e) => setNewEntity({ ...newEntity, governing_law: e.target.value })}
                  placeholder="e.g., Delaware"
                  className="input-trust"
                  data-testid="entity-governing-law"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <Button onClick={() => setShowModal(false)} variant="outline" className="flex-1 btn-secondary">
                  Cancel
                </Button>
                <Button onClick={handleCreateEntity} className="flex-1 btn-primary" data-testid="submit-entity-btn">
                  Create Entity
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
