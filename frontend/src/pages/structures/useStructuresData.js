import { useState, useEffect, useCallback } from 'react';
import { fetchWithAuth, toast, showError } from '@/utils/sharedImports';

const PAGE_SIZE = 50;
const GLOBAL_LIMIT = 200;

/**
 * Custom hook: encapsulates all data loading + mutation handlers for
 * the Structures page so the component body stays flat.
 */
export const useStructuresData = ({ selectedTrust, trusts, viewMode, activeTab, setSearchParams }) => {
  const [entities, setEntities] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [loading, setLoading] = useState(true);
  const [separationData, setSeparationData] = useState(null);
  const [sepLoading, setSepLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [entitiesTotal, setEntitiesTotal] = useState(0);
  const [loadingMoreEntities, setLoadingMoreEntities] = useState(false);

  // ─── Load entities + relationships ─────────────────────────────────
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

  // ─── Load separation data ──────────────────────────────────────────
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

  // ─── Download audit report ─────────────────────────────────────────
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

  // ─── Tab change ────────────────────────────────────────────────────
  const handleTabChange = (value) => {
    if (value === 'separation' && viewMode === 'all-trusts') return;
    setSearchParams({ tab: value });
  };

  return {
    entities,
    setEntities,
    relationships,
    loading,
    separationData,
    sepLoading,
    downloading,
    entitiesTotal,
    loadingMoreEntities,
    handleLoadMoreEntities,
    handleDownloadAuditReport,
    handleTabChange,
    loadData,
  };
};