// Phase 3: 3-tier pricing structure (Trustee, Estate, Advisor)
// Each tier supports both monthly and annual billing periods.
// 2026-09-08 restructure: annual anchor — annual billed = monthly × 12 × 0.8
// ("save 20% with annual"). Monthly is the flexible (higher) rate.
export const TIERS = [
  {
    id: 'trustee',
    name: 'Trustee Plan',
    tagline: 'One trust, fully documented, every deadline caught — you decide who sees what, and when.',
    monthly: 99,
    annual: 948,
    maxTrusts: 1,
    trustLimit: '1 trust',
    features: [
      '1 trust record',
      'Governance health tracking',
      'Minutes & distribution management',
      'PDF generation',
      'CSV data export',
      'Priority support'
    ]
  },
  {
    id: 'estate',
    name: 'Estate Plan',
    tagline: 'One dashboard, one calendar, one source of truth for your whole family portfolio.',
    monthly: 189,
    annual: 1788,
    maxTrusts: 8,
    trustLimit: 'Up to 8 trusts',
    popular: true,
    features: [
      'Everything in Trustee',
      'Up to 8 trusts & entities',
      'Multi-trust dashboard',
      'Recurring task automation',
      'Minutes & distribution management',
      'Client Access: grant view access to your fiduciary organization — time-boxed, revocable anytime',
      'PDF generation & CSV export'
    ]
  },
  {
    id: 'advisor',
    name: 'Advisor Plan',
    tagline: 'Your clients see their records on their terms; you see every trust you serve in one console.',
    monthly: 499,
    annual: 4788,
    maxTrusts: Infinity,
    trustLimit: 'Unlimited trusts',
    features: [
      'Everything in Estate',
      'Unlimited trusts & entities',
      'Org Console: every client trust in one view — clients grant access from their own account, revocable anytime',
      'Multi-trust dashboard',
      'Recurring task automation',
      'PDF generation & CSV export',
      'Dedicated account manager'
    ]
  }
];

// WingPoint-exclusive plan Ã¢ÂÂ only shown to WingPoint customers (is_wingpoint).
// NOT added to the public TIERS array to prevent it leaking to non-WingPoint users.
//
// Jeff-approved offer (msg 1565060388909744262): WingPoint customers get BOTH plans
// at WingPoint-discounted rates:
//
//   (a) WingPoint Trustee Ã¢ÂÂ 1 trust only: $79/mo monthly ÃÂ· $758/yr annual (20% off)
//   (b) WingPoint Plan Ã¢ÂÂ unlimited trusts: $99/mo monthly ÃÂ· $948/yr annual (20% off)
//
// Public TrustOffice pricing (TIERS above) is untouched: Trustee $99/mo ÃÂ· $948/yr.
// Both WingPoint options are real purchasable plans with Stripe price IDs and are
// checkout-gated by server-side WingPoint membership verification (wp_ref ledger).
export const WINGPOINT_TRUSTEE_TIER = {
  id: 'wingpoint_trustee',
  name: 'Trustee Plan (WingPoint)',
  monthly: 79,        // $79/mo Ã¢ÂÂ WingPoint discount vs public $99/mo
  annual: 758,        // $758/yr Ã¢ÂÂ 20% off $948; real Stripe price below
  maxTrusts: 1,
  trustLimit: '1 trust',
  features: [
    'Govern one trust end-to-end',
    'AI-powered guided minutes',
    'Governance Health Score & compliance calendar',
  ],
};

export const WINGPOINT_TIER = {
  id: 'wingpoint',
  name: 'WingPoint Plan',
  monthly: 99,        // $99/mo Ã¢ÂÂ real Stripe price (price_1UVXj8JE7N1BszdfjAlfQSaE)
  annual: 948,       // $948/yr Ã¢ÂÂ real Stripe price (price_1UVXj8JE7N1BszdfsPoo3rkm)
  maxTrusts: Infinity,
  trustLimit: 'Unlimited trusts',
  features: [
    'Unlimited trusts & entities',
    'AI-powered guided minutes',
    '31 professional document templates',
    'Governance Health Score & compliance calendar',
    'Minutes â Money integration',
    'Priority support'
  ]
};

// Convenience: the Trustee tier, isolated so it can be rendered alongside the
// WingPoint tier in the WingPoint two-option purchase section without pulling
// in the Estate/Advisor tiers.
export const TRUSTEE_TIER = TIERS.find((t) => t.id === 'trustee');

// Legacy (grandfathered) Trustee rates — subscribers who subscribed BEFORE the
// 2026-09-08 pricing restructure keep these prices until they cancel. The rate
// survives renewals; changing tier or billing period ends it.
export const LEGACY_TRUSTEE_RATES = { monthly: 79, annual: 790 };

// Uniform annual-savings copy (annual = 20% off monthly).
export const ANNUAL_SAVINGS_LABEL = 'Save 20% with annual';

// Map subscription plan_type to a display name.
// Handles the new tiers (trustee/estate/advisor) AND legacy values
// (monthly/annual) which are now grandfathered Trustee plans.
export const planDisplayName = (planType) => {
  switch (planType) {
    case 'trustee': return 'Trustee Plan';
    case 'estate': return 'Estate Plan';
    case 'advisor': return 'Advisor Plan';
    case 'wingpoint': return 'WingPoint Plan';
    case 'monthly': return 'Trustee Plan (Legacy)';
    case 'annual': return 'Trustee Plan (Legacy)';
    case 'forever_free':
    case 'free':
      return 'Free Plan';
    case 'trial':
      return 'Free Plan';
    default:
      return planType || 'Unknown';
  }
};

// Return the tier price for a given billing period.
// Legacy plan types (monthly/annual) map to the grandfathered Trustee rates.
export const tierPriceFor = (tierId, period) => {
  if (tierId === 'monthly') return LEGACY_TRUSTEE_RATES.monthly;
  if (tierId === 'annual') return LEGACY_TRUSTEE_RATES.annual;
  const tier = TIERS.find((t) => t.id === tierId);
  if (!tier) return null;
  return period === 'annual' ? tier.annual : tier.monthly;
};