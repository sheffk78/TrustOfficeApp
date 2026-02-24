import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
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
  Download,
  FileDown
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
  const { selectedTrust } = useAuth();
  const [assets, setAssets] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState(null);
  const [showDisposed, setShowDisposed] = useState(false);
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

  useEffect(() => {
    if (selectedTrust) {
      loadAssets();
      loadSummary();
    }
  }, [selectedTrust, showDisposed]);

  const loadAssets = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const status = showDisposed ? 'all' : 'active';
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
        toast.error(error.detail || 'Failed to save asset');
      }
    } catch (error) {
      toast.error('Failed to save asset');
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
      toast.error('Failed to delete asset');
    }
  };

  const handleEdit = (asset) => {
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
      // Try ISO format first
      const date = parseISO(dateStr);
      if (isNaN(date.getTime())) {
        // Try parsing as a plain date string
        const plainDate = new Date(dateStr);
        if (isNaN(plainDate.getTime())) {
          return dateStr; // Return original if parsing fails
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
        // Create download link
        const link = document.createElement('a');
        link.href = `data:application/pdf;base64,${data.pdf_base64}`;
        link.download = data.filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        toast.success('Schedule A PDF downloaded');
      } else {
        toast.error('Failed to generate PDF');
      }
    } catch (error) {
      console.error('Failed to export PDF:', error);
      toast.error('Failed to export PDF');
    } finally {
      setExporting(false);
    }
  };

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
    <div className="min-h-screen bg-background">
      <Sidebar />
      <main className="lg:pl-64 pt-16 lg:pt-0">
        <div className="p-4 lg:p-8">
          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-8">
            <div>
              <h1 className="font-serif text-3xl lg:text-4xl text-navy mb-2">Schedule A</h1>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                {selectedTrust.name} • Initial Corpus of the Trust
              </p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={showDisposed}
                  onChange={(e) => setShowDisposed(e.target.checked)}
                  className="rounded border-border"
                />
                <span className="text-muted-foreground">Show disposed assets</span>
              </label>
              <Button 
                variant="outline" 
                onClick={handleExportPDF}
                disabled={exporting || assets.length === 0}
                data-testid="export-pdf-btn"
              >
                <FileDown className="w-4 h-4 mr-2" />
                {exporting ? 'Exporting...' : 'Export PDF'}
              </Button>
              <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
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
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Total Assets</p>
                <p className="font-serif text-2xl text-navy">{summary.total_items}</p>
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
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Trust</p>
                <p className="font-serif text-lg text-navy truncate">{summary.trust_name}</p>
              </div>
            </div>
          )}

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
              <Button className="btn-primary" onClick={() => setDialogOpen(true)}>
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
                const categoryTotal = categoryAssets.reduce((sum, a) => sum + (a.approximate_value || 0), 0);
                
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
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="trust-table w-full">
                        <thead>
                          <tr>
                            <th className="text-left p-3">Description</th>
                            <th className="text-left p-3">Identifier</th>
                            <th className="text-left p-3">Location</th>
                            <th className="text-right p-3">Value</th>
                            <th className="text-center p-3">Date Conveyed</th>
                            <th className="text-center p-3">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {categoryAssets.map(asset => (
                            <tr key={asset.item_id} className="border-t border-border">
                              <td className="p-3">
                                <p className="font-medium text-navy">{asset.description}</p>
                                {asset.notes && <p className="text-xs text-muted-foreground mt-1">{asset.notes}</p>}
                              </td>
                              <td className="p-3 font-mono text-sm">{asset.identifier || '—'}</td>
                              <td className="p-3 text-sm">{asset.location || '—'}</td>
                              <td className="p-3 text-right font-mono">{formatValue(asset.approximate_value)}</td>
                              <td className="p-3 text-center text-sm">
                                {formatDate(asset.date_conveyed)}
                              </td>
                              <td className="p-3 text-center">
                                <div className="flex justify-center gap-2">
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => handleEdit(asset)}
                                    data-testid={`edit-asset-${asset.item_id}`}
                                  >
                                    <Edit className="w-4 h-4" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="text-red-600 hover:text-red-700"
                                    onClick={() => handleDelete(asset.item_id)}
                                    data-testid={`delete-asset-${asset.item_id}`}
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </Button>
                                </div>
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
    </div>
  );
}
