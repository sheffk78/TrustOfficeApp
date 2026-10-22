// Connect Flow v2 — the WingPoint-known email reaches the pricing flow.
//
// The connect handoff passes the member's WingPoint-known email as &email=
// so the pricing page can prefill the checkout form (and the WP-plan login
// redirect) instead of making the member retype the address.
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PricingPage from '@/pages/PricingPage';
import { useAuth } from '@/context/AuthContext';

const mockNavigate = jest.fn();

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));
jest.mock('@/utils/utm', () => ({ getUtmParams: () => ({}) }));
jest.mock('react-router-dom', () => ({
  useSearchParams: () => [new URLSearchParams(mockSearchParams), jest.fn()],
  useNavigate: () => mockNavigate,
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Navigate: ({ to }) => <span data-testid="navigate">{to}</span>,
  useParams: () => ({}),
  useLocation: () => ({ pathname: '/', search: '' }),
  Routes: ({ children }) => <>{children}</>,
  Route: () => null,
}));

let mockSearchParams = '';

beforeEach(() => {
  jest.clearAllMocks();
  mockSearchParams = '';
  useAuth.mockReturnValue({ user: null });
});

describe('PricingPage — WingPoint email prefill', () => {
  test('prefills the guest-checkout email from the ?email= param', async () => {
    mockSearchParams = 'email=member@example.com&wp=1&plan=wingpoint';
    render(<PricingPage />);

    // Open the guest checkout modal for a non-WP tier.
    const buttons = await screen.findAllByRole('button');
    const cta = buttons.find((b) => /get started|start|choose/i.test(b.textContent || ''));
    fireEvent.click(cta);

    await waitFor(() => {
      expect(screen.getByLabelText(/email/i)).toHaveValue('member@example.com');
    });
  });

  test('carries the email into the WingPoint-plan login redirect', async () => {
    mockSearchParams = 'email=member@example.com&wp=1';
    render(<PricingPage />);

    const buttons = await screen.findAllByRole('button');
    const wpButton = buttons.find((b) =>
      /wingpoint/i.test(b.textContent || '') && /get started|start|choose|connect/i.test(b.textContent || ''),
    );
    expect(wpButton).toBeTruthy();
    fireEvent.click(wpButton);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalled();
    });
    const target = mockNavigate.mock.calls[0][0];
    expect(target).toContain('/login?');
    expect(target).toContain('email=member%40example.com');
    expect(target).toContain('wp=1');
  });

  test('leaves the email empty when no ?email= param is present', async () => {
    mockSearchParams = 'wp=1';
    render(<PricingPage />);

    const buttons = await screen.findAllByRole('button');
    const cta = buttons.find((b) => /get started|start|choose/i.test(b.textContent || ''));
    fireEvent.click(cta);

    await waitFor(() => {
      expect(screen.getByLabelText(/email/i)).toHaveValue('');
    });
  });
});
