import { useState, useEffect, useCallback } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { 
  Search, 
  FileText, 
  Calendar, 
  Users, 
  Loader2, 
  Check,
  Link2
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

/**
 * AttachMinutesDialog - Dialog for linking money records to existing minutes
 * 
 * Used in the "Money → Minutes" flow where trustees can attach an existing
 * minutes record to a compensation payment, distribution, or benevolence record.
 * 
 * @param {boolean} open - Controls dialog visibility
 * @param {function} onOpenChange - Callback when dialog state changes
 * @param {string} trustId - The trust ID to search within
 * @param {string} recordType - Type of record: 'compensation', 'distribution', or 'benevolence'
 * @param {string} recordId - The ID of the money record to attach minutes to
 * @param {function} onAttached - Callback after successfully attaching minutes
 */
export function AttachMinutesDialog({
  open,
  onOpenChange,
  trustId,
  recordType,
  recordId,
  onAttached
}) {
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [minutesType, setMinutesType] = useState('');
  const [minutes, setMinutes] = useState([]);
  const [selectedMinutes, setSelectedMinutes] = useState(null);
  const [attaching, setAttaching] = useState(false);

  // Search minutes when filters change
  const searchMinutes = useCallback(async () => {
    if (!trustId) return;
    
    setSearching(true);
    try {
      const params = new URLSearchParams({ trust_id: trustId, limit: '20' });
      if (searchQuery) params.append('query', searchQuery);
      if (minutesType) params.append('minutes_type', minutesType);
      
      const response = await fetchWithAuth(`/guided-minutes/search?${params.toString()}`);
      if (response.ok) {
        const data = await response.json();
        setMinutes(data);
      } else {
        toast.error('Failed to search minutes');
      }
    } catch (error) {
      console.error('Error searching minutes:', error);
      toast.error('Failed to search minutes');
    } finally {
      setSearching(false);
    }
  }, [trustId, searchQuery, minutesType]);

  // Load initial minutes when dialog opens
  useEffect(() => {
    if (open && trustId) {
      searchMinutes();
    }
  }, [open, trustId, searchMinutes]);

  // Handle attaching minutes to the record
  const handleAttach = async () => {
    if (!selectedMinutes || !recordId) return;
    
    setAttaching(true);
    try {
      let endpoint = '';
      if (recordType === 'compensation') {
        endpoint = `/compensation-payments/${recordId}/attach-minutes`;
      } else if (recordType === 'distribution') {
        endpoint = `/distributions/${recordId}/attach-minutes`;
      } else if (recordType === 'benevolence') {
        endpoint = `/benevolence/${recordId}/attach-minutes`;
      }
      
      const response = await fetchWithAuth(endpoint, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes_record_id: selectedMinutes.minutes_id })
      });
      
      if (response.ok) {
        toast.success('Minutes linked successfully');
        onAttached && onAttached(selectedMinutes.minutes_id);
        onOpenChange(false);
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to link minutes');
      }
    } catch (error) {
      console.error('Error attaching minutes:', error);
      toast.error('Failed to link minutes');
    } finally {
      setAttaching(false);
    }
  };

  // Format date for display
  const formatDate = (dateStr) => {
    try {
      if (dateStr.includes('T')) {
        return format(parseISO(dateStr), 'MMM d, yyyy');
      }
      return format(new Date(dateStr + 'T00:00:00'), 'MMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  // Get minutes type label
  const getTypeLabel = (type) => {
    const labels = {
      annual: 'Annual Meeting',
      quarterly: 'Quarterly Meeting',
      compensation: 'Compensation',
      distribution: 'Distribution',
      solvency: 'Solvency',
      general: 'General'
    };
    return labels[type] || type;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="attach-minutes-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy dark:text-gold flex items-center gap-2">
            <Link2 className="w-5 h-5" />
            Link to Existing Minutes
          </DialogTitle>
          <DialogDescription>
            Search and select a minutes record to link to this {recordType} record.
            This creates a reference without modifying the minutes text.
          </DialogDescription>
        </DialogHeader>

        {/* Search Controls */}
        <div className="space-y-4">
          <div className="flex gap-3">
            <div className="flex-1">
              <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-2 block">
                Search
              </Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && searchMinutes()}
                  placeholder="Search minutes..."
                  className="pl-10"
                  data-testid="minutes-search-input"
                />
              </div>
            </div>
            <div className="w-48">
              <Label className="font-mono text-xs uppercase tracking-widest text-navy/70 dark:text-white/70 mb-2 block">
                Type
              </Label>
              <Select value={minutesType || "all"} onValueChange={(val) => setMinutesType(val === "all" ? "" : val)}>
                <SelectTrigger data-testid="minutes-type-filter">
                  <SelectValue placeholder="All types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All types</SelectItem>
                  <SelectItem value="annual">Annual</SelectItem>
                  <SelectItem value="quarterly">Quarterly</SelectItem>
                  <SelectItem value="compensation">Compensation</SelectItem>
                  <SelectItem value="distribution">Distribution</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button 
                onClick={searchMinutes}
                disabled={searching}
                variant="outline"
                data-testid="search-minutes-btn"
              >
                {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              </Button>
            </div>
          </div>

          {/* Minutes List */}
          <div className="border border-navy/10 dark:border-white/10 max-h-80 overflow-y-auto">
            {searching ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-navy/30 dark:text-gold/30" />
              </div>
            ) : minutes.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <FileText className="w-10 h-10 text-navy/20 dark:text-white/20 mb-2" />
                <p className="text-muted-foreground text-sm">No minutes found</p>
                <p className="text-muted-foreground text-xs mt-1">
                  Try adjusting your search or create new minutes first
                </p>
              </div>
            ) : (
              <div className="divide-y divide-navy/10 dark:divide-white/10">
                {minutes.map((m) => (
                  <button
                    key={m.minutes_id}
                    onClick={() => setSelectedMinutes(m)}
                    className={`w-full text-left p-4 transition-colors ${
                      selectedMinutes?.minutes_id === m.minutes_id
                        ? 'bg-navy/5 dark:bg-gold/5 border-l-2 border-navy dark:border-gold'
                        : 'hover:bg-subtle-bg dark:hover:bg-slate-800'
                    }`}
                    data-testid={`minutes-item-${m.minutes_id}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-mono text-xs uppercase tracking-widest text-navy dark:text-gold">
                            {getTypeLabel(m.minutes_type)}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            • {formatDate(m.meeting_date)}
                          </span>
                        </div>
                        {m.participants_text && (
                          <div className="flex items-center gap-1 text-sm text-muted-foreground mb-1">
                            <Users className="w-3 h-3" />
                            <span className="truncate">{m.participants_text}</span>
                          </div>
                        )}
                        {m.preview && (
                          <p className="text-sm text-navy/70 dark:text-white/70 line-clamp-2">
                            {m.preview}
                          </p>
                        )}
                      </div>
                      {selectedMinutes?.minutes_id === m.minutes_id && (
                        <div className="ml-3 flex-shrink-0">
                          <div className="w-6 h-6 bg-navy dark:bg-gold flex items-center justify-center">
                            <Check className="w-4 h-4 text-white dark:text-navy" />
                          </div>
                        </div>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button 
            variant="outline" 
            onClick={() => onOpenChange(false)}
            data-testid="cancel-attach-btn"
          >
            Cancel
          </Button>
          <Button
            onClick={handleAttach}
            disabled={!selectedMinutes || attaching}
            className="btn-primary"
            data-testid="confirm-attach-btn"
          >
            {attaching ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Linking...
              </>
            ) : (
              <>
                <Link2 className="w-4 h-4 mr-2" />
                Link Minutes
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default AttachMinutesDialog;
