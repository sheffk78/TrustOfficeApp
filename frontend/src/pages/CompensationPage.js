import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { 
  Wallet, 
  Plus, 
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  X,
  Trash2
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { toast } from 'sonner';

export default function CompensationPage() {
  const { selectedTrust } = useAuth();
  const [plans, setPlans] = useState([]);
  const [payments, setPayments] = useState([]);
  const [ytdData, setYtdData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [newPlan, setNewPlan] = useState({
    annual_approved_amount: '',
    effective_date: format(new Date(), 'yyyy-MM-dd'),
    notes: ''
  });
  const [newPayment, setNewPayment] = useState({
    amount: '',
    date: format(new Date(), 'yyyy-MM-dd'),
    classification_text: ''
  });

  useEffect(() => {
    if (selectedTrust) {
      loadData();
    }
  }, [selectedTrust]);

  const loadData = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const [plansRes, paymentsRes, ytdRes] = await Promise.all([
        fetchWithAuth(`/compensation-plans?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/compensation-payments?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/compensation-ytd?trust_id=${selectedTrust.trust_id}`)
      ]);
      
      if (plansRes.ok) setPlans(await plansRes.json());
      if (paymentsRes.ok) setPayments(await paymentsRes.json());
      if (ytdRes.ok) setYtdData(await ytdRes.json());
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePlan = async () => {
    if (!selectedTrust || !newPlan.annual_approved_amount) {
      toast.error('Annual amount is required');
      return;
    }
    try {
      const response = await fetchWithAuth('/compensation-plans', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          annual_approved_amount: parseFloat(newPlan.annual_approved_amount),
          effective_date: newPlan.effective_date,
          notes: newPlan.notes
        })
      });
      if (response.ok) {
        toast.success('Plan created');
        setShowPlanModal(false);
        setNewPlan({
          annual_approved_amount: '',
          effective_date: format(new Date(), 'yyyy-MM-dd'),
          notes: ''
        });
        loadData();
      }
    } catch (error) {
      toast.error('Failed to create plan');
    }
  };

  const handleCreatePayment = async () => {
    if (!selectedTrust || !newPayment.amount) {
      toast.error('Amount is required');
      return;
    }
    try {
      const response = await fetchWithAuth('/compensation-payments', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          amount: parseFloat(newPayment.amount),
          date: newPayment.date,
          classification_text: newPayment.classification_text
        })
      });
      if (response.ok) {
        toast.success('Payment recorded');
        setShowPaymentModal(false);
        setNewPayment({
          amount: '',
          date: format(new Date(), 'yyyy-MM-dd'),
          classification_text: ''
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

  const currentPlan = plans.length > 0 ? plans[0] : null;
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
            <div className="flex gap-3">
              <Button 
                onClick={() => setShowPlanModal(true)} 
                variant="outline"
                className="btn-secondary"
                data-testid="create-plan-btn"
              >
                <Plus className="w-4 h-4 mr-2" /> New Plan
              </Button>
              <Button 
                onClick={() => setShowPaymentModal(true)} 
                className="btn-primary"
                data-testid="record-payment-btn"
              >
                <Plus className="w-4 h-4 mr-2" /> Record Payment
              </Button>
            </div>
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
              {/* YTD Summary */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                <div className="lg:col-span-2 card-trust corner-mark">
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <p className="label-trust mb-1">Year-to-Date Compensation</p>
                      <h2 className="font-serif text-3xl text-navy">
                        {ytdData ? formatCurrency(ytdData.ytd_total) : '$0.00'}
                      </h2>
                    </div>
                    {ytdData?.exceeds_plan ? (
                      <div className="flex items-center gap-2 px-3 py-1 bg-error/10 text-error">
                        <AlertTriangle className="w-4 h-4" />
                        <span className="font-mono text-xs uppercase">Exceeds Plan</span>
                      </div>
                    ) : ytdData?.annual_approved ? (
                      <div className="flex items-center gap-2 px-3 py-1 bg-success/10 text-success">
                        <CheckCircle2 className="w-4 h-4" />
                        <span className="font-mono text-xs uppercase">Within Plan</span>
                      </div>
                    ) : null}
                  </div>

                  {currentPlan && (
                    <div className="space-y-3">
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Annual Approved</span>
                        <span className="font-mono">{formatCurrency(currentPlan.annual_approved_amount)}</span>
                      </div>
                      <div className="h-3 bg-navy/10">
                        <div 
                          className={`h-full transition-all ${ytdData?.exceeds_plan ? 'bg-error' : 'bg-navy'}`}
                          style={{ width: `${progressPercent}%` }}
                        ></div>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Remaining</span>
                        <span className="font-mono">{formatCurrency(ytdData?.remaining || 0)}</span>
                      </div>
                    </div>
                  )}

                  {!currentPlan && (
                    <div className="text-center py-4">
                      <p className="text-muted-foreground mb-3">No compensation plan set</p>
                      <Button onClick={() => setShowPlanModal(true)} className="btn-secondary">
                        Create Plan
                      </Button>
                    </div>
                  )}
                </div>

                <div className="card-trust">
                  <p className="label-trust mb-4">Current Plan</p>
                  {currentPlan ? (
                    <div className="space-y-4">
                      <div>
                        <p className="font-mono text-2xl text-navy">
                          {formatCurrency(currentPlan.annual_approved_amount)}
                        </p>
                        <p className="text-sm text-muted-foreground">Annual Amount</p>
                      </div>
                      <div>
                        <p className="font-mono text-sm text-navy">
                          Effective: {formatDate(currentPlan.effective_date)}
                        </p>
                      </div>
                      {currentPlan.notes && (
                        <p className="text-sm text-muted-foreground">{currentPlan.notes}</p>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-4">
                      <Wallet className="w-8 h-8 text-navy/30 mx-auto mb-2" />
                      <p className="text-sm text-muted-foreground">No plan configured</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Payments List */}
              <div className="card-trust">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <p className="label-trust mb-1">Payment History</p>
                    <h2 className="font-serif text-xl text-navy">Compensation Payments</h2>
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
                            <p className="font-mono text-lg text-navy">{formatCurrency(payment.amount)}</p>
                            <p className="text-sm text-muted-foreground mt-1">
                              {formatDate(payment.date)}
                              {payment.classification_text && ` • ${payment.classification_text}`}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            {payment.exceeds_plan_flag && (
                              <span className="badge-trust badge-error flex items-center gap-1">
                                <AlertTriangle className="w-3 h-3" /> Exceeds
                              </span>
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

      {/* Create Plan Modal */}
      {showPlanModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white p-6 w-full max-w-md corner-mark" data-testid="create-plan-modal">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-serif text-xl text-navy">Create Compensation Plan</h2>
              <button onClick={() => setShowPlanModal(false)} className="text-navy hover:text-gold">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="label-trust mb-2 block">Annual Approved Amount *</label>
                <Input
                  type="number"
                  value={newPlan.annual_approved_amount}
                  onChange={(e) => setNewPlan({ ...newPlan, annual_approved_amount: e.target.value })}
                  placeholder="e.g., 25000"
                  className="input-trust"
                  data-testid="plan-amount"
                />
              </div>

              <div>
                <label className="label-trust mb-2 block">Effective Date</label>
                <Input
                  type="date"
                  value={newPlan.effective_date}
                  onChange={(e) => setNewPlan({ ...newPlan, effective_date: e.target.value })}
                  className="input-trust"
                />
              </div>

              <div>
                <label className="label-trust mb-2 block">Notes (Optional)</label>
                <Input
                  value={newPlan.notes}
                  onChange={(e) => setNewPlan({ ...newPlan, notes: e.target.value })}
                  placeholder="e.g., Approved by trust protector"
                  className="input-trust"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <Button onClick={() => setShowPlanModal(false)} variant="outline" className="flex-1 btn-secondary">
                  Cancel
                </Button>
                <Button onClick={handleCreatePlan} className="flex-1 btn-primary" data-testid="submit-plan-btn">
                  Create Plan
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Record Payment Modal */}
      {showPaymentModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white p-6 w-full max-w-md corner-mark" data-testid="record-payment-modal">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-serif text-xl text-navy">Record Payment</h2>
              <button onClick={() => setShowPaymentModal(false)} className="text-navy hover:text-gold">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="label-trust mb-2 block">Amount *</label>
                <Input
                  type="number"
                  value={newPayment.amount}
                  onChange={(e) => setNewPayment({ ...newPayment, amount: e.target.value })}
                  placeholder="e.g., 6250"
                  className="input-trust"
                  data-testid="payment-amount"
                />
              </div>

              <div>
                <label className="label-trust mb-2 block">Date</label>
                <Input
                  type="date"
                  value={newPayment.date}
                  onChange={(e) => setNewPayment({ ...newPayment, date: e.target.value })}
                  className="input-trust"
                />
              </div>

              <div>
                <label className="label-trust mb-2 block">Classification (Optional)</label>
                <Input
                  value={newPayment.classification_text}
                  onChange={(e) => setNewPayment({ ...newPayment, classification_text: e.target.value })}
                  placeholder="e.g., Q1 2026 trustee services"
                  className="input-trust"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <Button onClick={() => setShowPaymentModal(false)} variant="outline" className="flex-1 btn-secondary">
                  Cancel
                </Button>
                <Button onClick={handleCreatePayment} className="flex-1 btn-primary" data-testid="submit-payment-btn">
                  Record Payment
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
