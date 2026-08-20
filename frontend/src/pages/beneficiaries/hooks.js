import { useState, useEffect, useCallback } from 'react';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '../../utils/errors';
import {
  makeCertificateForm,
  DEFAULT_TRANSFER_FORM,
  DEFAULT_SETTINGS_FORM,
  DEFAULT_CLASS_BENEFICIARY_FORM,
  DEFAULT_PERSON_FORM,
} from './constants';

// ========== DATA LOADING HOOK ==========
export function useBeneficiariesData(selectedTrust, onSummaryLoaded) {
  const [overviewData, setOverviewData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadOverviewData = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/beneficiaries/dashboard?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        setOverviewData(await response.json());
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Failed to load overview (${response.status})` }, { operation: 'load', page: 'Beneficiaries' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'load', page: 'Beneficiaries' });
    } finally {
      setLoading(false);
    }
  }, [selectedTrust]);

  const loadCertificatesData = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/trust-units/summary?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        const data = await response.json();
        setSummary(data);
        if (onSummaryLoaded) onSummaryLoaded(data);
        return data;
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Failed to load certificates (${response.status})` }, { operation: 'load', page: 'Beneficiaries' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'load', page: 'Beneficiaries' });
    } finally {
      setLoading(false);
    }
    return null;
  }, [selectedTrust, onSummaryLoaded]);

  useEffect(() => {
    if (selectedTrust) {
      loadOverviewData();
      loadCertificatesData();
    }
  }, [selectedTrust, loadOverviewData, loadCertificatesData]);

  return {
    overviewData,
    setOverviewData,
    summary,
    setSummary,
    loading,
    loadOverviewData,
    loadCertificatesData,
  };
}

// ========== CERTIFICATE FORM HOOK ==========
export function useCertificateForm(selectedTrust, isReadOnly, showUpgradeModal, summary, loadCertificatesData, loadOverviewData) {
  const [showCertificateModal, setShowCertificateModal] = useState(false);
  const [editingCertificate, setEditingCertificate] = useState(null);
  const [certificateForm, setCertificateForm] = useState(makeCertificateForm());

  const resetCertificateForm = useCallback(() => {
    setCertificateForm(makeCertificateForm());
    setEditingCertificate(null);
  }, []);

  const handleOpenCertificateModal = useCallback((editing = null) => {
    if (isReadOnly) {
      showUpgradeModal('issue certificates', 'button_click', 'beneficiaries_page');
      return;
    }
    if (editing) {
      setEditingCertificate(editing);
      setCertificateForm({
        holder_name: editing.holder_name,
        holder_identifier: editing.holder_identifier || '',
        holder_type: editing.holder_type || 'individual',
        holder_trust_id: editing.holder_trust_id || '',
        email: editing.email || '',
        phone: editing.phone || '',
        units: editing.units.toString(),
        issue_date: editing.issue_date?.split('T')[0] || makeCertificateForm().issue_date,
        notes: editing.notes || ''
      });
    }
    setShowCertificateModal(true);
  }, [isReadOnly, showUpgradeModal]);

  const openEditModal = useCallback((certificate) => {
    if (isReadOnly) {
      showUpgradeModal('edit certificates', 'button_click', 'beneficiaries_page');
      return;
    }
    setEditingCertificate(certificate);
    setCertificateForm({
      holder_name: certificate.holder_name,
      holder_identifier: certificate.holder_identifier || '',
      holder_type: certificate.holder_type || 'individual',
      holder_trust_id: certificate.holder_trust_id || '',
      email: certificate.email || '',
      phone: certificate.phone || '',
      units: certificate.units.toString(),
      issue_date: certificate.issue_date,
      notes: certificate.notes || ''
    });
    setShowCertificateModal(true);
  }, [isReadOnly, showUpgradeModal]);

  const handleIssueCertificate = useCallback(async () => {
    if (!certificateForm.holder_name || !certificateForm.units) {
      toast.error('Holder name and units are required');
      return;
    }
    if (certificateForm.holder_type === 'trust' && !certificateForm.holder_trust_id) {
      toast.error('Please select a trust from the dropdown');
      return;
    }

    const units = parseFloat(certificateForm.units);
    if (isNaN(units) || units <= 0) {
      toast.error('Units must be a positive number');
      return;
    }
    if (summary?.settings?.allow_fractional === false && !Number.isInteger(units)) {
      toast.error('Fractional units are not allowed. Please enter a whole number.');
      return;
    }
    if (!editingCertificate && summary && units > summary.remaining_units) {
      toast.error(`Cannot issue ${units} units. Only ${summary.remaining_units} units remaining.`);
      return;
    }
    if (!editingCertificate && !summary) {
      toast.error('Trust data is still loading. Please try again in a moment.');
      return;
    }

    const sanitizeOptional = (val) =>
      val === null || val === undefined || val.trim() === '' ? null : val;

    try {
      const url = editingCertificate
        ? `/trust-units/certificates/${editingCertificate.certificate_id}`
        : '/trust-units/certificates';
      const method = editingCertificate ? 'PATCH' : 'POST';

      const response = await fetchWithAuth(url, {
        method,
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          ...certificateForm,
          holder_identifier: sanitizeOptional(certificateForm.holder_identifier),
          holder_trust_id: sanitizeOptional(certificateForm.holder_trust_id),
          email: sanitizeOptional(certificateForm.email),
          phone: sanitizeOptional(certificateForm.phone),
          notes: sanitizeOptional(certificateForm.notes),
          units: parseFloat(certificateForm.units)
        })
      });

      if (response.ok) {
        toast.success(editingCertificate ? 'Certificate updated' : 'Certificate issued');
        setShowCertificateModal(false);
        resetCertificateForm();
        loadCertificatesData();
        loadOverviewData();
        // NOTE: When holder_type='trust', the backend auto-creates an entity
        // relationship in the Structures hierarchy.  If the Structures page is
        // mounted elsewhere, its data should be invalidated/refetched so the new
        // cross-trust relationship appears in the hierarchy tree.  There is no
        // shared cache today (each page fetches independently), so the user will
        // see the updated tree on next visit to Structures.  If a global query
        // cache (e.g. react-query) is added later, invalidate the
        // 'structures-entities' and 'structures-relationships' queries here.
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Failed to save certificate (${response.status})` }, { operation: 'save', page: 'Beneficiaries' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'save', page: 'Beneficiaries' });
    }
  }, [certificateForm, editingCertificate, summary, selectedTrust, resetCertificateForm, loadCertificatesData, loadOverviewData]);

  return {
    showCertificateModal,
    setShowCertificateModal,
    editingCertificate,
    certificateForm,
    setCertificateForm,
    resetCertificateForm,
    handleOpenCertificateModal,
    openEditModal,
    handleIssueCertificate,
  };
}

// ========== TRANSFER FORM HOOK ==========
export function useTransferForm(selectedTrust, isReadOnly, showUpgradeModal, summary, loadCertificatesData, loadOverviewData) {
  const [showTransferModal, setShowTransferModal] = useState(false);
  const [transferForm, setTransferForm] = useState(DEFAULT_TRANSFER_FORM);

  const handleOpenTransferModal = useCallback((fromCert) => {
    if (isReadOnly) {
      showUpgradeModal('transfer certificates', 'button_click', 'beneficiaries_page');
      return;
    }
    setTransferForm({
      from_certificate_id: fromCert?.certificate_id || '',
      to_certificate_id: '',
      to_holder_name: '',
      to_holder_identifier: '',
      units: '',
      reason: ''
    });
    setShowTransferModal(true);
  }, [isReadOnly, showUpgradeModal]);

  const handleTransfer = useCallback(async () => {
    if (!transferForm.from_certificate_id || !transferForm.to_certificate_id || !transferForm.units) {
      toast.error('All fields are required');
      return;
    }
    if (transferForm.from_certificate_id === transferForm.to_certificate_id) {
      toast.error('Cannot transfer units to the same certificate. Please select a different destination.');
      return;
    }
    try {
      const fromCert = summary?.certificates?.find(c => c.certificate_id === transferForm.from_certificate_id);
      if (!fromCert) {
        toast.error('Invalid source certificate');
        return;
      }
      const toCert = summary?.certificates?.find(c => c.certificate_id === transferForm.to_certificate_id);
      if (!toCert) {
        toast.error('Invalid destination certificate');
        return;
      }
      const units = parseFloat(transferForm.units);
      if (isNaN(units) || units <= 0) {
        toast.error('Units must be a positive number');
        return;
      }
      if (fromCert.units < units) {
        toast.error(`Cannot transfer ${units} units. ${fromCert.holder_name} only has ${fromCert.units} units.`);
        return;
      }

      const response = await fetchWithAuth('/trust-units/transfers', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          from_certificate_id: fromCert.certificate_id,
          to_certificate_id: toCert.certificate_id,
          from_holder: fromCert.holder_name,
          to_holder: toCert.holder_name,
          units: units,
          reason: transferForm.reason || 'Transfer'
        })
      });
      if (response.ok) {
        toast.success('Transfer completed');
        setShowTransferModal(false);
        setTransferForm({ from_certificate_id: '', to_certificate_id: '', to_holder_name: '', to_holder_identifier: '', units: '', reason: '' });
        loadCertificatesData();
        loadOverviewData();
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Transfer failed (${response.status})` }, { operation: 'transfer_certificate', page: 'Beneficiaries' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'transfer_certificate', page: 'Beneficiaries' });
    }
  }, [transferForm, summary, selectedTrust, loadCertificatesData, loadOverviewData]);

  return {
    showTransferModal,
    setShowTransferModal,
    transferForm,
    setTransferForm,
    handleOpenTransferModal,
    handleTransfer,
  };
}

// ========== REVOKE HOOK ==========
export function useRevoke(selectedTrust, loadCertificatesData, loadOverviewData) {
  const [showRevokeModal, setShowRevokeModal] = useState(null);
  const [revokeReason, setRevokeReason] = useState('');

  const handleRevoke = useCallback(async (certificate) => {
    try {
      const response = await fetchWithAuth(`/trust-units/certificates/${certificate.certificate_id}/revoke`, {
        method: 'POST',
        body: JSON.stringify({ trust_id: selectedTrust.trust_id, reason: revokeReason || '' })
      });
      if (response.ok) {
        toast.success('Certificate revoked');
        setShowRevokeModal(null);
        setRevokeReason('');
        loadCertificatesData();
        loadOverviewData();
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Revoke failed (${response.status})` }, { operation: 'revoke', page: 'Beneficiaries' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'revoke', page: 'Beneficiaries' });
    }
  }, [selectedTrust, revokeReason, loadCertificatesData, loadOverviewData]);

  return {
    showRevokeModal,
    setShowRevokeModal,
    revokeReason,
    setRevokeReason,
    handleRevoke,
  };
}

// ========== SETTINGS HOOK ==========
export function useSettings(selectedTrust, isReadOnly, showUpgradeModal, loadCertificatesDataRef, loadOverviewDataRef) {
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [settingsForm, setSettingsForm] = useState(DEFAULT_SETTINGS_FORM);

  // Sync settingsForm from loaded summary data
  const syncSettingsFromSummary = useCallback((data) => {
    if (data?.settings) {
      setSettingsForm({
        total_authorized_units: data.settings.total_authorized_units || 100,
        unit_label: data.settings.unit_label || 'Unit',
        allow_fractional: data.settings.allow_fractional || false,
        allocation_mode: data.settings.allocation_mode || 'percentage',
        authorized_units_ceiling: data.settings.authorized_units_ceiling ?? 100,
        unlimited_units: data.settings.unlimited_units || false,
        class_distribution_convention: data.settings.class_distribution_convention || 'per_capita'
      });
    }
  }, []);

  const handleOpenSettingsModal = useCallback(() => {
    if (isReadOnly) {
      showUpgradeModal('modify trust settings', 'button_click', 'beneficiaries_page');
      return;
    }
    setShowSettingsModal(true);
  }, [isReadOnly, showUpgradeModal]);

  const handleSaveSettings = useCallback(async () => {
    const totalAuthorized = parseFloat(settingsForm.total_authorized_units);
    if (isNaN(totalAuthorized) || totalAuthorized <= 0) {
      toast.error('Total authorized units must be a positive number');
      return;
    }
    try {
      const response = await fetchWithAuth('/trust-units/settings', {
        method: 'PATCH',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          ...settingsForm,
          total_authorized_units: totalAuthorized,
          authorized_units_ceiling: parseInt(settingsForm.authorized_units_ceiling, 10) || 0
        })
      });
      if (response.ok) {
        toast.success('Settings updated');
        setShowSettingsModal(false);
        if (loadCertificatesDataRef?.current) loadCertificatesDataRef.current();
        if (loadOverviewDataRef?.current) loadOverviewDataRef.current();
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Failed to save settings (${response.status})` }, { operation: 'save', page: 'Beneficiaries' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'save', page: 'Beneficiaries' });
    }
  }, [settingsForm, selectedTrust, loadCertificatesDataRef, loadOverviewDataRef]);

  return {
    showSettingsModal,
    setShowSettingsModal,
    settingsForm,
    setSettingsForm,
    syncSettingsFromSummary,
    handleOpenSettingsModal,
    handleSaveSettings,
  };
}

// ========== PDF PREVIEW HOOK ==========
export function usePdfPreview() {
  const [pdfPreview, setPdfPreview] = useState({ show: false, loading: false, data: null, filename: '' });

  const handleViewPDF = useCallback(async (certificate) => {
    setPdfPreview({ show: true, loading: true, data: null, filename: '' });
    try {
      const response = await fetchWithAuth(`/trust-units/certificates/${certificate.certificate_id}/pdf`);
      if (response.ok) {
        const data = await response.json();
        setPdfPreview({ show: true, loading: false, data: data.pdf_base64, filename: data.filename });
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Failed to load PDF (${response.status})` }, { operation: 'load', page: 'Beneficiaries' });
        setPdfPreview({ show: false, loading: false, data: null, filename: '' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'load', page: 'Beneficiaries' });
      setPdfPreview({ show: false, loading: false, data: null, filename: '' });
    }
  }, []);

  const closePdfPreview = useCallback(() => {
    setPdfPreview({ show: false, loading: false, data: null, filename: '' });
  }, []);

  return {
    pdfPreview,
    setPdfPreview,
    handleViewPDF,
    closePdfPreview,
  };
}

// ========== CLASS BENEFICIARY HOOK ==========
export function useClassBeneficiary(selectedTrust, isReadOnly, showUpgradeModal, loadOverviewData) {
  const [showClassBeneficiaryModal, setShowClassBeneficiaryModal] = useState(false);
  const [classBeneficiaryForm, setClassBeneficiaryForm] = useState(DEFAULT_CLASS_BENEFICIARY_FORM);
  const [deleteConfirmClass, setDeleteConfirmClass] = useState(null);

  const handleAddClassBeneficiary = useCallback(async () => {
    if (!classBeneficiaryForm.class_type) {
      toast.error('Class type is required');
      return;
    }
    const percentage = parseFloat(classBeneficiaryForm.percentage);
    if (classBeneficiaryForm.percentage !== '' && (isNaN(percentage) || percentage <= 0 || percentage > 100)) {
      toast.error('Percentage must be between 0 and 100');
      return;
    }
    try {
      const response = await fetchWithAuth('/beneficiaries/class-beneficiaries', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          class_type: classBeneficiaryForm.class_type,
          description: classBeneficiaryForm.description,
          percentage: parseFloat(classBeneficiaryForm.percentage) || 0,
          notes: classBeneficiaryForm.notes,
          distribution_convention: classBeneficiaryForm.distribution_convention
        })
      });
      if (response.ok) {
        toast.success('Class Beneficiary added');
        setShowClassBeneficiaryModal(false);
        setClassBeneficiaryForm({ class_type: 'children', description: '', percentage: '', notes: '', distribution_convention: 'per_capita' });
        loadOverviewData();
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Failed to add Class Beneficiary (${response.status})` }, { operation: 'add', page: 'Beneficiaries' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'add', page: 'Beneficiaries' });
    }
  }, [classBeneficiaryForm, selectedTrust, loadOverviewData]);

  const handleDeleteClassBeneficiary = useCallback(async (classBeneficiaryId) => {
    try {
      const response = await fetchWithAuth(`/beneficiaries/class-beneficiaries/${classBeneficiaryId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        toast.success('Class Beneficiary removed');
        loadOverviewData();
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Failed to remove Class Beneficiary (${response.status})` }, { operation: 'remove', page: 'Beneficiaries' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'remove', page: 'Beneficiaries' });
    }
  }, [loadOverviewData]);

  return {
    showClassBeneficiaryModal,
    setShowClassBeneficiaryModal,
    classBeneficiaryForm,
    setClassBeneficiaryForm,
    deleteConfirmClass,
    setDeleteConfirmClass,
    handleAddClassBeneficiary,
    handleDeleteClassBeneficiary,
  };
}

// ========== PERSON (ADD BENEFICIARY) HOOK ==========
export function usePersonForm(selectedTrust, isReadOnly, showUpgradeModal, summary, loadCertificatesData, loadOverviewData) {
  const [showPersonModal, setShowPersonModal] = useState(false);
  const [personForm, setPersonForm] = useState(DEFAULT_PERSON_FORM);

  const resetPersonForm = useCallback(() => {
    setPersonForm({ name: '', relationship: '', sharePercentage: '' });
  }, []);

  const handleOpenPersonModal = useCallback(() => {
    if (isReadOnly) {
      showUpgradeModal('add beneficiaries', 'button_click', 'beneficiaries_page');
      return;
    }
    setShowPersonModal(true);
  }, [isReadOnly, showUpgradeModal]);

  const handleAddPerson = useCallback(async () => {
    if (!personForm.name || !personForm.sharePercentage) {
      toast.error('Name and share percentage are required');
      return;
    }
    const pct = parseFloat(personForm.sharePercentage);
    if (!pct || pct <= 0 || pct > 100) {
      toast.error('Share percentage must be between 0 and 100');
      return;
    }
    if (isReadOnly) {
      showUpgradeModal('add beneficiaries', 'button_click', 'beneficiaries_page');
      return;
    }

    const totalAuthorized = summary?.settings?.total_authorized_units || 100;
    let units = (pct / 100) * totalAuthorized;
    if (summary?.settings?.allow_fractional !== true) {
      units = Math.round(units);
    }

    if (units <= 0) {
      toast.error('Share is too small to allocate a unit.');
      return;
    }

    if (summary && units > summary.remaining_units) {
      toast.error(`Cannot allocate ${pct}%. Only ${summary.remaining_units} units available (${((summary.remaining_units / totalAuthorized) * 100).toFixed(1)}%).`);
      return;
    }

    try {
      const relationship = personForm.relationship || '';
      const isCharity = relationship === 'Charity';
      const notesText = relationship ? `Relationship to grantor: ${relationship}` : '';
      const response = await fetchWithAuth('/trust-units/certificates', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          holder_name: personForm.name,
          holder_identifier: null,
          holder_type: isCharity ? 'charity' : 'individual',
          email: null,
          phone: null,
          units: units,
          issue_date: (() => {
            const today = new Date();
            return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
          })(),
          notes: notesText || null,
        }),
      });

      if (response.ok) {
        toast.success(`${personForm.name} added as a beneficiary (${pct}%)`);
        setShowPersonModal(false);
        setPersonForm({ name: '', relationship: '', sharePercentage: '' });
        loadCertificatesData();
        loadOverviewData();
      } else {
        const errBody = await response.json().catch(() => null);
        showError(toast, errBody || { detail: `Failed to add beneficiary (${response.status})` }, { operation: 'add', page: 'Beneficiaries' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'add', page: 'Beneficiaries' });
    }
  }, [personForm, isReadOnly, showUpgradeModal, summary, selectedTrust, loadCertificatesData, loadOverviewData]);

  return {
    showPersonModal,
    setShowPersonModal,
    personForm,
    setPersonForm,
    resetPersonForm,
    handleOpenPersonModal,
    handleAddPerson,
  };
}