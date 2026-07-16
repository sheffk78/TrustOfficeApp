import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { 
  FileText,
  Users,
  DollarSign,
  PlusCircle,
  MinusCircle,
  UserPlus,
  UserCheck,
  UsersRound,
  Landmark,
  MapPin,
  ChevronRight,
  ArrowLeft,
  HeartHandshake,
  Gavel
} from 'lucide-react';

const ICONS = {
  'file-text': FileText,
  'users': Users,
  'dollar-sign': DollarSign,
  'plus-circle': PlusCircle,
  'minus-circle': MinusCircle,
  'user-plus': UserPlus,
  'user-check': UserCheck,
  'users-round': UsersRound,
  'landmark': Landmark,
  'map-pin': MapPin,
  'heart-handshake': HeartHandshake,
  'gavel': Gavel
};

/** Resolution subtitles for templates that produce WHEREAS/RESOLVED text. */
const RESOLUTION_SUBTITLES = {
  'initial_trustee_meeting': 'Initial Trustee Resolution & Minutes',
  'general_meeting': 'General Meeting & Resolutions',
  'acceptance_of_property': 'Resolution to Accept Property into Trust',
  'disposition_of_asset': 'Resolution to Dispose of Trust Asset',
  'distribution_to_beneficiaries': 'Resolution to Distribute',
  'appointment_additional_trustee': 'Resolution to Appoint Trustee',
  'appointment_successor_trustee': 'Resolution to Appoint Successor',
  'designation_of_beneficiaries': 'Resolution to Designate Beneficiaries',
  'bank_account_authorization': 'Resolution to Open Bank Account',
  'change_of_situs': 'Resolution to Change Situs',
  'benevolence_approval': 'Resolution to Approve Assistance',
  'investment_policy': 'Resolution to Approve Investment Policy',
  'loan_authorization': 'Resolution to Authorize Loan',
  'insurance_authorization': 'Resolution to Authorize Insurance',
  'annual_review': 'Annual Review Resolution',
  'quarterly_review': 'Quarterly Review Resolution',
  'trustee_compensation': 'Resolution to Approve Compensation',
  'trustee_resignation': 'Resolution for Trustee Resignation',
  'beneficiary_request_denial': 'Resolution to Deny Request',
  'hems_distribution': 'Resolution for HEMS Distribution',
  'beneficiary_distribution_notice': 'Resolution for Distribution Notice',
  'beneficiary_loan': 'Resolution to Authorize Beneficiary Loan',
  'evaluate_distribution': 'Resolution to Evaluate Distribution',
  'trust_amendment': 'Resolution to Amend Trust',
  'power_of_attorney': 'Resolution to Authorize POA',
  'trust_termination': 'Resolution to Terminate Trust',
  'real_estate_purchase': 'Resolution to Purchase Real Estate',
  'business_interest_acquisition': 'Resolution to Acquire Business Interest',
  'real_estate_lease': 'Resolution to Lease Real Estate',
  'fiscal_year_election': 'Resolution for Fiscal Year Election',
  'tax_filing_authorization': 'Resolution to Authorize Tax Filing',
  'emergency_ratification': 'Resolution to Ratify Emergency Action',
  'conflict_of_interest': 'Resolution to Disclose Conflict',
  'bill_of_sale': 'Resolution & Bill of Sale',
  'assignment_of_personal_property': 'Resolution to Assign Property',
  'general_assignment': 'Resolution for General Assignment',
};

export default function MinutesTemplatesPage() {
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (selectedTrust) {
      loadTemplates();
    }
  }, [selectedTrust]);

  const loadTemplates = async () => {
    try {
      const url = selectedTrust 
        ? `/template-options?trust_id=${selectedTrust.trust_id}` 
        : '/template-options';
      const response = await fetchWithAuth(url);
      if (response.ok) {
        setTemplates(await response.json());
      }
    } catch (error) {
      console.error('Failed to load templates:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTemplate = (templateType) => {
    if (!selectedTrust) {
      toast.error('Please select a trust first');
      return;
    }
    
    if (templateType === 'blank') {
      navigate('/minutes/create');
    } else {
      navigate(`/minutes/template/${templateType}`);
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
              className="btn-secondary mb-4"
              onClick={() => navigate('/minutes')}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Minutes
            </Button>
            <h1 className="font-serif text-3xl lg:text-4xl text-navy mb-2">Create Minutes</h1>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              {selectedTrust.name} • Choose a Template
            </p>
          </div>

          {/* Template Grid */}
          {loading ? (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3, 4, 5, 6].map(i => (
                <div key={i} className="card-trust p-6 animate-pulse">
                  <div className="h-10 w-10 bg-muted rounded mb-4"></div>
                  <div className="h-5 bg-muted rounded w-2/3 mb-2"></div>
                  <div className="h-4 bg-muted rounded w-full"></div>
                </div>
              ))}
            </div>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {templates.sort((a, b) => (b.priority ? 1 : 0) - (a.priority ? 1 : 0)).map(template => {
                const IconComponent = ICONS[template.icon] || FileText;
                return (
                  <button
                    key={template.type}
                    onClick={() => handleSelectTemplate(template.type)}
                    className="card-trust p-6 text-left hover:border-gold transition-colors group relative"
                    data-testid={`template-${template.type}`}
                  >
                    {template.priority && (
                      <span className="absolute top-3 right-3 bg-gold/10 text-gold border border-gold/30 text-xs font-medium px-2 py-1 rounded-full">
                        Start Here
                      </span>
                    )}
                    <div className="flex items-start justify-between">
                      <div className="w-12 h-12 bg-navy/10 flex items-center justify-center mb-4 group-hover:bg-gold/20 transition-colors">
                        <IconComponent className="w-6 h-6 text-navy" />
                      </div>
                      <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-navy/70 transition-colors" />
                    </div>
                    <h3 className="font-serif text-lg text-navy mb-2">{template.name}</h3>
                    <p className="text-sm text-muted-foreground">{RESOLUTION_SUBTITLES[template.type] || template.description}</p>
                    {RESOLUTION_SUBTITLES[template.type] && (
                      <p className="text-xs text-muted-foreground/70 mt-1">{template.description}</p>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {/* Info Box */}
          <div className="mt-8 p-6 bg-navy/5 border border-navy/10">
            <h4 className="font-serif text-lg text-navy mb-2">About Templates</h4>
            <p className="text-sm text-muted-foreground">
              Templates provide pre-filled language following private trust governance standards. 
              All generated documents are editable and maintain an audit trail of any changes. 
              The formal WHEREAS/RESOLVED format follows established trust administration practices.
            </p>
          </div>
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
