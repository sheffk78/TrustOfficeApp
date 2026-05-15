import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { PDFPreviewModal } from '@/components/PDFPreviewModal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar as CalendarPicker } from '@/components/ui/calendar';
import { fetchWithAuth } from '@/utils/api';
import { 
  Plus, 
  FileText,
  Search,
  Calendar,
  Users,
  ChevronRight,
  ChevronDown,
  Eye,
  Loader2,
  Pencil
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
  const [dateFrom, setDateFrom] = useState(null);
  const [dateTo, setDateTo] = useState(null);
  const [dateFromOpen, setDateFromOpen] = useState(false);
  const [dateToOpen, setDateToOpen] = useState(false);
  const [pdfPreview, setPdfPreview] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  // Drafts state
  const [drafts, setDrafts] = useState([]);
  const [draftsOpen, setDraftsOpen] = useState(false);
  const [draftsLoading, setDraftsLoading] = useState(false);

  const debouncedSearch = useDebounce(searchTerm, 300);

  useEffect(() => {
    if (selectedTrust) {
      loadMinutes(debouncedSearch);
      loadDrafts();
    }
  }, [selectedTrust, debouncedSearch, dateFrom, dateTo]);

  const loadMinutes = async (search = '') => {
    if (!selectedTrust) {
      setLoading(false);
      return;
    }
    
    setLoading(true);
    try {
      let url = `/minutes?trust_id=${selectedTrust.trust_id}`;
      if (search) {
        url += `&search=${encodeURIComponent(search)}`;
      }
      if (dateFrom) {
        url += `&date_from=${format(dateFrom, 'yyyy-MM-dd')}`;
      }
      if (dateTo) {
        url += `&date_to=${format(dateTo, 'yyyy-MM-dd')}`;
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

  const loadDrafts = async () => {
    if (!selectedTrust) return;
    setDraftsLoading(true);
    try {
      const url = `/minutes?status=draft&trust_id=${selectedTrust.trust_id}`;
      const response = await fetchWithAuth(url);
      if (response.ok) {
        setDrafts(await response.json());
      }
    } catch (error) {
      console.error('Failed to load drafts:', error);
    } finally {
      setDraftsLoading(false);
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

  const getTemplateTypeLabel = (type) => {
    switch (type) {
      case 'guided': return 'Guided';
      case 'manual': return 'Manual';
      case 'ai': return 'AI';
      default: return type;
    }
  };

  const filteredMinutes = minutes.filter(m => {
    const entryType = m.entry_type || m.minutes_type || '';
    const matchesType = filterType === 'all' || entryType === filterType;
    return matchesType;
  });

  // Handle create minutes button with read-only check
  const handleCreateMinutes = () => {
    if (isReadOnly) {
      showUpgradeModal('create meeting minutes', 'button_click', 'minutes_page');
      return;
    }
    navigate('/minutes/create');
  };

  return (
    <div className="main-layout" data-testid="minutes-page">
      <Sidebar />
      <main className="main-content">
        {/* Subscription Banners */}
        
        <div className="page-container">
          {/* Page Header */}
          <div className="flex items-start justify-between mb-8">
            <div>
              <h1 className="page-title">Minutes & Decisions</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'}
              </p>
            </div>
            <Button 
              onClick={handleCreateMinutes}
              className={`btn-primary ${isReadOnly ? 'opacity-60' : ''}`}
              data-testid="create-minutes-btn"
            >
              <Plus className="w-4 h-4 mr-2" />
              Create Minutes
            </Button>
          </div>

          {/* Drafts Section */}
          {drafts.length > 0 && (
            <div className="card-trust mb-6">
              <button
                className="flex items-center justify-between w-full text-left"
                onClick={() => setDraftsOpen(!draftsOpen)}
                data-testid="drafts-toggle"
              >
                <div className="flex items-center gap-2">
                  <Pencil className="w-4 h-4 text-gold" />
                  <span className="font-serif text-lg text-navy">Drafts</span>
                  <span className="ml-1 px-2 py-0.5 text-xs font-mono bg-gold/20 text-gold rounded-full">
                    {drafts.length}
                  </span>
                </div>
                {draftsOpen ? (
                  <ChevronDown className="w-5 h-5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="w-5 h-5 text-muted-foreground" />
                )}
              </button>
              {draftsOpen && (
                <div className="mt-4 space-y-3">
                  {drafts.map((draft) => {
                    const summary = draft.summary || `${(draft.minutes_type || 'Meeting').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())} Minutes`;
                    const entryDate = draft.date || draft.meeting_date;
                    const entryType = draft.entry_type || draft.minutes_type || 'meeting';
                    return (
                      <div
                        key={draft.minutes_id}
                        className="flex items-center justify-between p-3 bg-navy/[0.03] border border-navy/10 rounded"
                        data-testid={`draft-item-${draft.minutes_id}`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-serif text-navy">{summary}</span>
                            <span className="badge-trust">{getEntryTypeLabel(entryType)}</span>
                            {draft.template_type && (
                              <span className="px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider bg-blue-100 text-blue-700 rounded">
                                {getTemplateTypeLabel(draft.template_type)}
                              </span>
                            )}
                          </div>
                          {entryDate && (
                            <span className="font-mono text-xs text-muted-foreground mt-1 block">
                              {formatDate(entryDate)}
                            </span>
                          )}
                        </div>
                        <Button
                          size="sm"
                          onClick={() => navigate(`/minutes/create?draft_id=${draft.minutes_id}`)}
                          className="btn-primary text-xs ml-4"
                          data-testid={`continue-draft-${draft.minutes_id}`}
                        >
                          Continue
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

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
              <div className="flex gap-2 items-center flex-wrap">
                <Popover open={dateFromOpen} onOpenChange={setDateFromOpen}>
                  <PopoverTrigger asChild>
                    <Button variant="outline" size="sm" className="font-mono text-xs h-9" data-testid="date-from-btn">
                      <Calendar className="w-3.5 h-3.5 mr-1.5" />
                      {dateFrom ? format(dateFrom, 'MMM d, yyyy') : 'From'}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <CalendarPicker mode="single" selected={dateFrom}
                      onSelect={d => { setDateFrom(d); setDateFromOpen(false); }} />
                  </PopoverContent>
                </Popover>
                <span className="text-muted-foreground text-xs">—</span>
                <Popover open={dateToOpen} onOpenChange={setDateToOpen}>
                  <PopoverTrigger asChild>
                    <Button variant="outline" size="sm" className="font-mono text-xs h-9" data-testid="date-to-btn">
                      <Calendar className="w-3.5 h-3.5 mr-1.5" />
                      {dateTo ? format(dateTo, 'MMM d, yyyy') : 'To'}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <CalendarPicker mode="single" selected={dateTo}
                      onSelect={d => { setDateTo(d); setDateToOpen(false); }} />
                  </PopoverContent>
                </Popover>
                {(dateFrom || dateTo) && (
                  <Button variant="ghost" size="sm" className="h-9 px-2 text-xs text-muted-foreground"
                    onClick={() => { setDateFrom(null); setDateTo(null); }} data-testid="clear-dates-btn">
                    Clear
                  </Button>
                )}
              </div>
            </div>
            <div className="flex gap-2 mt-3">
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
              <Button onClick={() => navigate('/minutes/create')} className="btn-primary">
                Create Minutes
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredMinutes.map((entry) => {
                const summary = entry.summary || `${(entry.minutes_type || 'Meeting').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())} Minutes`;
                const details = entry.details || entry.decisions_text || '';
                const entryDate = entry.date || entry.meeting_date;
                const entryType = entry.entry_type || entry.minutes_type || 'meeting';
                
                // Count both trustees and other attendees
                const trusteeCount = entry.participants?.length || (entry.participants_text ? entry.participants_text.split(',').filter(p => p.trim()).length : 0);
                const otherCount = entry.other_attendees_text ? entry.other_attendees_text.split(',').filter(p => p.trim()).length : 0;
                const totalParticipants = trusteeCount + otherCount;
                
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
                          <span className="font-mono text-xs">{totalParticipants} participant{totalParticipants !== 1 ? 's' : ''}</span>
                        </div>
                        <span className="badge-trust">
                          {getEntryTypeLabel(entryType)}
                        </span>
                        {entry.template_type && (
                          <span className="px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider bg-blue-100 text-blue-700 rounded">
                            {getTemplateTypeLabel(entry.template_type)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )})}
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* PDF Preview Modal */}
      <PDFPreviewModal
        open={!!pdfPreview}
        onOpenChange={(open) => !open && setPdfPreview(null)}
        pdfBase64={pdfPreview?.base64}
        title="Minutes PDF Preview"
        filename={pdfPreview?.filename || 'minutes.pdf'}
      />
    </div>
  );
}