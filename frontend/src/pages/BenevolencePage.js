import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
  HeartHandshake,
  Search,
  Filter,
  FileText,
  DollarSign,
  Calendar,
  User,
  Users,
  Building2,
  TrendingUp,
  Download
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const PURPOSE_OPTIONS = [
  { value: 'medical', label: 'Medical Expenses', icon: '🏥' },
  { value: 'housing', label: 'Housing Assistance', icon: '🏠' },
  { value: 'education', label: 'Education', icon: '📚' },
  { value: 'food_necessities', label: 'Food & Necessities', icon: '🍎' },
  { value: 'utilities', label: 'Utilities', icon: '💡' },
  { value: 'transportation', label: 'Transportation', icon: '🚗' },
  { value: 'emergency', label: 'Emergency Relief', icon: '🆘' },
  { value: 'spiritual', label: 'Spiritual/Ministry', icon: '✝️' },
  { value: 'other', label: 'Other', icon: '📋' }
];

const BENEFICIARY_TYPES = [
  { value: 'individual', label: 'Individual', icon: User },
  { value: 'family', label: 'Family', icon: Users },
  { value: 'organization', label: 'Organization', icon: Building2 }
];

export default function BenevolencePage() {
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  
  // Filters
  const [filterPurpose, setFilterPurpose] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  
  // View mode
  const [viewMode, setViewMode] = useState('list'); // list, summary
  
  // Form data
  const [formData, setFormData] = useState({
    beneficiary_name: '',
    beneficiary_type: 'individual',
    purpose: 'other',
    purpose_description: '',
    amount: '',
    date: new Date().toISOString().split('T')[0],
    approved_by: [],
    approval_method: 'unanimous',
    notes: '',
    status: 'approved'
  });

  useEffect(() => {
    if (selectedTrust?.benevolence_enabled) {
      loadRecords();
      loadSummary();
    }
  }, [selectedTrust]);

  const loadRecords = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      let url = `/benevolence?trust_id=${selectedTrust.trust_id}`;
      if (filterPurpose !== 'all') url += `&purpose=${filterPurpose}`;
      if (filterStatus !== 'all') url += `&status=${filterStatus}`;
      
      const response = await fetchWithAuth(url);
      if (response.ok) {
        setRecords(await response.json());
      }
    } catch (error) {
      console.error('Failed to load benevolence records:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadSummary = async () => {
    if (!selectedTrust) return;
    try {
      const response = await fetchWithAuth(`/benevolence/summary/${selectedTrust.trust_id}`);
      if (response.ok) {
        setSummary(await response.json());
      }
    } catch (error) {
      console.error('Failed to load summary:', error);
    }
  };

  useEffect(() => {
    if (selectedTrust?.benevolence_enabled) {
      loadRecords();
    }
  }, [filterPurpose, filterStatus]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormLoading(true);
    
    try {
      const payload = {
        ...formData,
        trust_id: selectedTrust.trust_id,
        amount: parseFloat(formData.amount) || 0,
        approved_by: formData.approved_by.length > 0 ? formData.approved_by : (selectedTrust.trustees || ['Trustee'])
      };
      
      const response = await fetchWithAuth('/benevolence', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (response.ok) {
        toast.success('Benevolence record created');
        setDialogOpen(false);
        resetForm();
        loadRecords();
        loadSummary();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to create record');
      }
    } catch (error) {
      toast.error('Failed to create record');
    } finally {
      setFormLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({
      beneficiary_name: '',
      beneficiary_type: 'individual',
      purpose: 'other',
      purpose_description: '',
      amount: '',
      date: new Date().toISOString().split('T')[0],
      approved_by: [],
      approval_method: 'unanimous',
      notes: '',
      status: 'approved'
    });
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value || 0);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const date = parseISO(dateStr);
      return format(date, 'MMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  const getPurposeLabel = (value) => {
    return PURPOSE_OPTIONS.find(p => p.value === value)?.label || value;
  };

  const getPurposeIcon = (value) => {
    return PURPOSE_OPTIONS.find(p => p.value === value)?.icon || '📋';
  };

  const filteredRecords = records.filter(r => {
    if (!searchTerm) return true;
    const search = searchTerm.toLowerCase();
    return (
      r.beneficiary_name.toLowerCase().includes(search) ||
      r.purpose_description.toLowerCase().includes(search) ||
      r.notes?.toLowerCase().includes(search)
    );
  });

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust p-8 text-center">
              <HeartHandshake className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
              <p className="text-muted-foreground">Select a trust to view benevolence records</p>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (!selectedTrust.benevolence_enabled) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust corner-mark p-8 text-center">
              <HeartHandshake className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
              <h2 className="font-serif text-2xl text-navy mb-2">Benevolence Mode Not Enabled</h2>
              <p className="text-muted-foreground mb-6">
                Benevolence tracking is available for 501/508-type charitable trusts.
                Enable it in your trust settings to start tracking benevolence grants.
              </p>
              <Button onClick={() => navigate('/settings')} className="btn-primary">
                Go to Settings
              </Button>
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
              <h1 className="font-serif text-3xl lg:text-4xl text-navy mb-2">Benevolence Log</h1>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                {selectedTrust.name} • Charitable Assistance Records
              </p>
            </div>
            <div className="flex gap-3 mt-4 md:mt-0">
              <Button
                variant="outline"
                onClick={() => navigate('/minutes/template/benevolence_approval')}
              >
                <FileText className="w-4 h-4 mr-2" />
                Create Minutes
              </Button>
              <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogTrigger asChild>
                  <Button className="btn-primary" data-testid="add-benevolence-btn">
                    <Plus className="w-4 h-4 mr-2" />
                    Record Grant
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle className="font-serif text-xl text-navy">Record Benevolence Grant</DialogTitle>
                  </DialogHeader>
                  <form onSubmit={handleSubmit} className="space-y-4 mt-4">
                    <div>
                      <Label className="label-trust">Beneficiary Name *</Label>
                      <Input
                        value={formData.beneficiary_name}
                        onChange={(e) => setFormData({ ...formData, beneficiary_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Name of recipient"
                        required
                      />
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label className="label-trust">Beneficiary Type</Label>
                        <Select value={formData.beneficiary_type} onValueChange={(v) => setFormData({ ...formData, beneficiary_type: v })}>
                          <SelectTrigger className="mt-1">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {BENEFICIARY_TYPES.map(type => (
                              <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="label-trust">Purpose Category</Label>
                        <Select value={formData.purpose} onValueChange={(v) => setFormData({ ...formData, purpose: v })}>
                          <SelectTrigger className="mt-1">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {PURPOSE_OPTIONS.map(p => (
                              <SelectItem key={p.value} value={p.value}>{p.icon} {p.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    
                    <div>
                      <Label className="label-trust">Purpose Description *</Label>
                      <Textarea
                        value={formData.purpose_description}
                        onChange={(e) => setFormData({ ...formData, purpose_description: e.target.value })}
                        className="mt-1"
                        placeholder="Describe the need and how assistance will help"
                        rows={2}
                        required
                      />
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label className="label-trust">Amount *</Label>
                        <Input
                          type="number"
                          value={formData.amount}
                          onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="0.00"
                          required
                        />
                      </div>
                      <div>
                        <Label className="label-trust">Date *</Label>
                        <Input
                          type="date"
                          value={formData.date}
                          onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                          className="mt-1 input-trust"
                          required
                        />
                      </div>
                    </div>
                    
                    <div>
                      <Label className="label-trust">Approval Method</Label>
                      <Select value={formData.approval_method} onValueChange={(v) => setFormData({ ...formData, approval_method: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="unanimous">Unanimous Approval</SelectItem>
                          <SelectItem value="majority">Majority Vote</SelectItem>
                          <SelectItem value="single_trustee">Single Trustee (within authority)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <div>
                      <Label className="label-trust">Internal Notes</Label>
                      <Textarea
                        value={formData.notes}
                        onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                        className="mt-1"
                        placeholder="Internal notes (not included in formal records)"
                        rows={2}
                      />
                    </div>
                    
                    <div className="flex justify-end gap-3 pt-4">
                      <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                        Cancel
                      </Button>
                      <Button type="submit" className="btn-primary" disabled={formLoading}>
                        {formLoading ? 'Saving...' : 'Record Grant'}
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
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Total Grants</p>
                <p className="font-serif text-2xl text-navy">{summary.total_count}</p>
              </div>
              <div className="card-trust p-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Total Amount</p>
                <p className="font-serif text-2xl text-navy">{formatCurrency(summary.total_amount)}</p>
              </div>
              <div className="card-trust p-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">This Year</p>
                <p className="font-serif text-2xl text-navy">
                  {formatCurrency(summary.by_year?.[new Date().getFullYear().toString()]?.total || 0)}
                </p>
              </div>
              <div className="card-trust p-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Categories</p>
                <p className="font-serif text-2xl text-navy">{Object.keys(summary.by_purpose || {}).length}</p>
              </div>
            </div>
          )}

          {/* View Toggle & Filters */}
          <div className="flex flex-col md:flex-row gap-4 mb-6">
            <div className="flex gap-2">
              <Button
                variant={viewMode === 'list' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('list')}
              >
                List View
              </Button>
              <Button
                variant={viewMode === 'summary' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('summary')}
              >
                Summary
              </Button>
            </div>
            
            {viewMode === 'list' && (
              <div className="flex flex-1 gap-3">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Search grants..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-9 input-trust"
                  />
                </div>
                <Select value={filterPurpose} onValueChange={setFilterPurpose}>
                  <SelectTrigger className="w-40">
                    <SelectValue placeholder="Purpose" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Purposes</SelectItem>
                    {PURPOSE_OPTIONS.map(p => (
                      <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={filterStatus} onValueChange={setFilterStatus}>
                  <SelectTrigger className="w-32">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="approved">Approved</SelectItem>
                    <SelectItem value="disbursed">Disbursed</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* Content */}
          {viewMode === 'list' ? (
            loading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => (
                  <div key={i} className="card-trust p-4 animate-pulse">
                    <div className="h-5 bg-muted rounded w-1/3 mb-2"></div>
                    <div className="h-4 bg-muted rounded w-2/3"></div>
                  </div>
                ))}
              </div>
            ) : filteredRecords.length === 0 ? (
              <div className="card-trust corner-mark p-12 text-center">
                <HeartHandshake className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
                <h3 className="font-serif text-xl text-navy mb-2">No Benevolence Records</h3>
                <p className="text-muted-foreground mb-6">
                  Start tracking charitable assistance grants for your trust.
                </p>
                <Button className="btn-primary" onClick={() => setDialogOpen(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  Record First Grant
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredRecords.map(record => (
                  <div key={record.record_id} className="card-trust p-4 hover:border-gold transition-colors">
                    <div className="flex items-start justify-between">
                      <div className="flex items-start gap-4">
                        <div className="w-10 h-10 bg-gold/20 flex items-center justify-center text-xl">
                          {getPurposeIcon(record.purpose)}
                        </div>
                        <div>
                          <h3 className="font-medium text-navy">{record.beneficiary_name}</h3>
                          <p className="text-sm text-muted-foreground">{record.purpose_description}</p>
                          <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                            <span className="flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              {formatDate(record.date)}
                            </span>
                            <span className="capitalize">{record.beneficiary_type}</span>
                            <span className="capitalize">{getPurposeLabel(record.purpose)}</span>
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-lg text-navy">{formatCurrency(record.amount)}</p>
                        <span className={`text-xs px-2 py-0.5 ${
                          record.status === 'disbursed' ? 'bg-green-100 text-green-700' :
                          record.status === 'approved' ? 'bg-blue-100 text-blue-700' :
                          'bg-yellow-100 text-yellow-700'
                        }`}>
                          {record.status}
                        </span>
                      </div>
                    </div>
                    {record.notes && (
                      <p className="mt-3 text-xs text-muted-foreground italic border-t pt-3">
                        Note: {record.notes}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )
          ) : (
            /* Summary View */
            summary && (
              <div className="grid md:grid-cols-2 gap-6">
                {/* By Purpose */}
                <div className="card-trust p-6">
                  <h3 className="font-serif text-lg text-navy mb-4">By Purpose Category</h3>
                  <div className="space-y-3">
                    {Object.entries(summary.by_purpose || {}).map(([purpose, data]) => (
                      <div key={purpose} className="flex items-center justify-between p-2 bg-muted/30">
                        <div className="flex items-center gap-2">
                          <span>{getPurposeIcon(purpose)}</span>
                          <span className="text-sm">{getPurposeLabel(purpose)}</span>
                          <span className="text-xs text-muted-foreground">({data.count})</span>
                        </div>
                        <span className="font-mono text-sm">{formatCurrency(data.total)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* By Quarter */}
                <div className="card-trust p-6">
                  <h3 className="font-serif text-lg text-navy mb-4">By Quarter</h3>
                  <div className="space-y-3">
                    {Object.entries(summary.by_quarter || {}).slice(0, 8).map(([quarter, data]) => (
                      <div key={quarter} className="flex items-center justify-between p-2 bg-muted/30">
                        <div className="flex items-center gap-2">
                          <TrendingUp className="w-4 h-4 text-navy" />
                          <span className="text-sm font-mono">{quarter}</span>
                          <span className="text-xs text-muted-foreground">({data.count} grants)</span>
                        </div>
                        <span className="font-mono text-sm">{formatCurrency(data.total)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* By Year */}
                <div className="card-trust p-6">
                  <h3 className="font-serif text-lg text-navy mb-4">By Year</h3>
                  <div className="space-y-3">
                    {Object.entries(summary.by_year || {}).map(([year, data]) => (
                      <div key={year} className="flex items-center justify-between p-2 bg-muted/30">
                        <div className="flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-navy" />
                          <span className="text-sm font-mono">{year}</span>
                          <span className="text-xs text-muted-foreground">({data.count} grants)</span>
                        </div>
                        <span className="font-mono text-sm">{formatCurrency(data.total)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Approvers */}
                <div className="card-trust p-6">
                  <h3 className="font-serif text-lg text-navy mb-4">Approvers</h3>
                  <div className="flex flex-wrap gap-2">
                    {(summary.approvers || []).map(approver => (
                      <span key={approver} className="px-3 py-1 bg-navy/10 text-navy text-sm">
                        {approver}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )
          )}
        </div>
      </main>
    </div>
  );
}
