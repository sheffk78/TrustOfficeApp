import { Link } from 'react-router-dom';
import { CalendarCheck, ArrowRight } from 'lucide-react';
import { getSeverityClass } from './constants';

/**
 * Weekly Briefing hero — "N things need your attention".
 * Lists AI-generated weekly briefing items with severity color coding.
 */
export function DashboardWeeklyBriefing({ weeklyBriefing }) {
  if (!weeklyBriefing || weeklyBriefing.length === 0) return null;

  const headingSuffix = weeklyBriefing.length === 1 ? 'thing' : 'things';
  const verbSuffix = weeklyBriefing.length === 1 ? 's' : '';

  return (
    <div className="mb-8 card-trust border-l-4 border-l-gold" data-testid="weekly-briefing-hero">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 bg-gradient-to-br from-gold/20 to-navy/10 flex items-center justify-center">
          <CalendarCheck className="w-5 h-5 text-gold" />
        </div>
        <div>
          <h3 className="font-serif text-lg text-navy">{weeklyBriefing.length} {headingSuffix} need{verbSuffix} your attention</h3>
          <p className="text-sm text-muted-foreground">Weekly briefing</p>
        </div>
      </div>
      <div className="space-y-2">
        {weeklyBriefing.map((item) => {
          const severityClass = getSeverityClass(item.severity);
          return (
            <div key={item.id} className={`flex items-center justify-between p-3 border ${severityClass}`}>
              <span className="text-sm font-medium">{item.title}</span>
              <div className="flex items-center gap-2">
                <Link
                  to={`/trust-assistant?prompt=${encodeURIComponent(item.cta_prompt)}`}
                  className="text-xs text-navy hover:text-navy/70 font-mono uppercase tracking-widest flex items-center gap-1"
                >
                  Ask AI <ArrowRight className="w-3 h-3" />
                </Link>
                <Link
                  to={item.action_link}
                  className="text-xs text-navy/60 hover:text-navy font-mono uppercase tracking-widest flex items-center gap-1"
                >
                  Fix now <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}