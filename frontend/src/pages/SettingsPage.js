import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
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
  Sparkles
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
  }, []);

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

  return (
    <div className="main-layout" data-testid="settings-page">
      <Sidebar />
      <main className="main-content">
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
                      <Label className="text-sm font-normal">Task Reminders</Label>
                      <p className="text-xs text-muted-foreground">Receive reminders for upcoming governance tasks</p>
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
                      <Label className="text-sm font-normal">Overdue Task Alerts</Label>
                      <p className="text-xs text-muted-foreground">Receive alerts when tasks become overdue</p>
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
    </div>
  );
}
