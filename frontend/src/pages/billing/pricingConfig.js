// Phase 3: 3-tier pricing structure (Trustee, Estate, Advisor)
// Each tier supports both monthly and annual billing periods.
// 2026-09-08 restructure: annual anchor — annual billed = monthly × 12 × 0.8
// ("save 20% with annual"). Monthly is the flexible (higher) rate.
export const TIERS = [
  {
    id: 'trustee',
    name: 'Trustee Plan',
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
      'PDF generation & CSV export'
    ]
  },
  {
    id: 'advisor',
    name: 'Advisor Plan',
    monthly: 499,
    annual: 4788,
    maxTrusts: Infinity,
    trustLimit: 'Unlimited trusts',
    features: [
      'Everything in Estate',
      'Unlimited trusts & entities',
      'Multi-trust dashboard',
      'Recurring task automation',
      'White-label binder export',
      'PDF generation & CSV export',
      'Dedicated account manager'
    ]
  }
];

// WingPoint-exclusive plan — only shown to WingPoint customers (is_wingpoint).
// NOT added to the public TIERS array to prevent it leaking to non-WingPoint users.
//
// Jeff's requirement: WingPoint customers must be given TWO options:
//   (a) $79/month  → maps to the existing 'trustee' tier (monthly 79, annual 790)
//   (b) WingPoint plan → unlimited trusts at a discounted rate
//       Monthly: $119/mo   (new — price-conscious customers)
//       Annual:  $1,188/yr ($99/mo equivalent — best value, annual commitment)
//
// Both monthly and annual are real purchasable plans with Stripe price IDs.
export const WINGPOINT_TIER = {
  id: 'wingpoint',
  name: 'WingPoint Plan',
  monthly: 119,        // $119/mo — real Stripe price (price_1U4mSwJE7N1Bszdf9GHSbm89)
  annual: 1188,       // $1,188/yr — real Stripe price (price_1U1JcFJE7N1BszdfbSjSSa7c)
  maxTrusts: Infinity,
  trustLimit: 'Unlimited trusts',
  features: [
    'Unlimited trusts & entities',
    'AI-powered guided minutes',
    '31 professional document templates',
    'Governance Health Score & compliance calendar',
    'Minutes ↔ Money integration',
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