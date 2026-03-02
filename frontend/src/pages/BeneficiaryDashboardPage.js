import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';
import { 
  Users,
  PieChart,
  Award,
  ArrowRight,
  TrendingUp,
  ArrowRightLeft,
  FileCheck,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

// Simple pie chart component using CSS conic-gradient
const OwnershipPieChart = ({ beneficiaries, totalAuthorized }) => {
  const colors = [
    '#010079', // navy
    '#D5AD36', // gold
    '#2563eb', // blue
    '#16a34a', // green
    '#dc2626', // red
    '#9333ea', // purple
    '#ea580c', // orange
    '#0891b2', // cyan
    '#4f46e5', // indigo
    '#be185d', // pink
  ];
  
  // Build conic gradient
  let gradientStops = [];
  let currentAngle = 0;
  
  beneficiaries.forEach((ben, index) => {
    const angle = (ben.percentage / 100) * 360;
    const color = colors[index % colors.length];
    gradientStops.push(`${color} ${currentAngle}deg ${currentAngle + angle}deg`);
    currentAngle += angle;
  });
  
  // Add remaining units if any
  const totalIssued = beneficiaries.reduce((sum, b) => sum + b.percentage, 0);
  if (totalIssued < 100) {
    gradientStops.push(`#e5e7eb ${currentAngle}deg 360deg`);
  }
  
  const gradient = `conic-gradient(${gradientStops.join(', ')})`;
  
  return (
    <div className="flex flex-col items-center">
      <div 
        className="w-48 h-48 rounded-full shadow-inner"
        style={{ background: gradient }}
      />
      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {beneficiaries.slice(0, 6).map((ben, index) => (
          <div key={ben.holder_name} className="flex items-center gap-2">
            <div 
              className="w-3 h-3 flex-shrink-0"
              style={{ backgroundColor: colors[index % colors.length] }}
            />
            <span className="truncate max-w-[120px]" title={ben.holder_name}>
              {ben.holder_name}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {ben.percentage.toFixed(1)}%
            </span>
          </div>
        ))}
        {beneficiaries.length > 6 && (
          <div className="col-span-2 text-muted-foreground text-xs mt-1">
            +{beneficiaries.length - 6} more holders
          </div>
        )}
        {totalIssued < 100 && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 flex-shrink-0 bg-gray-200" />
            <span>Unissued</span>
            <span className="font-mono text-xs text-muted-foreground">
              {(100 - totalIssued).toFixed(1)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default function BeneficiaryDashboardPage() {
  const { selectedTrust } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedHolder, setExpandedHolder] = useState(null);

  const loadData = useCallback(async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/beneficiaries/dashboard?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        setData(await response.json());
      } else {
        toast.error('Failed to load beneficiary data');
      }
    } catch (error) {
      console.error('Failed to load beneficiary dashboard:', error);
      toast.error('Failed to load beneficiary data');
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

  const toggleHolder = (holderName) => {
    setExpandedHolder(expandedHolder === holderName ? null : holderName);
  };

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Select a trust to view beneficiary allocations</p>
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
                Beneficiary Allocations
              </h1>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                {data?.trust_name || selectedTrust.name} • Ownership Distribution
              </p>
            </div>
            <Link to="/trust/units" className="mt-4 md:mt-0">
              <Button variant="outline" data-testid="manage-units-btn">
                <Award className="w-4 h-4 mr-2" />
                Manage Units
                <ArrowRight className="w-4 h-4 ml-2" />
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
              {/* Summary Row */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                <div className="card-trust p-4" data-testid="total-authorized-card">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-navy/10 dark:bg-gold/10 flex items-center justify-center">
                      <Award className="w-5 h-5 text-navy dark:text-gold" />
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Total Authorized</p>
                      <p className="font-serif text-2xl text-navy dark:text-foreground">{data.total_authorized_units}</p>
                    </div>
                  </div>
                </div>
                
                <div className="card-trust p-4" data-testid="issued-units-card">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                      <FileCheck className="w-5 h-5 text-green-700 dark:text-green-400" />
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Issued</p>
                      <p className="font-serif text-2xl text-navy dark:text-foreground">{data.total_issued_units}</p>
                    </div>
                  </div>
                </div>
                
                <div className="card-trust p-4" data-testid="remaining-units-card">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                      <PieChart className="w-5 h-5 text-blue-700 dark:text-blue-400" />
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Remaining</p>
                      <p className="font-serif text-2xl text-navy dark:text-foreground">{data.remaining_units}</p>
                    </div>
                  </div>
                </div>
                
                <div className="card-trust p-4" data-testid="beneficiaries-count-card">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                      <Users className="w-5 h-5 text-amber-700 dark:text-amber-400" />
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Beneficiaries</p>
                      <p className="font-serif text-2xl text-navy dark:text-foreground">{data.beneficiaries.length}</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Main Content - Pie Chart & Beneficiary List */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* Pie Chart */}
                <div className="card-trust p-6" data-testid="ownership-chart">
                  <div className="flex items-center gap-2 mb-6">
                    <PieChart className="w-4 h-4 text-navy dark:text-gold" />
                    <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Ownership Distribution</h2>
                  </div>
                  {data.beneficiaries.length > 0 ? (
                    <OwnershipPieChart 
                      beneficiaries={data.beneficiaries} 
                      totalAuthorized={data.total_authorized_units}
                    />
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      No certificates issued yet
                    </div>
                  )}
                </div>

                {/* Beneficiary List */}
                <div className="lg:col-span-2 card-trust overflow-hidden">
                  <div className="p-4 border-b border-border flex items-center gap-2">
                    <Users className="w-4 h-4 text-navy dark:text-gold" />
                    <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Certificate Holders</h2>
                  </div>
                  
                  {data.beneficiaries.length === 0 ? (
                    <div className="p-8 text-center">
                      <Users className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
                      <p className="text-muted-foreground">No beneficiaries yet</p>
                      <Link to="/trust/units">
                        <Button className="btn-primary mt-4">Issue First Certificate</Button>
                      </Link>
                    </div>
                  ) : (
                    <div className="divide-y divide-border">
                      {data.beneficiaries.map((ben, index) => (
                        <div key={ben.holder_name} data-testid={`beneficiary-row-${index}`}>
                          <button
                            onClick={() => toggleHolder(ben.holder_name)}
                            className="w-full p-4 flex items-center justify-between hover:bg-muted/20 transition-colors"
                          >
                            <div className="flex items-center gap-4">
                              <div className="w-10 h-10 bg-navy/10 dark:bg-gold/10 flex items-center justify-center font-serif text-navy dark:text-gold">
                                {index + 1}
                              </div>
                              <div className="text-left">
                                <p className="font-medium text-navy dark:text-foreground">{ben.holder_name}</p>
                                {ben.holder_identifier && (
                                  <p className="text-xs text-muted-foreground font-mono">{ben.holder_identifier}</p>
                                )}
                              </div>
                            </div>
                            <div className="flex items-center gap-6">
                              <div className="text-right">
                                <p className="font-mono text-lg text-navy dark:text-foreground">{ben.total_units}</p>
                                <p className="text-xs text-muted-foreground">{data.unit_label}s</p>
                              </div>
                              <div className="text-right min-w-[80px]">
                                <p className="font-mono text-lg text-gold">{ben.percentage.toFixed(2)}%</p>
                                <p className="text-xs text-muted-foreground">ownership</p>
                              </div>
                              {expandedHolder === ben.holder_name ? (
                                <ChevronUp className="w-5 h-5 text-muted-foreground" />
                              ) : (
                                <ChevronDown className="w-5 h-5 text-muted-foreground" />
                              )}
                            </div>
                          </button>
                          
                          {/* Expanded Certificate Details */}
                          {expandedHolder === ben.holder_name && (
                            <div className="bg-muted/30 p-4 border-t border-border">
                              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
                                {ben.certificate_count} Certificate{ben.certificate_count !== 1 ? 's' : ''}
                              </p>
                              <div className="space-y-2">
                                {ben.certificates.map((cert) => (
                                  <div 
                                    key={cert.certificate_id}
                                    className="flex items-center justify-between p-3 bg-background border border-border"
                                  >
                                    <div className="flex items-center gap-3">
                                      <span className="font-mono text-sm text-navy dark:text-gold">
                                        {cert.certificate_number}
                                      </span>
                                      <span className="text-sm text-muted-foreground">
                                        {cert.units} units
                                      </span>
                                    </div>
                                    <span className="text-xs text-muted-foreground font-mono">
                                      Issued {formatDate(cert.issue_date)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Recent Transfers */}
              {data.recent_transfers.length > 0 && (
                <div className="card-trust overflow-hidden">
                  <div className="p-4 border-b border-border flex items-center gap-2">
                    <ArrowRightLeft className="w-4 h-4 text-navy dark:text-gold" />
                    <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Recent Transfers</h2>
                  </div>
                  <div className="divide-y divide-border">
                    {data.recent_transfers.slice(0, 5).map((transfer) => (
                      <div key={transfer.transfer_id} className="p-4 flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                            <TrendingUp className="w-5 h-5 text-blue-700 dark:text-blue-400" />
                          </div>
                          <div>
                            <p className="font-medium text-navy dark:text-foreground">
                              {transfer.from_holder ? (
                                <>{transfer.from_holder} → {transfer.to_holder}</>
                              ) : (
                                <>New issuance to {transfer.to_holder}</>
                              )}
                            </p>
                            <p className="text-xs text-muted-foreground">{transfer.reason}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="font-mono text-navy dark:text-foreground">{transfer.units} units</p>
                          <p className="text-xs text-muted-foreground font-mono">{formatDate(transfer.created_at)}</p>
                        </div>
                      </div>
                    ))}
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
