import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { DashboardTrustAdminCard } from '@/pages/dashboard/DashboardTrustAdminCard';

/* Mock the app's authed fetch — the card's single integration point. */
jest.mock('@/utils/api', () => ({
  fetchWithAuth: jest.fn(),
}));

const { fetchWithAuth } = require('@/utils/api');

function mockResponse(entitled, url = null) {
  return { ok: entitled, json: async () => ({ entitled, scheduling_url: url }) };
}

describe('DashboardTrustAdminCard', () => {
  beforeEach(() => {
    fetchWithAuth.mockReset();
  });

  it('renders the scheduling card with the live URL for entitled users', async () => {
    fetchWithAuth.mockResolvedValue(
      mockResponse(true, 'https://book.trustoffice.app/')
    );
    render(<DashboardTrustAdminCard />);
    await waitFor(() => {
      expect(screen.getByTestId('trust-admin-schedule-cta')).toHaveAttribute(
        'href',
        'https://book.trustoffice.app/'
      );
    });
    expect(screen.getByText('Schedule with Kenneth')).toBeInTheDocument();
  });

  it('renders NOTHING for users without the entitlement (never upsells)', async () => {
    fetchWithAuth.mockResolvedValue(mockResponse(false, null));
    const { container } = render(<DashboardTrustAdminCard />);
    await waitFor(() => {
      expect(screen.queryByTestId('trust-admin-card')).not.toBeInTheDocument();
    });
    expect(container).toBeEmptyDOMElement();
  });

  it('stays hidden when the API fails (perk, not a notice)', async () => {
    fetchWithAuth.mockRejectedValue(new Error('network down'));
    const { container } = render(<DashboardTrustAdminCard />);
    await waitFor(() => {
      expect(container).toBeEmptyDOMElement();
    });
  });
});