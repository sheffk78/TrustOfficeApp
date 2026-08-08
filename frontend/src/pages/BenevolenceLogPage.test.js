import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import BenevolenceLogPage from '@/pages/BenevolenceLogPage';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';

// --- Mock heavy / non-essential modules so the test focuses on the page's
// own null-safety logic, not the full app shell. ---
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));

const noop = () => undefined;

// Proxy-backed mock so ANY lucide icon (including ones used internally by
// shadcn ui components, e.g. Select's ChevronDown/Check) resolves to a stub
// instead of undefined. Built fully inside the factory to avoid referencing
// out-of-scope variables (jest.mock factories are hoisted above consts).
jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});
jest.mock('@/components/Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }));
jest.mock('@/components/MobileBottomNav', () => ({ MobileBottomNav: () => <nav data-testid="mobile-nav" /> }));
jest.mock('@/components/PageHelpButton', () => () => <div data-testid="page-help" />);
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}));

describe('BenevolenceLogPage regression: monthly_aggregates may be undefined', () => {
  const selectedTrust = { trust_id: 'trust_1' };

  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust });
  });

  // Bug: "Cannot read properties of undefined (reading 'length')" — when the
  // API returned a data object without a `monthly_aggregates` array, the
  // Monthly Breakdown section dereferenced `data.monthly_aggregates.length`
  // directly and crashed the page render.
  it('does not throw and renders the table when monthly_aggregates is missing', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({
        distributions: [
          { distribution_id: 'd1', amount: 100, benevolence_recipient_name: 'Alice', beneficiary_name: 'Alice', date: '2026-08-01' },
        ],
        total_all_time: 100,
        total_count: 1,
        incomplete_documentation_count: 0,
      }),
    });

    let didThrow = false;
    try {
      render(<BenevolenceLogPage />);
    } catch (e) {
      didThrow = true;
    }

    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalled());
    expect(didThrow).toBe(false);
    expect(await screen.findByText('Alice')).toBeInTheDocument();
  });

  it('renders the select-a-trust empty state when no trust is selected', () => {
    useAuth.mockReturnValue({ selectedTrust: null });
    render(<BenevolenceLogPage />);
    expect(screen.getByText('Select a Trust')).toBeInTheDocument();
  });
});
