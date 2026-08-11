/**
 * Unit tests for analytics.js utility functions
 * Focus: trackActivationComplete idempotency and event tracking
 */

const mockGtag = jest.fn();
const mockLocalStorage = (() => {
  let store = {};
  return {
    getItem: jest.fn((key) => store[key] || null),
    setItem: jest.fn((key, value) => { store[key] = String(value); }),
    removeItem: jest.fn((key) => { delete store[key]; }),
    clear: jest.fn(() => { store = {}; }),
  };
})();

// Set up mocks BEFORE requiring the module under test
beforeAll(() => {
  // Mock gtag on the global/window object
  Object.defineProperty(global, 'gtag', { value: mockGtag, writable: true });
  Object.defineProperty(global, 'localStorage', { value: mockLocalStorage, writable: true });
});

afterAll(() => {
  // No cleanup needed — jsdom environment is torn down after suite,
  // and beforeEach already resets mocks before each test.
});

beforeEach(() => {
  jest.clearAllMocks();
  mockLocalStorage.getItem.mockReturnValue(null);
  mockLocalStorage.setItem.mockClear();
  mockLocalStorage.clear();
});

// Import the analytics module (after mocks are set up)
const analytics = require('../analytics');

describe('analytics utilities', () => {
  describe('trackActivationComplete', () => {
    it('fires trackEvent with correct params when user_id is provided', () => {
      analytics.trackActivationComplete({
        user_id: 'user_abc123',
        plan_type: 'trustee',
        billing_period: 'monthly',
        transaction_id: 'txn_abc123',
      });

      // activation_complete event
      expect(mockGtag).toHaveBeenCalledWith('event', 'activation_complete', {
        event_category: 'subscription',
        plan_type: 'trustee',
        billing_period: 'monthly',
        transaction_id: 'txn_abc123',
        value: 79,
        currency: 'USD',
        user_id: 'user_abc123',
      });
    });

    it('uses correct tier pricing for estate/annual ($1,490)', () => {
      analytics.trackActivationComplete({
        user_id: 'user_estate',
        plan_type: 'estate',
        billing_period: 'annual',
        transaction_id: 'txn_estate',
      });

      expect(mockGtag).toHaveBeenCalledWith('event', 'activation_complete',
        expect.objectContaining({ value: 1490 })
      );
    });

    it('uses correct tier pricing for advisor/monthly ($399)', () => {
      analytics.trackActivationComplete({
        user_id: 'user_advisor',
        plan_type: 'advisor',
        billing_period: 'monthly',
      });

      expect(mockGtag).toHaveBeenCalledWith('event', 'activation_complete',
        expect.objectContaining({ value: 399 })
      );
    });

    it('uses correct tier pricing for wingpoint/annual ($1,188)', () => {
      analytics.trackActivationComplete({
        user_id: 'user_wp',
        plan_type: 'wingpoint',
        billing_period: 'annual',
      });

      expect(mockGtag).toHaveBeenCalledWith('event', 'activation_complete',
        expect.objectContaining({ value: 1188 })
      );
    });

    it('warns and returns early when user_id is missing', () => {
      const originalWarn = console.warn;
      console.warn = jest.fn();

      analytics.trackActivationComplete({
        plan_type: 'trustee',
        billing_period: 'monthly',
      });

      expect(console.warn).toHaveBeenCalledWith(
        '[Analytics] trackActivationComplete requires a user_id'
      );
      expect(mockGtag).not.toHaveBeenCalled();
      expect(mockLocalStorage.setItem).not.toHaveBeenCalled();

      console.warn = originalWarn;
    });

    it('is idempotent — fires only once per user per plan type', () => {
      analytics.trackActivationComplete({
        user_id: 'user_abc123',
        plan_type: 'trustee',
        billing_period: 'monthly',
        transaction_id: 'txn_first',
      });

      // Should have called gtag once (activation_complete only, no purchase event)
      expect(mockGtag).toHaveBeenCalledTimes(1);
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
        'activation_complete_user_abc123_trustee', 'true'
      );

      // Simulate localStorage already has the key for this user+plan
      mockLocalStorage.getItem.mockReturnValue('true');
      mockGtag.mockClear();

      // Second call with same user and plan type should be a no-op
      analytics.trackActivationComplete({
        user_id: 'user_abc123',
        plan_type: 'trustee',
        billing_period: 'monthly',
        transaction_id: 'txn_second',
      });

      expect(mockGtag).not.toHaveBeenCalled();
    });

    it('fires independently for different users with same plan type', () => {
      // Activate first user
      analytics.trackActivationComplete({
        user_id: 'user_alice',
        plan_type: 'trustee',
        billing_period: 'monthly',
        transaction_id: 'txn_alice',
      });

      // Simulate localStorage has alice but not bob
      mockLocalStorage.getItem
        .mockImplementation((key) => key === 'activation_complete_user_alice_trustee' ? 'true' : null);

      mockGtag.mockClear();

      // Second user with same plan should still fire
      analytics.trackActivationComplete({
        user_id: 'user_bob',
        plan_type: 'trustee',
        billing_period: 'monthly',
        transaction_id: 'txn_bob',
      });

      expect(mockGtag).toHaveBeenCalledTimes(1);
      expect(mockGtag).toHaveBeenCalledWith('event', 'activation_complete',
        expect.objectContaining({ user_id: 'user_bob', value: 79 })
      );
    });

    it('fires independently for different plan types for same user', () => {
      // Activate trustee first
      analytics.trackActivationComplete({
        user_id: 'user_alice',
        plan_type: 'trustee',
        billing_period: 'monthly',
        transaction_id: 'txn_trustee',
      });

      // Simulate localStorage has trustee but not estate key for this user
      mockLocalStorage.getItem
        .mockImplementation((key) => key === 'activation_complete_user_alice_trustee' ? 'true' : null);

      mockGtag.mockClear();

      // Estate activation should still fire
      analytics.trackActivationComplete({
        user_id: 'user_alice',
        plan_type: 'estate',
        billing_period: 'annual',
        transaction_id: 'txn_estate',
      });

      expect(mockGtag).toHaveBeenCalledTimes(1);
      expect(mockGtag).toHaveBeenCalledWith('event', 'activation_complete',
        expect.objectContaining({ plan_type: 'estate', value: 1490 })
      );
    });

    it('includes source field when provided', () => {
      analytics.trackActivationComplete({
        user_id: 'user_abc',
        plan_type: 'trustee',
        billing_period: 'monthly',
        source: 'stripe_webhook',
      });

      expect(mockGtag).toHaveBeenCalledWith('event', 'activation_complete',
        expect.objectContaining({ source: 'stripe_webhook' })
      );
    });

    it('sets localStorage activation key after firing', () => {
      analytics.trackActivationComplete({
        user_id: 'user_advisor',
        plan_type: 'advisor',
        billing_period: 'monthly',
      });

      expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
        'activation_complete_user_advisor_advisor', 'true'
      );
    });
  });

  describe('exported functions exist', () => {
    it('exports trackActivationComplete', () => {
      expect(typeof analytics.trackActivationComplete).toBe('function');
    });

    it('exports trackEvent', () => {
      expect(typeof analytics.trackEvent).toBe('function');
    });

    it('exports isGtagAvailable', () => {
      expect(typeof analytics.isGtagAvailable).toBe('function');
    });

    it('tracks lead capture in GA4 with attribution', () => {
      analytics.trackLeadCapture({
        source: 'trustee-101-landing-page',
        utm_source: 'google',
        utm_campaign: 'trustee-101',
        utm_medium: 'cpc',
      });

      expect(mockGtag).toHaveBeenCalledWith('event', 'lead_captured', expect.objectContaining({
        event_category: 'lead',
        source: 'trustee-101-landing-page',
        utm_source: 'google',
        utm_campaign: 'trustee-101',
        utm_medium: 'cpc',
      }));
    });
  });
});