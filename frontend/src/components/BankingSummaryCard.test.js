/**
 * TO-004 regression: BankingSummaryCard must distinguish a fetch failure from
 * a genuine empty state. Previously any non-OK/JSON/network failure collapsed
 * into summary=null, which rendered the misleading "No bank accounts linked
 * yet" even when accounts existed. The card now shows an explicit error state
 * with a retry button; the legitimate empty state (API succeeds with
 * account_count=0) is preserved.
 *
 * Run: cd frontend && npx craco test --testPathPattern=BankingSummaryCard
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';

import BankingSummaryCard from '@/components/BankingSummaryCard';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));

// Proxy-backed mock so any lucide icon resolves to a stub.
jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

describe('BankingSummaryCard (TO-004): error state vs empty state', () => {
  const selectedTrust = { trust_id: 'trust_1' };

  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust });
  });

  // ─────────────────────────────────────────────────────────────
  it('shows the error state with retry on a non-OK response (500), not the empty state', async () => {
    fetchWithAuth.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });

    render(<BankingSummaryCard />);

    await waitFor(() => expect(screen.getByTestId('banking-summary-error')).toBeInTheDocument());
    expect(screen.getByTestId('banking-summary-retry')).toBeInTheDocument();
    // Must NOT show the misleading empty state.
    expect(screen.queryByText('No bank accounts linked yet')).not.toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────
  it('shows the error state on a network rejection, not the empty state', async () => {
    fetchWithAuth.mockRejectedValue(new Error('Network down'));

    render(<BankingSummaryCard />);

    await waitFor(() => expect(screen.getByTestId('banking-summary-error')).toBeInTheDocument());
    expect(screen.queryByText('No bank accounts linked yet')).not.toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────
  it('shows the error state when JSON parsing fails', async () => {
    fetchWithAuth.mockResolvedValue({ ok: true, status: 200, json: async () => { throw new Error('invalid json'); } });

    render(<BankingSummaryCard />);

    await waitFor(() => expect(screen.getByTestId('banking-summary-error')).toBeInTheDocument());
    expect(screen.queryByText('No bank accounts linked yet')).not.toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────
  it('preserves the legitimate empty state when API succeeds with account_count=0', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ account_count: 0, accounts_with_balance: 0, total_latest_balance: null, accounts: [] }),
    });

    render(<BankingSummaryCard />);

    expect(await screen.findByTestId('banking-summary-empty')).toBeInTheDocument();
    expect(screen.getByText('No bank accounts linked yet')).toBeInTheDocument();
    expect(screen.queryByTestId('banking-summary-error')).not.toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────
  it('renders account data when API succeeds with accounts', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ account_count: 2, accounts_with_balance: 1, total_latest_balance: 1234.56, accounts: [] }),
    });

    render(<BankingSummaryCard />);

    expect(await screen.findByText('2')).toBeInTheDocument();
    // $ and the formatted amount render as adjacent text nodes; match the
    // numeric part which is the fmtMoney output.
    expect(screen.getByText('1,234.56')).toBeInTheDocument();
    expect(screen.queryByTestId('banking-summary-error')).not.toBeInTheDocument();
    expect(screen.queryByText('No bank accounts linked yet')).not.toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────
  it('retry button re-invokes the fetch', async () => {
    // First call fails; after retry we resolve successfully.
    fetchWithAuth
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ account_count: 1, accounts_with_balance: 0, total_latest_balance: null, accounts: [] }),
      });

    render(<BankingSummaryCard />);

    await waitFor(() => expect(screen.getByTestId('banking-summary-error')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('banking-summary-retry'));

    expect(await screen.findByText('1')).toBeInTheDocument();
    expect(screen.queryByTestId('banking-summary-error')).not.toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────
  it('renders nothing when no trust is selected', () => {
    useAuth.mockReturnValue({ selectedTrust: null });
    const { container } = render(<BankingSummaryCard />);
    expect(container.firstChild).toBeNull();
  });
});