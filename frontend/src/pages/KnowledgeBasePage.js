import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import KnowledgeCard from '@/components/KnowledgeCard';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  Grid,
  List,
  BookOpen,
  ArrowUpDown,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const PAGE_SIZE = 12;

const CATEGORY_LABELS = {
  trust_basics: 'Trust Basics',
  compliance: 'Compliance',
  tax: 'Tax',
  distributions: 'Distributions',
  compensation: 'Compensation',
  governance: 'Governance',
  structures: 'Structures',
  onboarding: 'Onboarding',
  glossary: 'Glossary',
  best_practices: 'Best Practices',
};

const CATEGORY_ORDER = [
  'trust_basics',
  'compliance',
  'tax',
  'distributions',
  'compensation',
  'governance',
  'structures',
  'onboarding',
  'glossary',
  'best_practices',
];

export default function KnowledgeBasePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [articles, setArticles] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState(null);

  // Filters from URL query params
  const activeCategory = searchParams.get('category') || '';
  const searchQuery = searchParams.get('q') || '';

  // UI state
  const [viewMode, setViewMode] = useState('grid'); // 'grid' or 'list'
  const [sortOrder, setSortOrder] = useState('newest');

  const fetchCategories = useCallback(async () => {
    try {
      const res = await fetchWithAuth('/knowledge/categories');
      if (res.ok) {
        const data = await res.json();
        setCategories(data.categories || []);
      }
    } catch (error) {
      showError(toast, error, { operation: 'load_categories', page: 'KnowledgeBase' });
    }
  }, []);

  const fetchArticles = useCallback(
    async (page = 1) => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        params.set('page', page);
        params.set('limit', PAGE_SIZE);
        if (activeCategory) params.set('category', activeCategory);
        if (searchQuery) params.set('search', searchQuery);
        params.set('published_only', 'true');

        const res = await fetchWithAuth(`/knowledge?${params.toString()}`);
        if (res.ok) {
          const data = await res.json();
          setArticles(data.articles || []);
          setPagination(data.pagination || {});
        } else {
          const errData = await res.json().catch(() => ({}));
          toast.error(errData.detail || 'Failed to load articles');
        }
      } catch (error) {
        showError(toast, error, { operation: 'load_articles', page: 'KnowledgeBase' });
      } finally {
        setLoading(false);
      }
    },
    [activeCategory, searchQuery]
  );

  useEffect(() => {
    fetchCategories();
  }, [fetchCategories]);

  useEffect(() => {
    fetchArticles(1);
  }, [fetchArticles]);

  const handleSearch = (e) => {
    const value = e.target.value;
    setSearchParams((prev) => {
      if (value) {
        prev.set('q', value);
      } else {
        prev.delete('q');
      }
      prev.delete('page');
      return prev;
    });
  };

  const handleCategoryFilter = (value) => {
    setSearchParams((prev) => {
      if (value && value !== 'all') {
        prev.set('category', value);
      } else {
        prev.delete('category');
      }
      prev.delete('page');
      return prev;
    });
  };

  const handlePageChange = (newPage) => {
    setSearchParams((prev) => {
      prev.set('page', newPage);
      return prev;
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const clearFilters = () => {
    setSearchParams({});
  };

  const hasActiveFilters = activeCategory || searchQuery;

  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-subtle-bg min-h-screen pb-20 md:pb-0 lg:ml-64 pt-16 lg:pt-0">
        <div className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-8">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-navy/10 flex items-center justify-center rounded-lg">
                <BookOpen className="w-5 h-5 text-navy" />
              </div>
              <div>
                <h1 className="font-serif text-2xl md:text-3xl text-navy">Knowledge Base</h1>
                <p className="text-sm text-muted-foreground mt-0.5">
                  Centralized resources for trust administrators
                </p>
              </div>
            </div>
          </div>

          {/* Toolbar */}
          <div className="flex flex-wrap items-center gap-3 mb-6">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search articles..."
                value={searchQuery}
                onChange={handleSearch}
                className="pl-9 w-full"
              />
            </div>

            {/* Category filter */}
            <Select value={activeCategory || 'all'} onValueChange={handleCategoryFilter}>
              <SelectTrigger className="w-[180px]">
                <Filter className="w-3.5 h-3.5 mr-1.5" />
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                {CATEGORY_ORDER.map((cat) => (
                  <SelectItem key={cat} value={cat}>
                    {CATEGORY_LABELS[cat] || cat}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* View toggle */}
            <div className="flex items-center border border-border rounded overflow-hidden">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-2 ${viewMode === 'grid' ? 'bg-navy text-white' : 'bg-white text-navy'} transition-colors`}
                title="Grid view"
              >
                <Grid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-2 ${viewMode === 'list' ? 'bg-navy text-white' : 'bg-white text-navy'} transition-colors`}
                title="List view"
              >
                <List className="w-4 h-4" />
              </button>
            </div>

            {/* Sort */}
            <Select value={sortOrder} onValueChange={setSortOrder}>
              <SelectTrigger className="w-[140px]">
                <ArrowUpDown className="w-3.5 h-3.5 mr-1.5" />
                <SelectValue placeholder="Sort" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="newest">Newest First</SelectItem>
                <SelectItem value="oldest">Oldest First</SelectItem>
                <SelectItem value="most-viewed">Most Viewed</SelectItem>
                <SelectItem value="a-z">Title A–Z</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Active filters pill */}
          {hasActiveFilters && (
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xs text-muted-foreground font-mono">Filters:</span>
              {(activeCategory || searchQuery) && (
                <Badge variant="outline" className="text-xs">
                  {activeCategory
                    ? CATEGORY_LABELS[activeCategory] || activeCategory
                    : ''}
                  {searchQuery ? (activeCategory ? ' + ' : '') + `"${searchQuery}"` : ''}
                  <button
                    onClick={clearFilters}
                    className="ml-1 text-muted-foreground hover:text-navy"
                  >
                    ✕
                  </button>
                </Badge>
              )}
            </div>
          )}

          {/* Loading state */}
          {loading && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="card-trust p-6 animate-pulse space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 bg-navy/10 rounded animate-pulse" />
                    <div className="h-4 bg-navy/10 rounded w-1/2 animate-pulse" />
                  </div>
                  <div className="h-3 bg-navy/5 rounded w-full animate-pulse" />
                  <div className="h-3 bg-navy/5 rounded w-2/3 animate-pulse" />
                </div>
              ))}
            </div>
          )}

          {/* Empty state */}
          {!loading && articles.length === 0 && (
            <div className="text-center py-16">
              <BookOpen className="w-16 h-16 text-navy/20 mx-auto mb-4" />
              <h3 className="font-serif text-lg text-navy mb-2">
                No articles found
              </h3>
              <p className="text-sm text-muted-foreground max-w-sm mx-auto">
                {hasActiveFilters
                  ? 'Try adjusting your filters or search terms.'
                  : 'No knowledge base articles have been published yet.'}
              </p>
              {hasActiveFilters && (
                <Button onClick={clearFilters} variant="outline" className="mt-4">
                  Clear Filters
                </Button>
              )}
            </div>
          )}

          {/* Article grid */}
          {!loading && articles.length > 0 && (
            <>
              <div
                className={
                  viewMode === 'grid'
                    ? 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5'
                    : 'space-y-4'
                }
              >
                {articles
                  .sort((a, b) => {
                    switch (sortOrder) {
                      case 'oldest':
                        return new Date(a.created_at) - new Date(b.created_at);
                      case 'most-viewed':
                        return (b.views || 0) - (a.views || 0);
                      case 'a-z':
                        return a.title.localeCompare(b.title);
                      case 'newest':
                      default:
                        return new Date(b.created_at) - new Date(a.created_at);
                    }
                  })
                  .map((article) => (
                    <KnowledgeCard key={article.id} article={article} />
                  ))}
              </div>

              {/* Pagination */}
              {pagination && pagination.total_pages > 1 && (
                <div className="flex items-center justify-center gap-2 mt-8">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!pagination.has_prev}
                    onClick={() => handlePageChange(pagination.page - 1)}
                  >
                    ← Prev
                  </Button>
                  <span className="text-sm text-muted-foreground font-mono">
                    Page {pagination.page} of {pagination.total_pages}
                    <span className="hidden md:inline">
                      {' '}
                      ({pagination.total} total)
                    </span>
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!pagination.has_next}
                    onClick={() => handlePageChange(pagination.page + 1)}
                  >
                    Next →
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}