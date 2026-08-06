import { useState, useCallback } from 'react';
import { fetchWithAuth, toast, showError } from '@/utils/sharedImports';

const EMPTY_ENTITY = { name: '', entity_type: 'Trust', legal_name: '', governing_law: '' };
const EMPTY_RELATIONSHIP = {
  parent_entity_id: '', child_entity_id: '',
  relationship_type: 'owns', ownership_percentage: '', notes: '',
};

/**
 * Custom hook: entity + relationship create/delete mutations for the
 * Structures page. Keeps modal form state and submission handlers together
 * so the main component body stays flat.
 */
export const useStructuresMutations = ({ selectedTrust, trusts, viewMode, entities, loadData }) => {
  const [showEntityModal, setShowEntityModal] = useState(false);
  const [showRelationshipModal, setShowRelationshipModal] = useState(false);
  const [formLoading, setFormLoading] = useState(false);

  const [entitySearch, setEntitySearch] = useState('');
  const [relModalTrustFilter, setRelModalTrustFilter] = useState('');
  const [isTrustToTrust, setIsTrustToTrust] = useState(false);
  const [collapsedTrustGroups, setCollapsedTrustGroups] = useState({});
  const [entityModalTrustId, setEntityModalTrustId] = useState('');

  const [newEntity, setNewEntity] = useState(EMPTY_ENTITY);
  const [newRelationship, setNewRelationship] = useState(EMPTY_RELATIONSHIP);

  const toggleTrustGroup = useCallback((trustId) => {
    setCollapsedTrustGroups(prev => ({ ...prev, [trustId]: !prev[trustId] }));
  }, []);

  // ─── Resolve the trust_id for an entity creation ───────────────────
  const resolveEntityTrustId = () => {
    if (viewMode === 'all-trusts') {
      if (!entityModalTrustId) { toast.error('Please select a trust'); return null; }
      return entityModalTrustId;
    }
    if (!selectedTrust || !newEntity.name) { toast.error('Entity name is required'); return null; }
    return selectedTrust.trust_id;
  };

  const handleCreateEntity = async () => {
    if (!newEntity.name) { toast.error('Entity name is required'); return; }
    const trustId = resolveEntityTrustId();
    if (!trustId) return;
    setFormLoading(true);
    try {
      const response = await fetchWithAuth('/entities', {
        method: 'POST',
        body: JSON.stringify({ trust_id: trustId, ...newEntity }),
      });
      if (response.ok) {
        toast.success('Entity created');
        setShowEntityModal(false);
        setNewEntity(EMPTY_ENTITY);
        setEntityModalTrustId('');
        loadData();
      } else {
        const error = await response.json().catch(() => ({}));
        showError(toast, new Error(error.detail || 'Failed to create entity'),
          { operation: 'create', page: 'Structures' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'create', page: 'Structures' });
    } finally {
      setFormLoading(false);
    }
  };

  // ─── Resolve the trust_id for a relationship creation ──────────────
  const resolveRelationshipTrustId = () => {
    if (viewMode === 'all-trusts') {
      if (isTrustToTrust) {
        const parentEntity = entities.find(e => e.entity_id === newRelationship.parent_entity_id);
        if (!parentEntity) { toast.error('Please select a valid parent entity'); return null; }
        return parentEntity.trust_id;
      }
      if (!relModalTrustFilter) { toast.error('Please select a trust'); return null; }
      return relModalTrustFilter;
    }
    if (!selectedTrust) { toast.error('Please select a trust'); return null; }
    return selectedTrust.trust_id;
  };

  const validateRelationship = () => {
    if (!newRelationship.parent_entity_id || !newRelationship.child_entity_id) {
      toast.error('Please select both entities');
      return false;
    }
    if (newRelationship.parent_entity_id === newRelationship.child_entity_id) {
      toast.error('Cannot create relationship with same entity');
      return false;
    }
    return true;
  };

  const handleCreateRelationship = async () => {
    const trustId = resolveRelationshipTrustId();
    if (!trustId) return;
    if (!validateRelationship()) return;
    setFormLoading(true);
    try {
      const payload = {
        trust_id: trustId,
        ...newRelationship,
        ownership_percentage: newRelationship.ownership_percentage
          ? parseFloat(newRelationship.ownership_percentage) : null,
      };
      const response = await fetchWithAuth('/entity-relationships', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (response.ok) {
        toast.success('Relationship created');
        setShowRelationshipModal(false);
        setNewRelationship(EMPTY_RELATIONSHIP);
        setRelModalTrustFilter('');
        setIsTrustToTrust(false);
        loadData();
      } else if (response.status === 400) {
        const error = await response.json().catch(() => ({}));
        const detail = error.detail || '';
        const isCycleError = /circular|cycle|hierarchy/i.test(detail)
          || /circular|cycle|hierarchy/i.test(JSON.stringify(error));
        if (isCycleError) {
          toast.error('Cannot create this relationship — it would create a circular trust hierarchy');
        } else {
          showError(toast, new Error(detail || 'Failed to create relationship'),
            { operation: 'create', page: 'Structures' });
        }
      } else {
        const error = await response.json().catch(() => ({}));
        showError(toast, new Error(error.detail || 'Failed to create relationship'),
          { operation: 'create', page: 'Structures' });
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
      const response = await fetchWithAuth(`/entity-relationships/${relationshipId}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        toast.success('Relationship deleted');
        loadData();
      }
    } catch (error) {
      showError(toast, error, { operation: 'delete', page: 'Structures' });
    }
  };

  // ─── Open-modal helpers (pre-fill trust filters in all-trusts mode) ─
  const openEntityModal = useCallback(() => {
    if (viewMode === 'all-trusts') setEntityModalTrustId(selectedTrust?.trust_id || '');
    setShowEntityModal(true);
  }, [viewMode, selectedTrust]);

  const openRelationshipModal = useCallback(() => {
    if (viewMode === 'all-trusts') {
      setRelModalTrustFilter(selectedTrust?.trust_id || (trusts[0]?.trust_id || ''));
    }
    setShowRelationshipModal(true);
  }, [viewMode, selectedTrust, trusts]);

  return {
    // modal visibility
    showEntityModal, setShowEntityModal,
    showRelationshipModal, setShowRelationshipModal,
    formLoading,
    // entity form
    newEntity, setNewEntity,
    entityModalTrustId, setEntityModalTrustId,
    // relationship form
    newRelationship, setNewRelationship,
    relModalTrustFilter, setRelModalTrustFilter,
    isTrustToTrust, setIsTrustToTrust,
    // search + grouping
    entitySearch, setEntitySearch,
    collapsedTrustGroups, toggleTrustGroup,
    // handlers
    handleCreateEntity,
    handleCreateRelationship,
    handleDeleteRelationship,
    openEntityModal,
    openRelationshipModal,
  };
};