import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { PDFPreviewModal } from '@/components/PDFPreviewModal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
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
  ArrowRightLeft,
  FileCheck,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Printer,
  RefreshCw,
  Save,
  Eye
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
  const [saving, setSaving] = useState(false);
  const [filterStatus, setFilterStatus] = useState('active');
  
  // Dialog states
  const [certificateDialogOpen, setCertificateDialogOpen] = useState(false);
  const [transferDialogOpen, setTransferDialogOpen] = useState(false);
  const [pdfPreviewOpen, setPdfPreviewOpen] = useState(false);
  const [pdfData, setPdfData] = useState(null);
  const [editingCertificate, setEditingCertificate] = useState(null);
  const [reissuingCertificate, setReissuingCertificate] = useState(null);
  
  // Settings form (editable in top card)
  const [settingsForm, setSettingsForm] = useState({
    total_authorized_units: 100,
    unit_label: 'Unit',
    allow_fractional: false
  });
  const [settingsDirty, setSettingsDirty] = useState(false);
  
  // Certificate form
  const [certificateForm, setCertificateForm] = useState({
    holder_name: '',
    holder_identifier: '',
    units: '',
    issue_date: new Date().toISOString().split('T')[0],
    notes: '',
    status: 'active'
  });
  
  // Transfer form
  const [transferForm, setTransferForm] = useState({
    from_holder: '',
    to_holder: '',
    units: '',
    reason: ''
  });

  const loadSummary = useCallback(async () => {
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
        setSettingsDirty(false);
      }
    } catch (error) {
      console.error('Failed to load units summary:', error);
      toast.error('Failed to load certificate units');
    } finally {
      setLoading(false);
    }
  }, [selectedTrust]);

  useEffect(() => {
    if (selectedTrust) {
      loadSummary();
    }
  }, [selectedTrust, loadSummary]);

  const handleSettingsChange = (field, value) => {
    setSettingsForm(prev => ({ ...prev, [field]: value }));
    setSettingsDirty(true);
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      const response = await fetchWithAuth(`/trust-units/settings?trust_id=${selectedTrust.trust_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsForm)
      });
      
      if (response.ok) {
        toast.success('Settings saved');
        setSettingsDirty(false);
        loadSummary();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to save settings');
      }
    } catch (error) {
      toast.error('Failed to save settings');
    } finally {
      setSaving(false);
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
            notes: certificateForm.notes,
            status: certificateForm.status
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
    if (!confirm(`Cancel certificate ${certificate.certificate_number}? This cannot be undone.`)) return;
    
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

  const handleReissue = (certificate) => {
    setReissuingCertificate(certificate);
    setCertificateForm({
      holder_name: certificate.holder_name,
      holder_identifier: certificate.holder_identifier || '',
      units: certificate.units.toString(),
      issue_date: new Date().toISOString().split('T')[0],
      notes: `Reissued from ${certificate.certificate_number}`,
      status: 'active'
    });
    setCertificateDialogOpen(true);
  };

  const handleReissueCertificate = async (e) => {
    e.preventDefault();
    
    // First cancel the old certificate
    try {
      await fetchWithAuth(`/trust-units/certificates/${reissuingCertificate.certificate_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'replaced' })
      });
    } catch (error) {
      toast.error('Failed to mark old certificate as replaced');
      return;
    }
    
    // Then create the new one
    const payload = {
      trust_id: selectedTrust.trust_id,
      holder_name: certificateForm.holder_name,
      holder_identifier: certificateForm.holder_identifier || null,
      units: parseFloat(certificateForm.units),
      issue_date: certificateForm.issue_date,
      notes: certificateForm.notes
    };

    try {
      const response = await fetchWithAuth('/trust-units/certificates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        toast.success('Certificate reissued');
        setCertificateDialogOpen(false);
        resetCertificateForm();
        loadSummary();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to reissue certificate');
      }
    } catch (error) {
      toast.error('Failed to reissue certificate');
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
        toast.success('Transfer recorded');
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

  const handlePrintCertificate = async (certificate) => {
    try {
      const response = await fetchWithAuth(`/trust-units/certificates/${certificate.certificate_id}/pdf`);
      if (response.ok) {
        const data = await response.json();
        setPdfData(data);
        setPdfPreviewOpen(true);
      } else {
        toast.error('Failed to generate PDF');
      }
    } catch (error) {
      toast.error('Failed to generate PDF');
    }
  };

  const handleDownloadPdf = () => {
    // Kept for backwards compatibility if needed elsewhere, but PDFPreviewModal handles this
    if (!pdfData) return;
    const link = document.createElement('a');
    link.href = `data:application/pdf;base64,${pdfData.pdf_base64}`;
    link.download = pdfData.filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success('PDF downloaded');
  };

  const handleEditCertificate = (cert) => {
    setEditingCertificate(cert);
    setReissuingCertificate(null);
    setCertificateForm({
      holder_name: cert.holder_name,
      holder_identifier: cert.holder_identifier || '',
      units: cert.units.toString(),
      issue_date: cert.issue_date,
      notes: cert.notes || '',
      status: cert.status
    });
    setCertificateDialogOpen(true);
  };

  const resetCertificateForm = () => {
    setEditingCertificate(null);
    setReissuingCertificate(null);
    setCertificateForm({
      holder_name: '',
      holder_identifier: '',
      units: '',
      issue_date: new Date().toISOString().split('T')[0],
      notes: '',
      status: 'active'
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

  // Filter certificates based on filterStatus
  const displayedCertificates = summary?.certificates?.filter(c => 
    filterStatus === 'all' || c.status === filterStatus
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
          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
            <div>
              <h1 className="font-serif text-3xl lg:text-4xl text-navy dark:text-gold mb-1" data-testid="page-title">
                Trust Units
              </h1>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                {selectedTrust.name} • Beneficial Interest Tracking
              </p>
            </div>
          </div>

          {/* Trust Units Settings Card */}
          <div className="card-trust mb-6">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Settings2 className="w-4 h-4 text-navy dark:text-gold" />
                <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Trust Units Settings</h2>
              </div>
              {settingsDirty && (
                <Button 
                  size="sm" 
                  onClick={handleSaveSettings} 
                  disabled={saving}
                  className="btn-primary"
                  data-testid="save-settings-btn"
                >
                  <Save className="w-4 h-4 mr-2" />
                  {saving ? 'Saving...' : 'Save Changes'}
                </Button>
              )}
            </div>
            <div className="p-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Editable Settings */}
                <div>
                  <Label className="label-trust">Total Authorized Units</Label>
                  <Input
                    type="number"
                    min="1"
                    value={settingsForm.total_authorized_units}
                    onChange={(e) => handleSettingsChange('total_authorized_units', parseInt(e.target.value) || 100)}
                    className="mt-1"
                    data-testid="total-units-input"
                  />
                </div>
                <div>
                  <Label className="label-trust">Unit Label</Label>
                  <Input
                    value={settingsForm.unit_label}
                    onChange={(e) => handleSettingsChange('unit_label', e.target.value)}
                    placeholder="Certificate Unit"
                    className="mt-1"
                    data-testid="unit-label-input"
                  />
                </div>
                <div className="flex items-center justify-between md:pt-6">
                  <div>
                    <Label className="label-trust">Allow Fractional Units</Label>
                    <p className="text-xs text-muted-foreground">Enable decimals (e.g., 12.5)</p>
                  </div>
                  <Switch
                    checked={settingsForm.allow_fractional}
                    onCheckedChange={(checked) => handleSettingsChange('allow_fractional', checked)}
                    data-testid="fractional-switch"
                  />
                </div>
              </div>
              
              {/* Read-only Summary */}
              {summary && (
                <div className="mt-6 pt-6 border-t border-border">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                        <FileCheck className="w-5 h-5 text-green-700 dark:text-green-400" />
                      </div>
                      <div>
                        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Total Issued</p>
                        <p className="font-serif text-xl text-navy dark:text-foreground" data-testid="total-issued">
                          {summary.total_issued_units} units
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                        <PieChart className="w-5 h-5 text-blue-700 dark:text-blue-400" />
                      </div>
                      <div>
                        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Remaining</p>
                        <p className="font-serif text-xl text-navy dark:text-foreground" data-testid="remaining-units">
                          {summary.remaining_units} units
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                        <Users className="w-5 h-5 text-amber-700 dark:text-amber-400" />
                      </div>
                      <div>
                        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Active Certificates</p>
                        <p className="font-serif text-xl text-navy dark:text-foreground" data-testid="active-certs">
                          {summary.active_certificate_count}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Certificates Section */}
          <div className="card-trust overflow-hidden">
            <div className="p-4 border-b border-border flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="flex items-center gap-2">
                <Award className="w-4 h-4 text-navy dark:text-gold" />
                <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Certificates</h2>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {/* Filter */}
                <Select value={filterStatus} onValueChange={setFilterStatus}>
                  <SelectTrigger className="w-[140px]" data-testid="filter-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active Only</SelectItem>
                    <SelectItem value="all">All Certificates</SelectItem>
                  </SelectContent>
                </Select>
                
                {/* Transfer Button */}
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => setTransferDialogOpen(true)}
                  disabled={activeHolders.length === 0}
                  data-testid="transfer-btn"
                >
                  <ArrowRightLeft className="w-4 h-4 mr-2" />
                  Transfer
                </Button>
                
                {/* Issue Units Button */}
                <Button 
                  className="btn-primary" 
                  size="sm"
                  onClick={() => { resetCertificateForm(); setCertificateDialogOpen(true); }}
                  data-testid="issue-units-btn"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Issue Units
                </Button>
              </div>
            </div>
            
            {loading ? (
              <div className="p-8 text-center">
                <div className="w-8 h-8 border-2 border-navy dark:border-gold border-t-transparent animate-spin mx-auto mb-4"></div>
                <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading...</p>
              </div>
            ) : displayedCertificates.length === 0 ? (
              <div className="p-8 text-center">
                <Award className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
                <p className="text-muted-foreground">
                  {filterStatus === 'active' ? 'No active certificates' : 'No certificates issued yet'}
                </p>
                <p className="text-sm text-muted-foreground mt-1">Click "Issue Units" to create the first certificate</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full" data-testid="certificates-table">
                  <thead>
                    <tr className="border-b border-border bg-muted/30">
                      <th className="text-left p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Certificate #</th>
                      <th className="text-left p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Holder</th>
                      <th className="text-right p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Units</th>
                      <th className="text-right p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Percentage</th>
                      <th className="text-left p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Status</th>
                      <th className="text-left p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Issue Date</th>
                      <th className="text-right p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayedCertificates.map((cert) => {
                      const statusStyle = STATUS_STYLES[cert.status] || STATUS_STYLES.active;
                      const StatusIcon = statusStyle.icon;
                      
                      return (
                        <tr key={cert.certificate_id} className="border-b border-border hover:bg-muted/20" data-testid={`cert-row-${cert.certificate_id}`}>
                          <td className="p-3">
                            <span className="font-mono text-sm">{cert.certificate_number}</span>
                          </td>
                          <td className="p-3">
                            <div>
                              <p className="font-medium text-sm">{cert.holder_name}</p>
                              {cert.holder_identifier && (
                                <p className="text-xs text-muted-foreground font-mono">{cert.holder_identifier}</p>
                              )}
                            </div>
                          </td>
                          <td className="p-3 text-right font-mono text-sm">{cert.units}</td>
                          <td className="p-3 text-right">
                            <span className="font-mono text-sm">{cert.percentage.toFixed(2)}%</span>
                          </td>
                          <td className="p-3">
                            <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-mono uppercase ${statusStyle.bg} ${statusStyle.text}`}>
                              <StatusIcon className="w-3 h-3" />
                              {cert.status}
                            </span>
                          </td>
                          <td className="p-3 text-sm text-muted-foreground font-mono">{formatDate(cert.issue_date)}</td>
                          <td className="p-3">
                            <div className="flex items-center justify-end gap-1">
                              {/* Print */}
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handlePrintCertificate(cert)}
                                title="Print Certificate"
                                data-testid={`print-cert-${cert.certificate_id}`}
                              >
                                <Printer className="w-4 h-4" />
                              </Button>
                              
                              {cert.status === 'active' && (
                                <>
                                  {/* Edit */}
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleEditCertificate(cert)}
                                    title="Edit Certificate"
                                    data-testid={`edit-cert-${cert.certificate_id}`}
                                  >
                                    <Edit className="w-4 h-4" />
                                  </Button>
                                  
                                  {/* Reissue */}
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleReissue(cert)}
                                    title="Reissue Certificate"
                                    data-testid={`reissue-cert-${cert.certificate_id}`}
                                  >
                                    <RefreshCw className="w-4 h-4" />
                                  </Button>
                                  
                                  {/* Cancel */}
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleCancelCertificate(cert)}
                                    className="text-destructive hover:text-destructive"
                                    title="Cancel Certificate"
                                    data-testid={`cancel-cert-${cert.certificate_id}`}
                                  >
                                    <XCircle className="w-4 h-4" />
                                  </Button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Issue/Edit Certificate Dialog */}
      <Dialog open={certificateDialogOpen} onOpenChange={(open) => { setCertificateDialogOpen(open); if (!open) resetCertificateForm(); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-navy dark:text-gold">
              {reissuingCertificate ? 'Reissue Certificate' : editingCertificate ? 'Edit Certificate' : 'Issue New Certificate'}
            </DialogTitle>
            <DialogDescription>
              {summary && (
                <span className="font-mono text-xs">
                  {summary.remaining_units} of {summary.settings.total_authorized_units} units available
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={reissuingCertificate ? handleReissueCertificate : handleCreateCertificate} className="space-y-4 mt-4">
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
                step={summary?.settings?.allow_fractional ? "any" : "1"}
                min="0.01"
                value={certificateForm.units}
                onChange={(e) => setCertificateForm({ ...certificateForm, units: e.target.value })}
                placeholder={summary?.settings?.allow_fractional ? "25.5" : "25"}
                required
                className="mt-1"
                data-testid="units-input"
              />
              {/* Show available units and validation */}
              {summary && (
                <div className="mt-2 space-y-1">
                  {certificateForm.units && parseFloat(certificateForm.units) > 0 && (
                    <p className="text-xs text-muted-foreground font-mono">
                      = {((parseFloat(certificateForm.units) / summary.settings.total_authorized_units) * 100).toFixed(2)}% ownership
                    </p>
                  )}
                  {certificateForm.units && parseFloat(certificateForm.units) > summary.remaining_units && !editingCertificate && (
                    <p className="text-xs text-red-600 dark:text-red-400 font-medium flex items-center gap-1">
                      <AlertCircle className="w-3 h-3" />
                      Exceeds available units ({summary.remaining_units} remaining)
                    </p>
                  )}
                </div>
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
            
            {editingCertificate && !reissuingCertificate && (
              <div>
                <Label className="label-trust">Status</Label>
                <Select 
                  value={certificateForm.status} 
                  onValueChange={(v) => setCertificateForm({ ...certificateForm, status: v })}
                >
                  <SelectTrigger className="mt-1" data-testid="status-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="cancelled">Cancelled</SelectItem>
                    <SelectItem value="replaced">Replaced</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            
            <div>
              <Label className="label-trust">Notes</Label>
              <Textarea
                value={certificateForm.notes}
                onChange={(e) => setCertificateForm({ ...certificateForm, notes: e.target.value })}
                placeholder="Additional details..."
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
                {reissuingCertificate ? 'Reissue Certificate' : editingCertificate ? 'Update Certificate' : 'Issue Certificate'}
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
              <Label className="label-trust">From Holder *</Label>
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
                step={summary?.settings?.allow_fractional ? "any" : "1"}
                min="0.01"
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

      {/* PDF Preview Modal */}
      <PDFPreviewModal
        open={pdfPreviewOpen}
        onOpenChange={setPdfPreviewOpen}
        pdfBase64={pdfData?.pdf_base64}
        title="Certificate Preview"
        filename={pdfData?.filename || 'certificate.pdf'}
      />
    </div>
  );
}
