import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import BillingPage from '@/pages/BillingPage';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

jest.mock('@/components/Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }));
jest.mock('@/components/MobileBottomNav', () => ({ MobileBottomNav: () => <nav data-testid="mobile-nav" /> }));
jest.mock('@/components/PageHelpButton', () => () => <div data-testid="page-help" />);
jest.mock('@/pages/billing/WingPointBanners', () => ({ actionParam, isWp }) =>
  <div data-testid="wp-banners" data-iswp={String(isWp)} />);
jest.mock('@/pages/billing/SubscriptionStatusCard', () => ({ onCancel }) =>
  <div data-testid="sub-card"><button data-testid="card-cancel-btn" onClick={onCancel}>Cancel</button></div>);
jest.mock('@/pages/billing/TierChangeSection', () => () => <div data-testid="tier-change" />);
jest.mock('@/pages/billing/BillingFAQ', () => () => <div data-testid="faq" />);
jest.mock('@/components/billing/CancelFlowModal', () => ({ open, onOpenChange }) =>
  open ? (
    <div data-testid="cancel-flow-modal-open">
      <button data-testid="modal-close-stub" onClick={() => onOpenChange(false)}>Close</button>
    </div>
  ) : null);

jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

const user = { email: 'a@b.com', is_wingpoint: false };
const selectedTrust = { trust_id: 't1' };

async function renderBilling() {
  let cmp;
  await waitFor(() => {
    cmp = render(<BillingPage />);
  });
  return cmp;
}

describe('BillingPage', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  it('shows the Records Repository pre-cancel visibility note', async () => {
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ plan_type: 'trustee', status: 'active' }) });
    useAuth.mockReturnValue({ user, selectedTrust, loadSubscriptionState: jest.fn() });
    await renderBilling();
    expect(await screen.findByTestId('records-repository-note')).toBeInTheDocument();
    expect(screen.getByTestId('records-repository-note')).toHaveTextContent(/Records Repository/i);
    expect(screen.getByTestId('records-repository-note')).toHaveTextContent(/becomes available when you cancel/i);
  });

  it('opens the cancel-flow modal when the cancel button is clicked (no window.confirm)', async () => {
    const confirmSpy = jest.spyOn(window, 'confirm').mockImplementation(() => true);
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ plan_type: 'trustee', status: 'active' }) });
    useAuth.mockReturnValue({ user, selectedTrust, loadSubscriptionState: jest.fn() });
    await renderBilling();

    fireEvent.click(await screen.findByTestId('card-cancel-btn'));
    expect(await screen.findByTestId('cancel-flow-modal-open')).toBeInTheDocument();
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
