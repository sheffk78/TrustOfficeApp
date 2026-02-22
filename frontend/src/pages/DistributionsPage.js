import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { fetchWithAuth, API } from '@/utils/api';
import { 
  Plus, 
  Search,
  Calendar as CalendarIcon,
  DollarSign,
  Filter,
  Check,
  X,
  Clock
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

export default function DistributionsPage() {
  const { selectedTrust } = useAuth();
  const [distributions, setDistributions] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  
  // Approval modal state
  const [approvalModal, setApprovalModal] = useState(null);
  const [solvencyConfirmed, setSolvencyConfirmed] = useState(false);
  const [recusalAcknowledged, setRecusalAcknowledged] = useState(false);
  const [approvalLoading, setApprovalLoading] = useState(false);
  
  const [formData, setFormData] = useState({
    date: new Date(),
    amount: '',
    distribution_type: 'trust_distribution',
    beneficiary: '',
    category: '',
    notes: '',
    status: 'review'
  });

  useEffect(() => {
    loadCategories();
  }, []);

  useEffect(() => {
    if (selectedTrust) {
      loadDistributions();
    }
  }, [selectedTrust]);

  const loadCategories = async () => {
    try {
      const response = await fetch(`${API}/categories`);
      if (response.ok) {
        const data = await response.json();
        // Use purpose_classifications from backend
        setCategories(data.purpose_classifications || data.distribution_categories || []);
      }
    } catch (error) {
      console.error('Failed to load categories:', error);
    }
  };

  const loadDistributions = async () => {
    if (!selectedTrust) return;
    
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/distributions?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        setDistributions(await response.json());
      }
    } catch (error) {
      console.error('Failed to load distributions:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateDistribution = async () => {
    if (!selectedTrust) {
      toast.error('Please select a trust first');
      return;
    }

    if (!formData.amount || !formData.beneficiary || !formData.category) {
      toast.error('Please fill in all required fields');
      return;
    }

    setFormLoading(true);
    try {
      const response = await fetchWithAuth('/distributions', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          beneficiary_name: formData.beneficiary,
          amount: parseFloat(formData.amount),
          date: formData.date.toISOString().split('T')[0],
          purpose_classification: formData.category,
          notes: formData.notes || ''
        })
      });

      if (!response.ok) {
        throw new Error('Failed to create distribution');
      }

      toast.success('Distribution created');
      setDialogOpen(false);
      setFormData({
        date: new Date(),
        amount: '',
        distribution_type: 'trust_distribution',
        beneficiary: '',
        category: '',
        notes: '',
        status: 'review'
      });
      loadDistributions();
    } catch (error) {
      toast.error(error.message);
    } finally {
      setFormLoading(false);
    }
  };

  const handleUpdateStatus = async (distributionId, newStatus) => {
    try {
      const response = await fetchWithAuth(`/distributions/${distributionId}?status=${newStatus}`, {
        method: 'PUT'
      });

      if (!response.ok) {
        throw new Error('Failed to update status');
      }

      toast.success(`Status updated to ${newStatus}`);
      loadDistributions();
    } catch (error) {
      toast.error(error.message);
    }
  };

  const formatDate = (dateString) => {
    try {
      return format(parseISO(dateString), 'MMM d, yyyy');
    } catch {
      return dateString;
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(amount);
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'approved': return 'badge-success';
      case 'review': return 'badge-warning';
      case 'declined': return 'badge-error';
      default: return '';
    }
  };

  const filteredDistributions = distributions.filter(d => {
    const beneficiary = d.beneficiary_name || d.beneficiary || '';
    const category = d.purpose_classification || d.category || '';
    const status = d.approved_at ? 'approved' : 'review';
    const matchesSearch = 
      beneficiary.toLowerCase().includes(searchTerm.toLowerCase()) ||
      category.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (d.notes && d.notes.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesStatus = filterStatus === 'all' || status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  const totalAmount = filteredDistributions.reduce((sum, d) => sum + d.amount, 0);
  const pendingCount = distributions.filter(d => !d.approved_at).length;

  return (
    <div className="main-layout" data-testid="distributions-page">
      <Sidebar />
      <main className="main-content">
        <div className="page-container">
          {/* Page Header */}
          <div className="flex items-start justify-between mb-8">
            <div>
              <h1 className="page-title">Distributions</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'}
              </p>
            </div>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button className="btn-primary" data-testid="add-distribution-btn">
                  <Plus className="w-4 h-4 mr-2" />
                  Add Distribution
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                  <DialogTitle className="font-serif text-2xl text-navy">New Distribution</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 mt-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Date *</Label>
                      <Popover>
                        <PopoverTrigger asChild>
                          <Button
                            variant="outline"
                            className="w-full justify-start text-left font-mono input-trust mt-1"
                            data-testid="dist-date-picker"
                          >
                            <CalendarIcon className="mr-2 h-4 w-4" />
                            {format(formData.date, 'MMM d, yyyy')}
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0" align="start">
                          <Calendar
                            mode="single"
                            selected={formData.date}
                            onSelect={(date) => setFormData({ ...formData, date: date || new Date() })}
                          />
                        </PopoverContent>
                      </Popover>
                    </div>
                    <div>
                      <Label className="label-trust">Amount *</Label>
                      <div className="relative mt-1">
                        <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <Input
                          type="number"
                          step="0.01"
                          value={formData.amount}
                          onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                          className="pl-10 input-trust"
                          placeholder="0.00"
                          data-testid="dist-amount-input"
                        />
                      </div>
                    </div>
                  </div>

                  <div>
                    <Label className="label-trust">Beneficiary *</Label>
                    <Input
                      value={formData.beneficiary}
                      onChange={(e) => setFormData({ ...formData, beneficiary: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="Beneficiary name"
                      data-testid="dist-beneficiary-input"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Type</Label>
                      <Select 
                        value={formData.distribution_type} 
                        onValueChange={(value) => setFormData({ ...formData, distribution_type: value })}
                      >
                        <SelectTrigger className="mt-1 input-trust" data-testid="dist-type-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="trust_distribution">Trust Distribution</SelectItem>
                          <SelectItem value="loan">Loan</SelectItem>
                          <SelectItem value="gift">Gift</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Category *</Label>
                      <Select 
                        value={formData.category} 
                        onValueChange={(value) => setFormData({ ...formData, category: value })}
                      >
                        <SelectTrigger className="mt-1 input-trust" data-testid="dist-category-select">
                          <SelectValue placeholder="Select category" />
                        </SelectTrigger>
                        <SelectContent>
                          {categories.map((cat) => (
                            <SelectItem key={cat} value={cat}>{cat}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div>
                    <Label className="label-trust">Status</Label>
                    <Select 
                      value={formData.status} 
                      onValueChange={(value) => setFormData({ ...formData, status: value })}
                    >
                      <SelectTrigger className="mt-1 input-trust" data-testid="dist-status-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="review">Pending Review</SelectItem>
                        <SelectItem value="approved">Approved</SelectItem>
                        <SelectItem value="declined">Declined</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="label-trust">Notes</Label>
                    <Textarea
                      value={formData.notes}
                      onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="Additional notes..."
                      data-testid="dist-notes-input"
                    />
                  </div>

                  <Button
                    onClick={handleCreateDistribution}
                    disabled={formLoading}
                    className="w-full btn-primary"
                    data-testid="submit-distribution-btn"
                  >
                    {formLoading ? 'Creating...' : 'Create Distribution'}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="card-trust">
              <p className="label-trust">Total Distributed</p>
              <p className="font-mono text-3xl text-navy mt-2">{formatCurrency(totalAmount)}</p>
            </div>
            <div className="card-trust">
              <p className="label-trust">Total Records</p>
              <p className="font-mono text-3xl text-navy mt-2">{distributions.length}</p>
            </div>
            <div className="card-trust">
              <p className="label-trust">Pending Review</p>
              <p className="font-mono text-3xl text-warning mt-2">{pendingCount}</p>
            </div>
          </div>

          {/* Filters */}
          <div className="card-trust mb-6">
            <div className="flex flex-col md:flex-row gap-4">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search distributions..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10 input-trust"
                  data-testid="search-distributions"
                />
              </div>
              <div className="flex gap-2">
                {['all', 'approved', 'review', 'declined'].map((status) => (
                  <button
                    key={status}
                    onClick={() => setFilterStatus(status)}
                    className={`px-4 py-2 font-mono text-xs uppercase tracking-widest border ${
                      filterStatus === status 
                        ? 'bg-navy text-white border-navy' 
                        : 'bg-white text-navy border-navy/20 hover:border-navy'
                    }`}
                    data-testid={`filter-${status}`}
                  >
                    {status === 'all' ? 'All' : status}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Table */}
          {loading ? (
            <div className="card-trust">
              <div className="skeleton h-8 w-full mb-4"></div>
              <div className="skeleton h-12 w-full mb-2"></div>
              <div className="skeleton h-12 w-full mb-2"></div>
              <div className="skeleton h-12 w-full"></div>
            </div>
          ) : filteredDistributions.length === 0 ? (
            <div className="empty-state">
              <DollarSign className="w-16 h-16 text-navy/20 mx-auto mb-4" />
              <h2 className="font-serif text-2xl text-navy mb-2">No Distributions Found</h2>
              <p className="text-muted-foreground mb-6">
                {searchTerm ? 'Try a different search term' : 'Add your first distribution to get started'}
              </p>
              <Button onClick={() => setDialogOpen(true)} className="btn-primary">
                Add Distribution
              </Button>
            </div>
          ) : (
            <div className="card-trust overflow-x-auto">
              <table className="w-full trust-table">
                <thead>
                  <tr>
                    <th className="text-left">Date</th>
                    <th className="text-left">Beneficiary</th>
                    <th className="text-left">Category</th>
                    <th className="text-right">Amount</th>
                    <th className="text-center">Status</th>
                    <th className="text-center">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDistributions.map((dist) => {
                    const status = dist.approved_at ? 'approved' : 'review';
                    return (
                    <tr key={dist.distribution_id} data-testid={`dist-row-${dist.distribution_id}`}>
                      <td>{formatDate(dist.date)}</td>
                      <td>{dist.beneficiary_name || dist.beneficiary || '-'}</td>
                      <td>{dist.purpose_classification || dist.category || '-'}</td>
                      <td className="text-right font-mono">{formatCurrency(dist.amount)}</td>
                      <td className="text-center">
                        <span className={`badge-trust ${getStatusBadgeClass(status)}`}>
                          {status}
                        </span>
                      </td>
                      <td className="text-center">
                        {status === 'review' && (
                          <div className="flex justify-center gap-2">
                            <button
                              onClick={() => handleUpdateStatus(dist.distribution_id, 'approved')}
                              className="p-1 hover:bg-success/10 text-success"
                              title="Approve"
                              data-testid={`approve-${dist.distribution_id}`}
                            >
                              <Check className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleUpdateStatus(dist.distribution_id, 'declined')}
                              className="p-1 hover:bg-error/10 text-error"
                              title="Decline"
                              data-testid={`decline-${dist.distribution_id}`}
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        )}
                        {status !== 'review' && (
                          <button
                            onClick={() => handleUpdateStatus(dist.distribution_id, 'review')}
                            className="p-1 hover:bg-warning/10 text-warning"
                            title="Set to Review"
                          >
                            <Clock className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  )})}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
