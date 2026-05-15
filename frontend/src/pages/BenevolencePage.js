import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { AttachMinutesDialog } from '@/components/AttachMinutesDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import { 
  Plus, 
  HeartHandshake,
  Search,
  DollarSign,
  Calendar,
  User,
  Users,
  Building2,
  TrendingUp,
  Download,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  Filter,
  X,
  MoreVertical,
  Link2,
  FileText
} from 'lucide-react';
import { format, parseISO, startOfMonth, endOfMonth, startOfYear, endOfYear, subDays } from 'date-fns';

const PURPOSE_OPTIONS = [
  { value: 'medical', label: 'Medical Expenses' },
  { value: 'housing', label: 'Housing Assistance' },
  { value: 'education', label: 'Education' },
  { value: 'food_necessities', label: 'Food & Necessities' },
  { value: 'utilities', label: 'Utilities' },
  { value: 'transportation', label: 'Transportation' },
  { value: 'emergency', label: 'Emergency Relief' },
  { value: 'spiritual', label: 'Spiritual/Ministry' },
  { value: 'other', label: 'Other' }
];

const BENEFICIARY_TYPES = [
  { value: 'individual', label: 'Individual', icon: User },
  { value: 'family', label: 'Family', icon: Users },
  { value: 'organization', label: 'Organization', icon: Building2 }
];

const DATE_FILTER_OPTIONS = [
  { value: 'all', label: 'All History' },
  { value: 'last_30', label: 'Last 30 Days' },
  { value: 'this_month', label: 'This Month' },
  { value: 'last_month', label: 'Last Month' },
  { value: 'this_year', label: 'This Year' },
  { value: 'last_year', label: 'Last Year' }
];

export default function BenevolencePage() {
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  
  // Unified log state
  const [allRecords, setAllRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Filters
  const [dateFilter, setDateFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [purposeFilter, setPurposeFilter] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  
  // Modal states
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  
  // Attach minutes dialog state
  const [attachMinutesDialog, setAttachMinutesDialog] = useState({ open: false, recordId: null });
  
  // Form data for new benevolence grant
  const [formData, setFormData] = useState({
    beneficiary_name: '',
    beneficiary_type: 'individual',
    purpose: 'other',
    purpose_description: '',
    amount: '',
    date: format(new Date(), 'yyyy-MM-dd'),
    approved_by: [],
    approval_method: 'unanimous',
    notes: '',
    status: 'approved'
  });

  // Load all benevolence data on mount
  useEffect(() => {
    if (selectedTrust?.benevolence_enabled) {
      loadAllData();
    }
  }, [selectedTrust]);

  const loadAllData = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    
    try {
      // Load from both sources in parallel
      const [recordsRes, logRes, summaryRes] = await Promise.all([
        fetchWithAuth(`/benevolence?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/benevolence-log?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/benevolence/summary/${selectedTrust.trust_id}`)
      ]);
      
      let combinedRecords = [];
      
      // Get benevolence_records (grants)
      if (recordsRes.ok) {
        const grants = await recordsRes.json();
        combinedRecords = grants.map(g => ({
          ...g,
          id: g.record_id,
          source: 'grant',
          recipient_name: g.beneficiary_name,
          description: g.purpose_description || g.notes,
          category: g.purpose,
          is_documented: g.status === 'approved'
        }));
      }
      
      // Get benevolence distributions (from distribution_records with is_benevolence=true)
      if (logRes.ok) {
        const logData = await logRes.json();
        const distributions = (logData.distributions || []).map(d => ({
          ...d,
          id: d.distribution_id,
          source: 'distribution',
          recipient_name: d.benevolence_recipient_name || d.beneficiary_name,
          description: d.benevolence_need_description || d.notes,
          category: d.benevolence_category || 'other',
          is_documented: !!(d.approved_at || d.minutes_record_id)
        }));
        
        // Merge, avoiding duplicates by checking amount+date+recipient
        distributions.forEach(dist => {
          const isDuplicate = combinedRecords.some(r => 
            r.amount === dist.amount && 
            r.date === dist.date && 
            r.recipient_name?.toLowerCase() === dist.recipient_name?.toLowerCase()
          );
          if (!isDuplicate) {
            combinedRecords.push(dist);
          }
        });
      }
      
      // Sort by date descending
      combinedRecords.sort((a, b) => new Date(b.date) - new Date(a.date));
      setAllRecords(combinedRecords);
      
      // Get summary
      if (summaryRes.ok) {
        setSummary(await summaryRes.json());
      }
    } catch (error) {
      console.error('Failed to load benevolence data:', error);
      toast.error('Failed to load benevolence records');
    } finally {
      setLoading(false);
    }
  }, [selectedTrust]);

  // Filter records based on current filters
  const getFilteredRecords = useCallback(() => {
    let filtered = [...allRecords];
    
    // Date filter
    const now = new Date();
    if (dateFilter === 'last_30') {
      const cutoff = subDays(now, 30);
      filtered = filtered.filter(r => new Date(r.date) >= cutoff);
    } else if (dateFilter === 'this_month') {
      const monthStart = startOfMonth(now);
      const monthEnd = endOfMonth(now);
      filtered = filtered.filter(r => {
        const d = new Date(r.date);
        return d >= monthStart && d <= monthEnd;
      });
    } else if (dateFilter === 'last_month') {
      const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const monthStart = startOfMonth(lastMonth);
      const monthEnd = endOfMonth(lastMonth);
      filtered = filtered.filter(r => {
        const d = new Date(r.date);
        return d >= monthStart && d <= monthEnd;
      });
    } else if (dateFilter === 'this_year') {
      const yearStart = startOfYear(now);
      const yearEnd = endOfYear(now);
      filtered = filtered.filter(r => {
        const d = new Date(r.date);
        return d >= yearStart && d <= yearEnd;
      });
    } else if (dateFilter === 'last_year') {
      const lastYear = new Date(now.getFullYear() - 1, 0, 1);
      const yearStart = startOfYear(lastYear);
      const yearEnd = endOfYear(lastYear);
      filtered = filtered.filter(r => {
        const d = new Date(r.date);
        return d >= yearStart && d <= yearEnd;
      });
    }
    
    // Search filter (recipient name)
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(r => 
        r.recipient_name?.toLowerCase().includes(term) ||
        r.description?.toLowerCase().includes(term)
      );
    }
    
    // Purpose filter
    if (purposeFilter !== 'all') {
      filtered = filtered.filter(r => r.category === purposeFilter || r.purpose === purposeFilter);
    }
    
    return filtered;
  }, [allRecords, dateFilter, searchTerm, purposeFilter]);

  const filteredRecords = getFilteredRecords();

  // Calculate summary stats based on current filter
  const getFilteredStats = useCallback(() => {
    const records = filteredRecords;
    const total = records.reduce((sum, r) => sum + (r.amount || 0), 0);
    const count = records.length;
    const documented = records.filter(r => r.is_documented).length;
    return { total, count, documented, pending: count - documented };
  }, [filteredRecords]);

  const filteredStats = getFilteredStats();

  // Real summary stats (all time)
  const allTimeTotal = allRecords.reduce((sum, r) => sum + (r.amount || 0), 0);
  const thisYearRecords = allRecords.filter(r => new Date(r.date).getFullYear() === new Date().getFullYear());
  const thisYearTotal = thisYearRecords.reduce((sum, r) => sum + (r.amount || 0), 0);
  const thisMonthRecords = allRecords.filter(r => {
    const d = new Date(r.date);
    const now = new Date();
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  });
  const thisMonthTotal = thisMonthRecords.reduce((sum, r) => sum + (r.amount || 0), 0);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.beneficiary_name || !formData.amount) {
      toast.error('Recipient name and amount are required');
      return;
    }
    
    setFormLoading(true);
    try {
      const payload = {
        ...formData,
        trust_id: selectedTrust.trust_id,
        amount: parseFloat(formData.amount) || 0,
        approved_by: formData.approved_by.length > 0 ? formData.approved_by : ['Trustee']
      };
      
      const response = await fetchWithAuth('/benevolence', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (response.ok) {
        toast.success('Benevolence grant recorded');
        setDialogOpen(false);
        resetForm();
        loadAllData();
      } else {
        const error = await response.json().catch(() => ({}));
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
      date: format(new Date(), 'yyyy-MM-dd'),
      approved_by: [],
      approval_method: 'unanimous',
      notes: '',
      status: 'approved'
    });
  };

  const clearFilters = () => {
    setDateFilter('all');
    setSearchTerm('');
    setPurposeFilter('all');
  };

  const hasActiveFilters = dateFilter !== 'all' || searchTerm || purposeFilter !== 'all';

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(amount || 0);
  };

  const formatDate = (dateString) => {
    try {
      return format(parseISO(dateString), 'MMM d, yyyy');
    } catch {
      return dateString;
    }
  };

  const getPurposeLabel = (purpose) => {
    const opt = PURPOSE_OPTIONS.find(p => p.value === purpose);
    return opt?.label || purpose || 'Other';
  };

  // Not enabled state
  if (!selectedTrust?.benevolence_enabled) {
    return (
      <div className="main-layout" data-testid="benevolence-page">
        <Sidebar />
        <main className="main-content dot-grid">
          <div className="page-container">
            <div className="card-trust p-8 text-center">
              <HeartHandshake className="w-12 h-12 text-navy/30 mx-auto mb-4" />
              <h2 className="font-serif text-xl text-navy mb-2">Benevolence Not Enabled</h2>
              <p className="text-muted-foreground mb-4">
                Enable benevolence tracking in Trust Settings to record charitable assistance.
              </p>
              <Button onClick={() => window.location.href = '/settings'} className="btn-secondary">
                Go to Settings
              </Button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="main-layout" data-testid="benevolence-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
            <div>
              <h1 className="page-title">Benevolence Log</h1>
              <p className="page-subtitle">
                {selectedTrust?.name} • Charitable Assistance Tracking
              </p>
            </div>
            <div className="flex gap-3 mt-4 md:mt-0">
              <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogTrigger asChild>
                  <Button className="btn-primary" data-testid="record-grant-btn">
                    <Plus className="w-4 h-4 mr-2" />
                    Record Grant
                  </Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-lg" data-testid="grant-modal">
                  <DialogHeader>
                    <DialogTitle className="font-serif text-xl text-navy">Record Benevolence Grant</DialogTitle>
                  </DialogHeader>
                  <form onSubmit={handleSubmit} className="space-y-4 py-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="col-span-2">
                        <Label className="label-trust">Recipient Name *</Label>
                        <Input
                          value={formData.beneficiary_name}
                          onChange={(e) => setFormData({ ...formData, beneficiary_name: e.target.value })}
                          placeholder="Enter recipient name"
                          className="input-trust mt-1"
                          data-testid="recipient-name"
                          required
                        />
                      </div>
                      <div>
                        <Label className="label-trust">Recipient Type</Label>
                        <Select value={formData.beneficiary_type} onValueChange={(v) => setFormData({ ...formData, beneficiary_type: v })}>
                          <SelectTrigger className="input-trust mt-1">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {BENEFICIARY_TYPES.map(t => (
                              <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="label-trust">Purpose/Category</Label>
                        <Select value={formData.purpose} onValueChange={(v) => setFormData({ ...formData, purpose: v })}>
                          <SelectTrigger className="input-trust mt-1">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {PURPOSE_OPTIONS.map(p => (
                              <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="label-trust">Amount *</Label>
                        <Input
                          type="number"
                          value={formData.amount}
                          onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                          placeholder="0.00"
                          className="input-trust mt-1"
                          data-testid="grant-amount"
                          required
                        />
                      </div>
                      <div>
                        <Label className="label-trust">Date</Label>
                        <Input
                          type="date"
                          value={formData.date}
                          onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                          className="input-trust mt-1"
                        />
                      </div>
                      <div className="col-span-2">
                        <Label className="label-trust">Description / Need</Label>
                        <Textarea
                          value={formData.purpose_description}
                          onChange={(e) => setFormData({ ...formData, purpose_description: e.target.value })}
                          placeholder="Describe the need or purpose of this grant..."
                          className="input-trust mt-1"
                          rows={2}
                        />
                      </div>
                      <div className="col-span-2">
                        <Label className="label-trust">Notes (Optional)</Label>
                        <Textarea
                          value={formData.notes}
                          onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                          placeholder="Any additional notes..."
                          className="input-trust mt-1"
                          rows={2}
                        />
                      </div>
                    </div>
                    <DialogFooter>
                      <Button type="button" variant="outline" onClick={() => setDialogOpen(false)} className="btn-secondary">
                        Cancel
                      </Button>
                      <Button type="submit" disabled={formLoading} className="btn-primary" data-testid="submit-grant-btn">
                        {formLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                        Record Grant
                      </Button>
                    </DialogFooter>
                  </form>
                </DialogContent>
              </Dialog>
            </div>
          </div>

          {/* Summary Strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="card-trust p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gold/20 flex items-center justify-center">
                  <Calendar className="w-5 h-5 text-gold" />
                </div>
                <div>
                  <p className="label-trust">This Month</p>
                  <p className="font-serif text-xl text-navy">{formatCurrency(thisMonthTotal)}</p>
                </div>
              </div>
            </div>
            <div className="card-trust p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-blue-700 dark:text-blue-400" />
                </div>
                <div>
                  <p className="label-trust">This Year</p>
                  <p className="font-serif text-xl text-navy">{formatCurrency(thisYearTotal)}</p>
                </div>
              </div>
            </div>
            <div className="card-trust p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                  <HeartHandshake className="w-5 h-5 text-green-700 dark:text-green-400" />
                </div>
                <div>
                  <p className="label-trust">All Time</p>
                  <p className="font-serif text-xl text-navy">{formatCurrency(allTimeTotal)}</p>
                </div>
              </div>
            </div>
            <div className="card-trust p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-navy/10 flex items-center justify-center">
                  <DollarSign className="w-5 h-5 text-navy" />
                </div>
                <div>
                  <p className="label-trust">Total Grants</p>
                  <p className="font-serif text-xl text-navy">{allRecords.length}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Filters */}
          <div className="card-trust mb-6">
            <div className="p-4">
              <div className="flex flex-col sm:flex-row gap-4">
                {/* Search */}
                <div className="flex-1">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      placeholder="Search by recipient..."
                      className="pl-10 input-trust"
                      data-testid="search-recipient"
                    />
                  </div>
                </div>
                
                {/* Date Filter */}
                <div className="w-full sm:w-48">
                  <Select value={dateFilter} onValueChange={setDateFilter}>
                    <SelectTrigger className="input-trust" data-testid="date-filter">
                      <Calendar className="w-4 h-4 mr-2 text-muted-foreground" />
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {DATE_FILTER_OPTIONS.map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                
                {/* Purpose Filter */}
                <div className="w-full sm:w-48">
                  <Select value={purposeFilter} onValueChange={setPurposeFilter}>
                    <SelectTrigger className="input-trust" data-testid="purpose-filter">
                      <Filter className="w-4 h-4 mr-2 text-muted-foreground" />
                      <SelectValue placeholder="All Categories" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Categories</SelectItem>
                      {PURPOSE_OPTIONS.map(p => (
                        <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                
                {/* Clear Filters */}
                {hasActiveFilters && (
                  <Button variant="ghost" onClick={clearFilters} className="text-muted-foreground hover:text-navy">
                    <X className="w-4 h-4 mr-1" /> Clear
                  </Button>
                )}
              </div>
              
              {/* Active filter indicator */}
              {hasActiveFilters && (
                <div className="mt-3 pt-3 border-t border-border">
                  <p className="text-sm text-muted-foreground">
                    Showing {filteredRecords.length} of {allRecords.length} records
                    {dateFilter !== 'all' && ` • ${DATE_FILTER_OPTIONS.find(o => o.value === dateFilter)?.label}`}
                    {purposeFilter !== 'all' && ` • ${getPurposeLabel(purposeFilter)}`}
                    {searchTerm && ` • Matching "${searchTerm}"`}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Records List */}
          <div className="card-trust">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <HeartHandshake className="w-4 h-4 text-navy" />
                <span className="label-trust">Benevolence Records</span>
              </div>
              <span className="text-sm text-muted-foreground">{filteredRecords.length} records</span>
            </div>

            {loading ? (
              <div className="p-8 text-center">
                <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4 text-navy" />
                <p className="label-trust">Loading benevolence records...</p>
              </div>
            ) : filteredRecords.length === 0 ? (
              <div className="p-8 text-center" data-testid="empty-state">
                <HeartHandshake className="w-12 h-12 text-navy/20 mx-auto mb-4" />
                {allRecords.length === 0 ? (
                  <>
                    <h3 className="font-serif text-lg text-navy mb-2">No Benevolence Records Yet</h3>
                    <p className="text-muted-foreground mb-4">
                      Record your first benevolence grant to start tracking charitable assistance.
                    </p>
                    <Button onClick={() => setDialogOpen(true)} className="btn-secondary">
                      Record First Grant
                    </Button>
                  </>
                ) : (
                  <>
                    <h3 className="font-serif text-lg text-navy mb-2">No Records Match Filters</h3>
                    <p className="text-muted-foreground mb-4">
                      No benevolence records match these filters. Try broadening your date range or clearing filters.
                    </p>
                    <Button onClick={clearFilters} className="btn-secondary">
                      Clear All Filters
                    </Button>
                  </>
                )}
              </div>
            ) : (
              <div className="divide-y divide-border">
                {filteredRecords.map((record) => (
                  <div 
                    key={record.id} 
                    className="p-4 hover:bg-muted/30 transition-colors"
                    data-testid={`benevolence-record-${record.id}`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="font-medium text-navy truncate">
                            {record.recipient_name || 'Unknown Recipient'}
                          </p>
                          {record.is_documented ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono uppercase bg-success/10 text-success">
                              <CheckCircle2 className="w-3 h-3" /> Documented
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono uppercase bg-warning/10 text-warning">
                              <Clock className="w-3 h-3" /> Pending
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                          <span>{formatDate(record.date)}</span>
                          <span className="text-navy/30">•</span>
                          <span>{getPurposeLabel(record.category || record.purpose)}</span>
                          {record.description && (
                            <>
                              <span className="text-navy/30">•</span>
                              <span className="truncate max-w-[200px]">{record.description}</span>
                            </>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        {/* Minutes Actions */}
                        {!record.is_documented && record.source_type === 'benevolence' && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="sm" data-testid={`minutes-menu-${record.id}`}>
                                <MoreVertical className="w-4 h-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setAttachMinutesDialog({ open: true, recordId: record.id })}>
                                <Link2 className="w-4 h-4 mr-2" />
                                Link to existing minutes
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => {
                                const params = new URLSearchParams({
                                  prefill_type: 'benevolence',
                                  prefill_amount: record.amount.toString(),
                                  prefill_recipient: record.recipient_name || '',
                                  prefill_description: record.description || record.category || ''
                                });
                                navigate(`/minutes/create?${params.toString()}`);
                              }}>
                                <FileText className="w-4 h-4 mr-2" />
                                Document in minutes (retroactive)
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                        <div className="text-right">
                          <p className="font-mono text-lg text-navy">{formatCurrency(record.amount)}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
      <MobileBottomNav />

      {/* Attach Minutes Dialog */}
      <AttachMinutesDialog
        open={attachMinutesDialog.open}
        onOpenChange={(open) => setAttachMinutesDialog({ open, recordId: open ? attachMinutesDialog.recordId : null })}
        trustId={selectedTrust?.trust_id}
        recordType="benevolence"
        recordId={attachMinutesDialog.recordId}
        onAttached={() => {
          loadAllData();
          setAttachMinutesDialog({ open: false, recordId: null });
        }}
      />
    </div>
  );
}
