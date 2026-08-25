import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import PageHelpButton from '@/components/PageHelpButton';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  Plus,
  Edit,
  Trash2,
  Eye,
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  FileText,
  Save,
  X,
  AlertCircle,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Textarea } from '@/components/ui/textarea';

const PAGE_SIZE = 10;

const CATEGORIES = [
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

const CATEGORY_COLORS = {
  trust_basics: 'bg-navy/10 text-navy',
  compliance: 'bg-gold/10 text-gold',
  tax: 'bg-navy/10 text-navy',
  distributions: 'bg-gold/10 text-gold',
  compensation: 'bg-navy/10 text-navy',
  governance: 'bg-gold/10 text-gold',
  structures: 'bg-navy/10 text-navy',
  onboarding: 'bg-gold/10 text-gold',
  glossary: 'bg-navy/10 text-navy',
  best_practices: 'bg-gold/10 text-gold',
};

function ArticleForm({ article, onSave, onCancel, saving }) {
  const [title, setTitle] = useState(article?.title || '');
  const [category, setCategory] = useState(article?.category || 'trust_basics');
  const [summary, setSummary] = useState(article?.summary || '');
  const [content, setContent] = useState(article?.content || '');
  const [tags, setTags] = useState(article?.tags?.join(', ') || '');
  const [published, setPublished] = useState(article?.published ?? true);
  const [errors, setErrors] = useState({});

  const validate = () => {
    const newErrors = {};
    if (!title.trim()) newErrors.title = 'Title is required';
    if (!content.trim()) newErrors.content = 'Content is required';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = () => {
    if (!validate()) return;
    const tagList = tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
    onSave({ title, category, summary, content, tags: tagList, published });
  };

  return (
    <div className="space-y-5">
      {/* Title */}
      <div>
        <label className="block text-sm font-medium text-navy mb-1">
          Title <span className="text-error">*</span>
        </label>
        <Input
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            if (errors.title) setErrors((p) => ({ ...p, title: null }));
          }}
          placeholder="Article title"
          maxLength={200}
          className={errors.title ? 'border-error' : ''}
        />
        {errors.title && (
          <p className="text-xs text-error mt-1">{errors.title}</p>
        )}
      </div>

      {/* Category */}
      <div>
        <label className="block text-sm font-medium text-navy mb-1">
          Category <span className="text-error">*</span>
        </label>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger>
            <SelectValue placeholder="Select category" />
          </SelectTrigger>
          <SelectContent>
            {CATEGORIES.map((cat) => (
              <SelectItem key={cat} value={cat}>
                {CATEGORY_LABELS[cat] || cat}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Tags */}
      <div>
        <label className="block text-sm font-medium text-navy mb-1">
          Tags (comma-separated)
        </label>
        <Input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="e.g. hems, distributions, tax"
        />
      </div>

      {/* Summary */}
      <div>
        <label className="block text-sm font-medium text-navy mb-1">Summary</label>
        <Textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="Brief summary shown in listings..."
          rows={3}
          maxLength={500}
        />
      </div>

      {/* Content */}
      <div>
        <label className="block text-sm font-medium text-navy mb-1">
          Content (Markdown) <span className="text-error">*</span>
        </label>
        <Textarea
          value={content}
          onChange={(e) => {
            setContent(e.target.value);
            if (errors.content) setErrors((p) => ({ ...p, content: null }));
          }}
          placeholder="# Heading&#10;&#10;Write your article in **Markdown** format..."
          rows={12}
          className={`font-mono text-sm ${errors.content ? 'border-error' : ''}`}
        />
        {errors.content && (
          <p className="text-xs text-error mt-1">{errors.content}</p>
        )}
        <p className="text-xs text-muted-foreground mt-1">
          Supports Markdown including tables, lists, and headings.
        </p>
      </div>

      {/* Published toggle */}
      <div className="flex items-center gap-3">
        <input
          type="checkbox"
          id="published"
          checked={published}
          onChange={(e) => setPublished(e.target.checked)}
          className="w-4 h-4 rounded border-navy/30 text-navy focus:ring-navy/20"
        />
        <label htmlFor="published" className="text-sm text-navy">
          Published
        </label>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSubmit} disabled={saving} className="min-w-[120px]">
          {saving ? (
            'Saving...'
          ) : (
            <>
              <Save className="w-3.5 h-3.5 mr-1.5" />
              {article ? 'Update Article' : 'Create Article'}
            </>
          )}
        </Button>
        <Button
          variant="outline"
          onClick={onCancel}
          disabled={saving}
          className="min-w-[100px]"
        >
          <X className="w-3.5 h-3.5 mr-1.5" />
          Cancel
        </Button>
      </div>
    </div>
  );
}

export default function KnowledgeAdmin() {
  const navigate = useNavigate();

  const [articles, setArticles] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [selectedArticle, setSelectedArticle] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const fetchArticles = useCallback(
    async (page = 1) => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        params.set('page', page);
        params.set('limit', PAGE_SIZE);
        params.set('published_only', 'false'); // Admin sees all
        if (searchQuery) params.set('search', searchQuery);
        if (categoryFilter && categoryFilter !== 'all') {
          params.set('category', categoryFilter);
        }

        const res = await fetchWithAuth(`/knowledge?${params.toString()}`);
        if (res.ok) {
          const data = await res.json();
          setArticles(data.articles || []);
          setPagination(data.pagination || {});
        } else {
          toast.error('Failed to load articles');
        }
      } catch (error) {
        showError(toast, error, {
          operation: 'load_articles_admin',
          page: 'KnowledgeAdmin',
        });
      } finally {
        setLoading(false);
      }
    },
    [searchQuery, categoryFilter]
  );

  useEffect(() => {
    fetchArticles(1);
  }, [fetchArticles]);

  const handleCreate = async (data) => {
    setSaving(true);
    try {
      const res = await fetchWithAuth('/knowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (res.ok) {
        toast.success('Article created successfully');
        setShowCreateModal(false);
        fetchArticles(1);
      } else {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        toast.error(err.detail || 'Failed to create article');
      }
    } catch (error) {
      showError(toast, error, {
        operation: 'create_article',
        page: 'KnowledgeAdmin',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async (data) => {
    if (!selectedArticle) return;
    setSaving(true);
    try {
      const res = await fetchWithAuth(`/knowledge/${selectedArticle.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (res.ok) {
        toast.success('Article updated successfully');
        setShowEditModal(false);
        setSelectedArticle(null);
        fetchArticles(pagination?.page || 1);
      } else {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        toast.error(err.detail || 'Failed to update article');
      }
    } catch (error) {
      showError(toast, error, {
        operation: 'update_article',
        page: 'KnowledgeAdmin',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedArticle) return;
    setDeleteLoading(true);
    try {
      const res = await fetchWithAuth(`/knowledge/${selectedArticle.id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        toast.success('Article deleted successfully');
        setShowDeleteDialog(false);
        setSelectedArticle(null);
        fetchArticles(pagination?.page || 1);
      } else {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        toast.error(err.detail || 'Failed to delete article');
      }
    } catch (error) {
      showError(toast, error, {
        operation: 'delete_article',
        page: 'KnowledgeAdmin',
      });
    } finally {
      setDeleteLoading(false);
    }
  };

  const openEdit = (article) => {
    setSelectedArticle(article);
    setShowEditModal(true);
  };

  const openDelete = (article) => {
    setSelectedArticle(article);
    setShowDeleteDialog(true);
  };

  const handlePageChange = (newPage) => {
    fetchArticles(newPage);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-subtle-bg min-h-screen pb-20 md:pb-0 lg:ml-64 pt-16 lg:pt-0">
        <div className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-8">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Knowledge Base Admin</h1>
              <p className="page-subtitle">Create, edit, and manage knowledge articles</p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Create, edit, and manage trust education articles' },
                  { text: 'Organize articles by category for the Knowledge Base' },
                  { text: 'Articles appear in the Knowledge Base for all users' },
                ]}
                taPrompt="Walk me through the Knowledge Base Admin and how to create an article"
              />
              <Button onClick={() => setShowCreateModal(true)}>
                <Plus className="w-4 h-4 mr-2" />
                New Article
              </Button>
            </div>
          </div>

          {/* Toolbar */}
          <div className="flex flex-wrap items-center gap-3 mb-6">
            <div className="relative flex-1 min-w-[200px] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search articles..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                }}
                className="pl-9 w-full"
                debounce={300}
              />
            </div>

            <Select value={categoryFilter} onValueChange={setCategoryFilter}>
              <SelectTrigger className="w-[180px]">
                <Filter className="w-3.5 h-3.5 mr-1.5" />
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                {CATEGORIES.map((cat) => (
                  <SelectItem key={cat} value={cat}>
                    {CATEGORY_LABELS[cat] || cat}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Loading */}
          {loading && (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="card-trust p-6 animate-pulse space-y-3"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 bg-navy/10 rounded animate-pulse" />
                    <div className="h-4 bg-navy/10 rounded w-1/3 animate-pulse" />
                    <div className="h-4 bg-navy/10 rounded w-16 animate-pulse ml-auto" />
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
              <FileText className="w-16 h-16 text-navy/20 mx-auto mb-4" />
              <h3 className="font-serif text-lg text-navy mb-2">
                No articles found
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                {searchQuery || categoryFilter !== 'all'
                  ? 'Try adjusting your filters.'
                  : 'No articles have been created yet.'}
              </p>
              <Button onClick={() => setShowCreateModal(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Create First Article
              </Button>
            </div>
          )}

          {/* Article list */}
          {!loading && articles.length > 0 && (
            <div className="space-y-3">
              {articles.map((article) => (
                <div
                  key={article.id}
                  className="card-trust border border-border hover:shadow-md transition-shadow p-5 md:p-6 flex flex-col md:flex-row md:items-center md:gap-4"
                >
                  {/* Left: title + meta */}
                  <div className="flex-1 min-w-0 mb-3 md:mb-0">
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <h3 className="font-semibold text-navy text-sm truncate flex-1">
                        {article.title}
                      </h3>
                      <Badge
                        className={`flex-shrink-0 ${
                          CATEGORY_COLORS[article.category] ||
                          'bg-navy/10 text-navy'
                        }`}
                      >
                        {CATEGORY_LABELS[article.category] || article.category}
                      </Badge>
                      {!article.published && (
                        <Badge variant="secondary" className="flex-shrink-0">
                          Draft
                        </Badge>
                      )}
                    </div>
                    {article.summary && (
                      <p className="text-xs text-muted-foreground line-clamp-2 mb-2">
                        {article.summary}
                      </p>
                    )}
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Eye className="w-3 h-3" />
                        {article.views ?? 0}
                      </span>
                      <span>
                        {article.author || 'Unknown author'}
                      </span>
                      <span>
                        {article.updated_at
                          ? new Date(article.updated_at).toLocaleDateString()
                          : new Date(article.created_at).toLocaleDateString()}
                      </span>
                      {article.tags && article.tags.length > 0 && (
                        <span className="text-muted-foreground/60">
                          {article.tags.slice(0, 2).join(', ')}
                          {article.tags.length > 2 &&
                            ` +${article.tags.length - 2}`}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Right: actions */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        navigate(`/knowledge/${article.id}`)
                      }
                      title="View article"
                    >
                      <Eye className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openEdit(article)}
                      title="Edit article"
                    >
                      <Edit className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openDelete(article)}
                      title="Delete article"
                      className="text-error hover:text-error/80"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Pagination */}
          {pagination && pagination.total_pages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
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
        </div>
      </main>

      {/* Create/Edit Modal */}
      <Dialog
        open={showCreateModal || showEditModal}
        onOpenChange={(open) => {
          if (!open) {
            setShowCreateModal(false);
            setShowEditModal(false);
            setSelectedArticle(null);
          }
        }}
      >
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {showEditModal ? 'Edit Article' : 'Create New Article'}
            </DialogTitle>
            <DialogDescription>
              {showEditModal
                ? 'Update the article details below.'
                : 'Create a new knowledge base article. Written in Markdown.'}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <ArticleForm
              article={showEditModal ? selectedArticle : null}
              onSave={showEditModal ? handleUpdate : handleCreate}
              onCancel={() => {
                setShowCreateModal(false);
                setShowEditModal(false);
                setSelectedArticle(null);
              }}
              saving={saving}
            />
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog
        open={showDeleteDialog}
        onOpenChange={(open) => {
          if (!open) {
            setShowDeleteDialog(false);
            setSelectedArticle(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Article</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete{' '}
              <strong>"{selectedArticle?.title}"</strong>? This action cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleteLoading}
              className="bg-error text-error-foreground hover:bg-error/90"
            >
              {deleteLoading ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}