import { Button } from '@/components/ui/button';

// Segmented Monthly/Annual billing-period toggle used by both the
// no-subscription plan picker and the tier-change section.
//
// Props:
//   value    – 'monthly' | 'annual'
//   onChange – (period) => void
export default function BillingPeriodToggle({ value, onChange }) {
  return (
    <div className="flex justify-center mb-6">
      <div className="inline-flex items-center border border-border p-1">
        <Button
          type="button"
          variant="ghost"
          onClick={() => onChange('monthly')}
          className={`text-sm font-medium ${value === 'monthly' ? 'btn-primary' : 'btn-secondary'}`}
        >
          Monthly
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => onChange('annual')}
          className={`text-sm font-medium ${value === 'annual' ? 'btn-primary' : 'btn-secondary'}`}
        >
          Annual <span className="ml-1 text-xs text-success">Save 20%</span>
        </Button>
      </div>
    </div>
  );
}