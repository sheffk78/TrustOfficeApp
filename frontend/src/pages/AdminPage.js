import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import PageHelpButton from '@/components/PageHelpButton';
import NotificationCenter from '@/components/NotificationCenter';
import LeadFollowUpModal from '@/components/LeadFollowUpModal';
import {
  Users, Shield, Crown, Link2, Target,
  TrendingUp, Gift, DollarSign, CheckCircle,
  RefreshCw, BarChart3, MessageSquare,
} from 'lucide-react';

import { RevenueTab } from './admin/RevenueTab';
import { CustomersTab } from './admin/CustomersTab';
import { AdminsTab } from './admin/AdminsTab';
import { ReferralsTab } from './admin/ReferralsTab';
import { LeadsTab } from './admin/LeadsTab';
import { LeadAnalyticsTab } from './admin/LeadAnalyticsTab';
import { ConversationsTab } from './admin/ConversationsTab';
import {
  LeadDetailDialog, BulkLeadStageDialog, CustomerDetailDialog,
  GrantAccessDialog, DeleteDialog, CreateAdminDialog,
  CreateUserDialog, FixReferralDialog, BulkDeleteDialog, ImpersonateDialog,
} from './admin/AdminDialogs';

// Stats card config — keeps the JSX in the return body flat
const STATS_CARDS = [
  { icon: Users, iconClass: '', label: 'Total Users', getValue: s => s.total_users, valueClass: 'text-navy dark:text-white' },
  { icon: CheckCircle, iconClass: 'text-success', label: 'Active Subs', getValue: s => s.active_subscriptions, valueClass: 'text-success' },
  { icon: Gift, iconClass: 'text-gold', label: 'Gifted', getValue: s => s.gifted_users || s.trial_users, valueClass: 'text-gold' },
  { icon: TrendingUp, iconClass: 'text-purple-500', label: 'New (30d)', getValue: s => s.new_users_30d, valueClass: 'text-purple-600' },
  { icon: DollarSign, iconClass: 'text-gold', label: 'Est. MRR', getValue: s => `$${s.revenue_estimate_monthly}`, valueClass: 'text-gold' },
];

const TAB_CONFIG = [
  { value: 'customers', icon: Users, label: 'Customers' },
  { value: 'conversations', icon: MessageSquare, label: 'Conversations' },
  { value: 'revenue', icon: BarChart3, label: 'Revenue' },
  { value: 'admins', icon: Crown, label: 'Admins' },
  { value: 'referrals', icon: Link2, label: 'Referrals' },
  { value: 'leads', icon: Target, label: 'Leads', showNewBadge: true },
  { value: 'lead-analytics', icon: BarChart3, label: 'Lead Analytics' },
];

export default function AdminPage() {
  const navigate = useNavigate();
  const { user, setUser, loadTrusts, loadSubscriptionState } = useAuth();
  const [activeTab, setActiveTab] = useState('customers');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);

  // Customer list state
  const [customers, setCustomers] = useState([]);
  const [customerTotal, setCustomerTotal] = useState(0);
  const [customerPage, setCustomerPage] = useState(1);
  const [customerSearch, setCustomerSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  // Selected customer for detail view
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [customerDetail, setCustomerDetail] = useState(null);

  // Dialogs
  const [showGrantAccessDialog, setShowGrantAccessDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showCreateAdminDialog, setShowCreateAdminDialog] = useState(false);
  const [showFixReferralDialog, setShowFixReferralDialog] = useState(false);
  const [showBulkDeleteDialog, setShowBulkDeleteDialog] = useState(false);
  const [showImpersonateDialog, setShowImpersonateDialog] = useState(false);
  const [impersonateLoading, setImpersonateLoading] = useState(false);
  const [showCreateUserDialog, setShowCreateUserDialog] = useState(false);
  const [createUserLoading, setCreateUserLoading] = useState(false);

  // Multi-select state
  const [selectedCustomerIds, setSelectedCustomerIds] = useState(new Set());
  const [bulkActionLoading, setBulkActionLoading] = useState(false);

  // Form states
  const [grantAccessForm, setGrantAccessForm] = useState({ plan_type: 'gifted_14day', days: 14 });
  const [createUserForm, setCreateUserForm] = useState({ email: '', name: '', gifted_tier: '14day' });
  const [createAdminForm, setCreateAdminForm] = useState({ email: '', name: '', password: '' });
  const [fixReferralForm, setFixReferralForm] = useState({ referrer_email: '', referee_email: '', action: 'create', status: '' });

  // Referrals list
  const [referrals, setReferrals] = useState([]);
  const [referralsLoading, setReferralsLoading] = useState(false);

  // Admin list
  const [admins, setAdmins] = useState([]);

  // Revenue data for Revenue tab
  const [revenueData, setRevenueData] = useState(null);
  const [revenuePreset, setRevenuePreset] = useState('last_30_days');
  const [revenueLoading, setRevenueLoading] = useState(false);
  const [revenueError, setRevenueError] = useState(null);

  // Stats users list
  const [statsUsers, setStatsUsers] = useState([]);

  // Leads state
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

  // Lead analytics state
  const [leadAnalytics, setLeadAnalytics] = useState(null);
  const [leadAnalyticsLoading, setLeadAnalyticsLoading] = useState(false);

  // Lead bulk selection state
  const [selectedLeadIds, setSelectedLeadIds] = useState(new Set());
  const [showBulkLeadStageDialog, setShowBulkLeadStageDialog] = useState(false);
  const [bulkLeadStage, setBulkLeadStage] = useState('new');
  const [bulkLeadActionLoading, setBulkLeadActionLoading] = useState(false);

  // Lead triage view state — default to Table View
  const [showTriageView, setShowTriageView] = useState(false);

  // Follow-up email modal state
  const [followUpLead, setFollowUpLead] = useState(null);
  const [showFollowUpModal, setShowFollowUpModal] = useState(false);

  // Conversations state
  const [conversations, setConversations] = useState([]);
  const [conversationsTotal, setConversationsTotal] = useState(0);
  const [conversationsPage, setConversationsPage] = useState(1);
  const [conversationsLimit, setConversationsLimit] = useState(50);
  const [conversationsStatus, setConversationsStatus] = useState('all');
  const [conversationsSentiment, setConversationsSentiment] = useState('all');
  const [conversationsSearch, setConversationsSearch] = useState('');
  const [conversationsLoading, setConversationsLoading] = useState(false);

  // Check if user is admin - first check from user object, then verify with API
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminCheckDone, setAdminCheckDone] = useState(false);

  // Quick check from user email
  const isPrimaryAdmin = user?.email?.toLowerCase() === 'contact@trustoffice.app';

  // ─── Admin check + initial stats ───────────────────────────────────
  useEffect(() => {
    const checkAdmin = async () => {
      if (user?.is_admin || isPrimaryAdmin) {
        setIsAdmin(true);
        try {
          const response = await fetchWithAuth('/admin/stats');
          if (response.ok) {
            const data = await response.json();
            setStats(data);
          }
        } catch (error) {
          console.error('Failed to fetch admin stats:', error);
        }
        setAdminCheckDone(true);
        setLoading(false);
        return;
      }

      try {
        const response = await fetchWithAuth('/admin/stats');
        if (response.ok) {
          setIsAdmin(true);
          const data = await response.json();
          setStats(data);
        } else {
          setIsAdmin(false);
        }
      } catch (error) {
        setIsAdmin(false);
      }
      setAdminCheckDone(true);
      setLoading(false);
    };

    checkAdmin();
  }, []);

  // ─── Fetch customers ──────────────────────────────────────────────
  const fetchCustomers = useCallback(async () => {
    if (!isAdmin) return;

    try {
      let url = `/admin/customers?page=${customerPage}&limit=20`;
      if (customerSearch) url += `&search=${encodeURIComponent(customerSearch)}`;
      if (statusFilter !== 'all') url += `&status=${statusFilter}`;

      const response = await fetchWithAuth(url);

      if (response.ok) {
        const data = await response.json();
        setCustomers(data.customers || []);
        setCustomerTotal(data.total || 0);
      } else {
        const errorText = await response.text();
        console.error('[AdminPage] Error response:', errorText);
        toast.error('Failed to load customers');
      }
    } catch (error) {
      console.error('[AdminPage] Failed to fetch customers:', error);
      toast.error('Failed to load customers: ' + error.message);
    }
  }, [isAdmin, customerPage, customerSearch, statusFilter]);

  useEffect(() => {
    if (isAdmin) {
      fetchCustomers();
    }
  }, [isAdmin, fetchCustomers]);

  // ─── Fetch customer detail ────────────────────────────────────────
  const fetchCustomerDetail = async (userId) => {
    try {
      const response = await fetchWithAuth(`/admin/customers/${userId}`);
      if (response.ok) {
        const data = await response.json();
        setCustomerDetail(data);
      }
    } catch (error) {
      toast.error('Failed to fetch customer details');
    }
  };

  // ─── Fetch referrals ──────────────────────────────────────────────
  const fetchReferrals = async () => {
    setReferralsLoading(true);
    try {
      const response = await fetchWithAuth('/admin/referrals');
      if (response.ok) {
        const data = await response.json();
        setReferrals(data.referrals);
      }
    } catch (error) {
      console.error('Failed to fetch referrals:', error);
    }
    setReferralsLoading(false);
  };

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

  // ─── Fetch conversations ─────────────────────────────────────────
  const fetchConversations = useCallback(async () => {
    setConversationsLoading(true);
    try {
      let url = `/admin/conversations?page=${conversationsPage}&limit=${conversationsLimit}`;
      if (conversationsStatus !== 'all') url += `&status=${conversationsStatus}`;
      if (conversationsSentiment !== 'all') url += `&sentiment=${conversationsSentiment}`;
      if (conversationsSearch) url += `&search=${encodeURIComponent(conversationsSearch)}`;

      const response = await fetchWithAuth(url);
      if (response.ok) {
        const data = await response.json();
        setConversations(data.conversations || []);
        setConversationsTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Failed to fetch conversations:', error);
    }
    setConversationsLoading(false);
  }, [conversationsPage, conversationsLimit, conversationsStatus, conversationsSentiment, conversationsSearch]);

  // ─── Fetch lead analytics ─────────────────────────────────────────
  const fetchLeadAnalytics = async () => {
    setLeadAnalyticsLoading(true);
    try {
      const response = await fetchWithAuth('/admin/leads/analytics');
      if (response.ok) {
        const data = await response.json();
        setLeadAnalytics(data);
      }
    } catch (error) {
      console.error('Failed to fetch lead analytics:', error);
    }
    setLeadAnalyticsLoading(false);
  };

  // ─── Export leads as CSV ─────────────────────────────────────────
  const exportLeadsCsv = async () => {
    try {
      let url = '/admin/leads/export';
      if (leadsStageFilter !== 'all') url += `?stage=${leadsStageFilter}`;
      const response = await fetchWithAuth(url);
      if (response.ok) {
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `trustoffice-leads-${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);
        toast.success('Leads exported as CSV');
      }
    } catch (error) {
      console.error('Failed to export leads:', error);
      toast.error('Failed to export leads');
    }
  };

  // ─── Bulk lead actions ───────────────────────────────────────────
  const toggleSelectLead = (leadId) => {
    setSelectedLeadIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(leadId)) {
        newSet.delete(leadId);
      } else {
        newSet.add(leadId);
      }
      return newSet;
    });
  };

  const toggleSelectAllLeads = () => {
    if (selectedLeadIds.size === leads.length) {
      setSelectedLeadIds(new Set());
    } else {
      setSelectedLeadIds(new Set(leads.map(l => l.lead_id)));
    }
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
        toast.success(`Updated ${selectedLeadIds.size} leads to ${bulkLeadStage}`);
        setShowBulkLeadStageDialog(false);
        setSelectedLeadIds(new Set());
        fetchLeads();
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to update leads');
      }
    } catch (error) {
      toast.error('Failed to update leads');
    }
    setBulkLeadActionLoading(false);
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
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `trustoffice-selected-leads-${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);
        toast.success(`Exported ${selectedLeadIds.size} leads`);
      }
    } catch (error) {
      toast.error('Failed to export selected leads');
    }
  };

  // ─── Fetch lead detail ───────────────────────────────────────────
  const fetchLeadDetail = async (leadId) => {
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

  // ─── Add lead note ───────────────────────────────────────────────
  const addLeadNote = async (leadId) => {
    if (!leadNoteText.trim()) return;
    try {
      const response = await fetchWithAuth(`/admin/leads/${leadId}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: leadNoteText, action_type: 'manual' }),
      });
      if (response.ok) {
        setLeadNoteText('');
        fetchLeadDetail(leadId);
      }
    } catch (error) {
      console.error('Failed to add lead note:', error);
    }
  };

  // ─── Update lead stage ───────────────────────────────────────────
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

  // ─── Update lead call outcome (show/no-show) ────────────────────
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

  // ─── Fetch admins ────────────────────────────────────────────────
  const fetchAdmins = async () => {
    try {
      const response = await fetchWithAuth('/admin/admins');
      if (response.ok) {
        const data = await response.json();
        setAdmins(data.admins);
      }
    } catch (error) {
      console.error('Failed to fetch admins:', error);
    }
  };

  // ─── Fetch revenue data ──────────────────────────────────────────
  const fetchRevenueData = useCallback(async () => {
    setRevenueLoading(true);
    setRevenueError(null);
    try {
      const response = await fetchWithAuth(`/admin/revenue?preset=${revenuePreset}`);
      if (response.ok) {
        const data = await response.json();
        setRevenueData(data);
      } else {
        const errorData = await response.json().catch(() => ({}));
        setRevenueError(errorData.detail || 'Failed to load revenue data');
      }
    } catch (error) {
      console.error('Failed to fetch revenue data:', error);
      setRevenueError('Failed to load revenue data. Please try again.');
    } finally {
      setRevenueLoading(false);
    }
  }, [revenuePreset]);

  // ─── Fetch stats users ───────────────────────────────────────────
  const fetchStatsUsers = async () => {
    try {
      const response = await fetchWithAuth('/admin/stats-users');
      if (response.ok) {
        const data = await response.json();
        setStatsUsers(data.stats_users || []);
      }
    } catch (error) {
      console.error('Failed to fetch stats users:', error);
    }
  };

  // ─── Grant/revoke stats access handlers ──────────────────────────
  const handleGrantStats = async (userId) => {
    try {
      const response = await fetchWithAuth(`/admin/customers/${userId}/grant-stats`, {
        method: 'POST',
        body: JSON.stringify({})
      });
      if (response.ok) {
        toast.success('Stats access granted');
        fetchCustomers();
        if (customerDetail?.user_id === userId) {
          fetchCustomerDetail(userId);
        }
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to grant stats access');
      }
    } catch (error) {
      toast.error('Failed to grant stats access');
    }
  };

  const handleRevokeStats = async (userId) => {
    try {
      const response = await fetchWithAuth(`/admin/customers/${userId}/revoke-stats`, {
        method: 'POST',
        body: JSON.stringify({})
      });
      if (response.ok) {
        toast.success('Stats access revoked');
        fetchCustomers();
        if (customerDetail?.user_id === userId) {
          fetchCustomerDetail(userId);
        }
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to revoke stats access');
      }
    } catch (error) {
      toast.error('Failed to revoke stats access');
    }
  };

  // ─── Tab-change data fetching ────────────────────────────────────
  useEffect(() => {
    if (!isAdmin) return;
    if (activeTab === 'referrals') fetchReferrals();
    if (activeTab === 'lead-analytics') fetchLeadAnalytics();
    if (activeTab === 'admins') { fetchAdmins(); fetchStatsUsers(); }
    if (activeTab === 'revenue') fetchRevenueData();
    if (activeTab === 'conversations') fetchConversations();
  }, [isAdmin, activeTab, revenuePreset, fetchRevenueData, fetchConversations]);

  // ─── Fetch leads on tab open OR when stage filter / page changes ──
  // The filter buttons and pagination only update state; this effect is what
  // actually re-queries the API so clicking a stage filter takes effect.
  useEffect(() => {
    if (activeTab === 'leads' && isAdmin) {
      fetchLeads();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, activeTab, leadsPage, leadsStageFilter]);

  // ─── Actions ──────────────────────────────────────────────────────
  const handleMakeAdmin = async (userId) => {
    try {
      const response = await fetchWithAuth(`/admin/customers/${userId}/make-admin`, {
        method: 'POST',
        body: JSON.stringify({ reason: 'Promoted via admin panel' })
      });

      if (response.ok) {
        toast.success('Admin privileges granted');
        fetchCustomers();
        if (customerDetail?.user_id === userId) {
          fetchCustomerDetail(userId);
        }
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to grant admin privileges');
      }
    } catch (error) {
      toast.error('Failed to grant admin privileges');
    }
  };

  const handleRemoveAdmin = async (userId) => {
    try {
      const response = await fetchWithAuth(`/admin/customers/${userId}/remove-admin`, {
        method: 'POST',
        body: JSON.stringify({ reason: 'Removed via admin panel' })
      });

      if (response.ok) {
        toast.success('Admin privileges removed');
        fetchCustomers();
        fetchAdmins();
        if (customerDetail?.user_id === userId) {
          fetchCustomerDetail(userId);
        }
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to remove admin privileges');
      }
    } catch (error) {
      toast.error('Failed to remove admin privileges');
    }
  };

  const handleGrantAccess = async () => {
    if (!selectedCustomer) return;

    try {
      const response = await fetchWithAuth(`/admin/customers/${selectedCustomer.user_id}/grant-access`, {
        method: 'POST',
        body: JSON.stringify(grantAccessForm)
      });

      if (response.ok) {
        toast.success('Access granted successfully');
        setShowGrantAccessDialog(false);
        fetchCustomers();
        if (customerDetail?.user_id === selectedCustomer.user_id) {
          fetchCustomerDetail(selectedCustomer.user_id);
        }
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to grant access');
      }
    } catch (error) {
      toast.error('Failed to grant access');
    }
  };

  const handleDeleteCustomer = async () => {
    if (!selectedCustomer) return;

    try {
      const response = await fetchWithAuth(`/admin/customers/${selectedCustomer.user_id}?confirm=true`, {
        method: 'DELETE'
      });

      if (response.ok) {
        toast.success('Customer deleted');
        setShowDeleteDialog(false);
        setSelectedCustomer(null);
        setCustomerDetail(null);
        fetchCustomers();
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to delete customer');
      }
    } catch (error) {
      toast.error('Failed to delete customer');
    }
  };

  const handleCreateAdmin = async () => {
    try {
      const response = await fetchWithAuth('/admin/create-admin', {
        method: 'POST',
        body: JSON.stringify(createAdminForm)
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        setShowCreateAdminDialog(false);
        setCreateAdminForm({ email: '', name: '', password: '' });
        fetchAdmins();
        fetchCustomers();
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to create admin');
      }
    } catch (error) {
      toast.error('Failed to create admin');
    }
  };

  const handleCreateUser = async () => {
    if (!createUserForm.email.trim() || !createUserForm.name.trim()) {
      toast.error('Please fill in name and email');
      return;
    }
    if (!createUserForm.gifted_tier) {
      toast.error('Please select a gift tier for this user');
      return;
    }

    setCreateUserLoading(true);
    try {
      const response = await fetchWithAuth('/admin/create-user', {
        method: 'POST',
        body: JSON.stringify({
          email: createUserForm.email.trim().toLowerCase(),
          name: createUserForm.name.trim(),
          gifted_tier: createUserForm.gifted_tier
        })
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        setShowCreateUserDialog(false);
        setCreateUserForm({ email: '', name: '', gifted_tier: '14day' });
        fetchCustomers();
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to create user');
      }
    } catch (error) {
      toast.error('Failed to create user');
    } finally {
      setCreateUserLoading(false);
    }
  };

  const handleFixReferral = async () => {
    try {
      const response = await fetchWithAuth('/admin/referrals/fix', {
        method: 'POST',
        body: JSON.stringify(fixReferralForm)
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        setShowFixReferralDialog(false);
        setFixReferralForm({ referrer_email: '', referee_email: '', action: 'create', status: '' });
        fetchReferrals();
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to fix referral');
      }
    } catch (error) {
      toast.error('Failed to fix referral');
    }
  };

  // ─── Multi-select handlers ───────────────────────────────────────
  const toggleSelectCustomer = (customerId) => {
    setSelectedCustomerIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(customerId)) {
        newSet.delete(customerId);
      } else {
        newSet.add(customerId);
      }
      return newSet;
    });
  };

  const toggleSelectAll = () => {
    const selectableCount = customers.filter(c => !c.is_admin && c.email !== 'contact@trustoffice.app').length;
    if (selectedCustomerIds.size === selectableCount) {
      setSelectedCustomerIds(new Set());
    } else {
      const selectableIds = customers
        .filter(c => !c.is_admin && c.email !== 'contact@trustoffice.app')
        .map(c => c.user_id);
      setSelectedCustomerIds(new Set(selectableIds));
    }
  };

  const clearSelection = () => setSelectedCustomerIds(new Set());

  const handleBulkDelete = async () => {
    if (selectedCustomerIds.size === 0) return;

    setBulkActionLoading(true);
    try {
      const response = await fetchWithAuth('/admin/customers/bulk-delete', {
        method: 'POST',
        body: JSON.stringify({ user_ids: Array.from(selectedCustomerIds) })
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(`Successfully deleted ${data.deleted_count} account(s)`);
        setShowBulkDeleteDialog(false);
        setSelectedCustomerIds(new Set());
        fetchCustomers();
        const statsResponse = await fetchWithAuth('/admin/stats');
        if (statsResponse.ok) {
          setStats(await statsResponse.json());
        }
      } else {
        const data = await response.json();
        toast.error(data.detail || 'Failed to delete accounts');
      }
    } catch (error) {
      toast.error('Failed to delete accounts');
    } finally {
      setBulkActionLoading(false);
    }
  };

  // ─── Impersonation handler ───────────────────────────────────────
  const handleImpersonate = async () => {
    if (!selectedCustomer) return;

    setImpersonateLoading(true);
    try {
      const response = await fetchWithAuth(`/admin/impersonate/${selectedCustomer.user_id}`, {
        method: 'POST'
      });

      if (response.ok) {
        const data = await response.json();

        const adminToken = localStorage.getItem('auth_token');
        sessionStorage.setItem('admin_token', adminToken);
        sessionStorage.setItem('admin_user_data', JSON.stringify(user));

        sessionStorage.setItem('impersonation_data', JSON.stringify({
          email: data.user.email,
          name: data.user.name,
          userId: data.user.user_id,
          adminEmail: user.email,
          startTime: new Date().toISOString()
        }));

        localStorage.setItem('auth_token', data.token);
        setUser(data.user);

        await loadTrusts();
        await loadSubscriptionState(data.user.email);

        toast.success(`Now viewing as ${data.user.email}`);
        setShowImpersonateDialog(false);
        navigate('/dashboard');
      } else {
        const errorData = await response.json();
        toast.error(errorData.detail || 'Failed to impersonate user');
      }
    } catch (error) {
      console.error('Impersonation error:', error);
      toast.error('Failed to impersonate user');
    } finally {
      setImpersonateLoading(false);
    }
  };

  // ─── Early returns ────────────────────────────────────────────────
  if (adminCheckDone && !isAdmin) {
    return (
      <div className="min-h-screen bg-background flex">
        <Sidebar />
        <main className="flex-1 p-8 lg:ml-64 pb-24 lg:pb-8">
          <div className="max-w-2xl mx-auto text-center py-20">
            <Shield className="w-16 h-16 mx-auto mb-6 text-muted-foreground" />
            <h1 className="font-serif text-3xl text-navy dark:text-white mb-4">Access Denied</h1>
            <p className="text-muted-foreground">
              You don't have permission to access the admin panel.
              Only authorized administrators can view this page.
            </p>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <RefreshCw className="w-8 h-8 animate-spin text-navy" />
      </div>
    );
  }

  // ─── Helpers for sub-component callbacks ──────────────────────────
  const handleViewCustomer = (customer) => {
    setSelectedCustomer(customer);
    fetchCustomerDetail(customer.user_id);
  };

  const handleImpersonateFromCustomer = (customer) => {
    setSelectedCustomer(customer);
    setShowImpersonateDialog(true);
  };

  const handleGrantAccessFromCustomer = (customer) => {
    setSelectedCustomer(customer);
    setShowGrantAccessDialog(true);
  };

  const handleDeleteFromCustomerDetail = (customer) => {
    setSelectedCustomer(customer);
    setShowDeleteDialog(true);
  };

  const handleImpersonateFromCustomerDetail = (customer) => {
    setSelectedCustomer(customer);
    setCustomerDetail(null);
    setShowImpersonateDialog(true);
  };

  const handleGrantAccessFromCustomerDetail = (customer) => {
    setSelectedCustomer(customer);
    setShowGrantAccessDialog(true);
  };

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <main className="flex-1 p-4 lg:p-8 lg:ml-64 pb-24 lg:pb-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title flex items-center gap-3">
                <Shield className="w-8 h-8 text-navy dark:text-white" />
                Admin Panel
              </h1>
              <p className="page-subtitle">Customer management and system administration</p>
            </div>
            <div className="flex items-center gap-2">
              <NotificationCenter onNotificationClick={(n) => {
                if (n.lead_id) {
                  setActiveTab('leads');
                }
              }} />
              <PageHelpButton
                items={[
                  { text: 'Manage customers, subscriptions, and system administration' },
                  { text: 'View and manage leads, extend trials, and gift subscriptions' },
                  { text: 'Access revenue data and customer details' },
                ]}
                taPrompt="Walk me through the Admin panel"
              />
            </div>
          </div>

          {/* Stats Cards */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4 mb-8">
              {STATS_CARDS.map((card) => {
                const Icon = card.icon;
                return (
                  <div key={card.label} className="card-trust p-4">
                    <div className="flex items-center gap-2 text-muted-foreground mb-1">
                      <Icon className={`w-4 h-4 ${card.iconClass}`} />
                      <span className="text-xs">{card.label}</span>
                    </div>
                    <p className={`text-2xl font-bold ${card.valueClass}`}>{card.getValue(stats)}</p>
                  </div>
                );
              })}
            </div>
          )}

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="mb-6 bg-muted/50 flex w-full gap-1 overflow-x-auto whitespace-nowrap">
              {TAB_CONFIG.map((tab) => {
                const Icon = tab.icon;
                return (
                  <TabsTrigger key={tab.value} value={tab.value} className="flex items-center gap-2 shrink-0">
                    <Icon className="w-4 h-4" />
                    {tab.label}
                    {tab.showNewBadge && leadsStageCounts.new > 0 && (
                      <span className="ml-1 px-1.5 py-0.5 text-xs bg-rust text-white rounded-full">
                        {leadsStageCounts.new}
                      </span>
                    )}
                  </TabsTrigger>
                );
              })}
            </TabsList>

            {/* Revenue Tab */}
            <TabsContent value="revenue">
              <RevenueTab
                revenueData={revenueData}
                revenuePreset={revenuePreset}
                revenueLoading={revenueLoading}
                revenueError={revenueError}
                onPresetChange={setRevenuePreset}
                onRefresh={fetchRevenueData}
              />
            </TabsContent>

            {/* Customers Tab */}
            <TabsContent value="customers">
              <CustomersTab
                customers={customers}
                customerTotal={customerTotal}
                customerPage={customerPage}
                customerSearch={customerSearch}
                statusFilter={statusFilter}
                selectedCustomerIds={selectedCustomerIds}
                onSearchChange={(v) => { setCustomerSearch(v); setCustomerPage(1); }}
                onStatusFilterChange={(v) => { setStatusFilter(v); setCustomerPage(1); }}
                onRefresh={fetchCustomers}
                onAddUser={() => setShowCreateUserDialog(true)}
                onClearSelection={clearSelection}
                onBulkDelete={() => setShowBulkDeleteDialog(true)}
                onSelectAll={toggleSelectAll}
                onSelectCustomer={toggleSelectCustomer}
                onViewCustomer={handleViewCustomer}
                onImpersonate={handleImpersonateFromCustomer}
                onGrantAccess={handleGrantAccessFromCustomer}
                onPrevPage={() => setCustomerPage(p => Math.max(1, p - 1))}
                onNextPage={() => setCustomerPage(p => p + 1)}
              />
            </TabsContent>

            {/* Conversations Tab */}
            <TabsContent value="conversations">
              <ConversationsTab
                conversations={conversations}
                loading={conversationsLoading}
                total={conversationsTotal}
                page={conversationsPage}
                limit={conversationsLimit}
                statusFilter={conversationsStatus}
                sentimentFilter={conversationsSentiment}
                search={conversationsSearch}
                onStatusFilterChange={setConversationsStatus}
                onSentimentFilterChange={setConversationsSentiment}
                onSearchChange={setConversationsSearch}
                onRefresh={fetchConversations}
                onPrevPage={() => setConversationsPage(p => Math.max(1, p - 1))}
                onNextPage={() => setConversationsPage(p => p + 1)}
              />
            </TabsContent>

            {/* Admins Tab */}
            <TabsContent value="admins">
              <AdminsTab
                admins={admins}
                statsUsers={statsUsers}
                onAddAdmin={() => setShowCreateAdminDialog(true)}
                onRemoveAdmin={handleRemoveAdmin}
                onRevokeStats={handleRevokeStats}
              />
            </TabsContent>

            {/* Referrals Tab */}
            <TabsContent value="referrals">
              <ReferralsTab
                referrals={referrals}
                referralsLoading={referralsLoading}
                onRefresh={fetchReferrals}
                onFixReferral={() => setShowFixReferralDialog(true)}
              />
            </TabsContent>

            {/* Leads Tab */}
            <TabsContent value="leads">
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
            </TabsContent>

            {/* Lead Analytics Tab */}
            <TabsContent value="lead-analytics">
              <LeadAnalyticsTab
                leadAnalytics={leadAnalytics}
                leadAnalyticsLoading={leadAnalyticsLoading}
                onRefresh={fetchLeadAnalytics}
              />
            </TabsContent>

            {/* ── Dialogs ────────────────────────────────────────────── */}
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

            <CustomerDetailDialog
              customerDetail={customerDetail}
              onClose={() => { setCustomerDetail(null); setSelectedCustomer(null); }}
              onImpersonate={handleImpersonateFromCustomerDetail}
              onGrantAccess={handleGrantAccessFromCustomerDetail}
              onMakeAdmin={handleMakeAdmin}
              onRemoveAdmin={handleRemoveAdmin}
              onGrantStats={handleGrantStats}
              onRevokeStats={handleRevokeStats}
              onDelete={handleDeleteFromCustomerDetail}
            />

            <GrantAccessDialog
              show={showGrantAccessDialog}
              selectedCustomerEmail={selectedCustomer?.email}
              grantAccessForm={grantAccessForm}
              onClose={() => setShowGrantAccessDialog(false)}
              onFormChange={setGrantAccessForm}
              onConfirm={handleGrantAccess}
            />

            <DeleteDialog
              show={showDeleteDialog}
              selectedCustomerEmail={selectedCustomer?.email}
              onClose={() => setShowDeleteDialog(false)}
              onConfirm={handleDeleteCustomer}
            />

            <CreateAdminDialog
              show={showCreateAdminDialog}
              createAdminForm={createAdminForm}
              onClose={() => setShowCreateAdminDialog(false)}
              onFormChange={setCreateAdminForm}
              onConfirm={handleCreateAdmin}
            />

            <CreateUserDialog
              show={showCreateUserDialog}
              createUserForm={createUserForm}
              createUserLoading={createUserLoading}
              onClose={() => setShowCreateUserDialog(false)}
              onFormChange={setCreateUserForm}
              onConfirm={handleCreateUser}
            />

            <FixReferralDialog
              show={showFixReferralDialog}
              fixReferralForm={fixReferralForm}
              onClose={() => setShowFixReferralDialog(false)}
              onFormChange={setFixReferralForm}
              onConfirm={handleFixReferral}
            />

            <BulkDeleteDialog
              show={showBulkDeleteDialog}
              selectedCustomerIds={selectedCustomerIds}
              customers={customers}
              bulkActionLoading={bulkActionLoading}
              onClose={() => setShowBulkDeleteDialog(false)}
              onConfirm={handleBulkDelete}
            />

            <ImpersonateDialog
              show={showImpersonateDialog}
              selectedCustomer={selectedCustomer}
              impersonateLoading={impersonateLoading}
              onClose={() => setShowImpersonateDialog(false)}
              onConfirm={handleImpersonate}
            />
          </Tabs>

          {/* Follow-up email modal */}
          <LeadFollowUpModal
            lead={followUpLead}
            open={showFollowUpModal}
            onClose={() => {
              setShowFollowUpModal(false);
              setFollowUpLead(null);
            }}
            onSent={() => {
              fetchLeads();
            }}
          />
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}