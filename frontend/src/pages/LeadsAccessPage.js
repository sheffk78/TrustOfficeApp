import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Target, RefreshCw } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import LeadFollowUpModal from '@/components/LeadFollowUpModal';
import { LeadsTab } from './admin/LeadsTab';
import { LeadDetailDialog, BulkLeadStageDialog } from './admin/AdminDialogs';

/**
 * LeadsAccessPage — the "Leads" menu destination for leads-scoped users
 * (is_leads_user). Reuses the admin LeadsTab UI and lead dialogs, but has
 * no access to customers, revenue, conversations, or system administration.
 * Backend enforces the same boundary via require_leads_or_admin.
 */
export default function LeadsAccessPage() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const isLeadsUser = user?.is_leads_user || user?.is_admin;
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';

  const [accessChecked, setAccessChecked] = useState(false);
  const [leads, setLeads] = useState([]);
  const [leadsTotal, setLeadsTotal] = useState(0);
  const [leadsPage, setLeadsPage] = useState(1);
  const [leadsSearch, setLeadsSearch] = useState('');
  const [leadsStageFilter, setLeadsStageFilter] = useState('all');
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [leadsStageCounts, setLeadsStageCounts] = useState({});
  const [selectedLead, setSelectedLead] = useState(null);
  const [leadDetailLoading, setLeadDetailLoading] = useState(false);
  const [leadNoteText, setLeadNoteText] = useState('');

  // Bulk selection
  const [selectedLeadIds, setSelectedLeadIds] = useState(new Set());
  const [showBulkLeadStageDialog, setShowBulkLeadStageDialog] = useState(false);
  const [bulkLeadStage, setBulkLeadStage] = useState('new');
  const [bulkLeadActionLoading, setBulkLeadActionLoading] = useState(false);

  // Triage view
  const [showTriageView, setShowTriageView] = useState(false);

  // Follow-up modal
  const [followUpLead, setFollowUpLead] = useState(null);
  const [showFollowUpModal, setShowFollowUpModal] = useState(false);

  // ─── Verify access with the API (source of truth) ─────────────────
  useEffect(() => {
    const check = async () => {
      try {
        const response = await fetchWithAuth('/admin/leads?page=1&limit=1');
        if (!response.ok) {
          navigate('/dashboard', { replace: true });
          return;
        }
        setAccessChecked(true);
      } catch {
        navigate('/dashboard', { replace: true });
      }
    };
    if (user) check();
  }, [user, navigate]);

  // ─── Fetch leads ──────────────────────────────────────────────────
  const fetchLeads = async () => {
    setLeadsLoading(true);
    try {
      let url = `/admin/leads?page=${leadsPage}&limit=20`;
      if (leadsSearch) url += `&search=${encodeURIComponent(leadsSearch)}`;
      if (leadsStageFilter === 'booked_call') {
        url += `&booked_call=true`;
      } else if (leadsStageFilter !== 'all') {
        url += `&stage=${leadsStageFilter}`;
      }

      const response = await fetchWithAuth(url);
      if (response.ok) {
        const data = await response.json();
        setLeads(data.leads);
        setLeadsTotal(data.total);
        setLeadsStageCounts(data.stages || {});
      }
    } catch (error) {
      console.error('Failed to fetch leads:', error);
    }
    setLeadsLoading(false);
  };

  useEffect(() => {
    if (isLeadsUser && accessChecked) {
      fetchLeads();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLeadsUser, accessChecked, leadsPage, leadsStageFilter]);

  // ─── Lead detail ──────────────────────────────────────────────────
  const fetchLeadDetail = async (leadId) => {
    setSelectedLead(leadId);
    setLeadDetailLoading(true);
    try {
      const response = await fetchWithAuth(`/admin/leads/${leadId}`);
      if (response.ok) {
        const data = await response.json();
        setSelectedLead(data);
      }
    } catch (error) {
      console.error('Failed to fetch lead detail:', error);
    }
    setLeadDetailLoading(false);
  };

  const addLeadNote = async () => {
    if (!leadNoteText.trim() || !selectedLead) return;
    try {
      const response = await fetchWithAuth(`/admin/leads/${selectedLead.lead_id}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: leadNoteText }),
      });
      if (response.ok) {
        setLeadNoteText('');
        fetchLeadDetail(selectedLead.lead_id);
        fetchLeads();
      }
    } catch (error) {
      console.error('Failed to add lead note:', error);
    }
  };

  const updateLeadStage = async (leadId, stage) => {
    try {
      const response = await fetchWithAuth(`/admin/leads/${leadId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage }),
      });
      if (response.ok) {
        fetchLeads();
        if (selectedLead?.lead_id === leadId) {
          fetchLeadDetail(leadId);
        }
      }
    } catch (error) {
      console.error('Failed to update lead stage:', error);
    }
  };

  const updateLeadCallOutcome = async (leadId, callOutcome) => {
    try {
      const response = await fetchWithAuth(`/admin/leads/${leadId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ call_outcome: callOutcome }),
      });
      if (response.ok) {
        fetchLeads();
        if (selectedLead?.lead_id === leadId) {
          fetchLeadDetail(leadId);
        }
      }
    } catch (error) {
      console.error('Failed to update lead call outcome:', error);
    }
  };

  // ─── Selection + bulk ─────────────────────────────────────────────
  const toggleSelectLead = (leadId) => {
    setSelectedLeadIds(prev => {
      const next = new Set(prev);
      if (next.has(leadId)) next.delete(leadId);
      else next.add(leadId);
      return next;
    });
  };

  const toggleSelectAllLeads = () => {
    setSelectedLeadIds(prev => {
      if (prev.size === leads.length) return new Set();
      return new Set(leads.map(l => l.lead_id));
    });
  };

  const clearLeadSelection = () => setSelectedLeadIds(new Set());

  const handleBulkLeadStageChange = async () => {
    if (selectedLeadIds.size === 0) return;
    setBulkLeadActionLoading(true);
    try {
      const response = await fetchWithAuth('/admin/leads/bulk/stage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_ids: Array.from(selectedLeadIds), stage: bulkLeadStage }),
      });
      if (response.ok) {
        toast.success(`Updated ${selectedLeadIds.size} leads`);
        setShowBulkLeadStageDialog(false);
        clearLeadSelection();
        fetchLeads();
      }
    } catch (error) {
      console.error('Bulk stage change failed:', error);
    }
    setBulkLeadActionLoading(false);
  };

  const exportLeadsCsv = async () => {
    try {
      const response = await fetchWithAuth('/admin/leads/export');
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `leads-${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Export failed:', error);
    }
  };

  const handleBulkLeadExport = async () => {
    if (selectedLeadIds.size === 0) return;
    try {
      const response = await fetchWithAuth('/admin/leads/bulk/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Array.from(selectedLeadIds)),
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `leads-selected-${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Bulk export failed:', error);
    }
  };

  // ─── Access denied state ──────────────────────────────────────────
  if (user && !isLeadsUser) {
    return (
      <div className="min-h-screen bg-background flex">
        <Sidebar />
        <main className="flex-1 p-4 lg:p-8 lg:ml-64 pb-24 lg:pb-8 flex items-center justify-center">
          <div className="text-center">
            <Target className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h1 className="text-xl font-medium text-navy dark:text-white mb-2">Leads access required</h1>
            <p className="text-muted-foreground">You don't have access to the leads area.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <main className="flex-1 p-4 lg:p-8 lg:ml-64 pb-24 lg:pb-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="page-header flex items-center justify-between mb-8">
            <div>
              <h1 className="page-title flex items-center gap-3">
                <Target className="w-8 h-8 text-navy dark:text-white" />
                Leads
              </h1>
              <p className="page-subtitle">Lead pipeline and follow-up</p>
            </div>
          </div>

          <LeadsTab
            leads={leads}
            leadsLoading={leadsLoading}
            leadsTotal={leadsTotal}
            leadsPage={leadsPage}
            leadsSearch={leadsSearch}
            leadsStageFilter={leadsStageFilter}
            leadsStageCounts={leadsStageCounts}
            selectedLeadIds={selectedLeadIds}
            showTriageView={showTriageView}
            onToggleTriage={() => setShowTriageView(!showTriageView)}
            onExportCsv={exportLeadsCsv}
            onRefresh={fetchLeads}
            onStageFilterChange={(key) => { setLeadsStageFilter(key); setLeadsPage(1); }}
            onSearchChange={setLeadsSearch}
            onSearchSubmit={() => { setLeadsPage(1); fetchLeads(); }}
            onClearSelection={clearLeadSelection}
            onBulkExport={handleBulkLeadExport}
            onBulkStageChange={() => setShowBulkLeadStageDialog(true)}
            onSelectAll={toggleSelectAllLeads}
            onSelectLead={toggleSelectLead}
            onViewLead={fetchLeadDetail}
            onTriageViewLead={fetchLeadDetail}
            onTriageFollowUp={(lead) => { setFollowUpLead(lead); setShowFollowUpModal(true); }}
            onUpdateLeadStage={updateLeadStage}
            onPrevPage={() => setLeadsPage(p => Math.max(1, p - 1))}
            onNextPage={() => setLeadsPage(p => p + 1)}
          />
        </div>

        <LeadDetailDialog
          selectedLead={selectedLead}
          leadDetailLoading={leadDetailLoading}
          onClose={() => setSelectedLead(null)}
          onUpdateLeadStage={updateLeadStage}
          onUpdateCallOutcome={updateLeadCallOutcome}
          onAddNote={addLeadNote}
          onNoteChange={setLeadNoteText}
          leadNoteText={leadNoteText}
        />

        <BulkLeadStageDialog
          show={showBulkLeadStageDialog}
          selectedCount={selectedLeadIds.size}
          bulkLeadStage={bulkLeadStage}
          bulkLeadActionLoading={bulkLeadActionLoading}
          onClose={() => setShowBulkLeadStageDialog(false)}
          onStageSelect={setBulkLeadStage}
          onConfirm={handleBulkLeadStageChange}
        />

        <LeadFollowUpModal
          lead={followUpLead}
          open={showFollowUpModal}
          onClose={() => { setFollowUpLead(null); setShowFollowUpModal(false); }}
          onSent={() => fetchLeads()}
        />
      </main>
    </div>
  );
}