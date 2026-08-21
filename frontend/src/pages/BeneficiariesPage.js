import { useState, useCallback, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import PageHelpButton from '@/components/PageHelpButton';
import {
  Users, PieChart, Award, Settings, ArrowRightLeft, UsersRound,
} from 'lucide-react';

import { formatDate, filterCertificatesByStatus } from './beneficiaries/constants';
import {
  useBeneficiariesData,
  useCertificateForm,
  useTransferForm,
  useRevoke,
  useSettings,
  usePdfPreview,
  useClassBeneficiary,
  usePersonForm,
  useAllocationMode,
} from './beneficiaries/hooks';
import BeneficiaryListTab from './beneficiaries/BeneficiaryListTab';
import OverviewTab from './beneficiaries/OverviewTab';
import CertificatesTab from './beneficiaries/CertificatesTab';
import TransfersTab from './beneficiaries/TransfersTab';
import ClassBeneficiariesTab from './beneficiaries/ClassBeneficiariesTab';
import { BeneficiariesModals } from './beneficiaries/Modals';

// ========== MAIN PAGE COMPONENT ==========
export default function BeneficiariesPage() {
  const { selectedTrust, isReadOnly, trusts } = useAuth();
  const { showUpgradeModal } = useUpgradeModal();
  const [searchParams, setSearchParams] = useSearchParams();
  const validTabs = ['overview', 'beneficiaries', 'certificates', 'transfers', 'class'];
  const requestedTab = searchParams.get('tab');
  const [activeTab, setActiveTabState] = useState(
    validTabs.includes(requestedTab) ? requestedTab : 'overview'
  );
  const setActiveTab = useCallback((tab) => {
    if (!validTabs.includes(tab)) return;
    setActiveTabState(tab);
    const next = new URLSearchParams(searchParams);
    next.set('tab', tab);
    setSearchParams(next);
  }, [searchParams, setSearchParams]);
  useEffect(() => {
    const nextTab = validTabs.includes(requestedTab) ? requestedTab : 'overview';
    setActiveTabState((current) => current === nextTab ? current : nextTab);
  }, [requestedTab]);
  const [expandedHolder, setExpandedHolder] = useState(null);
  const [statusFilter, setStatusFilter] = useState('active');

  // Refs to hold the latest data-reload callbacks for the settings hook
  const loadCertificatesDataRef = useRef(null);
  const loadOverviewDataRef = useRef(null);

  // Settings hook (uses refs so it can call reload without circular dependency)
  const settings = useSettings(selectedTrust, isReadOnly, showUpgradeModal, loadCertificatesDataRef, loadOverviewDataRef);

  // Data loading — sync settings form when summary loads
  const {
    overviewData,
    summary,
    loading,
    loadOverviewData,
    loadCertificatesData,
  } = useBeneficiariesData(selectedTrust, settings.syncSettingsFromSummary);

  // Keep refs updated with the latest reload functions
  loadCertificatesDataRef.current = loadCertificatesData;
  loadOverviewDataRef.current = loadOverviewData;

  // Certificate form hook
  const certForm = useCertificateForm(selectedTrust, isReadOnly, showUpgradeModal, summary, loadCertificatesData, loadOverviewData);

  // Transfer form hook
  const transfer = useTransferForm(selectedTrust, isReadOnly, showUpgradeModal, summary, loadCertificatesData, loadOverviewData);

  // Revoke hook
  const revoke = useRevoke(selectedTrust, loadCertificatesData, loadOverviewData);

  // PDF preview hook
  const pdfPreview = usePdfPreview();

  // Class beneficiary hook
  const classBeneficiary = useClassBeneficiary(selectedTrust, isReadOnly, showUpgradeModal, loadOverviewData);

  // Allocation mode hook
  const allocationMode = useAllocationMode(summary);

  // Person form hook
  const personForm = usePersonForm(
    selectedTrust,
    isReadOnly,
    showUpgradeModal,
    summary,
    loadCertificatesData,
    loadOverviewData,
    allocationMode.allocationMode
  );

  // Filter certificates
  const filteredCertificates = filterCertificatesByStatus(summary?.certificates, statusFilter);

  if (!selectedTrust) {
    return (
      <div className="main-layout">
        <Sidebar />
        <main className="main-content dot-grid">
          <div className="page-container">
            <div className="card-trust p-12 flex flex-col items-center justify-center">
              <Users className="w-12 h-12 text-muted-foreground/40 mb-3"/>
              <h2 className="text-xl font-semibold text-navy mb-1">Select a trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to manage beneficiaries.</p>
            </div>
          </div>
        </main>
      <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="main-layout">
      <Sidebar />
      <main className="main-content dot-grid mobile-layout-offset">
        <div className="page-container">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Beneficiaries</h1>
              <p className="page-subtitle">Manage trust beneficiaries, ownership interests, and class designations — add, update, or remove beneficiaries with proper documentation</p>
            </div>
            <div className="flex items-center gap-2 mt-4 md:mt-0">
              <PageHelpButton
                items={[
                  { text: 'Manage trust beneficiaries, ownership interests, and class designations' },
                  { text: 'Add, update, or remove beneficiaries with proper documentation' },
                  { text: 'View beneficiary certificates and allocation percentages' },
                ]}
                taPrompt="Help me understand the Beneficiaries page and how to add a beneficiary"
              />
              <Button variant="outline" onClick={settings.handleOpenSettingsModal} data-testid="settings-btn">
                <Settings className="w-4 h-4 mr-2" />
                Settings
              </Button>
            </div>
          </div>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="mb-6 bg-muted/50 flex w-full gap-1 overflow-x-auto whitespace-nowrap">
              <TabsTrigger value="overview" className="data-[state=active]:bg-navy data-[state=active]:text-white" data-testid="tab-overview">
                <PieChart className="w-4 h-4 mr-2" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="beneficiaries" className="data-[state=active]:bg-navy data-[state=active]:text-white" data-testid="tab-beneficiaries">
                <Users className="w-4 h-4 mr-2" />
                Beneficiaries
              </TabsTrigger>
              <TabsTrigger value="certificates" className="data-[state=active]:bg-navy data-[state=active]:text-white" data-testid="tab-certificates">
                <Award className="w-4 h-4 mr-2" />
                Ownership Shares
              </TabsTrigger>
              <TabsTrigger value="transfers" className="data-[state=active]:bg-navy data-[state=active]:text-white" data-testid="tab-transfers">
                <ArrowRightLeft className="w-4 h-4 mr-2" />
                Transfer History
              </TabsTrigger>
              <TabsTrigger value="class" className="data-[state=active]:bg-navy data-[state=active]:text-white" data-testid="tab-class">
                <UsersRound className="w-4 h-4 mr-2" />
                Class Beneficiaries
              </TabsTrigger>
            </TabsList>

            {/* ========== BENEFICIARIES TAB ========== */}
            <TabsContent value="beneficiaries">
              <BeneficiaryListTab
                overviewData={overviewData}
                loading={loading}
                handleOpenPersonModal={personForm.handleOpenPersonModal}
                openEditModal={certForm.openEditModal}
                summary={summary}
                setShowSettingsModal={settings.setShowSettingsModal}
                allocationMode={allocationMode.allocationMode}
              />
            </TabsContent>

            {/* ========== OVERVIEW TAB ========== */}
            <TabsContent value="overview">
              <OverviewTab
                overviewData={overviewData}
                loading={loading}
                summary={summary}
                expandedHolder={expandedHolder}
                setExpandedHolder={setExpandedHolder}
                openEditModal={certForm.openEditModal}
                setActiveTab={setActiveTab}
                handleOpenCertificateModal={certForm.handleOpenCertificateModal}
                formatDateFn={formatDate}
                allocationMode={allocationMode.allocationMode}
              />
            </TabsContent>

            {/* ========== CERTIFICATES TAB ========== */}
            <TabsContent value="certificates">
              <CertificatesTab
                summary={summary}
                loading={loading}
                statusFilter={statusFilter}
                setStatusFilter={setStatusFilter}
                filteredCertificates={filteredCertificates}
                handleOpenTransferModal={transfer.handleOpenTransferModal}
                resetCertificateForm={certForm.resetCertificateForm}
                handleOpenCertificateModal={certForm.handleOpenCertificateModal}
                handleViewPDF={pdfPreview.handleViewPDF}
                openEditModal={certForm.openEditModal}
                setTransferForm={transfer.setTransferForm}
                setShowTransferModal={transfer.setShowTransferModal}
                setShowRevokeModal={revoke.setShowRevokeModal}
                transferForm={transfer.transferForm}
                setShowSettingsModal={settings.setShowSettingsModal}
                allocationMode={allocationMode.allocationMode}
              />
            </TabsContent>

            {/* ========== TRANSFERS TAB ========== */}
            <TabsContent value="transfers">
              <TransfersTab overviewData={overviewData} />
            </TabsContent>

            {/* ========== CLASS BENEFICIARIES TAB ========== */}
            <TabsContent value="class">
              <ClassBeneficiariesTab
                overviewData={overviewData}
                setShowClassBeneficiaryModal={classBeneficiary.setShowClassBeneficiaryModal}
                setDeleteConfirmClass={classBeneficiary.setDeleteConfirmClass}
              />
            </TabsContent>
          </Tabs>
        </div>
      </main>
      <MobileBottomNav />

      {/* ========== MODALS ========== */}
      <BeneficiariesModals
        showCertificateModal={certForm.showCertificateModal}
        setShowCertificateModal={certForm.setShowCertificateModal}
        editingCertificate={certForm.editingCertificate}
        certificateForm={certForm.certificateForm}
        setCertificateForm={certForm.setCertificateForm}
        resetCertificateForm={certForm.resetCertificateForm}
        handleIssueCertificate={certForm.handleIssueCertificate}
        summary={summary}
        trusts={trusts}
        selectedTrust={selectedTrust}
        showTransferModal={transfer.showTransferModal}
        setShowTransferModal={transfer.setShowTransferModal}
        transferForm={transfer.transferForm}
        setTransferForm={transfer.setTransferForm}
        handleTransfer={transfer.handleTransfer}
        showRevokeModal={revoke.showRevokeModal}
        setShowRevokeModal={revoke.setShowRevokeModal}
        revokeReason={revoke.revokeReason}
        setRevokeReason={revoke.setRevokeReason}
        handleRevoke={revoke.handleRevoke}
        showSettingsModal={settings.showSettingsModal}
        setShowSettingsModal={settings.setShowSettingsModal}
        settingsForm={settings.settingsForm}
        setSettingsForm={settings.setSettingsForm}
        handleSaveSettings={settings.handleSaveSettings}
        deleteConfirmClass={classBeneficiary.deleteConfirmClass}
        setDeleteConfirmClass={classBeneficiary.setDeleteConfirmClass}
        handleDeleteClassBeneficiary={classBeneficiary.handleDeleteClassBeneficiary}
        showClassBeneficiaryModal={classBeneficiary.showClassBeneficiaryModal}
        setShowClassBeneficiaryModal={classBeneficiary.setShowClassBeneficiaryModal}
        classBeneficiaryForm={classBeneficiary.classBeneficiaryForm}
        setClassBeneficiaryForm={classBeneficiary.setClassBeneficiaryForm}
        handleAddClassBeneficiary={classBeneficiary.handleAddClassBeneficiary}
        showPersonModal={personForm.showPersonModal}
        setShowPersonModal={personForm.setShowPersonModal}
        personForm={personForm.personForm}
        setPersonForm={personForm.setPersonForm}
        resetPersonForm={personForm.resetPersonForm}
        handleAddPerson={personForm.handleAddPerson}
        allocationMode={allocationMode.allocationMode}
        allocationModeHelp={allocationMode.modeHelp}
        totalAuthorizedUnits={allocationMode.totalAuthorized}
        unitLabel={allocationMode.unitLabel}
        pdfPreview={pdfPreview.pdfPreview}
        setPdfPreview={pdfPreview.setPdfPreview}
      />
    </div>
  );
}