import { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { AttachMinutesDialog } from '@/components/AttachMinutesDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import PageHelpButton from '@/components/PageHelpButton';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { fetchWithAuth, API } from '@/utils/api';
import PageAgentAssistant from '@/components/PageAgentAssistant';
import PageAgentErrorBoundary from '@/components/PageAgentErrorBoundary';
import { 
  Plus, 
  Search,
  Calendar as CalendarIcon,
  DollarSign,
  Filter,
  Check,
  X,
  Clock,
  HeartHandshake,
  MoreVertical,
  Link2,
  FileText,
  Send,
  Mail,
  Bot,
  Trash2
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

// Debounce hook
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}

// Feature flag: only render the Page Agent pilot when explicitly enabled.
const PAGE_AGENT_ENABLED = process.env.REACT_APP_ENABLE_PAGE_AGENT === 'true';

export default function DistributionsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTrust, isReadOnly } = useAuth();
  const { showUpgradeModal } = useUpgradeModal();
  const [distributions, setDistributions] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const PAGE_SIZE = 50;
  
  // Approval modal state
  const [approvalModal, setApprovalModal] = useState(null);
  const [solvencyConfirmed, setSolvencyConfirmed] = useState(false);
  const [recusalAcknowledged, setRecusalAcknowledged] = useState(false);
  const [approvalLoading, setApprovalLoading] = useState(false);
  
  // Attach minutes dialog state
  const [attachMinutesDialog, setAttachMinutesDialog] = useState({ open: false, recordId: null });
  
  // Send notice state
  const [sendingNotice, setSendingNotice] = useState({});
  const [sendNoticeResult, setSendNoticeResult] = useState({});

  // Delete confirmation state
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const [formData, setFormData] = useState({
    date: new Date(),
    amount: '',
    distribution_type: 'trust_distribution',
    beneficiary: '',
    category: '',
    notes: '',
    status: 'review',
    trustee_name: '',
    // Benevolence fields
    is_benevolence: false,
    benevolence_recipient_name: '',
    benevolence_need_description: '',
    benevolence_notes: ''
  });
  const [beneficiaryVerified, setBeneficiaryVerified] = useState(null); // null = not checked, true = verified, false = not found
  const debouncedBeneficiary = useDebounce(formData.beneficiary, 500);

  const debouncedSearch = useDebounce(searchTerm, 300);

  // Ref for the "New Distribution" dialog form container — passed to
  // PageAgentAssistant so the agent is restricted to interacting only with
  // elements inside this form. It does NOT cover the approval modal,
  // delete modal, or the distributions table.
  const distributionFormRef = useRef(null);

  // ---------------- Page Agent system instructions ----------------
  // Distributions-specific instructions. The agent can help fill in draft
  // values for a new distribution (amount, beneficiary, category, notes,
  // dates, type, trustee, benevolence fields) but must NEVER submit the
  // distribution or approve/decline an existing one. Those are fiduciary
  // actions reserved for the user.
  const pageAgentInstructions = useMemo(() => {
    return `
You are the TrustOffice Distributions Page Agent, embedded in the "New
Distribution" dialog form. Your ONLY job is to help the user fill in draft
values for the form fields and explain what each field means. You operate
inside the dialog that opens when the user clicks "Add Distribution".

ABSOLUTE RULES:
1. NEVER submit the form. Do not click, tap, or otherwise activate the
   "Create Distribution" button (data-testid="submit-distribution-btn").
   Creating a distribution is a fiduciary action reserved for the user.
2. NEVER click the "Add Distribution" button (data-testid="add-distribution-btn")
   or the dialog trigger — the dialog is already open when you are active.
3. NEVER approve or decline a distribution. Do not click any element with
   data-testid starting with "approve-" or "decline-". Do not click
   "Approve Distribution" (data-testid="confirm-approval-btn") in the
   approval modal. Do not check the solvency or recusal checkboxes
   (data-testid="solvency-checkbox", data-testid="recusal-checkbox").
   Approval is a fiduciary action reserved for the user.
4. NEVER delete a distribution. Do not click any element with data-testid
   starting with "delete-" or the "confirm-delete-btn" button.
5. NEVER send a distribution notice. Do not click any element with
   data-testid starting with "send-notice-".
6. You may ONLY interact with elements inside the "New Distribution" dialog
   form container. Do not navigate away, open menus, close the dialog, or
   touch anything outside that container (no table rows, no approval modal,
   no delete modal, no filters, no search).
7. Never run arbitrary JavaScript. The execute_javascript tool is disabled.
8. Never ask for or reveal sensitive PII that is not already visible on the
   page. Never invent beneficiary names, EINs, SSNs, or credit card numbers.
9. If the user asks you to submit, approve, decline, delete, or send a
   notice, refuse and explain that those are fiduciary actions reserved
   for the user.

WHAT YOU CAN DO:
- Fill form fields from values the user provides in their instruction.
- Explain what a field means (e.g. "What category should I select?").
- Suggest a value for a field based on the user's instruction.
- Clear a field the user asks to clear.
- Toggle the "Benevolence Distribution" switch
  (data-testid="benevolence-toggle") if the user asks to mark the
  distribution as benevolence, and then fill the revealed benevolence
  fields. Do NOT toggle it off unless the user explicitly asks.

HOW TO FILL:
- Date (calendar popover trigger): data-testid="dist-date-picker"
  — this is a Radix Popover with a Calendar inside. Click the trigger to
  open it, then click the desired day cell in the calendar grid. The
  calendar shows the current month; use the month navigation arrows if
  needed. After selecting a day, the popover closes automatically.
- Amount (number input): data-testid="dist-amount-input"
- Beneficiary (text input): data-testid="dist-beneficiary-input"
- Type (Radix Select): use the select_radix_option tool with
  testid="dist-type-select" and optionText = the visible label
  (e.g. "Trust Distribution", "Loan", "Gift").
- Category (Radix Select): use the select_radix_option tool with
  testid="dist-category-select" and optionText = the exact visible label
  of the category. The available categories are loaded dynamically; if the
  dropdown is empty or the requested category is not listed, tell the user.
- Trustee (Radix Select, only when multiple trustees exist):
  use select_radix_option with testid="dist-trustee-select" and the
  trustee's name as optionText. If there is only one trustee or none,
  the field is a read-only input (data-testid="dist-trustee-input") — do
  not try to change it.
- Status (Radix Select): use select_radix_option with
  testid="dist-status-select" and optionText = "Pending Review",
  "Approved", or "Declined". NOTE: setting status to "Approved" here only
  changes the draft form field — it does NOT approve the distribution.
  Actual approval requires the solvency + recusal modal, which you must
  never touch.
- Benevolence toggle (Switch): data-testid="benevolence-toggle"
- Benevolence Recipient Name: data-testid="benevolence-recipient-input"
  (only visible after toggling benevolence on)
- Benevolence Need Description: data-testid="benevolence-need-input"
  (only visible after toggling benevolence on)
- Benevolence Notes: data-testid="benevolence-notes-input"
  (only visible after toggling benevolence on)
- Notes (textarea): data-testid="dist-notes-input"

When you fill a field, briefly tell the user what you set and why. If a
requested value is missing or unclear, say so — do not guess. Always remind
the user that they must review and submit the form themselves.
`.trim();
  }, []);

  useEffect(() => {
    loadCategories();
  }, []);

  // Beneficiary verification check
  useEffect(() => {
    if (!selectedTrust || !debouncedBeneficiary || !debouncedBeneficiary.trim()) {
      setBeneficiaryVerified(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const response = await fetchWithAuth(`/distributions/validate-beneficiary?trust_id=${selectedTrust.trust_id}&name=${encodeURIComponent(debouncedBeneficiary.trim())}`);
        if (cancelled) return;
        if (response.ok) {
          const data = await response.json();
          setBeneficiaryVerified(data.valid);
        } else {
          setBeneficiaryVerified(null);
        }
      } catch {
        setBeneficiaryVerified(null);
      }
    })();
    return () => { cancelled = true; };
  }, [debouncedBeneficiary, selectedTrust]);

  useEffect(() => {
    if (selectedTrust) {
      loadDistributions(debouncedSearch);
    }
  }, [selectedTrust, debouncedSearch, filterStatus]);

  // Auto-open approval modal when arriving via ?approve=<id> deep-link
  const [autoApproveHandled, setAutoApproveHandled] = useState(false);
  useEffect(() => {
    const approveId = searchParams.get('approve');
    if (approveId && !autoApproveHandled && distributions.length > 0) {
      const dist = distributions.find(d => d.distribution_id === approveId);
      if (dist) {
        setApprovalModal(dist);
        setSolvencyConfirmed(false);
        setRecusalAcknowledged(false);
      }
      setAutoApproveHandled(true);
      // Clean URL
      searchParams.delete('approve');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, distributions, autoApproveHandled]);

  // Highlight deep-link: scroll to and flash a distribution row when arriving via ?highlight=<id>
  const [highlightId, setHighlightId] = useState(null);
  useEffect(() => {
    const hlId = searchParams.get('highlight');
    if (hlId && distributions.length > 0) {
      setHighlightId(hlId);
      // Clean URL
      searchParams.delete('highlight');
      setSearchParams(searchParams, { replace: true });
      // Scroll to the row after render
      setTimeout(() => {
        const row = document.querySelector(`[data-testid="dist-row-${hlId}"]`);
        if (row) {
          row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 100);
      // Clear highlight after 3 seconds
      setTimeout(() => setHighlightId(null), 3000);
    }
  }, [searchParams, distributions]);

  const loadCategories = async () => {
    try {
      const response = await fetchWithAuth('/categories');
      if (response.ok) {
        const data = await response.json();
        // Use purpose_classifications from backend
        setCategories(data.purpose_classifications || data.distribution_categories || []);
      }
    } catch (error) {
      console.error('Failed to load categories:', error);
    }
  };

  const loadDistributions = async (search = '', append = false) => {
    if (!selectedTrust) {
      setLoading(false);
      return;
    }
    
    if (!append) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    try {
      const skip = append ? distributions.length : 0;
      let url = `/distributions?trust_id=${selectedTrust.trust_id}&skip=${skip}&limit=${PAGE_SIZE}`;
      if (search) {
        url += `&search=${encodeURIComponent(search)}`;
      }
      if (filterStatus && filterStatus !== 'all') {
        url += `&status=${encodeURIComponent(filterStatus)}`;
      }
      const response = await fetchWithAuth(url);
      if (response.ok) {
        const data = await response.json();
        const items = data.items || data || [];
        setTotalCount(data.total || 0);
        if (append) {
          setDistributions(prev => [...prev, ...items]);
        } else {
          setDistributions(items);
        }
      }
    } catch (error) {
      console.error('Failed to load distributions:', error);
      showError(toast, error, { operation: 'load', page: 'Distributions' });
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  const handleLoadMore = () => {
    loadDistributions(debouncedSearch, true);
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

    // Validate benevolence fields if is_benevolence is true
    if (formData.is_benevolence) {
      if (!formData.benevolence_recipient_name?.trim()) {
        toast.error('Benevolence recipient name is required');
        return;
      }
      if (!formData.benevolence_need_description?.trim()) {
        toast.error('Benevolence need description is required');
        return;
      }
    }

    setFormLoading(true);
    try {
      const payload = {
        trust_id: selectedTrust.trust_id,
        beneficiary_name: formData.beneficiary,
        amount: parseFloat(formData.amount),
        date: formData.date.toISOString().split('T')[0],
        purpose_classification: formData.category,
        notes: formData.notes || '',
        trustee_name: formData.trustee_name || (Array.isArray(selectedTrust?.trustees) ? selectedTrust.trustees[0] : String(selectedTrust?.trustees || '').split(',')[0])?.trim() || '',
        is_benevolence: formData.is_benevolence,
        benevolence_recipient_name: formData.is_benevolence ? formData.benevolence_recipient_name : null,
        benevolence_need_description: formData.is_benevolence ? formData.benevolence_need_description : null,
        benevolence_notes: formData.is_benevolence ? formData.benevolence_notes : null
      };

      const response = await fetchWithAuth('/distributions', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create distribution');
      }

      toast.success(formData.is_benevolence ? 'Benevolence distribution created' : 'Distribution created');
      setDialogOpen(false);
      setFormData({
        date: new Date(),
        amount: '',
        distribution_type: 'trust_distribution',
        beneficiary: '',
        category: '',
        notes: '',
        status: 'review',
        trustee_name: '',
        is_benevolence: false,
        benevolence_recipient_name: '',
        benevolence_need_description: '',
        benevolence_notes: ''
      });
      loadDistributions();
    } catch (error) {
      showError(toast, error, { operation: 'create_distribution', page: 'Distributions' });
    } finally {
      setFormLoading(false);
    }
  };

  const handleUpdateStatus = async (distributionId, newStatus) => {
    if (newStatus === 'approved') {
      // Open approval modal for formal approval
      const dist = distributions.find(d => d.distribution_id === distributionId);
      setApprovalModal(dist);
      setSolvencyConfirmed(false);
      setRecusalAcknowledged(false);
      return;
    }
    
    // For decline or review, use the PATCH endpoint
    try {
      const response = await fetchWithAuth(`/distributions/${distributionId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update status');
      }

      const statusMessage = newStatus === 'declined' ? 'declined' : 'set to review';
      toast.success(`Distribution ${statusMessage}`);
      loadDistributions();
    } catch (error) {
      showError(toast, error, { operation: 'update_distribution_status', page: 'Distributions' });
    }
  };

  const handleApproveWithChecks = async () => {
    if (!approvalModal) return;
    
    if (!solvencyConfirmed || !recusalAcknowledged) {
      toast.error('Please confirm both solvency and recusal acknowledgments');
      return;
    }
    
    setApprovalLoading(true);
    try {
      const response = await fetchWithAuth(`/distributions/${approvalModal.distribution_id}/approve`, {
        method: 'PATCH',
        body: JSON.stringify({
          solvency_confirmed: solvencyConfirmed,
          recusal_acknowledged: recusalAcknowledged
        })
      });

      if (!response.ok) {
        throw new Error('Failed to approve distribution');
      }

      toast.success('Distribution approved');
      setApprovalModal(null);
      loadDistributions();
    } catch (error) {
      showError(toast, error, { operation: 'approve_distribution', page: 'Distributions' });
    } finally {
      setApprovalLoading(false);
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
    const status = d.status === 'declined' ? 'declined' : (d.approved_at ? 'approved' : 'review');
    const matchesStatus = filterStatus === 'all' || status === filterStatus;
    return matchesStatus;
  });

  const totalAmount = filteredDistributions.reduce((sum, d) => sum + d.amount, 0);
  const pendingCount = distributions.filter(d => !d.approved_at && d.status !== 'declined').length;

  // Handle dialog open with read-only check
  const handleDialogOpenChange = (open) => {
    if (open && isReadOnly) {
      showUpgradeModal('create a distribution', 'button_click', 'distributions_page');
      return;
    }
    setDialogOpen(open);
  };

  // Navigate to Create Minutes to document this distribution (retroactive)
  const handleCreateMinutesFromDistribution = (dist) => {
    const params = new URLSearchParams({
      prefill_type: 'distribution',
      prefill_amount: dist.amount.toString(),
      prefill_recipient: dist.beneficiary_name || dist.beneficiary || '',
      prefill_description: dist.purpose_classification || dist.category || ''
    });
    navigate(`/minutes/create?${params.toString()}`);
  };

  // Handle successful minutes attachment
  const handleMinutesAttached = () => {
    loadDistributions();
    setAttachMinutesDialog({ open: false, recordId: null });
  };

  // Send distribution notice to beneficiary
  const handleSendNotice = async (dist) => {
    setSendingNotice(prev => ({ ...prev, [dist.distribution_id]: true }));
    setSendNoticeResult(prev => ({ ...prev, [dist.distribution_id]: null }));
    try {
      const response = await fetchWithAuth(`/distributions/${dist.distribution_id}/send-notice`, {
        method: 'POST'
      });
      const data = await response.json();
      if (response.ok) {
        toast.success(`Notice sent to ${data.recipient_email}`);
        setSendNoticeResult(prev => ({ ...prev, [dist.distribution_id]: 'sent' }));
      } else {
        showError(toast, new Error(data.detail || 'Failed to send notice'), { operation: 'send', page: 'Distributions' });
        setSendNoticeResult(prev => ({ ...prev, [dist.distribution_id]: 'error' }));
      }
    } catch (error) {
      showError(toast, error, { operation: 'send', page: 'Distributions' });
      setSendNoticeResult(prev => ({ ...prev, [dist.distribution_id]: 'error' }));
    } finally {
      setSendingNotice(prev => ({ ...prev, [dist.distribution_id]: false }));
    }
  };

  // Handle delete with read-only check
  const handleDeleteClick = (dist) => {
    if (isReadOnly) {
      showUpgradeModal('delete a distribution', 'button_click', 'distributions_page');
      return;
    }
    setDeleteConfirm(dist);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;
    setDeleteLoading(true);
    try {
      const response = await fetchWithAuth(`/distributions/${deleteConfirm.distribution_id}`, {
        method: 'DELETE'
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to delete distribution');
      }
      toast.success('Distribution deleted');
      setDeleteConfirm(null);
      loadDistributions();
    } catch (error) {
      showError(toast, error, { operation: 'delete', page: 'Distributions' });
    } finally {
      setDeleteLoading(false);
    }
  };

  if (!selectedTrust) {
    return (
      <div className="main-layout" data-testid="distributions-page">
        <Sidebar />
        <main className="main-content dot-grid">
          <div className="page-container">
            <div className="card-trust p-12 flex flex-col items-center justify-center">
              <DollarSign className="w-12 h-12 text-navy/30 mb-3" />
              <h2 className="text-xl font-semibold text-navy mb-1">Select a Trust</h2>
              <p className="text-sm text-muted-foreground">Choose a trust to manage distributions.</p>
            </div>
          </div>
        </main>
        <MobileBottomNav />
      </div>
    );
  }

  return (
    <div className="main-layout" data-testid="distributions-page">
      <Sidebar />
      <main className="main-content dot-grid">
        {/* Subscription Banners */}

        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-start justify-between">
            <div>
              <h1 className="page-title">Distributions</h1>
              <p className="page-subtitle">Record and manage trust distributions to beneficiaries — document amounts, purposes, and approvals for fiduciary compliance</p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Record and manage all distributions to trust beneficiaries' },
                  { text: 'Track distribution amounts, purposes, and approval status' },
                  { text: 'Send beneficiary notices and attach supporting minutes' },
                ]}
                taPrompt="Walk me through the Distributions page and how to record a distribution"
              />
              <Dialog open={dialogOpen} onOpenChange={handleDialogOpenChange}>
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
                <div className="space-y-4 mt-4" ref={distributionFormRef}>
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
                    {beneficiaryVerified === false && formData.beneficiary.trim() && (
                      <p className="text-xs text-warning mt-1 flex items-center gap-1" data-testid="beneficiary-warning">
                        <span>⚠</span> This beneficiary is not in your trust's beneficiary list. Verify this is the correct recipient before proceeding.
                      </p>
                    )}
                    {beneficiaryVerified === true && formData.beneficiary.trim() && (
                      <p className="text-xs text-success mt-1 flex items-center gap-1">
                        <span>✓</span> Verified beneficiary
                      </p>
                    )}
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
                    <Label className="label-trust">Trustee</Label>
                    {(() => {
                      const trusteeList = Array.isArray(selectedTrust?.trustees)
                        ? selectedTrust.trustees
                        : String(selectedTrust?.trustees || '')
                        .split(',')
                        .map(t => t.trim())
                        .filter(t => t);
                      if (trusteeList.length === 0) {
                        return (
                          <Input
                            value=""
                            readOnly
                            className="mt-1 input-trust"
                            placeholder="No trustees configured"
                            data-testid="dist-trustee-input"
                          />
                        );
                      }
                      if (trusteeList.length === 1) {
                        return (
                          <Input
                            value={trusteeList[0]}
                            readOnly
                            className="mt-1 input-trust"
                            data-testid="dist-trustee-input"
                          />
                        );
                      }
                      return (
                        <Select
                          value={formData.trustee_name || trusteeList[0]}
                          onValueChange={(value) => setFormData({ ...formData, trustee_name: value })}
                        >
                          <SelectTrigger className="mt-1 input-trust" data-testid="dist-trustee-select">
                            <SelectValue placeholder="Select trustee..." />
                          </SelectTrigger>
                          <SelectContent>
                            {trusteeList.map((trustee) => (
                              <SelectItem key={trustee} value={trustee}>
                                {trustee}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      );
                    })()}
                    <p className="text-xs text-muted-foreground mt-1">
                      Trustee responsible for authorizing this distribution
                    </p>
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

                  {/* Benevolence Mode Toggle */}
                  <div className="p-4 border border-gold/30 bg-gold/5">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <Label className="label-trust text-gold">Benevolence Distribution</Label>
                        <p className="text-xs text-muted-foreground mt-0.5">Mark as charitable/benevolent distribution</p>
                      </div>
                      <Switch
                        checked={formData.is_benevolence}
                        onCheckedChange={(checked) => setFormData({ ...formData, is_benevolence: checked })}
                        data-testid="benevolence-toggle"
                      />
                    </div>
                    
                    {formData.is_benevolence && (
                      <div className="space-y-3 mt-4 pt-4 border-t border-gold/20">
                        <div>
                          <Label className="label-trust">Recipient Name *</Label>
                          <Input
                            value={formData.benevolence_recipient_name}
                            onChange={(e) => setFormData({ ...formData, benevolence_recipient_name: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="Organization or individual receiving benevolence"
                            data-testid="benevolence-recipient-input"
                          />
                        </div>
                        <div>
                          <Label className="label-trust">Need Description *</Label>
                          <Textarea
                            value={formData.benevolence_need_description}
                            onChange={(e) => setFormData({ ...formData, benevolence_need_description: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="Describe the charitable purpose or need being addressed..."
                            rows={2}
                            data-testid="benevolence-need-input"
                          />
                        </div>
                        <div>
                          <Label className="label-trust">Benevolence Notes (Optional)</Label>
                          <Input
                            value={formData.benevolence_notes}
                            onChange={(e) => setFormData({ ...formData, benevolence_notes: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="Additional charitable notes..."
                            data-testid="benevolence-notes-input"
                          />
                        </div>
                      </div>
                    )}
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

                  {/* Page Agent pilot — only renders when REACT_APP_ENABLE_PAGE_AGENT === 'true'.
                      Restricted to the dialog form container via distributionFormRef.
                      The agent can fill draft values but NEVER submit/approve/delete. */}
                  {PAGE_AGENT_ENABLED && (
                    <PageAgentErrorBoundary>
                      <PageAgentAssistant
                        containerRef={distributionFormRef}
                        systemInstructions={pageAgentInstructions}
                        pageName="Distributions"
                        placeholder='e.g. "Fill in $500 to John Smith as a Trust Distribution"'
                        idleMessage='Ready. Type an instruction like "Fill in $500 to John Smith".'
                        helpText='The agent can fill draft values for the form and explain fields. It will never submit, approve, or delete — those are fiduciary actions you must take yourself.'
                      />
                    </PageAgentErrorBoundary>
                  )}
                </div>
              </DialogContent>
            </Dialog>
            </div>
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
              <div className="flex flex-wrap gap-2">
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
                    <th className="text-center">Minutes</th>
                    <th className="text-center">Notice</th>
                    <th className="text-center">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDistributions.map((dist) => {
                    const status = dist.status === 'declined' ? 'declined' : (dist.approved_at ? 'approved' : 'review');
                    return (
                    <tr key={dist.distribution_id} data-testid={`dist-row-${dist.distribution_id}`} className={highlightId === dist.distribution_id ? 'bg-gold/10 border-l-4 border-l-gold' : ''}>
                      <td>{formatDate(dist.date)}</td>
                      <td>
                        {dist.beneficiary_name || dist.beneficiary || '-'}
                        {dist.beneficiary_not_verified && (
                          <span className="ml-1 text-xs text-warning" title="Beneficiary not found in trust beneficiary list">⚠</span>
                        )}
                      </td>
                      <td>{dist.purpose_classification || dist.category || '-'}</td>
                      <td className="text-right font-mono">{formatCurrency(dist.amount)}</td>
                      <td className="text-center">
                        <span className={`badge-trust ${getStatusBadgeClass(status)}`}>
                          {status}
                        </span>
                      </td>
                      <td className="text-center">
                        {dist.minutes_record_id ? (
                          <span className="flex items-center justify-center gap-1 text-xs text-success dark:text-success">
                            <Link2 className="w-3 h-3" />
                            Linked
                          </span>
                        ) : (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <button className="p-1 hover:bg-navy/10 dark:hover:bg-white/10" data-testid={`minutes-menu-${dist.distribution_id}`}>
                                <MoreVertical className="w-4 h-4 text-navy/60 dark:text-white/60" />
                              </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setAttachMinutesDialog({ open: true, recordId: dist.distribution_id })}>
                                <Link2 className="w-4 h-4 mr-2" />
                                Link to existing minutes
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => handleCreateMinutesFromDistribution(dist)}>
                                <FileText className="w-4 h-4 mr-2" />
                                Document in minutes (retroactive)
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </td>
                      <td className="text-center">
                        <button
                          onClick={() => handleSendNotice(dist)}
                          disabled={sendingNotice[dist.distribution_id] || sendNoticeResult[dist.distribution_id] === 'sent'}
                          className={`p-1 transition-colors ${
                            sendNoticeResult[dist.distribution_id] === 'sent'
                              ? 'text-gold'
                              : 'text-navy/60 hover:text-navy hover:bg-navy/10'
                          }`}
                          title={sendNoticeResult[dist.distribution_id] === 'sent' ? 'Notice sent' : 'Send distribution notice to beneficiary'}
                          data-testid={`send-notice-${dist.distribution_id}`}
                        >
                          {sendingNotice[dist.distribution_id] ? (
                            <div className="w-4 h-4 border-2 border-navy/30 border-t-navy animate-spin" />
                          ) : sendNoticeResult[dist.distribution_id] === 'sent' ? (
                            <Mail className="w-4 h-4" />
                          ) : (
                            <Send className="w-4 h-4" />
                          )}
                        </button>
                      </td>
                      <td className="text-center">
                        <div className="flex justify-center items-center gap-1.5">
                          {status === 'review' && (
                            <>
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
                            </>
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
                          <Link
                            to={`/trust-assistant?prompt=${encodeURIComponent(`Draft meeting minutes documenting the $${dist.amount} distribution to ${dist.beneficiary_name || dist.beneficiary || 'the beneficiary'} on ${formatDate(dist.date)}.`)}`}
                            className="inline-flex items-center gap-1 px-2 py-1 text-xs text-gold hover:bg-gold/10 transition-colors"
                            title="Ask Trust Assistant to draft minutes"
                            data-testid={`ta-draft-minutes-${dist.distribution_id}`}
                          >
                            <Bot className="w-3.5 h-3.5" />
                            <span className="hidden lg:inline">Draft Minutes</span>
                          </Link>
                          <button
                            onClick={() => handleDeleteClick(dist)}
                            className="p-1 hover:bg-error/10 text-error"
                            title="Delete distribution"
                            data-testid={`delete-${dist.distribution_id}`}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )})}
                </tbody>
              </table>
            </div>
          )}

          {/* Load More button */}
          {distributions.length > 0 && distributions.length < totalCount && (
            <div className="flex justify-center mt-6">
              <Button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="btn-secondary"
                data-testid="load-more-distributions"
              >
                {loadingMore ? 'Loading...' : `Load More (${totalCount - distributions.length} remaining)`}
              </Button>
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* Approval Modal with Solvency & Recusal Checks */}
      {approvalModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" data-testid="approval-modal">
          <div className="bg-white p-6 w-full max-w-md corner-mark">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-serif text-xl text-navy">Approve Distribution</h2>
              <button 
                onClick={() => setApprovalModal(null)} 
                className="text-navy hover:text-navy/70"
                data-testid="close-approval-modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Distribution Summary */}
            <div className="p-4 bg-navy/5 border border-navy/10 mb-6">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Beneficiary</p>
                  <p className="font-medium text-navy">{approvalModal.beneficiary_name || approvalModal.beneficiary}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Amount</p>
                  <p className="font-mono text-navy">{formatCurrency(approvalModal.amount)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Category</p>
                  <p className="text-navy">{approvalModal.purpose_classification || approvalModal.category}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Date</p>
                  <p className="font-mono text-navy">{formatDate(approvalModal.date)}</p>
                </div>
              </div>
            </div>

            {/* Solvency Confirmation */}
            <div className="space-y-4 mb-6">
              <label className="flex items-start gap-3 p-4 border border-navy/20 cursor-pointer hover:border-navy/40 transition-colors">
                <input
                  type="checkbox"
                  checked={solvencyConfirmed}
                  onChange={(e) => setSolvencyConfirmed(e.target.checked)}
                  className="mt-1 w-5 h-5"
                  data-testid="solvency-checkbox"
                />
                <div>
                  <p className="font-medium text-navy">Solvency Confirmation</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    I confirm that the Trust has sufficient assets to make this distribution while meeting all other known obligations and maintaining appropriate reserves.
                  </p>
                </div>
              </label>

              {/* Recusal Acknowledgment */}
              <label className="flex items-start gap-3 p-4 border border-navy/20 cursor-pointer hover:border-navy/40 transition-colors">
                <input
                  type="checkbox"
                  checked={recusalAcknowledged}
                  onChange={(e) => setRecusalAcknowledged(e.target.checked)}
                  className="mt-1 w-5 h-5"
                  data-testid="recusal-checkbox"
                />
                <div>
                  <p className="font-medium text-navy">Recusal Acknowledgment</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    I acknowledge that any trustee who is a beneficiary of this distribution has properly recused themselves from the approval decision.
                  </p>
                </div>
              </label>
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <Button 
                onClick={() => setApprovalModal(null)} 
                variant="outline" 
                className="flex-1 btn-secondary"
              >
                Cancel
              </Button>
              <Button 
                onClick={handleApproveWithChecks}
                disabled={!solvencyConfirmed || !recusalAcknowledged || approvalLoading}
                className="flex-1 btn-primary"
                data-testid="confirm-approval-btn"
              >
                {approvalLoading ? 'Approving...' : (
                  <>
                    <Check className="w-4 h-4 mr-2" />
                    Approve Distribution
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" data-testid="delete-confirm-modal">
          <div className="bg-white p-6 w-full max-w-md corner-mark">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-serif text-xl text-navy">Delete Distribution</h2>
              <button
                onClick={() => setDeleteConfirm(null)}
                className="text-navy hover:text-navy/70"
                data-testid="close-delete-modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 bg-error/5 border border-error/10 mb-6">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Beneficiary</p>
                  <p className="font-medium text-navy">{deleteConfirm.beneficiary_name || deleteConfirm.beneficiary}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Amount</p>
                  <p className="font-mono text-navy">{formatCurrency(deleteConfirm.amount)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Date</p>
                  <p className="font-mono text-navy">{formatDate(deleteConfirm.date)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Category</p>
                  <p className="text-navy">{deleteConfirm.purpose_classification || deleteConfirm.category}</p>
                </div>
              </div>
            </div>
            <p className="text-sm text-muted-foreground mb-6">
              Are you sure you want to delete this distribution record? This action cannot be undone.
            </p>
            <div className="flex gap-3">
              <Button
                onClick={() => setDeleteConfirm(null)}
                variant="outline"
                className="flex-1 btn-secondary"
              >
                Cancel
              </Button>
              <Button
                onClick={handleDeleteConfirm}
                disabled={deleteLoading}
                className="flex-1 btn-primary"
                data-testid="confirm-delete-btn"
              >
                {deleteLoading ? 'Deleting...' : 'Delete Distribution'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Attach Minutes Dialog */}
      <AttachMinutesDialog
        open={attachMinutesDialog.open}
        onOpenChange={(open) => setAttachMinutesDialog({ open, recordId: open ? attachMinutesDialog.recordId : null })}
        trustId={selectedTrust?.trust_id}
        recordType="distribution"
        recordId={attachMinutesDialog.recordId}
        onAttached={handleMinutesAttached}
      />
    </div>
  );
}
