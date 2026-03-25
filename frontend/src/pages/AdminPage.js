import { useState, useEffect, useCallback } from 'react';
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
  CheckSquare
} from 'lucide-react';

export default function AdminPage() {
  const { user } = useAuth();
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
  
  // Multi-select state
  const [selectedCustomerIds, setSelectedCustomerIds] = useState(new Set());
  const [bulkActionLoading, setBulkActionLoading] = useState(false);
  
  // Form states
  const [grantAccessForm, setGrantAccessForm] = useState({ plan_type: 'trial', days: 14 });
  const [createAdminForm, setCreateAdminForm] = useState({ email: '', name: '', password: '' });
  const [fixReferralForm, setFixReferralForm] = useState({ referrer_email: '', referee_email: '', action: 'create', status: '' });
  
  // Referrals list
  const [referrals, setReferrals] = useState([]);
  const [referralsLoading, setReferralsLoading] = useState(false);
  
  // Admin list
  const [admins, setAdmins] = useState([]);
  
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

  useEffect(() => {
    if (isAdmin && activeTab === 'referrals') {
      fetchReferrals();
    }
    if (isAdmin && activeTab === 'admins') {
      fetchAdmins();
    }
  }, [isAdmin, activeTab]);

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

  // Status badge helper
  const getStatusBadge = (status) => {
    const styles = {
      active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
      trialing: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
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
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="page-title flex items-center gap-3">
                <Shield className="w-8 h-8 text-navy dark:text-white" />
                Admin Panel
              </h1>
              <p className="page-subtitle">Customer management and system administration</p>
            </div>
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
                  <Clock className="w-4 h-4 text-blue-500" />
                  <span className="text-xs">In Trial</span>
                </div>
                <p className="text-2xl font-bold text-blue-600">{stats.trial_users}</p>
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
              <TabsTrigger value="admins" className="flex items-center gap-2">
                <Crown className="w-4 h-4" />
                Admins
              </TabsTrigger>
              <TabsTrigger value="referrals" className="flex items-center gap-2">
                <Link2 className="w-4 h-4" />
                Referrals
              </TabsTrigger>
            </TabsList>

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
                <DialogTitle className="font-serif text-xl text-navy dark:text-white">Grant Access</DialogTitle>
                <DialogDescription>
                  Grant subscription access to {selectedCustomer?.email}
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
                      <SelectItem value="trial">Trial (14 days)</SelectItem>
                      <SelectItem value="monthly">Monthly (complimentary)</SelectItem>
                      <SelectItem value="annual">Annual (complimentary)</SelectItem>
                      <SelectItem value="forever_free">Forever Free</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                {grantAccessForm.plan_type === 'trial' && (
                  <div>
                    <Label className="label-trust">Trial Days</Label>
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
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
