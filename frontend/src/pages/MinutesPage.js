import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Sidebar } from '@/components/Sidebar';
import { ReadOnlyBanner } from '@/components/ReadOnlyBanner';
import { TrialBanner } from '@/components/TrialBanner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { 
  Plus, 
  FileText,
  Search,
  Calendar,
  Users,
  ChevronRight,
  Download,
  Eye,
  X,
  Loader2
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { toast } from 'sonner';

// Debounce hook
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}

export default function MinutesPage() {
  const navigate = useNavigate();
  const { selectedTrust, isReadOnly } = useAuth();
  const { showUpgradeModal } = useUpgradeModal();
  const [minutes, setMinutes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [pdfPreview, setPdfPreview] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  const debouncedSearch = useDebounce(searchTerm, 300);

  useEffect(() => {
    if (selectedTrust) {
      loadMinutes(debouncedSearch);
    }
  }, [selectedTrust, debouncedSearch]);

  const loadMinutes = async (search = '') => {
    if (!selectedTrust) return;
    
    setLoading(true);
    try {
      let url = `/minutes?trust_id=${selectedTrust.trust_id}`;
      if (search) {
        url += `&search=${encodeURIComponent(search)}`;
      }
      const response = await fetchWithAuth(url);
      if (response.ok) {
        setMinutes(await response.json());
      }
    } catch (error) {
      console.error('Failed to load minutes:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleViewPdf = async (minutesId) => {
    setPdfLoading(true);
    try {
      const response = await fetchWithAuth(`/minutes/${minutesId}/pdf`);
      if (response.ok) {
        const data = await response.json();
        setPdfPreview({
          base64: data.pdf_base64,
          filename: data.filename,
          minutesId
        });
      } else {
        toast.error('Failed to generate PDF');
      }
    } catch (error) {
      toast.error('Failed to generate PDF');
    } finally {
      setPdfLoading(false);
    }
  };

  const handleDownloadPdf = () => {
    if (!pdfPreview) return;
    
    const link = document.createElement('a');
    link.href = `data:application/pdf;base64,${pdfPreview.base64}`;
    link.download = pdfPreview.filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success('PDF downloaded');
  };

  const formatDate = (dateString) => {
    try {
      return format(parseISO(dateString), 'MMM d, yyyy');
    } catch {
      return dateString;
    }
  };

  const getEntryTypeLabel = (type) => {
    switch (type) {
      case 'meeting': return 'Meeting';
      case 'decision': return 'Decision';
      case 'distribution_approval': return 'Distribution Approval';
      default: return type;
    }
  };

  const filteredMinutes = minutes.filter(m => {
    const entryType = m.entry_type || m.minutes_type || '';
    const matchesType = filterType === 'all' || entryType === filterType;
    return matchesType;
  });

  return (
    <div className="main-layout" data-testid="minutes-page">
      <Sidebar />
      <main className="main-content">
        <div className="page-container">
          {/* Page Header */}
          <div className="flex items-start justify-between mb-8">
            <div>
              <h1 className="page-title">Minutes & Decisions</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'}
              </p>
            </div>
            <div className="flex gap-2">
              <Button 
                onClick={() => navigate('/minutes/templates')}
                className="btn-primary"
                data-testid="record-minutes-btn"
              >
                <Plus className="w-4 h-4 mr-2" />
                Record Minutes
              </Button>
            </div>
          </div>

          {/* Filters */}
          <div className="card-trust mb-6">
            <div className="flex flex-col md:flex-row gap-4">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search minutes..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10 input-trust"
                  data-testid="search-minutes"
                />
              </div>
              <div className="flex gap-2">
                {['all', 'meeting', 'decision', 'distribution_approval'].map((type) => (
                  <button
                    key={type}
                    onClick={() => setFilterType(type)}
                    className={`px-4 py-2 font-mono text-xs uppercase tracking-widest border ${
                      filterType === type 
                        ? 'bg-navy text-white border-navy' 
                        : 'bg-white text-navy border-navy/20 hover:border-navy'
                    }`}
                    data-testid={`filter-${type}`}
                  >
                    {type === 'all' ? 'All' : getEntryTypeLabel(type)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Minutes List */}
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="card-trust">
                  <div className="skeleton h-6 w-48 mb-2"></div>
                  <div className="skeleton h-4 w-full"></div>
                </div>
              ))}
            </div>
          ) : filteredMinutes.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">
                <FileText className="w-16 h-16 text-navy/20" />
              </div>
              <h2 className="font-serif text-2xl text-navy mb-2">No Minutes Found</h2>
              <p className="text-muted-foreground mb-6">
                {searchTerm ? 'Try a different search term' : 'Record your first minutes to get started'}
              </p>
              <Button onClick={() => navigate('/minutes/new')} className="btn-primary">
                Record Minutes
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredMinutes.map((entry) => {
                const summary = entry.summary || `${(entry.minutes_type || 'Meeting').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())} Minutes`;
                const details = entry.details || entry.decisions_text || '';
                const entryDate = entry.date || entry.meeting_date;
                const entryType = entry.entry_type || entry.minutes_type || 'meeting';
                const participantCount = entry.participants?.length || (entry.participants_text ? entry.participants_text.split(',').length : 0);
                
                return (
                <div 
                  key={entry.minutes_id} 
                  className="card-trust hover-lift"
                  data-testid={`minutes-entry-${entry.minutes_id}`}
                >
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 bg-navy/5 flex items-center justify-center flex-shrink-0">
                      <FileText className="w-6 h-6 text-navy" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-4">
                        <div className="cursor-pointer" onClick={() => navigate(`/minutes/${entry.minutes_id}`)}>
                          <h3 className="font-serif text-lg text-navy mb-1 hover:text-gold transition-colors">{summary}</h3>
                          <p className="text-sm text-muted-foreground line-clamp-2">{details}</p>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleViewPdf(entry.minutes_id);
                            }}
                            disabled={pdfLoading}
                            className="btn-secondary text-xs"
                            data-testid={`view-pdf-${entry.minutes_id}`}
                          >
                            {pdfLoading ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <>
                                <Eye className="w-4 h-4 mr-1" />
                                PDF
                              </>
                            )}
                          </Button>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-4 mt-3">
                        <div className="flex items-center gap-1 text-muted-foreground">
                          <Calendar className="w-4 h-4" />
                          <span className="font-mono text-xs">{formatDate(entryDate)}</span>
                        </div>
                        <div className="flex items-center gap-1 text-muted-foreground">
                          <Users className="w-4 h-4" />
                          <span className="font-mono text-xs">{participantCount} participants</span>
                        </div>
                        <span className="badge-trust">
                          {getEntryTypeLabel(entryType)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )})}
            </div>
          )}
        </div>
      </main>

      {/* PDF Preview Modal */}
      {pdfPreview && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" data-testid="pdf-preview-modal">
          <div className="bg-white w-full max-w-4xl h-[80vh] flex flex-col corner-mark">
            <div className="flex items-center justify-between p-4 border-b border-navy/10">
              <h2 className="font-serif text-xl text-navy">Minutes PDF Preview</h2>
              <div className="flex items-center gap-3">
                <Button
                  onClick={handleDownloadPdf}
                  className="btn-primary"
                  data-testid="download-pdf-btn"
                >
                  <Download className="w-4 h-4 mr-2" />
                  Download
                </Button>
                <button 
                  onClick={() => setPdfPreview(null)}
                  className="text-navy hover:text-gold"
                  data-testid="close-pdf-modal"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>
            <div className="flex-1 p-4 bg-subtle-bg overflow-auto">
              <object
                data={`data:application/pdf;base64,${pdfPreview.base64}`}
                type="application/pdf"
                className="w-full h-full border border-navy/10"
                title="Minutes PDF Preview"
              >
                <div className="flex flex-col items-center justify-center h-full text-center p-8">
                  <FileText className="w-16 h-16 text-navy/30 mb-4" />
                  <p className="text-navy mb-4">PDF preview not supported in this browser.</p>
                  <Button onClick={handleDownloadPdf} className="btn-primary">
                    <Download className="w-4 h-4 mr-2" />
                    Download PDF to View
                  </Button>
                </div>
              </object>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
