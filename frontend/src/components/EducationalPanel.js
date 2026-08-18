import { useState, useEffect, useCallback } from 'react';
import { fetchWithAuth } from '@/utils/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import {
  BookOpen,
  GraduationCap,
  FileText,
  Video,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Lightbulb,
} from 'lucide-react';

const TYPE_ICONS = {
  article: FileText,
  video: Video,
  course: GraduationCap,
  guide: BookOpen,
  default: Lightbulb,
};

function ResourceIcon({ type }) {
  const Icon = TYPE_ICONS[type] || TYPE_ICONS.default;
  return <Icon className="w-4 h-4 text-navy/70 flex-shrink-0" />;
}

export default function EducationalPanel({ trustId, healthScore }) {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState('recommended');
  const [resources, setResources] = useState([]);
  const [recommended, setRecommended] = useState([]);
  const [curriculum, setCurriculum] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadAll = useCallback(async () => {
    if (!trustId) return;
    setLoading(true);
    try {
      const [resRes, recRes, currRes] = await Promise.allSettled([
        fetchWithAuth(`/educational/${trustId}/resources`),
        fetchWithAuth(`/educational/${trustId}/recommended`),
        fetchWithAuth('/educational/trustee-101/curriculum'),
      ]);

      const safeArray = (v) => (Array.isArray(v) ? v : []);
      if (resRes.status === 'fulfilled' && resRes.value.ok) {
        const data = await resRes.value.json();
        setResources(safeArray(data.resources || data));
      }
      if (recRes.status === 'fulfilled' && recRes.value.ok) {
        const data = await recRes.value.json();
        setRecommended(safeArray(data.recommended || data.resources || data));
      }
      if (currRes.status === 'fulfilled' && currRes.value.ok) {
        const data = await currRes.value.json();
        setCurriculum(safeArray(data.curriculum || data.lessons || data));
      }
    } catch (error) {
      showError(toast, error, { operation: 'load_educational', page: 'EducationalPanel' });
    } finally {
      setLoading(false);
    }
  }, [trustId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const totalCount = (resources?.length || 0) + (recommended?.length || 0) + (curriculum?.length || 0);

  const tabs = [
    { id: 'recommended', label: 'Recommended', count: recommended.length },
    { id: 'courses', label: 'Courses', count: curriculum.length },
    { id: 'guides', label: 'Guides', count: resources.length },
  ];

  const getItems = () => {
    switch (activeTab) {
      case 'recommended':
        return recommended;
      case 'courses':
        return curriculum;
      case 'guides':
        return resources;
      default:
        return [];
    }
  };

  const renderItem = (item, idx) => {
    const title = item.title || item.name || item.lesson_title || 'Untitled';
    const description = item.description || item.summary || '';
    const url = item.url || item.link || item.external_url;
    const type = item.type || (item.lesson_number ? 'course' : 'guide');

    return (
      <div
        key={item.id || item.lesson_number || idx}
        className="flex items-start gap-3 p-3 border border-navy/10 bg-cream/50"
        data-testid={`edu-item-${idx}`}
      >
        <ResourceIcon type={type} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-navy truncate">{title}</p>
          {description && (
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{description}</p>
          )}
          {item.reason && (
            <p className="text-xs text-gold mt-1 italic">{item.reason}</p>
          )}
        </div>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-shrink-0 text-navy/50 hover:text-navy transition-colors"
            aria-label={`Open ${title}`}
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        )}
      </div>
    );
  };

  return (
    <div className="card-trust" data-testid="educational-panel">
      {/* Collapsed header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 text-left"
        aria-expanded={expanded}
        data-testid="educational-panel-toggle"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-navy/10 flex items-center justify-center">
            <GraduationCap className="w-4 h-4 text-navy" />
          </div>
          <div>
            <h3 className="font-serif text-lg text-navy">Educational Resources</h3>
            {!expanded && (
              <p className="text-xs text-muted-foreground">
                {totalCount} educational resource{totalCount !== 1 ? 's' : ''} available
              </p>
            )}
          </div>
        </div>
        {expanded ? (
          <ChevronUp className="w-5 h-5 text-navy/50" />
        ) : (
          <ChevronDown className="w-5 h-5 text-navy/50" />
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-navy/10">
          {/* Tabs */}
          <div className="flex gap-1 mt-3 mb-3">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-1.5 text-xs font-mono border transition-colors ${
                  activeTab === tab.id
                    ? 'bg-navy text-cream border-navy'
                    : 'border-navy/20 text-muted-foreground hover:border-navy/40'
                }`}
                data-testid={`edu-tab-${tab.id}`}
              >
                {tab.label}
                {tab.count > 0 && (
                  <Badge variant="outline" className="ml-1.5 font-mono text-[10px] px-1 py-0">
                    {tab.count}
                  </Badge>
                )}
              </button>
            ))}
          </div>

          {/* Items */}
          {loading ? (
            <div className="py-4 text-center text-sm text-muted-foreground">Loading resources...</div>
          ) : getItems().length === 0 ? (
            <div className="py-4 text-center text-sm text-muted-foreground">
              No {activeTab} resources available.
            </div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {getItems().map((item, idx) => renderItem(item, idx))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
