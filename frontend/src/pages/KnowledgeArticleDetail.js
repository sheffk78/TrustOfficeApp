import { useState, useEffect } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  BookOpen,
  Eye,
  Calendar,
  Tag,
  ArrowLeft,
  ChevronRight,
  FileText,
  Share2,
  Printer,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

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
  trust_basics: 'bg-blue-100 text-blue-700',
  compliance: 'bg-green-100 text-green-700',
  tax: 'bg-purple-100 text-purple-700',
  distributions: 'bg-orange-100 text-orange-700',
  compensation: 'bg-pink-100 text-pink-700',
  governance: 'bg-indigo-100 text-indigo-700',
  structures: 'bg-cyan-100 text-cyan-700',
  onboarding: 'bg-yellow-100 text-yellow-700',
  glossary: 'bg-gray-100 text-gray-700',
  best_practices: 'bg-emerald-100 text-emerald-700',
};

export default function KnowledgeArticleDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Related articles state
  const [relatedArticles, setRelatedArticles] = useState([]);

  useEffect(() => {
    fetchArticle();
  }, [id]);

  const fetchArticle = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth(`/knowledge/${id}`);
      if (res.ok) {
        const data = await res.json();
        setArticle(data);

        // Fetch related articles (same category, excluding current)
        try {
          const relRes = await fetchWithAuth(
            `/knowledge?category=${data.category}&published_only=true&limit=5`
          );
          if (relRes.ok) {
            const relData = await relRes.json();
            setRelatedArticles(
              (relData.articles || []).filter((a) => a.id !== data.id)
            );
          }
        } catch {
          // Related articles are non-critical
          setRelatedArticles([]);
        }
      } else if (res.status === 404) {
        setError('Article not found.');
      } else {
        const errData = await res.json().catch(() => ({ detail: 'Unknown error' }));
        setError(errData.detail || 'Failed to load article.');
      }
    } catch (err) {
      showError(toast, err, {
        operation: 'load_article',
        page: 'KnowledgeArticleDetail',
      });
      setError('Failed to load article. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleShare = async () => {
    if (navigator.share && navigator.canShare) {
      try {
        await navigator.share({
          title: article.title,
          text: article.summary || article.title,
          url: window.location.href,
        });
        return;
      } catch {
        // Fall through to copy
      }
    }
    // Fallback: copy to clipboard
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success('Link copied to clipboard!');
    } catch {
      toast.error('Failed to copy link.');
    }
  };

  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center min-h-screen lg:ml-64 pt-16 lg:pt-0">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mx-auto mb-4"></div>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Loading article...
            </p>
          </div>
        </main>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center min-h-screen lg:ml-64 pt-16 lg:pt-0">
          <div className="text-center max-w-md">
            <FileText className="w-16 h-16 text-navy/20 mx-auto mb-4" />
            <h2 className="font-serif text-xl text-navy mb-2">
              {error === 'Article not found.' ? 'Article Not Found' : 'Error'}
            </h2>
            <p className="text-sm text-muted-foreground mb-4">{error}</p>
            <Button variant="outline" onClick={() => navigate('/knowledge')}>
              <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
              Back to Knowledge Base
            </Button>
          </div>
        </main>
      </div>
    );
  }

  const catColor = CATEGORY_COLORS[article.category] || 'bg-gray-100 text-gray-700';
  const catLabel = CATEGORY_LABELS[article.category] || article.category;

  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-subtle-bg min-h-screen pb-20 md:pb-0 lg:ml-64 pt-16 lg:pt-0 print:bg-white">
        <div className="max-w-4xl mx-auto px-4 md:px-6 py-6 md:py-8">
          {/* Back button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/knowledge')}
            className="mb-6"
          >
            <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
            Back to Knowledge Base
          </Button>

          {/* Article header */}
          <article className="card-trust border border-border overflow-hidden">
            {/* Header section */}
            <div className="p-6 md:p-8 border-b border-border print:pb-4">
              {/* Category badge */}
              <Badge className={`${catColor} mb-3`}>{catLabel}</Badge>

              <h1 className="font-serif text-2xl md:text-3xl text-navy mb-3 leading-tight">
                {article.title}
              </h1>

              {/* Meta info */}
              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground mb-4">
                <span className="flex items-center gap-1.5">
                  <Eye className="w-4 h-4" />
                  {article.views ?? 0} views
                </span>
                <span className="flex items-center gap-1.5">
                  <Calendar className="w-4 h-4" />
                  {article.created_at
                    ? new Date(article.created_at).toLocaleDateString('en-US', {
                        month: 'long',
                        day: 'numeric',
                        year: 'numeric',
                      })
                    : 'Unknown date'}
                </span>
                {article.author && (
                  <span className="flex items-center gap-1.5">
                    <FileText className="w-4 h-4" />
                    {article.author}
                  </span>
                )}
              </div>

              {/* Tags */}
              {article.tags && article.tags.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <Tag className="w-3.5 h-3.5 text-muted-foreground" />
                  {article.tags.map((tag, idx) => (
                    <Badge
                      key={idx}
                      variant="outline"
                      className="text-xs mr-1"
                    >
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            {/* Article content */}
            <div className="p-6 md:p-8 prose prose-navy max-w-none print:p-0 print:prose-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {article.content}
              </ReactMarkdown>
            </div>

            {/* Action bar */}
            <div className="px-6 md:px-8 py-4 border-t border-border flex items-center justify-between print:hidden">
              <span className="text-xs text-muted-foreground font-mono">
                Last updated:{' '}
                {article.updated_at
                  ? new Date(article.updated_at).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })
                  : 'N/A'}
              </span>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" onClick={handleShare}>
                  <Share2 className="w-3.5 h-3.5 mr-1.5" />
                  Share
                </Button>
                <Button variant="ghost" size="sm" onClick={handlePrint}>
                  <Printer className="w-3.5 h-3.5 mr-1.5" />
                  Print
                </Button>
              </div>
            </div>
          </article>

          {/* Related articles */}
          {relatedArticles.length > 0 && (
            <section className="mt-8">
              <h2 className="font-serif text-lg text-navy mb-4 flex items-center gap-2">
                <BookOpen className="w-4 h-4" />
                Related Articles
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {relatedArticles.map((rel) => (
                  <Link
                    key={rel.id}
                    to={`/knowledge/${rel.id}`}
                    className="flex items-start gap-3 p-3 border border-border rounded hover:bg-navy/5 transition-colors group"
                  >
                    <FileText className="w-4 h-4 text-navy/50 mt-0.5 group-hover:text-navy flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-navy truncate group-hover:underline">
                        {rel.title}
                      </p>
                      {rel.summary && (
                        <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                          {rel.summary}
                        </p>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}