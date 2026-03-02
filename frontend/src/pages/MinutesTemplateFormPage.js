import { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { 
  ArrowLeft,
  Plus,
  Trash2,
  FileText,
  Download,
  Save,
  Eye
} from 'lucide-react';
import { format } from 'date-fns';

const TEMPLATE_TITLES = {
  'general_meeting': 'General Meeting Minutes',
  'distribution_to_beneficiaries': 'Distribution to Beneficiaries',
  'acceptance_of_property': 'Accept Property into Trust',
  'disposition_of_asset': 'Dispose / Sell Asset',
  'appointment_additional_trustee': 'Appoint Additional Trustee',
  'appointment_successor_trustee': 'Appoint Successor Trustee',
  'designation_of_beneficiaries': 'Designate Beneficiaries',
  'bank_account_authorization': 'Open Bank Account',
  'change_of_situs': 'Change Trust Situs',
  'benevolence_approval': 'Benevolence Assistance Approval'
};

const ASSET_CATEGORIES = [
  { value: 'real_property', label: 'Real Property' },
  { value: 'personal_property', label: 'Personal Property' },
  { value: 'financial_accounts', label: 'Financial Accounts' },
  { value: 'business_interests', label: 'Business Interests' },
  { value: 'digital_assets', label: 'Digital Assets' },
  { value: 'intellectual_property', label: 'Intellectual Property' },
  { value: 'notes_receivable', label: 'Notes Receivable' },
  { value: 'other_property', label: 'Other Property' }
];

export default function MinutesTemplateFormPage() {
  const navigate = useNavigate();
  const { templateType } = useParams();
  const [searchParams] = useSearchParams();
  const { selectedTrust } = useAuth();
  
  const [loading, setLoading] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [generatedDoc, setGeneratedDoc] = useState('');
  const [minutesId, setMinutesId] = useState(null);
  
  // Common fields
  const [formData, setFormData] = useState({
    minute_number: `${new Date().getFullYear()}-001`,
    meeting_date: format(new Date(), 'MMMM d, yyyy'),
    meeting_time: '10:00 AM',
    meeting_type: 'unanimous_written_consent',
    meeting_location: '',
    trustees_present: [],
    trust_indenture_date: '',
    adjournment_time: '10:30 AM'
  });

  // Distribution fields
  const [distributionData, setDistributionData] = useState({
    distribution_total: '',
    distribution_items: [{ beneficiary_name: '', amount: '', percentage: '' }],
    distribution_date: format(new Date(), 'MMMM d, yyyy'),
    distribution_characterization: 'income'
  });

  // Property acceptance fields
  const [propertyData, setPropertyData] = useState({
    grantor_name: '',
    property_description: '',
    property_value: '',
    property_identifier: '',  // VIN, account number, legal description
    property_location: '',    // Address, institution, platform
    conveyance_date: format(new Date(), 'MMMM d, yyyy'),
    add_to_schedule_a: true,
    schedule_a_category: 'real_property'
  });

  // Asset disposition fields
  const [dispositionData, setDispositionData] = useState({
    disposition_asset_id: '',
    disposition_asset_description: '',
    disposition_reason: 'sale',
    disposition_date: format(new Date(), 'MMMM d, yyyy'),
    disposition_value: '',
    disposition_recipient: '',
    disposition_notes: '',
    update_schedule_a: true
  });

  // Schedule A assets for disposition selection
  const [scheduleAAssets, setScheduleAAssets] = useState([]);
  const [loadingAssets, setLoadingAssets] = useState(false);

  // Trustee appointment fields
  const [trusteeData, setTrusteeData] = useState({
    new_trustee_name: '',
    new_trustee_gender: 'man',
    departing_trustee_name: '',
    departing_reason: 'resigned',
    signature_requirement: 'any_one',
    signature_threshold: '',
    banking_powers_granted: true,
    effective_date: format(new Date(), 'MMMM d, yyyy')
  });

  // Beneficiary designation fields
  const [beneficiaryData, setBeneficiaryData] = useState({
    designation_type: 'initial',
    total_units: 100,
    beneficiaries: [{ name: '', units: '', percentage: '', relationship: '' }]
  });

  // Bank account fields
  const [bankData, setBankData] = useState({
    bank_name: '',
    account_type: 'checking',
    purpose: 'general trust administration',
    authorized_signers: [],
    signature_requirement: 'any_one',
    signature_threshold: '',
    initial_deposit: ''
  });

  // Change of situs fields
  const [situsData, setSitusData] = useState({
    current_situs: '',
    new_situs: '',
    effective_date: format(new Date(), 'MMMM d, yyyy'),
    reasons: ['']
  });

  // Benevolence approval fields
  const [benevolenceData, setBenevolenceData] = useState({
    beneficiary_name: '',
    beneficiary_type: 'individual',
    benevolence_purpose: 'assistance',
    purpose_description: '',
    amount: '',
    disbursement_date: format(new Date(), 'MMMM d, yyyy'),
    add_to_benevolence_log: true
  });

  // General meeting resolutions
  const [resolutions, setResolutions] = useState([{
    title: '',
    whereas_clauses: [''],
    resolved_clauses: [''],
    vote: 'Unanimous approval',
    effective_date: 'Immediately upon adoption'
  }]);

  // Trust entity data for auto-population
  const [trustEntity, setTrustEntity] = useState(null);

  useEffect(() => {
    if (selectedTrust) {
      loadTrustEntityData();
    }
  }, [selectedTrust]);

  // Load Schedule A assets when disposition template is selected
  useEffect(() => {
    if (selectedTrust && templateType === 'disposition_of_asset') {
      loadScheduleAAssets();
    }
  }, [selectedTrust, templateType]);

  const loadScheduleAAssets = async () => {
    if (!selectedTrust) return;
    setLoadingAssets(true);
    try {
      // Only load active assets
      const response = await fetchWithAuth(`/schedule-a?trust_id=${selectedTrust.trust_id}&status=active`);
      if (response.ok) {
        const assets = await response.json();
        setScheduleAAssets(assets);
      }
    } catch (error) {
      console.error('Failed to load Schedule A assets:', error);
    } finally {
      setLoadingAssets(false);
    }
  };

  const loadTrustEntityData = async () => {
    try {
      const response = await fetchWithAuth(`/entities?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        const entities = await response.json();
        // Find the main trust entity (entity_type === 'Trust')
        const mainTrust = entities.find(e => e.entity_type === 'Trust');
        if (mainTrust) {
          setTrustEntity(mainTrust);
          
          // Auto-populate trust_indenture_date
          if (mainTrust.formation_date) {
            const formattedDate = format(new Date(mainTrust.formation_date), 'MMMM d, yyyy');
            setFormData(prev => ({
              ...prev,
              trust_indenture_date: formattedDate
            }));
          }
          
          // Auto-populate trustees from trustee_names field
          if (mainTrust.trustee_names) {
            const trustees = mainTrust.trustee_names.split(',').map(t => t.trim()).filter(t => t);
            if (trustees.length > 0) {
              setFormData(prev => ({
                ...prev,
                trustees_present: trustees
              }));
              setBankData(prev => ({
                ...prev,
                authorized_signers: trustees
              }));
            }
          }
        }
      }
    } catch (error) {
      console.error('Failed to load trust entity data:', error);
    }
  };

  const handleAddTrustee = () => {
    setFormData(prev => ({
      ...prev,
      trustees_present: [...prev.trustees_present, '']
    }));
  };

  const handleRemoveTrustee = (index) => {
    setFormData(prev => ({
      ...prev,
      trustees_present: prev.trustees_present.filter((_, i) => i !== index)
    }));
  };

  const handleTrusteeChange = (index, value) => {
    setFormData(prev => ({
      ...prev,
      trustees_present: prev.trustees_present.map((t, i) => i === index ? value : t)
    }));
  };

  const handleAddDistributionItem = () => {
    setDistributionData(prev => ({
      ...prev,
      distribution_items: [...prev.distribution_items, { beneficiary_name: '', amount: '', percentage: '' }]
    }));
  };

  const handleRemoveDistributionItem = (index) => {
    setDistributionData(prev => ({
      ...prev,
      distribution_items: prev.distribution_items.filter((_, i) => i !== index)
    }));
  };

  const handleDistributionItemChange = (index, field, value) => {
    setDistributionData(prev => ({
      ...prev,
      distribution_items: prev.distribution_items.map((item, i) => 
        i === index ? { ...item, [field]: value } : item
      )
    }));
  };

  const handleAddResolution = () => {
    setResolutions(prev => [...prev, {
      title: '',
      whereas_clauses: [''],
      resolved_clauses: [''],
      vote: 'Unanimous approval',
      effective_date: 'Immediately upon adoption'
    }]);
  };

  const handleRemoveResolution = (index) => {
    setResolutions(prev => prev.filter((_, i) => i !== index));
  };

  const buildTemplateData = () => {
    const baseData = {
      ...formData,
      trustees_present: formData.trustees_present.filter(t => t.trim()),
      // Include article references from trust entity
      article_ref_distribution: trustEntity?.article_ref_distribution || '',
      article_ref_compensation: trustEntity?.article_ref_compensation || '',
      article_ref_amendment: trustEntity?.article_ref_amendment || '',
      beneficiary_standard: trustEntity?.beneficiary_standard || ''
    };

    switch (templateType) {
      case 'distribution_to_beneficiaries':
        return {
          ...baseData,
          distribution_total: parseFloat(distributionData.distribution_total) || 0,
          distribution_items: distributionData.distribution_items
            .filter(item => item.beneficiary_name)
            .map(item => ({
              beneficiary_name: item.beneficiary_name,
              amount: parseFloat(item.amount) || 0,
              percentage: parseFloat(item.percentage) || 0
            })),
          distribution_date: distributionData.distribution_date,
          distribution_characterization: distributionData.distribution_characterization
        };
      
      case 'acceptance_of_property':
        return {
          ...baseData,
          grantor_name: propertyData.grantor_name,
          property_description: propertyData.property_description,
          property_value: parseFloat(propertyData.property_value) || null,
          property_identifier: propertyData.property_identifier,
          property_location: propertyData.property_location,
          conveyance_date: propertyData.conveyance_date,
          add_to_schedule_a: propertyData.add_to_schedule_a,
          schedule_a_category: propertyData.schedule_a_category
        };
      
      case 'disposition_of_asset':
        return {
          ...baseData,
          disposition_asset_id: dispositionData.disposition_asset_id,
          disposition_asset_description: dispositionData.disposition_asset_description,
          disposition_reason: dispositionData.disposition_reason,
          disposition_date: dispositionData.disposition_date,
          disposition_value: parseFloat(dispositionData.disposition_value) || null,
          disposition_recipient: dispositionData.disposition_recipient,
          disposition_notes: dispositionData.disposition_notes,
          update_schedule_a: dispositionData.update_schedule_a
        };
      
      case 'appointment_additional_trustee':
      case 'appointment_successor_trustee':
        return {
          ...baseData,
          appointment_type: templateType === 'appointment_successor_trustee' ? 'successor' : 'additional',
          new_trustee_name: trusteeData.new_trustee_name,
          new_trustee_gender: trusteeData.new_trustee_gender,
          departing_trustee_name: trusteeData.departing_trustee_name,
          departing_reason: trusteeData.departing_reason,
          signature_requirement: trusteeData.signature_requirement,
          signature_threshold: parseFloat(trusteeData.signature_threshold) || null,
          banking_powers_granted: trusteeData.banking_powers_granted,
          effective_date: trusteeData.effective_date
        };
      
      case 'designation_of_beneficiaries':
        return {
          ...baseData,
          designation_type: beneficiaryData.designation_type,
          total_units: parseInt(beneficiaryData.total_units) || 100,
          beneficiaries: beneficiaryData.beneficiaries
            .filter(b => b.name)
            .map(b => ({
              name: b.name,
              units: parseInt(b.units) || 0,
              percentage: parseFloat(b.percentage) || 0,
              relationship: b.relationship
            }))
        };
      
      case 'bank_account_authorization':
        return {
          ...baseData,
          bank_name: bankData.bank_name,
          account_type: bankData.account_type,
          purpose: bankData.purpose,
          authorized_signers: bankData.authorized_signers.filter(s => s.trim()),
          signature_requirement: bankData.signature_requirement,
          signature_threshold: parseFloat(bankData.signature_threshold) || null,
          initial_deposit: parseFloat(bankData.initial_deposit) || null
        };
      
      case 'change_of_situs':
        return {
          ...baseData,
          current_situs: situsData.current_situs,
          new_situs: situsData.new_situs,
          effective_date: situsData.effective_date,
          reasons: situsData.reasons.filter(r => r.trim())
        };
      
      case 'benevolence_approval':
        return {
          ...baseData,
          beneficiary_name: benevolenceData.beneficiary_name,
          beneficiary_type: benevolenceData.beneficiary_type,
          benevolence_purpose: benevolenceData.benevolence_purpose,
          purpose_description: benevolenceData.purpose_description,
          amount: parseFloat(benevolenceData.amount) || 0,
          disbursement_date: benevolenceData.disbursement_date,
          add_to_benevolence_log: benevolenceData.add_to_benevolence_log
        };
      
      case 'general_meeting':
      default:
        return {
          ...baseData,
          resolutions: resolutions.filter(r => r.title).map(r => ({
            title: r.title,
            whereas_clauses: r.whereas_clauses.filter(c => c.trim()),
            resolved_clauses: r.resolved_clauses.filter(c => c.trim()),
            vote: r.vote,
            effective_date: r.effective_date
          }))
        };
    }
  };

  const handleGeneratePreview = async () => {
    if (!selectedTrust) {
      toast.error('Please select a trust');
      return;
    }

    setLoading(true);
    try {
      const templateData = buildTemplateData();
      
      const response = await fetchWithAuth('/minutes-templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          template_type: templateType,
          template_data: templateData
        })
      });

      if (response.ok) {
        const result = await response.json();
        setGeneratedDoc(result.generated_document);
        setMinutesId(result.minutes_id);
        setPreviewMode(true);
        toast.success('Minutes generated');
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to generate minutes');
      }
    } catch (error) {
      toast.error('Failed to generate minutes');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveMinutes = async () => {
    if (!minutesId) return;

    setLoading(true);
    try {
      const response = await fetchWithAuth(`/minutes-templates/${minutesId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          generated_document: generatedDoc,
          status: 'final'
        })
      });

      if (response.ok) {
        toast.success('Minutes saved');
        navigate('/minutes');
      } else {
        toast.error('Failed to save minutes');
      }
    } catch (error) {
      toast.error('Failed to save minutes');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    if (!minutesId) return;

    try {
      const response = await fetchWithAuth(`/minutes-templates/${minutesId}/pdf`);
      if (response.ok) {
        const data = await response.json();
        const link = document.createElement('a');
        link.href = `data:application/pdf;base64,${data.pdf_base64}`;
        link.download = data.filename;
        link.click();
        toast.success('PDF downloaded');
      }
    } catch (error) {
      toast.error('Failed to download PDF');
    }
  };

  if (!selectedTrust) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Select a trust to create minutes</p>
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
          <div className="mb-8">
            <Button 
              variant="ghost" 
              className="mb-4"
              onClick={() => previewMode ? setPreviewMode(false) : navigate('/minutes/templates')}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              {previewMode ? 'Back to Form' : 'Back to Templates'}
            </Button>
            <h1 className="font-serif text-3xl lg:text-4xl text-navy mb-2">
              {TEMPLATE_TITLES[templateType] || 'Create Minutes'}
            </h1>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              {selectedTrust.name}
            </p>
          </div>

          {previewMode ? (
            /* Preview Mode */
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <h2 className="font-serif text-xl text-navy">Document Preview</h2>
                <div className="flex gap-3">
                  <Button variant="outline" onClick={handleDownloadPDF}>
                    <Download className="w-4 h-4 mr-2" />
                    Download PDF
                  </Button>
                  <Button className="btn-primary" onClick={handleSaveMinutes} disabled={loading}>
                    <Save className="w-4 h-4 mr-2" />
                    {loading ? 'Saving...' : 'Save Minutes'}
                  </Button>
                </div>
              </div>
              
              <div className="card-trust p-6">
                <p className="text-xs text-muted-foreground mb-4">
                  You can edit the document below before saving. Changes are tracked for audit purposes.
                </p>
                <Textarea
                  value={generatedDoc}
                  onChange={(e) => setGeneratedDoc(e.target.value)}
                  className="font-mono text-sm min-h-[600px] whitespace-pre-wrap"
                  data-testid="generated-document"
                />
              </div>
            </div>
          ) : (
            /* Form Mode */
            <div className="space-y-8">
              {/* Common Fields */}
              <div className="card-trust corner-mark p-6">
                <h2 className="font-serif text-xl text-navy mb-4">Meeting Information</h2>
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <Label className="label-trust">Minute Number</Label>
                    <Input
                      value={formData.minute_number}
                      onChange={(e) => setFormData({ ...formData, minute_number: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="2024-001"
                    />
                  </div>
                  <div>
                    <Label className="label-trust">Meeting Date</Label>
                    <Input
                      value={formData.meeting_date}
                      onChange={(e) => setFormData({ ...formData, meeting_date: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="February 23, 2024"
                    />
                  </div>
                  <div>
                    <Label className="label-trust">Meeting Time</Label>
                    <Input
                      value={formData.meeting_time}
                      onChange={(e) => setFormData({ ...formData, meeting_time: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="10:00 AM"
                    />
                  </div>
                  <div>
                    <Label className="label-trust">Meeting Type</Label>
                    <Select value={formData.meeting_type} onValueChange={(v) => setFormData({ ...formData, meeting_type: v })}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="unanimous_written_consent">Unanimous Written Consent</SelectItem>
                        <SelectItem value="in_person">In Person</SelectItem>
                        <SelectItem value="video_conference">Video/Phone Conference</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {formData.meeting_type === 'in_person' && (
                    <div className="md:col-span-2">
                      <Label className="label-trust">Meeting Location</Label>
                      <Input
                        value={formData.meeting_location}
                        onChange={(e) => setFormData({ ...formData, meeting_location: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="123 Main Street, City, State"
                      />
                    </div>
                  )}
                  <div className="md:col-span-2">
                    <Label className="label-trust">Trust Indenture Date</Label>
                    <Input
                      value={formData.trust_indenture_date}
                      onChange={(e) => setFormData({ ...formData, trust_indenture_date: e.target.value })}
                      className="mt-1 input-trust"
                      placeholder="January 1, 2020"
                    />
                  </div>
                </div>

                {/* Trustees Present */}
                <div className="mt-6">
                  <div className="flex items-center justify-between mb-2">
                    <Label className="label-trust">Trustees Present</Label>
                    <Button type="button" variant="ghost" size="sm" onClick={handleAddTrustee}>
                      <Plus className="w-4 h-4 mr-1" />
                      Add Trustee
                    </Button>
                  </div>
                  <div className="space-y-2">
                    {formData.trustees_present.map((trustee, index) => (
                      <div key={index} className="flex gap-2">
                        <Input
                          value={trustee}
                          onChange={(e) => handleTrusteeChange(index, e.target.value)}
                          className="input-trust"
                          placeholder="Trustee name"
                        />
                        {formData.trustees_present.length > 1 && (
                          <Button type="button" variant="ghost" size="icon" onClick={() => handleRemoveTrustee(index)}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Template-specific fields */}
              {templateType === 'distribution_to_beneficiaries' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Distribution Details</h2>
                  <div className="grid md:grid-cols-2 gap-4 mb-6">
                    <div>
                      <Label className="label-trust">Total Distribution Amount</Label>
                      <Input
                        type="number"
                        value={distributionData.distribution_total}
                        onChange={(e) => setDistributionData({ ...distributionData, distribution_total: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="50000"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Distribution Date</Label>
                      <Input
                        value={distributionData.distribution_date}
                        onChange={(e) => setDistributionData({ ...distributionData, distribution_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="March 1, 2024"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Characterization</Label>
                      <Select value={distributionData.distribution_characterization} onValueChange={(v) => setDistributionData({ ...distributionData, distribution_characterization: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="income">Income</SelectItem>
                          <SelectItem value="principal">Principal</SelectItem>
                          <SelectItem value="return_of_corpus">Return of Corpus</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mb-2">
                    <Label className="label-trust">Beneficiaries</Label>
                    <Button type="button" variant="ghost" size="sm" onClick={handleAddDistributionItem}>
                      <Plus className="w-4 h-4 mr-1" />
                      Add Beneficiary
                    </Button>
                  </div>
                  <div className="space-y-3">
                    {distributionData.distribution_items.map((item, index) => (
                      <div key={index} className="flex gap-2 items-end">
                        <div className="flex-1">
                          <Input
                            value={item.beneficiary_name}
                            onChange={(e) => handleDistributionItemChange(index, 'beneficiary_name', e.target.value)}
                            placeholder="Beneficiary name"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-32">
                          <Input
                            type="number"
                            value={item.amount}
                            onChange={(e) => handleDistributionItemChange(index, 'amount', e.target.value)}
                            placeholder="Amount"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-24">
                          <Input
                            type="number"
                            value={item.percentage}
                            onChange={(e) => handleDistributionItemChange(index, 'percentage', e.target.value)}
                            placeholder="%"
                            className="input-trust"
                          />
                        </div>
                        {distributionData.distribution_items.length > 1 && (
                          <Button type="button" variant="ghost" size="icon" onClick={() => handleRemoveDistributionItem(index)}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {templateType === 'acceptance_of_property' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Property Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <Label className="label-trust">Grantor/Creator Name</Label>
                      <Input
                        value={propertyData.grantor_name}
                        onChange={(e) => setPropertyData({ ...propertyData, grantor_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="John Smith"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Property Description</Label>
                      <Textarea
                        value={propertyData.property_description}
                        onChange={(e) => setPropertyData({ ...propertyData, property_description: e.target.value })}
                        className="mt-1"
                        placeholder="Single-family residence located at 123 Main Street, City, State 12345; Lot 4, Block 2, Subdivision XYZ"
                        rows={3}
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Identifier (VIN, Account #, Legal Description)</Label>
                      <Input
                        value={propertyData.property_identifier}
                        onChange={(e) => setPropertyData({ ...propertyData, property_identifier: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="VIN: 1HGBH41JXMN109186"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Location / Institution</Label>
                      <Input
                        value={propertyData.property_location}
                        onChange={(e) => setPropertyData({ ...propertyData, property_location: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="123 Main St, City, State 12345"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Approximate Value</Label>
                      <Input
                        type="number"
                        value={propertyData.property_value}
                        onChange={(e) => setPropertyData({ ...propertyData, property_value: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="250000"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Date of Conveyance</Label>
                      <Input
                        value={propertyData.conveyance_date}
                        onChange={(e) => setPropertyData({ ...propertyData, conveyance_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="February 23, 2024"
                      />
                    </div>
                    <div className="md:col-span-2 flex items-center gap-3 mt-2">
                      <Checkbox
                        checked={propertyData.add_to_schedule_a}
                        onCheckedChange={(checked) => setPropertyData({ ...propertyData, add_to_schedule_a: checked })}
                        id="add-schedule-a"
                      />
                      <Label htmlFor="add-schedule-a" className="cursor-pointer">
                        Automatically add to Schedule A
                      </Label>
                    </div>
                    {propertyData.add_to_schedule_a && (
                      <div className="md:col-span-2">
                        <Label className="label-trust">Asset Category (for Schedule A)</Label>
                        <Select value={propertyData.schedule_a_category} onValueChange={(v) => setPropertyData({ ...propertyData, schedule_a_category: v })}>
                          <SelectTrigger className="mt-1">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {ASSET_CATEGORIES.map(cat => (
                              <SelectItem key={cat.value} value={cat.value}>{cat.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {templateType === 'disposition_of_asset' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Asset Disposition Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <Label className="label-trust">Select Asset from Schedule A</Label>
                      {loadingAssets ? (
                        <div className="mt-2 text-muted-foreground">Loading assets...</div>
                      ) : scheduleAAssets.length === 0 ? (
                        <div className="mt-2 text-muted-foreground">No active assets found in Schedule A</div>
                      ) : (
                        <Select 
                          value={dispositionData.disposition_asset_id} 
                          onValueChange={(v) => {
                            const asset = scheduleAAssets.find(a => a.item_id === v);
                            setDispositionData({ 
                              ...dispositionData, 
                              disposition_asset_id: v,
                              disposition_asset_description: asset ? `${asset.description} (${asset.category.replace(/_/g, ' ')})` : ''
                            });
                          }}
                        >
                          <SelectTrigger className="mt-1">
                            <SelectValue placeholder="Select an asset to dispose" />
                          </SelectTrigger>
                          <SelectContent>
                            {scheduleAAssets.map(asset => (
                              <SelectItem key={asset.item_id} value={asset.item_id}>
                                {asset.description} - {asset.category.replace(/_/g, ' ')} 
                                {asset.approximate_value && ` ($${asset.approximate_value.toLocaleString()})`}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    </div>
                    
                    {dispositionData.disposition_asset_id && (
                      <>
                        <div className="md:col-span-2">
                          <Label className="label-trust">Asset Description (for minutes)</Label>
                          <Textarea
                            value={dispositionData.disposition_asset_description}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_asset_description: e.target.value })}
                            className="mt-1"
                            placeholder="2020 Toyota Camry, VIN: 1HGBH41JXMN109186"
                            rows={2}
                          />
                        </div>
                        
                        <div>
                          <Label className="label-trust">Reason for Disposition</Label>
                          <Select 
                            value={dispositionData.disposition_reason} 
                            onValueChange={(v) => setDispositionData({ ...dispositionData, disposition_reason: v })}
                          >
                            <SelectTrigger className="mt-1">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="sale">Sale</SelectItem>
                              <SelectItem value="transfer">Transfer</SelectItem>
                              <SelectItem value="donation">Donation</SelectItem>
                              <SelectItem value="destruction">Destruction / Total Loss</SelectItem>
                              <SelectItem value="other">Other</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        
                        <div>
                          <Label className="label-trust">Date of Disposition</Label>
                          <Input
                            value={dispositionData.disposition_date}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_date: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="February 23, 2024"
                          />
                        </div>
                        
                        <div>
                          <Label className="label-trust">
                            {dispositionData.disposition_reason === 'sale' ? 'Sale Price' : 'Fair Market Value'}
                          </Label>
                          <Input
                            type="number"
                            value={dispositionData.disposition_value}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_value: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="25000"
                          />
                        </div>
                        
                        <div>
                          <Label className="label-trust">
                            {dispositionData.disposition_reason === 'sale' ? 'Buyer' : 'Recipient'} (if applicable)
                          </Label>
                          <Input
                            value={dispositionData.disposition_recipient}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_recipient: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="ABC Motors LLC"
                          />
                        </div>
                        
                        <div className="md:col-span-2">
                          <Label className="label-trust">Additional Notes</Label>
                          <Textarea
                            value={dispositionData.disposition_notes}
                            onChange={(e) => setDispositionData({ ...dispositionData, disposition_notes: e.target.value })}
                            className="mt-1"
                            placeholder="Any additional details about the disposition..."
                            rows={2}
                          />
                        </div>
                        
                        <div className="md:col-span-2 flex items-center gap-3 mt-2">
                          <Checkbox
                            checked={dispositionData.update_schedule_a}
                            onCheckedChange={(checked) => setDispositionData({ ...dispositionData, update_schedule_a: checked })}
                            id="update-schedule-a"
                          />
                          <Label htmlFor="update-schedule-a" className="cursor-pointer">
                            Mark asset as disposed in Schedule A (keeps historical record)
                          </Label>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}

              {(templateType === 'appointment_additional_trustee' || templateType === 'appointment_successor_trustee') && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">
                    {templateType === 'appointment_successor_trustee' ? 'Successor Trustee Details' : 'New Trustee Details'}
                  </h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">New Trustee Name</Label>
                      <Input
                        value={trusteeData.new_trustee_name}
                        onChange={(e) => setTrusteeData({ ...trusteeData, new_trustee_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Jane Doe"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Gender (for document language)</Label>
                      <Select value={trusteeData.new_trustee_gender} onValueChange={(v) => setTrusteeData({ ...trusteeData, new_trustee_gender: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="man">Man</SelectItem>
                          <SelectItem value="woman">Woman</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    {templateType === 'appointment_successor_trustee' && (
                      <>
                        <div>
                          <Label className="label-trust">Departing Trustee Name</Label>
                          <Input
                            value={trusteeData.departing_trustee_name}
                            onChange={(e) => setTrusteeData({ ...trusteeData, departing_trustee_name: e.target.value })}
                            className="mt-1 input-trust"
                            placeholder="John Smith"
                          />
                        </div>
                        <div>
                          <Label className="label-trust">Reason for Departure</Label>
                          <Select value={trusteeData.departing_reason} onValueChange={(v) => setTrusteeData({ ...trusteeData, departing_reason: v })}>
                            <SelectTrigger className="mt-1">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="resigned">Resigned</SelectItem>
                              <SelectItem value="died">Died</SelectItem>
                              <SelectItem value="incapacitated">Become Incapacitated</SelectItem>
                              <SelectItem value="removed">Been Removed</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </>
                    )}

                    <div>
                      <Label className="label-trust">Effective Date</Label>
                      <Input
                        value={trusteeData.effective_date}
                        onChange={(e) => setTrusteeData({ ...trusteeData, effective_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="February 23, 2024"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Signature Requirement</Label>
                      <Select value={trusteeData.signature_requirement} onValueChange={(v) => setTrusteeData({ ...trusteeData, signature_requirement: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="any_one">Any One Trustee (no limit)</SelectItem>
                          <SelectItem value="any_two">Any Two Trustees (all transactions)</SelectItem>
                          <SelectItem value="threshold">One up to threshold, Two above</SelectItem>
                          <SelectItem value="all_trustees">All Trustees (above threshold)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    {(trusteeData.signature_requirement === 'threshold' || trusteeData.signature_requirement === 'all_trustees') && (
                      <div>
                        <Label className="label-trust">Signature Threshold Amount</Label>
                        <Input
                          type="number"
                          value={trusteeData.signature_threshold}
                          onChange={(e) => setTrusteeData({ ...trusteeData, signature_threshold: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="10000"
                        />
                      </div>
                    )}

                    <div className="md:col-span-2 flex items-center gap-3 mt-2">
                      <Checkbox
                        checked={trusteeData.banking_powers_granted}
                        onCheckedChange={(checked) => setTrusteeData({ ...trusteeData, banking_powers_granted: checked })}
                        id="banking-powers"
                      />
                      <Label htmlFor="banking-powers" className="cursor-pointer">
                        Grant banking and signatory powers
                      </Label>
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'designation_of_beneficiaries' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Beneficiary Designation</h2>
                  <div className="grid md:grid-cols-2 gap-4 mb-6">
                    <div>
                      <Label className="label-trust">Designation Type</Label>
                      <Select value={beneficiaryData.designation_type} onValueChange={(v) => setBeneficiaryData({ ...beneficiaryData, designation_type: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="initial">Initial Designation</SelectItem>
                          <SelectItem value="amendment">Amendment to Existing</SelectItem>
                          <SelectItem value="restatement">Complete Restatement</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Total Units of Beneficial Interest</Label>
                      <Input
                        type="number"
                        value={beneficiaryData.total_units}
                        onChange={(e) => setBeneficiaryData({ ...beneficiaryData, total_units: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="100"
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-between mb-2">
                    <Label className="label-trust">Beneficiaries</Label>
                    <Button type="button" variant="ghost" size="sm" onClick={() => setBeneficiaryData(prev => ({
                      ...prev,
                      beneficiaries: [...prev.beneficiaries, { name: '', units: '', percentage: '', relationship: '' }]
                    }))}>
                      <Plus className="w-4 h-4 mr-1" />
                      Add Beneficiary
                    </Button>
                  </div>
                  <div className="space-y-3">
                    {beneficiaryData.beneficiaries.map((ben, index) => (
                      <div key={index} className="flex gap-2 items-end">
                        <div className="flex-1">
                          <Input
                            value={ben.name}
                            onChange={(e) => {
                              const newBens = [...beneficiaryData.beneficiaries];
                              newBens[index].name = e.target.value;
                              setBeneficiaryData({ ...beneficiaryData, beneficiaries: newBens });
                            }}
                            placeholder="Beneficiary name"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-24">
                          <Input
                            type="number"
                            value={ben.units}
                            onChange={(e) => {
                              const newBens = [...beneficiaryData.beneficiaries];
                              newBens[index].units = e.target.value;
                              setBeneficiaryData({ ...beneficiaryData, beneficiaries: newBens });
                            }}
                            placeholder="Units"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-20">
                          <Input
                            type="number"
                            value={ben.percentage}
                            onChange={(e) => {
                              const newBens = [...beneficiaryData.beneficiaries];
                              newBens[index].percentage = e.target.value;
                              setBeneficiaryData({ ...beneficiaryData, beneficiaries: newBens });
                            }}
                            placeholder="%"
                            className="input-trust"
                          />
                        </div>
                        <div className="w-32">
                          <Input
                            value={ben.relationship}
                            onChange={(e) => {
                              const newBens = [...beneficiaryData.beneficiaries];
                              newBens[index].relationship = e.target.value;
                              setBeneficiaryData({ ...beneficiaryData, beneficiaries: newBens });
                            }}
                            placeholder="Relationship"
                            className="input-trust"
                          />
                        </div>
                        {beneficiaryData.beneficiaries.length > 1 && (
                          <Button type="button" variant="ghost" size="icon" onClick={() => {
                            setBeneficiaryData(prev => ({
                              ...prev,
                              beneficiaries: prev.beneficiaries.filter((_, i) => i !== index)
                            }));
                          }}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {templateType === 'bank_account_authorization' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Bank Account Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Bank/Institution Name</Label>
                      <Input
                        value={bankData.bank_name}
                        onChange={(e) => setBankData({ ...bankData, bank_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., Chase Bank, Charles Schwab"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Account Type</Label>
                      <Select value={bankData.account_type} onValueChange={(v) => setBankData({ ...bankData, account_type: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="checking">Checking Account</SelectItem>
                          <SelectItem value="savings">Savings Account</SelectItem>
                          <SelectItem value="brokerage">Brokerage/Investment Account</SelectItem>
                          <SelectItem value="money_market">Money Market Account</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Purpose</Label>
                      <Input
                        value={bankData.purpose}
                        onChange={(e) => setBankData({ ...bankData, purpose: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., general trust administration, investment holdings"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Signature Requirement</Label>
                      <Select value={bankData.signature_requirement} onValueChange={(v) => setBankData({ ...bankData, signature_requirement: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="any_one">Any One Trustee</SelectItem>
                          <SelectItem value="any_two">Any Two Trustees</SelectItem>
                          <SelectItem value="threshold">One up to threshold, Two above</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    {bankData.signature_requirement === 'threshold' && (
                      <div>
                        <Label className="label-trust">Signature Threshold</Label>
                        <Input
                          type="number"
                          value={bankData.signature_threshold}
                          onChange={(e) => setBankData({ ...bankData, signature_threshold: e.target.value })}
                          className="mt-1 input-trust"
                          placeholder="10000"
                        />
                      </div>
                    )}
                    <div>
                      <Label className="label-trust">Initial Deposit (optional)</Label>
                      <Input
                        type="number"
                        value={bankData.initial_deposit}
                        onChange={(e) => setBankData({ ...bankData, initial_deposit: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="0.00"
                      />
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="flex items-center justify-between mb-2">
                      <Label className="label-trust">Authorized Signers</Label>
                      <Button type="button" variant="ghost" size="sm" onClick={() => setBankData(prev => ({
                        ...prev,
                        authorized_signers: [...prev.authorized_signers, '']
                      }))}>
                        <Plus className="w-4 h-4 mr-1" />
                        Add Signer
                      </Button>
                    </div>
                    <div className="space-y-2">
                      {bankData.authorized_signers.map((signer, index) => (
                        <div key={index} className="flex gap-2">
                          <Input
                            value={signer}
                            onChange={(e) => {
                              const newSigners = [...bankData.authorized_signers];
                              newSigners[index] = e.target.value;
                              setBankData({ ...bankData, authorized_signers: newSigners });
                            }}
                            className="input-trust"
                            placeholder="Trustee name"
                          />
                          {bankData.authorized_signers.length > 1 && (
                            <Button type="button" variant="ghost" size="icon" onClick={() => {
                              setBankData(prev => ({
                                ...prev,
                                authorized_signers: prev.authorized_signers.filter((_, i) => i !== index)
                              }));
                            }}>
                              <Trash2 className="w-4 h-4 text-red-500" />
                            </Button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'change_of_situs' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Change of Situs Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label className="label-trust">Current Situs (State/Jurisdiction)</Label>
                      <Input
                        value={situsData.current_situs}
                        onChange={(e) => setSitusData({ ...situsData, current_situs: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., State of Texas"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">New Situs (State/Jurisdiction)</Label>
                      <Input
                        value={situsData.new_situs}
                        onChange={(e) => setSitusData({ ...situsData, new_situs: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="e.g., State of Nevada"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Effective Date</Label>
                      <Input
                        value={situsData.effective_date}
                        onChange={(e) => setSitusData({ ...situsData, effective_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="March 1, 2024"
                      />
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="flex items-center justify-between mb-2">
                      <Label className="label-trust">Reasons for Change (optional)</Label>
                      <Button type="button" variant="ghost" size="sm" onClick={() => setSitusData(prev => ({
                        ...prev,
                        reasons: [...prev.reasons, '']
                      }))}>
                        <Plus className="w-4 h-4 mr-1" />
                        Add Reason
                      </Button>
                    </div>
                    <div className="space-y-2">
                      {situsData.reasons.map((reason, index) => (
                        <div key={index} className="flex gap-2">
                          <Input
                            value={reason}
                            onChange={(e) => {
                              const newReasons = [...situsData.reasons];
                              newReasons[index] = e.target.value;
                              setSitusData({ ...situsData, reasons: newReasons });
                            }}
                            className="input-trust"
                            placeholder="e.g., Favorable trust laws, tax considerations"
                          />
                          {situsData.reasons.length > 1 && (
                            <Button type="button" variant="ghost" size="icon" onClick={() => {
                              setSitusData(prev => ({
                                ...prev,
                                reasons: prev.reasons.filter((_, i) => i !== index)
                              }));
                            }}>
                              <Trash2 className="w-4 h-4 text-red-500" />
                            </Button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'benevolence_approval' && (
                <div className="card-trust corner-mark p-6">
                  <h2 className="font-serif text-xl text-navy mb-4">Benevolence Grant Details</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="md:col-span-2">
                      <Label className="label-trust">Beneficiary Name *</Label>
                      <Input
                        value={benevolenceData.beneficiary_name}
                        onChange={(e) => setBenevolenceData({ ...benevolenceData, beneficiary_name: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="Name of recipient"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Beneficiary Type</Label>
                      <Select value={benevolenceData.beneficiary_type} onValueChange={(v) => setBenevolenceData({ ...benevolenceData, beneficiary_type: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="individual">Individual</SelectItem>
                          <SelectItem value="family">Family</SelectItem>
                          <SelectItem value="organization">Organization</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="label-trust">Purpose Category</Label>
                      <Select value={benevolenceData.benevolence_purpose} onValueChange={(v) => setBenevolenceData({ ...benevolenceData, benevolence_purpose: v })}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="medical">Medical Expenses</SelectItem>
                          <SelectItem value="housing">Housing Assistance</SelectItem>
                          <SelectItem value="education">Education</SelectItem>
                          <SelectItem value="food_necessities">Food & Necessities</SelectItem>
                          <SelectItem value="utilities">Utilities</SelectItem>
                          <SelectItem value="transportation">Transportation</SelectItem>
                          <SelectItem value="emergency">Emergency Relief</SelectItem>
                          <SelectItem value="spiritual">Spiritual/Ministry</SelectItem>
                          <SelectItem value="assistance">General Assistance</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="md:col-span-2">
                      <Label className="label-trust">Purpose Description *</Label>
                      <Textarea
                        value={benevolenceData.purpose_description}
                        onChange={(e) => setBenevolenceData({ ...benevolenceData, purpose_description: e.target.value })}
                        className="mt-1"
                        placeholder="Describe the need and how the assistance will help"
                        rows={3}
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Grant Amount *</Label>
                      <Input
                        type="number"
                        value={benevolenceData.amount}
                        onChange={(e) => setBenevolenceData({ ...benevolenceData, amount: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="500.00"
                      />
                    </div>
                    <div>
                      <Label className="label-trust">Disbursement Date</Label>
                      <Input
                        value={benevolenceData.disbursement_date}
                        onChange={(e) => setBenevolenceData({ ...benevolenceData, disbursement_date: e.target.value })}
                        className="mt-1 input-trust"
                        placeholder="March 1, 2024"
                      />
                    </div>
                    <div className="md:col-span-2 flex items-center gap-3 mt-2">
                      <Checkbox
                        checked={benevolenceData.add_to_benevolence_log}
                        onCheckedChange={(checked) => setBenevolenceData({ ...benevolenceData, add_to_benevolence_log: checked })}
                        id="add-benevolence-log"
                      />
                      <Label htmlFor="add-benevolence-log" className="cursor-pointer">
                        Automatically add to Benevolence Log
                      </Label>
                    </div>
                  </div>
                </div>
              )}

              {templateType === 'general_meeting' && (
                <div className="card-trust corner-mark p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="font-serif text-xl text-navy">Resolutions</h2>
                    <Button type="button" variant="outline" onClick={handleAddResolution}>
                      <Plus className="w-4 h-4 mr-2" />
                      Add Resolution
                    </Button>
                  </div>
                  
                  {resolutions.map((res, index) => (
                    <div key={index} className="mb-6 p-4 border border-border rounded-lg">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="font-medium">Resolution {index + 1}</h3>
                        {resolutions.length > 1 && (
                          <Button type="button" variant="ghost" size="sm" onClick={() => handleRemoveResolution(index)}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        )}
                      </div>
                      <div className="space-y-4">
                        <div>
                          <Label className="label-trust">Title/Subject</Label>
                          <Input
                            value={res.title}
                            onChange={(e) => {
                              const newRes = [...resolutions];
                              newRes[index].title = e.target.value;
                              setResolutions(newRes);
                            }}
                            className="mt-1 input-trust"
                            placeholder="e.g., Approval of Annual Report"
                          />
                        </div>
                        <div>
                          <Label className="label-trust">WHEREAS Clause(s)</Label>
                          <Textarea
                            value={res.whereas_clauses[0]}
                            onChange={(e) => {
                              const newRes = [...resolutions];
                              newRes[index].whereas_clauses = [e.target.value];
                              setResolutions(newRes);
                            }}
                            className="mt-1"
                            placeholder="State the background, circumstances, or reason for the resolution"
                            rows={2}
                          />
                        </div>
                        <div>
                          <Label className="label-trust">BE IT RESOLVED Clause(s)</Label>
                          <Textarea
                            value={res.resolved_clauses[0]}
                            onChange={(e) => {
                              const newRes = [...resolutions];
                              newRes[index].resolved_clauses = [e.target.value];
                              setResolutions(newRes);
                            }}
                            className="mt-1"
                            placeholder="State the specific action, decision, or authorization"
                            rows={2}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Generate Button */}
              <div className="flex justify-end gap-3">
                <Button variant="outline" onClick={() => navigate('/minutes/templates')}>
                  Cancel
                </Button>
                <Button className="btn-primary" onClick={handleGeneratePreview} disabled={loading}>
                  <Eye className="w-4 h-4 mr-2" />
                  {loading ? 'Generating...' : 'Generate Preview'}
                </Button>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
