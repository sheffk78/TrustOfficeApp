import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  BookOpen,
  FileText,
  Eye,
  Calendar,
  ChevronRight,
  Tag,
} from 'lucide-react';

const CATEGORY_COLORS = {
  trust_basics: 'bg-blue-100 text-blue-700 border-blue-200',
  compliance: 'bg-green-100 text-green-700 border-green-200',
  tax: 'bg-purple-100 text-purple-700 border-purple-200',
  distributions: 'bg-orange-100 text-orange-700 border-orange-200',
  compensation: 'bg-pink-100 text-pink-700 border-pink-200',
  governance: 'bg-indigo-100 text-indigo-700 border-indigo-200',
  structures: 'bg-cyan-100 text-cyan-700 border-cyan-200',
  onboarding: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  glossary: 'bg-gray-100 text-gray-700 border-gray-200',
  best_practices: 'bg-emerald-100 text-emerald-700 border-emerald-200',
};

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

/**
 * KnowledgeCard — compact card for a knowledge base article in the listing view.
 *
 * Props:
 *   article: { id, title, slug, category, summary, tags, views, created_at }
 */
export default function KnowledgeCard({ article }) {
  if (!article) return null;

  const catColor = CATEGORY_COLORS[article.category] || 'bg-gray-100 text-gray-700 border-gray-200';
  const catLabel = CATEGORY_LABELS[article.category] || article.category;

  return (
    <Card className="card-trust border border-border hover:shadow-md transition-shadow">
      <CardContent className="p-5">
        {/* Title + Category badge */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className="w-9 h-9 rounded-lg bg-navy/5 flex items-center justify-center shrink-0">
              <FileText className="w-4 h-4 text-navy" />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-navy text-sm truncate">
                {article.title || 'Untitled Article'}
              </h3>
            </div>
          </div>
          <Badge className={`flex-shrink-0 ${catColor}`}>
            {catLabel}
          </Badge>
        </div>

        {/* Summary */}
        {article.summary && (
          <p className="text-sm text-muted-foreground line-clamp-2 mb-4">
            {article.summary}
          </p>
        )}

        {/* Meta bar */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mb-4">
          <span className="flex items-center gap-1">
            <Eye className="w-3 h-3" />
            {article.views ?? 0}
          </span>
          <span className="flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            {article.created_at
              ? new Date(article.created_at).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })
              : 'Unknown date'}
          </span>
          {article.tags && article.tags.length > 0 && (
            <span className="flex items-center gap-1">
              <Tag className="w-3 h-3" />
              <span className="truncate max-w-[120px]">{article.tags[0]}</span>
              {article.tags.length > 1 && (
                <span className="text-muted-foreground/60">
                  +{article.tags.length - 1}
                </span>
              )}
            </span>
          )}
        </div>

        {/* Read more link */}
        <Link
          to={`/knowledge/${article.id}`}
          className="block"
        >
          <button className="w-full flex items-center justify-center gap-1.5 text-sm font-mono text-navy hover:text-navy/70 border border-navy/10 rounded py-1.5 hover:bg-navy/5 transition-colors">
            Read Article
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </Link>
      </CardContent>
    </Card>
  );
}