/**
 * useTrustEntityData — custom hook encapsulating the trust-entity auto-population
 * and Schedule A asset-loading logic extracted from MinutesTemplateFormPage.
 *
 * Responsibilities:
 *  - loadTrustEntityData(): fetches /entities and pre-fills formData (formation date,
 *    trustees_present) and bankData (authorized_signers) from the main Trust entity
 *    (falling back to selectedTrust from auth context).
 *  - loadScheduleAAssets(): fetches active Schedule A assets for the disposition
 *    template's asset selector.
 *  - Pre-fill disposition data from URL search params (coming from the Schedule A page).
 *  - Pre-fill property acceptance data from URL search params.
 *  - Pre-fill trustee names into compensation / resignation / conflict / emergency /
 *    distribution-notice forms whenever trustees_present is populated.
 *
 * The hook returns { trustEntity, trustEntityLoading, scheduleAAssets, loadingAssets }
 * and expects the page component to pass in the state setters so it can update form
 * state directly — preserving the exact original behaviour.
 */
import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { fetchWithAuth } from '@/utils/api';

export const useTrustEntityData = ({
  selectedTrust,
  templateType,
  searchParams,
  setFormData,
  setBankData,
  setPropertyData,
  setDispositionData,
  setTrusteeCompData,
  setTrusteeResignData,
  setConflictData,
  setEmergencyData,
  setDistributionNoticeData,
}) => {
  const [trustEntity, setTrustEntity] = useState(null);
  const [trustEntityLoading, setTrustEntityLoading] = useState(true);
  const [scheduleAAssets, setScheduleAAssets] = useState([]);
  const [loadingAssets, setLoadingAssets] = useState(false);

  // Helper: apply trustees to formData + bankData
  const applyTrustees = (trustees) => {
    if (!trustees || trustees.length === 0) return;
    setFormData((prev) => ({ ...prev, trustees_present: trustees }));
    setBankData((prev) => ({ ...prev, authorized_signers: trustees }));
  };

  // Helper: parse trustees from a string or array
  const parseTrustees = (raw) => {
    if (!raw) return [];
    return Array.isArray(raw)
      ? raw
      : String(raw).split(',').map((t) => t.trim()).filter((t) => t);
  };

  const loadTrustEntityData = async () => {
    try {
      const response = await fetchWithAuth(`/entities?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        const entities = await response.json();
        const entityList = entities.items || entities;
        const mainTrust = entityList.find((e) => e.entity_type === 'Trust');
        if (mainTrust) {
          setTrustEntity(mainTrust);

          // Auto-populate trust_formation_date from entity formation date
          if (mainTrust.formation_date) {
            const isoDate = mainTrust.formation_date.slice(0, 10);
            setFormData((prev) => ({ ...prev, trust_formation_date: isoDate }));
          } else if (selectedTrust?.start_date) {
            const isoDate = selectedTrust.start_date.slice(0, 10);
            setFormData((prev) => ({ ...prev, trust_formation_date: isoDate }));
          }

          // Auto-populate trustees from entity trustee_names field
          if (mainTrust.trustee_names) {
            applyTrustees(parseTrustees(mainTrust.trustee_names));
          } else if (selectedTrust?.trustees) {
            applyTrustees(parseTrustees(selectedTrust.trustees));
          }
        } else {
          // No Trust entity exists yet — fall back to trust data from auth context
          if (selectedTrust?.start_date) {
            const isoDate = selectedTrust.start_date.slice(0, 10);
            setFormData((prev) => ({ ...prev, trust_formation_date: isoDate }));
          }
          if (selectedTrust?.trustees) {
            applyTrustees(parseTrustees(selectedTrust.trustees));
          }
        }
      }
    } catch (error) {
      console.error('Failed to load trust entity data:', error);
    } finally {
      setTrustEntityLoading(false);
    }
  };

  const loadScheduleAAssets = async () => {
    if (!selectedTrust) return;
    setLoadingAssets(true);
    try {
      const response = await fetchWithAuth(`/schedule-a?trust_id=${selectedTrust.trust_id}&status=active`);
      if (response.ok) {
        const assets = await response.json();
        setScheduleAAssets(assets.items || assets);
      }
    } catch (error) {
      console.error('Failed to load Schedule A assets:', error);
    } finally {
      setLoadingAssets(false);
    }
  };

  // Load trust entity data when selectedTrust changes
  useEffect(() => {
    if (selectedTrust) {
      setTrustEntityLoading(true);
      loadTrustEntityData();
    }
  }, [selectedTrust]);

  // Pre-fill property acceptance data from URL params
  useEffect(() => {
    if (templateType === 'acceptance_of_property') {
      const assetName = searchParams.get('asset_name');
      if (assetName) {
        setPropertyData((prev) => ({ ...prev, property_description: assetName }));
      }
    }
  }, [templateType, searchParams]);

  // Load Schedule A assets + pre-fill disposition data from URL params
  useEffect(() => {
    if (selectedTrust && templateType === 'disposition_of_asset') {
      loadScheduleAAssets();

      const assetId = searchParams.get('asset_id');
      const assetDescription = searchParams.get('asset_description');
      const dispositionDate = searchParams.get('disposition_date');
      const dispositionReason = searchParams.get('disposition_reason');
      const dispositionValue = searchParams.get('disposition_value');
      const dispositionRecipient = searchParams.get('disposition_recipient');
      const dispositionNotes = searchParams.get('disposition_notes');

      if (assetId || assetDescription) {
        setDispositionData((prev) => ({
          ...prev,
          disposition_asset_id: assetId || '',
          disposition_asset_description: assetDescription || '',
          disposition_date: dispositionDate ? format(new Date(dispositionDate), 'MMMM d, yyyy') : prev.disposition_date,
          disposition_reason: dispositionReason || prev.disposition_reason,
          disposition_value: dispositionValue || '',
          disposition_recipient: dispositionRecipient || '',
          disposition_notes: dispositionNotes || '',
          update_schedule_a: true,
        }));
      }
    }
  }, [selectedTrust, templateType, searchParams]);

  // Pre-fill trustee names into all minutes template forms when trustees_present is populated
  const preFillTrusteeNames = (trustees) => {
    if (trustees.length === 0) return;

    // Trustee compensation: pre-fill first trustee name
    setTrusteeCompData((prev) => (prev.trustee_name ? prev : { ...prev, trustee_name: trustees[0] }));

    // Trustee resignation: pre-fill remaining trustees
    setTrusteeResignData((prev) => {
      const current = prev.remaining_trustees.filter((t) => t.trim());
      return current.length > 0 ? prev : { ...prev, remaining_trustees: [...trustees] };
    });

    // Conflict of interest: pre-fill first trustee
    setConflictData((prev) => (prev.trustee_name ? prev : { ...prev, trustee_name: trustees[0] }));

    // Emergency ratification: pre-fill first trustee
    setEmergencyData((prev) => (prev.trustee_acting ? prev : { ...prev, trustee_acting: trustees[0] }));

    // Beneficiary distribution notice: pre-fill first trustee
    setDistributionNoticeData((prev) => (prev.trustee_name ? prev : { ...prev, trustee_name: trustees[0] }));
  };

  return {
    trustEntity,
    trustEntityLoading,
    scheduleAAssets,
    loadingAssets,
    loadScheduleAAssets,
    preFillTrusteeNames,
  };
};