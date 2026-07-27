import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Shield, FileText, CalendarDays, ChevronRight, MapPin } from 'lucide-react';

const getScoreColor = (score) => {
  if (score >= 96) return 'text-success';
  if (score >= 72) return 'text-warning';
  return 'text-error';
};

const getScoreBadgeStyle = (score) => {
  if (score >= 96) return 'bg-success/10 text-success border-success/20';
  if (score >= 72) return 'bg-warning/10 text-warning border-warning/20';
  return 'bg-error/10 text-error border-error/20';
};

const getHealthLabel = (score) => {
  if (score >= 96) return 'Healthy';
  if (score >= 72) return 'Needs Attention';
  return 'At Risk';
};

/**
 * TrustCard — compact summary card for a trust linked to a client.
 *
 * Props:
 *   trust: { trust_id, trust_name, trust_type, jurisdiction, governance_score, health_color, created_at }
 */
export default function TrustCard({ trust }) {
  if (!trust) return null;

  const score = trust.governance_score ?? null;
  const trustId = trust.trust_id;

  return (
    <Card className="card-trust border border-border">
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-navy/5 flex items-center justify-center shrink-0">
              <Shield className="w-4.5 h-4.5 text-navy" />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-navy text-sm truncate">
                {trust.trust_name || 'Unnamed Trust'}
              </h3>
              <p className="text-xs text-muted-foreground">
                {trust.trust_type || 'Trust'}
                {trust.jurisdiction && (
                  <span className="inline-flex items-center ml-1">
                    <span className="mx-1">·</span>
                    <MapPin className="w-3 h-3 mr-0.5" />
                    {trust.jurisdiction}
                  </span>
                )}
              </p>
            </div>
          </div>
          {score !== null && (
            <Badge variant="outline" className={getScoreBadgeStyle(score)}>
              <span className={`font-mono font-semibold ${getScoreColor(score)}`}>{score}</span>
              <span className="ml-1 text-[10px] uppercase tracking-wide hidden sm:inline">
                {getHealthLabel(score)}
              </span>
            </Badge>
          )}
        </div>

        <div className="flex flex-col gap-1.5 mt-4">
          <Link to={`/governance`} className="block">
            <Button variant="outline" size="sm" className="w-full justify-between">
              <span className="flex items-center">
                <Shield className="w-3.5 h-3.5 mr-1.5" />
                View Trust
              </span>
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </Link>
          <Link to={`/governance/history/${trustId}`} className="block">
            <Button variant="ghost" size="sm" className="w-full justify-between text-muted-foreground">
              <span className="flex items-center">
                <FileText className="w-3.5 h-3.5 mr-1.5" />
                View Minutes
              </span>
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </Link>
          <Link to={`/calendar`} className="block">
            <Button variant="ghost" size="sm" className="w-full justify-between text-muted-foreground">
              <span className="flex items-center">
                <CalendarDays className="w-3.5 h-3.5 mr-1.5" />
                View Deadlines
              </span>
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
