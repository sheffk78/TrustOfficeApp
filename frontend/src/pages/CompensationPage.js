import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { AttachMinutesDialog } from '@/components/AttachMinutesDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { fetchWithAuth } from '@/utils/api';
import { 
  Wallet, 
  Plus, 
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  Trash2,
  Edit2,
  Info,
  ChevronDown,
  ChevronUp,
  MoreVertical,
  Link2,
  FileText
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { toast } from 'sonner';

export default function CompensationPage() {
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [plans, setPlans] = useState([]);
  const [payments, setPayments] = useState([]);
  const [ytdData, setYtdData] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Modal states
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showAdvancedPlans, setShowAdvancedPlans] = useState(false);
  const [editingPlan, setEditingPlan] = useState(null); // null for new, plan object for edit
  
  // Attach minutes dialog state
  const [attachMinutesDialog, setAttachMinutesDialog] = useState({ open: false, recordId: null });
  
  // Form states
  const [planForm, setPlanForm] = useState({
    annual_approved_amount: '',
    effective_date: format(new Date(), 'yyyy-MM-dd'),
    notes: '',
    trustee_name: '',
    role: '',
    is_primary: true
  });
  const [paymentForm, setPaymentForm] = useState({
    amount: '',
    date: format(new Date(), 'yyyy-MM-dd'),
    classification_text: '',
    trustee_name: '' // Which trustee receives this payment
  });

  // Get trustees from trust or plans
  const [trustees, setTrustees] = useState([]);

  const currentYear = new Date().getFullYear();

  useEffect(() => {
    if (selectedTrust) {
      loadData();
    }
  }, [selectedTrust]);

  const loadData = async () => {
    if (!selectedTrust) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [plansRes, paymentsRes, ytdRes, contextRes] = await Promise.all([
        fetchWithAuth(`/compensation-plans?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/compensation-payments?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/compensation-ytd?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/guided-minutes/context?trust_id=${selectedTrust.trust_id}`)
      ]);
      
      if (plansRes.ok) setPlans(await plansRes.json());
      if (paymentsRes.ok) setPayments(await paymentsRes.json());
      if (ytdRes.ok) setYtdData(await ytdRes.json());
      
      // Get trustees list from context
      if (contextRes.ok) {
        const context = await contextRes.json();
        setTrustees(context.trustees || []);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSavePlan = async () => {
    if (!selectedTrust || !planForm.annual_approved_amount) {
      toast.error('Annual amount is required');
      return;
    }
    
    try {
      const payload = {
        trust_id: selectedTrust.trust_id,
        annual_approved_amount: parseFloat(planForm.annual_approved_amount),
        effective_date: planForm.effective_date,
        notes: planForm.notes,
        trustee_name: planForm.trustee_name,
        role: planForm.role,
        is_primary: planForm.is_primary
      };

      let response;
      if (editingPlan) {
        response = await fetchWithAuth(`/compensation-plans/${editingPlan.plan_id}`, {
          method: 'PUT',
          body: JSON.stringify(payload)
        });
      } else {
        response = await fetchWithAuth('/compensation-plans', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
      }
      
      if (response.ok) {
        toast.success(editingPlan ? 'Plan updated' : 'Plan created');
        setShowPlanModal(false);
        setEditingPlan(null);
        resetPlanForm();
        loadData();
      } else {
        const error = await response.json().catch(() => ({}));
        toast.error(error.detail || 'Failed to save plan');
      }
    } catch (error) {
      toast.error('Failed to save plan');
    }
  };

  const handleDeletePlan = async (planId) => {
    if (!confirm('Delete this compensation plan?')) return;
    try {
      const response = await fetchWithAuth(`/compensation-plans/${planId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        toast.success('Plan deleted');
        loadData();
      }
    } catch (error) {
      toast.error('Failed to delete plan');
    }
  };

  const handleCreatePayment = async () => {
    if (!selectedTrust || !paymentForm.amount) {
      toast.error('Amount is required');
      return;
    }
    try {
      const response = await fetchWithAuth('/compensation-payments', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          amount: parseFloat(paymentForm.amount),
          date: paymentForm.date,
          classification_text: paymentForm.classification_text,
          trustee_name: paymentForm.trustee_name || null
        })
      });
      if (response.ok) {
        toast.success('Payment recorded');
        setShowPaymentModal(false);
        setPaymentForm({
          amount: '',
          date: format(new Date(), 'yyyy-MM-dd'),
          classification_text: '',
          trustee_name: ''
        });
        loadData();
      }
    } catch (error) {
      toast.error('Failed to record payment');
    }
  };

  const handleDeletePayment = async (paymentId) => {
    if (!confirm('Delete this payment?')) return;
    try {
      const response = await fetchWithAuth(`/compensation-payments/${paymentId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        toast.success('Payment deleted');
        loadData();
      }
    } catch (error) {
      toast.error('Failed to delete payment');
    }
  };

  const openEditPlan = (plan) => {
    setEditingPlan(plan);
    setPlanForm({
      annual_approved_amount: plan.annual_approved_amount || plan.annual_fee || '',
      effective_date: plan.effective_date?.split('T')[0] || format(new Date(), 'yyyy-MM-dd'),
      notes: plan.notes || '',
      trustee_name: plan.trustee_name || '',
      role: plan.role || '',
      is_primary: plan.is_primary !== false
    });
    setShowPlanModal(true);
  };

  const openNewPrimaryPlan = () => {
    setEditingPlan(null);
    resetPlanForm();
    setPlanForm(prev => ({ ...prev, is_primary: true }));
    setShowPlanModal(true);
  };

  const openNewAdditionalPlan = () => {
    setEditingPlan(null);
    resetPlanForm();
    setPlanForm(prev => ({ ...prev, is_primary: false }));
    setShowPlanModal(true);
  };

  const resetPlanForm = () => {
    setPlanForm({
      annual_approved_amount: '',
      effective_date: format(new Date(), 'yyyy-MM-dd'),
      notes: '',
      trustee_name: '',
      role: '',
      is_primary: true
    });
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
    }).format(amount || 0);
  };

  // Get primary plan from ytdData or plans array
  const primaryPlan = ytdData?.primary_plan || plans.find(p => p.is_primary);
  const additionalPlans = plans.filter(p => !p.is_primary && p.trustee_name);
  const progressPercent = ytdData && ytdData.annual_approved 
    ? Math.min(100, (ytdData.ytd_total / ytdData.annual_approved) * 100)
    : 0;

  return (
    <div className="main-layout" data-testid="compensation-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Compensation</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'} • Trustee Compensation Tracking
              </p>
            </div>
            <Button 
              onClick={() => setShowPaymentModal(true)} 
              className="btn-primary"
              data-testid="record-payment-btn"
            >
              <Plus className="w-4 h-4 mr-2" /> Record Payment
            </Button>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 card-trust">
                <div className="skeleton h-32 w-full"></div>
              </div>
              <div className="card-trust">
                <div className="skeleton h-32 w-full"></div>
              </div>
            </div>
          ) : (
            <>
              {/* Main YTD Summary & Primary Plan */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* YTD Progress Card */}
                <div className="lg:col-span-2 card-trust corner-mark">
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <p className="label-trust mb-1">{currentYear} Year-to-Date Compensation</p>
                      <h2 className="font-serif text-3xl text-navy">
                        {formatCurrency(ytdData?.ytd_total)}
                      </h2>
                    </div>
                    {ytdData?.exceeds_plan ? (
                      <div className="flex items-center gap-2 px-3 py-1 bg-error/10 text-error">
                        <AlertTriangle className="w-4 h-4" />
                        <span className="font-mono text-xs uppercase">Exceeds Plan</span>
                      </div>
                    ) : primaryPlan ? (
                      <div className="flex items-center gap-2 px-3 py-1 bg-success/10 text-success">
                        <CheckCircle2 className="w-4 h-4" />
                        <span className="font-mono text-xs uppercase">Within Plan</span>
                      </div>
                    ) : null}
                  </div>

                  {primaryPlan ? (
                    <div className="space-y-3">
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Annual Approved Envelope</span>
                        <span className="font-mono">{formatCurrency(ytdData?.annual_approved)}</span>
                      </div>
                      <div className="h-3 bg-navy/10">
                        <div 
                          className={`h-full transition-all ${ytdData?.exceeds_plan ? 'bg-error' : 'bg-navy'}`}
                          style={{ width: `${progressPercent}%` }}
                        ></div>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Remaining</span>
                        <span className={`font-mono ${ytdData?.remaining <= 0 ? 'text-error' : ''}`}>
                          {formatCurrency(ytdData?.remaining)}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-4">
                      <p className="text-muted-foreground mb-3">No compensation plan set for {currentYear}</p>
                      <Button onClick={openNewPrimaryPlan} className="btn-secondary">
                        Set Annual Compensation Plan
                      </Button>
                    </div>
                  )}
                </div>

                {/* Primary Plan Card */}
                <div className="card-trust">
                  <div className="flex items-center justify-between mb-4">
                    <p className="label-trust">{currentYear} Compensation Plan</p>
                    {primaryPlan && (
                      <Button 
                        variant="ghost" 
                        size="sm"
                        onClick={() => openEditPlan(primaryPlan)}
                        className="text-navy hover:text-gold"
                      >
                        <Edit2 className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                  
                  {primaryPlan ? (
                    <div className="space-y-4">
                      <div>
                        <p className="font-mono text-2xl text-navy">
                          {formatCurrency(primaryPlan.annual_approved_amount || primaryPlan.annual_fee)}
                        </p>
                        <p className="text-sm text-muted-foreground">Annual Approved Amount</p>
                      </div>
                      <div>
                        <p className="font-mono text-sm text-navy">
                          Effective: {formatDate(primaryPlan.effective_date)}
                        </p>
                      </div>
                      {primaryPlan.notes && (
                        <p className="text-sm text-muted-foreground">{primaryPlan.notes}</p>
                      )}
                      
                      {/* Helper text */}
                      <div className="pt-3 border-t border-border">
                        <p className="text-xs text-muted-foreground flex items-start gap-1.5">
                          <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
                          This is the total annual compensation envelope for this trust. Individual payments are tracked against this amount.
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-4">
                      <Wallet className="w-8 h-8 text-navy/30 mx-auto mb-2" />
                      <p className="text-sm text-muted-foreground mb-3">No plan configured</p>
                      <Button onClick={openNewPrimaryPlan} className="btn-secondary">
                        Create Plan
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              {/* Additional Plans Section (Advanced) */}
              {(additionalPlans.length > 0 || primaryPlan) && (
                <div className="card-trust mb-8">
                  <button 
                    onClick={() => setShowAdvancedPlans(!showAdvancedPlans)}
                    className="w-full flex items-center justify-between p-4 hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className="label-trust">Per-Trustee Compensation Caps (Optional)</span>
                      {additionalPlans.length > 0 && (
                        <span className="px-2 py-0.5 text-xs font-mono bg-navy/10 text-navy">
                          {additionalPlans.length} configured
                        </span>
                      )}
                    </div>
                    {showAdvancedPlans ? (
                      <ChevronUp className="w-4 h-4 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    )}
                  </button>
                  
                  {showAdvancedPlans && (
                    <div className="p-4 pt-0 border-t border-border">
                      <p className="text-xs text-muted-foreground mb-4 flex items-start gap-1.5">
                        <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
                        Set individual annual compensation limits for specific trustees. Useful when different trustees have different fee structures. The primary plan above tracks total trust compensation; these per-trustee caps provide additional oversight.
                      </p>
                      
                      {additionalPlans.length > 0 ? (
                        <div className="space-y-3 mb-4">
                          {additionalPlans.map(plan => (
                            <div 
                              key={plan.plan_id}
                              className="p-3 border border-navy/10 flex items-center justify-between"
                            >
                              <div>
                                <p className="font-medium text-navy">
                                  {plan.trustee_name || plan.role || 'Unnamed'}
                                </p>
                                <p className="text-sm text-muted-foreground">
                                  {formatCurrency(plan.annual_approved_amount)} • {formatDate(plan.effective_date)}
                                </p>
                              </div>
                              <div className="flex items-center gap-2">
                                <Button 
                                  variant="ghost" 
                                  size="sm"
                                  onClick={() => openEditPlan(plan)}
                                >
                                  <Edit2 className="w-4 h-4" />
                                </Button>
                                <Button 
                                  variant="ghost" 
                                  size="sm"
                                  onClick={() => handleDeletePlan(plan.plan_id)}
                                  className="text-error hover:text-error"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground mb-4">No trustee-specific plans configured.</p>
                      )}
                      
                      <Button 
                        variant="outline" 
                        onClick={openNewAdditionalPlan}
                        className="btn-secondary"
                      >
                        <Plus className="w-4 h-4 mr-2" /> Add Trustee-Specific Plan
                      </Button>
                    </div>
                  )}
                </div>
              )}

              {/* Payments List */}
              <div className="card-trust">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <p className="label-trust mb-1">Payment History</p>
                    <h2 className="font-serif text-xl text-navy">
                      {currentYear} Compensation Payments ({payments.filter(p => p.date?.startsWith(currentYear.toString())).length})
                    </h2>
                  </div>
                </div>

                {payments.length === 0 ? (
                  <div className="text-center py-8">
                    <Wallet className="w-12 h-12 text-navy/30 mx-auto mb-4" />
                    <h3 className="font-serif text-lg text-navy mb-2">No Payments Yet</h3>
                    <p className="text-muted-foreground mb-4">
                      Record your first compensation payment
                    </p>
                    <Button onClick={() => setShowPaymentModal(true)} className="btn-secondary">
                      Record Payment
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {payments.map(payment => (
                      <div 
                        key={payment.payment_id}
                        className={`p-4 border ${payment.exceeds_plan_flag ? 'border-error/30 bg-error/5' : 'border-navy/10'}`}
                        data-testid={`payment-${payment.payment_id}`}
                      >
                        <div className="flex items-start justify-between">
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="font-mono text-lg text-navy">{formatCurrency(payment.amount)}</p>
                              {payment.trustee_name && (
                                <span className="px-2 py-0.5 text-xs font-medium bg-navy/10 text-navy">
                                  {payment.trustee_name}
                                </span>
                              )}
                            </div>
                            <p className="text-sm text-muted-foreground mt-1">
                              {formatDate(payment.date)}
                              {payment.classification_text && ` • ${payment.classification_text}`}
                            </p>
                            {/* Minutes link indicator */}
                            {payment.minutes_record_id && (
                              <p className="text-xs text-green-600 dark:text-green-400 mt-1 flex items-center gap-1">
                                <Link2 className="w-3 h-3" /> Linked to minutes
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            {payment.exceeds_plan_flag && (
                              <span className="badge-trust badge-error flex items-center gap-1">
                                <AlertTriangle className="w-3 h-3" /> Exceeds
                              </span>
                            )}
                            {/* Minutes Actions */}
                            {!payment.minutes_record_id && (
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button variant="ghost" size="sm" data-testid={`minutes-menu-${payment.payment_id}`}>
                                    <MoreVertical className="w-4 h-4" />
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                  <DropdownMenuItem onClick={() => setAttachMinutesDialog({ open: true, recordId: payment.payment_id })}>
                                    <Link2 className="w-4 h-4 mr-2" />
                                    Link to existing minutes
                                  </DropdownMenuItem>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem onClick={() => {
                                    const params = new URLSearchParams({
                                      prefill_type: 'compensation',
                                      prefill_amount: payment.amount.toString(),
                                      prefill_recipient: payment.classification_text || 'Trustee',
                                      prefill_description: `Compensation payment on ${formatDate(payment.date)}`
                                    });
                                    navigate(`/minutes/create?${params.toString()}`);
                                  }}>
                                    <FileText className="w-4 h-4 mr-2" />
                                    Document in minutes (retroactive)
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            )}
                            <Button
                              onClick={() => handleDeletePayment(payment.payment_id)}
                              variant="ghost"
                              size="sm"
                              className="text-error hover:text-error hover:bg-error/10"
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* Plan Modal (Create/Edit) */}
      <Dialog open={showPlanModal} onOpenChange={setShowPlanModal}>
        <DialogContent className="sm:max-w-md" data-testid="plan-modal">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-navy">
              {editingPlan ? 'Edit Compensation Plan' : (planForm.is_primary ? 'Set Annual Compensation Plan' : 'Add Trustee-Specific Plan')}
            </DialogTitle>
            <DialogDescription>
              {planForm.is_primary 
                ? 'Set the total annual compensation envelope for this trust.'
                : 'Set a compensation cap for a specific trustee or role.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Trustee Name (only for non-primary) */}
            {!planForm.is_primary && (
              <div>
                <Label className="label-trust">Trustee / Role Name *</Label>
                <Input
                  value={planForm.trustee_name}
                  onChange={(e) => setPlanForm({ ...planForm, trustee_name: e.target.value })}
                  placeholder="e.g., John Smith or Executive Trustee"
                  className="input-trust mt-1"
                  data-testid="plan-trustee-name"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Identify which trustee or role this cap applies to
                </p>
              </div>
            )}

            <div>
              <Label className="label-trust">Annual Approved Amount *</Label>
              <Input
                type="number"
                value={planForm.annual_approved_amount}
                onChange={(e) => setPlanForm({ ...planForm, annual_approved_amount: e.target.value })}
                placeholder="e.g., 25000"
                className="input-trust mt-1"
                data-testid="plan-amount"
              />
            </div>

            <div>
              <Label className="label-trust">Effective Date</Label>
              <Input
                type="date"
                value={planForm.effective_date}
                onChange={(e) => setPlanForm({ ...planForm, effective_date: e.target.value })}
                className="input-trust mt-1"
              />
            </div>

            <div>
              <Label className="label-trust">Notes (Optional)</Label>
              <Textarea
                value={planForm.notes}
                onChange={(e) => setPlanForm({ ...planForm, notes: e.target.value })}
                placeholder="e.g., Approved by trust protector, per Article IV.2"
                className="input-trust mt-1"
                rows={2}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPlanModal(false)} className="btn-secondary">
              Cancel
            </Button>
            <Button onClick={handleSavePlan} className="btn-primary" data-testid="submit-plan-btn">
              {editingPlan ? 'Save Changes' : 'Create Plan'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Record Payment Modal */}
      <Dialog open={showPaymentModal} onOpenChange={setShowPaymentModal}>
        <DialogContent className="sm:max-w-md" data-testid="payment-modal">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-navy">Record Compensation Payment</DialogTitle>
            <DialogDescription>
              Record a trustee compensation payment. This will be tracked against the annual plan.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Trustee Selection */}
            <div>
              <Label className="label-trust">Recipient Trustee *</Label>
              <Select
                value={paymentForm.trustee_name}
                onValueChange={(value) => setPaymentForm({ ...paymentForm, trustee_name: value })}
              >
                <SelectTrigger className="input-trust mt-1" data-testid="payment-trustee-select">
                  <SelectValue placeholder="Select trustee..." />
                </SelectTrigger>
                <SelectContent>
                  {trustees.length > 0 ? (
                    trustees.map((trustee) => (
                      <SelectItem key={trustee} value={trustee}>
                        {trustee}
                      </SelectItem>
                    ))
                  ) : (
                    <SelectItem value="__other__" disabled>No trustees found</SelectItem>
                  )}
                  <SelectItem value="__other__">Other (specify in notes)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                Select which trustee is receiving this compensation payment
              </p>
            </div>

            <div>
              <Label className="label-trust">Amount *</Label>
              <Input
                type="number"
                value={paymentForm.amount}
                onChange={(e) => setPaymentForm({ ...paymentForm, amount: e.target.value })}
                placeholder="e.g., 5000"
                className="input-trust mt-1"
                data-testid="payment-amount"
              />
            </div>

            <div>
              <Label className="label-trust">Payment Date</Label>
              <Input
                type="date"
                value={paymentForm.date}
                onChange={(e) => setPaymentForm({ ...paymentForm, date: e.target.value })}
                className="input-trust mt-1"
              />
            </div>

            <div>
              <Label className="label-trust">Classification / Notes (Optional)</Label>
              <Input
                value={paymentForm.classification_text}
                onChange={(e) => setPaymentForm({ ...paymentForm, classification_text: e.target.value })}
                placeholder="e.g., Q1 trustee fee, Administrative services"
                className="input-trust mt-1"
              />
            </div>

            {/* Show warning if this would exceed plan */}
            {ytdData && paymentForm.amount && (
              (parseFloat(paymentForm.amount) + ytdData.ytd_total) > ytdData.annual_approved && ytdData.annual_approved > 0
            ) && (
              <div className="p-3 bg-warning/10 border border-warning/30 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-warning flex-shrink-0 mt-0.5" />
                <div className="text-sm">
                  <p className="font-medium text-warning">This payment will exceed the annual plan</p>
                  <p className="text-muted-foreground">
                    Current YTD: {formatCurrency(ytdData.ytd_total)} + {formatCurrency(parseFloat(paymentForm.amount))} = {formatCurrency(ytdData.ytd_total + parseFloat(paymentForm.amount))}
                    <br />
                    Annual Plan: {formatCurrency(ytdData.annual_approved)}
                  </p>
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPaymentModal(false)} className="btn-secondary">
              Cancel
            </Button>
            <Button onClick={handleCreatePayment} className="btn-primary" data-testid="submit-payment-btn">
              Record Payment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Attach Minutes Dialog */}
      <AttachMinutesDialog
        open={attachMinutesDialog.open}
        onOpenChange={(open) => setAttachMinutesDialog({ open, recordId: open ? attachMinutesDialog.recordId : null })}
        trustId={selectedTrust?.trust_id}
        recordType="compensation"
        recordId={attachMinutesDialog.recordId}
        onAttached={() => {
          loadData();
          setAttachMinutesDialog({ open: false, recordId: null });
        }}
      />
    </div>
  );
}
