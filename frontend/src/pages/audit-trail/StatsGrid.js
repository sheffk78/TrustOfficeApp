import { SECURITY_ACTIONS } from './constants';

function buildStats(events) {
  return [
    { label: 'Total Events', value: events.length, color: 'text-navy' },
    {
      label: 'Minutes',
      value: events.filter((e) => e.type.includes('minutes')).length,
      color: 'text-navy',
    },
    {
      label: 'Financial',
      value: events.filter(
        (e) =>
          e.type.includes('distribution') ||
          e.type.includes('compensation') ||
          e.type.includes('transaction'),
      ).length,
      color: 'text-success',
    },
    {
      label: 'Alerts',
      value: events.filter((e) => e.type.includes('alert')).length,
      color: 'text-warning',
    },
    {
      label: 'Security',
      value: events.filter((e) => SECURITY_ACTIONS.includes(e.type)).length,
      color: 'text-navy',
    },
  ];
}

export default function StatsGrid({ events }) {
  const stats = buildStats(events);
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {stats.map((stat) => (
        <div key={stat.label} className="card-trust text-center">
          <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
          <p className="text-xs text-muted-foreground">{stat.label}</p>
        </div>
      ))}
    </div>
  );
}