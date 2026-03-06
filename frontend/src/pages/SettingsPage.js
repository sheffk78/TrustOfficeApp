import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { TrialBanner } from '@/components/TrialBanner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
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
  Check
} from 'lucide-react';
import { Switch } from '@/components/ui/switch';

const API_BASE = process.env.REACT_APP_BACKEND_URL;

export default function SettingsPage() {
  const navigate = useNavigate();
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
  const [userPrefs, setUserPrefs] = useState({ hide_watermark: false });
  const [userPrefsLoading, setUserPrefsLoading] = useState(false);
  
  // Demo data management state
  const [demoStatus, setDemoStatus] = useState(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [deleteDemoDialogOpen, setDeleteDemoDialogOpen] = useState(false);
  
  // Create trust modal state
  const [createTrustOpen, setCreateTrustOpen] = useState(false);
  const [newTrustData, setNewTrustData] = useState({
    name: '',
    trust_type: 'family',
    jurisdiction: '',
    role: 'Trustee',
    start_date: '',
    trustees: '',
    authority_clause: ''
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
    tax_status: selectedTrust?.tax_status || 'private'
  });

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
      toast.error('Failed to copy link');
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
        const error = await response.json();
        toast.error(error.detail || 'Failed to seed demo data');
      }
    } catch (error) {
      toast.error('Failed to seed demo data');
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
        const error = await response.json();
        toast.error(error.detail || 'Failed to delete data');
      }
    } catch (error) {
      toast.error('Failed to delete data');
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
        toast.error(error.detail || 'Failed to update preference');
      }
    } catch (error) {
      toast.error('Failed to update preference');
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
        // Revert on error
        setNotificationPrefs({ ...notificationPrefs });
        toast.error('Failed to update preference');
      }
    } catch (error) {
      setNotificationPrefs({ ...notificationPrefs });
      toast.error('Failed to update preference');
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
        const error = await response.json();
        toast.error(error.detail || 'Failed to update profile');
      }
    } catch (error) {
      toast.error('Failed to update profile');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (type) => {
    setExportLoading(type);
    try {
      const token = localStorage.getItem('token') || document.cookie.split('; ').find(row => row.startsWith('session_token='))?.split('=')[1];
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
      toast.error('Export failed');
    } finally {
      setExportLoading(null);
    }
  };

  const handleUpdateTrust = async () => {
    if (!selectedTrust) {
      toast.error('No trust selected');
      return;
    }

    setLoading(true);
    try {
      const response = await fetchWithAuth(`/trusts/${selectedTrust.trust_id}`, {
        method: 'PUT',
        body: JSON.stringify(trustData)
      });

      if (!response.ok) {
        throw new Error('Failed to update trust');
      }

      const updatedTrust = await response.json();
      setSelectedTrust(updatedTrust);
      await loadTrusts();
      toast.success('Trust updated');
    } catch (error) {
      toast.error(error.message);
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
      toast.error(error.message);
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
          authority_clause: newTrustData.authority_clause.trim() || null
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create trust');
      }

      const createdTrust = await response.json();
      
      // Auto-create the trust as an entity in the Entities section
      try {
        await fetchWithAuth('/entities', {
          method: 'POST',
          body: JSON.stringify({
            trust_id: createdTrust.trust_id,
            name: newTrustData.name.trim(),
            entity_type: 'trust',
            jurisdiction: newTrustData.jurisdiction.trim(),
            formation_date: newTrustData.start_date || new Date().toISOString().split('T')[0],
            status: 'active',
            ein: '',
            notes: newTrustData.trustees ? `Trustees: ${newTrustData.trustees}` : ''
          })
        });
      } catch (entityError) {
        console.log('Entity creation optional, continuing...');
      }
      
      toast.success('Trust created successfully!');
      setCreateTrustOpen(false);
      setNewTrustData({ name: '', trust_type: 'family', jurisdiction: '', role: 'Trustee', start_date: '', trustees: '', authority_clause: '' });
      await loadTrusts();
      setSelectedTrust(createdTrust);
    } catch (error) {
      toast.error(error.message);
    } finally {
      setCreateTrustLoading(false);
    }
  };

  return (
    <div className="main-layout" data-testid="settings-page">
      <Sidebar />
      <main className="main-content">
        <TrialBanner location="settings" />
        <div className="page-container max-w-3xl">
          {/* Page Header */}
          <div className="page-header">
            <h1 className="page-title">Settings</h1>
            <p className="page-subtitle">
              Manage your account and trust settings
            </p>
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
                <div className="bg-slate-50 dark:bg-slate-900 p-4 rounded-lg">
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
                        <Check className="w-4 h-4 text-green-600" />
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
                    <div className="text-center p-3 bg-blue-50 dark:bg-blue-950/30 rounded-lg">
                      <p className="text-2xl font-bold text-navy">{referralStats.total_referred || 0}</p>
                      <p className="text-xs text-muted-foreground">Friends Invited</p>
                    </div>
                    <div className="text-center p-3 bg-green-50 dark:bg-green-950/30 rounded-lg">
                      <p className="text-2xl font-bold text-green-700 dark:text-green-400">{referralStats.successful_conversions || 0}</p>
                      <p className="text-xs text-muted-foreground">Subscribed</p>
                    </div>
                    <div className="text-center p-3 bg-gold/10 rounded-lg">
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
                              <span className="inline-flex items-center gap-1 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 px-2 py-1 rounded">
                                <CheckCircle2 className="w-3 h-3" />
                                Subscribed
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 px-2 py-1 rounded">
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
                <div className="bg-navy/5 dark:bg-navy/20 p-4 rounded-lg mt-4">
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
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
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
                    <div className="mt-4 p-3 bg-green-50 border border-green-200">
                      <p className="text-sm font-medium text-green-700">
                        Your custom data is safe!
                      </p>
                      <p className="mt-1 text-xs text-green-600">
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
                        <SelectItem value="family">Family Trust</SelectItem>
                        <SelectItem value="charitable">Charitable Trust</SelectItem>
                        <SelectItem value="business">Business Trust</SelectItem>
                        <SelectItem value="ecclesiastical">Ecclesiastical Trust</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="label-trust">Jurisdiction *</Label>
                    <Input
                      value={newTrustData.jurisdiction}
                      onChange={(e) => setNewTrustData({ ...newTrustData, jurisdiction: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="e.g., Delaware, Nevada, Wyoming"
                      data-testid="new-trust-jurisdiction"
                    />
                  </div>
                  <div>
                    <Label className="label-trust">Your Role</Label>
                    <Select 
                      value={newTrustData.role} 
                      onValueChange={(v) => setNewTrustData({ ...newTrustData, role: v })}
                    >
                      <SelectTrigger className="mt-1 input-trust">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Trustee">Trustee</SelectItem>
                        <SelectItem value="Co-Trustee">Co-Trustee</SelectItem>
                        <SelectItem value="Successor Trustee">Successor Trustee</SelectItem>
                        <SelectItem value="Trust Protector">Trust Protector</SelectItem>
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

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="label-trust">Your Role</Label>
                    <Select 
                      value={trustData.role} 
                      onValueChange={(value) => setTrustData({ ...trustData, role: value })}
                    >
                      <SelectTrigger className="mt-1 input-trust" data-testid="settings-role-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Trustee">Trustee</SelectItem>
                        <SelectItem value="Co-Trustee">Co-Trustee</SelectItem>
                        <SelectItem value="Successor Trustee">Successor Trustee</SelectItem>
                        <SelectItem value="Trust Protector">Trust Protector</SelectItem>
                        <SelectItem value="Beneficiary">Beneficiary</SelectItem>
                      </SelectContent>
                    </Select>
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

          {/* Notification Settings */}
          <div className="card-trust">
            <div className="flex items-center gap-2 mb-6">
              <Bell className="w-5 h-5 text-navy" />
              <h2 className="font-serif text-xl text-navy">Notifications</h2>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 border border-navy/10">
                <div>
                  <p className="font-medium text-navy">Review Reminders</p>
                  <p className="text-sm text-muted-foreground">
                    Get reminded when it's time for your {selectedTrust?.review_cadence || 'quarterly'} review
                  </p>
                </div>
                <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Coming Soon
                </div>
              </div>

              <div className="flex items-center justify-between p-4 border border-navy/10">
                <div>
                  <p className="font-medium text-navy">Pending Item Alerts</p>
                  <p className="text-sm text-muted-foreground">
                    Get notified when items are pending review for too long
                  </p>
                </div>
                <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Coming Soon
                </div>
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
