import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import { 
  HeartHandshake,
  DollarSign,
  Calendar,
  TrendingUp,
  Search,
  Filter,
  ExternalLink,
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText
} from 'lucide-react';
import { format, parseISO, startOfMonth, endOfMonth, startOfYear, endOfYear } from 'date-fns';

export default function BenevolenceLogPage() {
  const { selectedTrust } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchRecipient, setSearchRecipient] = useState('');
  const [dateFilter, setDateFilter] = useState('all');

  const loadData = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/benevolence-log?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        setData(await response.json());
      } else {
        toast.error('Failed to load benevolence log');
      }
    } catch (error) {
      console.error('Failed to load benevolence log:', error);
      toast.error('Failed to load benevolence log');
    } finally {
      setLoading(false);
    }
  }, [selectedTrust]);

  useEffect(() => {
    if (selectedTrust) {
      loadData();
    }
  }, [selectedTrust, loadData]);

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      return format(parseISO(dateStr), 'MMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  // Calculate filtered distributions
  const getFilteredDistributions = () => {
    if (!data?.distributions) return [];
    
    let filtered = data.distributions;
    
    // Filter by recipient
    if (searchRecipient) {
      const search = searchRecipient.toLowerCase();
      filtered = filtered.filter(d => 
        d.benevolence_recipient_name?.toLowerCase().includes(search) ||
        d.beneficiary_name?.toLowerCase().includes(search)
      );
    }
    
    // Filter by date range
    const now = new Date();
    if (dateFilter === 'this_month') {
      const monthStart = startOfMonth(now);
      const monthEnd = endOfMonth(now);
      filtered = filtered.filter(d => {
        const date = parseISO(d.date);
        return date >= monthStart && date <= monthEnd;
      });
    } else if (dateFilter === 'this_year') {
      const yearStart = startOfYear(now);
      const yearEnd = endOfYear(now);
      filtered = filtered.filter(d => {
        const date = parseISO(d.date);
        return date >= yearStart && date <= yearEnd;
      });
    } else if (dateFilter === 'last_month') {
      const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const monthStart = startOfMonth(lastMonth);
      const monthEnd = endOfMonth(lastMonth);
      filtered = filtered.filter(d => {
        const date = parseISO(d.date);
        return date >= monthStart && date <= monthEnd;
      });
    }
    
    return filtered;
  };

  // Calculate current month/year totals
  const getCurrentMonthTotal = () => {
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const monthData = data?.monthly_aggregates?.find(m => m.month === currentMonth);
    return monthData?.total_amount || 0;
  };

  const getCurrentYearTotal = () => {
    const currentYear = new Date().getFullYear();
    const yearData = data?.yearly_aggregates?.find(y => y.year === currentYear);
    return yearData?.total_amount || 0;
  };

  const filteredDistributions = getFilteredDistributions();

  const getStatusIcon = (dist) => {
    if (dist.approved_at || dist.minutes_record_id) {
      return <CheckCircle2 className="w-4 h-4 text-success" />;
    }
    return <Clock className="w-4 h-4 text-warning" />;
  };

  const getStatusText = (dist) => {
    if (dist.approved_at) return 'Approved';
    if (dist.minutes_record_id) return 'Documented';
    return 'Pending';
  };

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Select a trust to view benevolence log</p>
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
              <h1 className="font-serif text-3xl lg:text-4xl text-navy dark:text-gold mb-2" data-testid="page-title">
                Benevolence Log
              </h1>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                {data?.trust_name || selectedTrust.name} • Charitable Distributions
              </p>
            </div>
            <Link to="/distributions" className="mt-4 md:mt-0">
              <Button variant="outline" data-testid="all-distributions-btn">
                <DollarSign className="w-4 h-4 mr-2" />
                All Distributions
              </Button>
            </Link>
          </div>

          {loading ? (
            <div className="card-trust p-8 text-center">
              <div className="w-8 h-8 border-2 border-navy dark:border-gold border-t-transparent animate-spin mx-auto mb-4"></div>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading...</p>
            </div>
          ) : !data ? (
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">No data available</p>
            </div>
          ) : (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                <div className="card-trust p-4" data-testid="this-month-card">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gold/20 flex items-center justify-center">
                      <Calendar className="w-5 h-5 text-gold" />
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">This Month</p>
                      <p className="font-serif text-2xl text-navy dark:text-foreground">
                        {formatCurrency(getCurrentMonthTotal())}
                      </p>
                    </div>
                  </div>
                </div>
                
                <div className="card-trust p-4" data-testid="this-year-card">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                      <TrendingUp className="w-5 h-5 text-blue-700 dark:text-blue-400" />
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">This Year</p>
                      <p className="font-serif text-2xl text-navy dark:text-foreground">
                        {formatCurrency(getCurrentYearTotal())}
                      </p>
                    </div>
                  </div>
                </div>
                
                <div className="card-trust p-4" data-testid="all-time-card">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                      <HeartHandshake className="w-5 h-5 text-green-700 dark:text-green-400" />
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">All Time</p>
                      <p className="font-serif text-2xl text-navy dark:text-foreground">
                        {formatCurrency(data.total_all_time)}
                      </p>
                    </div>
                  </div>
                </div>
                
                <div className="card-trust p-4" data-testid="incomplete-card">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 flex items-center justify-center ${
                      data.incomplete_documentation_count > 0 
                        ? 'bg-warning/20' 
                        : 'bg-success/20'
                    }`}>
                      {data.incomplete_documentation_count > 0 ? (
                        <AlertCircle className="w-5 h-5 text-warning" />
                      ) : (
                        <CheckCircle2 className="w-5 h-5 text-success" />
                      )}
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Documentation</p>
                      <p className={`font-serif text-2xl ${
                        data.incomplete_documentation_count > 0 
                          ? 'text-warning' 
                          : 'text-success'
                      }`}>
                        {data.incomplete_documentation_count > 0 
                          ? `${data.incomplete_documentation_count} Pending`
                          : 'Complete'
                        }
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Documentation Warning */}
              {data.incomplete_documentation_count > 0 && (
                <div className="mb-6 p-4 border border-warning/30 bg-warning/5 flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-warning">Incomplete Documentation</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      {data.incomplete_documentation_count} benevolence distribution{data.incomplete_documentation_count !== 1 ? 's' : ''} need 
                      approval or minutes documentation. Complete documentation improves your governance health score.
                    </p>
                  </div>
                </div>
              )}

              {/* Filters */}
              <div className="card-trust mb-6">
                <div className="p-4 flex flex-col sm:flex-row gap-4">
                  <div className="flex-1">
                    <Label className="label-trust">Search Recipient</Label>
                    <div className="relative mt-1">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <Input
                        value={searchRecipient}
                        onChange={(e) => setSearchRecipient(e.target.value)}
                        placeholder="Search by recipient name..."
                        className="pl-10"
                        data-testid="search-recipient"
                      />
                    </div>
                  </div>
                  <div className="w-full sm:w-48">
                    <Label className="label-trust">Date Range</Label>
                    <Select value={dateFilter} onValueChange={setDateFilter}>
                      <SelectTrigger className="mt-1" data-testid="date-filter">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Time</SelectItem>
                        <SelectItem value="this_month">This Month</SelectItem>
                        <SelectItem value="last_month">Last Month</SelectItem>
                        <SelectItem value="this_year">This Year</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>

              {/* Benevolence Distributions Table */}
              <div className="card-trust overflow-hidden">
                <div className="p-4 border-b border-border flex items-center gap-2">
                  <HeartHandshake className="w-4 h-4 text-navy dark:text-gold" />
                  <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                    Benevolence Distributions ({filteredDistributions.length})
                  </h2>
                </div>
                
                {filteredDistributions.length === 0 ? (
                  <div className="p-8 text-center">
                    <HeartHandshake className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
                    <p className="text-muted-foreground">
                      {data.total_count === 0 
                        ? 'No benevolence distributions yet'
                        : 'No distributions match your filters'
                      }
                    </p>
                    {data.total_count === 0 && (
                      <Link to="/distributions">
                        <Button className="btn-primary mt-4">
                          Create Benevolence Distribution
                        </Button>
                      </Link>
                    )}
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full" data-testid="benevolence-table">
                      <thead>
                        <tr className="border-b border-border bg-muted/30">
                          <th className="text-left p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Recipient</th>
                          <th className="text-right p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Amount</th>
                          <th className="text-left p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Date</th>
                          <th className="text-left p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Need/Purpose</th>
                          <th className="text-left p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Status</th>
                          <th className="text-right p-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredDistributions.map((dist) => (
                          <tr key={dist.distribution_id} className="border-b border-border hover:bg-muted/20" data-testid={`dist-row-${dist.distribution_id}`}>
                            <td className="p-3">
                              <div>
                                <p className="font-medium text-navy dark:text-foreground">
                                  {dist.benevolence_recipient_name || dist.beneficiary_name}
                                </p>
                                {dist.benevolence_recipient_name && dist.benevolence_recipient_name !== dist.beneficiary_name && (
                                  <p className="text-xs text-muted-foreground">via {dist.beneficiary_name}</p>
                                )}
                              </div>
                            </td>
                            <td className="p-3 text-right">
                              <span className="font-mono text-lg text-navy dark:text-foreground">
                                {formatCurrency(dist.amount)}
                              </span>
                            </td>
                            <td className="p-3">
                              <span className="font-mono text-sm text-muted-foreground">
                                {formatDate(dist.date)}
                              </span>
                            </td>
                            <td className="p-3">
                              <p className="text-sm text-muted-foreground line-clamp-2 max-w-[200px]">
                                {dist.benevolence_need_description || dist.notes || '—'}
                              </p>
                            </td>
                            <td className="p-3">
                              <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-mono uppercase ${
                                dist.approved_at || dist.minutes_record_id
                                  ? 'bg-success/20 text-success'
                                  : 'bg-warning/20 text-warning'
                              }`}>
                                {getStatusIcon(dist)}
                                {getStatusText(dist)}
                              </span>
                            </td>
                            <td className="p-3 text-right">
                              <Link 
                                to={`/distributions?highlight=${dist.distribution_id}`}
                                className="inline-flex items-center gap-1 text-navy dark:text-gold hover:underline text-sm"
                                data-testid={`view-dist-${dist.distribution_id}`}
                              >
                                <FileText className="w-4 h-4" />
                                View
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Monthly Breakdown */}
              {data.monthly_aggregates.length > 0 && (
                <div className="mt-8 card-trust overflow-hidden">
                  <div className="p-4 border-b border-border flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-navy dark:text-gold" />
                    <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                      Monthly Breakdown
                    </h2>
                  </div>
                  <div className="p-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                      {data.monthly_aggregates.slice(0, 12).map((month) => (
                        <div key={month.month} className="p-3 border border-border">
                          <p className="font-mono text-xs text-muted-foreground">{month.month}</p>
                          <p className="font-serif text-lg text-navy dark:text-foreground mt-1">
                            {formatCurrency(month.total_amount)}
                          </p>
                          <p className="text-xs text-muted-foreground">{month.count} distribution{month.count !== 1 ? 's' : ''}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
