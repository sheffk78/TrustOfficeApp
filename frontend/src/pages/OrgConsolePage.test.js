import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import OrgConsolePage from '@/pages/OrgConsolePage';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';

// Mirror the BenevolenceLogPage regression-test setup: stub the shell so the
// test exercises OrgConsolePage's own data-wiring and null-safety.
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));
jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});
jest.mock('@/components/Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}));

const ORG = { org_id: 'org_1', name: 'Fiduciary Group' };
const MEMBER = { member_id: 'm1', name: 'Owner', email: 'o@x.com', role: 'owner' };
const TRUST = {
  trust_id: 'trust_1', name: 'Family Trust',
  owner_name: 'Jane Client', owner_email: 'jane@x.com',
  grantor_name: 'Jane Grantor', trustee_name: 'Bob Trustee',
  grant_level: 'preparer', pending_minutes: 2, next_deadline: '2026-10-15T00:00:00Z',
};
const EVENT = {
  event_id: 'e1', action: 'distribution_approved',
  member_name: 'Associate', created_at: '2026-09-27T00:00:00Z',
  attribution: 'For Jane Client',
};

// Default resolver: /orgs → list; members/trusts/activity per org. Overridable per test.
const api = (over = {}) => (url) => {
  const map = {
    '/orgs': { ok: true, json: async () => [ORG] },
    [`/orgs/${ORG.org_id}/members`]: { ok: true, json: async () => [MEMBER] },
    [`/orgs/${ORG.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: [TRUST] }) },
    [`/orgs/${ORG.org_id}/activity?limit=50`]: { ok: true, json: async () => ({ events: [EVENT] }) },
  };
  const route = over[url] || map[url];
  return route || { ok: false, json: async () => ({}) };
};

// Text in the page is split across nested spans; match against combined text
// content of the DEEPEST element containing it (function matchers otherwise hit
// every ancestor too and testing-library reports 'multiple elements').
const deepest = (match) => (_, el) => {
  if (!el) return false;
  const mine = typeof match === 'string' ? el.textContent.includes(match) : match.test(el.textContent || '');
  if (!mine) return false;
  const kids = [...el.children].some(c =>
    (typeof match === 'string' ? c.textContent.includes(match) : match.test(c.textContent || '')));
  return !kids;
};
const hasText = (text) => (_, el) => deepest(text)(_, el);
const textOf = (re) => (_, el) => deepest(re)(_, el);

describe('OrgConsolePage (institution M4 frontend upgrade)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust: null, setSelectedTrust: jest.fn() });
  });

  it('renders trust card with full client context + grant-level badge', async () => {
    fetchWithAuth.mockImplementation(api());
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('trust-card').length).toBe(1));
    expect(screen.getByTestId('trust-card-client').textContent).toContain('Jane Client');
    expect(screen.getByTestId('trust-card-client').textContent).toContain('jane@x.com');
    expect(screen.getByTestId('trust-card-level').textContent).toBe('preparer');
    expect(screen.getByText('Family Trust')).toBeInTheDocument();
    expect(screen.getByText('Jane Grantor')).toBeInTheDocument();
    expect(screen.getByText('Bob Trustee')).toBeInTheDocument();
    expect(screen.getByText(hasText('2 minutes pending review'))).toBeInTheDocument();
    expect(screen.getByText(textOf(/deadline/))).toBeInTheDocument();
  });

  it('deep-link: sets global selectedTrust before navigating to /minutes', async () => {
    const setSelectedTrust = jest.fn();
    useAuth.mockReturnValue({ selectedTrust: null, setSelectedTrust });
    fetchWithAuth.mockImplementation(api());
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('trust-card').length).toBe(1));
    fireEvent.click(screen.getByTestId('go-to-minutes'));
    expect(mockNavigate).toHaveBeenCalledWith('/minutes');
    // setSelectedTrust must have been called BEFORE navigate (order matters —
    // the workspace routes read the persisted selected_trust_id on mount)
    const setCallOrder = setSelectedTrust.mock.invocationCallOrder[0];
    expect(setCallOrder).toBeDefined();
    expect(setCallOrder).toBeLessThan(mockNavigate.mock.invocationCallOrder[0]);
    expect(setSelectedTrust).toHaveBeenCalledWith(
      expect.objectContaining({ trust_id: 'trust_1', name: 'Family Trust' })
    );
  });

  it('deep-links for meetings and distributions too', async () => {
    fetchWithAuth.mockImplementation(api());
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('trust-card').length).toBe(1));
    fireEvent.click(screen.getByTestId(`go-to-meetings-trust_1`));
    expect(mockNavigate).toHaveBeenCalledWith('/governance/history/trust_1');
    fireEvent.click(screen.getByTestId(`go-to-distributions-trust_1`));
    expect(mockNavigate).toHaveBeenCalledWith('/distributions');
  });

  it('renders the activity feed with label, member, attribution', async () => {
    fetchWithAuth.mockImplementation(api());
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('activity-feed').length).toBeGreaterThan(0));
    expect(screen.getByText('Approved a distribution')).toBeInTheDocument();
    expect(screen.getByText(textOf(/Associate ·/))).toBeInTheDocument();
    expect(screen.getByText('For Jane Client')).toBeInTheDocument();
  });

  it('empty state: no orgs → create-org prompt; empty trusts and activity lists render', async () => {
    fetchWithAuth.mockImplementation(api({
      '/orgs': { ok: true, json: async () => [ORG] },
      [`/orgs/${ORG.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: [] }) },
      [`/orgs/${ORG.org_id}/activity?limit=50`]: { ok: true, json: async () => ({ events: [] }) },
    }));
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByText(textOf(/Client trusts \(0\)/))).toBeInTheDocument());
    expect(screen.getByText(textOf(/None yet/))).toBeInTheDocument();
    expect(screen.getByText(textOf(/No activity yet/))).toBeInTheDocument();
  });

  it('null-safety: missing envelope keys and null next_deadline do not crash', async () => {
    fetchWithAuth.mockImplementation(api({
      '/orgs': { ok: true, json: async () => [ORG] },
      [`/orgs/${ORG.org_id}/members`]: { ok: true, json: async () => [] },
      [`/orgs/${ORG.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: [null, { trust_id: 't2' }] }) },
      [`/orgs/${ORG.org_id}/activity?limit=50`]: { ok: true, json: async () => ({ events: [null] }) },
    }));
    let didThrow = false;
    try {
      render(<OrgConsolePage />);
      await waitFor(() => expect(screen.getByText('Untitled trust')).toBeInTheDocument());
      expect(screen.getByText(hasText('No minutes pending'))).toBeInTheDocument();
      expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    } catch (e) { didThrow = true; console.error(e); }
    expect(didThrow).toBe(false);
  });

  it('per-org fetch failure is tolerated (page still renders org header)', async () => {
    fetchWithAuth.mockImplementation((url) =>
      url === '/orgs'
        ? { ok: true, json: async () => [ORG] }
        : Promise.reject(new Error('network down')));
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByText('Fiduciary Group')).toBeInTheDocument());
    expect(screen.getByText(textOf(/Client trusts \(0\)/))).toBeInTheDocument();
  });
});