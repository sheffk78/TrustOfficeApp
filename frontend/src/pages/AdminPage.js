import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import PageHelpButton from '@/components/PageHelpButton';
import { 
  Users, 
  Shield, 
  Search,
  ChevronLeft,
  ChevronRight,
  UserCog,
  Trash2,
  Gift,
  Clock,
  DollarSign,
  TrendingUp,
  FileText,
  Building2,
  Crown,
  UserPlus,
  Link2,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Eye,
  CheckSquare,
  LogIn,
  BarChart3,
  Calendar,
  Target,
  MessageSquare,
  Activity
} from 'lucide-react';

function formatLastActive(lastLogin) {
  if (!lastLogin) return '—';
  const now = new Date();
  const date = new Date(lastLogin);
  const diffMs = now - date;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours === 0) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60));
      if (diffMinutes === 0) return 'Just now';
      return `${diffMinutes} min ago`;
    }
    if (diffHours === 1) return '1 hour ago';
    return `${diffHours} hours ago`;
  }
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 30) return `${diffDays} days ago`;
  return date.toLocaleDateString();
}

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
  
  // Check if user is admin - first check from user object, then verify with API
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminCheckDone, setAdminCheckDone] = useState(false);
  
  // Quick check from user email
  const isPrimaryAdmin = user?.email?.toLowerCase() === 'contact@trustoffice.app';

  // Check admin status via API
  useEffect(() => {
    const checkAdmin = async () => {
      // If user has is_admin flag or is primary admin, grant access immediately
      if (user?.is_admin || isPrimaryAdmin) {
        setIsAdmin(true);
        // Still fetch stats
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
      
      // Otherwise check via API
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

  // Fetch customers
  const fetchCustomers = useCallback(async () => {
    if (!isAdmin) return;
    
    try {
      let url = `/admin/customers?page=${customerPage}&limit=20`;
      if (customerSearch) url += `&search=${encodeURIComponent(customerSearch)}`;
      if (statusFilter !== 'all') url += `&status=${statusFilter}`;
      
      console.log('[AdminPage] Fetching customers:', url);
      const response = await fetchWithAuth(url);
      console.log('[AdminPage] Response status:', response.status);
      
      if (response.ok) {
        const data = await response.json();
        console.log('[AdminPage] Customers received:', data.total, 'total,', data.customers?.length, 'in this page');
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

  // Fetch customer detail
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

  // Fetch referrals
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

  // Fetch leads
  const fetchLeads = async () => {
    setLeadsLoading(true);
    try {
      let url = `/admin/leads?page=${leadsPage}&limit=20`;
      if (leadsSearch) url += `&search=${encodeURIComponent(leadsSearch)}`;
      if (leadsStageFilter !== 'all') url += `&stage=${leadsStageFilter}`;
      
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

  // Fetch lead analytics
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

  // Export leads as CSV
  const exportLeadsCsv = async () => {
    try {
      let url = '/admin/leads/export';
      if (leadsStageFilter !== 'all') url += `?stage=${leadsStageFilter}`;
      const response = await fetchWithAuth(url);
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `trustoffice-leads-${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        toast.success('Leads exported as CSV');
      }
    } catch (error) {
      console.error('Failed to export leads:', error);
      toast.error('Failed to export leads');
    }
  };

  // Bulk lead actions
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

  const clearLeadSelection = () => {
    setSelectedLeadIds(new Set());
  };

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
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `trustoffice-selected-leads-${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        toast.success(`Exported ${selectedLeadIds.size} leads`);
      }
    } catch (error) {
      toast.error('Failed to export selected leads');
    }
  };

  // Fetch lead detail
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

  // Add lead note
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

  // Update lead stage
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

  // Fetch admins
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

  // Fetch revenue data
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

  // Fetch stats users
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

  // Grant/revoke stats access handlers
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

  useEffect(() => {
    if (isAdmin && activeTab === 'referrals') {
      fetchReferrals();
    }
    if (isAdmin && activeTab === 'leads') {
      fetchLeads();
    }
    if (isAdmin && activeTab === 'lead-analytics') {
      fetchLeadAnalytics();
    }
    if (isAdmin && activeTab === 'admins') {
      fetchAdmins();
    }
    if (isAdmin && activeTab === 'revenue') {
      fetchRevenueData();
    }
    if (isAdmin && activeTab === 'admins') {
      fetchStatsUsers();
    }
  }, [isAdmin, activeTab, revenuePreset, fetchRevenueData]);

  // Actions
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

  // Multi-select handlers
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
    if (selectedCustomerIds.size === customers.filter(c => !c.is_admin && c.email !== 'contact@trustoffice.app').length) {
      setSelectedCustomerIds(new Set());
    } else {
      // Select all non-admin customers
      const selectableIds = customers
        .filter(c => !c.is_admin && c.email !== 'contact@trustoffice.app')
        .map(c => c.user_id);
      setSelectedCustomerIds(new Set(selectableIds));
    }
  };

  const clearSelection = () => {
    setSelectedCustomerIds(new Set());
  };

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
        // Refresh stats
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

  // Impersonation handler
  const handleImpersonate = async () => {
    if (!selectedCustomer) return;
    
    setImpersonateLoading(true);
    try {
      const response = await fetchWithAuth(`/admin/impersonate/${selectedCustomer.user_id}`, {
        method: 'POST'
      });
      
      if (response.ok) {
        const data = await response.json();
        
        // Store admin's current token and user data for later restoration
        const adminToken = localStorage.getItem('auth_token');
        sessionStorage.setItem('admin_token', adminToken);
        sessionStorage.setItem('admin_user_data', JSON.stringify(user));
        
        // Store impersonation metadata for the banner
        sessionStorage.setItem('impersonation_data', JSON.stringify({
          email: data.user.email,
          name: data.user.name,
          userId: data.user.user_id,
          adminEmail: user.email,
          startTime: new Date().toISOString()
        }));
        
        // Set the new token for the impersonated user
        localStorage.setItem('auth_token', data.token);
        
        // Update user in context
        setUser(data.user);
        
        // Reload trusts and subscription for the impersonated user
        await loadTrusts();
        await loadSubscriptionState(data.user.email);
        
        toast.success(`Now viewing as ${data.user.email}`);
        setShowImpersonateDialog(false);
        
        // Navigate to dashboard
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

  // Status badge helper
  const getStatusBadge = (status) => {
    const styles = {
      active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
      trialing: 'bg-gold/20 text-gold dark:bg-gold/30 dark:text-gold',
      expired: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
      canceled: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
      none: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
    };
    return styles[status] || styles.none;
  };

  // Show access denied if not admin
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
            <PageHelpButton
              items={[
                { text: 'Manage customers, subscriptions, and system administration' },
                { text: 'View and manage leads, extend trials, and gift subscriptions' },
                { text: 'Access revenue data and customer details' },
              ]}
              taPrompt="Walk me through the Admin panel"
            />
          </div>

          {/* Stats Cards */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4 mb-8">
              <div className="card-trust p-4">
                <div className="flex items-center gap-2 text-muted-foreground mb-1">
                  <Users className="w-4 h-4" />
                  <span className="text-xs">Total Users</span>
                </div>
                <p className="text-2xl font-bold text-navy dark:text-white">{stats.total_users}</p>
              </div>
              <div className="card-trust p-4">
                <div className="flex items-center gap-2 text-muted-foreground mb-1">
                  <CheckCircle className="w-4 h-4 text-green-500" />
                  <span className="text-xs">Active Subs</span>
                </div>
                <p className="text-2xl font-bold text-green-600">{stats.active_subscriptions}</p>
              </div>
              <div className="card-trust p-4">
                <div className="flex items-center gap-2 text-muted-foreground mb-1">
                  <Gift className="w-4 h-4 text-gold" />
                  <span className="text-xs">Gifted</span>
                </div>
                <p className="text-2xl font-bold text-gold">{stats.gifted_users || stats.trial_users}</p>
              </div>
              <div className="card-trust p-4">
                <div className="flex items-center gap-2 text-muted-foreground mb-1">
                  <TrendingUp className="w-4 h-4 text-purple-500" />
                  <span className="text-xs">New (30d)</span>
                </div>
                <p className="text-2xl font-bold text-purple-600">{stats.new_users_30d}</p>
              </div>
              <div className="card-trust p-4">
                <div className="flex items-center gap-2 text-muted-foreground mb-1">
                  <DollarSign className="w-4 h-4 text-gold" />
                  <span className="text-xs">Est. MRR</span>
                </div>
                <p className="text-2xl font-bold text-gold">${stats.revenue_estimate_monthly}</p>
              </div>
            </div>
          )}

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="mb-6">
              <TabsTrigger value="customers" className="flex items-center gap-2">
                <Users className="w-4 h-4" />
                Customers
              </TabsTrigger>
              <TabsTrigger value="revenue" className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4" />
                Revenue
              </TabsTrigger>
              <TabsTrigger value="admins" className="flex items-center gap-2">
                <Crown className="w-4 h-4" />
                Admins
              </TabsTrigger>
              <TabsTrigger value="referrals" className="flex items-center gap-2">
                <Link2 className="w-4 h-4" />
                Referrals
              </TabsTrigger>
              <TabsTrigger value="leads" className="flex items-center gap-2">
                <Target className="w-4 h-4" />
                Leads
                {leadsStageCounts.new > 0 && (
                  <span className="ml-1 px-1.5 py-0.5 text-xs bg-rust text-white rounded-full">
                    {leadsStageCounts.new}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="lead-analytics" className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4" />
                Lead Analytics
              </TabsTrigger>
            </TabsList>

            {/* Revenue Tab */}
            <TabsContent value="revenue">
              {/* Date Range Selector */}
              <div className="card-trust p-4 mb-6">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-muted-foreground" />
                    <span className="font-medium text-navy dark:text-white text-sm">Date Range</span>
                  </div>
                  <button
                    onClick={() => fetchRevenueData()}
                    className="flex items-center gap-2 text-sm text-muted-foreground hover:text-navy dark:hover:text-white"
                    disabled={revenueLoading}
                  >
                    <RefreshCw className={`w-4 h-4 ${revenueLoading ? 'animate-spin' : ''}`} />
                    Refresh
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {[
                    { key: 'today', label: 'Today' },
                    { key: 'this_week', label: 'This Week' },
                    { key: 'this_month', label: 'This Month' },
                    { key: 'last_30_days', label: 'Last 30 Days' },
                    { key: 'last_90_days', label: 'Last 90 Days' },
                    { key: 'all_time', label: 'All Time' },
                  ].map((p) => (
                    <button
                      key={p.key}
                      onClick={() => setRevenuePreset(p.key)}
                      className={`px-3 py-1.5 text-sm font-mono transition-colors ${
                        revenuePreset === p.key
                          ? 'bg-navy text-white dark:bg-gold dark:text-navy'
                          : 'bg-navy/5 dark:bg-white/5 text-navy dark:text-white hover:bg-navy/10 dark:hover:bg-white/10'
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                {revenueData?.date_range && (
                  <p className="text-xs text-muted-foreground mt-2 font-mono">
                    {new Date(revenueData.date_range.start).toLocaleDateString()} — {new Date(revenueData.date_range.end).toLocaleDateString()}
                  </p>
                )}
              </div>

              {/* Error state */}
              {revenueError && (
                <div className="card-trust p-4 mb-6 border border-rust/30 bg-rust/5 dark:bg-rust/10">
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5 text-rust" />
                    <p className="font-medium text-rust">{revenueError}</p>
                  </div>
                </div>
              )}

              {revenueLoading && !revenueData ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="w-8 h-8 animate-spin text-navy dark:text-white" />
                </div>
              ) : revenueData ? (
                <>
                  {/* Revenue Metric Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
                    <div className="card-trust p-4" title="Gross revenue from all paid TrustOffice invoices (Stripe) in the selected date range">
                      <div className="flex items-center gap-2 text-muted-foreground mb-1">
                        <DollarSign className="w-4 h-4 text-gold" />
                        <span className="text-xs">Total Revenue</span>
                      </div>
                      <p className="text-2xl font-bold text-navy dark:text-white">
                        {revenueData.total_revenue_formatted}
                      </p>
                    </div>
                    <div className="card-trust p-4" title="Monthly Recurring Revenue — (monthly subscribers × $79) + (annual subscribers × $65.83)">
                      <div className="flex items-center gap-2 text-muted-foreground mb-1">
                        <TrendingUp className="w-4 h-4 text-gold" />
                        <span className="text-xs">MRR</span>
                      </div>
                      <p className="text-2xl font-bold text-gold">
                        {revenueData.mrr_formatted}
                      </p>
                    </div>
                    <div className="card-trust p-4" title="Annual Recurring Revenue — MRR × 12. A projection of annual revenue based on current monthly subscriptions">
                      <div className="flex items-center gap-2 text-muted-foreground mb-1">
                        <TrendingUp className="w-4 h-4 text-navy dark:text-white" />
                        <span className="text-xs">ARR</span>
                      </div>
                      <p className="text-2xl font-bold text-navy dark:text-white">
                        {revenueData.arr_formatted}
                      </p>
                    </div>
                    <div className="card-trust p-4">
                      <div className="flex items-center gap-2 text-muted-foreground mb-1">
                        <Users className="w-4 h-4 text-navy dark:text-white" />
                        <span className="text-xs">Paid Customers</span>
                      </div>
                      <p className="text-2xl font-bold text-navy dark:text-white">
                        {revenueData.paid_customers}
                      </p>
                    </div>
                    <div className="card-trust p-4">
                      <div className="flex items-center gap-2 text-muted-foreground mb-1">
                        <DollarSign className="w-4 h-4 text-navy dark:text-white" />
                        <span className="text-xs">Avg/Customer</span>
                      </div>
                      <p className="text-2xl font-bold text-navy dark:text-white">
                        {revenueData.avg_revenue_per_customer_formatted}
                      </p>
                    </div>
                  </div>

                  {/* Period Revenue Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                    <div className="card-trust p-4">
                      <div className="text-xs text-muted-foreground mb-1">Today</div>
                      <p className="text-lg font-bold text-navy dark:text-white">{revenueData.revenue_today_formatted}</p>
                    </div>
                    <div className="card-trust p-4">
                      <div className="text-xs text-muted-foreground mb-1">This Week</div>
                      <p className="text-lg font-bold text-navy dark:text-white">{revenueData.revenue_this_week_formatted}</p>
                    </div>
                    <div className="card-trust p-4">
                      <div className="text-xs text-muted-foreground mb-1">This Month</div>
                      <p className="text-lg font-bold text-navy dark:text-white">{revenueData.revenue_this_month_formatted}</p>
                    </div>
                    <div className="card-trust p-4">
                      <div className="text-xs text-muted-foreground mb-1">All Time</div>
                      <p className="text-lg font-bold text-gold">{revenueData.revenue_all_time_formatted}</p>
                    </div>
                  </div>

                  {/* Revenue Over Time & Plan Breakdown */}
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                    {/* Revenue Chart */}
                    <div className="card-trust p-6 lg:col-span-2">
                      <h2 className="font-serif text-xl text-navy dark:text-white mb-4">Revenue Over Time</h2>
                      {revenueData?.stripe_error && (
                        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
                          <p className="text-sm text-red-600 dark:text-red-400">
                            <strong>Stripe Error:</strong> {revenueData.stripe_error}
                          </p>
                        </div>
                      )}
                      {revenueData?.revenue_by_month?.length > 0 ? (
                        <div className="space-y-2">
                          {revenueData.revenue_by_month.map((month) => {
                            const maxRev = Math.max(...revenueData.revenue_by_month.map(m => m.amount_cents));
                            return (
                              <div key={month.month} className="flex items-center gap-3">
                                <span className="text-xs font-mono text-muted-foreground w-20 shrink-0">
                                  {(() => {
                                    const [y, m] = month.month.split('-');
                                    return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
                                  })()}
                                </span>
                                <div className="flex-1 bg-navy/5 dark:bg-white/5 h-8 relative overflow-hidden">
                                  <div
                                    className="h-full bg-gold/80 dark:bg-gold/60 transition-all duration-300"
                                    style={{ width: maxRev > 0 ? `${(month.amount_cents / maxRev) * 100}%` : '0%' }}
                                  />
                                </div>
                                <span className="text-sm font-mono text-navy dark:text-white w-24 text-right shrink-0">
                                  ${(month.amount_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="text-center py-8 text-muted-foreground">
                          <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
                          <p>No revenue data available for this period</p>
                        </div>
                      )}
                    </div>

                    {/* Plan Breakdown */}
                    <div className="card-trust p-6">
                      <h2 className="font-serif text-xl text-navy dark:text-white mb-4">Plan Breakdown</h2>
                      <div className="space-y-4">
                        <div className="p-4 bg-navy/5 dark:bg-white/5">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium text-navy dark:text-white">Monthly</span>
                            <span className="text-sm font-mono text-gold">{revenueData.subscriptions_by_plan?.monthly || 0} invoices</span>
                          </div>
                          <div className="w-full bg-navy/10 dark:bg-white/10 h-2">
                            <div
                              className="h-full bg-gold transition-all"
                              style={{ width: `${((revenueData.subscriptions_by_plan?.monthly || 0) / Math.max((revenueData.subscriptions_by_plan?.monthly || 0) + (revenueData.subscriptions_by_plan?.annual || 0), 1)) * 100}%` }}
                            />
                          </div>
                        </div>
                        <div className="p-4 bg-navy/5 dark:bg-white/5">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium text-navy dark:text-white">Annual</span>
                            <span className="text-sm font-mono text-navy dark:text-white">{revenueData.subscriptions_by_plan?.annual || 0} invoices</span>
                          </div>
                          <div className="w-full bg-navy/10 dark:bg-white/10 h-2">
                            <div
                              className="h-full bg-navy dark:bg-white transition-all"
                              style={{ width: `${((revenueData.subscriptions_by_plan?.annual || 0) / Math.max((revenueData.subscriptions_by_plan?.monthly || 0) + (revenueData.subscriptions_by_plan?.annual || 0), 1)) * 100}%` }}
                            />
                          </div>
                        </div>
                        <div className="border-t border-navy/10 dark:border-white/10 pt-4">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-muted-foreground">Active Monthly Subs</span>
                            <span className="text-sm font-bold text-navy dark:text-white">{revenueData.monthly_subs || 0}</span>
                          </div>
                          <div className="flex items-center justify-between mt-2">
                            <span className="text-sm font-medium text-muted-foreground">Active Annual Subs</span>
                            <span className="text-sm font-bold text-navy dark:text-white">{revenueData.annual_subs || 0}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Recent Transactions */}
                  <div className="card-trust p-6">
                    <h2 className="font-serif text-xl text-navy dark:text-white mb-4">
                      Recent Transactions
                    </h2>
                    {revenueData.recent_transactions?.length > 0 ? (
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead>
                            <tr className="border-b border-navy/10 dark:border-white/10">
                              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Date</th>
                              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Customer</th>
                              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Amount</th>
                              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Plan</th>
                              <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {revenueData.recent_transactions.slice(0, 25).map((tx, idx) => (
                              <tr key={idx} className="border-b border-navy/5 dark:border-white/5 hover:bg-navy/5 dark:hover:bg-white/5">
                                <td className="py-3 px-4 text-sm text-navy dark:text-white">
                                  {new Date(tx.date).toLocaleDateString()}
                                </td>
                                <td className="py-3 px-4 text-sm text-muted-foreground">
                                  {tx.customer_email || '—'}
                                </td>
                                <td className="py-3 px-4 text-sm font-mono text-gold">
                                  ${(tx.amount_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </td>
                                <td className="py-3 px-4">
                                  <span className={`px-2 py-0.5 text-xs font-mono ${
                                    tx.plan === 'annual'
                                      ? 'bg-navy/10 dark:bg-white/10 text-navy dark:text-white'
                                      : 'bg-gold/20 text-gold'
                                  }`}>
                                    {tx.plan}
                                  </span>
                                </td>
                                <td className="py-3 px-4">
                                  <span className="px-2 py-0.5 text-xs bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                                    {tx.status}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground">
                        <p>No transactions found for this period</p>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="card-trust p-12 text-center">
                  <BarChart3 className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-30" />
                  <h2 className="font-serif text-xl text-navy dark:text-white mb-2">No Revenue Data</h2>
                  <p className="text-muted-foreground">
                    Revenue data will appear here once there are paid subscriptions.
                  </p>
                </div>
              )}
            </TabsContent>

            {/* Customers Tab */}
            <TabsContent value="customers">
              <div className="card-trust">
                {/* Search and Filters */}
                <div className="flex flex-col md:flex-row gap-4 mb-6">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      placeholder="Search by email or name..."
                      value={customerSearch}
                      onChange={(e) => setCustomerSearch(e.target.value)}
                      className="pl-10 input-trust"
                    />
                  </div>
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger className="w-40 input-trust">
                      <SelectValue placeholder="All Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Status</SelectItem>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="trialing">Trialing</SelectItem>
                      <SelectItem value="expired">Expired</SelectItem>
                      <SelectItem value="canceled">Canceled</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button onClick={fetchCustomers} variant="outline">
                    <RefreshCw className="w-4 h-4" />
                  </Button>
                  <Button 
                    onClick={() => setShowCreateUserDialog(true)}
                    className="btn-primary"
                  >
                    <UserPlus className="w-4 h-4 mr-2" />
                    Add User
                  </Button>
                </div>

                {/* Bulk Action Bar */}
                {selectedCustomerIds.size > 0 && (
                  <div className="flex items-center justify-between p-3 mb-4 bg-navy/5 dark:bg-white/5 rounded-lg border border-navy/10 dark:border-white/10">
                    <div className="flex items-center gap-3">
                      <CheckSquare className="w-5 h-5 text-navy dark:text-white" />
                      <span className="font-medium text-navy dark:text-white">
                        {selectedCustomerIds.size} account{selectedCustomerIds.size !== 1 ? 's' : ''} selected
                      </span>
                      <Button variant="ghost" size="sm" onClick={clearSelection}>
                        Clear
                      </Button>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                        onClick={() => setShowBulkDeleteDialog(true)}
                      >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Delete Selected
                      </Button>
                    </div>
                  </div>
                )}

                {/* Customer List */}
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-navy/10 dark:border-white/10">
                        <th className="w-12 py-3 px-4">
                          <Checkbox
                            checked={customers.filter(c => !c.is_admin && c.email !== 'contact@trustoffice.app').length > 0 && 
                                     selectedCustomerIds.size === customers.filter(c => !c.is_admin && c.email !== 'contact@trustoffice.app').length}
                            onCheckedChange={toggleSelectAll}
                            aria-label="Select all"
                          />
                        </th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">User</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Status</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Plan</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Trusts</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Joined</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Last Active</th>
                        <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {customers.map((customer) => {
                        const isSelectable = !customer.is_admin && customer.email !== 'contact@trustoffice.app';
                        const isSelected = selectedCustomerIds.has(customer.user_id);
                        
                        return (
                        <tr 
                          key={customer.user_id} 
                          className={`border-b border-navy/5 dark:border-white/5 hover:bg-navy/5 dark:hover:bg-white/5 ${isSelected ? 'bg-navy/10 dark:bg-white/10' : ''}`}
                        >
                          <td className="py-3 px-4">
                            {isSelectable ? (
                              <Checkbox
                                checked={isSelected}
                                onCheckedChange={() => toggleSelectCustomer(customer.user_id)}
                                aria-label={`Select ${customer.name}`}
                              />
                            ) : (
                              <div className="w-4 h-4" /> 
                            )}
                          </td>
                          <td className="py-3 px-4">
                            <div>
                              <p className="font-medium text-navy dark:text-white flex items-center gap-2">
                                {customer.name}
                                {customer.is_admin && (
                                  <Crown className="w-4 h-4 text-gold" />
                                )}
                                {customer.is_stats_user && !customer.is_admin && (
                                  <BarChart3 className="w-4 h-4 text-gold" />
                                )}
                              </p>
                              <p className="text-sm text-muted-foreground">{customer.email}</p>
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <Badge className={getStatusBadge(customer.subscription_status)}>
                              {customer.subscription_status}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-sm text-muted-foreground">
                            {customer.subscription_plan}
                          </td>
                          <td className="py-3 px-4 text-sm text-muted-foreground">
                            {customer.trust_count}
                          </td>
                          <td className="py-3 px-4 text-sm text-muted-foreground">
                            {customer.created_at ? new Date(customer.created_at).toLocaleDateString() : '—'}
                          </td>
                          <td className="py-3 px-4 text-sm text-muted-foreground">
                            {formatLastActive(customer.last_login)}
                          </td>
                          <td className="py-3 px-4 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setSelectedCustomer(customer);
                                  fetchCustomerDetail(customer.user_id);
                                }}
                              >
                                <Eye className="w-4 h-4" />
                              </Button>
                              {!customer.is_admin && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setSelectedCustomer(customer);
                                    setShowImpersonateDialog(true);
                                  }}
                                  title="Login as this user"
                                  className="text-orange-500 hover:text-orange-600 hover:bg-orange-50 dark:hover:bg-orange-900/20"
                                >
                                  <LogIn className="w-4 h-4" />
                                </Button>
                              )}
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setSelectedCustomer(customer);
                                  setShowGrantAccessDialog(true);
                                }}
                              >
                                <Gift className="w-4 h-4" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                <div className="flex items-center justify-between mt-4 pt-4 border-t border-navy/10 dark:border-white/10">
                  <p className="text-sm text-muted-foreground">
                    Showing {customers.length} of {customerTotal} customers
                  </p>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCustomerPage(p => Math.max(1, p - 1))}
                      disabled={customerPage === 1}
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <span className="text-sm text-muted-foreground">Page {customerPage}</span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCustomerPage(p => p + 1)}
                      disabled={customers.length < 20}
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </div>
            </TabsContent>

            {/* Admins Tab */}
            <TabsContent value="admins">
              <div className="card-trust">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="font-serif text-xl text-navy dark:text-white">Administrator Accounts</h2>
                  <Button className="btn-primary" onClick={() => setShowCreateAdminDialog(true)}>
                    <UserPlus className="w-4 h-4 mr-2" />
                    Add Admin
                  </Button>
                </div>
                
                <div className="space-y-4">
                  {admins.map((admin) => (
                    <div key={admin.user_id} className="flex items-center justify-between p-4 border border-navy/10 dark:border-white/10 rounded-lg">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-full bg-gold/20 flex items-center justify-center">
                          <Crown className="w-5 h-5 text-gold" />
                        </div>
                        <div>
                          <p className="font-medium text-navy dark:text-white">{admin.name}</p>
                          <p className="text-sm text-muted-foreground">{admin.email}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {admin.email !== 'contact@trustoffice.app' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-500 hover:text-red-600 hover:bg-red-50"
                            onClick={() => handleRemoveAdmin(admin.user_id)}
                          >
                            <XCircle className="w-4 h-4 mr-2" />
                            Remove
                          </Button>
                        )}
                        {admin.email === 'contact@trustoffice.app' && (
                          <Badge className="bg-gold/20 text-gold">Primary Admin</Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Stats Users Section */}
              <div className="card-trust mt-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="font-serif text-xl text-navy dark:text-white flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-gold" />
                    Stats Users
                  </h2>
                  <p className="text-sm text-muted-foreground">Users with read-only revenue dashboard access</p>
                </div>
                
                {statsUsers.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">No stats users configured. Grant stats access from the customer detail view.</p>
                ) : (
                  <div className="space-y-4">
                    {statsUsers.map((su) => (
                      <div key={su.user_id} className="flex items-center justify-between p-4 border border-navy/10 dark:border-white/10 rounded-lg">
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 rounded-full bg-gold/20 flex items-center justify-center">
                            <BarChart3 className="w-5 h-5 text-gold" />
                          </div>
                          <div>
                            <p className="font-medium text-navy dark:text-white">
                              {su.name}
                              {su.is_admin && <Crown className="w-4 h-4 text-gold ml-2 inline" />}
                            </p>
                            <p className="text-sm text-muted-foreground">{su.email}</p>
                            {su.stats_granted_at && (
                              <p className="text-xs text-muted-foreground">Granted: {new Date(su.stats_granted_at).toLocaleDateString()}</p>
                            )}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-500 hover:text-red-600 hover:bg-red-50"
                          onClick={() => handleRevokeStats(su.user_id)}
                        >
                          <XCircle className="w-4 h-4 mr-2" />
                          Revoke Stats
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </TabsContent>

            {/* Referrals Tab */}
            <TabsContent value="referrals">
              <div className="card-trust">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="font-serif text-xl text-navy dark:text-white">Referral Relationships</h2>
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={fetchReferrals}>
                      <RefreshCw className={`w-4 h-4 ${referralsLoading ? 'animate-spin' : ''}`} />
                    </Button>
                    <Button className="btn-primary" onClick={() => setShowFixReferralDialog(true)}>
                      <Link2 className="w-4 h-4 mr-2" />
                      Fix Referral
                    </Button>
                  </div>
                </div>
                
                {referrals.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">No referrals found</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-navy/10 dark:border-white/10">
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Referrer</th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Referee</th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Status</th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {referrals.map((ref) => (
                          <tr key={ref.referral_id || ref.referee_user_id} className="border-b border-navy/5 dark:border-white/5">
                            <td className="py-3 px-4">
                              <p className="font-medium text-navy dark:text-white">{ref.referrer_name}</p>
                              <p className="text-sm text-muted-foreground">{ref.referrer_email}</p>
                            </td>
                            <td className="py-3 px-4">
                              <p className="font-medium text-navy dark:text-white">{ref.referee_name}</p>
                              <p className="text-sm text-muted-foreground">{ref.referee_email}</p>
                            </td>
                            <td className="py-3 px-4">
                              <Badge className={ref.status === 'converted' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}>
                                {ref.status}
                              </Badge>
                            </td>
                            <td className="py-3 px-4 text-sm text-muted-foreground">
                              {ref.created_at ? new Date(ref.created_at).toLocaleDateString() : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </TabsContent>

            {/* Leads Tab */}
            <TabsContent value="leads">
              <div className="card-trust">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="font-serif text-xl text-navy dark:text-white">Leads</h2>
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={exportLeadsCsv} title="Export all leads as CSV">
                      <FileText className="w-4 h-4 mr-2" />
                      Export
                    </Button>
                    <Button variant="outline" onClick={fetchLeads}>
                      <RefreshCw className={`w-4 h-4 ${leadsLoading ? 'animate-spin' : ''}`} />
                    </Button>
                  </div>
                </div>

                {/* Stage filter pills */}
                <div className="flex flex-wrap gap-2 mb-4">
                  {[
                    { key: 'all', label: 'All', count: leadsStageCounts.all },
                    { key: 'new', label: 'New', count: leadsStageCounts.new },
                    { key: 'engaged', label: 'Engaged', count: leadsStageCounts.engaged },
                    { key: 'warm', label: 'Warm', count: leadsStageCounts.warm },
                    { key: 'converted', label: 'Converted', count: leadsStageCounts.converted },
                    { key: 'lost', label: 'Lost', count: leadsStageCounts.lost },
                  ].map((s) => (
                    <button
                      key={s.key}
                      onClick={() => { setLeadsStageFilter(s.key); setLeadsPage(1); }}
                      className={`px-3 py-1.5 text-sm transition-colors ${
                        leadsStageFilter === s.key
                          ? 'bg-navy text-white dark:bg-gold dark:text-navy'
                          : 'bg-navy/5 dark:bg-white/5 text-navy dark:text-white hover:bg-navy/10 dark:hover:bg-white/10'
                      }`}
                    >
                      {s.label}
                      {s.count !== undefined && (
                        <span className="ml-1.5 text-xs opacity-70">({s.count})</span>
                      )}
                    </button>
                  ))}
                </div>

                {/* Search */}
                <div className="relative mb-4">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder="Search leads by name or email..."
                    value={leadsSearch}
                    onChange={(e) => setLeadsSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { setLeadsPage(1); fetchLeads(); } }}
                    className="w-full pl-10 pr-4 py-2 border border-navy/10 dark:border-white/10 bg-transparent text-navy dark:text-white text-sm focus:outline-none focus:border-gold"
                  />
                </div>

                {leadsLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <RefreshCw className="w-8 h-8 animate-spin text-navy dark:text-white" />
                  </div>
                ) : leads.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">No leads found</p>
                ) : (
                  <>
                    {/* Bulk Action Bar */}
                    {selectedLeadIds.size > 0 && (
                      <div className="flex items-center justify-between p-3 mb-4 bg-navy/5 dark:bg-white/5 rounded-lg border border-navy/10 dark:border-white/10">
                        <div className="flex items-center gap-3">
                          <CheckSquare className="w-5 h-5 text-navy dark:text-white" />
                          <span className="font-medium text-navy dark:text-white">
                            {selectedLeadIds.size} lead{selectedLeadIds.size !== 1 ? 's' : ''} selected
                          </span>
                          <Button variant="ghost" size="sm" onClick={clearLeadSelection}>
                            Clear
                          </Button>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleBulkLeadExport}
                          >
                            <FileText className="w-4 h-4 mr-1" />
                            Export
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setShowBulkLeadStageDialog(true)}
                          >
                            <Activity className="w-4 h-4 mr-1" />
                            Change Stage
                          </Button>
                        </div>
                      </div>
                    )}

                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-navy/10 dark:border-white/10">
                            <th className="w-10 py-3 px-2">
                              <Checkbox
                                checked={leads.length > 0 && selectedLeadIds.size === leads.length}
                                onCheckedChange={toggleSelectAllLeads}
                                aria-label="Select all leads"
                              />
                            </th>
                            <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Name</th>
                            <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Email</th>
                            <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Stage</th>
                            <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Score</th>
                            <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Next Action</th>
                            <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Source</th>
                            <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Created</th>
                            <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {leads.map((lead) => (
                            <tr key={lead.lead_id} className={`border-b border-navy/5 dark:border-white/5 hover:bg-navy/5 dark:hover:bg-white/5 ${selectedLeadIds.has(lead.lead_id) ? 'bg-navy/10 dark:bg-white/10' : ''}`}>
                              <td className="py-3 px-2">
                                <Checkbox
                                  checked={selectedLeadIds.has(lead.lead_id)}
                                  onCheckedChange={() => toggleSelectLead(lead.lead_id)}
                                  aria-label={`Select ${lead.name || lead.email}`}
                                />
                              </td>
                              <td className="py-3 px-4">
                                <p className="font-medium text-navy dark:text-white">{lead.name || '—'}</p>
                              </td>
                              <td className="py-3 px-4 text-sm text-muted-foreground">{lead.email}</td>
                              <td className="py-3 px-4">
                                <Badge className={
                                  lead.stage === 'new' ? 'bg-blue-100 text-blue-800' :
                                  lead.stage === 'engaged' ? 'bg-purple-100 text-purple-800' :
                                  lead.stage === 'warm' ? 'bg-amber-100 text-amber-800' :
                                  lead.stage === 'converted' ? 'bg-green-100 text-green-800' :
                                  'bg-gray-100 text-gray-800'
                                }>
                                  {lead.stage_label || lead.stage}
                                </Badge>
                              </td>
                              <td className="py-3 px-4">
                                <div className="flex items-center gap-2">
                                  <div className="w-16 h-2 bg-gray-200 rounded-full overflow-hidden">
                                    <div
                                      className={`h-full rounded-full ${
                                        lead.score >= 70 ? 'bg-green-500' :
                                        lead.score >= 40 ? 'bg-amber-500' :
                                        'bg-rust'
                                      }`}
                                      style={{ width: `${lead.score}%` }}
                                    />
                                  </div>
                                  <span className="text-xs text-muted-foreground">{lead.score}</span>
                                </div>
                              </td>
                              <td className="py-3 px-4 text-xs text-muted-foreground max-w-[200px] truncate">
                                {lead.next_action || '—'}
                              </td>
                              <td className="py-3 px-4 text-sm text-muted-foreground">{lead.source || '—'}</td>
                              <td className="py-3 px-4 text-sm text-muted-foreground">
                                {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '—'}
                              </td>
                              <td className="py-3 px-4">
                                <div className="flex gap-1">
                                  <button
                                    onClick={() => fetchLeadDetail(lead.lead_id)}
                                    className="p-1.5 text-muted-foreground hover:text-navy dark:hover:text-white transition-colors"
                                    title="View details"
                                  >
                                    <Eye className="w-4 h-4" />
                                  </button>
                                  <select
                                    value={lead.stage}
                                    onChange={(e) => updateLeadStage(lead.lead_id, e.target.value)}
                                    className="text-xs border border-navy/20 dark:border-white/20 bg-transparent rounded px-1 py-0.5"
                                    title="Change stage"
                                  >
                                    <option value="new">New</option>
                                    <option value="engaged">Engaged</option>
                                    <option value="warm">Warm</option>
                                    <option value="converted">Converted</option>
                                    <option value="lost">Lost</option>
                                  </select>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Pagination */}
                    {leadsTotal > 20 && (
                      <div className="flex items-center justify-between mt-4">
                        <p className="text-sm text-muted-foreground">
                          Showing {((leadsPage - 1) * 20) + 1}-{Math.min(leadsPage * 20, leadsTotal)} of {leadsTotal}
                        </p>
                        <div className="flex gap-2">
                          <button
                            onClick={() => { setLeadsPage(p => Math.max(1, p - 1)); }}
                            disabled={leadsPage === 1}
                            className="p-2 text-muted-foreground hover:text-navy dark:hover:text-white disabled:opacity-30"
                          >
                            <ChevronLeft className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => { setLeadsPage(p => p + 1); }}
                            disabled={leadsPage * 20 >= leadsTotal}
                            className="p-2 text-muted-foreground hover:text-navy dark:hover:text-white disabled:opacity-30"
                          >
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </TabsContent>

            {/* Lead Analytics Tab */}
            <TabsContent value="lead-analytics">
              <div className="card-trust p-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="font-serif text-xl text-navy dark:text-white">Lead Analytics</h2>
                  <Button variant="outline" onClick={fetchLeadAnalytics}>
                    <RefreshCw className={`w-4 h-4 ${leadAnalyticsLoading ? 'animate-spin' : ''}`} />
                  </Button>
                </div>

                {leadAnalyticsLoading && !leadAnalytics ? (
                  <div className="flex items-center justify-center py-12">
                    <RefreshCw className="w-8 h-8 animate-spin text-navy dark:text-white" />
                  </div>
                ) : leadAnalytics ? (
                  <div className="space-y-6">
                    {/* Funnel Overview */}
                    <div>
                      <h3 className="font-medium text-navy dark:text-white mb-3">Funnel</h3>
                      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                        {[
                          { key: 'new', label: 'New', color: 'bg-blue-500' },
                          { key: 'engaged', label: 'Engaged', color: 'bg-purple-500' },
                          { key: 'warm', label: 'Warm', color: 'bg-amber-500' },
                          { key: 'converted', label: 'Converted', color: 'bg-green-500' },
                          { key: 'lost', label: 'Lost', color: 'bg-gray-500' },
                        ].map((s) => (
                          <div key={s.key} className="p-3 border border-navy/10 dark:border-white/10 rounded-lg text-center">
                            <div className={`w-3 h-3 rounded-full ${s.color} mx-auto mb-1`} />
                            <p className="text-lg font-bold text-navy dark:text-white">{leadAnalytics.funnel?.[s.key] || 0}</p>
                            <p className="text-xs text-muted-foreground">{s.label}</p>
                          </div>
                        ))}
                        <div className="p-3 border border-navy/10 dark:border-white/10 rounded-lg text-center">
                          <p className="text-lg font-bold text-navy dark:text-white">{leadAnalytics.total_leads || 0}</p>
                          <p className="text-xs text-muted-foreground">Total</p>
                        </div>
                      </div>
                    </div>

                    {/* Conversion Stats */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="p-4 border border-navy/10 dark:border-white/10 rounded-lg">
                        <p className="text-xs text-muted-foreground mb-1">Total Converted</p>
                        <p className="text-2xl font-bold text-green-600">{leadAnalytics.total_converted || 0}</p>
                      </div>
                      <div className="p-4 border border-navy/10 dark:border-white/10 rounded-lg">
                        <p className="text-xs text-muted-foreground mb-1">Avg Time to Convert</p>
                        <p className="text-2xl font-bold text-navy dark:text-white">
                          {leadAnalytics.avg_time_to_convert_days !== null ? `${leadAnalytics.avg_time_to_convert_days} days` : '—'}
                        </p>
                      </div>
                      <div className="p-4 border border-navy/10 dark:border-white/10 rounded-lg">
                        <p className="text-xs text-muted-foreground mb-1">Median Time to Convert</p>
                        <p className="text-2xl font-bold text-navy dark:text-white">
                          {leadAnalytics.median_time_to_convert_days !== null ? `${leadAnalytics.median_time_to_convert_days} days` : '—'}
                        </p>
                      </div>
                    </div>

                    {/* Conversion by Source */}
                    <div>
                      <h3 className="font-medium text-navy dark:text-white mb-3">Conversion Rate by Source</h3>
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead>
                            <tr className="border-b border-navy/10 dark:border-white/10">
                              <th className="text-left py-2 px-3 text-sm font-medium text-muted-foreground">Source</th>
                              <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Total</th>
                              <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Converted</th>
                              <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Rate</th>
                            </tr>
                          </thead>
                          <tbody>
                            {leadAnalytics.source_stats?.map((s) => (
                              <tr key={s.source} className="border-b border-navy/5 dark:border-white/5">
                                <td className="py-2 px-3 text-sm text-navy dark:text-white">{s.source}</td>
                                <td className="py-2 px-3 text-sm text-right text-muted-foreground">{s.total}</td>
                                <td className="py-2 px-3 text-sm text-right text-green-600">{s.converted}</td>
                                <td className="py-2 px-3 text-sm text-right font-mono">{s.conversion_rate}%</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* 30-Day Trend */}
                    <div>
                      <h3 className="font-medium text-navy dark:text-white mb-3">Leads Per Day (Last 30 Days)</h3>
                      {leadAnalytics.trend?.length > 0 ? (
                        <div className="space-y-1">
                          {leadAnalytics.trend.map((day) => {
                            const maxCount = Math.max(...leadAnalytics.trend.map(d => d.count), 1);
                            return (
                              <div key={day.date} className="flex items-center gap-3">
                                <span className="text-xs font-mono text-muted-foreground w-24 shrink-0">
                                  {new Date(day.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                </span>
                                <div className="flex-1 bg-navy/5 dark:bg-white/5 h-6 relative overflow-hidden">
                                  <div
                                    className="h-full bg-gold/70 transition-all duration-300"
                                    style={{ width: `${(day.count / maxCount) * 100}%` }}
                                  />
                                </div>
                                <span className="text-sm font-mono text-navy dark:text-white w-8 text-right shrink-0">
                                  {day.count}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">No lead data in the last 30 days</p>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-12 text-muted-foreground">
                    <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p>Click refresh to load lead analytics</p>
                  </div>
                )}
              </div>
            </TabsContent>

            {/* Lead Detail Dialog */}
            <Dialog open={!!selectedLead} onOpenChange={() => setSelectedLead(null)}>
              <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="font-serif text-xl text-navy dark:text-white flex items-center gap-2">
                    <Target className="w-5 h-5 text-gold" />
                    {selectedLead?.name || 'Lead Details'}
                  </DialogTitle>
                  <DialogDescription>{selectedLead?.email}</DialogDescription>
                </DialogHeader>

                {leadDetailLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <RefreshCw className="w-8 h-8 animate-spin text-navy dark:text-white" />
                  </div>
                ) : selectedLead ? (
                  <div className="space-y-4 py-4">
                    {/* Status Cards */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="p-3 border border-navy/10 dark:border-white/10 rounded-lg text-center">
                        <p className="text-xs text-muted-foreground mb-1">Stage</p>
                        <Badge className={
                          selectedLead.stage === 'new' ? 'bg-blue-100 text-blue-800' :
                          selectedLead.stage === 'engaged' ? 'bg-purple-100 text-purple-800' :
                          selectedLead.stage === 'warm' ? 'bg-amber-100 text-amber-800' :
                          selectedLead.stage === 'converted' ? 'bg-green-100 text-green-800' :
                          'bg-gray-100 text-gray-800'
                        }>
                          {selectedLead.stage_label || selectedLead.stage}
                        </Badge>
                      </div>
                      <div className="p-3 border border-navy/10 dark:border-white/10 rounded-lg text-center">
                        <p className="text-xs text-muted-foreground mb-1">Score</p>
                        <p className="text-lg font-bold text-navy dark:text-white">{selectedLead.score || 0}</p>
                      </div>
                      <div className="p-3 border border-navy/10 dark:border-white/10 rounded-lg text-center">
                        <p className="text-xs text-muted-foreground mb-1">Plan</p>
                        <p className="text-sm font-medium text-navy dark:text-white capitalize">{selectedLead.plan_type}</p>
                      </div>
                      <div className="p-3 border border-navy/10 dark:border-white/10 rounded-lg text-center">
                        <p className="text-xs text-muted-foreground mb-1">Lessons</p>
                        <p className="text-lg font-bold text-navy dark:text-white">{selectedLead.lessons_watched || 0}/9</p>
                      </div>
                    </div>

                    {/* Score Breakdown */}
                    {selectedLead.score_breakdown && (
                      <div className="p-4 border border-navy/10 dark:border-white/10 rounded-lg">
                        <h3 className="text-sm font-medium text-navy dark:text-white mb-3 flex items-center gap-2">
                          <Activity className="w-4 h-4 text-gold" />
                          Score Breakdown
                        </h3>
                        <div className="space-y-2">
                          {Object.entries(selectedLead.score_breakdown).map(([key, item]) => (
                            <div key={key} className="flex items-center gap-3">
                              <div className="flex-1">
                                <div className="flex items-center justify-between mb-0.5">
                                  <span className="text-xs text-muted-foreground capitalize">
                                    {key.replace(/_/g, ' ')}
                                  </span>
                                  <span className="text-xs font-mono text-navy dark:text-white">
                                    {item.score}/{item.max}
                                  </span>
                                </div>
                                <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                  <div
                                    className={`h-full rounded-full ${
                                      item.score / item.max >= 0.7 ? 'bg-green-500' :
                                      item.score / item.max >= 0.4 ? 'bg-amber-500' :
                                      'bg-rust'
                                    }`}
                                    style={{ width: `${(item.score / item.max) * 100}%` }}
                                  />
                                </div>
                                <p className="text-xs text-muted-foreground mt-0.5">{item.detail}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Next Action */}
                    <div className="p-3 border border-gold/30 bg-gold/5 rounded-lg">
                      <div className="flex items-center gap-2 mb-1">
                        <Activity className="w-4 h-4 text-gold" />
                        <span className="text-sm font-medium text-navy dark:text-white">Next Action</span>
                      </div>
                      <p className="text-sm text-muted-foreground">{selectedLead.next_action || 'Monitor — no action needed'}</p>
                    </div>

                    {/* Stage changer */}
                    <div>
                      <label className="text-sm font-medium text-navy dark:text-white block mb-2">Change Stage</label>
                      <div className="flex flex-wrap gap-2">
                        {['new', 'engaged', 'warm', 'converted', 'lost'].map((s) => (
                          <button
                            key={s}
                            onClick={() => updateLeadStage(selectedLead.lead_id, s)}
                            className={`px-3 py-1.5 text-sm transition-colors ${
                              selectedLead.stage === s
                                ? 'bg-navy text-white dark:bg-gold dark:text-navy'
                                : 'bg-navy/5 dark:bg-white/5 text-navy dark:text-white hover:bg-navy/10 dark:hover:bg-white/10'
                            }`}
                          >
                            {s.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Add Note */}
                    <div>
                      <label className="text-sm font-medium text-navy dark:text-white block mb-2">
                        <MessageSquare className="w-4 h-4 inline mr-1" />
                        Add Note
                      </label>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={leadNoteText}
                          onChange={(e) => setLeadNoteText(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') addLeadNote(selectedLead.lead_id); }}
                          placeholder="Type a note about this lead..."
                          className="flex-1 px-3 py-2 border border-navy/10 dark:border-white/10 bg-transparent text-navy dark:text-white text-sm focus:outline-none focus:border-gold"
                        />
                        <Button onClick={() => addLeadNote(selectedLead.lead_id)} disabled={!leadNoteText.trim()}>
                          Add
                        </Button>
                      </div>
                    </div>

                    {/* Activity Log */}
                    {selectedLead.activities && selectedLead.activities.length > 0 && (
                      <div>
                        <h3 className="text-sm font-medium text-navy dark:text-white mb-3">Activity Log</h3>
                        <div className="space-y-2 max-h-48 overflow-y-auto">
                          {selectedLead.activities.map((act, i) => (
                            <div key={act.activity_id || i} className="flex items-start gap-3 p-2 border-b border-navy/5 dark:border-white/5 last:border-0">
                              <div className="w-2 h-2 mt-1.5 rounded-full bg-gold shrink-0" />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-navy dark:text-white">{act.content}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">
                                  {act.action_type} · {act.created_at ? new Date(act.created_at).toLocaleString() : '—'}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : null}
              </DialogContent>
            </Dialog>

            {/* Bulk Lead Stage Change Dialog */}
            <Dialog open={showBulkLeadStageDialog} onOpenChange={setShowBulkLeadStageDialog}>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle className="font-serif text-xl text-navy dark:text-white flex items-center gap-2">
                    <Activity className="w-5 h-5 text-gold" />
                    Change {selectedLeadIds.size} Lead{selectedLeadIds.size !== 1 ? 's' : ''} Stage
                  </DialogTitle>
                  <DialogDescription>
                    Select the new stage for all selected leads.
                  </DialogDescription>
                </DialogHeader>
                
                <div className="py-4">
                  <div className="flex flex-wrap gap-2">
                    {['new', 'engaged', 'warm', 'converted', 'lost'].map((s) => (
                      <button
                        key={s}
                        onClick={() => setBulkLeadStage(s)}
                        className={`px-4 py-2 text-sm transition-colors ${
                          bulkLeadStage === s
                            ? 'bg-navy text-white dark:bg-gold dark:text-navy'
                            : 'bg-navy/5 dark:bg-white/5 text-navy dark:text-white hover:bg-navy/10 dark:hover:bg-white/10'
                        }`}
                      >
                        {s.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                      </button>
                    ))}
                  </div>
                </div>
                
                <DialogFooter>
                  <Button variant="outline" onClick={() => setShowBulkLeadStageDialog(false)} disabled={bulkLeadActionLoading}>
                    Cancel
                  </Button>
                  <Button 
                    className="btn-primary" 
                    onClick={handleBulkLeadStageChange}
                    disabled={bulkLeadActionLoading}
                  >
                    {bulkLeadActionLoading ? (
                      <>
                        <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        Updating...
                      </>
                    ) : (
                      `Move to ${bulkLeadStage.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}`
                    )}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </Tabs>

          {/* Customer Detail Sidebar */}
          {customerDetail && (
            <Dialog open={!!customerDetail} onOpenChange={() => { setCustomerDetail(null); setSelectedCustomer(null); }}>
              <DialogContent className="max-w-lg">
                <DialogHeader>
                  <DialogTitle className="font-serif text-xl text-navy dark:text-white flex items-center gap-2">
                    {customerDetail.name}
                    {customerDetail.is_admin && <Crown className="w-5 h-5 text-gold" />}
                  </DialogTitle>
                  <DialogDescription>{customerDetail.email}</DialogDescription>
                </DialogHeader>
                
                <div className="space-y-4 py-4">
                  {/* Subscription */}
                  <div className="p-4 border border-navy/10 dark:border-white/10 rounded-lg">
                    <h3 className="font-medium text-navy dark:text-white mb-2">Subscription</h3>
                    <div className="flex items-center gap-2">
                      <Badge className={getStatusBadge(customerDetail.subscription?.status)}>
                        {customerDetail.subscription?.status}
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        {customerDetail.subscription?.plan_type}
                      </span>
                      {customerDetail.is_stats_user && (
                        <Badge className="bg-gold/20 text-gold ml-2">
                          <BarChart3 className="w-3 h-3 mr-1" />
                          Stats Access
                        </Badge>
                      )}
                    </div>
                  </div>
                  
                  {/* Stats */}
                  <div className="grid grid-cols-3 gap-4">
                    <div className="p-3 border border-navy/10 dark:border-white/10 rounded-lg text-center">
                      <Building2 className="w-5 h-5 mx-auto mb-1 text-muted-foreground" />
                      <p className="text-lg font-bold text-navy dark:text-white">{customerDetail.stats?.trusts}</p>
                      <p className="text-xs text-muted-foreground">Trusts</p>
                    </div>
                    <div className="p-3 border border-navy/10 dark:border-white/10 rounded-lg text-center">
                      <FileText className="w-5 h-5 mx-auto mb-1 text-muted-foreground" />
                      <p className="text-lg font-bold text-navy dark:text-white">{customerDetail.stats?.minutes}</p>
                      <p className="text-xs text-muted-foreground">Minutes</p>
                    </div>
                    <div className="p-3 border border-navy/10 dark:border-white/10 rounded-lg text-center">
                      <DollarSign className="w-5 h-5 mx-auto mb-1 text-muted-foreground" />
                      <p className="text-lg font-bold text-navy dark:text-white">{customerDetail.stats?.distributions}</p>
                      <p className="text-xs text-muted-foreground">Distributions</p>
                    </div>
                  </div>
                  
                  {/* Referral Info */}
                  {customerDetail.referral_info && (
                    <div className="p-4 border border-navy/10 dark:border-white/10 rounded-lg">
                      <h3 className="font-medium text-navy dark:text-white mb-2">Referral Info</h3>
                      {customerDetail.referral_info.referral_code && (
                        <p className="text-sm text-muted-foreground">
                          Code: <span className="font-mono">{customerDetail.referral_info.referral_code}</span>
                        </p>
                      )}
                      {customerDetail.referral_info.referred_by && (
                        <p className="text-sm text-muted-foreground">Referred by another user</p>
                      )}
                      <p className="text-sm text-muted-foreground">
                        Successful referrals: {customerDetail.referral_info.successful_referrals}
                      </p>
                    </div>
                  )}
                  
                  {/* Actions */}
                  <div className="flex flex-wrap gap-2 pt-4 border-t border-navy/10 dark:border-white/10">
                    {!customerDetail.is_admin && (
                      <Button
                        size="sm"
                        className="bg-orange-500 hover:bg-orange-600 text-white"
                        onClick={() => {
                          setSelectedCustomer(customerDetail);
                          setCustomerDetail(null);
                          setShowImpersonateDialog(true);
                        }}
                      >
                        <LogIn className="w-4 h-4 mr-2" />
                        Login as User
                      </Button>
                    )}
                    
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setSelectedCustomer(customerDetail);
                        setShowGrantAccessDialog(true);
                      }}
                    >
                      <Gift className="w-4 h-4 mr-2" />
                      Grant Access
                    </Button>
                    
                    {!customerDetail.is_admin ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleMakeAdmin(customerDetail.user_id)}
                      >
                        <Crown className="w-4 h-4 mr-2" />
                        Make Admin
                      </Button>
                    ) : customerDetail.email !== 'contact@trustoffice.app' && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleRemoveAdmin(customerDetail.user_id)}
                      >
                        <XCircle className="w-4 h-4 mr-2" />
                        Remove Admin
                      </Button>
                    )}
                    
                    {customerDetail.is_stats_user ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-rust hover:text-rust"
                        onClick={() => handleRevokeStats(customerDetail.user_id)}
                      >
                        <BarChart3 className="w-4 h-4 mr-2" />
                        Revoke Stats
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleGrantStats(customerDetail.user_id)}
                      >
                        <BarChart3 className="w-4 h-4 mr-2" />
                        Grant Stats
                      </Button>
                    )}
                    
                    {customerDetail.email !== 'contact@trustoffice.app' && !customerDetail.is_admin && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-red-500 hover:text-red-600"
                        onClick={() => {
                          setSelectedCustomer(customerDetail);
                          setShowDeleteDialog(true);
                        }}
                      >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Delete
                      </Button>
                    )}
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          )}

          {/* Grant Access Dialog */}
          <Dialog open={showGrantAccessDialog} onOpenChange={setShowGrantAccessDialog}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="font-serif text-xl text-navy dark:text-white">Gift Access</DialogTitle>
                <DialogDescription>
                  Gift subscription access to {selectedCustomer?.email}
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 py-4">
                <div>
                  <Label className="label-trust">Plan Type</Label>
                  <Select 
                    value={grantAccessForm.plan_type} 
                    onValueChange={(v) => setGrantAccessForm({ ...grantAccessForm, plan_type: v })}
                  >
                    <SelectTrigger className="mt-1 input-trust">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="gifted_14day">Gift 14 Days</SelectItem>
                      <SelectItem value="gifted_monthly">Gift 1 Month</SelectItem>
                      <SelectItem value="gifted_annual">Gift 1 Year</SelectItem>
                      <SelectItem value="forever_free">Forever Free</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                {grantAccessForm.plan_type === 'gifted_14day' && (
                  <div>
                    <Label className="label-trust">Gift Days</Label>
                    <Input
                      type="number"
                      value={grantAccessForm.days}
                      onChange={(e) => setGrantAccessForm({ ...grantAccessForm, days: parseInt(e.target.value) })}
                      className="mt-1 input-trust"
                      min={1}
                      max={365}
                    />
                  </div>
                )}
              </div>
              
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowGrantAccessDialog(false)}>Cancel</Button>
                <Button className="btn-primary" onClick={handleGrantAccess}>Grant Access</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Delete Confirmation Dialog */}
          <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="font-serif text-xl text-red-600 flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5" />
                  Delete Customer
                </DialogTitle>
                <DialogDescription>
                  This will permanently delete {selectedCustomer?.email} and ALL their data including trusts, minutes, distributions, and settings.
                </DialogDescription>
              </DialogHeader>
              
              <div className="py-4">
                <p className="text-red-500 font-medium">This action cannot be undone!</p>
              </div>
              
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>Cancel</Button>
                <Button className="bg-red-600 hover:bg-red-700 text-white" onClick={handleDeleteCustomer}>
                  Delete Forever
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Create Admin Dialog */}
          <Dialog open={showCreateAdminDialog} onOpenChange={setShowCreateAdminDialog}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="font-serif text-xl text-navy dark:text-white">Create Admin User</DialogTitle>
                <DialogDescription>
                  Create a new admin account with full TrustOffice access.
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 py-4">
                <div>
                  <Label className="label-trust">Email *</Label>
                  <Input
                    type="email"
                    value={createAdminForm.email}
                    onChange={(e) => setCreateAdminForm({ ...createAdminForm, email: e.target.value })}
                    className="mt-1 input-trust"
                    placeholder="admin@example.com"
                  />
                </div>
                <div>
                  <Label className="label-trust">Name *</Label>
                  <Input
                    value={createAdminForm.name}
                    onChange={(e) => setCreateAdminForm({ ...createAdminForm, name: e.target.value })}
                    className="mt-1 input-trust"
                    placeholder="Admin Name"
                  />
                </div>
                <div>
                  <Label className="label-trust">Password (optional)</Label>
                  <Input
                    type="password"
                    value={createAdminForm.password}
                    onChange={(e) => setCreateAdminForm({ ...createAdminForm, password: e.target.value })}
                    className="mt-1 input-trust"
                    placeholder="Leave blank for OAuth-only"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    If no password is set, the user can only log in via Google OAuth.
                  </p>
                </div>
              </div>
              
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowCreateAdminDialog(false)}>Cancel</Button>
                <Button 
                  className="btn-primary" 
                  onClick={handleCreateAdmin}
                  disabled={!createAdminForm.email || !createAdminForm.name}
                >
                  Create Admin
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Create User Dialog */}
          <Dialog open={showCreateUserDialog} onOpenChange={setShowCreateUserDialog}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="font-serif text-xl text-navy dark:text-white">Add New User</DialogTitle>
                <DialogDescription>
                  Create a user account. They will receive a welcome email with a link to set their password.
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 py-4">
                <div>
                  <Label className="label-trust">Name *</Label>
                  <Input
                    value={createUserForm.name}
                    onChange={(e) => setCreateUserForm({ ...createUserForm, name: e.target.value })}
                    className="mt-1 input-trust"
                    placeholder="John Smith"
                  />
                </div>
                <div>
                  <Label className="label-trust">Email *</Label>
                  <Input
                    type="email"
                    value={createUserForm.email}
                    onChange={(e) => setCreateUserForm({ ...createUserForm, email: e.target.value })}
                    className="mt-1 input-trust"
                    placeholder="user@example.com"
                  />
                </div>
                <div>
                  <Label className="label-trust">Gift Tier *</Label>
                  <Select
                    value={createUserForm.gifted_tier}
                    onValueChange={(v) => setCreateUserForm({ ...createUserForm, gifted_tier: v })}
                  >
                    <SelectTrigger className="mt-1 input-trust">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="14day">Gift 14 Days</SelectItem>
                      <SelectItem value="monthly">Gift 1 Month</SelectItem>
                      <SelectItem value="annual">Gift 1 Year</SelectItem>
                      <SelectItem value="forever_free">Forever Free</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground mt-1">
                    This user will receive gifted access on the selected tier.
                  </p>
                </div>
                <p className="text-xs text-muted-foreground">
                  An email will be sent to this address with a link to set their password. The link expires in 24 hours.
                </p>
              </div>
              
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowCreateUserDialog(false)}>Cancel</Button>
                <Button 
                  className="btn-primary" 
                  onClick={handleCreateUser}
                  disabled={!createUserForm.email.trim() || !createUserForm.name.trim() || createUserLoading}
                >
                  {createUserLoading ? 'Creating...' : 'Add User'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Fix Referral Dialog */}
          <Dialog open={showFixReferralDialog} onOpenChange={setShowFixReferralDialog}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="font-serif text-xl text-navy dark:text-white">Fix Referral</DialogTitle>
                <DialogDescription>
                  Create, delete, or update a referral relationship.
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 py-4">
                <div>
                  <Label className="label-trust">Action</Label>
                  <Select 
                    value={fixReferralForm.action} 
                    onValueChange={(v) => setFixReferralForm({ ...fixReferralForm, action: v })}
                  >
                    <SelectTrigger className="mt-1 input-trust">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="create">Create Referral</SelectItem>
                      <SelectItem value="delete">Delete Referral</SelectItem>
                      <SelectItem value="update_status">Update Status</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="label-trust">Referrer Email</Label>
                  <Input
                    type="email"
                    value={fixReferralForm.referrer_email}
                    onChange={(e) => setFixReferralForm({ ...fixReferralForm, referrer_email: e.target.value })}
                    className="mt-1 input-trust"
                    placeholder="referrer@example.com"
                  />
                </div>
                <div>
                  <Label className="label-trust">Referee Email</Label>
                  <Input
                    type="email"
                    value={fixReferralForm.referee_email}
                    onChange={(e) => setFixReferralForm({ ...fixReferralForm, referee_email: e.target.value })}
                    className="mt-1 input-trust"
                    placeholder="referee@example.com"
                  />
                </div>
                {fixReferralForm.action === 'update_status' && (
                  <div>
                    <Label className="label-trust">New Status</Label>
                    <Select 
                      value={fixReferralForm.status} 
                      onValueChange={(v) => setFixReferralForm({ ...fixReferralForm, status: v })}
                    >
                      <SelectTrigger className="mt-1 input-trust">
                        <SelectValue placeholder="Select status" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="pending">Pending</SelectItem>
                        <SelectItem value="converted">Converted</SelectItem>
                        <SelectItem value="expired">Expired</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
              
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowFixReferralDialog(false)}>Cancel</Button>
                <Button 
                  className="btn-primary" 
                  onClick={handleFixReferral}
                  disabled={!fixReferralForm.referrer_email || !fixReferralForm.referee_email}
                >
                  Apply Fix
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Bulk Delete Confirmation Dialog */}
          <Dialog open={showBulkDeleteDialog} onOpenChange={setShowBulkDeleteDialog}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="font-serif text-xl text-red-600 flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5" />
                  Delete {selectedCustomerIds.size} Account{selectedCustomerIds.size !== 1 ? 's' : ''}
                </DialogTitle>
                <DialogDescription>
                  This will permanently delete the selected accounts and ALL their data including trusts, minutes, distributions, and settings.
                </DialogDescription>
              </DialogHeader>
              
              <div className="py-4">
                <p className="text-red-500 font-medium mb-3">This action cannot be undone!</p>
                <div className="max-h-40 overflow-y-auto bg-muted/50 rounded-lg p-3">
                  <p className="text-sm text-muted-foreground mb-2">Accounts to be deleted:</p>
                  <ul className="text-sm space-y-1">
                    {customers
                      .filter(c => selectedCustomerIds.has(c.user_id))
                      .map(c => (
                        <li key={c.user_id} className="text-navy dark:text-white">
                          • {c.email}
                        </li>
                      ))
                    }
                  </ul>
                </div>
              </div>
              
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowBulkDeleteDialog(false)} disabled={bulkActionLoading}>
                  Cancel
                </Button>
                <Button 
                  className="bg-red-600 hover:bg-red-700 text-white" 
                  onClick={handleBulkDelete}
                  disabled={bulkActionLoading}
                >
                  {bulkActionLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                      Deleting...
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-4 h-4 mr-2" />
                      Delete Forever
                    </>
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Impersonate User Confirmation Dialog */}
          <Dialog open={showImpersonateDialog} onOpenChange={setShowImpersonateDialog}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="font-serif text-xl text-orange-600 flex items-center gap-2">
                  <LogIn className="w-5 h-5" />
                  Login as User
                </DialogTitle>
                <DialogDescription>
                  You will be able to see and interact with the app exactly as this user sees it.
                </DialogDescription>
              </DialogHeader>
              
              <div className="py-4">
                <div className="bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded-lg p-4 mb-4">
                  <p className="text-sm text-orange-800 dark:text-orange-200 mb-2">
                    <strong>You are about to view as:</strong>
                  </p>
                  <p className="font-medium text-navy dark:text-white">
                    {selectedCustomer?.name}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {selectedCustomer?.email}
                  </p>
                </div>
                
                <ul className="text-sm text-muted-foreground space-y-2">
                  <li className="flex items-start gap-2">
                    <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 shrink-0" />
                    You'll see their dashboard, trusts, and all data
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 shrink-0" />
                    An orange banner will remind you that you're impersonating
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 shrink-0" />
                    Click "Exit Impersonation" to return to admin
                  </li>
                  <li className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                    This action is logged for audit purposes
                  </li>
                </ul>
              </div>
              
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowImpersonateDialog(false)} disabled={impersonateLoading}>
                  Cancel
                </Button>
                <Button 
                  className="bg-orange-500 hover:bg-orange-600 text-white" 
                  onClick={handleImpersonate}
                  disabled={impersonateLoading}
                >
                  {impersonateLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                      Switching...
                    </>
                  ) : (
                    <>
                      <LogIn className="w-4 h-4 mr-2" />
                      Login as User
                    </>
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
