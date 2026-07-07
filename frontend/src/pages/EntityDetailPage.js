import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { SeparationAlertsPanel } from '@/components/SeparationAlertsPanel';
import BankAccountsSection from '@/components/BankAccountsSection';
import PageHelpButton from '@/components/PageHelpButton';
import { 
  ArrowLeft, 
  Save,
  Trash2,
  Landmark,
  Building2,
  Building,
  ArrowUpRight,
  ArrowDownLeft,
  FileSpreadsheet,
  Loader2
} from 'lucide-react';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { format, parseISO } from 'date-fns';

export default function EntityDetailPage() {
  const { entityId } = useParams();
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [entity, setEntity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({});
  const [entityTxns, setEntityTxns] = useState([]);
  const [txnLoading, setTxnLoading] = useState(false);

  useEffect(() => {
    if (entityId) {
      loadEntity();
      loadEntityTransactions();
    }
  }, [entityId]);

  const loadEntityTransactions = async () => {
    if (!selectedTrust || !entityId) return;
    setTxnLoading(true);
    try {
      const res = await fetchWithAuth(`/transactions?trust_id=${selectedTrust.trust_id}&entity_id=${entityId}&limit=20`);
      if (res.ok) setEntityTxns(await res.json());
    } catch { /* ignore */ } finally { setTxnLoading(false); }
  };

  const loadEntity = async () => {
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/entities/${entityId}`);
      if (response.ok) {
        const data = await response.json();
        setEntity(data);
        setFormData(data);
      } else {
        toast.error('Entity not found');
        navigate('/entities');
      }
    } catch (error) {
      console.error('Failed to load entity:', error);
      navigate('/entities');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetchWithAuth(`/entities/${entityId}`, {
        method: 'PATCH',
        body: JSON.stringify(formData)
      });
      if (response.ok) {
        toast.success('Entity saved');
        const data = await response.json();
        setEntity(data);
      } else {
        showError(toast, error, { operation: 'save', page: 'EntityDetail' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'save', page: 'EntityDetail' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this entity? This action cannot be undone.')) {
      return;
    }
    try {
      const response = await fetchWithAuth(`/entities/${entityId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        toast.success('Entity deleted');
        navigate('/entities');
      } else {
        showError(toast, error, { operation: 'delete', page: 'EntityDetail' });
      }
    } catch (error) {
      showError(toast, error, { operation: 'delete', page: 'EntityDetail' });
    }
  };

  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const getEntityIcon = (type) => {
    switch (type) {
      case 'Trust': return <Landmark className="w-6 h-6" />;
      case 'Holding LLC': return <Building2 className="w-6 h-6" />;
      case 'Operating LLC': return <Building className="w-6 h-6" />;
      default: return <Building2 className="w-6 h-6" />;
    }
  };

  const isTrust = entity?.entity_type === 'Trust';
  const isLLC = entity?.entity_type?.includes('LLC');

  if (loading) {
    return (
      <div className="main-layout" data-testid="entity-detail-page">
        <Sidebar />
        <main className="main-content dot-grid">
          <div className="page-container">
            <div className="skeleton h-8 w-48 mb-4"></div>
            <div className="card-trust">
              <div className="skeleton h-6 w-full mb-4"></div>
              <div className="skeleton h-6 w-3/4"></div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="main-layout" data-testid="entity-detail-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Back Button */}
          <Button 
            onClick={() => navigate('/entities')}
            variant="ghost"
            className="mb-4 text-navy hover:text-navy/70"
          >
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Entities
          </Button>

          {/* Page Header */}
          <div className="page-header flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-navy/10 flex items-center justify-center text-navy flex-shrink-0">
                {getEntityIcon(entity?.entity_type)}
              </div>
              <div className="min-w-0">
                <h1 className="page-title truncate">{entity?.name}</h1>
                <p className="page-subtitle">View and manage entity details — update information, track relationships, and maintain accurate trust records</p>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <PageHelpButton
                items={[
                  { text: 'View and manage entity details including type, status, and relationships' },
                  { text: 'Update entity information and track changes over time' },
                  { text: 'Maintain accurate records of all trust-related entities' },
                ]}
                taPrompt="Help me understand the Entity Detail page"
              />
              <Button 
                onClick={handleDelete}
                variant="outline"
                className="text-error border-error hover:bg-error/10"
              >
                <Trash2 className="w-4 h-4 mr-2" /> Delete
              </Button>
              <Button 
                onClick={handleSave}
                className="btn-primary"
                disabled={saving}
                data-testid="save-entity-btn"
              >
                <Save className="w-4 h-4 mr-2" /> {saving ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Basic Information */}
            <div className="card-trust">
              <h2 className="font-serif text-lg text-navy mb-4">Basic Information</h2>
              <div className="space-y-4">
                <div>
                  <label className="label-trust mb-2 block">Display Name</label>
                  <Input
                    value={formData.name || ''}
                    onChange={(e) => updateField('name', e.target.value)}
                    className="input-trust"
                    data-testid="entity-edit-name"
                  />
                </div>
                <div>
                  <label className="label-trust mb-2 block">Legal Name</label>
                  <Input
                    value={formData.legal_name || ''}
                    onChange={(e) => updateField('legal_name', e.target.value)}
                    className="input-trust"
                  />
                </div>
                <div>
                  <label className="label-trust mb-2 block">EIN</label>
                  <Input
                    value={formData.ein || ''}
                    onChange={(e) => updateField('ein', e.target.value)}
                    placeholder="XX-XXXXXXX"
                    className="input-trust"
                  />
                </div>
                <div>
                  <label className="label-trust mb-2 block">Formation Date</label>
                  <Input
                    type="date"
                    value={formData.formation_date || ''}
                    onChange={(e) => updateField('formation_date', e.target.value)}
                    className="input-trust"
                  />
                </div>
                <div>
                  <label className="label-trust mb-2 block">Governing Law / State</label>
                  <Input
                    value={formData.governing_law || ''}
                    onChange={(e) => updateField('governing_law', e.target.value)}
                    className="input-trust"
                  />
                </div>
              </div>
            </div>

            {/* Trust-Specific Fields */}
            {isTrust && (
              <div className="card-trust">
                <h2 className="font-serif text-lg text-navy mb-4">Trust Details</h2>
                <div className="space-y-4">
                  <div>
                    <label className="label-trust mb-2 block">Trustee Names</label>
                    <Input
                      value={formData.trustee_names || ''}
                      onChange={(e) => updateField('trustee_names', e.target.value)}
                      placeholder="e.g., John Smith, Jane Smith"
                      className="input-trust"
                    />
                  </div>
                  <div>
                    <label className="label-trust mb-2 block">Beneficiary Standard</label>
                    <Input
                      value={formData.beneficiary_standard || ''}
                      onChange={(e) => updateField('beneficiary_standard', e.target.value)}
                      placeholder="e.g., Health, Education, Maintenance, Support"
                      className="input-trust"
                    />
                  </div>
                  <div>
                    <label className="label-trust mb-2 block">Distribution Article Reference</label>
                    <Input
                      value={formData.article_ref_distribution || ''}
                      onChange={(e) => updateField('article_ref_distribution', e.target.value)}
                      placeholder="e.g., Article IV, Section 4.1"
                      className="input-trust"
                    />
                  </div>
                  <div>
                    <label className="label-trust mb-2 block">Compensation Article Reference</label>
                    <Input
                      value={formData.article_ref_compensation || ''}
                      onChange={(e) => updateField('article_ref_compensation', e.target.value)}
                      placeholder="e.g., Article V, Section 5.2"
                      className="input-trust"
                    />
                  </div>
                  <div>
                    <label className="label-trust mb-2 block">Amendment Article Reference</label>
                    <Input
                      value={formData.article_ref_amendment || ''}
                      onChange={(e) => updateField('article_ref_amendment', e.target.value)}
                      placeholder="e.g., Article VIII"
                      className="input-trust"
                    />
                  </div>
                  <div className="flex items-center gap-3 pt-2">
                    <input
                      type="checkbox"
                      id="oversight_required"
                      checked={formData.oversight_required || false}
                      onChange={(e) => updateField('oversight_required', e.target.checked)}
                      className="w-4 h-4"
                    />
                    <label htmlFor="oversight_required" className="text-sm text-navy">
                      Oversight Required (Trust Protector/Advisor)
                    </label>
                  </div>
                </div>
              </div>
            )}

            {/* LLC-Specific Fields */}
            {isLLC && (
              <div className="card-trust">
                <h2 className="font-serif text-lg text-navy mb-4">LLC Details</h2>
                <div className="space-y-4">
                  <div>
                    <label className="label-trust mb-2 block">Member Names</label>
                    <Input
                      value={formData.member_names || ''}
                      onChange={(e) => updateField('member_names', e.target.value)}
                      placeholder="e.g., Smith Family Trust (100%)"
                      className="input-trust"
                    />
                  </div>
                  <div>
                    <label className="label-trust mb-2 block">Manager Names</label>
                    <Input
                      value={formData.manager_names || ''}
                      onChange={(e) => updateField('manager_names', e.target.value)}
                      placeholder="e.g., John Smith"
                      className="input-trust"
                    />
                  </div>
                  <div>
                    <label className="label-trust mb-2 block">Authority Article Reference</label>
                    <Input
                      value={formData.article_ref_authority || ''}
                      onChange={(e) => updateField('article_ref_authority', e.target.value)}
                      placeholder="e.g., Section 3.2"
                      className="input-trust"
                    />
                  </div>
                  <div>
                    <label className="label-trust mb-2 block">Profit Distribution Article Reference</label>
                    <Input
                      value={formData.article_ref_profit_distribution || ''}
                      onChange={(e) => updateField('article_ref_profit_distribution', e.target.value)}
                      placeholder="e.g., Section 5.1"
                      className="input-trust"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Bank Accounts Section */}
          <div className="mt-8">
            <BankAccountsSection entityId={entityId} />
          </div>

          {/* Separation Intelligence Section */}
          <div className="mt-8 space-y-6">
            {/* Entity Alerts */}
            <div className="card-trust">
              <SeparationAlertsPanel entityId={entityId} compact />
            </div>

            {/* Recent Transactions for this entity */}
            <div className="card-trust">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-serif text-lg text-navy">Recent Transactions</h2>
                <Button variant="outline" size="sm" onClick={() => navigate('/transactions')} data-testid="view-all-txns-btn">
                  View All
                </Button>
              </div>
              {txnLoading ? (
                <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
              ) : entityTxns.length === 0 ? (
                <div className="text-center py-8">
                  <FileSpreadsheet className="w-8 h-8 text-muted-foreground/40 mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">No transactions for this entity</p>
                  <Button variant="link" size="sm" onClick={() => navigate('/transactions')} className="mt-1">
                    Record a transaction
                  </Button>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-navy/10">
                        <th className="py-2 text-left text-xs uppercase tracking-wider text-muted-foreground">Date</th>
                        <th className="py-2 text-right text-xs uppercase tracking-wider text-muted-foreground">Amount</th>
                        <th className="py-2 text-left text-xs uppercase tracking-wider text-muted-foreground">Classification</th>
                        <th className="py-2 text-left text-xs uppercase tracking-wider text-muted-foreground">Memo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {entityTxns.slice(0, 10).map(t => (
                        <tr key={t.transaction_id} className="border-b border-navy/5">
                          <td className="py-2 text-foreground whitespace-nowrap">
                            {(() => { try { return format(parseISO(t.date), 'MMM d, yyyy'); } catch { return t.date; } })()}
                          </td>
                          <td className="py-2 text-right font-medium whitespace-nowrap">
                            <span className={t.direction === 'inflow' ? 'text-emerald-600' : 'text-red-500'}>
                              {t.direction === 'inflow' ? '+' : '-'}${t.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                            </span>
                          </td>
                          <td className="py-2">
                            <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-navy/5 text-navy">
                              {t.governance_classification}
                            </span>
                          </td>
                          <td className="py-2 text-muted-foreground text-xs max-w-[200px] truncate">{t.purpose_memo}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {entityTxns.length > 10 && (
                    <p className="text-xs text-muted-foreground text-center mt-2">
                      Showing 10 of {entityTxns.length} transactions
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
