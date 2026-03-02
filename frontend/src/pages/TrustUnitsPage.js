import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import { 
  Plus, 
  Award,
  Users,
  PieChart,
  Settings2,
  Edit,
  Trash2,
  ArrowRightLeft,
  FileCheck,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  XCircle
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const STATUS_STYLES = {
  active: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-800 dark:text-green-300', icon: CheckCircle2 },
  cancelled: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-800 dark:text-red-300', icon: XCircle },
  replaced: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-800 dark:text-amber-300', icon: AlertCircle }
};

export default function TrustUnitsPage() {
  const { selectedTrust } = useAuth();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showInactive, setShowInactive] = useState(false);
  
  // Dialog states
  const [settingsDialogOpen, setSettingsDialogOpen] = useState(false);
  const [certificateDialogOpen, setCertificateDialogOpen] = useState(false);
  const [transferDialogOpen, setTransferDialogOpen] = useState(false);
  const [editingCertificate, setEditingCertificate] = useState(null);
  
  // Form states
  const [settingsForm, setSettingsForm] = useState({
    total_authorized_units: 100,
    unit_label: 'Certificate Unit',
    allow_fractional: false
  });
  
  const [certificateForm, setCertificateForm] = useState({
    holder_name: '',
    holder_identifier: '',
    units: '',
    issue_date: new Date().toISOString().split('T')[0],
    notes: ''
  });
  
  const [transferForm, setTransferForm] = useState({
    from_holder: '',
    to_holder: '',
    units: '',
    reason: ''
  });

  useEffect(() => {
    if (selectedTrust) {
      loadSummary();
    }
  }, [selectedTrust]);

  const loadSummary = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/trust-units/summary?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        const data = await response.json();
        setSummary(data);
        setSettingsForm({
          total_authorized_units: data.settings.total_authorized_units,
          unit_label: data.settings.unit_label,
          allow_fractional: data.settings.allow_fractional
        });
      }
    } catch (error) {
      console.error('Failed to load units summary:', error);
      toast.error('Failed to load certificate units');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    try {
      const response = await fetchWithAuth(`/trust-units/settings?trust_id=${selectedTrust.trust_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsForm)
      });
      
      if (response.ok) {
        toast.success('Settings updated');
        setSettingsDialogOpen(false);
        loadSummary();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to update settings');
      }
    } catch (error) {
      toast.error('Failed to update settings');
    }
  };

  const handleCreateCertificate = async (e) => {
    e.preventDefault();
    
    const payload = {
      trust_id: selectedTrust.trust_id,
      holder_name: certificateForm.holder_name,
      holder_identifier: certificateForm.holder_identifier || null,
      units: parseFloat(certificateForm.units),
      issue_date: certificateForm.issue_date,
      notes: certificateForm.notes
    };

    try {
      let response;
      if (editingCertificate) {
        response = await fetchWithAuth(`/trust-units/certificates/${editingCertificate.certificate_id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            holder_name: certificateForm.holder_name,
            holder_identifier: certificateForm.holder_identifier || null,
            units: parseFloat(certificateForm.units),
            notes: certificateForm.notes
          })
        });
      } else {
        response = await fetchWithAuth('/trust-units/certificates', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }

      if (response.ok) {
        toast.success(editingCertificate ? 'Certificate updated' : 'Certificate issued');
        setCertificateDialogOpen(false);
        resetCertificateForm();
        loadSummary();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to save certificate');
      }
    } catch (error) {
      toast.error('Failed to save certificate');
    }
  };

  const handleCancelCertificate = async (certificate) => {
    if (!confirm(`Are you sure you want to cancel certificate ${certificate.certificate_number}?`)) return;
    
    try {
      const response = await fetchWithAuth(`/trust-units/certificates/${certificate.certificate_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'cancelled' })
      });
      
      if (response.ok) {
        toast.success('Certificate cancelled');
        loadSummary();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to cancel certificate');
      }
    } catch (error) {
      toast.error('Failed to cancel certificate');
    }
  };

  const handleTransfer = async (e) => {
    e.preventDefault();
    
    const payload = {
      trust_id: selectedTrust.trust_id,
      from_holder: transferForm.from_holder || null,
      to_holder: transferForm.to_holder,
      units: parseFloat(transferForm.units),
      reason: transferForm.reason
    };

    try {
      const response = await fetchWithAuth('/trust-units/transfers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        toast.success('Transfer recorded successfully');
        setTransferDialogOpen(false);
        resetTransferForm();
        loadSummary();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to record transfer');
      }
    } catch (error) {
      toast.error('Failed to record transfer');
    }
  };

  const handleEditCertificate = (cert) => {
    setEditingCertificate(cert);
    setCertificateForm({
      holder_name: cert.holder_name,
      holder_identifier: cert.holder_identifier || '',
      units: cert.units.toString(),
      issue_date: cert.issue_date,
      notes: cert.notes || ''
    });
    setCertificateDialogOpen(true);
  };

  const resetCertificateForm = () => {
    setEditingCertificate(null);
    setCertificateForm({
      holder_name: '',
      holder_identifier: '',
      units: '',
      issue_date: new Date().toISOString().split('T')[0],
      notes: ''
    });
  };

  const resetTransferForm = () => {
    setTransferForm({
      from_holder: '',
      to_holder: '',
      units: '',
      reason: ''
    });
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const date = parseISO(dateStr);
      if (isNaN(date.getTime())) {
        const plainDate = new Date(dateStr);
        if (isNaN(plainDate.getTime())) return dateStr;
        return format(plainDate, 'MMM d, yyyy');
      }
      return format(date, 'MMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  // Get unique active holders for transfer dropdown
  const activeHolders = summary?.certificates
    ?.filter(c => c.status === 'active')
    ?.map(c => c.holder_name)
    ?.filter((v, i, a) => a.indexOf(v) === i) || [];

  // Filter certificates based on showInactive toggle
  const displayedCertificates = summary?.certificates?.filter(c => 
    showInactive || c.status === 'active'
  ) || [];

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Select a trust to view Certificate Units</p>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <main className="lg:pl-64 pt-16 lg:pt-0">
        <div className="p-4 lg:p-8">
          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-8">
            <div>
              <h1 className="font-serif text-3xl lg:text-4xl text-navy dark:text-gold mb-2" data-testid="page-title">
                Certificate Units
              </h1>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                {selectedTrust.name} • Beneficial Interest Tracking
              </p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0">
              <Button 
                variant="outline" 
                onClick={() => setSettingsDialogOpen(true)}
                data-testid="settings-btn"
              >
                <Settings2 className="w-4 h-4 mr-2" />
                Settings
              </Button>
              <Button 
                variant="outline" 
                onClick={() => setTransferDialogOpen(true)}
                disabled={activeHolders.length === 0}
                data-testid="transfer-btn"
              >
                <ArrowRightLeft className="w-4 h-4 mr-2" />
                Transfer
              </Button>
              <Dialog open={certificateDialogOpen} onOpenChange={(open) => { setCertificateDialogOpen(open); if (!open) resetCertificateForm(); }}>
                <DialogTrigger asChild>
                  <Button className="btn-primary" data-testid="issue-certificate-btn">
                    <Plus className="w-4 h-4 mr-2" />
                    Issue Certificate
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-lg">
                  <DialogHeader>
                    <DialogTitle className="font-serif text-xl text-navy dark:text-gold">
                      {editingCertificate ? 'Edit Certificate' : 'Issue New Certificate'}
                    </DialogTitle>
                    <DialogDescription>
                      {summary && (
                        <span className="text-muted-foreground">
                          {summary.remaining_units} units available of {summary.settings.total_authorized_units} total
                        </span>
                      )}
                    </DialogDescription>
                  </DialogHeader>
                  <form onSubmit={handleCreateCertificate} className="space-y-4 mt-4">
                    <div>
                      <Label className="label-trust">Holder Name *</Label>
                      <Input
                        value={certificateForm.holder_name}
                        onChange={(e) => setCertificateForm({ ...certificateForm, holder_name: e.target.value })}
                        placeholder="John Smith"
                        required
                        className="mt-1"
                        data-testid="holder-name-input"
                      />
                    </div>
                    
                    <div>
                      <Label className="label-trust">Holder Identifier (Optional)</Label>
                      <Input
                        value={certificateForm.holder_identifier}
                        onChange={(e) => setCertificateForm({ ...certificateForm, holder_identifier: e.target.value })}
                        placeholder="SSN last 4, Trust EIN, etc."
                        className="mt-1"
                        data-testid="holder-id-input"
                      />
                    </div>
                    
                    <div>
                      <Label className="label-trust">Units *</Label>
                      <Input
                        type="number"
                        step={summary?.settings?.allow_fractional ? "0.0001" : "1"}
                        min="0.0001"
                        value={certificateForm.units}
                        onChange={(e) => setCertificateForm({ ...certificateForm, units: e.target.value })}
                        placeholder={summary?.settings?.allow_fractional ? "25.5" : "25"}
                        required
                        className="mt-1"
                        data-testid="units-input"
                      />
                      {summary && (
                        <p className="text-xs text-muted-foreground mt-1">
                          {certificateForm.units && parseFloat(certificateForm.units) > 0 ? (
                            <>= {((parseFloat(certificateForm.units) / summary.settings.total_authorized_units) * 100).toFixed(2)}% ownership</>
                          ) : (
                            <>Enter units to see percentage</>
                          )}
                        </p>
                      )}
                    </div>
                    
                    {!editingCertificate && (
                      <div>
                        <Label className="label-trust">Issue Date *</Label>
                        <Input
                          type="date"
                          value={certificateForm.issue_date}
                          onChange={(e) => setCertificateForm({ ...certificateForm, issue_date: e.target.value })}
                          required
                          className="mt-1"
                          data-testid="issue-date-input"
                        />
                      </div>
                    )}
                    
                    <div>
                      <Label className="label-trust">Notes</Label>
                      <Textarea
                        value={certificateForm.notes}
                        onChange={(e) => setCertificateForm({ ...certificateForm, notes: e.target.value })}
                        placeholder="Additional details about this certificate..."
                        rows={2}
                        className="mt-1"
                        data-testid="notes-input"
                      />
                    </div>
                    
                    <DialogFooter>
                      <Button type="button" variant="outline" onClick={() => { setCertificateDialogOpen(false); resetCertificateForm(); }}>
                        Cancel
                      </Button>
                      <Button type="submit" className="btn-primary" data-testid="submit-certificate-btn">
                        {editingCertificate ? 'Update Certificate' : 'Issue Certificate'}
                      </Button>
                    </DialogFooter>
                  </form>
                </DialogContent>
              </Dialog>
            </div>
          </div>

          {/* Summary Cards */}
          {summary && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <div className="card-trust p-4" data-testid="total-authorized-card">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-navy/10 dark:bg-gold/10 flex items-center justify-center">
                    <Award className="w-5 h-5 text-navy dark:text-gold" />
                  </div>
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Total Authorized</p>
                    <p className="font-serif text-2xl text-navy dark:text-foreground">{summary.settings.total_authorized_units}</p>
                  </div>
                </div>
              </div>
              
              <div className="card-trust p-4" data-testid="issued-units-card">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                    <FileCheck className="w-5 h-5 text-green-700 dark:text-green-400" />
                  </div>
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Issued Units</p>
                    <p className="font-serif text-2xl text-navy dark:text-foreground">{summary.total_issued_units}</p>
                  </div>
                </div>
              </div>
              
              <div className="card-trust p-4" data-testid="remaining-units-card">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                    <PieChart className="w-5 h-5 text-blue-700 dark:text-blue-400" />
                  </div>
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Remaining</p>
                    <p className="font-serif text-2xl text-navy dark:text-foreground">{summary.remaining_units}</p>
                  </div>
                </div>
              </div>
              
              <div className="card-trust p-4" data-testid="active-certs-card">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                    <Users className="w-5 h-5 text-amber-700 dark:text-amber-400" />
                  </div>
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Active Certificates</p>
                    <p className="font-serif text-2xl text-navy dark:text-foreground">{summary.active_certificate_count}</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Certificates Table */}
          <div className="card-trust overflow-hidden">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <h2 className="font-serif text-lg text-navy dark:text-foreground">Certificates</h2>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={showInactive}
                  onChange={(e) => setShowInactive(e.target.checked)}
                  className="rounded border-border"
                  data-testid="show-inactive-toggle"
                />
                <span className="text-muted-foreground">Show cancelled/replaced</span>
              </label>
            </div>
            
            {loading ? (
              <div className="p-8 text-center">
                <div className="w-8 h-8 border-2 border-navy dark:border-gold border-t-transparent animate-spin mx-auto mb-4"></div>
                <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading...</p>
              </div>
            ) : displayedCertificates.length === 0 ? (
              <div className="p-8 text-center">
                <Award className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
                <p className="text-muted-foreground">No certificates issued yet</p>
                <p className="text-sm text-muted-foreground mt-1">Click "Issue Certificate" to create the first one</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full" data-testid="certificates-table">
                  <thead>
                    <tr className="border-b border-border bg-muted/30">
                      <th className="text-left p-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Certificate #</th>
                      <th className="text-left p-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Holder</th>
                      <th className="text-right p-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Units</th>
                      <th className="text-right p-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Percentage</th>
                      <th className="text-left p-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Issue Date</th>
                      <th className="text-left p-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Status</th>
                      <th className="text-right p-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayedCertificates.map((cert) => {
                      const statusStyle = STATUS_STYLES[cert.status] || STATUS_STYLES.active;
                      const StatusIcon = statusStyle.icon;
                      
                      return (
                        <tr key={cert.certificate_id} className="border-b border-border hover:bg-muted/20" data-testid={`cert-row-${cert.certificate_id}`}>
                          <td className="p-4">
                            <span className="font-mono text-sm">{cert.certificate_number}</span>
                          </td>
                          <td className="p-4">
                            <div>
                              <p className="font-medium">{cert.holder_name}</p>
                              {cert.holder_identifier && (
                                <p className="text-xs text-muted-foreground">{cert.holder_identifier}</p>
                              )}
                            </div>
                          </td>
                          <td className="p-4 text-right font-mono">{cert.units}</td>
                          <td className="p-4 text-right">
                            <span className="font-mono text-sm">{cert.percentage.toFixed(2)}%</span>
                          </td>
                          <td className="p-4 text-sm text-muted-foreground">{formatDate(cert.issue_date)}</td>
                          <td className="p-4">
                            <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium ${statusStyle.bg} ${statusStyle.text}`}>
                              <StatusIcon className="w-3 h-3" />
                              {cert.status.charAt(0).toUpperCase() + cert.status.slice(1)}
                            </span>
                          </td>
                          <td className="p-4 text-right">
                            {cert.status === 'active' && (
                              <div className="flex items-center justify-end gap-2">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleEditCertificate(cert)}
                                  data-testid={`edit-cert-${cert.certificate_id}`}
                                >
                                  <Edit className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleCancelCertificate(cert)}
                                  className="text-destructive hover:text-destructive"
                                  data-testid={`cancel-cert-${cert.certificate_id}`}
                                >
                                  <XCircle className="w-4 h-4" />
                                </Button>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Settings Info */}
          {summary && (
            <div className="mt-8 card-trust p-4">
              <div className="flex items-center gap-2 mb-3">
                <Settings2 className="w-4 h-4 text-muted-foreground" />
                <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Unit Settings</h3>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Unit Label</p>
                  <p className="font-medium">{summary.settings.unit_label}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Total Authorized</p>
                  <p className="font-medium">{summary.settings.total_authorized_units}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Fractional Units</p>
                  <p className="font-medium">{summary.settings.allow_fractional ? 'Allowed' : 'Not Allowed'}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Settings Dialog */}
      <Dialog open={settingsDialogOpen} onOpenChange={setSettingsDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-navy dark:text-gold">Unit Settings</DialogTitle>
            <DialogDescription>
              Configure how certificate units are tracked for this trust
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSaveSettings} className="space-y-4 mt-4">
            <div>
              <Label className="label-trust">Total Authorized Units</Label>
              <Input
                type="number"
                min="1"
                value={settingsForm.total_authorized_units}
                onChange={(e) => setSettingsForm({ ...settingsForm, total_authorized_units: parseInt(e.target.value) || 100 })}
                className="mt-1"
                data-testid="total-units-setting"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Cannot be reduced below currently issued units ({summary?.total_issued_units || 0})
              </p>
            </div>
            
            <div>
              <Label className="label-trust">Unit Label</Label>
              <Input
                value={settingsForm.unit_label}
                onChange={(e) => setSettingsForm({ ...settingsForm, unit_label: e.target.value })}
                placeholder="Certificate Unit"
                className="mt-1"
                data-testid="unit-label-setting"
              />
            </div>
            
            <div className="flex items-center justify-between">
              <div>
                <Label className="label-trust">Allow Fractional Units</Label>
                <p className="text-xs text-muted-foreground">Enable decimals (e.g., 12.5 units)</p>
              </div>
              <Switch
                checked={settingsForm.allow_fractional}
                onCheckedChange={(checked) => setSettingsForm({ ...settingsForm, allow_fractional: checked })}
                data-testid="fractional-setting"
              />
            </div>
            
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setSettingsDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" className="btn-primary" data-testid="save-settings-btn">
                Save Settings
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Transfer Dialog */}
      <Dialog open={transferDialogOpen} onOpenChange={(open) => { setTransferDialogOpen(open); if (!open) resetTransferForm(); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-navy dark:text-gold">Transfer Units</DialogTitle>
            <DialogDescription>
              Transfer ownership units between certificate holders
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleTransfer} className="space-y-4 mt-4">
            <div>
              <Label className="label-trust">From Holder</Label>
              <Select 
                value={transferForm.from_holder} 
                onValueChange={(v) => setTransferForm({ ...transferForm, from_holder: v })}
              >
                <SelectTrigger className="mt-1" data-testid="from-holder-select">
                  <SelectValue placeholder="Select holder..." />
                </SelectTrigger>
                <SelectContent>
                  {activeHolders.map(holder => (
                    <SelectItem key={holder} value={holder}>{holder}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div>
              <Label className="label-trust">To Holder *</Label>
              <Input
                value={transferForm.to_holder}
                onChange={(e) => setTransferForm({ ...transferForm, to_holder: e.target.value })}
                placeholder="Recipient name"
                required
                className="mt-1"
                data-testid="to-holder-input"
              />
            </div>
            
            <div>
              <Label className="label-trust">Units to Transfer *</Label>
              <Input
                type="number"
                step={summary?.settings?.allow_fractional ? "0.0001" : "1"}
                min="0.0001"
                value={transferForm.units}
                onChange={(e) => setTransferForm({ ...transferForm, units: e.target.value })}
                required
                className="mt-1"
                data-testid="transfer-units-input"
              />
            </div>
            
            <div>
              <Label className="label-trust">Reason *</Label>
              <Textarea
                value={transferForm.reason}
                onChange={(e) => setTransferForm({ ...transferForm, reason: e.target.value })}
                placeholder="Reason for transfer..."
                required
                rows={2}
                className="mt-1"
                data-testid="transfer-reason-input"
              />
            </div>
            
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => { setTransferDialogOpen(false); resetTransferForm(); }}>
                Cancel
              </Button>
              <Button type="submit" className="btn-primary" data-testid="submit-transfer-btn">
                Record Transfer
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
