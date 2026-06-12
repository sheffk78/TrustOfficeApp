import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import PDFPreviewModal from '@/components/PDFPreviewModal';
import { format, parseISO } from 'date-fns';
import { 
  Users,
  PieChart,
  Award,
  Plus,
  MoreVertical,
  FileText,
  ArrowRightLeft,
  Pencil,
  XCircle,
  AlertCircle,
  TrendingUp,
  FileCheck,
  ChevronDown,
  ChevronUp,
  Settings,
  History,
  Info
} from 'lucide-react';

// ========== PIE CHART COMPONENT ==========
const OwnershipPieChart = ({ beneficiaries, totalAuthorized }) => {
  const colors = [
    '#010079', '#D5AD36', '#2563eb', '#16a34a', '#dc2626',
    '#9333ea', '#ea580c', '#0891b2', '#4f46e5', '#be185d',
  ];
  
  let gradientStops = [];
  let currentAngle = 0;
  
  beneficiaries.forEach((ben, index) => {
    const angle = (ben.percentage / 100) * 360;
    const color = colors[index % colors.length];
    gradientStops.push(`${color} ${currentAngle}deg ${currentAngle + angle}deg`);
    currentAngle += angle;
  });
  
  const totalIssued = beneficiaries.reduce((sum, b) => sum + b.percentage, 0);
  if (totalIssued < 100) {
    gradientStops.push(`#e5e7eb ${currentAngle}deg 360deg`);
  }
  
  const gradient = `conic-gradient(${gradientStops.join(', ')})`;
  
  return (
    <div className="flex flex-col items-center">
      <div className="w-48 h-48 rounded-full shadow-inner" style={{ background: gradient }} />
      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {beneficiaries.slice(0, 6).map((ben, index) => (
          <div key={ben.holder_name} className="flex items-center gap-2">
            <div className="w-3 h-3 flex-shrink-0" style={{ backgroundColor: colors[index % colors.length] }} />
            <span className="truncate max-w-[120px]" title={ben.holder_name}>{ben.holder_name}</span>
            <span className="font-mono text-xs text-muted-foreground">{ben.percentage.toFixed(1)}%</span>
          </div>
        ))}
        {beneficiaries.length > 6 && (
          <div className="col-span-2 text-muted-foreground text-xs mt-1">+{beneficiaries.length - 6} more holders</div>
        )}
        {totalIssued < 100 && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 flex-shrink-0 bg-gray-200" />
            <span>Unissued</span>
            <span className="font-mono text-xs text-muted-foreground">{(100 - totalIssued).toFixed(1)}%</span>
          </div>
        )}
      </div>
    </div>
  );
};

// ========== MAIN PAGE COMPONENT ==========
export default function BeneficiariesPage() {
  const { selectedTrust, isReadOnly } = useAuth();
  const { showUpgradeModal } = useUpgradeModal();
  const [activeTab, setActiveTab] = useState('overview');
  
  // Overview data
  const [overviewData, setOverviewData] = useState(null);
  const [expandedHolder, setExpandedHolder] = useState(null);
  
  // Certificates data
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showCertificateModal, setShowCertificateModal] = useState(false);
  const [showTransferModal, setShowTransferModal] = useState(false);
  const [editingCertificate, setEditingCertificate] = useState(null);
  const [showRevokeModal, setShowRevokeModal] = useState(null);
  const [certificateForm, setCertificateForm] = useState({
    holder_name: '',
    holder_identifier: '',
    email: '',
    phone: '',
    units: '',
    issue_date: format(new Date(), 'yyyy-MM-dd'),
    notes: ''
  });
  const [transferForm, setTransferForm] = useState({
    from_certificate_id: '',
    to_holder_name: '',
    to_holder_identifier: '',
    units: '',
    reason: ''
  });
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [settingsForm, setSettingsForm] = useState({
    total_authorized_units: 100,
    unit_label: 'Unit',
    allow_fractional: false
  });
  
  // PDF Preview
  const [pdfPreview, setPdfPreview] = useState({ show: false, loading: false, data: null, filename: '' });
  
  // Filter state
  const [statusFilter, setStatusFilter] = useState('active');

  // ========== DATA LOADING ==========
  const loadOverviewData = useCallback(async () => {
    if (!selectedTrust) return;
    try {
      const response = await fetchWithAuth(`/beneficiaries/dashboard?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        setOverviewData(await response.json());
      }
    } catch (error) {
      console.error('Failed to load overview:', error);
    }
  }, [selectedTrust]);

  const loadCertificatesData = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/trust-units/summary?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        const data = await response.json();
        setSummary(data);
        if (data.settings) {
          setSettingsForm({
            total_authorized_units: data.settings.total_authorized_units || 100,
            unit_label: data.settings.unit_label || 'Unit',
            allow_fractional: data.settings.allow_fractional || false
          });
        }
      }
    } catch (error) {
      console.error('Failed to load certificates:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedTrust]);

  useEffect(() => {
    if (selectedTrust) {
      loadOverviewData();
      loadCertificatesData();
    }
  }, [selectedTrust, loadOverviewData, loadCertificatesData]);

  // ========== HANDLERS ==========
  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      return format(parseISO(dateStr), 'MMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  // Read-only guards for write actions
  const handleOpenCertificateModal = (editing = null) => {
    if (isReadOnly) {
      showUpgradeModal('issue certificates', 'button_click', 'beneficiaries_page');
      return;
    }
    if (editing) {
      setEditingCertificate(editing);
      setCertificateForm({
        holder_name: editing.holder_name,
        holder_identifier: editing.holder_identifier || '',
        email: editing.email || '',
        phone: editing.phone || '',
        units: editing.units.toString(),
        issue_date: editing.issue_date?.split('T')[0] || format(new Date(), 'yyyy-MM-dd'),
        notes: editing.notes || ''
      });
    }
    setShowCertificateModal(true);
  };

  const handleOpenTransferModal = (fromCert) => {
    if (isReadOnly) {
      showUpgradeModal('transfer certificates', 'button_click', 'beneficiaries_page');
      return;
    }
    setTransferForm({
      from_certificate_id: fromCert.certificate_id,
      to_holder_name: '',
      to_holder_identifier: '',
      units: '',
      reason: ''
    });
    setShowTransferModal(true);
  };

  const handleOpenSettingsModal = () => {
    if (isReadOnly) {
      showUpgradeModal('modify trust settings', 'button_click', 'beneficiaries_page');
      return;
    }
    setShowSettingsModal(true);
  };

  const handleSaveSettings = async () => {
    try {
      const response = await fetchWithAuth('/trust-units/settings', {
        method: 'PUT',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          ...settingsForm
        })
      });
      if (response.ok) {
        toast.success('Settings updated');
        setShowSettingsModal(false);
        loadCertificatesData();
        loadOverviewData();
      }
    } catch (error) {
      toast.error('Failed to save settings');
    }
  };
  const sanitizeOptional = (val) => {
        return val === null || val === undefined || val.trim() === '' ? null : val;
      };

      // Handle issue/update certificate
      const handleIssueCertificate = async () => {
    if (!certificateForm.holder_name || !certificateForm.units) {
      toast.error('Holder name and units are required');
      return;
    }
    
    const units = parseFloat(certificateForm.units);
    if (!editingCertificate && summary && units > summary.remaining_units) {
      toast.error(`Cannot issue ${units} units. Only ${summary.remaining_units} units remaining.`);
      return;
    }
    
    try {
      const url = editingCertificate 
        ? `/trust-units/certificates/${editingCertificate.certificate_id}`
        : '/trust-units/certificates';
      const method = editingCertificate ? 'PATCH' : 'POST';
      
      const response = await fetchWithAuth(url, {
        method,
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          ...certificateForm,
          holder_identifier: sanitizeOptional(certificateForm.holder_identifier),
          email: sanitizeOptional(certificateForm.email),
          phone: sanitizeOptional(certificateForm.phone),
          notes: sanitizeOptional(certificateForm.notes),
          units: parseFloat(certificateForm.units)
        })
      });
      
      if (response.ok) {
        toast.success(editingCertificate ? 'Certificate updated' : 'Certificate issued');
        setShowCertificateModal(false);
        resetCertificateForm();
        loadCertificatesData();
        loadOverviewData();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to save certificate');
      }
    } catch (error) {
      toast.error('Failed to save certificate');
    }
  };

  const handleTransfer = async () => {
    if (!transferForm.from_certificate_id || !transferForm.to_holder_name || !transferForm.units) {
      toast.error('All fields are required');
      return;
    }
    try {
      // Get the "from" holder name from the selected certificate
      const fromCert = summary?.certificates?.find(c => c.certificate_id === transferForm.from_certificate_id);
      if (!fromCert) {
        toast.error('Invalid source certificate');
        return;
      }
      
      const response = await fetchWithAuth('/trust-units/transfers', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          from_holder: fromCert.holder_name,
          to_holder: transferForm.to_holder_name,
          units: parseFloat(transferForm.units),
          reason: transferForm.reason || 'Transfer'
        })
      });
      if (response.ok) {
        toast.success('Transfer completed');
        setShowTransferModal(false);
        setTransferForm({ from_certificate_id: '', to_holder_name: '', to_holder_identifier: '', units: '', reason: '' });
        loadCertificatesData();
        loadOverviewData();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Transfer failed');
      }
    } catch (error) {
      toast.error('Transfer failed');
    }
  };

  const handleRevoke = async (certificate) => {
    try {
      const response = await fetchWithAuth(`/trust-units/certificates/${certificate.certificate_id}/revoke`, {
        method: 'POST',
        body: JSON.stringify({ trust_id: selectedTrust.trust_id })
      });
      if (response.ok) {
        toast.success('Certificate revoked');
        setShowRevokeModal(null);
        loadCertificatesData();
        loadOverviewData();
      }
    } catch (error) {
      toast.error('Failed to revoke certificate');
    }
  };

  const handleViewPDF = async (certificate) => {
    setPdfPreview({ show: true, loading: true, data: null, filename: '' });
    try {
      const response = await fetchWithAuth(`/trust-units/certificates/${certificate.certificate_id}/pdf`);
      if (response.ok) {
        const data = await response.json();
        setPdfPreview({ show: true, loading: false, data: data.pdf_base64, filename: data.filename });
      } else {
        toast.error('Failed to load PDF');
        setPdfPreview({ show: false, loading: false, data: null, filename: '' });
      }
    } catch (error) {
      toast.error('Failed to load PDF');
      setPdfPreview({ show: false, loading: false, data: null, filename: '' });
    }
  };

  const resetCertificateForm = () => {
    setCertificateForm({
      holder_name: '',
      holder_identifier: '',
      email: '',
      phone: '',
      units: '',
      issue_date: format(new Date(), 'yyyy-MM-dd'),
      notes: ''
    });
    setEditingCertificate(null);
  };

  const openEditModal = (certificate) => {
    setEditingCertificate(certificate);
    setCertificateForm({
      holder_name: certificate.holder_name,
      holder_identifier: certificate.holder_identifier || '',
      email: certificate.email || '',
      phone: certificate.phone || '',
      units: certificate.units.toString(),
      issue_date: certificate.issue_date,
      notes: certificate.notes || ''
    });
    setShowCertificateModal(true);
  };

  // Filter certificates
  const filteredCertificates = summary?.certificates?.filter(cert => {
    if (statusFilter === 'all') return true;
    return cert.status === statusFilter;
  }) || [];

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Select a trust to manage beneficiaries</p>
            </div>
          </div>
        </main>
      <MobileBottomNav />
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
              <h1 className="font-serif text-3xl lg:text-4xl text-navy dark:text-gold mb-2" data-testid="beneficiaries-page-title">
                Beneficiaries
              </h1>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                {selectedTrust.name} • Beneficial Interest & Ownership
              </p>
            </div>
            <div className="flex gap-2 mt-4 md:mt-0">
              <Button variant="outline" onClick={() => setShowSettingsModal(true)} data-testid="settings-btn">
                <Settings className="w-4 h-4 mr-2" />
                Settings
              </Button>
            </div>
          </div>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="mb-6 bg-muted/50">
              <TabsTrigger value="overview" className="data-[state=active]:bg-navy data-[state=active]:text-white" data-testid="tab-overview">
                <PieChart className="w-4 h-4 mr-2" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="certificates" className="data-[state=active]:bg-navy data-[state=active]:text-white" data-testid="tab-certificates">
                <Award className="w-4 h-4 mr-2" />
                Certificates
              </TabsTrigger>
              <TabsTrigger value="transfers" className="data-[state=active]:bg-navy data-[state=active]:text-white" data-testid="tab-transfers">
                <ArrowRightLeft className="w-4 h-4 mr-2" />
                Transfer History
              </TabsTrigger>
            </TabsList>

            {/* ========== OVERVIEW TAB ========== */}
            <TabsContent value="overview">
              {loading ? (
                <div className="card-trust p-8 text-center">
                  <div className="w-8 h-8 border-2 border-navy dark:border-gold border-t-transparent animate-spin mx-auto mb-4"></div>
                  <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading...</p>
                </div>
              ) : !overviewData ? (
                <div className="card-trust p-8 text-center">
                  <p className="text-muted-foreground">No data available</p>
                </div>
              ) : (
                <>
                  {/* Summary Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                    <div className="card-trust p-4" data-testid="total-authorized-card">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-navy/10 dark:bg-gold/10 flex items-center justify-center">
                          <Award className="w-5 h-5 text-navy dark:text-gold" />
                        </div>
                        <div>
                          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Total Authorized</p>
                          <p className="font-serif text-2xl text-navy dark:text-foreground">{overviewData.total_authorized_units}</p>
                        </div>
                      </div>
                    </div>
                    
                    <div className="card-trust p-4" data-testid="issued-units-card">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                          <FileCheck className="w-5 h-5 text-green-700 dark:text-green-400" />
                        </div>
                        <div>
                          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Issued</p>
                          <p className="font-serif text-2xl text-navy dark:text-foreground">{overviewData.total_issued_units}</p>
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
                          <p className="font-serif text-2xl text-navy dark:text-foreground">{overviewData.remaining_units}</p>
                        </div>
                      </div>
                    </div>
                    
                    <div className="card-trust p-4" data-testid="beneficiaries-count-card">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                          <Users className="w-5 h-5 text-amber-700 dark:text-amber-400" />
                        </div>
                        <div>
                          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Beneficiaries</p>
                          <p className="font-serif text-2xl text-navy dark:text-foreground">{overviewData.beneficiaries.length}</p>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Pie Chart & Holder List */}
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div className="card-trust p-6" data-testid="ownership-chart">
                      <div className="flex items-center gap-2 mb-6">
                        <PieChart className="w-4 h-4 text-navy dark:text-gold" />
                        <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Ownership Distribution</h2>
                      </div>
                      {overviewData.beneficiaries.length > 0 ? (
                        <OwnershipPieChart beneficiaries={overviewData.beneficiaries} totalAuthorized={overviewData.total_authorized_units} />
                      ) : (
                        <div className="text-center py-8 text-muted-foreground">
                          <Users className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
                          <p>No certificates issued yet</p>
                          <Button className="btn-primary mt-4" onClick={() => { setActiveTab('certificates'); handleOpenCertificateModal(); }}>
                            <Plus className="w-4 h-4 mr-2" /> Issue First Certificate
                          </Button>
                        </div>
                      )}
                    </div>

                    <div className="lg:col-span-2 card-trust overflow-hidden">
                      <div className="p-4 border-b border-border flex items-center gap-2">
                        <Users className="w-4 h-4 text-navy dark:text-gold" />
                        <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Certificate Holders</h2>
                      </div>
                      
                      {overviewData.beneficiaries.length === 0 ? (
                        <div className="p-8 text-center">
                          <Users className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
                          <p className="text-muted-foreground">No beneficiaries yet</p>
                        </div>
                      ) : (
                        <div className="divide-y divide-border max-h-[500px] overflow-y-auto">
                          {overviewData.beneficiaries.map((ben, index) => (
                            <div key={ben.holder_name} data-testid={`beneficiary-row-${index}`}>
                              <button
                                onClick={() => setExpandedHolder(expandedHolder === ben.holder_name ? null : ben.holder_name)}
                                className="w-full p-4 flex items-center justify-between hover:bg-muted/20 transition-colors"
                              >
                                <div className="flex items-center gap-4">
                                  <div className="w-10 h-10 bg-navy/10 dark:bg-gold/10 flex items-center justify-center font-serif text-navy dark:text-gold">
                                    {index + 1}
                                  </div>
                                  <div className="text-left">
                                    <p className="font-medium text-navy dark:text-foreground">{ben.holder_name}</p>
                                    {ben.holder_identifier && (
                                      <p className="text-xs text-muted-foreground font-mono">{ben.holder_identifier}</p>
                                    )}
                                    {ben.email && (
                                      <p className="text-xs text-muted-foreground">{ben.email}</p>
                                    )}
                                    {ben.phone && (
                                      <p className="text-xs text-muted-foreground">{ben.phone}</p>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-6">
                                  <div className="text-right">
                                    <p className="font-mono text-lg text-navy dark:text-foreground">{ben.total_units}</p>
                                    <p className="text-xs text-muted-foreground">{overviewData.unit_label}s</p>
                                  </div>
                                  <div className="text-right min-w-[80px]">
                                    <p className="font-mono text-lg text-gold">{ben.percentage.toFixed(2)}%</p>
                                    <p className="text-xs text-muted-foreground">ownership</p>
                                  </div>
                                  {expandedHolder === ben.holder_name ? <ChevronUp className="w-5 h-5 text-muted-foreground" /> : <ChevronDown className="w-5 h-5 text-muted-foreground" />}
                                </div>
                              </button>
                              
                              {expandedHolder === ben.holder_name && (
                                <div className="bg-muted/30 p-4 border-t border-border">
                                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
                                    {ben.certificate_count} Certificate{ben.certificate_count !== 1 ? 's' : ''}
                                  </p>
                                  <div className="space-y-2">
                                    {ben.certificates.map((cert) => (
                                      <div key={cert.certificate_id} className="flex items-center justify-between p-3 bg-background border border-border">
                                        <div className="flex items-center gap-3">
                                          <span className="font-mono text-sm text-navy dark:text-gold">{cert.certificate_number}</span>
                                          <span className="text-sm text-muted-foreground">{cert.units} units</span>
                                        </div>
                                        <span className="text-xs text-muted-foreground font-mono">Issued {formatDate(cert.issue_date)}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </TabsContent>

            {/* ========== CERTIFICATES TAB ========== */}
            <TabsContent value="certificates">
              {/* Actions Bar */}
              <div className="card-trust p-4 mb-6">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <Select value={statusFilter} onValueChange={setStatusFilter}>
                      <SelectTrigger className="w-[150px]" data-testid="status-filter">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="active">Active Only</SelectItem>
                        <SelectItem value="all">All Certificates</SelectItem>
                        <SelectItem value="revoked">Revoked</SelectItem>
                        <SelectItem value="transferred">Transferred</SelectItem>
                      </SelectContent>
                    </Select>
                    
                    {summary && (
                      <div className="text-sm">
                        <span className="text-muted-foreground">Available: </span>
                        <span className="font-mono font-medium text-navy dark:text-gold">{summary.remaining_units} units</span>
                        <span className="text-muted-foreground"> of {summary.settings?.total_authorized_units}</span>
                      </div>
                    )}
                  </div>
                  
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => handleOpenTransferModal(summary?.certificates?.find(c => c.status === 'active'))} disabled={!summary?.certificates?.filter(c => c.status === 'active').length} data-testid="transfer-btn">
                      <ArrowRightLeft className="w-4 h-4 mr-2" />
                      Transfer
                    </Button>
                    <Button className="btn-primary" onClick={() => { resetCertificateForm(); handleOpenCertificateModal(); }} data-testid="issue-units-btn">
                      <Plus className="w-4 h-4 mr-2" />
                      Issue Units
                    </Button>
                  </div>
                </div>
              </div>

              {/* Certificates List */}
              <div className="card-trust overflow-hidden">
                <div className="p-4 border-b border-border flex items-center gap-2">
                  <Award className="w-4 h-4 text-navy dark:text-gold" />
                  <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Certificates</h2>
                  <span className="ml-auto text-xs text-muted-foreground">{filteredCertificates.length} records</span>
                </div>
                
                {loading ? (
                  <div className="p-8 text-center">
                    <div className="w-8 h-8 border-2 border-navy dark:border-gold border-t-transparent animate-spin mx-auto mb-4"></div>
                    <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading...</p>
                  </div>
                ) : filteredCertificates.length === 0 ? (
                  <div className="p-8 text-center">
                    <Award className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
                    <p className="text-muted-foreground mb-4">No certificates found</p>
                    <Button className="btn-primary" onClick={() => { resetCertificateForm(); handleOpenCertificateModal(); }}>
                      <Plus className="w-4 h-4 mr-2" /> Issue First Certificate
                    </Button>
                  </div>
                ) : (
                  <div className="divide-y divide-border">
                    {filteredCertificates.map((cert) => (
                      <div key={cert.certificate_id} className={`p-4 flex items-center justify-between ${cert.status !== 'active' ? 'opacity-60 bg-muted/30' : ''}`} data-testid={`cert-${cert.certificate_id}`}>
                        <div className="flex items-center gap-4">
                          <div className="w-12 h-12 bg-navy/10 dark:bg-gold/10 flex items-center justify-center">
                            <Award className={`w-6 h-6 ${cert.status === 'active' ? 'text-navy dark:text-gold' : 'text-muted-foreground'}`} />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="font-medium text-navy dark:text-foreground">{cert.holder_name}</p>
                              <span className={`px-2 py-0.5 text-xs font-mono ${
                                cert.status === 'active' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                                cert.status === 'revoked' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
                              }`}>
                                {cert.status}
                              </span>
                            </div>
                            <p className="text-sm text-muted-foreground">
                              {cert.certificate_number} • {cert.units} {summary?.settings?.unit_label || 'Unit'}s ({cert.percentage.toFixed(2)}%)
                            </p>
                            <p className="text-xs text-muted-foreground font-mono">Issued {formatDate(cert.issue_date)}</p>
                            {cert.email && (
                              <p className="text-xs text-muted-foreground">{cert.email}</p>
                            )}
                            {cert.phone && (
                              <p className="text-xs text-muted-foreground">{cert.phone}</p>
                            )}
                          </div>
                        </div>
                        
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" data-testid={`cert-menu-${cert.certificate_id}`}>
                              <MoreVertical className="w-4 h-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => handleViewPDF(cert)}>
                              <FileText className="w-4 h-4 mr-2" />
                              View Certificate PDF
                            </DropdownMenuItem>
                            {cert.status === 'active' && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => openEditModal(cert)}>
                                  <Pencil className="w-4 h-4 mr-2" />
                                  Edit
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => { setTransferForm({ ...transferForm, from_certificate_id: cert.certificate_id }); setShowTransferModal(true); }}>
                                  <ArrowRightLeft className="w-4 h-4 mr-2" />
                                  Transfer Units
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => setShowRevokeModal(cert)} className="text-red-600">
                                  <XCircle className="w-4 h-4 mr-2" />
                                  Revoke
                                </DropdownMenuItem>
                              </>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </TabsContent>

            {/* ========== TRANSFERS TAB ========== */}
            <TabsContent value="transfers">
              <div className="card-trust overflow-hidden">
                <div className="p-4 border-b border-border flex items-center gap-2">
                  <History className="w-4 h-4 text-navy dark:text-gold" />
                  <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Transfer History</h2>
                </div>
                
                {!overviewData?.recent_transfers?.length ? (
                  <div className="p-8 text-center">
                    <ArrowRightLeft className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
                    <p className="text-muted-foreground">No transfers recorded yet</p>
                    <p className="text-sm text-muted-foreground mt-2">Transfers will appear here when units are moved between holders</p>
                  </div>
                ) : (
                  <div className="divide-y divide-border">
                    {overviewData.recent_transfers.map((transfer) => (
                      <div key={transfer.transfer_id} className="p-4 flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                            <TrendingUp className="w-5 h-5 text-blue-700 dark:text-blue-400" />
                          </div>
                          <div>
                            <p className="font-medium text-navy dark:text-foreground">
                              {transfer.from_holder ? (
                                <>{transfer.from_holder} → {transfer.to_holder}</>
                              ) : (
                                <>New issuance to {transfer.to_holder}</>
                              )}
                            </p>
                            <p className="text-xs text-muted-foreground">{transfer.reason || 'No reason specified'}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="font-mono text-navy dark:text-foreground">{transfer.units} units</p>
                          <p className="text-xs text-muted-foreground font-mono">{formatDate(transfer.created_at)}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </main>
      <MobileBottomNav />

      {/* ========== MODALS ========== */}
      
      {/* Issue/Edit Certificate Modal */}
      <Dialog open={showCertificateModal} onOpenChange={(open) => { if (!open) resetCertificateForm(); setShowCertificateModal(open); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingCertificate ? 'Edit Certificate' : 'Issue New Certificate'}</DialogTitle>
            <DialogDescription>
              {editingCertificate ? 'Update certificate details' : `Issue beneficial interest units. ${summary?.remaining_units || 0} units available.`}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label className="label-trust">Holder Name *</Label>
              <Input
                value={certificateForm.holder_name}
                onChange={(e) => setCertificateForm({ ...certificateForm, holder_name: e.target.value })}
                placeholder="John Smith"
                className="mt-1"
                data-testid="holder-name-input"
              />
            </div>
            <div>
              <Label className="label-trust">Holder Identifier (Optional)</Label>
              <Input
                value={certificateForm.holder_identifier}
                onChange={(e) => setCertificateForm({ ...certificateForm, holder_identifier: e.target.value })}
                placeholder="SSN last 4, EIN, etc."
                className="mt-1"
              />
            </div>
            <div>
              <Label className="label-trust">Email</Label>
              <Input
                type="email"
                value={certificateForm.email}
                onChange={(e) => setCertificateForm({ ...certificateForm, email: e.target.value })}
                placeholder="beneficiary@email.com"
                className="mt-1"
              />
            </div>
            <div>
              <Label className="label-trust">Phone</Label>
              <Input
                type="tel"
                value={certificateForm.phone}
                onChange={(e) => setCertificateForm({ ...certificateForm, phone: e.target.value })}
                placeholder="(555) 123-4567"
                className="mt-1"
              />
            </div>
            <div>
              <Label className="label-trust">Units *</Label>
              <Input
                type="number"
                step="any"
                min="0"
                value={certificateForm.units}
                onChange={(e) => setCertificateForm({ ...certificateForm, units: e.target.value })}
                placeholder="25"
                required
                className="mt-1"
                data-testid="units-input"
              />
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
            <div>
              <Label className="label-trust">Issue Date</Label>
              <Input
                type="date"
                value={certificateForm.issue_date}
                onChange={(e) => setCertificateForm({ ...certificateForm, issue_date: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label className="label-trust">Notes (Optional)</Label>
              <Textarea
                value={certificateForm.notes}
                onChange={(e) => setCertificateForm({ ...certificateForm, notes: e.target.value })}
                placeholder="Additional notes..."
                className="mt-1"
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCertificateModal(false); resetCertificateForm(); }}>Cancel</Button>
            <Button className="btn-primary" onClick={handleIssueCertificate} data-testid="save-certificate-btn">
              {editingCertificate ? 'Update' : 'Issue Certificate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Transfer Modal */}
      <Dialog open={showTransferModal} onOpenChange={setShowTransferModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Transfer Units</DialogTitle>
            <DialogDescription>Transfer units from one certificate holder to another</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label className="label-trust">From Certificate *</Label>
              <Select 
                value={transferForm.from_certificate_id} 
                onValueChange={(v) => {
                  // When changing "from", check if current "to" holder is the same as new "from" holder
                  const newFromCert = summary?.certificates?.find(c => c.certificate_id === v);
                  const shouldClearTo = transferForm.to_holder_name === newFromCert?.holder_name;
                  
                  setTransferForm({ 
                    ...transferForm, 
                    from_certificate_id: v,
                    // Clear "to" selection if it's now the same as "from"
                    to_holder_name: shouldClearTo ? '' : transferForm.to_holder_name,
                    to_holder_identifier: shouldClearTo ? '' : transferForm.to_holder_identifier
                  });
                }}
              >
                <SelectTrigger className="mt-1" data-testid="from-cert-select">
                  <SelectValue placeholder="Select source certificate" />
                </SelectTrigger>
                <SelectContent>
                  {summary?.certificates?.filter(c => c.status === 'active').map((cert) => (
                    <SelectItem key={cert.certificate_id} value={cert.certificate_id}>
                      {cert.holder_name} - {cert.units} units ({cert.certificate_number})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-trust">To Beneficiary *</Label>
              <Select 
                value={transferForm.to_holder_name} 
                onValueChange={(v) => {
                  // Find the selected certificate to get the identifier
                  const selectedCert = summary?.certificates?.find(c => c.holder_name === v);
                  setTransferForm({ 
                    ...transferForm, 
                    to_holder_name: v,
                    to_holder_identifier: selectedCert?.holder_identifier || ''
                  });
                }}
              >
                <SelectTrigger className="mt-1" data-testid="to-holder-select">
                  <SelectValue placeholder="Select destination beneficiary" />
                </SelectTrigger>
                <SelectContent>
                  {(() => {
                    // Get the holder name of the selected "from" certificate
                    const fromCert = summary?.certificates?.find(c => c.certificate_id === transferForm.from_certificate_id);
                    const fromHolderName = fromCert?.holder_name;
                    
                    // Aggregate units per holder, excluding the "from" holder
                    const holderTotals = {};
                    summary?.certificates?.filter(c => c.status === 'active').forEach(cert => {
                      if (cert.holder_name !== fromHolderName) {
                        if (!holderTotals[cert.holder_name]) {
                          holderTotals[cert.holder_name] = {
                            holder_name: cert.holder_name,
                            holder_identifier: cert.holder_identifier,
                            total_units: 0,
                            certificate_count: 0
                          };
                        }
                        holderTotals[cert.holder_name].total_units += cert.units || 0;
                        holderTotals[cert.holder_name].certificate_count += 1;
                      }
                    });
                    
                    return Object.values(holderTotals).map((holder) => (
                      <SelectItem key={holder.holder_name} value={holder.holder_name}>
                        {holder.holder_name} - {holder.total_units} units
                      </SelectItem>
                    ));
                  })()}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-trust">Units to Transfer *</Label>
              <Input
                type="number"
                step="any"
                min="0"
                value={transferForm.units}
                onChange={(e) => setTransferForm({ ...transferForm, units: e.target.value })}
                required
                className="mt-1"
                data-testid="transfer-units-input"
              />
            </div>
            <div>
              <Label className="label-trust">Reason (Optional)</Label>
              <Input
                value={transferForm.reason}
                onChange={(e) => setTransferForm({ ...transferForm, reason: e.target.value })}
                placeholder="Gift, sale, etc."
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowTransferModal(false)}>Cancel</Button>
            <Button className="btn-primary" onClick={handleTransfer} data-testid="confirm-transfer-btn">Complete Transfer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke Confirmation Modal */}
      <Dialog open={!!showRevokeModal} onOpenChange={() => setShowRevokeModal(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-red-600">Revoke Certificate</DialogTitle>
            <DialogDescription>
              Are you sure you want to revoke certificate {showRevokeModal?.certificate_number}? 
              This will return {showRevokeModal?.units} units to the available pool.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRevokeModal(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => handleRevoke(showRevokeModal)} data-testid="confirm-revoke-btn">Revoke Certificate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Settings Modal */}
      <Dialog open={showSettingsModal} onOpenChange={setShowSettingsModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Unit Settings</DialogTitle>
            <DialogDescription>Configure trust unit parameters</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label className="label-trust">Total Authorized Units</Label>
              <Input
                type="number"
                value={settingsForm.total_authorized_units}
                onChange={(e) => setSettingsForm({ ...settingsForm, total_authorized_units: parseInt(e.target.value) || 0 })}
                className="mt-1"
                data-testid="total-units-input"
              />
              <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1">
                <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
                This is the maximum number of units that can be issued. Cannot be less than currently issued units.
              </p>
            </div>
            <div>
              <Label className="label-trust">Unit Label</Label>
              <Input
                value={settingsForm.unit_label}
                onChange={(e) => setSettingsForm({ ...settingsForm, unit_label: e.target.value })}
                placeholder="Unit, Share, Interest"
                className="mt-1"
              />
            </div>
            <div className="flex items-center justify-between p-3 bg-muted/30 border border-border">
              <div>
                <Label className="label-trust">Allow Fractional Units</Label>
                <p className="text-xs text-muted-foreground">Enable decimals (e.g., 12.5 units)</p>
              </div>
              <Switch
                checked={settingsForm.allow_fractional}
                onCheckedChange={(checked) => setSettingsForm({ ...settingsForm, allow_fractional: checked })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSettingsModal(false)}>Cancel</Button>
            <Button className="btn-primary" onClick={handleSaveSettings} data-testid="save-settings-btn">Save Settings</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* PDF Preview Modal */}
      <PDFPreviewModal
        open={pdfPreview.show}
        onOpenChange={(isOpen) => !isOpen && setPdfPreview({ show: false, loading: false, data: null, filename: '' })}
        pdfBase64={pdfPreview.data}
        filename={pdfPreview.filename}
        title="Unit Certificate"
      />
    </div>
  );
}
