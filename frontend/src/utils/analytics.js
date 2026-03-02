/**
 * GA4 Analytics Utility for TrustOffice
 * Measurement ID: G-MT6FBPRE60
 * 
 * This utility provides helper functions for sending events to Google Analytics 4.
 * The base GA4 script is loaded in public/index.html.
 * 
 * Usage:
 *   import { trackEvent, trackSubscriptionEvent } from '@/utils/analytics';
 *   trackEvent('button_click', { button_name: 'save_minutes' });
 */

const GA4_MEASUREMENT_ID = 'G-MT6FBPRE60';

/**
 * Check if gtag is available
 */
export const isGtagAvailable = () => {
  return typeof window !== 'undefined' && typeof window.gtag === 'function';
};

/**
 * Send a custom event to GA4
 * @param {string} eventName - The name of the event
 * @param {Object} eventParams - Additional parameters for the event
 */
export const trackEvent = (eventName, eventParams = {}) => {
  if (isGtagAvailable()) {
    window.gtag('event', eventName, eventParams);
    if (process.env.NODE_ENV === 'development') {
      console.log(`[GA4] Event: ${eventName}`, eventParams);
    }
  } else {
    console.warn('GA4 gtag not available');
  }
};

/**
 * Track a page view manually (useful for dynamic content changes)
 * @param {string} pagePath - The page path
 * @param {string} pageTitle - The page title
 */
export const trackPageView = (pagePath, pageTitle) => {
  if (isGtagAvailable()) {
    window.gtag('config', GA4_MEASUREMENT_ID, {
      page_path: pagePath,
      page_title: pageTitle
    });
  }
};

/**
 * Set user properties for GA4
 * @param {Object} properties - User properties to set
 */
export const setUserProperties = (properties) => {
  if (isGtagAvailable()) {
    window.gtag('set', 'user_properties', properties);
  }
};

/**
 * Track user ID for cross-device tracking (use hashed/anonymized IDs)
 * @param {string} userId - The user ID
 */
export const setUserId = (userId) => {
  if (isGtagAvailable()) {
    window.gtag('config', GA4_MEASUREMENT_ID, {
      user_id: userId
    });
  }
};

// ============================================================
// SUBSCRIPTION FUNNEL EVENTS
// ============================================================

/**
 * Track when a user starts their trial
 * @param {Object} params - Event parameters
 * @param {string} params.plan_type - 'trial'
 * @param {string} params.origin - 'direct' | 'pricing_page' | 'register'
 * @param {number} params.trial_length_days - Number of trial days (default 14)
 */
export const trackTrialStarted = (params = {}) => {
  trackEvent('subscription_trial_started', {
    event_category: 'subscription',
    plan_type: 'trial',
    origin: params.origin || 'direct',
    trial_length_days: params.trial_length_days || 14,
    ...params
  });
};

/**
 * Track when a trial user converts to a paid subscription
 * @param {Object} params - Event parameters
 * @param {string} params.plan_type - 'monthly' | 'annual'
 * @param {string} params.origin - Where the conversion originated
 * @param {number} params.trial_length_days - Original trial length
 * @param {number} params.days_until_trial_end - Days remaining when converted
 */
export const trackTrialConverted = (params = {}) => {
  trackEvent('subscription_trial_converted', {
    event_category: 'subscription',
    plan_type: params.plan_type || 'monthly',
    origin: params.origin || 'billing_page',
    trial_length_days: params.trial_length_days || 14,
    days_until_trial_end: params.days_until_trial_end,
    value: params.plan_type === 'annual' ? 790 : 79,
    currency: 'USD',
    ...params
  });
};

/**
 * Track when a subscription is canceled
 * @param {Object} params - Event parameters
 * @param {string} params.plan_type - 'monthly' | 'annual'
 * @param {string} params.cancellation_reason - Optional reason
 */
export const trackSubscriptionCanceled = (params = {}) => {
  trackEvent('subscription_canceled', {
    event_category: 'subscription',
    plan_type: params.plan_type || 'monthly',
    cancellation_reason: params.cancellation_reason || 'user_initiated',
    ...params
  });
};

/**
 * Track when a subscription goes past due (payment failed)
 * @param {Object} params - Event parameters
 * @param {string} params.plan_type - 'monthly' | 'annual'
 */
export const trackSubscriptionPastDue = (params = {}) => {
  trackEvent('subscription_past_due', {
    event_category: 'subscription',
    plan_type: params.plan_type || 'monthly',
    ...params
  });
};

/**
 * Track checkout initiated
 * @param {Object} params - Event parameters
 */
export const trackCheckoutInitiated = (params = {}) => {
  trackEvent('checkout_initiated', {
    event_category: 'subscription',
    plan_type: params.plan_type || 'monthly',
    origin: params.origin || 'billing_page',
    value: params.plan_type === 'annual' ? 790 : 79,
    currency: 'USD',
    ...params
  });
};

/**
 * Track upgrade prompt shown (for conversion optimization)
 * @param {Object} params - Event parameters
 */
export const trackUpgradePromptShown = (params = {}) => {
  trackEvent('upgrade_prompt_shown', {
    event_category: 'subscription',
    prompt_location: params.location || 'unknown',
    prompt_type: params.type || 'modal',
    ...params
  });
};

/**
 * Track upgrade prompt clicked
 * @param {Object} params - Event parameters
 */
export const trackUpgradePromptClicked = (params = {}) => {
  trackEvent('upgrade_prompt_clicked', {
    event_category: 'subscription',
    prompt_location: params.location || 'unknown',
    prompt_type: params.type || 'modal',
    ...params
  });
};

/**
 * Track when a feature is blocked due to read-only/expired subscription
 * @param {Object} params - Event parameters
 * @param {string} params.feature_name - Name of the blocked feature
 * @param {string} params.location - Where the block occurred
 */
export const trackFeatureBlocked = (params = {}) => {
  trackEvent('feature_blocked', {
    event_category: 'subscription',
    feature_name: params.feature_name || 'unknown',
    location: params.location || 'unknown',
    subscription_status: params.subscription_status || 'expired',
    ...params
  });
};

/**
 * Track when trial banner is viewed
 * @param {Object} params - Event parameters
 * @param {number} params.days_remaining - Days left in trial
 */
export const trackTrialBannerViewed = (params = {}) => {
  trackEvent('trial_banner_viewed', {
    event_category: 'subscription',
    days_remaining: params.days_remaining,
    location: params.location || 'dashboard',
    ...params
  });
};

/**
 * Track when user clicks upgrade from trial banner
 * @param {Object} params - Event parameters
 */
export const trackTrialBannerClicked = (params = {}) => {
  trackEvent('trial_banner_clicked', {
    event_category: 'subscription',
    days_remaining: params.days_remaining,
    location: params.location || 'dashboard',
    ...params
  });
};

/**
 * Track when upgrade modal is shown
 * @param {Object} params - Event parameters
 */
export const trackUpgradeModalShown = (params = {}) => {
  trackEvent('upgrade_modal_shown', {
    event_category: 'subscription',
    trigger: params.trigger || 'blocked_action',
    feature_attempted: params.feature_attempted || 'unknown',
    ...params
  });
};

/**
 * Track when user clicks upgrade from modal
 * @param {Object} params - Event parameters
 */
export const trackUpgradeModalClicked = (params = {}) => {
  trackEvent('upgrade_modal_clicked', {
    event_category: 'subscription',
    trigger: params.trigger || 'blocked_action',
    feature_attempted: params.feature_attempted || 'unknown',
    ...params
  });
};

// Legacy subscription event tracker (backward compatible)
export const trackSubscriptionEvent = (eventType, params = {}) => {
  const validEvents = [
    'subscription_started',
    'subscription_upgraded',
    'subscription_downgraded',
    'subscription_canceled',
    'subscription_reactivated',
    'trial_started',
    'trial_ended'
  ];

  if (!validEvents.includes(eventType)) {
    console.warn(`Invalid subscription event type: ${eventType}`);
    return;
  }

  trackEvent(eventType, {
    event_category: 'subscription',
    ...params
  });
};

export default {
  trackEvent,
  trackPageView,
  setUserProperties,
  setUserId,
  trackSubscriptionEvent,
  trackTrialStarted,
  trackTrialConverted,
  trackSubscriptionCanceled,
  trackSubscriptionPastDue,
  trackCheckoutInitiated,
  trackUpgradePromptShown,
  trackUpgradePromptClicked,
  isGtagAvailable
};
