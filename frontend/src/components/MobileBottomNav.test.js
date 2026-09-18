/**
 * MobileBottomNav tests — phase2-nav-knowledge
 *
 * Covers DEEP-TESTING-LOG Feature #3 fix-later item 15 follow-up: the More
 * sheet already contained State Compliance / Risk Dashboard / Audit Trail, but
 * isSubActive()/isActive() compared location.pathname only, so query-string
 * routes (e.g. /governance?tab=state) never rendered as active after
 * navigation. These tests pin the pathname+search matching, plus the State
 * Compliance entry's icon/label/route/visibility contract (MapPin icon,
 * /governance?tab=state href, visible to every logged-in user regardless of
 * admin or benevolence flags — visibility itself is enforced app-wide by
 * ProtectedRoute, since no public page embeds this nav).
 */
import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { useAuth } from '@/context/AuthContext';

const mockUseLocation = jest.fn();

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  // Lazy reference: the factory runs before the const below is initialized.
  useLocation: () => mockUseLocation(),
}));

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));

jest.mock('lucide-react', () => new Proxy({}, {
  get: (_target, name) => (props) => (
    <span data-testid={`icon-${String(name)}`} {...props} />
  ),
}));

const setLocation = ({ pathname, search = '' }) => {
  mockUseLocation.mockReturnValue({ pathname, search });
};

describe('MobileBottomNav More sheet — compliance & audit links', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust: { trust_id: 't1' }, user: null });
    setLocation({ pathname: '/dashboard' });
  });

  it('shows State Compliance, Risk Dashboard and Audit Trail in the More sheet with correct hrefs', () => {
    render(<MobileBottomNav />);
    fireEvent.click(screen.getByTestId('mobile-nav-more'));

    const state = screen.getByTestId('mobile-more-state-compliance');
    const risk = screen.getByTestId('mobile-more-risk-dashboard');
    const audit = screen.getByTestId('mobile-more-audit-trail');

    expect(state).toHaveAttribute('href', '/governance?tab=state');
    expect(risk).toHaveAttribute('href', '/governance?tab=risk');
    expect(audit).toHaveAttribute('href', '/audit-trail');
  });
});

describe('MobileBottomNav active state for query-string routes', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust: { trust_id: 't1' }, user: null });
  });

  it('highlights State Compliance (and the More button) on /governance?tab=state', () => {
    setLocation({ pathname: '/governance', search: '?tab=state' });
    render(<MobileBottomNav />);
    fireEvent.click(screen.getByTestId('mobile-nav-more'));

    expect(screen.getByTestId('mobile-more-state-compliance')).toHaveClass('active');
    expect(screen.getByTestId('mobile-nav-more')).toHaveClass('active');
    expect(screen.getByTestId('mobile-more-risk-dashboard')).not.toHaveClass('active');
    expect(screen.getByTestId('mobile-more-trust-health')).not.toHaveClass('active');
  });

  it('highlights Risk Dashboard on /governance?tab=risk and not State Compliance', () => {
    setLocation({ pathname: '/governance', search: '?tab=risk' });
    render(<MobileBottomNav />);
    fireEvent.click(screen.getByTestId('mobile-nav-more'));

    expect(screen.getByTestId('mobile-more-risk-dashboard')).toHaveClass('active');
    expect(screen.getByTestId('mobile-more-state-compliance')).not.toHaveClass('active');
  });

  it('highlights Audit Trail on /audit-trail', () => {
    setLocation({ pathname: '/audit-trail' });
    render(<MobileBottomNav />);
    fireEvent.click(screen.getByTestId('mobile-nav-more'));

    expect(screen.getByTestId('mobile-more-audit-trail')).toHaveClass('active');
  });

  it('highlights Trust Health on plain /governance without highlighting the tab entries', () => {
    setLocation({ pathname: '/governance' });
    render(<MobileBottomNav />);
    fireEvent.click(screen.getByTestId('mobile-nav-more'));

    expect(screen.getByTestId('mobile-more-trust-health')).toHaveClass('active');
    expect(screen.getByTestId('mobile-more-state-compliance')).not.toHaveClass('active');
    expect(screen.getByTestId('mobile-more-risk-dashboard')).not.toHaveClass('active');
  });
});

describe('MobileBottomNav State Compliance entry — icon/label/visibility contract', () => {
  const openMore = () => {
    render(<MobileBottomNav />);
    fireEvent.click(screen.getByTestId('mobile-nav-more'));
    return within(screen.getByTestId('mobile-more-state-compliance'));
  };

  it('State Compliance entry follows the nav pattern: MapPin icon, label, href, no gating flags', () => {
    useAuth.mockReturnValue({ selectedTrust: { trust_id: 't1' }, user: null });
    setLocation({ pathname: '/dashboard' });
    const item = openMore();

    // Icon pattern: MapPin rendered inside the item, same lucide pattern as siblings
    expect(item.getByTestId('icon-MapPin')).toBeInTheDocument();
    // Label pattern: visible "State Compliance" text
    expect(item.getByText('State Compliance')).toBeInTheDocument();
    // Route: /governance with the state tab selected
    expect(screen.getByTestId('mobile-more-state-compliance')).toHaveAttribute('href', '/governance?tab=state');
  });

  it('entry is visible to a standard (non-admin) logged-in user — same as other More entries', () => {
    useAuth.mockReturnValue({
      selectedTrust: { trust_id: 't1' },
      user: { email: 'trustee@example.com', is_admin: false },
    });
    setLocation({ pathname: '/dashboard' });
    openMore();

    expect(screen.getByTestId('mobile-more-state-compliance')).toBeInTheDocument();
    // Standard entries stay visible for non-admins; only the Admin group is admin-gated
    expect(screen.queryByTestId('mobile-more-leads')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mobile-more-admin-panel')).not.toBeInTheDocument();
  });

  it('entry is visible to an admin user', () => {
    useAuth.mockReturnValue({
      selectedTrust: { trust_id: 't1' },
      user: { email: 'contact@trustoffice.app', is_admin: true },
    });
    setLocation({ pathname: '/dashboard' });
    openMore();

    expect(screen.getByTestId('mobile-more-state-compliance')).toBeInTheDocument();
    // Admin-gated group appears only for admins, mirroring the sidebar's isAdmin check
    expect(screen.getByTestId('mobile-more-leads')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-more-admin-panel')).toBeInTheDocument();
  });

  it('is not benevolence-gated: renders even when the trust has benevolence disabled', () => {
    useAuth.mockReturnValue({
      selectedTrust: { trust_id: 't1', benevolence_enabled: false },
      user: { email: 'trustee@example.com', is_admin: false },
    });
    setLocation({ pathname: '/dashboard' });
    openMore();

    expect(screen.getByTestId('mobile-more-state-compliance')).toBeInTheDocument();
  });
});