import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { getActivityIcon, getStatusBadgeClass } from './constants';
import { format, parseISO } from 'date-fns';

// Activity icon background color by type
const ACTIVITY_BG_COLORS = {
  minutes: 'bg-navy/10 text-navy',
  distribution: 'bg-gold/20 text-gold',
  compensation: 'bg-navy/10 text-navy',
  task: 'bg-success/20 text-success',
  default: 'bg-muted text-muted-foreground',
};

function getActivityBgColor(type) {
  return ACTIVITY_BG_COLORS[type] || ACTIVITY_BG_COLORS.default;
}

function formatDate(dateString) {
  try {
    return format(parseISO(dateString), 'MMM d, yyyy');
  } catch {
    return dateString;
  }
}

function ActivityRow({ activity, index, navigate }) {
  return (
    <div
      key={`${activity.type}-${activity.id}-${String(index)}`}
      className={`timeline-item ${activity.type}`}
    >
      <div className="flex items-start gap-4">
        <div className={`w-8 h-8 flex items-center justify-center ${getActivityBgColor(activity.type)}`}>
          {getActivityIcon(activity.type)}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-navy truncate">
            {activity.type === 'minutes' && activity.id ? (
              <button
                onClick={() => navigate(`/minutes/${activity.id}`)}
                className="text-left hover:text-gold transition-colors"
              >
                {activity.title}
              </button>
            ) : activity.title}
          </p>
          <div className="flex items-center gap-3 mt-1">
            <span className="font-mono text-xs text-muted-foreground">
              {formatDate(activity.date)}
            </span>
            {activity.status && (
              <span className={`badge-trust ${getStatusBadgeClass(activity.status)}`}>
                {activity.status}
              </span>
            )}
            {activity.entry_type && (
              <span className="badge-trust">
                {activity.entry_type}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Recent Activity timeline — shows the trust's recent governance activity.
 * Displays an empty-state CTA when there are no activities.
 */
export function DashboardRecentActivity({ activities, stats }) {
  const navigate = useNavigate();

  return (
    <div className="card-trust">
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="label-trust mb-1">Recent Activity</p>
          <h2 className="font-serif text-xl text-navy">Timeline</h2>
        </div>
        {stats && (
          <div className="text-right">
            <p className="font-mono text-sm text-muted-foreground">
              {stats.total_distributions} distributions
            </p>
            <p className="font-mono text-xs text-muted-foreground">
              ${stats.ytd_distributions_amount?.toLocaleString()} YTD
            </p>
          </div>
        )}
      </div>

      {activities.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-muted-foreground">No activity yet</p>
          <Button
            onClick={() => navigate('/minutes/create')}
            className="btn-secondary mt-4"
          >
            Record Your First Minutes
          </Button>
        </div>
      ) : (
        <div className="space-y-0">
          {activities.map((activity, index) => (
            <ActivityRow key={`${activity.type}-${activity.id}-${index}`} activity={activity} index={index} navigate={navigate} />
          ))}
        </div>
      )}
    </div>
  );
}