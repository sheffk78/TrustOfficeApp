import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
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
  Loader2
} from 'lucide-react';

const API_BASE = process.env.REACT_APP_BACKEND_URL;

export default function SettingsPage() {
  const navigate = useNavigate();
  const { user, selectedTrust, setSelectedTrust, loadTrusts } = useAuth();
  const [loading, setLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  
  const [trustData, setTrustData] = useState({
    name: selectedTrust?.name || '',
    role: selectedTrust?.role || 'Trustee',
    review_cadence: selectedTrust?.review_cadence || 'quarterly',
    description: selectedTrust?.description || ''
  });

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
              <div>
                <p className="font-medium text-lg text-navy">{user?.name}</p>
                <p className="font-mono text-sm text-muted-foreground">{user?.email}</p>
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-2">
                  User ID: {user?.user_id}
                </p>
              </div>
            </div>
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
