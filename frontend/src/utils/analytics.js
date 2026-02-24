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
// SUBSCRIPTION EVENT HELPERS (Ready for future implementation)
// ============================================================

/**
 * Track subscription-related events
 * These are placeholder functions ready for future use
 * 
 * Event naming convention:
 * - subscription_started: New subscription created
 * - subscription_upgraded: Upgraded from monthly to annual
 * - subscription_downgraded: Downgraded from annual to monthly
 * - subscription_canceled: Subscription canceled
 * - subscription_reactivated: Canceled subscription reactivated
 * - trial_started: Free trial started
 * - trial_ended: Free trial ended (converted or expired)
 */

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
  isGtagAvailable
};
