import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import {
  Search,
  ArrowUpDown,
  Filter,
  Layers,
  CheckSquare,
  Square,
  Archive,
  Download,
  Trash2,
  Plus,
  ChevronDown,
  ChevronRight,
  Landmark,
  HeartHandshake,
  Briefcase,
  Church,
  Building2,
  X,
  Loader2,
  Settings2,
  FolderTree,
  FileText,
  AlertTriangle,
  Check,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const TRUST_TYPES = [
  { value: 'family', label: 'Family', icon: HeartHandshake },
  { value: 'charitable', label: 'Charitable', icon: HeartHandshake },
  { value: 'business', label: 'Business', icon: Briefcase },
  { value: 'ecclesiastical', label: 'Religious/Charitable', icon: Church },
  { value: 'institutional', label: 'Institutional', icon: Building2 },
];

const SORT_OPTIONS = [
  { value: 'name-asc', label: 'Name (A–Z)' },
  { value: 'name-desc', label: 'Name (Z–A)' },
  { value: 'created-desc', label: 'Newest First' },
  { value: 'created-asc', label: 'Oldest First' },
  { value: 'score-desc', label: 'Highest Score' },
  { value: 'score-asc', label: 'Lowest Score' },
];

const GROUP_OPTIONS = [
  { value: 'none', label: 'Flat List' },
  { value: 'type', label: 'By Type' },
  { value: 'status', label: 'By Score' },
];

const STATUS_TIERS = [
  { key: 'healthy', label: 'Healthy (96+)', min: 96, color: 'success' },
  { key: 'attention', label: 'Needs Attention (72–95)', min: 72, max: 95, color: 'warning' },
  { key: 'critical', label: 'Critical (<72)', min: 0, max: 71, color: 'error' },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

const getTrustTypeIcon = (type) => {
  const found = TRUST_TYPES.find((t) => t.value === type);
  return found ? found.icon : Landmark;
};

const getTrustTypeLabel = (type) => {
  const found = TRUST_TYPES.find((t) => t.value === type);
  return found ? found.label : type || 'Unknown';
};

const getScoreTier = (score) => {
  if (score >= 96) return STATUS_TIERS[0];
  if (score >= 72) return STATUS_TIERS[1];
  return STATUS_TIERS[2];
};

const getScoreColorClass = (score) => {
  if (score >= 96) return 'text-success';
  if (score >= 72) return 'text-warning';
  return 'text-error';
};

const getScoreBgClass = (score) => {
  if (score >= 96) return 'bg-success/10 text-success';
  if (score >= 72) return 'bg-warning/10 text-warning';
  return 'bg-error/10 text-error';
};

const formatDate = (dateString) => {
  if (!dateString) return '—';
  try {
    return format(parseISO(dateString), 'MMM d, yyyy');
  } catch {
    return dateString;
  }
};

// ─── Sub-components ──────────────────────────────────────────────────────────

function TrustTypeIcon({ type, className = 'w-4 h-4' }) {
  const Icon = getTrustTypeIcon(type);
  return <Icon className={className} />;
}

function FilterChip({ label, active, onClick, onClear }) {
  return (
    <div
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 border text-xs font-mono uppercase tracking-wider cursor-pointer transition-colors ${
        active
          ? 'border-navy bg-navy text-white'
          : 'border-navy/20 text-navy hover:border-navy/40 bg-white'
      }`}
      onClick={onClick}
    >
      {label}
      {active && onClear && (
        <X
          className="w-3 h-3 hover:text-navy/70"
          onClick={(e) => {
            e.stopPropagation();
            onClear();
          }}
        />
      )}
    </div>
  );
}

function TrustCard({
  trust,
  isSelected,
  onToggleSelect,
  onSelect,
  onArchive,
  onDelete,
  isReadOnly,
}) {
  const score = trust.governance_score ?? 0;
  const tier = getScoreTier(score);

  return (
    <div
      className={`card-trust transition-all hover:shadow-md ${
        isSelected ? 'ring-2 ring-gold ring-offset-2' : ''
      }`}
      data-testid={`trust-card-${trust.trust_id}`}
    >
      {/* Selection checkbox + header */}
      <div className="flex items-start gap-3 mb-4">
        <button
          onClick={() => onToggleSelect(trust.trust_id)}
          className="mt-1 flex-shrink-0 text-navy/40 hover:text-navy transition-colors"
          data-testid={`trust-select-${trust.trust_id}`}
        >
          {isSelected ? (
            <CheckSquare className="w-5 h-5 text-gold" />
          ) : (
            <Square className="w-5 h-5" />
          )}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <TrustTypeIcon type={trust.trust_type} className="w-4 h-4 text-navy/60" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-navy/50">
              {getTrustTypeLabel(trust.trust_type)}
            </span>
          </div>
          <h3
            className="font-serif text-lg text-navy truncate cursor-pointer hover:text-navy/70 transition-colors"
            onClick={() => onSelect(trust)}
          >
            {trust.name}
          </h3>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        {/* Score */}
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-navy/40 mb-1">
            Score
          </p>
          <div className="flex items-center gap-2">
            <span className={`font-mono text-xl font-bold ${getScoreColorClass(score)}`}>
              {score}
            </span>
            <span className={`px-1.5 py-0.5 text-[9px] font-mono uppercase ${getScoreBgClass(score)}`}>
              {tier.label.split(' ')[0]}
            </span>
          </div>
        </div>
        {/* Jurisdiction */}
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-navy/40 mb-1">
            State
          </p>
          <p className="text-sm text-navy font-medium">{trust.jurisdiction || '—'}</p>
        </div>
        {/* Created */}
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-navy/40 mb-1">
            Created
          </p>
          <p className="text-sm text-navy font-medium">{formatDate(trust.created_at)}</p>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-navy/10">
        <div className="flex items-center gap-3 text-xs text-navy/50">
          {trust.ein && (
            <span className="font-mono">EIN: {trust.ein}</span>
          )}
          {trust.role && (
            <span className="font-mono">Role: {trust.role}</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            className="text-xs"
            onClick={() => onSelect(trust)}
            data-testid={`trust-open-${trust.trust_id}`}
          >
            Open
          </Button>
          {!isReadOnly && (
            <button
              onClick={() => onDelete(trust)}
              className="p-1.5 text-navy/30 hover:text-error transition-colors"
              title="Delete trust"
              data-testid={`trust-delete-${trust.trust_id}`}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function GroupHeader({ label, count, icon: Icon, colorClass }) {
  return (
    <div className="flex items-center gap-2 mb-4 mt-6 first:mt-0">
      {Icon && (
        <div className={`w-7 h-7 flex items-center justify-center ${colorClass || 'bg-navy/10 text-navy'}`}>
          <Icon className="w-4 h-4" />
        </div>
      )}
      <h3 className="font-serif text-lg text-navy">{label}</h3>
      <span className="font-mono text-xs text-navy/40 uppercase tracking-wider">
        {count} {count === 1 ? 'trust' : 'trusts'}
      </span>
      <div className="flex-1 h-px bg-navy/10" />
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

export const TrustManager = ({ embedded = false }) => {
  const navigate = useNavigate();
  const {
    user,
    trusts,
    trustsLoading,
    selectedTrust,
    setSelectedTrust,
    loadTrusts,
    isReadOnly,
  } = useAuth();

  // Local state
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [sortBy, setSortBy] = useState('name-asc');
  const [filterType, setFilterType] = useState(null);
  const [filterStatus, setFilterStatus] = useState(null);
  const [groupBy, setGroupBy] = useState('none');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [showFilters, setShowFilters] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const searchTimerRef = useRef(null);

  // Debounced search
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 250);
    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, [searchQuery]);

  // ─── Filter + Sort ─────────────────────────────────────────────────────────

  const filteredTrusts = useMemo(() => {
    let result = [...trusts];

    // Search by name or type
    if (debouncedSearch.trim()) {
      const q = debouncedSearch.toLowerCase().trim();
      result = result.filter(
        (t) =>
          t.name?.toLowerCase().includes(q) ||
          t.trust_type?.toLowerCase().includes(q) ||
          getTrustTypeLabel(t.trust_type).toLowerCase().includes(q) ||
          t.jurisdiction?.toLowerCase().includes(q) ||
          t.ein?.toLowerCase().includes(q)
      );
    }

    // Filter by type
    if (filterType) {
      result = result.filter((t) => t.trust_type === filterType);
    }

    // Filter by status (score tier)
    if (filterStatus) {
      const tier = STATUS_TIERS.find((s) => s.key === filterStatus);
      if (tier) {
        result = result.filter((t) => {
          const score = t.governance_score ?? 0;
          if (tier.max !== undefined) return score >= tier.min && score <= tier.max;
          return score >= tier.min;
        });
      }
    }

    // Sort
    const [field, direction] = sortBy.split('-');
    result.sort((a, b) => {
      let cmp = 0;
      if (field === 'name') {
        cmp = (a.name || '').localeCompare(b.name || '');
      } else if (field === 'created') {
        cmp = (a.created_at || '').localeCompare(b.created_at || '');
      } else if (field === 'score') {
        cmp = (a.governance_score ?? 0) - (b.governance_score ?? 0);
      }
      return direction === 'desc' ? -cmp : cmp;
    });

    return result;
  }, [trusts, debouncedSearch, filterType, filterStatus, sortBy]);

  // ─── Grouping ──────────────────────────────────────────────────────────────

  const groupedTrusts = useMemo(() => {
    if (groupBy === 'none') {
      return [{ key: 'all', label: 'All Trusts', trusts: filteredTrusts }];
    }

    if (groupBy === 'type') {
      const groups = {};
      for (const trust of filteredTrusts) {
        const key = trust.trust_type || 'unknown';
        if (!groups[key]) groups[key] = [];
        groups[key].push(trust);
      }
      return Object.entries(groups).map(([key, trusts]) => ({
        key,
        label: getTrustTypeLabel(key),
        icon: getTrustTypeIcon(key),
        trusts,
      }));
    }

    if (groupBy === 'status') {
      const groups = {};
      for (const trust of filteredTrusts) {
        const tier = getScoreTier(trust.governance_score ?? 0);
        if (!groups[tier.key]) groups[tier.key] = [];
        groups[tier.key].push(trust);
      }
      return STATUS_TIERS.filter((t) => groups[t.key]).map((tier) => {
        const colorMap = { success: 'bg-success/10 text-success', warning: 'bg-warning/10 text-warning', error: 'bg-error/10 text-error' };
        return {
          key: tier.key,
          label: tier.label,
          colorClass: colorMap[tier.color] || 'bg-muted/10 text-muted-foreground',
          trusts: groups[tier.key],
        };
      });
    }

    return [{ key: 'all', label: 'All Trusts', trusts: filteredTrusts }];
  }, [filteredTrusts, groupBy]);

  // ─── Bulk selection ────────────────────────────────────────────────────────

  const toggleSelect = useCallback((trustId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(trustId)) next.delete(trustId);
      else next.add(trustId);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (prev.size === filteredTrusts.length) return new Set();
      return new Set(filteredTrusts.map((t) => t.trust_id));
    });
  }, [filteredTrusts]);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  // ─── Actions ───────────────────────────────────────────────────────────────

  const handleSelectTrust = (trust) => {
    setSelectedTrust(trust);
    navigate('/dashboard');
  };

  const handleBulkArchive = async () => {
    if (selectedIds.size === 0) return;
    setArchiving(true);
    try {
      let successCount = 0;
      let failCount = 0;
      const results = await Promise.allSettled(
        Array.from(selectedIds).map((trustId) =>
          fetchWithAuth(`/trusts/${trustId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tax_status: 'archived' }),
          })
        )
      );
      for (const result of results) {
        if (result.status === 'fulfilled' && result.value.ok) successCount++;
        else failCount++;
      }
      if (successCount > 0) {
        toast.success(`Archived ${successCount} trust${successCount !== 1 ? 's' : ''}`);
      }
      if (failCount > 0) {
        toast.error(`Failed to archive ${failCount} trust${failCount !== 1 ? 's' : ''}`);
      }
      await loadTrusts();
      clearSelection();
    } catch (error) {
      toast.error('Archive operation failed');
    } finally {
      setArchiving(false);
    }
  };

  const handleBulkExport = async () => {
    if (selectedIds.size === 0) return;
    setExporting(true);
    try {
      // Export selected trusts as CSV
      const selected = trusts.filter((t) => selectedIds.has(t.trust_id));
      const headers = [
        'Trust ID',
        'Name',
        'Type',
        'Jurisdiction',
        'Role',
        'EIN',
        'Score',
        'Start Date',
        'Created At',
        'Trustees',
      ];
      const rows = selected.map((t) => {
        // Sanitize each field for CSV: quote all strings, escape internal quotes,
        // and prefix with single quote to prevent formula injection (=, +, -, @)
        const esc = (val) => {
          const s = String(val ?? '');
          const escaped = s.replace(/"/g, '""');
          // Prefix with single quote if starts with formula character
          const prefix = /^[=+\-@]/.test(s) ? "'" : '';
          return `"${prefix}${escaped}"`;
        };
        return [
          esc(t.trust_id),
          esc(t.name),
          esc(t.trust_type),
          esc(t.jurisdiction),
          esc(t.role),
          esc(t.ein),
          t.governance_score ?? 0,
          esc(t.start_date),
          esc(t.created_at),
          esc(t.trustees),
        ].join(',');
      });
      const csv = [headers.join(','), ...rows].join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trusts_export_${format(new Date(), 'yyyyMMdd')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${selected.length} trust${selected.length !== 1 ? 's' : ''} to CSV`);
      clearSelection();
    } catch (error) {
      toast.error('Export failed');
    } finally {
      setExporting(false);
    }
  };

  const handleDeleteTrust = async (trust) => {
    if (
      !confirm(
        `Are you sure you want to delete "${trust.name}"? This will permanently remove all associated data (minutes, distributions, entities, etc.). This action cannot be undone.`
      )
    )
      return;

    try {
      const resp = await fetchWithAuth(`/trusts/${trust.trust_id}`, { method: 'DELETE' });
      if (resp.ok) {
        toast.success(`"${trust.name}" deleted`);
        // If we deleted the currently selected trust, switch to another
        if (selectedTrust?.trust_id === trust.trust_id) {
          const remaining = trusts.filter((t) => t.trust_id !== trust.trust_id);
          setSelectedTrust(remaining[0] || null);
        }
        await loadTrusts();
      } else {
        toast.error('Failed to delete trust');
      }
    } catch (error) {
      toast.error('Failed to delete trust');
    }
  };

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    if (
      !confirm(
        `Delete ${selectedIds.size} trust${selectedIds.size !== 1 ? 's' : ''}? This will permanently remove ALL associated data. This cannot be undone.`
      )
    )
      return;

    setDeleting(true);
    let successCount = 0;
    let failCount = 0;
    const results = await Promise.allSettled(
      Array.from(selectedIds).map((trustId) =>
        fetchWithAuth(`/trusts/${trustId}`, { method: 'DELETE' })
      )
    );
    for (const result of results) {
      if (result.status === 'fulfilled' && result.value.ok) successCount++;
      else failCount++;
    }
    if (successCount > 0) {
      toast.success(`Deleted ${successCount} trust${successCount !== 1 ? 's' : ''}`);
    }
    if (failCount > 0) {
      toast.error(`Failed to delete ${failCount} trust${failCount !== 1 ? 's' : ''}`);
    }
    // If selected trust was deleted, pick a remaining one
    if (selectedTrust && selectedIds.has(selectedTrust.trust_id)) {
      const remaining = trusts.filter(
        (t) => !selectedIds.has(t.trust_id)
      );
      setSelectedTrust(remaining[0] || null);
    }
    await loadTrusts();
    clearSelection();
    setDeleting(false);
  };

  const clearFilters = () => {
    setFilterType(null);
    setFilterStatus(null);
    setSearchQuery('');
  };

  const hasActiveFilters = filterType || filterStatus || debouncedSearch.trim();

  // ─── Derived counts ────────────────────────────────────────────────────────

  const typeCounts = useMemo(() => {
    const counts = {};
    for (const t of trusts) {
      const key = t.trust_type || 'unknown';
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [trusts]);

  const statusCounts = useMemo(() => {
    const counts = { healthy: 0, attention: 0, critical: 0 };
    for (const t of trusts) {
      const tier = getScoreTier(t.governance_score ?? 0);
      counts[tier.key]++;
    }
    return counts;
  }, [trusts]);

  // ─── Loading state ─────────────────────────────────────────────────────────

  if (trustsLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-navy mr-2" />
        <span className="text-sm text-muted-foreground">Loading trusts…</span>
      </div>
    );
  }

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div className={embedded ? '' : 'page-container'} data-testid="trust-manager">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-6">
        <div>
          <h2 className={`font-serif text-2xl text-navy ${embedded ? '' : 'page-title'}`}>
            Trust Manager
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            {trusts.length} {trusts.length === 1 ? 'trust' : 'trusts'} ·
            {' '}{filteredTrusts.length} shown
            {selectedIds.size > 0 && ` · ${selectedIds.size} selected`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/settings')}
            className="text-xs"
          >
            <Settings2 className="w-3.5 h-3.5 mr-1.5" />
            Settings
          </Button>
          {!isReadOnly && (
            <Button
              size="sm"
              className="btn-primary"
              onClick={() => navigate('/onboarding')}
            >
              <Plus className="w-3.5 h-3.5 mr-1.5" />
              New Trust
            </Button>
          )}
        </div>
      </div>

      {/* Toolbar */}
      <div className="card-trust mb-6">
        {/* Search + Sort row */}
        <div className="flex flex-col md:flex-row gap-3 mb-3">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-navy/30" />
            <Input
              type="text"
              placeholder="Search by name, type, state, or EIN…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 input-trust"
              data-testid="trust-search-input"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-navy/30 hover:text-navy"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Sort dropdown */}
          <div className="relative">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="appearance-none pl-9 pr-8 py-2 border border-navy/20 bg-white text-sm text-navy font-mono cursor-pointer hover:border-navy/40 transition-colors w-full md:w-44"
              data-testid="trust-sort-select"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <ArrowUpDown className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-navy/40 pointer-events-none" />
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-navy/40 pointer-events-none" />
          </div>

          {/* Group dropdown */}
          <div className="relative">
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value)}
              className="appearance-none pl-9 pr-8 py-2 border border-navy/20 bg-white text-sm text-navy font-mono cursor-pointer hover:border-navy/40 transition-colors w-full md:w-40"
              data-testid="trust-group-select"
            >
              {GROUP_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <Layers className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-navy/40 pointer-events-none" />
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-navy/40 pointer-events-none" />
          </div>
        </div>

        {/* Filter chips row */}
        <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-navy/10">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 border text-xs font-mono uppercase tracking-wider transition-colors ${
              showFilters || hasActiveFilters
                ? 'border-gold bg-gold/10 text-navy'
                : 'border-navy/20 text-navy hover:border-navy/40'
            }`}
          >
            <Filter className="w-3.5 h-3.5" />
            Filters
            {hasActiveFilters && (
              <span className="bg-gold text-navy px-1.5 py-0.5 text-[9px] font-bold">
                {[filterType, filterStatus, debouncedSearch].filter(Boolean).length}
              </span>
            )}
          </button>

          {/* Active filter chips */}
          {filterType && (
            <FilterChip
              label={`Type: ${getTrustTypeLabel(filterType)}`}
              active
              onClear={() => setFilterType(null)}
            />
          )}
          {filterStatus && (
            <FilterChip
              label={`Score: ${STATUS_TIERS.find((s) => s.key === filterStatus)?.label || filterStatus}`}
              active
              onClear={() => setFilterStatus(null)}
            />
          )}
          {debouncedSearch && (
            <FilterChip
              label={`Search: "${debouncedSearch}"`}
              active
              onClear={() => setSearchQuery('')}
            />
          )}

          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="text-xs text-navy/50 hover:text-error font-mono ml-1"
            >
              Clear all
            </button>
          )}

          {/* Select all */}
          {filteredTrusts.length > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={toggleSelectAll}
                className="inline-flex items-center gap-1.5 text-xs font-mono uppercase tracking-wider text-navy hover:text-navy/70 transition-colors"
                data-testid="trust-select-all"
              >
                {selectedIds.size === filteredTrusts.length && selectedIds.size > 0 ? (
                  <CheckSquare className="w-3.5 h-3.5" />
                ) : (
                  <Square className="w-3.5 h-3.5" />
                )}
                {selectedIds.size === filteredTrusts.length && selectedIds.size > 0
                  ? 'Deselect All'
                  : 'Select All'}
              </button>
            </div>
          )}
        </div>

        {/* Expanded filter panel */}
        {showFilters && (
          <div className="mt-4 pt-4 border-t border-navy/10 grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Type filters */}
            <div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-navy/50 mb-2">
                Trust Type
              </p>
              <div className="flex flex-wrap gap-2">
                {TRUST_TYPES.map((type) => (
                  <FilterChip
                    key={type.value}
                    label={`${type.label} (${typeCounts[type.value] || 0})`}
                    active={filterType === type.value}
                    onClick={() =>
                      setFilterType(filterType === type.value ? null : type.value)
                    }
                  />
                ))}
              </div>
            </div>

            {/* Status filters */}
            <div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-navy/50 mb-2">
                Health Score
              </p>
              <div className="flex flex-wrap gap-2">
                {STATUS_TIERS.map((tier) => (
                  <FilterChip
                    key={tier.key}
                    label={`${tier.label} (${statusCounts[tier.key] || 0})`}
                    active={filterStatus === tier.key}
                    onClick={() =>
                      setFilterStatus(filterStatus === tier.key ? null : tier.key)
                    }
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div
          className="sticky top-0 z-10 mb-6 bg-navy text-white p-3 flex items-center justify-between shadow-lg"
          data-testid="trust-bulk-action-bar"
        >
          <div className="flex items-center gap-3">
            <CheckSquare className="w-5 h-5 text-gold" />
            <span className="font-mono text-sm">
              {selectedIds.size} selected
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleBulkExport}
              disabled={exporting}
              className="text-xs border-white/30 text-white hover:bg-white/10"
              data-testid="trust-bulk-export"
            >
              {exporting ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5 mr-1.5" />
              )}
              Export CSV
            </Button>
            {!isReadOnly && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleBulkArchive}
                  disabled={archiving}
                  className="text-xs border-white/30 text-white hover:bg-white/10"
                  data-testid="trust-bulk-archive"
                >
                  {archiving ? (
                    <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  ) : (
                    <Archive className="w-3.5 h-3.5 mr-1.5" />
                  )}
                  Archive
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleBulkDelete}
                  className="text-xs border-error/50 text-error hover:bg-error/10"
                  data-testid="trust-bulk-delete"
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                  Delete
                </Button>
              </>
            )}
            <button
              onClick={clearSelection}
              className="text-white/60 hover:text-white ml-2"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Trust list / groups */}
      {filteredTrusts.length === 0 ? (
        <div className="card-trust text-center py-16">
          {hasActiveFilters ? (
            <>
              <Search className="w-10 h-10 text-navy/20 mx-auto mb-4" />
              <h3 className="font-serif text-lg text-navy mb-2">No trusts match your filters</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Try adjusting your search or clearing filters.
              </p>
              <Button onClick={clearFilters} variant="outline" className="btn-secondary">
                Clear Filters
              </Button>
            </>
          ) : (
            <>
              <Landmark className="w-10 h-10 text-navy/20 mx-auto mb-4" />
              <h3 className="font-serif text-lg text-navy mb-2">No trusts yet</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Create your first trust to get started.
              </p>
              {!isReadOnly && (
                <Button
                  onClick={() => navigate('/onboarding')}
                  className="btn-primary"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Create Trust
                </Button>
              )}
            </>
          )}
        </div>
      ) : (
        <div className="space-y-6">
          {groupedTrusts.map((group) => (
            <div key={group.key} data-testid={`trust-group-${group.key}`}>
              {groupBy !== 'none' && (
                <GroupHeader
                  label={group.label}
                  count={group.trusts.length}
                  icon={group.icon}
                  colorClass={group.colorClass}
                />
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {group.trusts.map((trust) => (
                  <TrustCard
                    key={trust.trust_id}
                    trust={trust}
                    isSelected={selectedIds.has(trust.trust_id)}
                    onToggleSelect={toggleSelect}
                    onSelect={handleSelectTrust}
                    onDelete={handleDeleteTrust}
                    isReadOnly={isReadOnly}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TrustManager;