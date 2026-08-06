import { useState, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  useAuth, Sidebar, MobileBottomNav, Button, Tabs, TabsContent, TabsList, TabsTrigger,
  PageHelpButton, fetchWithAuth, toast,
} from '@/utils/sharedImports';
import { SeparationAlertsPanel } from '@/components/SeparationAlertsPanel';
import {
  Building2, Plus, GitBranch, ShieldAlert, Loader2, FileDown, Layers,
} from 'lucide-react';

import { SeparationTab } from './structures/SeparationTab';
import { EntitiesTab } from './structures/EntitiesTab';
import { HierarchyTab } from './structures/HierarchyTab';
import { getEntityIcon } from './structures/TreeNode';
import { EntityModal, RelationshipModal } from './structures/Modals';
import { useStructuresData } from './structures/useStructuresData';
import { useStructuresMutations } from './structures/useStructuresMutations';
import {
  getEntityColor, buildTree, getChildren, detectCrossTrustRelationships,
  groupRootsByTrust,
} from './structures/helpers';

const VIEW_MODE_OPTIONS = [
  { mode: 'per-trust', label: 'This Trust', hasIcon: false },
  { mode: 'all-trusts', label: 'All Trusts', hasIcon: true },
];

export default function StructuresPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTrust, trusts } = useAuth();

  const activeTab = searchParams.get('tab') || 'entities';
  const [viewMode, setViewMode] = useState('per-trust');

  // ─── Data loading + audit report + tab change (custom hook) ──────────
  const {
    entities, relationships, loading, separationData, sepLoading, downloading,
    entitiesTotal, loadingMoreEntities, handleLoadMoreEntities,
    handleDownloadAuditReport, handleTabChange, loadData,
  } = useStructuresData({ selectedTrust, trusts, viewMode, activeTab, setSearchParams });

  // ─── Create/delete mutations + modal form state (custom hook) ───────
  const mut = useStructuresMutations({
    selectedTrust, trusts, viewMode, entities, loadData,
  });

  // ─── Derived data ─────────────────────────────────────────────────
  const trustMap = useMemo(() => {
    const map = {};
    if (trusts && trusts.length > 0) {
      trusts.forEach(t => { map[t.trust_id] = t.trust_name || t.name || 'Unknown Trust'; });
    }
    return map;
  }, [trusts]);

  const getTrustName = useCallback((trustId) => {
    if (trustId === null || trustId === undefined) return 'Unknown Trust';
    return trustMap[trustId] || 'Unknown Trust';
  }, [trustMap]);

  const getEntityById = useCallback(
    (entityId) => entities.find(e => e.entity_id === entityId),
    [entities],
  );

  const hasCrossTrustRelationships = useMemo(() => {
    if (viewMode !== 'all-trusts') return false;
    return detectCrossTrustRelationships(relationships, entities);
  }, [viewMode, relationships, entities]);

  const structuralMapEntities = useMemo(() => {
    if (viewMode !== 'all-trusts') return entities;
    return entities.map(e => ({ ...e, name: `${getTrustName(e.trust_id)} — ${e.name}` }));
  }, [entities, viewMode, getTrustName]);

  const rootEntities = useMemo(
    () => buildTree(entities, relationships),
    [entities, relationships],
  );

  const groupedRoots = useMemo(() => {
    if (viewMode !== 'all-trusts' || hasCrossTrustRelationships) return null;
    return groupRootsByTrust(rootEntities);
  }, [viewMode, rootEntities, hasCrossTrustRelationships]);

  const countEntitiesByTrust = useCallback((trustId) => {
    return entities.filter(e => (e.trust_id || 'unknown') === trustId).length;
  }, [entities]);

  // ─── View mode change ──────────────────────────────────────────────
  const handleViewModeChange = (mode) => {
    setViewMode(mode);
    if (mode === 'all-trusts' && activeTab === 'separation') {
      setSearchParams({ tab: 'entities' });
    }
  };

  // ─── Early return: per-trust with no trust selected ────────────────
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

  // ─── Tab action button config ──────────────────────────────────────
  const tabActionConfig = {
    entities: { label: 'New Entity', icon: Plus, testId: 'create-entity-btn', onClick: mut.openEntityModal, disabled: false },
    hierarchy: { label: 'Add Relationship', icon: Plus, testId: 'add-relationship-btn', onClick: mut.openRelationshipModal, disabled: entities.length < 2 },
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
            {VIEW_MODE_OPTIONS.map(opt => (
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
              <EntitiesTab
                entities={entities}
                loading={loading}
                entitySearch={mut.entitySearch}
                setEntitySearch={mut.setEntitySearch}
                entitiesTotal={entitiesTotal}
                loadingMoreEntities={loadingMoreEntities}
                handleLoadMoreEntities={handleLoadMoreEntities}
                viewMode={viewMode}
                getTrustName={getTrustName}
                navigate={navigate}
                onCreateEntity={mut.openEntityModal}
              />
            </TabsContent>

            {/* ── Hierarchy Tab ── */}
            <TabsContent value="hierarchy">
              <HierarchyTab
                loading={loading}
                entities={entities}
                relationships={relationships}
                viewMode={viewMode}
                groupedRoots={groupedRoots}
                hasCrossTrustRelationships={hasCrossTrustRelationships}
                rootEntities={rootEntities}
                getTrustName={getTrustName}
                countEntitiesByTrust={countEntitiesByTrust}
                collapsedTrustGroups={mut.collapsedTrustGroups}
                toggleTrustGroup={mut.toggleTrustGroup}
                structuralMapEntities={structuralMapEntities}
                getEntityById={getEntityById}
                onDeleteRelationship={mut.handleDeleteRelationship}
                onAddRelationship={mut.openRelationshipModal}
              />
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
        show={mut.showEntityModal}
        onClose={(open) => mut.setShowEntityModal(open)}
        newEntity={mut.newEntity}
        setNewEntity={mut.setNewEntity}
        entityModalTrustId={mut.entityModalTrustId}
        setEntityModalTrustId={mut.setEntityModalTrustId}
        viewMode={viewMode}
        trusts={trusts}
        onSubmit={mut.handleCreateEntity}
        formLoading={mut.formLoading}
      />

      <RelationshipModal
        show={mut.showRelationshipModal}
        onClose={(open) => mut.setShowRelationshipModal(open)}
        newRelationship={mut.newRelationship}
        setNewRelationship={mut.setNewRelationship}
        relModalTrustFilter={mut.relModalTrustFilter}
        setRelModalTrustFilter={mut.setRelModalTrustFilter}
        isTrustToTrust={mut.isTrustToTrust}
        setIsTrustToTrust={mut.setIsTrustToTrust}
        viewMode={viewMode}
        trusts={trusts}
        entities={entities}
        getTrustName={getTrustName}
        onSubmit={mut.handleCreateRelationship}
        formLoading={mut.formLoading}
      />
    </div>
  );
}