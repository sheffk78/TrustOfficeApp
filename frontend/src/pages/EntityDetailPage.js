import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { TrialBanner } from '@/components/TrialBanner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { 
  ArrowLeft, 
  Save,
  Trash2,
  Landmark,
  Building2,
  Building
} from 'lucide-react';
import { toast } from 'sonner';

export default function EntityDetailPage() {
  const { entityId } = useParams();
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [entity, setEntity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({});

  useEffect(() => {
    if (entityId) {
      loadEntity();
    }
  }, [entityId]);

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
        toast.error('Failed to save entity');
      }
    } catch (error) {
      toast.error('Failed to save entity');
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
        toast.error('Failed to delete entity');
      }
    } catch (error) {
      toast.error('Failed to delete entity');
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
        <TrialBanner location="entity_detail" />
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
            className="mb-4 text-navy hover:text-gold"
          >
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Entities
          </Button>

          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-navy/10 flex items-center justify-center text-navy">
                {getEntityIcon(entity?.entity_type)}
              </div>
              <div>
                <h1 className="page-title">{entity?.name}</h1>
                <p className="page-subtitle">{entity?.entity_type}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
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
        </div>
      </main>
    </div>
  );
}
