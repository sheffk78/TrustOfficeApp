// Segmented Monthly/Annual billing-period toggle used by both the
// no-subscription plan picker and the tier-change section.
//
// Props:
//   value    – 'monthly' | 'annual'
//   onChange – (period) => void
export default function BillingPeriodToggle({ value, onChange }) {
  return (
    <div className="flex justify-center mb-6">
      <div className="inline-flex items-center bg-subtle-bg border border-border rounded-full p-1">
        <button
          type="button"
          onClick={() => onChange('monthly')}
          className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${value === 'monthly' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
        >
          Monthly
        </button>
        <button
          type="button"
          onClick={() => onChange('annual')}
          className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${value === 'annual' ? 'bg-navy text-white' : 'text-muted-foreground hover:text-navy'}`}
        >
          Annual <span className="ml-1 text-xs text-success">2 months free</span>
        </button>
      </div>
    </div>
  );
}