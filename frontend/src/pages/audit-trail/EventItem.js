import { EVENT_ICONS, EVENT_COLORS, DEFAULT_COLOR, DEFAULT_ICON } from './constants';

export function getEventIcon(type) {
  return EVENT_ICONS[type] || DEFAULT_ICON;
}

export function getEventColor(type) {
  return EVENT_COLORS[type] || DEFAULT_COLOR;
}

export default function EventItem({ event, idx }) {
  const Icon = getEventIcon(event.type);
  const colorClass = getEventColor(event.type);

  const dateStr = event.date
    ? new Date(event.date).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : 'Unknown date';

  const timeStr = event.date
    ? new Date(event.date).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '';

  return (
    <div
      key={event.id || idx}
      className={`card-trust flex items-start gap-3 border ${colorClass}`}
    >
      <div className="flex-shrink-0 mt-0.5">
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium text-sm truncate">{event.title}</p>
          {event.is_retroactive && (
            <span className="text-[10px] bg-warning/10 text-warning px-1.5 py-0.5 rounded font-medium">
              RETROACTIVE
            </span>
          )}
        </div>
        {event.description && (
          <p className="text-xs opacity-80 mt-0.5">{event.description}</p>
        )}
      </div>
      <div className="flex-shrink-0 text-right">
        <p className="text-xs font-medium">{dateStr}</p>
        {timeStr && <p className="text-[10px] opacity-60">{timeStr}</p>}
      </div>
    </div>
  );
}