/**
 * CreateMinutesPage.js
 *
 * Template picker for creating minutes.
 *   - Displays categorized template grid loaded from /api/template-options
 *   - "Ask Trust Assistant" card navigates to /trust-assistant for AI-assisted drafting
 *   - Deep-link ?type= auto-navigates to a template form
 *   - ?prefill_type= shows a banner pointing to Trust Assistant
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/utils/api';
import {
  ArrowLeft,
  Bot,
  Check,
  ChevronRight,
  FileText,
  Gavel,
  Sparkles,
  Users,
  DollarSign,
  PlusCircle,
  MinusCircle,
  UserPlus,
  UserCheck,
  UsersRound,
  Landmark,
  MapPin,
  HeartHandshake,
  TrendingUp,
  Banknote,
  ShieldCheck,
  CalendarCheck,
  CalendarDays,
  Wallet,
  FileEdit,
  Stamp,
  FileX,
  Home,
  Building2,
  Key,
  CalendarRange,
  Receipt,
  AlertTriangle,
  Scale,
  XCircle,
  HandCoins,
  UserMinus,
  ClipboardList,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Constants & Mappings
// ---------------------------------------------------------------------------

/** Map backend icon names to lucide-react components */
const ICONS = {
  'file-text': FileText,
  'users': Users,
  'dollar-sign': DollarSign,
  'plus-circle': PlusCircle,
  'minus-circle': MinusCircle,
  'user-plus': UserPlus,
  'user-check': UserCheck,
  'users-round': UsersRound,
  'landmark': Landmark,
  'map-pin': MapPin,
  'heart-handshake': HeartHandshake,
  'gavel': Gavel,
  'heart-pulse': HeartHandshake,
  'trending-up': TrendingUp,
  'banknote': Banknote,
  'shield-check': ShieldCheck,
  'calendar-check': CalendarCheck,
  'calendar-days': CalendarDays,
  'wallet': Wallet,
  'file-edit': FileEdit,
  'stamp': Stamp,
  'file-x': FileX,
  'home': Home,
  'building-2': Building2,
  'key': Key,
  'calendar-range': CalendarRange,
  'receipt': Receipt,
  'alert-triangle': AlertTriangle,
  'scale': Scale,
  'x-circle': XCircle,
  'hand-coins': HandCoins,
  'user-minus': UserMinus,
};

/** Category display order and labels for the template grid */
const CATEGORY_ORDER = [
  { key: 'recommended', label: 'Recommended' },
  { key: 'governance', label: 'Governance' },
  { key: 'financial', label: 'Financial' },
  { key: 'assets', label: 'Assets' },
  { key: 'beneficiaries', label: 'Beneficiaries' },
  { key: 'reviews', label: 'Reviews' },
  { key: 'administrative', label: 'Administrative' },
  { key: 'legal', label: 'Legal' },
];

/** Template types that belong to the "Recommended" section */
const RECOMMENDED_TYPES = new Set([
  'initial_trustee_meeting',
  'quarterly_review',
  'annual_review',
  'distribution_to_beneficiaries',
]);

/** Mapping from backend category key → our display categories */
const CATEGORY_MAP = {
  governance: 'governance',
  financial: 'financial',
  assets: 'assets',
  beneficiaries: 'beneficiaries',
  reviews: 'reviews',
  administrative: 'administrative',
  legal: 'legal',
  priority: 'recommended',
  basic: 'recommended',
  distributions: 'recommended',
  benevolence: 'beneficiaries',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CreateMinutesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { selectedTrust, isReadOnly } = useAuth();

  // ----- Read-only guard -----
  useEffect(() => {
    if (isReadOnly) {
      toast.error('Read-only users cannot create minutes');
      navigate('/minutes', { replace: true });
    }
  }, [isReadOnly, navigate]);

  // ----- Onboarding deep-link: auto-navigate to template when ?type= is passed -----
  const fromOnboarding = searchParams.get('from') === 'onboarding' || searchParams.get('source') === 'onboarding';
  const templateType = searchParams.get('type');

  useEffect(() => {
    if (templateType && selectedTrust?.trust_id) {
      navigate(`/minutes/template/${templateType}?from=create${fromOnboarding ? '&source=onboarding' : ''}`, { replace: true });
    }
  }, [templateType, selectedTrust?.trust_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ----- Money prefill: show banner pointing to Trust Assistant -----
  const prefillType = searchParams.get('prefill_type');
  const prefillAmount = searchParams.get('prefill_amount');
  const showPrefillBanner = prefillType && prefillAmount;

  // ----- Template options loaded from backend -----
  const [templateOptions, setTemplateOptions] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);

  useEffect(() => {
    if (!selectedTrust?.trust_id) return;
    let cancelled = false;
    setTemplatesLoading(true);
    fetchWithAuth(`/template-options?trust_id=${selectedTrust.trust_id}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load templates');
        return res.json();
      })
      .then((data) => {
        if (!cancelled) {
          setTemplateOptions(data.templates || data || []);
        }
      })
      .catch((err) => {
        console.error('Error loading template options:', err);
        if (!cancelled) toast.error('Failed to load templates');
      })
      .finally(() => {
        if (!cancelled) setTemplatesLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedTrust?.trust_id]);

  // =========================================================================
  // Template selection handler
  // =========================================================================

  const handleTemplateSelect = (type) => {
    navigate(`/minutes/template/${type}?from=create`);
  };

  // =========================================================================
  // Render helpers
  // =========================================================================

  /** Build a map of templates grouped by display category */
  const buildCategorizedTemplates = () => {
    const categorized = {};
    CATEGORY_ORDER.forEach((cat) => {
      categorized[cat.key] = [];
    });

    templateOptions.forEach((t) => {
      const backendCat = t.category || 'basic';
      const displayCat = CATEGORY_MAP[backendCat] || 'other';

      if (RECOMMENDED_TYPES.has(t.type)) {
        categorized.recommended.push(t);
      } else if (categorized[displayCat]) {
        categorized[displayCat].push(t);
      } else {
        if (!categorized.other) categorized.other = [];
        categorized.other.push(t);
      }
    });

    return categorized;
  };

  /** Render a single template card */
  const renderTemplateCard = (t) => {
    const IconComp = ICONS[t.icon] || FileText;
    const isPriority = t.priority || t.type === 'initial_trustee_meeting';

    return (
      <button
        key={t.type}
        data-testid={`template-${t.type}`}
        onClick={() => handleTemplateSelect(t.type)}
        className="card-trust corner-mark overflow-visible group relative flex flex-col items-start gap-2 p-5 text-left transition-all hover:border-gold/50 hover:shadow-md"
      >
        {isPriority && (
          <span className={`badge-trust absolute -top-2 -right-2 bg-gold text-navy text-sm font-bold px-3 py-1 rounded-full shadow-sm${fromOnboarding ? ' animate-pulse' : ''}`}>
            Start Here
          </span>
        )}
        <div className="flex items-center gap-3 w-full">
          <div className={`flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-lg ${isPriority ? 'bg-gold/10 text-gold' : 'bg-navy/5 text-navy'}`}>
            <IconComp className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-serif text-sm font-semibold text-navy truncate">
              {t.name}
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
              {t.description}
            </p>
          </div>
          <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
        </div>
      </button>
    );
  };

  // =========================================================================
  // Render: Template Picker
  // =========================================================================

  // No trust selected
  if (!selectedTrust?.trust_id) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <div className="lg:ml-64 min-h-screen dot-grid">
          <div className="p-4 md:p-8 pb-24 md:pb-8 max-w-5xl mx-auto">
            <div className="flex flex-col items-center justify-center py-20">
              <ClipboardList className="h-12 w-12 text-muted-foreground mb-4" />
              <h2 className="font-serif text-xl text-navy">Select a Trust</h2>
              <p className="text-muted-foreground mt-2">
                Choose a trust from the sidebar to create minutes.
              </p>
            </div>
          </div>
        </div>
        <MobileBottomNav />
      </div>
    );
  }

  const categorized = buildCategorizedTemplates();

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className="lg:ml-64 min-h-screen dot-grid">
        <div className="p-4 md:p-8 pb-24 md:pb-8 max-w-5xl mx-auto">
          {/* Back to minutes list */}
          <button
            onClick={() => navigate('/minutes')}
            className="text-sm text-muted-foreground hover:text-navy flex items-center gap-1 mb-6 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" /> Minutes
          </button>

          {/* Money prefill banner */}
          {showPrefillBanner && (
            <div className="rounded-lg border border-gold/30 bg-gold/10 p-4 text-sm text-navy flex items-start gap-3 mb-6">
              <Sparkles className="h-5 w-5 text-gold flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Action from Money</span>{' '}
                — This action is being drafted from Money. Ask Trust Assistant to complete it.
                <button
                  onClick={() => navigate('/trust-assistant?prompt=I+need+to+document+a+recent+meeting')}
                  className="ml-1 text-gold hover:text-gold/80 font-semibold underline underline-offset-2"
                >
                  Go to Trust Assistant →
                </button>
              </div>
            </div>
          )}

          {/* Page header */}
          <div className="mb-8">
            <h1 className="font-serif text-2xl text-navy">What are you documenting?</h1>
            <p className="text-muted-foreground mt-1">
              Choose a template to get started, or ask Trust Assistant for help.
            </p>
          </div>

          {/* Onboarding welcome message */}
          {fromOnboarding && (
            <div className="rounded-lg border border-gold/30 bg-gold/10 p-4 text-sm text-navy flex items-start gap-2 mb-6">
              <Sparkles className="h-5 w-5 text-gold flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Welcome!</span>{' '}
                Let's create your first meeting minutes. Choose a template below or ask Trust Assistant.
              </div>
            </div>
          )}

          {/* Template grid sections */}
          {CATEGORY_ORDER.map((cat) => {
            const templates = categorized[cat.key];
            if (!templates || templates.length === 0) return null;

            return (
              <section key={cat.key} className="space-y-3 mb-10">
                <h2 className="font-serif text-lg text-navy border-b border-gold/20 pb-1">
                  {cat.label}
                  {cat.key === 'recommended' && (
                    <span className="ml-2 text-xs font-mono text-gold normal-case">
                      — most common for your trust
                    </span>
                  )}
                </h2>
                {templatesLoading ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {Array.from({ length: templates.length || 4 }).map((_, i) => (
                      <div key={i} className="card-trust animate-pulse p-5 h-24" />
                    ))}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {templates.map((t) => renderTemplateCard(t))}
                  </div>
                )}
              </section>
            );
          })}

          {/* Ask Trust Assistant card */}
          {!templatesLoading && (
            <section className="space-y-3 mb-10">
              <h2 className="font-serif text-lg text-navy border-b border-gold/20 pb-1">
                AI-Assisted
              </h2>
              <button
                onClick={() => navigate('/trust-assistant?prompt=I+need+to+document+a+recent+meeting')}
                className="card-trust group relative flex flex-col items-start gap-2 p-5 text-left transition-all hover:border-gold/50 hover:shadow-md w-full md:w-2/3 lg:w-1/2"
              >
                <div className="flex items-center gap-3 w-full">
                  <div className="flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-lg bg-gold/10 text-gold">
                    <Bot className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-serif text-sm font-semibold text-navy">
                      Ask Trust Assistant
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Describe your meeting in plain English. Trust Assistant transforms your notes into formal, compliant minutes — no legal jargon needed.
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                </div>
              </button>
            </section>
          )}

          {/* Info box */}
          <div className="rounded-lg border border-gold/20 bg-gold/5 p-4 text-sm text-muted-foreground">
            <p className="flex items-start gap-2">
              <FileText className="h-4 w-4 mt-0.5 text-gold flex-shrink-0" />
              <span>
                Templates guide you through common trustee decisions. New here?
                Start with &ldquo;Initial Trustee Meeting&rdquo; — it walks you through everything.
                Or choose &ldquo;Ask Trust Assistant&rdquo; and describe your meeting in plain language.
              </span>
            </p>
          </div>
        </div>
      </div>
      <MobileBottomNav />
    </div>
  );
}