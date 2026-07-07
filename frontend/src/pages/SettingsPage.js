import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import TrustDocumentSummary from '@/components/TrustDocumentSummary';
import { 
  User,
  Building2,
  Bell,
  Trash2,
  Save,
  CreditCard,
  Download,
  FileText,
  ChevronRight,
  Loader2,
  HeartHandshake,
  Mail,
  Clock,
  CheckCircle2,
  AlertCircle,
  MessageSquare,
  ExternalLink,
  Database,
  RefreshCw,
  Sparkles,
  Plus,
  Gift,
  Users,
  Copy,
  Check,
  DollarSign,
  Shield,
  Lock,
  Unlock
} from 'lucide-react';
import { Switch } from '@/components/ui/switch';

const API_BASE = process.env.REACT_APP_BACKEND_URL || 'https://api.trustoffice.app';

export default function SettingsPage() {
  // EIN formatting: auto-inserts dash so user sees XX-XXXXXXX as they type
  const formatEIN = (value) => {
    const digits = value.replace(/\D/g, '').slice(0, 9);
    if (digits.length <= 2) return digits;
    return digits.slice(0, 2) + '-' + digits.slice(2);
  };

  const navigate = useNavigate();
  const location = useLocation();
  const { user, setUser, selectedTrust, setSelectedTrust, loadTrusts } = useAuth();
  const [loading, setLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileName, setProfileName] = useState(user?.name || '');
  const [notificationPrefs, setNotificationPrefs] = useState({
    minutes_created: true,
    distribution_created: true,
    distribution_approved: true,
    task_reminders: true,
    task_overdue: true,
    subscription_updates: true,
    weekly_digest: false
  });
  const [notificationLoading, setNotificationLoading] = useState(false);
  const [userPrefs, setUserPrefs] = useState({ hide_watermark: false, admin_access_locked: false });
  const [userPrefsLoading, setUserPrefsLoading] = useState(false);
  
  // Demo data management state
  const [demoStatus, setDemoStatus] = useState(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [deleteDemoDialogOpen, setDeleteDemoDialogOpen] = useState(false);
  
  // Create trust modal state
  const [createTrustOpen, setCreateTrustOpen] = useState(false);
  const [newTrustData, setNewTrustData] = useState({
    name: '',
    trust_type: 'revocable_living',
    jurisdiction: '',
    role: 'Trustee',
    start_date: '',
    trustees: '',
    authority_clause: '',
    ein: '',
    state_code: '',
    tax_year_end_month: '',
    tax_year_end_day: '',
    is_fiscal_year: false
  });
  const [createTrustLoading, setCreateTrustLoading] = useState(false);
  
  // Referral state
  const [referralData, setReferralData] = useState(null);
  const [referralStats, setReferralStats] = useState(null);
  const [referralLoading, setReferralLoading] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  
  const [trustData, setTrustData] = useState({
    name: selectedTrust?.name || '',
    role: selectedTrust?.role || 'Trustee',
    review_cadence: selectedTrust?.review_cadence || 'quarterly',
    description: selectedTrust?.description || '',
    benevolence_enabled: selectedTrust?.benevolence_enabled || false,
    tax_status: selectedTrust?.tax_status || 'private',
    ein: selectedTrust?.ein || '',
    state_code: selectedTrust?.state_code || '',
    start_date: selectedTrust?.start_date || '',
    tax_year_end_month: selectedTrust?.tax_year_end_month?.toString() || '',
    tax_year_end_day: selectedTrust?.tax_year_end_day?.toString() || '',
    is_fiscal_year: selectedTrust?.is_fiscal_year || false,
    trustees: selectedTrust?.trustees || '',
    successor_trustee_name: selectedTrust?.successor_trustee_name || '',
    successor_trustee_email: selectedTrust?.successor_trustee_email || '',
    successor_trustee_phone: selectedTrust?.successor_trustee_phone || '',
    successor_trustee_relationship: selectedTrust?.successor_trustee_relationship || '',
    successor_trustee_notes: selectedTrust?.successor_trustee_notes || '',
    grantor_name: selectedTrust?.grantor_name || '',
    attorney_name: selectedTrust?.attorney_name || '',
    attorney_phone: selectedTrust?.attorney_phone || '',
    attorney_email: selectedTrust?.attorney_email || '',
    cpa_name: selectedTrust?.cpa_name || '',
    cpa_phone: selectedTrust?.cpa_phone || '',
    cpa_email: selectedTrust?.cpa_email || '',
    financial_advisor_name: selectedTrust?.financial_advisor_name || '',
    financial_advisor_phone: selectedTrust?.financial_advisor_phone || '',
    financial_advisor_email: selectedTrust?.financial_advisor_email || '',
    successor_instructions: selectedTrust?.successor_instructions || '',
    document_location: selectedTrust?.document_location || '',
  });

  // Governance: Spending Threshold state (synced from selectedTrust.governance_settings)
  const GOVERNANCE_CLASSIFICATIONS = [
    'Distribution', 'Compensation', 'Inter-Entity Transfer',
    'Operational Expense', 'Capital Contribution', 'Tax Payment', 'Other'
  ];
  const [spendingThreshold, setSpendingThreshold] = useState(() => {
    const st = selectedTrust?.governance_settings?.spending_threshold;
    return {
      amount: st?.amount ?? '',
      requires_minutes: st?.requires_minutes ?? false,
      scope_classifications: st?.scope_classifications || ['Operational Expense', 'Other'],
    };
  });

  const updateSpendingThreshold = (field, value) => {
    setSpendingThreshold(prev => ({ ...prev, [field]: value }));
  };

  const toggleScopeClassification = (cls) => {
    setSpendingThreshold(prev => {
      const current = prev.scope_classifications || [];
      const next = current.includes(cls)
        ? current.filter(c => c !== cls)
        : [...current, cls];
      return { ...prev, scope_classifications: next };
    });
  };

  // Scroll to section from dashboard hash (e.g., /settings#ein, /settings#formation-date)
  useEffect(() => {
    if (location.hash) {
      const targetId = location.hash.slice(1); // remove '#'
      // Map hash to the data-section attribute on the wrapper div
      const el = document.querySelector(`[data-section="${targetId}"]`);
      if (el) {
        setTimeout(() => {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('ring-2', 'ring-navy/30', 'rounded');
          setTimeout(() => el.classList.remove('ring-2', 'ring-navy/30', 'rounded'), 3000);
        }, 300);
      }
    }
  }, [location.hash]);

  // Re-sync trustData when selectedTrust changes (e.g., after initial load)
  useEffect(() => {
    if (selectedTrust) {
      // Auto-populate trustees from the account creator's name if not set
      let trustees = selectedTrust.trustees || '';
      if (!trustees && user?.name) {
        trustees = user.name;
      }
      setTrustData({
        name: selectedTrust.name || '',
        role: selectedTrust.role || 'Trustee',
        review_cadence: selectedTrust.review_cadence || 'quarterly',
        description: selectedTrust.description || '',
        benevolence_enabled: selectedTrust.benevolence_enabled || false,
        tax_status: selectedTrust.tax_status || 'private',
        ein: selectedTrust.ein || '',
        state_code: selectedTrust.state_code || '',
        start_date: selectedTrust.start_date || '',
        tax_year_end_month: selectedTrust.tax_year_end_month?.toString() || '',
        tax_year_end_day: selectedTrust.tax_year_end_day?.toString() || '',
        is_fiscal_year: selectedTrust.is_fiscal_year || false,
        trustees: trustees,
        successor_trustee_name: selectedTrust.successor_trustee_name || '',
        successor_trustee_email: selectedTrust.successor_trustee_email || '',
        successor_trustee_phone: selectedTrust.successor_trustee_phone || '',
        successor_trustee_relationship: selectedTrust.successor_trustee_relationship || '',
        successor_trustee_notes: selectedTrust.successor_trustee_notes || '',
        grantor_name: selectedTrust.grantor_name || '',
        attorney_name: selectedTrust.attorney_name || '',
        attorney_phone: selectedTrust.attorney_phone || '',
        attorney_email: selectedTrust.attorney_email || '',
        cpa_name: selectedTrust.cpa_name || '',
        cpa_phone: selectedTrust.cpa_phone || '',
        cpa_email: selectedTrust.cpa_email || '',
        financial_advisor_name: selectedTrust.financial_advisor_name || '',
        financial_advisor_phone: selectedTrust.financial_advisor_phone || '',
        financial_advisor_email: selectedTrust.financial_advisor_email || '',
        successor_instructions: selectedTrust.successor_instructions || '',
        document_location: selectedTrust.document_location || '',
      });
      // Sync spending threshold from trust governance_settings
      const st = selectedTrust.governance_settings?.spending_threshold;
      setSpendingThreshold({
        amount: st?.amount ?? '',
        requires_minutes: st?.requires_minutes ?? false,
        scope_classifications: st?.scope_classifications || ['Operational Expense', 'Other'],
      });
    }
  }, [selectedTrust?.trust_id, user?.name]);

  // Load notification preferences on mount
  useEffect(() => {
    loadNotificationPreferences();
    loadUserPreferences();
    loadDemoStatus();
    loadReferralData();
  }, []);

  const loadReferralData = async () => {
    setReferralLoading(true);
    try {
      // Load referral code and stats in parallel
      const [codeRes, statsRes] = await Promise.all([
        fetchWithAuth('/referrals/my-code'),
        fetchWithAuth('/referrals/stats')
      ]);
      
      if (codeRes.ok) {
        const codeData = await codeRes.json();
        setReferralData(codeData);
      }
      
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setReferralStats(statsData);
      }
    } catch (error) {
      console.error('Failed to load referral data:', error);
    } finally {
      setReferralLoading(false);
    }
  };

  const copyReferralLink = async () => {
    if (!referralData?.referral_link) return;
    
    try {
      await navigator.clipboard.writeText(referralData.referral_link);
      setLinkCopied(true);
      toast.success('Referral link copied!', {
        description: 'Share this link with friends to earn rewards.'
      });
      setTimeout(() => setLinkCopied(false), 3000);
    } catch (error) {
      showError(toast, error, { operation: 'copy', page: 'Settings' });
    }
  };

  const loadDemoStatus = async () => {
    try {
      const response = await fetchWithAuth('/demo/status');
      if (response.ok) {
        const data = await response.json();
        setDemoStatus(data);
      }
    } catch (error) {
      console.error('Failed to load demo status:', error);
    }
  };

  const handleSeedDemoData = async () => {
    setDemoLoading(true);
    try {
      const response = await fetchWithAuth('/demo/seed', { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        if (data.seeded) {
          toast.success('Demo data created successfully!', {
            description: 'Your account now has sample trusts and data to explore all features.'
          });
          await loadDemoStatus();
          await loadTrusts();
          // Reload the page to show new data
          window.location.reload();
        } else {
          toast.info('You already have data', {
            description: 'Delete existing data first to seed demo data.'
          });
        }
      } else {
        const error = await response.json().catch(() => ({}));
        showError(toast, new Error(error.detail || 'Failed to seed demo data'), { operation: 'seed', page: 'Settings' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'seed', page: 'Settings' });
    } finally {
      setDemoLoading(false);
    }
  };

  const handleDeleteDemoData = async () => {
    setDemoLoading(true);
    try {
      const response = await fetchWithAuth('/demo/data', { method: 'DELETE' });
      if (response.ok) {
        const data = await response.json();
        toast.success('All data deleted', {
          description: `Removed ${data.deleted_counts?.trusts || 0} trusts and associated records.`
        });
        setDeleteDemoDialogOpen(false);
        await loadDemoStatus();
        await loadTrusts();
        setSelectedTrust(null);
      } else {
        const error = await response.json().catch(() => ({}));
        showError(toast, new Error(error.detail || 'Failed to delete data'), { operation: 'delete', page: 'Settings' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'delete', page: 'Settings' });
    } finally {
      setDemoLoading(false);
    }
  };

  const loadNotificationPreferences = async () => {
    try {
      const response = await fetchWithAuth('/notifications/preferences');
      if (response.ok) {
        const data = await response.json();
        setNotificationPrefs(data);
      }
    } catch (error) {
      console.error('Failed to load notification preferences:', error);
    }
  };

  const loadUserPreferences = async () => {
    try {
      const response = await fetchWithAuth('/user/preferences');
      if (response.ok) {
        const data = await response.json();
        setUserPrefs(data);
      }
    } catch (error) {
      console.error('Failed to load user preferences:', error);
    }
  };

  const handleWatermarkToggle = async (checked) => {
    try {
      setUserPrefsLoading(true);
      const response = await fetchWithAuth('/user/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hide_watermark: checked })
      });
      
      if (response.ok) {
        setUserPrefs({ ...userPrefs, hide_watermark: checked });
        toast.success(checked ? 'Watermark hidden' : 'Watermark enabled');
      } else {
        const error = await response.json();
        showError(toast, error, { operation: 'update', page: 'Settings' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'update', page: 'Settings' });
    } finally {
      setUserPrefsLoading(false);
    }
  };

  const handleAdminAccessLockToggle = async () => {
    const newValue = !userPrefs.admin_access_locked;
    try {
      setUserPrefsLoading(true);
      const response = await fetchWithAuth('/user/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ admin_access_locked: newValue })
      });

      if (response.ok) {
        setUserPrefs({ ...userPrefs, admin_access_locked: newValue });
        toast.success(newValue ? 'Admin access locked' : 'Admin access unlocked');
      } else {
        const error = await response.json();
        showError(toast, error, { operation: 'update', page: 'Settings' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'update', page: 'Settings' });
    } finally {
      setUserPrefsLoading(false);
    }
  };

  const handleNotificationChange = async (key, value) => {
    const newPrefs = { ...notificationPrefs, [key]: value };
    setNotificationPrefs(newPrefs);
    
    try {
      setNotificationLoading(true);
      const response = await fetchWithAuth('/notifications/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value })
      });
      
      if (!response.ok) {
        // Revert on error — use functional updater to avoid stale closure
        setNotificationPrefs(prev => ({ ...prev, [key]: !value }));
        showError(toast, error, { operation: 'update', page: 'Settings' });
      }
    } catch (error) {
      setNotificationPrefs(prev => ({ ...prev, [key]: !value }));
      showError(toast, error, { operation: 'update', page: 'Settings' });
    } finally {
      setNotificationLoading(false);
    }
  };

  const handleUpdateProfile = async () => {
    if (!profileName.trim()) {
      toast.error('Name cannot be empty');
      return;
    }
    
    setLoading(true);
    try {
      const response = await fetchWithAuth('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify({ name: profileName.trim() })
      });
      
      if (response.ok) {
        const data = await response.json();
        setUser(prev => ({ ...prev, name: data.user.name }));
        setEditingProfile(false);
        toast.success('Profile updated');
      } else {
        const error = await response.json().catch(() => ({}));
        showError(toast, error, { operation: 'update', page: 'Settings' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'update', page: 'Settings' });
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (type) => {
    setExportLoading(type);
    try {
      const token = localStorage.getItem('auth_token') || document.cookie.split('; ').find(row => row.startsWith('session_token='))?.split('=')[1];
      const trustParam = selectedTrust ? `?trust_id=${selectedTrust.trust_id}` : '';
      
      const response = await fetch(`${API_BASE}/api/export/${type}${trustParam}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        },
        credentials: 'include'
      });
      
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${type}_export_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        toast.success(`${type.charAt(0).toUpperCase() + type.slice(1)} exported successfully`);
      } else {
        toast.error('Export failed');
      }
    } catch (error) {
      showError(toast, error, { operation: 'export', page: 'Settings' });
    } finally {
      setExportLoading(null);
    }
  };

  const handleUpdateTrust = async () => {
    if (!selectedTrust) {
      toast.error('No trust selected');
      return;
    }

    // Auto-compute is_fiscal_year from the date
    const month = Number(trustData.tax_year_end_month);
    const day = Number(trustData.tax_year_end_day);
    const computedFiscalYear = (month && day) ? !(month === 12 && day === 31) : false;

    setLoading(true);
    try {
      // Merge spending threshold into governance_settings so it persists on save
      const governance_settings = {
        ...(selectedTrust.governance_settings || {}),
        spending_threshold: {
          amount: spendingThreshold.amount === '' ? null : Number(spendingThreshold.amount),
          requires_minutes: spendingThreshold.requires_minutes ?? false,
          scope_classifications: spendingThreshold.scope_classifications || [],
        },
      };
      const payload = { ...trustData, is_fiscal_year: computedFiscalYear, governance_settings };
      const response = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error('Failed to update trust');
      }

      const updatedTrust = await response.json();
      setSelectedTrust(updatedTrust);
      await loadTrusts();
      toast.success('Trust updated');
    } catch (error) {
      showError(toast, error, { operation: 'update_trust', page: 'Settings' });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTrust = async () => {
    if (!selectedTrust) return;

    setLoading(true);
    try {
      const response = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error('Failed to delete trust');
      }

      toast.success('Trust deleted');
      setDeleteDialogOpen(false);
      setSelectedTrust(null);
      await loadTrusts();
      navigate('/dashboard');
    } catch (error) {
      showError(toast, error, { operation: 'delete_trust', page: 'Settings' });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTrust = async () => {
    if (!newTrustData.name.trim()) {
      toast.error('Trust name is required');
      return;
    }
    if (!newTrustData.jurisdiction.trim()) {
      toast.error('Jurisdiction is required');
      return;
    }

    setCreateTrustLoading(true);
    try {
      // Create the trust
      const response = await fetchWithAuth('/trusts', {
        method: 'POST',
        body: JSON.stringify({
          name: newTrustData.name.trim(),
          trust_type: newTrustData.trust_type,
          jurisdiction: newTrustData.jurisdiction.trim(),
          role: newTrustData.role,
          start_date: newTrustData.start_date || null,
          trustees: newTrustData.trustees.trim() || null,
          authority_clause: newTrustData.authority_clause.trim() || null,
          ein: newTrustData.ein.trim() || null,
          state_code: newTrustData.state_code.trim().toUpperCase() || null,
          tax_year_end_month: newTrustData.tax_year_end_month ? parseInt(newTrustData.tax_year_end_month) : null,
          tax_year_end_day: newTrustData.tax_year_end_day ? parseInt(newTrustData.tax_year_end_day) : null,
          is_fiscal_year: newTrustData.tax_year_end_month && newTrustData.tax_year_end_day
            ? !(Number(newTrustData.tax_year_end_month) === 12 && Number(newTrustData.tax_year_end_day) === 31)
            : false
        })
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to create trust');
      }

      const createdTrust = await response.json();
      
      // Backend auto-creates the trust entity with trustee_names synced from trust.trustees
      // No need to create a separate entity from the frontend
      
      toast.success('Trust created successfully!');
      setCreateTrustOpen(false);
      setNewTrustData({ name: '', trust_type: 'family', jurisdiction: '', role: 'Trustee', start_date: '', trustees: '', authority_clause: '', ein: '', state_code: '', tax_year_end_month: '', tax_year_end_day: '', is_fiscal_year: false });
      await loadTrusts();
      setSelectedTrust(createdTrust);
    } catch (error) {
      showError(toast, error, { operation: 'create_trust', page: 'Settings' });
    } finally {
      setCreateTrustLoading(false);
    }
  };

  return (
    <div className="main-layout" data-testid="settings-page">
      <Sidebar />
      <main className="main-content">
        <div className="page-container max-w-3xl">
          {/* Page Header */}
          <div className="page-header flex items-start justify-between">
            <div>
              <h1 className="page-title">Settings</h1>
              <p className="page-subtitle">
                Configure trust settings, preferences, and account details — manage notifications, security, and trust profile information
              </p>
            </div>
            <PageHelpButton
              items={[
                { text: 'Configure trust settings, preferences, and account details' },
                { text: 'Manage notifications, security, and trust profile information' },
                { text: 'Update your personal and billing information' },
              ]}
              taPrompt="Walk me through the Settings page and what I can configure"
            />
          </div>

          {/* Profile Section */}
          <div className="card-trust corner-mark mb-8">
            <div className="flex items-center gap-2 mb-6">
              <User className="w-5 h-5 text-navy" />
              <h2 className="font-serif text-xl text-navy">Profile</h2>
            </div>

            <div className="flex items-center gap-6">
              {user?.picture ? (
                <img src={user.picture} alt={user.name} className="w-20 h-20 object-cover" />
              ) : (
                <div className="w-20 h-20 bg-gold flex items-center justify-center">
                  <span className="font-serif text-3xl text-navy font-bold">
                    {user?.name?.charAt(0) || 'U'}
                  </span>
                </div>
              )}
              <div className="flex-1">
                {editingProfile ? (
                  <div className="space-y-3">
                    <div>
                      <Label className="label-trust">Display Name</Label>
                      <Input
                        value={profileName}
                        onChange={(e) => setProfileName(e.target.value)}
                        className="mt-1 input-trust max-w-xs"
                        placeholder="Your name"
                        data-testid="profile-name-input"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button
                        onClick={handleUpdateProfile}
                        disabled={loading}
                        className="btn-primary text-sm"
                        data-testid="save-profile-btn"
                      >
                        <Save className="w-4 h-4 mr-1" />
                        {loading ? 'Saving...' : 'Save'}
                      </Button>
                      <Button
                        onClick={() => {
                          setEditingProfile(false);
                          setProfileName(user?.name || '');
                        }}
                        variant="outline"
                        className="btn-secondary text-sm"
                        data-testid="cancel-profile-edit-btn"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-lg text-navy">{user?.name}</p>
                      <Button
                        onClick={() => setEditingProfile(true)}
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground hover:text-navy"
                        data-testid="edit-profile-btn"
                      >
                        Edit
                      </Button>
                    </div>
                    <p className="font-mono text-sm text-muted-foreground">{user?.email}</p>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-2">
                      User ID: {user?.user_id}
                    </p>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Create New Trust Section */}
          <div className="card-trust mb-8">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Plus className="w-5 h-5 text-navy" />
                <h2 className="font-serif text-xl text-navy">Create New Trust</h2>
              </div>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              Add another trust or organization to your account. Each trust has its own minutes, assets, distributions, and governance tracking.
            </p>
            <Dialog open={createTrustOpen} onOpenChange={setCreateTrustOpen}>
              <DialogTrigger asChild>
                <Button className="btn-primary" data-testid="create-trust-btn">
                  <Plus className="w-4 h-4 mr-2" />
                  Create New Trust
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle className="font-serif text-xl text-navy">Create New Trust</DialogTitle>
                  <DialogDescription>
                    Set up a new trust entity. You can add more details after creation.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div>
                    <Label className="label-trust">Trust Name *</Label>
                    <Input
                      value={newTrustData.name}
                      onChange={(e) => setNewTrustData({ ...newTrustData, name: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="e.g., Smith Family Trust"
                      data-testid="new-trust-name"
                    />
                  </div>
                  <div>
                    <Label className="label-trust">Trust Type</Label>
                    <Select 
                      value={newTrustData.trust_type} 
                      onValueChange={(v) => setNewTrustData({ ...newTrustData, trust_type: v })}
                    >
                      <SelectTrigger className="mt-1 input-trust">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="revocable_living">Revocable Living Trust</SelectItem>
                        <SelectItem value="irrevocable_family">Irrevocable Family Trust</SelectItem>
                        <SelectItem value="family">Family Trust (Legacy)</SelectItem>
                        <SelectItem value="charitable">Charitable Trust</SelectItem>
                        <SelectItem value="charitable_remainder">Charitable Remainder Trust</SelectItem>
                        <SelectItem value="business">Business Trust</SelectItem>
                        <SelectItem value="ecclesiastical">Ecclesiastical Trust</SelectItem>
                        <SelectItem value="special_needs">Special Needs Trust</SelectItem>
                        <SelectItem value="spendthrift">Spendthrift Trust</SelectItem>
                        <SelectItem value="testamentary">Testamentary Trust</SelectItem>
                        <SelectItem value="life_insurance">Life Insurance Trust</SelectItem>
                        <SelectItem value="land">Land Trust</SelectItem>
                        <SelectItem value="institutional">Institutional Trust</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="label-trust">State / Jurisdiction *</Label>
                    <Select 
                      value={newTrustData.jurisdiction}
                      onValueChange={(v) => setNewTrustData({ ...newTrustData, jurisdiction: v })}
                    >
                      <SelectTrigger className="mt-1 input-trust" data-testid="new-trust-jurisdiction">
                        <SelectValue placeholder="Select state..." />
                      </SelectTrigger>
                      <SelectContent className="max-h-72">
                        <SelectItem value="AL">Alabama</SelectItem>
                        <SelectItem value="AK">Alaska</SelectItem>
                        <SelectItem value="AZ">Arizona</SelectItem>
                        <SelectItem value="AR">Arkansas</SelectItem>
                        <SelectItem value="CA">California</SelectItem>
                        <SelectItem value="CO">Colorado</SelectItem>
                        <SelectItem value="CT">Connecticut</SelectItem>
                        <SelectItem value="DE">Delaware</SelectItem>
                        <SelectItem value="FL">Florida</SelectItem>
                        <SelectItem value="GA">Georgia</SelectItem>
                        <SelectItem value="HI">Hawaii</SelectItem>
                        <SelectItem value="ID">Idaho</SelectItem>
                        <SelectItem value="IL">Illinois</SelectItem>
                        <SelectItem value="IN">Indiana</SelectItem>
                        <SelectItem value="IA">Iowa</SelectItem>
                        <SelectItem value="KS">Kansas</SelectItem>
                        <SelectItem value="KY">Kentucky</SelectItem>
                        <SelectItem value="LA">Louisiana</SelectItem>
                        <SelectItem value="ME">Maine</SelectItem>
                        <SelectItem value="MD">Maryland</SelectItem>
                        <SelectItem value="MA">Massachusetts</SelectItem>
                        <SelectItem value="MI">Michigan</SelectItem>
                        <SelectItem value="MN">Minnesota</SelectItem>
                        <SelectItem value="MS">Mississippi</SelectItem>
                        <SelectItem value="MO">Missouri</SelectItem>
                        <SelectItem value="MT">Montana</SelectItem>
                        <SelectItem value="NE">Nebraska</SelectItem>
                        <SelectItem value="NV">Nevada</SelectItem>
                        <SelectItem value="NH">New Hampshire</SelectItem>
                        <SelectItem value="NJ">New Jersey</SelectItem>
                        <SelectItem value="NM">New Mexico</SelectItem>
                        <SelectItem value="NY">New York</SelectItem>
                        <SelectItem value="NC">North Carolina</SelectItem>
                        <SelectItem value="ND">North Dakota</SelectItem>
                        <SelectItem value="OH">Ohio</SelectItem>
                        <SelectItem value="OK">Oklahoma</SelectItem>
                        <SelectItem value="OR">Oregon</SelectItem>
                        <SelectItem value="PA">Pennsylvania</SelectItem>
                        <SelectItem value="RI">Rhode Island</SelectItem>
                        <SelectItem value="SC">South Carolina</SelectItem>
                        <SelectItem value="SD">South Dakota</SelectItem>
                        <SelectItem value="TN">Tennessee</SelectItem>
                        <SelectItem value="TX">Texas</SelectItem>
                        <SelectItem value="UT">Utah</SelectItem>
                        <SelectItem value="VT">Vermont</SelectItem>
                        <SelectItem value="VA">Virginia</SelectItem>
                        <SelectItem value="WA">Washington</SelectItem>
                        <SelectItem value="WV">West Virginia</SelectItem>
                        <SelectItem value="WI">Wisconsin</SelectItem>
                        <SelectItem value="WY">Wyoming</SelectItem>
                        <SelectItem value="DC">District of Columbia</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="label-trust">Trust Start Date</Label>
                    <Input
                      type="date"
                      value={newTrustData.start_date}
                      onChange={(e) => setNewTrustData({ ...newTrustData, start_date: e.target.value })}
                      className="mt-1 input-trust"
                      data-testid="new-trust-start-date"
                    />
                    <p className="text-xs text-muted-foreground mt-1">Date the trust was established</p>
                  </div>
                  <div>
                    <Label className="label-trust">Trustees</Label>
                    <Input
                      value={newTrustData.trustees}
                      onChange={(e) => setNewTrustData({ ...newTrustData, trustees: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="e.g., John Smith, Jane Smith"
                      data-testid="new-trust-trustees"
                    />
                    <p className="text-xs text-muted-foreground mt-1">Comma-separated list of trustees</p>
                  </div>
                  <div>
                    <Label className="label-trust">Authority Clause (from DOT)</Label>
                    <Textarea
                      value={newTrustData.authority_clause}
                      onChange={(e) => setNewTrustData({ ...newTrustData, authority_clause: e.target.value })}
                      className="mt-1 input-trust min-h-[80px]"
                      placeholder="Paste the authority/powers clause from your Declaration of Trust..."
                      data-testid="new-trust-authority"
                    />
                    <p className="text-xs text-muted-foreground mt-1">This will be referenced in minutes and other documents</p>
                  </div>

                  <div className="border-t border-navy/10 pt-4">
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">Tax & Compliance</p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="label-trust">EIN</Label>
                        <Input
                          value={newTrustData.ein}
                          onChange={(e) => setNewTrustData({ ...newTrustData, ein: formatEIN(e.target.value) })}
                          className="mt-1 input-trust"
                          placeholder="XX-XXXXXXX"
                          data-testid="new-trust-ein"
                        />
                      </div>
                      <div>
                        <Label className="label-trust">State / Jurisdiction</Label>
                        <Select 
                          value={newTrustData.state_code} 
                          onValueChange={(v) => setNewTrustData({ ...newTrustData, state_code: v })}
                        >
                          <SelectTrigger className="mt-1 input-trust" data-testid="new-trust-state">
                            <SelectValue placeholder="Select state..." />
                          </SelectTrigger>
                          <SelectContent className="max-h-72">
                            <SelectItem value="AL">Alabama</SelectItem>
                            <SelectItem value="AK">Alaska</SelectItem>
                            <SelectItem value="AZ">Arizona</SelectItem>
                            <SelectItem value="AR">Arkansas</SelectItem>
                            <SelectItem value="CA">California</SelectItem>
                            <SelectItem value="CO">Colorado</SelectItem>
                            <SelectItem value="CT">Connecticut</SelectItem>
                            <SelectItem value="DE">Delaware</SelectItem>
                            <SelectItem value="FL">Florida</SelectItem>
                            <SelectItem value="GA">Georgia</SelectItem>
                            <SelectItem value="HI">Hawaii</SelectItem>
                            <SelectItem value="ID">Idaho</SelectItem>
                            <SelectItem value="IL">Illinois</SelectItem>
                            <SelectItem value="IN">Indiana</SelectItem>
                            <SelectItem value="IA">Iowa</SelectItem>
                            <SelectItem value="KS">Kansas</SelectItem>
                            <SelectItem value="KY">Kentucky</SelectItem>
                            <SelectItem value="LA">Louisiana</SelectItem>
                            <SelectItem value="ME">Maine</SelectItem>
                            <SelectItem value="MD">Maryland</SelectItem>
                            <SelectItem value="MA">Massachusetts</SelectItem>
                            <SelectItem value="MI">Michigan</SelectItem>
                            <SelectItem value="MN">Minnesota</SelectItem>
                            <SelectItem value="MS">Mississippi</SelectItem>
                            <SelectItem value="MO">Missouri</SelectItem>
                            <SelectItem value="MT">Montana</SelectItem>
                            <SelectItem value="NE">Nebraska</SelectItem>
                            <SelectItem value="NV">Nevada</SelectItem>
                            <SelectItem value="NH">New Hampshire</SelectItem>
                            <SelectItem value="NJ">New Jersey</SelectItem>
                            <SelectItem value="NM">New Mexico</SelectItem>
                            <SelectItem value="NY">New York</SelectItem>
                            <SelectItem value="NC">North Carolina</SelectItem>
                            <SelectItem value="ND">North Dakota</SelectItem>
                            <SelectItem value="OH">Ohio</SelectItem>
                            <SelectItem value="OK">Oklahoma</SelectItem>
                            <SelectItem value="OR">Oregon</SelectItem>
                            <SelectItem value="PA">Pennsylvania</SelectItem>
                            <SelectItem value="RI">Rhode Island</SelectItem>
                            <SelectItem value="SC">South Carolina</SelectItem>
                            <SelectItem value="SD">South Dakota</SelectItem>
                            <SelectItem value="TN">Tennessee</SelectItem>
                            <SelectItem value="TX">Texas</SelectItem>
                            <SelectItem value="UT">Utah</SelectItem>
                            <SelectItem value="VT">Vermont</SelectItem>
                            <SelectItem value="VA">Virginia</SelectItem>
                            <SelectItem value="WA">Washington</SelectItem>
                            <SelectItem value="WV">West Virginia</SelectItem>
                            <SelectItem value="WI">Wisconsin</SelectItem>
                            <SelectItem value="WY">Wyoming</SelectItem>
                            <SelectItem value="DC">District of Columbia</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="label-trust">Tax Year End — Month</Label>
                        <Select 
                          value={newTrustData.tax_year_end_month} 
                          onValueChange={(v) => setNewTrustData({ ...newTrustData, tax_year_end_month: v })}
                        >
                          <SelectTrigger className="mt-1 input-trust">
                            <SelectValue placeholder="Month" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="12">DEC (Calendar)</SelectItem>
                            <SelectItem value="1">JAN</SelectItem>
                            <SelectItem value="2">FEB</SelectItem>
                            <SelectItem value="3">MAR</SelectItem>
                            <SelectItem value="4">APR</SelectItem>
                            <SelectItem value="5">MAY</SelectItem>
                            <SelectItem value="6">JUN</SelectItem>
                            <SelectItem value="7">JUL</SelectItem>
                            <SelectItem value="8">AUG</SelectItem>
                            <SelectItem value="9">SEP</SelectItem>
                            <SelectItem value="10">OCT</SelectItem>
                            <SelectItem value="11">NOV</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="label-trust">Day</Label>
                        <Input
                          type="number"
                          min={1}
                          max={31}
                          value={newTrustData.tax_year_end_day}
                          onChange={(e) => setNewTrustData({ ...newTrustData, tax_year_end_day: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="31"
                          data-testid="new-trust-tax-day"
                        />
                      </div>
                    </div>
                    {newTrustData.tax_year_end_month && newTrustData.tax_year_end_day && 
                     !(Number(newTrustData.tax_year_end_month) === 12 && Number(newTrustData.tax_year_end_day) === 31) && (
                      <p className="text-xs text-muted-foreground mt-3">
                        Fiscal year — tax deadlines will be calculated from this date.
                      </p>
                    )}
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setCreateTrustOpen(false)}>
                    Cancel
                  </Button>
                  <Button 
                    className="btn-primary" 
                    onClick={handleCreateTrust}
                    disabled={createTrustLoading}
                    data-testid="confirm-create-trust-btn"
                  >
                    {createTrustLoading ? (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <Plus className="w-4 h-4 mr-2" />
                    )}
                    Create Trust
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          {/* Trust Settings */}
          {selectedTrust && (
            <div className="card-trust mb-8">
              <div className="flex items-center gap-2 mb-6">
                <Building2 className="w-5 h-5 text-navy" />
                <h2 className="font-serif text-xl text-navy">Trust Settings</h2>
              </div>

              <div className="space-y-6">
                <div>
                  <Label className="label-trust">Trust Name</Label>
                  <Input
                    value={trustData.name}
                    onChange={(e) => setTrustData({ ...trustData, name: e.target.value })}
                    className="mt-1 input-trust"
                    data-testid="settings-trust-name"
                  />
                </div>

                {/* Trustees Management - shown first, auto-populated with account creator's name */}
                <div className="p-4 border-2 border-navy/20 bg-navy/5">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <Users className="w-4 h-4 text-navy" />
                        <Label className="label-trust">Trustees</Label>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        We auto-filled your name from your account. Update it or add co-trustees. These names appear in meeting minutes.
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        const current = trustData.trustees || '';
                        const names = current.split(',').map(t => t.trim()).filter(t => t);
                        names.push('');
                        setTrustData({ ...trustData, trustees: names.join(', ') });
                      }}
                    >
                      <Plus className="w-4 h-4 mr-1" />
                      Add Trustee
                    </Button>
                  </div>
                  <div className="space-y-2">
                    {(trustData.trustees || '').split(',').map(t => t.trim()).filter(t => t || true).map((trustee, index) => (
                      <div key={index} className="flex gap-2">
                        <Input
                          value={trustee}
                          onChange={(e) => {
                            const names = (trustData.trustees || '').split(',').map(t => t.trim());
                            names[index] = e.target.value;
                            setTrustData({ ...trustData, trustees: names.join(', ') });
                          }}
                          className="input-trust"
                          placeholder={index === 0 ? "Your name (as trustee)" : "Co-trustee name"}
                        />
                        {(trustData.trustees || '').split(',').map(t => t.trim()).filter(t => t).length > 1 && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-10 w-10 shrink-0 text-muted-foreground hover:text-red-600 hover:bg-red-50"
                            onClick={() => {
                              const names = (trustData.trustees || '').split(',').map(t => t.trim());
                              const filtered = names.filter((_, i) => i !== index);
                              setTrustData({ ...trustData, trustees: filtered.join(', ') });
                            }}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <Label className="label-trust">Review Cadence</Label>
                  <Select
                    value={trustData.review_cadence}
                    onValueChange={(value) => setTrustData({ ...trustData, review_cadence: value })}
                  >
                    <SelectTrigger className="mt-1 input-trust" data-testid="settings-cadence-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="monthly">Monthly</SelectItem>
                      <SelectItem value="quarterly">Quarterly</SelectItem>
                      <SelectItem value="annual">Annual</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label className="label-trust">Description</Label>
                  <Textarea
                    value={trustData.description}
                    onChange={(e) => setTrustData({ ...trustData, description: e.target.value })}
                    className="mt-1 input-trust min-h-[100px]"
                    placeholder="Brief description of the trust's purpose..."
                    data-testid="settings-trust-description"
                  />
                </div>

                {/* Benevolence Mode Section */}
                <div className="p-4 border border-navy/10 bg-navy/5">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <HeartHandshake className="w-5 h-5 text-navy mt-0.5" />
                      <div>
                        <h3 className="font-medium text-navy">Benevolence Mode</h3>
                        <p className="text-sm text-muted-foreground mt-1">
                          Enable charitable assistance tracking for 501/508-type trusts. 
                          This adds a dedicated benevolence log and specialized minutes templates.
                        </p>
                      </div>
                    </div>
                    <Switch
                      checked={trustData.benevolence_enabled}
                      onCheckedChange={(checked) => setTrustData({ ...trustData, benevolence_enabled: checked })}
                      data-testid="benevolence-toggle"
                    />
                  </div>
                  {trustData.benevolence_enabled && (
                    <div className="mt-4 pl-8">
                      <Label className="label-trust">Tax Status</Label>
                      <Select 
                        value={trustData.tax_status} 
                        onValueChange={(value) => setTrustData({ ...trustData, tax_status: value })}
                      >
                        <SelectTrigger className="mt-1 input-trust max-w-xs" data-testid="tax-status-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="501c3">501(c)(3) Organization</SelectItem>
                          <SelectItem value="508">508 Church/Religious Org</SelectItem>
                          <SelectItem value="private">Private Foundation</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </div>

                {/* Tax & Compliance Fields */}
                <div className="p-4 border border-navy/10 bg-navy/5">
                  <div className="flex items-start gap-3 mb-4">
                    <DollarSign className="w-5 h-5 text-navy mt-0.5" />
                    <div>
                      <h3 className="font-medium text-navy">Tax & Compliance Profile</h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        Required for Tax Calendar, State Compliance, and Risk Dashboard.
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div data-section="formation-date">
                      <Label className="label-trust">Formation Date</Label>
                      <Input
                        type="date"
                        value={trustData.start_date}
                        onChange={(e) => setTrustData({ ...trustData, start_date: e.target.value })}
                        className="mt-1 input-trust"
                        data-testid="settings-formation-date"
                      />
                      <p className="text-xs text-muted-foreground mt-1">When the trust was established</p>
                    </div>
                    <div data-section="ein">
                      <Label className="label-trust">EIN</Label>
                      <Input
                        value={trustData.ein}
                        onChange={(e) => setTrustData({ ...trustData, ein: formatEIN(e.target.value) })}
                        className="mt-1 input-trust"
                        placeholder="XX-XXXXXXX"
                        data-testid="settings-ein"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">State / Jurisdiction</Label>
                      <Select 
                        value={trustData.state_code} 
                        onValueChange={(value) => setTrustData({ ...trustData, state_code: value })}
                      >
                        <SelectTrigger className="mt-1 input-trust" data-testid="settings-state-code">
                          <SelectValue placeholder="Select state..." />
                        </SelectTrigger>
                        <SelectContent className="max-h-72">
                          <SelectItem value="AL">Alabama</SelectItem>
                          <SelectItem value="AK">Alaska</SelectItem>
                          <SelectItem value="AZ">Arizona</SelectItem>
                          <SelectItem value="AR">Arkansas</SelectItem>
                          <SelectItem value="CA">California</SelectItem>
                          <SelectItem value="CO">Colorado</SelectItem>
                          <SelectItem value="CT">Connecticut</SelectItem>
                          <SelectItem value="DE">Delaware</SelectItem>
                          <SelectItem value="FL">Florida</SelectItem>
                          <SelectItem value="GA">Georgia</SelectItem>
                          <SelectItem value="HI">Hawaii</SelectItem>
                          <SelectItem value="ID">Idaho</SelectItem>
                          <SelectItem value="IL">Illinois</SelectItem>
                          <SelectItem value="IN">Indiana</SelectItem>
                          <SelectItem value="IA">Iowa</SelectItem>
                          <SelectItem value="KS">Kansas</SelectItem>
                          <SelectItem value="KY">Kentucky</SelectItem>
                          <SelectItem value="LA">Louisiana</SelectItem>
                          <SelectItem value="ME">Maine</SelectItem>
                          <SelectItem value="MD">Maryland</SelectItem>
                          <SelectItem value="MA">Massachusetts</SelectItem>
                          <SelectItem value="MI">Michigan</SelectItem>
                          <SelectItem value="MN">Minnesota</SelectItem>
                          <SelectItem value="MS">Mississippi</SelectItem>
                          <SelectItem value="MO">Missouri</SelectItem>
                          <SelectItem value="MT">Montana</SelectItem>
                          <SelectItem value="NE">Nebraska</SelectItem>
                          <SelectItem value="NV">Nevada</SelectItem>
                          <SelectItem value="NH">New Hampshire</SelectItem>
                          <SelectItem value="NJ">New Jersey</SelectItem>
                          <SelectItem value="NM">New Mexico</SelectItem>
                          <SelectItem value="NY">New York</SelectItem>
                          <SelectItem value="NC">North Carolina</SelectItem>
                          <SelectItem value="ND">North Dakota</SelectItem>
                          <SelectItem value="OH">Ohio</SelectItem>
                          <SelectItem value="OK">Oklahoma</SelectItem>
                          <SelectItem value="OR">Oregon</SelectItem>
                          <SelectItem value="PA">Pennsylvania</SelectItem>
                          <SelectItem value="RI">Rhode Island</SelectItem>
                          <SelectItem value="SC">South Carolina</SelectItem>
                          <SelectItem value="SD">South Dakota</SelectItem>
                          <SelectItem value="TN">Tennessee</SelectItem>
                          <SelectItem value="TX">Texas</SelectItem>
                          <SelectItem value="UT">Utah</SelectItem>
                          <SelectItem value="VT">Vermont</SelectItem>
                          <SelectItem value="VA">Virginia</SelectItem>
                          <SelectItem value="WA">Washington</SelectItem>
                          <SelectItem value="WV">West Virginia</SelectItem>
                          <SelectItem value="WI">Wisconsin</SelectItem>
                          <SelectItem value="WY">Wyoming</SelectItem>
                          <SelectItem value="DC">District of Columbia</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Tax Year End — Month</Label>
                      <Select 
                        value={trustData.tax_year_end_month} 
                        onValueChange={(value) => setTrustData({ ...trustData, tax_year_end_month: value })}
                      >
                        <SelectTrigger className="mt-1 input-trust" data-testid="settings-tax-month">
                          <SelectValue placeholder="Month" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="12">DEC (Calendar)</SelectItem>
                          <SelectItem value="1">JAN</SelectItem>
                          <SelectItem value="2">FEB</SelectItem>
                          <SelectItem value="3">MAR</SelectItem>
                          <SelectItem value="4">APR</SelectItem>
                          <SelectItem value="5">MAY</SelectItem>
                          <SelectItem value="6">JUN</SelectItem>
                          <SelectItem value="7">JUL</SelectItem>
                          <SelectItem value="8">AUG</SelectItem>
                          <SelectItem value="9">SEP</SelectItem>
                          <SelectItem value="10">OCT</SelectItem>
                          <SelectItem value="11">NOV</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Day</Label>
                      <Input
                        type="number"
                        min={1}
                        max={31}
                        value={trustData.tax_year_end_day}
                        onChange={(e) => setTrustData({ ...trustData, tax_year_end_day: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="31"
                        data-testid="settings-tax-day"
                      />
                    </div>
                  </div>

                  {trustData.tax_year_end_month && trustData.tax_year_end_day && 
                   !(Number(trustData.tax_year_end_month) === 12 && Number(trustData.tax_year_end_day) === 31) && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Fiscal year — tax deadlines are calculated from this date.
                    </p>
                  )}
                </div>

                {/* Successor Trustee */}
                <div className="p-4 border border-navy/10 bg-navy/5">
                  <div className="flex items-start gap-3 mb-4">
                    <Shield className="w-5 h-5 text-navy mt-0.5" />
                    <div>
                      <h3 className="font-medium text-navy">Successor Trustee</h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        Designate who steps in if the trustee can no longer serve.
                      </p>
                    </div>
                  </div>

                  <div data-section="successor-trustee" className="space-y-3">
                    <div>
                      <Label className="label-trust">Successor Trustee Name</Label>
                      <Input
                        type="text"
                        value={trustData.successor_trustee_name}
                        onChange={(e) => setTrustData({ ...trustData, successor_trustee_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Who steps in if you can't serve?"
                      />
                      <p className="text-xs text-muted-foreground mt-1">The person named to take over if the trustee dies or becomes incapacitated</p>
                    </div>
                    <div>
                      <Label className="label-trust">Successor Trustee Email</Label>
                      <Input
                        type="email"
                        value={trustData.successor_trustee_email}
                        onChange={(e) => setTrustData({ ...trustData, successor_trustee_email: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="email@example.com"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Successor Trustee Phone</Label>
                      <Input
                        type="tel"
                        value={trustData.successor_trustee_phone}
                        onChange={(e) => setTrustData({ ...trustData, successor_trustee_phone: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="(555) 123-4567"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Relationship to Grantor</Label>
                      <Input
                        type="text"
                        value={trustData.successor_trustee_relationship}
                        onChange={(e) => setTrustData({ ...trustData, successor_trustee_relationship: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Spouse, adult child, sibling, etc."
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Notes</Label>
                      <Input
                        type="text"
                        value={trustData.successor_trustee_notes}
                        onChange={(e) => setTrustData({ ...trustData, successor_trustee_notes: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Any special instructions about the successor trustee"
                      />
                    </div>
                  </div>
                </div>

                {/* Grantor */}
                <div className="p-4 border border-navy/10 bg-navy/5">
                  <div className="flex items-start gap-3 mb-4">
                    <Users className="w-5 h-5 text-navy mt-0.5" />
                    <div>
                      <h3 className="font-medium text-navy">Grantor</h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        The person who created the trust.
                      </p>
                    </div>
                  </div>

                  <div data-section="grantor" className="space-y-3">
                    <div>
                      <Label className="label-trust">Grantor Name</Label>
                      <Input
                        type="text"
                        value={trustData.grantor_name}
                        onChange={(e) => setTrustData({ ...trustData, grantor_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Who created the trust?"
                      />
                      <p className="text-xs text-muted-foreground mt-1">The person who established the trust</p>
                    </div>
                  </div>
                </div>

                {/* Key Contacts */}
                <div className="p-4 border border-navy/10 bg-navy/5">
                  <div className="flex items-start gap-3 mb-4">
                    <Mail className="w-5 h-5 text-navy mt-0.5" />
                    <div>
                      <h3 className="font-medium text-navy">Key Contacts</h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        Trusted professionals associated with this trust.
                      </p>
                    </div>
                  </div>

                  <div data-section="key-contacts" className="space-y-4">
                    <div>
                      <Label className="label-trust">Trust Attorney</Label>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-1">
                        <Input type="text" value={trustData.attorney_name} onChange={(e) => setTrustData({ ...trustData, attorney_name: e.target.value })} className="input-trust" placeholder="Name" />
                        <Input type="tel" value={trustData.attorney_phone} onChange={(e) => setTrustData({ ...trustData, attorney_phone: e.target.value })} className="input-trust" placeholder="Phone" />
                        <Input type="email" value={trustData.attorney_email} onChange={(e) => setTrustData({ ...trustData, attorney_email: e.target.value })} className="input-trust" placeholder="Email" />
                      </div>
                    </div>
                    <div>
                      <Label className="label-trust">CPA / Tax Preparer</Label>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-1">
                        <Input type="text" value={trustData.cpa_name} onChange={(e) => setTrustData({ ...trustData, cpa_name: e.target.value })} className="input-trust" placeholder="Name" />
                        <Input type="tel" value={trustData.cpa_phone} onChange={(e) => setTrustData({ ...trustData, cpa_phone: e.target.value })} className="input-trust" placeholder="Phone" />
                        <Input type="email" value={trustData.cpa_email} onChange={(e) => setTrustData({ ...trustData, cpa_email: e.target.value })} className="input-trust" placeholder="Email" />
                      </div>
                    </div>
                    <div>
                      <Label className="label-trust">Financial Advisor</Label>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-1">
                        <Input type="text" value={trustData.financial_advisor_name} onChange={(e) => setTrustData({ ...trustData, financial_advisor_name: e.target.value })} className="input-trust" placeholder="Name" />
                        <Input type="tel" value={trustData.financial_advisor_phone} onChange={(e) => setTrustData({ ...trustData, financial_advisor_phone: e.target.value })} className="input-trust" placeholder="Phone" />
                        <Input type="email" value={trustData.financial_advisor_email} onChange={(e) => setTrustData({ ...trustData, financial_advisor_email: e.target.value })} className="input-trust" placeholder="Email" />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Successor Instructions */}
                <div className="p-4 border border-navy/10 bg-navy/5">
                  <div className="flex items-start gap-3 mb-4">
                    <FileText className="w-5 h-5 text-navy mt-0.5" />
                    <div>
                      <h3 className="font-medium text-navy">Successor Instructions</h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        A letter of guidance and document location for your successor trustee.
                      </p>
                    </div>
                  </div>

                  <div data-section="successor-instructions" className="space-y-3">
                    <div>
                      <Label className="label-trust">Letter of Guidance for Successor Trustee</Label>
                      <textarea
                        value={trustData.successor_instructions}
                        onChange={(e) => setTrustData({ ...trustData, successor_instructions: e.target.value })}
                        className="mt-1 w-full rounded border border-input bg-background px-3 py-2 text-sm min-h-[120px]"
                        placeholder="Personal wishes, priorities, values, and guidance for your successor trustee. This is your voice to them."
                      />
                      <p className="text-xs text-muted-foreground mt-1">This will be included in the Successor Trustee Packet</p>
                    </div>
                    <div>
                      <Label className="label-trust">Physical Document Location</Label>
                      <Input
                        type="text"
                        value={trustData.document_location}
                        onChange={(e) => setTrustData({ ...trustData, document_location: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Where are the original paper documents stored? (safe deposit box, filing cabinet, etc.)"
                      />
                    </div>
                  </div>
                </div>

                {/* Governance Settings — Spending Threshold */}
                <div className="pt-4 border-t border-navy/10" data-section="governance">
                  <div className="flex items-center gap-2 mb-4">
                    <Shield className="w-4 h-4 text-navy" />
                    <Label className="label-trust">Governance Settings</Label>
                  </div>
                  <p className="text-xs text-muted-foreground mb-4">
                    Set a spending threshold. Transactions above this amount trigger an alert that can be resolved by linking meeting minutes documenting the decision.
                  </p>
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs text-muted-foreground">Spending Threshold Amount ($)</Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="e.g., 10000"
                          value={spendingThreshold.amount ?? ''}
                          onChange={(e) => updateSpendingThreshold('amount', e.target.value === '' ? '' : parseFloat(e.target.value))}
                          className="mt-1 input-trust"
                          data-testid="spending-threshold-amount"
                        />
                      </div>
                      <div className="flex items-center gap-2 mt-6">
                        <Switch
                          checked={spendingThreshold.requires_minutes ?? false}
                          onCheckedChange={(checked) => updateSpendingThreshold('requires_minutes', checked)}
                        />
                        <Label className="text-sm text-navy cursor-pointer" onClick={() => updateSpendingThreshold('requires_minutes', !spendingThreshold.requires_minutes)}>
                          Requires meeting minutes documentation
                        </Label>
                      </div>
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground mb-2 block">In-Scope Transaction Classifications</Label>
                      <div className="flex flex-wrap gap-2">
                        {CLASSIFICATIONS.map(cls => {
                          const selected = (spendingThreshold.scope_classifications || []).includes(cls);
                          return (
                            <button
                              key={cls}
                              type="button"
                              onClick={() => toggleScopeClassification(cls)}
                              className={`px-3 py-1.5 text-xs font-medium border transition-colors ${
                                selected
                                  ? 'bg-navy text-white border-navy'
                                  : 'bg-white text-navy border-navy/30 hover:border-navy'
                              }`}
                              data-testid={`scope-classification-${cls.replace(/\s+/g, '-').toLowerCase()}`}
                            >
                              {cls}
                            </button>
                          );
                        })}
                      </div>
                      <p className="text-xs text-muted-foreground mt-2">
                        Transactions classified as these types will be checked against the threshold.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-4 border-t border-navy/10">
                  <Button
                    onClick={handleUpdateTrust}
                    disabled={loading}
                    className="btn-primary"
                    data-testid="save-trust-settings"
                  >
                    <Save className="w-4 h-4 mr-2" />
                    {loading ? 'Saving...' : 'Save Changes'}
                  </Button>

                  <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                    <DialogTrigger asChild>
                      <Button variant="ghost" className="text-error hover:bg-error/10">
                        <Trash2 className="w-4 h-4 mr-2" />
                        Delete Trust
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle className="font-serif text-2xl text-navy">Delete Trust?</DialogTitle>
                      </DialogHeader>
                      <div className="py-4">
                        <p className="text-muted-foreground">
                          Are you sure you want to delete <strong>{selectedTrust.name}</strong>? 
                          This will permanently remove all minutes, distributions, and expenses associated with this trust.
                        </p>
                        <p className="mt-4 text-sm text-error font-medium">
                          This action cannot be undone.
                        </p>
                      </div>
                      <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
                          Cancel
                        </Button>
                        <Button 
                          onClick={handleDeleteTrust}
                          disabled={loading}
                          className="bg-error hover:bg-error/90 text-white"
                          data-testid="confirm-delete-trust"
                        >
                          {loading ? 'Deleting...' : 'Delete Trust'}
                        </Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
                </div>
              </div>
            </div>
          )}

          {/* Trust Document Intelligence — extracted provisions from uploaded trust document */}
          {selectedTrust && (
            <div className="mb-8">
              <TrustDocumentSummary trustId={selectedTrust.trust_id} />
            </div>
          )}

          {/* Billing Section */}
          <div className="card-trust mb-8">
            <div className="flex items-center gap-2 mb-4">
              <CreditCard className="w-5 h-5 text-navy" />
              <h2 className="font-serif text-xl text-navy">Billing & Subscription</h2>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              Manage your subscription, view billing history, and update payment methods.
            </p>
            <Button
              onClick={() => navigate('/settings/billing')}
              className="btn-secondary"
              data-testid="go-to-billing-btn"
            >
              Manage Subscription
              <ChevronRight className="w-4 h-4 ml-2" />
            </Button>
          </div>

          {/* Refer a Friend Section */}
          <div className="card-trust corner-mark mb-8" data-testid="referral-section">
            <div className="flex items-center gap-2 mb-4">
              <Gift className="w-5 h-5 text-gold" />
              <h2 className="font-serif text-xl text-navy">Refer a Friend</h2>
              <span className="bg-gold/20 text-gold px-2 py-0.5 text-xs font-medium rounded">
                50% OFF
              </span>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              Share TrustOffice with friends and you both save! When your friend subscribes, 
              you both get <span className="font-semibold text-navy">50% off</span> your next payment.
            </p>
            
            {referralLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-navy" />
              </div>
            ) : (
              <div className="space-y-4">
                {/* Referral Link */}
                <div className="bg-slate-50 dark:bg-slate-900 p-4 rounded">
                  <Label className="text-xs uppercase tracking-wider text-muted-foreground mb-2 block">
                    Your Referral Link
                  </Label>
                  <div className="flex items-center gap-2">
                    <Input
                      value={referralData?.referral_link || ''}
                      readOnly
                      className="font-mono text-sm bg-white dark:bg-slate-800"
                      data-testid="referral-link-input"
                    />
                    <Button
                      onClick={copyReferralLink}
                      variant="outline"
                      className="shrink-0"
                      data-testid="copy-referral-link-btn"
                    >
                      {linkCopied ? (
                        <Check className="w-4 h-4 text-success" />
                      ) : (
                        <Copy className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                  {referralData?.referral_code && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Or share your code: <span className="font-mono font-semibold text-navy">{referralData.referral_code}</span>
                    </p>
                  )}
                </div>
                
                {/* Referral Stats */}
                {referralStats && (
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center p-3 bg-blue-50 dark:bg-blue-950/30 rounded">
                      <p className="text-2xl font-bold text-navy">{referralStats.total_referred || 0}</p>
                      <p className="text-xs text-muted-foreground">Friends Invited</p>
                    </div>
                    <div className="text-center p-3 bg-success/10">
                      <p className="text-2xl font-bold text-success">{referralStats.successful_conversions || 0}</p>
                      <p className="text-xs text-muted-foreground">Subscribed</p>
                    </div>
                    <div className="text-center p-3 bg-gold/10 rounded">
                      <p className="text-2xl font-bold text-gold">{referralStats.rewards_earned || 0}</p>
                      <p className="text-xs text-muted-foreground">Rewards Earned</p>
                    </div>
                  </div>
                )}
                
                {/* Recent Referrals */}
                {referralStats?.referrals && referralStats.referrals.length > 0 && (
                  <div className="mt-4">
                    <h3 className="text-sm font-medium text-navy mb-2 flex items-center gap-2">
                      <Users className="w-4 h-4" />
                      Recent Referrals
                    </h3>
                    <div className="space-y-2">
                      {referralStats.referrals.slice(0, 5).map((ref, idx) => (
                        <div key={idx} className="flex items-center justify-between text-sm py-2 border-b border-slate-100 dark:border-slate-800 last:border-0">
                          <div>
                            <p className="font-medium">{ref.name}</p>
                            <p className="text-xs text-muted-foreground">{ref.email}</p>
                          </div>
                          <div className="text-right">
                            {ref.status === 'converted' ? (
                              <span className="inline-flex items-center gap-1 text-xs bg-success/10 text-success px-2 py-1">
                                <CheckCircle2 className="w-3 h-3" />
                                Subscribed
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-xs bg-warning/10 text-warning px-2 py-1">
                                <Clock className="w-3 h-3" />
                                Pending
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* How it works */}
                <div className="bg-navy/5 dark:bg-navy/20 p-4 rounded mt-4">
                  <h3 className="text-sm font-medium text-navy mb-2">How it works</h3>
                  <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside">
                    <li>Share your unique referral link with friends</li>
                    <li>They sign up and get 50% off their first payment</li>
                    <li>When they subscribe, you get 50% off your next payment</li>
                  </ol>
                </div>
              </div>
            )}
          </div>

          {/* Notification Preferences Section */}
          <div className="card-trust mb-8" data-testid="notification-preferences-section">
            <div className="flex items-center gap-2 mb-4">
              <Bell className="w-5 h-5 text-navy" />
              <h2 className="font-serif text-xl text-navy">Notification Preferences</h2>
            </div>
            <p className="text-sm text-muted-foreground mb-6">
              Control which email notifications you receive from TrustOffice.
            </p>
            
            <div className="space-y-4">
              {/* Document Notifications */}
              <div className="border-b border-navy/10 pb-4">
                <h3 className="text-sm font-medium text-navy mb-3 flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Document Notifications
                </h3>
                <div className="space-y-3 pl-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <Label className="text-sm font-normal">Minutes Created</Label>
                      <p className="text-xs text-muted-foreground">Receive an email when new minutes are recorded</p>
                    </div>
                    <Switch
                      checked={notificationPrefs.minutes_created}
                      onCheckedChange={(v) => handleNotificationChange('minutes_created', v)}
                      disabled={notificationLoading}
                      data-testid="notif-minutes-created"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <Label className="text-sm font-normal">Distribution Created</Label>
                      <p className="text-xs text-muted-foreground">Receive an email when a distribution is recorded</p>
                    </div>
                    <Switch
                      checked={notificationPrefs.distribution_created}
                      onCheckedChange={(v) => handleNotificationChange('distribution_created', v)}
                      disabled={notificationLoading}
                      data-testid="notif-distribution-created"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <Label className="text-sm font-normal">Distribution Approved</Label>
                      <p className="text-xs text-muted-foreground">Receive an email when a distribution is approved</p>
                    </div>
                    <Switch
                      checked={notificationPrefs.distribution_approved}
                      onCheckedChange={(v) => handleNotificationChange('distribution_approved', v)}
                      disabled={notificationLoading}
                      data-testid="notif-distribution-approved"
                    />
                  </div>
                </div>
              </div>

              {/* Task Notifications */}
              <div className="border-b border-navy/10 pb-4">
                <h3 className="text-sm font-medium text-navy mb-3 flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  Task Reminders
                </h3>
                <div className="space-y-3 pl-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <Label className="text-sm font-normal">Task Reminder</Label>
                      <p className="text-xs text-muted-foreground">One-time reminder when a task is due within 7 days</p>
                    </div>
                    <Switch
                      checked={notificationPrefs.task_reminders}
                      onCheckedChange={(v) => handleNotificationChange('task_reminders', v)}
                      disabled={notificationLoading}
                      data-testid="notif-task-reminders"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <Label className="text-sm font-normal">Overdue Task Alert</Label>
                      <p className="text-xs text-muted-foreground">One-time notification when a task becomes past due</p>
                    </div>
                    <Switch
                      checked={notificationPrefs.task_overdue}
                      onCheckedChange={(v) => handleNotificationChange('task_overdue', v)}
                      disabled={notificationLoading}
                      data-testid="notif-task-overdue"
                    />
                  </div>
                </div>
              </div>

              {/* Account Notifications */}
              <div>
                <h3 className="text-sm font-medium text-navy mb-3 flex items-center gap-2">
                  <Mail className="w-4 h-4" />
                  Account & Subscription
                </h3>
                <div className="space-y-3 pl-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <Label className="text-sm font-normal">Subscription Updates</Label>
                      <p className="text-xs text-muted-foreground">Payment confirmations, renewal notices, and billing alerts</p>
                    </div>
                    <Switch
                      checked={notificationPrefs.subscription_updates}
                      onCheckedChange={(v) => handleNotificationChange('subscription_updates', v)}
                      disabled={notificationLoading}
                      data-testid="notif-subscription-updates"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <Label className="text-sm font-normal">Weekly Digest</Label>
                      <p className="text-xs text-muted-foreground">A weekly summary of trust activity and upcoming tasks</p>
                    </div>
                    <Switch
                      checked={notificationPrefs.weekly_digest}
                      onCheckedChange={(v) => handleNotificationChange('weekly_digest', v)}
                      disabled={notificationLoading}
                      data-testid="notif-weekly-digest"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Export Data Section */}
          <div className="card-trust mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Download className="w-5 h-5 text-navy" />
              <h2 className="font-serif text-xl text-navy">Export Data</h2>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              Download your data as CSV files for backup or reporting purposes.
              {selectedTrust && <span className="text-navy font-medium"> Exporting for: {selectedTrust.name}</span>}
            </p>
            
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Button
                onClick={() => handleExport('minutes')}
                variant="outline"
                className="flex items-center justify-center gap-2"
                disabled={exportLoading === 'minutes'}
                data-testid="export-minutes-btn"
              >
                {exportLoading === 'minutes' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <FileText className="w-4 h-4" />
                )}
                Minutes
              </Button>
              
              <Button
                onClick={() => handleExport('distributions')}
                variant="outline"
                className="flex items-center justify-center gap-2"
                disabled={exportLoading === 'distributions'}
                data-testid="export-distributions-btn"
              >
                {exportLoading === 'distributions' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <FileText className="w-4 h-4" />
                )}
                Distributions
              </Button>
              
              <Button
                onClick={() => handleExport('compensation')}
                variant="outline"
                className="flex items-center justify-center gap-2"
                disabled={exportLoading === 'compensation'}
                data-testid="export-compensation-btn"
              >
                {exportLoading === 'compensation' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <FileText className="w-4 h-4" />
                )}
                Compensation
              </Button>
              
              <Button
                onClick={() => handleExport('tasks')}
                variant="outline"
                className="flex items-center justify-center gap-2"
                disabled={exportLoading === 'tasks'}
                data-testid="export-tasks-btn"
              >
                {exportLoading === 'tasks' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <FileText className="w-4 h-4" />
                )}
                Tasks
              </Button>
              
              <Button
                onClick={() => handleExport('expenses')}
                variant="outline"
                className="flex items-center justify-center gap-2"
                disabled={exportLoading === 'expenses'}
                data-testid="export-expenses-btn"
              >
                {exportLoading === 'expenses' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <FileText className="w-4 h-4" />
                )}
                Expenses
              </Button>
            </div>
          </div>

          {/* PDF Settings Section - Paid Members Only */}
          <div className="card-trust mb-8" data-testid="pdf-settings-section">
            <div className="flex items-center gap-2 mb-4">
              <FileText className="w-5 h-5 text-navy" />
              <h2 className="font-serif text-xl text-navy">PDF Settings</h2>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              Customize how your exported PDF documents appear.
            </p>
            
            <div className="p-4 border border-navy/10 bg-navy/5">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-medium text-navy">Hide TrustOffice Watermark</h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    Remove the "Generated by TrustOffice" footer from all exported PDFs.
                    <span className="block text-xs text-gold mt-1">Available for paid subscribers only</span>
                  </p>
                </div>
                <Switch
                  checked={userPrefs.hide_watermark}
                  onCheckedChange={handleWatermarkToggle}
                  disabled={userPrefsLoading}
                  data-testid="hide-watermark-toggle"
                />
              </div>
            </div>
          </div>

          {/* Demo Data Management Section */}
          <div className="card-trust mb-8" data-testid="demo-data-section">
            <div className="flex items-center gap-2 mb-4">
              <Database className="w-5 h-5 text-navy" />
              <h2 className="font-serif text-xl text-navy">Demo Data Management</h2>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              Load sample data to explore TrustOffice features. Demo data can be removed at any time without affecting your own trusts and records.
            </p>
            
            {demoStatus && (
              <div className="mb-4 p-4 bg-navy/5 border border-navy/10">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">Current Data in Your Account</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                  <div>
                    <p className="font-mono text-lg text-navy">{demoStatus.counts?.trusts || 0}</p>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Trusts</p>
                    {demoStatus.demo_counts?.trusts > 0 && (
                      <p className="font-mono text-[9px] text-gold">({demoStatus.demo_counts.trusts} demo)</p>
                    )}
                  </div>
                  <div>
                    <p className="font-mono text-lg text-navy">{demoStatus.counts?.minutes_records || 0}</p>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Minutes</p>
                    {demoStatus.demo_counts?.minutes_records > 0 && (
                      <p className="font-mono text-[9px] text-gold">({demoStatus.demo_counts.minutes_records} demo)</p>
                    )}
                  </div>
                  <div>
                    <p className="font-mono text-lg text-navy">{demoStatus.counts?.schedule_a_items || 0}</p>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Assets</p>
                    {demoStatus.demo_counts?.schedule_a_items > 0 && (
                      <p className="font-mono text-[9px] text-gold">({demoStatus.demo_counts.schedule_a_items} demo)</p>
                    )}
                  </div>
                  <div>
                    <p className="font-mono text-lg text-navy">{demoStatus.total_records || 0}</p>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Total Records</p>
                    {demoStatus.total_demo_records > 0 && (
                      <p className="font-mono text-[9px] text-gold">({demoStatus.total_demo_records} demo)</p>
                    )}
                  </div>
                </div>
              </div>
            )}
            
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={handleSeedDemoData}
                disabled={demoLoading || (demoStatus?.has_demo_data)}
                className="btn-primary"
                data-testid="seed-demo-btn"
              >
                {demoLoading ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4 mr-2" />
                )}
                Load Demo Data
              </Button>
              
              <Dialog open={deleteDemoDialogOpen} onOpenChange={setDeleteDemoDialogOpen}>
                <DialogTrigger asChild>
                  <Button
                    variant="outline"
                    disabled={demoLoading || !demoStatus?.has_demo_data}
                    className="border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
                    data-testid="delete-data-btn"
                  >
                    <Trash2 className="w-4 h-4 mr-2" />
                    Remove Demo Data
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle className="font-serif text-xl text-red-600">Remove Demo Data?</DialogTitle>
                    <DialogDescription>
                      This will remove all sample/demo data from your account. Your own trusts and records will NOT be affected.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="py-4">
                    <p className="text-sm text-muted-foreground mb-3">
                      The following demo/sample items will be removed:
                    </p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      <li>Demo trusts and entities</li>
                      <li>Demo Schedule A assets</li>
                      <li>Demo meeting minutes</li>
                      <li>Demo distribution records</li>
                      <li>Demo benevolence records</li>
                      <li>Demo compensation plans and payments</li>
                      <li>Demo governance tasks</li>
                      <li>Demo trust unit certificates</li>
                    </ul>
                    <div className="mt-4 p-3 bg-success/5 border border-success/20">
                      <p className="text-sm font-medium text-success">
                        Your custom data is safe!
                      </p>
                      <p className="mt-1 text-xs text-success/80">
                        Any trusts, minutes, or records you created yourself will NOT be deleted.
                      </p>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setDeleteDemoDialogOpen(false)}>
                      Cancel
                    </Button>
                    <Button 
                      onClick={handleDeleteDemoData}
                      disabled={demoLoading}
                      className="bg-red-600 hover:bg-red-700 text-white"
                      data-testid="confirm-delete-data-btn"
                    >
                      {demoLoading ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4 mr-2" />
                      )}
                      Remove Demo Data
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
              
              <Button
                variant="ghost"
                onClick={loadDemoStatus}
                disabled={demoLoading}
                className="text-muted-foreground"
              >
                <RefreshCw className={`w-4 h-4 mr-2 ${demoLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </div>
            
            {!demoStatus?.has_demo_data && (
              <p className="mt-4 text-xs text-muted-foreground">
                Demo data includes 2 trusts, entity hierarchy, Schedule A with active & disposed assets, 
                minutes of various types (quarterly, annual, disposition, benevolence), distributions, 
                benevolence records, compensation plans, trust certificates, and governance tasks.
              </p>
            )}
          </div>

          {/* Support & Feedback Section */}
          <div className="card-trust mb-8" data-testid="support-section">
            <div className="flex items-center gap-2 mb-4">
              <MessageSquare className="w-5 h-5 text-navy" />
              <h2 className="font-serif text-xl text-navy">Support & Feedback</h2>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              Have questions, need help, or want to share feedback? Our support team is here to assist you.
            </p>
            <Button
              onClick={() => window.open('https://trustoffice.app/support', '_blank')}
              className="btn-secondary"
              data-testid="go-to-support-btn"
            >
              <MessageSquare className="w-4 h-4 mr-2" />
              Contact Support
              <ExternalLink className="w-4 h-4 ml-2" />
            </Button>
          </div>

          {/* Privacy & Security Section */}
          <div className="card-trust mb-8" data-testid="privacy-security-section">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-5 h-5 text-navy" />
              <h2 className="font-serif text-xl text-navy">Privacy & Security</h2>
            </div>
            <p className="text-sm text-muted-foreground mb-6">
              Manage your account security and data privacy preferences.
            </p>

            <div className="space-y-4">
              {/* Admin Access Lock */}
              <div className="flex items-center justify-between p-4 border border-navy/10">
                <div className="flex items-start gap-3">
                  {userPrefs.admin_access_locked ? (
                    <Lock className="w-5 h-5 text-success mt-0.5 flex-shrink-0" />
                  ) : (
                    <Unlock className="w-5 h-5 text-muted-foreground mt-0.5 flex-shrink-0" />
                  )}
                  <div>
                    <p className="font-medium text-navy">Admin Access Lock</p>
                    <p className="text-sm text-muted-foreground">
                      When enabled, TrustOffice administrators cannot access your account or view your trust data. You can still contact support for help.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={userPrefs.admin_access_locked}
                  disabled={userPrefsLoading}
                  onClick={handleAdminAccessLockToggle}
                  data-testid="admin-access-lock-toggle"
                  className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-navy focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
                    userPrefs.admin_access_locked ? 'bg-success' : 'bg-navy/10'
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                      userPrefs.admin_access_locked ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              {/* Two-factor info */}
              <div className="flex items-center justify-between p-4 border border-navy/10">
                <div>
                  <p className="font-medium text-navy">Two-Factor Authentication</p>
                  <p className="text-sm text-muted-foreground">
                    Add an extra layer of security to your account with TOTP authentication.
                  </p>
                </div>
                <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Not Enabled
                </div>
              </div>

              {/* Session management */}
              <div className="flex items-center justify-between p-4 border border-navy/10">
                <div>
                  <p className="font-medium text-navy">Active Sessions</p>
                  <p className="text-sm text-muted-foreground">
                    Your authentication session is managed securely via HTTP-only cookies and JWT tokens.
                  </p>
                </div>
                <div className="font-mono text-xs uppercase tracking-widest text-success">
                  Active
                </div>
              </div>

              {/* Data retention */}
              <div className="flex items-center justify-between p-4 border border-navy/10">
                <div>
                  <p className="font-medium text-navy">Data Retention</p>
                  <p className="text-sm text-muted-foreground">
                    Your trust data is retained for 90 days after subscription cancellation. 
                    Delete your trust at any time to remove all associated records immediately.
                  </p>
                </div>
              </div>

              {/* Privacy policy link */}
              <div className="flex items-center justify-between p-4 border border-navy/10">
                <div>
                  <p className="font-medium text-navy">Privacy Policy</p>
                  <p className="text-sm text-muted-foreground">
                    Review how TrustOffice handles your data and privacy.
                  </p>
                </div>
                <Button
                  onClick={() => window.open('https://trustoffice.app/privacy', '_blank')}
                  variant="ghost"
                  className="text-navy hover:text-navy/70"
                  data-testid="privacy-policy-link"
                >
                  <ExternalLink className="w-4 h-4 mr-2" />
                  View
                </Button>
              </div>

              {/* Terms of Service link */}
              <div className="flex items-center justify-between p-4 border border-navy/10">
                <div>
                  <p className="font-medium text-navy">Terms of Service</p>
                  <p className="text-sm text-muted-foreground">
                    Review the terms and conditions for using TrustOffice.
                  </p>
                </div>
                <Button
                  onClick={() => window.open('https://trustoffice.app/terms', '_blank')}
                  variant="ghost"
                  className="text-navy hover:text-navy/70"
                  data-testid="terms-of-service-link"
                >
                  <ExternalLink className="w-4 h-4 mr-2" />
                  View
                </Button>
              </div>
            </div>
          </div>

          {/* Trust ID for reference */}
          {selectedTrust && (
            <div className="mt-8 p-4 bg-navy/5 border border-navy/10">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Trust ID: {selectedTrust.trust_id}
              </p>
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
