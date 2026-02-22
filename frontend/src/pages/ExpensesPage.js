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
  Receipt,
  Check,
  X,
  Clock
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

export default function ExpensesPage() {
  const { selectedTrust } = useAuth();
  const [expenses, setExpenses] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  
  const [formData, setFormData] = useState({
    date: new Date(),
    amount: '',
    payee: '',
    category: '',
    notes: '',
    status: 'review'
  });

  useEffect(() => {
    loadCategories();
  }, []);

  useEffect(() => {
    if (selectedTrust) {
      loadExpenses();
    }
  }, [selectedTrust]);

  const loadCategories = async () => {
    try {
      const response = await fetch(`${API}/categories`);
      if (response.ok) {
        const data = await response.json();
        setCategories(data.expense_categories || []);
      }
    } catch (error) {
      console.error('Failed to load categories:', error);
    }
  };

  const loadExpenses = async () => {
    if (!selectedTrust) return;
    
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/expenses?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        setExpenses(await response.json());
      }
    } catch (error) {
      console.error('Failed to load expenses:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateExpense = async () => {
    if (!selectedTrust) {
      toast.error('Please select a trust first');
      return;
    }

    if (!formData.amount || !formData.payee || !formData.category) {
      toast.error('Please fill in all required fields');
      return;
    }

    setFormLoading(true);
    try {
      const response = await fetchWithAuth('/expenses', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          date: formData.date.toISOString(),
          amount: parseFloat(formData.amount),
          payee: formData.payee,
          category: formData.category,
          notes: formData.notes || null,
          status: formData.status
        })
      });

      if (!response.ok) {
        throw new Error('Failed to create expense');
      }

      toast.success('Expense created');
      setDialogOpen(false);
      setFormData({
        date: new Date(),
        amount: '',
        payee: '',
        category: '',
        notes: '',
        status: 'review'
      });
      loadExpenses();
    } catch (error) {
      toast.error(error.message);
    } finally {
      setFormLoading(false);
    }
  };

  const handleUpdateStatus = async (expenseId, newStatus) => {
    try {
      const response = await fetchWithAuth(`/expenses/${expenseId}?status=${newStatus}`, {
        method: 'PUT'
      });

      if (!response.ok) {
        throw new Error('Failed to update status');
      }

      toast.success(`Status updated to ${newStatus}`);
      loadExpenses();
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

  const filteredExpenses = expenses.filter(e => {
    const matchesSearch = 
      e.payee.toLowerCase().includes(searchTerm.toLowerCase()) ||
      e.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (e.notes && e.notes.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesStatus = filterStatus === 'all' || e.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  const totalAmount = filteredExpenses.reduce((sum, e) => sum + e.amount, 0);
  const pendingCount = expenses.filter(e => e.status === 'review').length;

  return (
    <div className="main-layout" data-testid="expenses-page">
      <Sidebar />
      <main className="main-content">
        <div className="page-container">
          {/* Page Header */}
          <div className="flex items-start justify-between mb-8">
            <div>
              <h1 className="page-title">Expenses</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'}
              </p>
            </div>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button className="btn-primary" data-testid="add-expense-btn">
                  <Plus className="w-4 h-4 mr-2" />
                  Add Expense
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                  <DialogTitle className="font-serif text-2xl text-navy">New Expense</DialogTitle>
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
                            data-testid="expense-date-picker"
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
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                        <Input
                          type="number"
                          step="0.01"
                          value={formData.amount}
                          onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                          className="pl-8 input-trust"
                          placeholder="0.00"
                          data-testid="expense-amount-input"
                        />
                      </div>
                    </div>
                  </div>

                  <div>
                    <Label className="label-trust">Payee *</Label>
                    <Input
                      value={formData.payee}
                      onChange={(e) => setFormData({ ...formData, payee: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="Payee name or company"
                      data-testid="expense-payee-input"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Category *</Label>
                      <Select 
                        value={formData.category} 
                        onValueChange={(value) => setFormData({ ...formData, category: value })}
                      >
                        <SelectTrigger className="mt-1 input-trust" data-testid="expense-category-select">
                          <SelectValue placeholder="Select category" />
                        </SelectTrigger>
                        <SelectContent>
                          {categories.map((cat) => (
                            <SelectItem key={cat} value={cat}>{cat}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Status</Label>
                      <Select 
                        value={formData.status} 
                        onValueChange={(value) => setFormData({ ...formData, status: value })}
                      >
                        <SelectTrigger className="mt-1 input-trust" data-testid="expense-status-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="review">Pending Review</SelectItem>
                          <SelectItem value="approved">Approved</SelectItem>
                          <SelectItem value="declined">Declined</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div>
                    <Label className="label-trust">Notes</Label>
                    <Textarea
                      value={formData.notes}
                      onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="Additional notes..."
                      data-testid="expense-notes-input"
                    />
                  </div>

                  <Button
                    onClick={handleCreateExpense}
                    disabled={formLoading}
                    className="w-full btn-primary"
                    data-testid="submit-expense-btn"
                  >
                    {formLoading ? 'Creating...' : 'Create Expense'}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="card-trust">
              <p className="label-trust">Total Expenses</p>
              <p className="font-mono text-3xl text-navy mt-2">{formatCurrency(totalAmount)}</p>
            </div>
            <div className="card-trust">
              <p className="label-trust">Total Records</p>
              <p className="font-mono text-3xl text-navy mt-2">{expenses.length}</p>
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
                  placeholder="Search expenses..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10 input-trust"
                  data-testid="search-expenses"
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
          ) : filteredExpenses.length === 0 ? (
            <div className="empty-state">
              <Receipt className="w-16 h-16 text-navy/20 mx-auto mb-4" />
              <h2 className="font-serif text-2xl text-navy mb-2">No Expenses Found</h2>
              <p className="text-muted-foreground mb-6">
                {searchTerm ? 'Try a different search term' : 'Add your first expense to get started'}
              </p>
              <Button onClick={() => setDialogOpen(true)} className="btn-primary">
                Add Expense
              </Button>
            </div>
          ) : (
            <div className="card-trust overflow-x-auto">
              <table className="w-full trust-table">
                <thead>
                  <tr>
                    <th className="text-left">Date</th>
                    <th className="text-left">Payee</th>
                    <th className="text-left">Category</th>
                    <th className="text-right">Amount</th>
                    <th className="text-center">Status</th>
                    <th className="text-center">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredExpenses.map((expense) => (
                    <tr key={expense.expense_id} data-testid={`expense-row-${expense.expense_id}`}>
                      <td>{formatDate(expense.date)}</td>
                      <td>{expense.payee}</td>
                      <td>{expense.category}</td>
                      <td className="text-right font-mono">{formatCurrency(expense.amount)}</td>
                      <td className="text-center">
                        <span className={`badge-trust ${getStatusBadgeClass(expense.status)}`}>
                          {expense.status}
                        </span>
                      </td>
                      <td className="text-center">
                        {expense.status === 'review' && (
                          <div className="flex justify-center gap-2">
                            <button
                              onClick={() => handleUpdateStatus(expense.expense_id, 'approved')}
                              className="p-1 hover:bg-success/10 text-success"
                              title="Approve"
                              data-testid={`approve-${expense.expense_id}`}
                            >
                              <Check className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleUpdateStatus(expense.expense_id, 'declined')}
                              className="p-1 hover:bg-error/10 text-error"
                              title="Decline"
                              data-testid={`decline-${expense.expense_id}`}
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        )}
                        {expense.status !== 'review' && (
                          <button
                            onClick={() => handleUpdateStatus(expense.expense_id, 'review')}
                            className="p-1 hover:bg-warning/10 text-warning"
                            title="Set to Review"
                          >
                            <Clock className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
