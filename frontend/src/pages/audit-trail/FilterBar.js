import { FILTER_OPTIONS } from './constants';

export default function FilterBar({ filter, onChange }) {
  return (
    <div className="flex flex-wrap gap-2">
      {FILTER_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
            filter === opt.value
              ? 'bg-navy text-white border-navy'
              : 'card-trust text-muted-foreground border-border hover:border-navy/30'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}