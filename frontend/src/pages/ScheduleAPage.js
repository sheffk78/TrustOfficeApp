import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { fetchWithAuth } from '@/utils/api';
import PageHelpButton from '@/components/PageHelpButton';
import { 
  Plus, 
  Home,
  Car,
  Wallet,
  Building2,
  Bitcoin,
  Lightbulb,
  FileText,
  Package,
  Edit,
  Trash2,
  FileDown,
  ArrowRight,
  ExternalLink,
  Ban
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const ASSET_CATEGORIES = [
  { value: 'real_property', label: 'Real Property', icon: Home, description: 'Land, buildings, residences' },
  { value: 'personal_property', label: 'Personal Property (Tangible)', icon: Car, description: 'Vehicles, furnishings, equipment' },
  { value: 'financial_accounts', label: 'Financial Accounts', icon: Wallet, description: 'Bank accounts, investments, brokerage' },
  { value: 'business_interests', label: 'Business Interests', icon: Building2, description: 'LLCs, partnerships, corporations' },
  { value: 'digital_assets', label: 'Digital Assets', icon: Bitcoin, description: 'Cryptocurrency, NFTs, digital holdings' },
  { value: 'intellectual_property', label: 'Intellectual Property', icon: Lightbulb, description: 'Trademarks, copyrights, patents' },
  { value: 'notes_receivable', label: 'Notes Receivable', icon: FileText, description: 'Debts owed to grantor, promissory notes' },
  { value: 'other_property', label: 'Other Property', icon: Package, description: 'Precious metals, art, collectibles' }
];

export default function ScheduleAPage() {
  const navigate = useNavigate();
  const { selectedTrust, isReadOnly } = useAuth();
  const { showUpgradeModal } = useUpgradeModal();
  const [assets, setAssets] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState(null);
  const [activeTab, setActiveTab] = useState('active');
  const [formData, setFormData] = useState({
    category: 'real_property',
    description: '',
    identifier: '',
    location: '',
    approximate_value: '',
    date_conveyed: new Date().toISOString().split('T')[0],
    notes: ''
  });
  const [exporting, setExporting] = useState(false);
  
  // Disposition modal state
  const [disposeDialogOpen, setDisposeDialogOpen] = useState(false);
  const [assetToDispose, setAssetToDispose] = useState(null);
  const [disposeFormData, setDisposeFormData] = useState({
    disposition_date: new Date().toISOString().split('T')[0],
    disposition_reason: 'sale',
    disposition_value: '',
    disposition_recipient: '',
    disposition_notes: '',
    create_minutes: true
  });

  useEffect(() => {
    if (selectedTrust) {
      loadAssets();
      loadSummary();
    }
  }, [selectedTrust, activeTab]);

  const loadAssets = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const status = activeTab === 'all' ? 'all' : 'active';
      const response = await fetchWithAuth(`/schedule-a?trust_id=${selectedTrust.trust_id}&status=${status}`);
      if (response.ok) {
        setAssets(await response.json());
      }
    } catch (error) {
      console.error('Failed to load assets:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadSummary = async () => {
    if (!selectedTrust) return;
    try {
      const response = await fetchWithAuth(`/schedule-a/summary/${selectedTrust.trust_id}`);
      if (response.ok) {
        setSummary(await response.json());
      }
    } catch (error) {
      console.error('Failed to load summary:', error);
    }
  };

  const handleDialogOpenChange = (open) => {
    if (open && isReadOnly) {
      showUpgradeModal('add assets to Schedule A', 'button_click', 'schedule_a_page');
      return;
    }
    setDialogOpen(open);
    if (!open) resetForm();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    const payload = {
      ...formData,
      trust_id: selectedTrust.trust_id,
      approximate_value: formData.approximate_value ? parseFloat(formData.approximate_value) : null
    };

    try {
      let response;
      if (editingAsset) {
        response = await fetchWithAuth(`/schedule-a/${editingAsset.item_id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } else {
        response = await fetchWithAuth('/schedule-a', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }

      if (response.ok) {
        toast.success(editingAsset ? 'Asset updated' : 'Asset added to Schedule A');
        setDialogOpen(false);
        resetForm();
        loadAssets();
        loadSummary();
      } else {
        const error = await response.json();
        showError(toast, new Error(error.detail || 'Failed to save asset'), { operation: 'save', page: 'ScheduleA' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'save', page: 'ScheduleA' });
    }
  };

  const handleDelete = async (itemId) => {
    if (!confirm('Are you sure you want to remove this asset from Schedule A?')) return;
    
    try {
      const response = await fetchWithAuth(`/schedule-a/${itemId}`, { method: 'DELETE' });
      if (response.ok) {
        toast.success('Asset removed');
        loadAssets();
        loadSummary();
      }
    } catch (error) {
      showError(toast, error, { operation: 'delete', page: 'ScheduleA' });
    }
  };

  const handleEdit = (asset) => {
    if (isReadOnly) {
      showUpgradeModal('edit assets', 'button_click', 'schedule_a_page');
      return;
    }
    setEditingAsset(asset);
    setFormData({
      category: asset.category,
      description: asset.description,
      identifier: asset.identifier,
      location: asset.location,
      approximate_value: asset.approximate_value || '',
      date_conveyed: asset.date_conveyed,
      notes: asset.notes
    });
    setDialogOpen(true);
  };

  const handleDisposeClick = (asset) => {
    if (isReadOnly) {
      showUpgradeModal('dispose assets', 'button_click', 'schedule_a_page');
      return;
    }
    setAssetToDispose(asset);
    setDisposeFormData({
      disposition_date: new Date().toISOString().split('T')[0],
      disposition_reason: 'sale',
      disposition_value: asset.approximate_value || '',
      disposition_recipient: '',
      disposition_notes: '',
      create_minutes: true
    });
    setDisposeDialogOpen(true);
  };

  const handleDisposeSubmit = async () => {
    if (!assetToDispose) return;

    if (disposeFormData.create_minutes) {
      // Navigate to disposition minutes template with pre-filled data
      const params = new URLSearchParams({
        asset_id: assetToDispose.item_id,
        asset_description: assetToDispose.description,
        disposition_date: disposeFormData.disposition_date,
        disposition_reason: disposeFormData.disposition_reason,
        disposition_value: disposeFormData.disposition_value || '',
        disposition_recipient: disposeFormData.disposition_recipient || '',
        disposition_notes: disposeFormData.disposition_notes || ''
      });
      navigate(`/minutes/template/disposition_of_asset?${params.toString()}`);
    } else {
      // Direct disposition without minutes
      try {
        const response = await fetchWithAuth(`/schedule-a/${assetToDispose.item_id}/dispose`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            disposition_date: disposeFormData.disposition_date,
            disposition_reason: disposeFormData.disposition_reason,
            disposition_value: disposeFormData.disposition_value ? parseFloat(disposeFormData.disposition_value) : null,
            disposition_recipient: disposeFormData.disposition_recipient,
            disposition_notes: disposeFormData.disposition_notes
          })
        });

        if (response.ok) {
          toast.success('Asset marked as disposed');
          setDisposeDialogOpen(false);
          setAssetToDispose(null);
          loadAssets();
          loadSummary();
        } else {
          const error = await response.json();
          showError(toast, new Error(error.detail || 'Failed to dispose asset'), { operation: 'dispose', page: 'ScheduleA' });
        }
      } catch (error) {
        showError(toast, error, { operation: 'dispose', page: 'ScheduleA' });
      }
    }
  };

  const resetForm = () => {
    setEditingAsset(null);
    setFormData({
      category: 'real_property',
      description: '',
      identifier: '',
      location: '',
      approximate_value: '',
      date_conveyed: new Date().toISOString().split('T')[0],
      notes: ''
    });
  };

  const formatValue = (value) => {
    if (!value) return 'Not disclosed';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const date = parseISO(dateStr);
      if (isNaN(date.getTime())) {
        const plainDate = new Date(dateStr);
        if (isNaN(plainDate.getTime())) {
          return dateStr;
        }
        return format(plainDate, 'MMM d, yyyy');
      }
      return format(date, 'MMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  const getCategoryInfo = (categoryValue) => {
    return ASSET_CATEGORIES.find(c => c.value === categoryValue) || ASSET_CATEGORIES[7];
  };

  const handleExportPDF = async () => {
    if (!selectedTrust) return;
    
    setExporting(true);
    try {
      const response = await fetchWithAuth(`/schedule-a/export/${selectedTrust.trust_id}/pdf`);
      if (response.ok) {
        const data = await response.json();
        const link = document.createElement('a');
        link.href = `data:application/pdf;base64,${data.pdf_base64}`;
        link.download = data.filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        toast.success('Schedule A PDF downloaded');
      } else {
        toast.error('Failed to generate PDF. Please try again. If the problem continues, contact support@trustoffice.app.');
      }
    } catch (error) {
      console.error('Failed to export PDF:', error);
      showError(toast, error, { operation: 'export', page: 'ScheduleA' });
    } finally {
      setExporting(false);
    }
  };

  // Count assets by status
  const activeAssets = assets.filter(a => a.status !== 'disposed');
  const disposedAssets = assets.filter(a => a.status === 'disposed');

  // Group assets by category
  const groupedAssets = assets.reduce((acc, asset) => {
    const cat = asset.category;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(asset);
    return acc;
  }, {});

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Select a trust to view Schedule A</p>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background" data-testid="schedule-a-page">
      <Sidebar />
      <main className="lg:pl-64 pt-16 lg:pt-0 mobile-layout-offset">
        
        <div className="p-4 lg:p-8">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Trust Assets</h1>
              <p className="page-subtitle">Manage trust assets and corpus — add, update, or dispose of trust property with proper documentation</p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'Manage trust assets and corpus — the initial and current property of the trust' },
                  { text: 'Add, update, or dispose of trust assets with proper documentation' },
                  { text: 'Track asset values, dates, and disposition history' },
                ]}
                taPrompt="Walk me through the Schedule A page and how to add an asset"
              />
              <Button
                variant="outline" 
                onClick={handleExportPDF}
                disabled={exporting || assets.length === 0}
                data-testid="export-pdf-btn"
              >
                <FileDown className="w-4 h-4 mr-2" />
                {exporting ? 'Exporting...' : 'Export PDF'}
              </Button>
              <Dialog open={dialogOpen} onOpenChange={handleDialogOpenChange}>
                <DialogTrigger asChild>
                  <Button className="btn-primary" data-testid="add-asset-btn">
                    <Plus className="w-4 h-4 mr-2" />
                    Add Asset
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-lg">
                  <DialogHeader>
                    <DialogTitle className="font-serif text-xl text-navy">
                      {editingAsset ? 'Edit Asset' : 'Add Asset to Schedule A'}
                    </DialogTitle>
                  </DialogHeader>
                  <form onSubmit={handleSubmit} className="space-y-4 mt-4">
                    <div>
                      <Label className="label-trust">Asset Category</Label>
                      <Select value={formData.category} onValueChange={(v) => setFormData({ ...formData, category: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ASSET_CATEGORIES.map(cat => (
                            <SelectItem key={cat.value} value={cat.value}>
                              <div className="flex items-center gap-2">
                                <cat.icon className="w-4 h-4" />
                                {cat.label}
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <div>
                      <Label className="label-trust">Description *</Label>
                      <Input
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        placeholder="e.g., Single-family residence, 2020 Toyota Camry"
                        className="mt-1 input-trust"
                        required
                        data-testid="asset-description-input"
                      />
                    </div>

                    <div>
                      <Label className="label-trust">Identifier / Serial Number</Label>
                      <Input
                        value={formData.identifier}
                        onChange={(e) => setFormData({ ...formData, identifier: e.target.value })}
                        placeholder="e.g., VIN, Account #, USPTO Reg. No."
                        className="mt-1 input-trust"
                      />
                    </div>

                    <div>
                      <Label className="label-trust">Location / Legal Description</Label>
                      <Input
                        value={formData.location}
                        onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                        placeholder="e.g., 123 Main St, City, State or Bank Name"
                        className="mt-1 input-trust"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label className="label-trust">Approximate Value</Label>
                        <Input
                          type="number"
                          value={formData.approximate_value}
                          onChange={(e) => setFormData({ ...formData, approximate_value: e.target.value })}
                          placeholder="$0.00"
                          className="mt-1 input-trust"
                        />
                      </div>
                      <div>
                        <Label className="label-trust">Date Conveyed *</Label>
                        <Input
                          type="date"
                          value={formData.date_conveyed}
                          onChange={(e) => setFormData({ ...formData, date_conveyed: e.target.value })}
                          className="mt-1 input-trust"
                          required
                        />
                      </div>
                    </div>

                    <div>
                      <Label className="label-trust">Notes</Label>
                      <Textarea
                        value={formData.notes}
                        onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                        placeholder="Additional details..."
                        className="mt-1"
                        rows={2}
                      />
                    </div>

                    <div className="flex justify-end gap-3 pt-4">
                      <Button type="button" variant="outline" onClick={() => { setDialogOpen(false); resetForm(); }}>
                        Cancel
                      </Button>
                      <Button type="submit" className="btn-primary" data-testid="save-asset-btn">
                        {editingAsset ? 'Update Asset' : 'Add Asset'}
                      </Button>
                    </div>
                  </form>
                </DialogContent>
              </Dialog>
            </div>
          </div>

          {/* Summary Cards */}
          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              <div className="card-trust p-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Active Assets</p>
                <p className="font-serif text-2xl text-navy">{activeAssets.length}</p>
              </div>
              <div className="card-trust p-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Total Value</p>
                <p className="font-serif text-2xl text-navy">{formatValue(summary.total_value)}</p>
              </div>
              <div className="card-trust p-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Categories</p>
                <p className="font-serif text-2xl text-navy">{Object.keys(summary.categories || {}).length}</p>
              </div>
              <div className="card-trust p-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Disposed</p>
                <p className="font-serif text-2xl text-orange-600">{disposedAssets.length}</p>
              </div>
            </div>
          )}

          {/* Tabs for Active/All */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="mb-6">
            <TabsList className="grid w-full max-w-xs grid-cols-2">
              <TabsTrigger value="active" data-testid="tab-active">
                Active ({activeAssets.length})
              </TabsTrigger>
              <TabsTrigger value="all" data-testid="tab-all">
                All ({assets.length})
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Assets by Category */}
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map(i => (
                <div key={i} className="card-trust p-6 animate-pulse">
                  <div className="h-6 bg-muted rounded w-1/4 mb-4"></div>
                  <div className="h-4 bg-muted rounded w-3/4"></div>
                </div>
              ))}
            </div>
          ) : assets.length === 0 ? (
            <div className="card-trust corner-mark p-12 text-center">
              <Package className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
              <h3 className="font-serif text-xl text-navy mb-2">No Assets Yet</h3>
              <p className="text-muted-foreground mb-6">
                Add assets to Schedule A to track the trust corpus
              </p>
              <Button className="btn-primary" onClick={() => handleDialogOpenChange(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Add First Asset
              </Button>
            </div>
          ) : (
            <div className="space-y-6">
              {ASSET_CATEGORIES.map(category => {
                const categoryAssets = groupedAssets[category.value] || [];
                if (categoryAssets.length === 0) return null;
                
                const CategoryIcon = category.icon;
                const categoryTotal = categoryAssets
                  .filter(a => a.status !== 'disposed')
                  .reduce((sum, a) => sum + (a.approximate_value || 0), 0);
                
                return (
                  <div key={category.value} className="card-trust">
                    <div className="flex items-center justify-between p-4 border-b border-border">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-navy/10 flex items-center justify-center">
                          <CategoryIcon className="w-5 h-5 text-navy" />
                        </div>
                        <div>
                          <h3 className="font-serif text-lg text-navy">{category.label}</h3>
                          <p className="text-xs text-muted-foreground">{categoryAssets.length} item{categoryAssets.length !== 1 ? 's' : ''}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-sm text-navy">{formatValue(categoryTotal)}</p>
                        <p className="text-xs text-muted-foreground">active value</p>
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="trust-table w-full">
                        <thead>
                          <tr>
                            <th className="text-left p-3">Description</th>
                            <th className="text-left p-3 hidden md:table-cell">Identifier</th>
                            <th className="text-left p-3 hidden lg:table-cell">Location</th>
                            <th className="text-right p-3">Value</th>
                            <th className="text-center p-3 hidden md:table-cell">Date</th>
                            <th className="text-center p-3">Status</th>
                            <th className="text-center p-3">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {categoryAssets.map(asset => (
                            <tr key={asset.item_id} className={`border-t border-border ${asset.status === 'disposed' ? 'opacity-60 bg-muted/30' : ''}`}>
                              <td className="p-3">
                                <p className="font-medium text-navy">{asset.description}</p>
                                {asset.notes && <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{asset.notes}</p>}
                                {asset.minutes_ref && (
                                  <Link 
                                    to={`/minutes/${asset.minutes_ref}`}
                                    className="text-xs text-blue-600 hover:underline mt-1 flex items-center gap-1"
                                  >
                                    Added via Minutes <ExternalLink className="w-3 h-3" />
                                  </Link>
                                )}
                                {asset.disposition_minutes_ref && (
                                  <Link 
                                    to={`/minutes/${asset.disposition_minutes_ref}`}
                                    className="text-xs text-orange-600 hover:underline mt-1 flex items-center gap-1"
                                    data-testid={`disposition-minutes-link-${asset.item_id}`}
                                  >
                                    Disposition Minutes <ExternalLink className="w-3 h-3" />
                                  </Link>
                                )}
                              </td>
                              <td className="p-3 font-mono text-sm hidden md:table-cell">{asset.identifier || '—'}</td>
                              <td className="p-3 text-sm hidden lg:table-cell">{asset.location || '—'}</td>
                              <td className="p-3 text-right font-mono">{formatValue(asset.approximate_value)}</td>
                              <td className="p-3 text-center text-sm hidden md:table-cell">
                                {formatDate(asset.date_conveyed)}
                                {asset.disposition_date && (
                                  <div className="text-xs text-orange-600">
                                    Disposed: {formatDate(asset.disposition_date)}
                                  </div>
                                )}
                              </td>
                              <td className="p-3 text-center">
                                {asset.status === 'disposed' ? (
                                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400" data-testid={`status-badge-${asset.item_id}`}>
                                    Disposed
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-success/10 text-success dark:bg-success/20 dark:text-success" data-testid={`status-badge-${asset.item_id}`}>
                                    Active
                                  </span>
                                )}
                              </td>
                              <td className="p-3 text-center">
                                {asset.status !== 'disposed' ? (
                                  <div className="flex justify-center gap-1">
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => handleEdit(asset)}
                                      title="Edit asset"
                                      data-testid={`edit-asset-${asset.item_id}`}
                                    >
                                      <Edit className="w-4 h-4" />
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="text-orange-600 hover:text-orange-700 hover:bg-orange-50"
                                      onClick={() => handleDisposeClick(asset)}
                                      title="Dispose/Sell asset"
                                      data-testid={`dispose-asset-${asset.item_id}`}
                                    >
                                      <Ban className="w-4 h-4" />
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="text-red-600 hover:text-red-700"
                                      onClick={() => handleDelete(asset.item_id)}
                                      title="Delete asset"
                                      data-testid={`delete-asset-${asset.item_id}`}
                                    >
                                      <Trash2 className="w-4 h-4" />
                                    </Button>
                                  </div>
                                ) : (
                                  <span className="text-xs text-muted-foreground">—</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* Dispose Asset Dialog */}
      <Dialog open={disposeDialogOpen} onOpenChange={setDisposeDialogOpen}>
        <DialogContent className="max-w-md" data-testid="dispose-asset-dialog">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-navy">
              Dispose / Sell Asset
            </DialogTitle>
            <DialogDescription>
              Mark this asset as disposed and optionally create minutes to document the transaction.
            </DialogDescription>
          </DialogHeader>
          
          {assetToDispose && (
            <div className="space-y-4 mt-4">
              <div className="bg-muted/50 p-3 rounded">
                <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground mb-1">Asset</p>
                <p className="font-medium text-navy">{assetToDispose.description}</p>
                <p className="text-sm text-muted-foreground">{getCategoryInfo(assetToDispose.category).label}</p>
                {assetToDispose.approximate_value && (
                  <p className="text-sm font-mono mt-1">{formatValue(assetToDispose.approximate_value)}</p>
                )}
              </div>

              <div>
                <Label className="label-trust">Disposition Type</Label>
                <Select 
                  value={disposeFormData.disposition_reason} 
                  onValueChange={(v) => setDisposeFormData({ ...disposeFormData, disposition_reason: v })}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="sale">Sale</SelectItem>
                    <SelectItem value="transfer">Transfer</SelectItem>
                    <SelectItem value="donation">Donation</SelectItem>
                    <SelectItem value="destruction">Destruction/Loss</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="label-trust">Disposition Date</Label>
                <Input
                  type="date"
                  value={disposeFormData.disposition_date}
                  onChange={(e) => setDisposeFormData({ ...disposeFormData, disposition_date: e.target.value })}
                  className="mt-1 input-trust"
                />
              </div>

              <div>
                <Label className="label-trust">
                  {disposeFormData.disposition_reason === 'sale' ? 'Sale Price' : 'Fair Market Value'}
                </Label>
                <Input
                  type="number"
                  value={disposeFormData.disposition_value}
                  onChange={(e) => setDisposeFormData({ ...disposeFormData, disposition_value: e.target.value })}
                  placeholder="$0.00"
                  className="mt-1 input-trust"
                />
              </div>

              {disposeFormData.disposition_reason !== 'destruction' && (
                <div>
                  <Label className="label-trust">
                    {disposeFormData.disposition_reason === 'sale' ? 'Buyer Name' : 'Recipient Name'}
                  </Label>
                  <Input
                    value={disposeFormData.disposition_recipient}
                    onChange={(e) => setDisposeFormData({ ...disposeFormData, disposition_recipient: e.target.value })}
                    placeholder="Optional"
                    className="mt-1 input-trust"
                  />
                </div>
              )}

              <div>
                <Label className="label-trust">Notes</Label>
                <Textarea
                  value={disposeFormData.disposition_notes}
                  onChange={(e) => setDisposeFormData({ ...disposeFormData, disposition_notes: e.target.value })}
                  placeholder="Additional details about the disposition..."
                  className="mt-1"
                  rows={2}
                />
              </div>

              <div className="flex items-center space-x-2 pt-2 border-t">
                <Checkbox
                  id="create-minutes"
                  checked={disposeFormData.create_minutes}
                  onCheckedChange={(checked) => setDisposeFormData({ ...disposeFormData, create_minutes: checked })}
                />
                <label
                  htmlFor="create-minutes"
                  className="text-sm font-medium leading-none cursor-pointer"
                >
                  Create minutes for this disposition
                </label>
              </div>
              
              {disposeFormData.create_minutes && (
                <p className="text-xs text-muted-foreground pl-6">
                  You'll be taken to the disposition minutes template with this information pre-filled.
                </p>
              )}
            </div>
          )}

          <DialogFooter className="mt-6">
            <Button variant="outline" onClick={() => setDisposeDialogOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleDisposeSubmit}
              className={disposeFormData.create_minutes ? "btn-primary" : "bg-orange-600 hover:bg-orange-700 text-white"}
              data-testid="confirm-dispose-btn"
            >
              {disposeFormData.create_minutes ? (
                <>
                  Continue to Minutes
                  <ArrowRight className="w-4 h-4 ml-2" />
                </>
              ) : (
                'Mark as Disposed'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
