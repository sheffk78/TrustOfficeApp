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
  HeartHandshake
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
  'heart-handshake': HeartHandshake
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
      navigate('/minutes/new');
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
              className="mb-4"
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
              {templates.map(template => {
                const IconComponent = ICONS[template.icon] || FileText;
                return (
                  <button
                    key={template.type}
                    onClick={() => handleSelectTemplate(template.type)}
                    className="card-trust p-6 text-left hover:border-gold transition-colors group"
                    data-testid={`template-${template.type}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="w-12 h-12 bg-navy/10 flex items-center justify-center mb-4 group-hover:bg-gold/20 transition-colors">
                        <IconComponent className="w-6 h-6 text-navy" />
                      </div>
                      <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-gold transition-colors" />
                    </div>
                    <h3 className="font-serif text-lg text-navy mb-2">{template.name}</h3>
                    <p className="text-sm text-muted-foreground">{template.description}</p>
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
              The ecclesiastical language and WHEREAS/RESOLVED format follows established trust administration practices.
            </p>
          </div>
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}
