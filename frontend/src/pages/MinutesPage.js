import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { 
  Plus, 
  FileText,
  Search,
  Calendar,
  Users,
  ChevronRight
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

export default function MinutesPage() {
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  const [minutes, setMinutes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');

  useEffect(() => {
    if (selectedTrust) {
      loadMinutes();
    }
  }, [selectedTrust]);

  const loadMinutes = async () => {
    if (!selectedTrust) return;
    
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/minutes?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        setMinutes(await response.json());
      }
    } catch (error) {
      console.error('Failed to load minutes:', error);
    } finally {
      setLoading(false);
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

  const filteredMinutes = minutes.filter(m => {
    const summary = m.summary || m.minutes_type || '';
    const details = m.details || m.decisions_text || '';
    const entryType = m.entry_type || m.minutes_type || '';
    const matchesSearch = summary.toLowerCase().includes(searchTerm.toLowerCase()) ||
      details.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesType = filterType === 'all' || entryType === filterType;
    return matchesSearch && matchesType;
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
            <Button 
              onClick={() => navigate('/minutes/new')}
              className="btn-primary"
              data-testid="record-minutes-btn"
            >
              <Plus className="w-4 h-4 mr-2" />
              Record Minutes
            </Button>
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
              {filteredMinutes.map((entry) => (
                <div 
                  key={entry.minutes_id} 
                  className="card-trust hover-lift cursor-pointer"
                  onClick={() => navigate(`/minutes/${entry.minutes_id}`)}
                  data-testid={`minutes-entry-${entry.minutes_id}`}
                >
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 bg-navy/5 flex items-center justify-center flex-shrink-0">
                      <FileText className="w-6 h-6 text-navy" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h3 className="font-serif text-lg text-navy mb-1">{entry.summary}</h3>
                          <p className="text-sm text-muted-foreground line-clamp-2">{entry.details}</p>
                        </div>
                        <ChevronRight className="w-5 h-5 text-navy/40 flex-shrink-0" />
                      </div>
                      <div className="flex flex-wrap items-center gap-4 mt-3">
                        <div className="flex items-center gap-1 text-muted-foreground">
                          <Calendar className="w-4 h-4" />
                          <span className="font-mono text-xs">{formatDate(entry.date)}</span>
                        </div>
                        <div className="flex items-center gap-1 text-muted-foreground">
                          <Users className="w-4 h-4" />
                          <span className="font-mono text-xs">{entry.participants.length} participants</span>
                        </div>
                        <span className="badge-trust">
                          {getEntryTypeLabel(entry.entry_type)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
