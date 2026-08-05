import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { fetchWithAuth } from '@/utils/api';
import { SeparationAlertsPanel } from '@/components/SeparationAlertsPanel';
import { StructuralMap } from '@/components/StructuralMap';
import PageHelpButton from '@/components/PageHelpButton';
import {
  Building2, Plus, ChevronRight, GitBranch, ShieldAlert, ArrowRight,
  Loader2, FileDown, Layers, ChevronDown, Search,
} from 'lucide-react';
import { toast } from 'sonner';
import { showError } from '../utils/errors';

import { ENTITY_TYPES } from './structures/constants';
import { EntityCard } from './structures/EntityCard';
import { TreeNode, getEntityIcon } from './structures/TreeNode';
import { RelationshipItem } from './structures/RelationshipItem';
import { SeparationTab } from './structures/SeparationTab';
import { EntityModal, RelationshipModal } from './structures/Modals';
import {
  getEntityColor, formatRelationshipType, buildTree,
  getChildren, detectCrossTrustRelationships, groupRootsByTrust,
  filterEntitiesBySearch,
} from './structures/helpers';

export default function StructuresPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTrust, trusts } = useAuth();

  const activeTab = searchParams.get('tab') || 'entities';
  const [viewMode, setViewMode] = useState('per-trust');

  const [entities, setEntities] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [loading, setLoading] = useState(true);
  const [separationData, setSeparationData] = useState(null);
  const [sepLoading, setSepLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [entitiesTotal, setEntitiesTotal] = useState(0);
  const [loadingMoreEntities, setLoadingMoreEntities] = useState(false);
  const PAGE_SIZE = 50;
  const GLOBAL_LIMIT = 200;

  const [showEntityModal, setShowEntityModal] = useState(false);
  const [showRelationshipModal, setShowRelationshipModal] = useState(false);
  const [formLoading, setFormLoading] = useState(false);

  const [entitySearch, setEntitySearch] = useState('');
  const [relModalTrustFilter, setRelModalTrustFilter] = useState('');
  const [isTrustToTrust, setIsTrustToTrust] = useState(false);
  const [collapsedTrustGroups, setCollapsedTrustGroups] = useState({});
  const [entityModalTrustId, setEntityModalTrustId] = useState('');

  const [newEntity, setNewEntity] = useState({ name: '', entity_type: 'Trust', legal_name: '', governing_law: '' });
  const [newRelationship, setNewRelationship] = useState({ parent_entity_id: '', child_entity_id: '', relationship_type: 'owns', ownership_percentage: '', notes: '' });

  const trustMap = useMemo(() => {
    const map = {};
    if (trusts && trusts.length > 0) {
      trusts.forEach(t => { map[t.trust_id] = t.trust_name || t.name || 'Unknown Trust'; });
    }
    return map;
  }, [trusts]);

  const getTrustName = useCallback((trustId) => {
    return trustMap[trustId] || 'Unknown Trust';
  }, [trustMap]);

  // ─── Load data ───────────────────────────────────────────────────
  const loadData = useCallback(async () => {
    if (viewMode === 'per-trust' && !selectedTrust) { setLoading(false); return; }
    setLoading(true);
    try {
      let entitiesUrl, relsUrl;
      if (viewMode === 'all-trusts') {
        entitiesUrl = `/entities?limit=${GLOBAL_LIMIT}`;
        relsUrl = `/entity-relationships?limit=${GLOBAL_LIMIT}`;
      } else {
        entitiesUrl = `/entities?trust_id=${selectedTrust.trust_id}&limit=${PAGE_SIZE}`;
        relsUrl = `/entity-relationships?trust_id=${selectedTrust.trust_id}&limit=${PAGE_SIZE}`;
      }
      const [entitiesRes, relsRes] = await Promise.all([fetchWithAuth(entitiesUrl), fetchWithAuth(relsUrl)]);
      if (entitiesRes.ok) {
        const entitiesData = await entitiesRes.json();
        setEntities(entitiesData.items || []);
        setEntitiesTotal(entitiesData.total || 0);
      }
      if (relsRes.ok) {
        const relsData = await relsRes.json();
        setRelationships(relsData.items || []);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedTrust, viewMode]);

  const handleLoadMoreEntities = async () => {
    if (viewMode === 'per-trust' && !selectedTrust) return;
    setLoadingMoreEntities(true);
    try {
      const skip = entities.length;
      const url = viewMode === 'all-trusts'
        ? `/entities?skip=${skip}&limit=${GLOBAL_LIMIT}`
        : `/entities?trust_id=${selectedTrust.trust_id}&skip=${skip}&limit=${PAGE_SIZE}`;
      const res = await fetchWithAuth(url);
      if (res.ok) {
        const data = await res.json();
        setEntities(prev => [...prev, ...(data.items || data || [])]);
        setEntitiesTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Failed to load more entities:', error);
    } finally {
      setLoadingMoreEntities(false);
    }
  };

  useEffect(() => { loadData(); }, [loadData]);

  const loadSeparationData = useCallback(async () => {
    if (!selectedTrust) return;
    setSepLoading(true);
    try {
      const res = await fetchWithAuth(`/transactions/separation-dashboard?trust_id=${selectedTrust.trust_id}&days=90`);
      if (res.ok) setSeparationData(await res.json());
    } catch { /* ignore */ } finally { setSepLoading(false); }
  }, [selectedTrust]);

  useEffect(() => {
    if (activeTab === 'separation' && selectedTrust && viewMode === 'per-trust') loadSeparationData();
  }, [activeTab, selectedTrust, loadSeparationData, viewMode]);

  const handleDownloadAuditReport = async () => {
    if (!selectedTrust) return;
    setDownloading(true);
    try {
      const res = await fetchWithAuth(`/exports/audit-defense/${selectedTrust.trust_id}?days=365`);
      if (!res.ok) throw new Error('Failed to generate report');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_defense_${selectedTrust.trust_id}_${new Date().toISOString().slice(0,10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('Audit Defense Report downloaded');
    } catch (e) {
      showError(toast, e, { operation: 'download_audit_report', page: 'Structures' });
    } finally {
      setDownloading(false);
    }
  };

  // ─── Handlers ─────────────────────────────────────────────────────
  const handleTabChange = (value) => {
    if (value === 'separation' && viewMode === 'all-trusts') return;
    setSearchParams({ tab: value });
  };

  const handleViewModeChange = (mode) => {
    setViewMode(mode);
    if (mode === 'all-trusts' && activeTab === 'separation') {
      setSearchParams({ tab: 'entities' });
    }
  };

  const handleCreateEntity = async () => {
    let trustId;
    if (viewMode === 'all-trusts') {
      if (!entityModalTrustId) { toast.error('Please select a trust'); return; }
      trustId = entityModalTrustId;
    } else {
      if (!selectedTrust || !newEntity.name) { toast.error('Entity name is required'); return; }
      trustId = selectedTrust.trust_id;
    }
    if (!newEntity.name) { toast.error('Entity name is required'); return; }
    setFormLoading(true);
    try {
      const response = await fetchWithAuth('/entities', { method: 'POST', body: JSON.stringify({ trust_id: trustId, ...newEntity }) });
      if (response.ok) {
        toast.success('Entity created');
        setShowEntityModal(false);
        setNewEntity({ name: '', entity_type: 'Trust', legal_name: '', governing_law: '' });
        setEntityModalTrustId('');
        loadData();
      } else {
        const error = await response.json().catch(() => ({}));
        showError(toast, new Error(error.detail || 'Failed to create entity'), { operation: 'create', page: 'Structures' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'create', page: 'Structures' });
    } finally {
      setFormLoading(false);
    }
  };

  const handleCreateRelationship = async () => {
    let trustId;
    if (viewMode === 'all-trusts') {
      if (isTrustToTrust) {
        const parentEntity = entities.find(e => e.entity_id === newRelationship.parent_entity_id);
        if (!parentEntity) { toast.error('Please select a valid parent entity'); return; }
        trustId = parentEntity.trust_id;
      } else {
        if (!relModalTrustFilter) { toast.error('Please select a trust'); return; }
        trustId = relModalTrustFilter;
      }
    } else {
      if (!selectedTrust) { toast.error('Please select a trust'); return; }
      trustId = selectedTrust.trust_id;
    }
    if (!newRelationship.parent_entity_id || !newRelationship.child_entity_id) { toast.error('Please select both entities'); return; }
    if (newRelationship.parent_entity_id === newRelationship.child_entity_id) { toast.error('Cannot create relationship with same entity'); return; }
    setFormLoading(true);
    try {
      const payload = {
        trust_id: trustId,
        ...newRelationship,
        ownership_percentage: newRelationship.ownership_percentage ? parseFloat(newRelationship.ownership_percentage) : null,
      };
      const response = await fetchWithAuth('/entity-relationships', { method: 'POST', body: JSON.stringify(payload) });
      if (response.ok) {
        toast.success('Relationship created');
        setShowRelationshipModal(false);
        setNewRelationship({ parent_entity_id: '', child_entity_id: '', relationship_type: 'owns', ownership_percentage: '', notes: '' });
        setRelModalTrustFilter('');
        setIsTrustToTrust(false);
        loadData();
      } else if (response.status === 400) {
        const error = await response.json().catch(() => ({}));
        const detail = error.detail || '';
        const isCycleError = /circular|cycle|hierarchy/i.test(detail) || /circular|cycle|hierarchy/i.test(JSON.stringify(error));
        if (isCycleError) {
          toast.error('Cannot create this relationship — it would create a circular trust hierarchy');
        } else {
          showError(toast, new Error(detail || 'Failed to create relationship'), { operation: 'create', page: 'Structures' });
        }
      } else {
        const error = await response.json().catch(() => ({}));
        showError(toast, new Error(error.detail || 'Failed to create relationship'), { operation: 'create', page: 'Structures' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'create', page: 'Structures' });
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteRelationship = async (relationshipId) => {
    if (!confirm('Delete this relationship?')) return;
    try {
      const response = await fetchWithAuth(`/entity-relationships/${relationshipId}`, { method: 'DELETE' });
      if (response.ok) { toast.success('Relationship deleted'); loadData(); }
    } catch (error) {
      showError(toast, error, { operation: 'delete', page: 'Structures' });
    }
  };

  // ─── Derived data ─────────────────────────────────────────────────
  const getEntityById = (entityId) => entities.find(e => e.entity_id === entityId);

  const hasCrossTrustRelationships = useMemo(() => {
    if (viewMode !== 'all-trusts') return false;
    return detectCrossTrustRelationships(relationships, entities);
  }, [viewMode, relationships, entities]);

  const filteredEntities = useMemo(() => filterEntitiesBySearch(entities, entitySearch), [entities, entitySearch]);

  const structuralMapEntities = useMemo(() => {
    if (viewMode !== 'all-trusts') return entities;
    return entities.map(e => ({ ...e, name: `${getTrustName(e.trust_id)} — ${e.name}` }));
  }, [entities, viewMode, getTrustName]);

  const rootEntities = useMemo(() => buildTree(entities, relationships), [entities, relationships]);

  const groupedRoots = useMemo(() => {
    if (viewMode !== 'all-trusts' || hasCrossTrustRelationships) return null;
    return groupRootsByTrust(rootEntities);
  }, [viewMode, rootEntities, hasCrossTrustRelationships]);

  const toggleTrustGroup = (trustId) => {
    setCollapsedTrustGroups(prev => ({ ...prev, [trustId]: !prev[trustId] }));
  };

  const countEntitiesByTrust = useCallback((trustId) => {
    return entities.filter(e => (e.trust_id || 'unknown') === trustId).length;
  }, [entities]);

  // ─── Early return: per-trust with no trust selected ───────────────
  if (viewMode === 'per-trust' && !selectedTrust) {
    return (
      <div className="main-layout" data-testid="structures-page">
        <Sidebar />
        <main className="main-content dot-grid">
          <div className="page-container">
            <div className="card-trust text-center py-16">
              <Building2 className="w-12 h-12 text-navy/30 mx-auto mb-4" />
              <h3 className="font-serif text-xl text-navy mb-2">Select a trust to manage entities</h3>
              <p className="text-muted-foreground">Choose a trust from the sidebar to view and manage its structures</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  // ─── Tab action button config ────────────────────────────────────
  const tabActionConfig = {
    entities: { label: 'New Entity', icon: Plus, testId: 'create-entity-btn', onClick: () => { if (viewMode === 'all-trusts') setEntityModalTrustId(selectedTrust?.trust_id || ''); setShowEntityModal(true); }, disabled: false },
    hierarchy: { label: 'Add Relationship', icon: Plus, testId: 'add-relationship-btn', onClick: () => { if (viewMode === 'all-trusts') setRelModalTrustFilter(selectedTrust?.trust_id || (trusts[0]?.trust_id || '')); setShowRelationshipModal(true); }, disabled: entities.length < 2 },
    separation: { label: 'Audit Defense Report', icon: FileDown, testId: 'generate-audit-report-btn', onClick: handleDownloadAuditReport, disabled: downloading || !separationData, loading: downloading, loadingLabel: 'Generating...' },
  };
  const tabAction = tabActionConfig[activeTab];

  return (
    <div className="main-layout" data-testid="structures-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between mb-6">
            <div>
              <h1 className="page-title">Trust & Entities</h1>
              <p className="page-subtitle">
                Manage trust structures, entities, and relationships — define the organizational framework of your trust
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Manage trust structures, entities, and their relationships' },
                  { text: 'Define the organizational framework of your trust' },
                  { text: 'Add entities like LLCs, partnerships, or other trusts' },
                ]}
                taPrompt="Help me understand the Structures page and how to add an entity"
              />
            </div>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center gap-1 mb-6 p-1 bg-muted rounded-lg w-fit" data-testid="view-mode-toggle">
            {[
              { mode: 'per-trust', label: 'This Trust', hasIcon: false },
              { mode: 'all-trusts', label: 'All Trusts', hasIcon: true },
            ].map(opt => (
              <button
                key={opt.mode}
                onClick={() => handleViewModeChange(opt.mode)}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  viewMode === opt.mode ? 'bg-white text-navy shadow-sm' : 'text-muted-foreground hover:text-navy'
                }`}
              >
                {opt.hasIcon && <Layers className="w-3.5 h-3.5" />}
                {opt.label}
              </button>
            ))}
          </div>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
            <div className="flex items-center justify-between mb-6">
              <TabsList className="grid w-full max-w-md grid-cols-3">
                <TabsTrigger value="entities" data-testid="tab-entities">
                  <Building2 className="w-4 h-4 mr-2" /> Entities
                </TabsTrigger>
                <TabsTrigger value="hierarchy" data-testid="tab-hierarchy">
                  <GitBranch className="w-4 h-4 mr-2" /> Hierarchy
                </TabsTrigger>
                <TabsTrigger
                  value="separation"
                  data-testid="tab-separation"
                  className={`relative ${viewMode === 'all-trusts' ? 'opacity-40 cursor-not-allowed pointer-events-none' : ''}`}
                  disabled={viewMode === 'all-trusts'}
                  title={viewMode === 'all-trusts' ? 'Select a specific trust to view separation analysis' : ''}
                >
                  <ShieldAlert className="w-4 h-4 mr-2" /> Separation
                  {viewMode === 'all-trusts' && (
                    <span className="ml-1 text-[10px] text-muted-foreground">(per-trust only)</span>
                  )}
                  {viewMode !== 'all-trusts' && separationData?.alert_summary?.total_active > 0 && (
                    <span className="ml-1.5 w-5 h-5 rounded-full bg-error text-white text-[10px] font-bold flex items-center justify-center">
                      {separationData.alert_summary.total_active}
                    </span>
                  )}
                </TabsTrigger>
              </TabsList>

              {tabAction && (
                <Button onClick={tabAction.onClick} className="btn-primary" disabled={tabAction.disabled} data-testid={tabAction.testId}>
                  {tabAction.loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <tabAction.icon className="w-4 h-4 mr-2" />}
                  {tabAction.loading ? tabAction.loadingLabel : tabAction.label}
                </Button>
              )}
            </div>

            {/* ── Entities Tab ── */}
            <TabsContent value="entities">
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
                <div className="card-trust text-center py-12" data-testid="entities-empty-state">
                  <Building2 className="w-12 h-12 text-navy/30 mx-auto mb-4" />
                  <h3 className="font-serif text-xl text-navy mb-2">
                    {entitySearch ? 'No Matching Entities' : 'No Entities Yet'}
                  </h3>
                  <p className="text-muted-foreground mb-4">
                    {entitySearch ? 'Try a different search term' : 'Add your first trust or LLC to get started'}
                  </p>
                  {!entitySearch && (
                    <Button onClick={() => setShowEntityModal(true)} className="btn-secondary">Create Entity</Button>
                  )}
                </div>
              ) : (
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

              {filteredEntities.length > 0 && filteredEntities.length < entitiesTotal && !entitySearch && (
                <div className="flex justify-center mt-6">
                  <Button onClick={handleLoadMoreEntities} disabled={loadingMoreEntities} className="btn-secondary" data-testid="load-more-entities">
                    {loadingMoreEntities ? 'Loading...' : `Load More (${entitiesTotal - entities.length} remaining)`}
                  </Button>
                </div>
              )}
            </TabsContent>

            {/* ── Hierarchy Tab ── */}
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
                  <p className="text-muted-foreground mb-4">Create entities first, then define their relationships</p>
                  <Button onClick={() => handleTabChange('entities')} className="btn-secondary">Go to Entities</Button>
                </div>
              ) : (
                <div className="space-y-6">
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
                      ) : viewMode === 'all-trusts' && hasCrossTrustRelationships ? (
                        <div>
                          {rootEntities.length === 0 ? (
                            <div className="text-center py-8">
                              <p className="text-muted-foreground mb-2">All entities are linked in a hierarchy</p>
                              {entities.map(e => (
                                <TreeNode key={e.entity_id} entity={e} level={0} visited={new Set()}
                                  getChildren={(eid) => getChildren(eid, entities, relationships)}
                                  getEntityColor={getEntityColor} getEntityIcon={getEntityIcon} />
                              ))}
                            </div>
                          ) : (
                            <div className="space-y-2">
                              {rootEntities.map(entity => (
                                <TreeNode key={entity.entity_id} entity={entity} level={0} visited={new Set()}
                                  getChildren={(eid) => getChildren(eid, entities, relationships)}
                                  getEntityColor={getEntityColor} getEntityIcon={getEntityIcon} />
                              ))}
                            </div>
                          )}
                        </div>
                      ) : rootEntities.length === 0 ? (
                        <div className="text-center py-8">
                          <p className="text-muted-foreground">All entities are linked</p>
                          {entities.map(e => (
                            <TreeNode key={e.entity_id} entity={e} level={0} visited={new Set()}
                              getChildren={(eid) => getChildren(eid, entities, relationships)}
                              getEntityColor={getEntityColor} getEntityIcon={getEntityIcon} />
                          ))}
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {rootEntities.map(entity => (
                            <TreeNode key={entity.entity_id} entity={entity} level={0} visited={new Set()}
                              getChildren={(eid) => getChildren(eid, entities, relationships)}
                              getEntityColor={getEntityColor} getEntityIcon={getEntityIcon} />
                          ))}
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
                          <Button onClick={() => setShowRelationshipModal(true)} className="btn-secondary" disabled={entities.length < 2}>
                            Add First Relationship
                          </Button>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {relationships.map(rel => (
                            <RelationshipItem
                              key={rel.relationship_id}
                              rel={rel}
                              getEntityById={getEntityById}
                              getEntityColor={getEntityColor}
                              getEntityIcon={getEntityIcon}
                              onDelete={() => handleDeleteRelationship(rel.relationship_id)}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </TabsContent>

            {/* ── Separation Tab ── */}
            <TabsContent value="separation">
              <SeparationTab
                separationData={separationData}
                sepLoading={sepLoading}
                navigate={navigate}
                getEntityColor={getEntityColor}
                getEntityIcon={getEntityIcon}
              />
              {separationData && separationData.entities.length > 0 && (
                <div className="rounded border border-border bg-card p-4 mt-6">
                  <SeparationAlertsPanel />
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </main>
      <MobileBottomNav />

      {/* Modals */}
      <EntityModal
        show={showEntityModal}
        onClose={(open) => setShowEntityModal(open)}
        newEntity={newEntity}
        setNewEntity={setNewEntity}
        entityModalTrustId={entityModalTrustId}
        setEntityModalTrustId={setEntityModalTrustId}
        viewMode={viewMode}
        trusts={trusts}
        onSubmit={handleCreateEntity}
        formLoading={formLoading}
      />

      <RelationshipModal
        show={showRelationshipModal}
        onClose={(open) => setShowRelationshipModal(open)}
        newRelationship={newRelationship}
        setNewRelationship={setNewRelationship}
        relModalTrustFilter={relModalTrustFilter}
        setRelModalTrustFilter={setRelModalTrustFilter}
        isTrustToTrust={isTrustToTrust}
        setIsTrustToTrust={setIsTrustToTrust}
        viewMode={viewMode}
        trusts={trusts}
        entities={entities}
        getTrustName={getTrustName}
        onSubmit={handleCreateRelationship}
        formLoading={formLoading}
      />
    </div>
  );
}