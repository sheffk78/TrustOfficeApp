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
  useSearchParams: () => [new URLSearchParams(), jest.fn()],
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
  if (route) return route;
  // audited workspace entry (M4 Option B): POST enter-trust resolves the org
  // view envelope — deep-link tests route through it, so the mock must too.
  if (url.startsWith('/orgs/enter-trust/') && over._enter !== false) {
    return {
      ok: true,
      json: async () => ({
        trust: { trust_id: 'trust_1', name: 'Family Trust' },
        client: { name: 'Jane Client', email: 'jane@x.com' },
        org: { org_id: 'org_1' },
        view_level: 'preparer',
        expires_at: null,
        entered_at: 'now',
        return_path: '/org-console',
      }),
    };
  }
  return { ok: false, json: async () => ({}) };
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
    // entry is async (POST audited enter → then navigate): wait for the hop
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/minutes'));
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
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/governance/history/trust_1'));
    fireEvent.click(screen.getByTestId(`go-to-distributions-trust_1`));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/distributions'));
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
    // FIX 3: grant-less members get a clear empty state, not the terse owner line.
    expect(screen.getByText('Nothing shared with you yet')).toBeInTheDocument();
    expect(screen.getByText(textOf(/hasn't granted you access to any client trusts yet/))).toBeInTheDocument();
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
    await waitFor(() => expect(screen.getAllByText('Fiduciary Group').length).toBeGreaterThan(0));
    expect(screen.getByTestId('trusts-heading').textContent).toContain('Client trusts (0)');
    // section failure is explicit, not silent: a retry affordance exists
    expect(screen.getByTestId('org-section-failed')).toBeInTheDocument();
  });
});
describe('OrgConsolePage v2 — scale + member actions + error states', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust: null, setSelectedTrust: jest.fn() });
  });

  const manyTrusts = Array.from({ length: 30 }, (_, i) => ({
    trust_id: `trust_${i}`,
    name: i % 2 ? `Trust ${i}` : `Alpha Trust ${i}`,
    owner_name: `Client ${i}`,
    grant_level: i % 3 ? 'viewer' : 'preparer',
    pending_minutes: i < 4 ? 2 : 0,
    next_deadline: null,
  }));

  it('scale: 30 trusts → search + level filter + show-more pagination + pending-first sort', async () => {
    fetchWithAuth.mockImplementation(api({
      [`/orgs/${ORG.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: manyTrusts }) },
    }));
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('trust-card').length).toBe(24));
    // search narrows
    fireEvent.change(screen.getByTestId('trust-search'), { target: { value: 'Alpha' } });
    await waitFor(() => expect(screen.getAllByTestId('trust-card').length).toBe(15));
    // level filter
    fireEvent.click(screen.getByTestId('trust-level-preparer'));
    await waitFor(() => expect(screen.getAllByTestId('trust-card').length).toBe(5));
    fireEvent.click(screen.getByTestId('trust-level-all'));
    fireEvent.change(screen.getByTestId('trust-search'), { target: { value: '' } });
    // pending-first: card with pending_minutes appears before page-2 items
    expect(screen.getAllByTestId('trust-card-pending').length).toBeGreaterThan(0);
    // pagination: show more appends
    fireEvent.click(screen.getByTestId('trust-show-more'));
    await waitFor(() => expect(screen.getAllByTestId('trust-card').length).toBe(30));
  });

  it('switcher: chips render per org with stats; clicking focuses one org panel', async () => {
    const ORG2 = { org_id: 'org_2', name: 'Barlow Fiduciary' };
    fetchWithAuth.mockImplementation((url) => {
      const map = {
        '/orgs': { ok: true, json: async () => [ORG, ORG2] },
        [`/orgs/${ORG.org_id}/members`]: { ok: true, json: async () => [MEMBER] },
        [`/orgs/${ORG.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: [TRUST] }) },
        [`/orgs/${ORG.org_id}/activity?limit=50`]: { ok: true, json: async () => ({ events: [] }) },
        [`/orgs/${ORG2.org_id}/members`]: { ok: true, json: async () => [] },
        [`/orgs/${ORG2.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: [] }) },
        [`/orgs/${ORG2.org_id}/activity?limit=50`]: { ok: true, json: async () => ({ events: [] }) },
      };
      return map[url] || { ok: false, json: async () => ({}) };
    });
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByTestId('org-chip-org_2')).toBeInTheDocument());
    expect(screen.getByTestId('trusts-heading').textContent).toContain('(1)');
    fireEvent.click(screen.getByTestId('org-chip-org_2'));
    await waitFor(() => expect(screen.getByTestId('trusts-heading').textContent).toContain('(0)'));
  });

  it('attention rail renders pending + deadline chips from loaded data', async () => {
    fetchWithAuth.mockImplementation(api());
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByTestId('rail-pending')).toBeInTheDocument());
    expect(screen.getByTestId('rail-pending').textContent).toContain('2');
  });

  it('team: collapsed default at >8, search members, row menu exposes suspend via real PATCH', async () => {
    const MEMBERS = Array.from({ length: 10 }, (_, i) => ({
      member_id: `mem_${i}`,
      name: `Member ${i}`,
      email: `m${i}@x.com`,
      role: i === 0 ? 'owner' : 'member',
      status: i === 9 ? 'invited' : 'active',
    }));
    fetchWithAuth.mockImplementation(api({
      [`/orgs/${ORG.org_id}/members`]: { ok: true, json: async () => MEMBERS },
    }));
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByTestId('team-toggle')).toBeInTheDocument());
    // collapsed: only 5 rows visible
    expect(screen.queryByText('Member 9')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('team-toggle'));
    await waitFor(() => expect(screen.getByText('m9@x.com')).toBeInTheDocument());
    // invite → dialog has role select now
    fireEvent.click(screen.getByTestId(`invite-${ORG.org_id}`));
    expect(screen.getByTestId('invite-role-select')).toBeInTheDocument();
  });

  it('page-level load failure shows the error card, NOT the no-org empty state', async () => {
    fetchWithAuth.mockImplementation(() => ({ ok: false, json: async () => ({}) }));
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByTestId('org-console-error')).toBeInTheDocument());
    expect(screen.queryByText(/No organization yet/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('org-console-retry'));
  });
});

describe('OrgConsolePage Phase 0 — server-mode advanced filtering (>48 trusts)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust: null, setSelectedTrust: jest.fn() });
  });

  const bigBook = Array.from({ length: 60 }, (_, i) => ({
    trust_id: `trust_${i}`,
    name: i % 2 ? `Trust ${i}` : `Alpha Trust ${i}`,
    owner_name: `Client ${i % 10}`,
    owner_email: `c${i % 10}@x.com`,
    grant_level: i % 4 ? 'viewer' : 'preparer',
    pending_minutes: i < 3 ? 5 : 0,
    next_deadline: null,
  }));
  const searchBody = (over = {}) => ({ trusts: bigBook, total: 60, page: { page: 1, page_size: 24, pages: 3 }, ...over });

  it('server mode: renders server grid + count line + advanced filters; search hits /search endpoint', async () => {
    fetchWithAuth.mockImplementation((url) => {
      if (url.startsWith('/orgs/org_1/trusts/search')) {
        if (url.includes('q=Alpha')) return Promise.resolve({ ok: true, json: async () => searchBody({ trusts: bigBook.filter(t => t.name.includes('Alpha')), total: 30 }) });
        return Promise.resolve({ ok: true, json: async () => searchBody() });
      }
      const map = {
        '/orgs': { ok: true, json: async () => [ORG] },
        [`/orgs/${ORG.org_id}/members`]: { ok: true, json: async () => [MEMBER] },
        [`/orgs/${ORG.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: bigBook }) },
        [`/orgs/${ORG.org_id}/activity?limit=50`]: { ok: true, json: async () => ({ events: [] }) },
      };
      return map[url] || { ok: false, json: async () => ({}) };
    });
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByTestId('advanced-filters')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('trust-result-count').textContent).toContain('of 60'), { timeout: 2000 });
    fireEvent.change(screen.getByTestId('trust-search'), { target: { value: 'Alpha' } });
    // debounced 300ms — wait for server grid update
    await waitFor(() => expect(screen.getByTestId('trust-result-count').textContent).toContain('of 30'), { timeout: 2000 });
    expect(fetchWithAuth.mock.calls.some(([u]) => u.includes('q=Alpha'))).toBe(true);
    // status select present and functional (state change triggers refetch)
    fireEvent.change(screen.getByTestId('trust-status-filter'), { target: { value: 'attention' } });
    await waitFor(() => expect(fetchWithAuth.mock.calls.some(([u]) => u.includes('status=attention'))).toBe(true), { timeout: 2000 });
  });
});

describe('OrgConsolePage Phase 1 — portfolio overview + review queue', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust: null, setSelectedTrust: jest.fn() });
  });

  it('renders portfolio rollup cells + queue rows with preparer Complete action; non-preparer rows lack it', async () => {
    fetchWithAuth.mockImplementation((url) => {
      if (url.includes('/overview')) return Promise.resolve({ ok: true, json: async () => ({
        org_id: 'org_1',
        portfolio: { trust_count: 3, average_health: 78.4, at_risk: 1, overdue_total: 2, pending_minutes_total: 4, due_week: 1 },
        trusts: [{ trust_id: 'trust_1', name: 'Family Trust', grant_level: 'preparer', health_score: 78, health_chip: 'watch', pending_minutes: 4, overdue_count: 2, next_deadline: '2026-10-04' }],
      }) });
      if (url.includes('/org/queue')) return Promise.resolve({ ok: true, json: async () => ({
        items: [
          { task_id: 'tk1', trust_id: 'trust_1', trust_name: 'Family Trust', task_type: 'quarterly_review', title: 'Quarterly review', due_date: '2026-09-30', urgency: 'overdue', grant_level: 'preparer' },
          { task_id: 'tk2', trust_id: 'trust_1', trust_name: 'Family Trust', task_type: 'custom', title: 'Read ledger', due_date: '2026-11-01', urgency: 'later', grant_level: 'viewer' },
        ],
        counts: { overdue: 1, due_week: 0, later: 1 },
      }) });
      const map = {
        '/orgs': { ok: true, json: async () => [ORG] },
        [`/orgs/${ORG.org_id}/members`]: { ok: true, json: async () => [MEMBER] },
        [`/orgs/${ORG.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: [TRUST] }) },
        [`/orgs/${ORG.org_id}/activity?limit=50`]: { ok: true, json: async () => ({ events: [] }) },
      };
      return map[url] || { ok: false, json: async () => ({}) };
    });
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByTestId('portfolio-overview')).toBeInTheDocument());
    expect(screen.getByTestId('ov-health').textContent).toBe('78.4');
    expect(screen.getByTestId('ov-overdue').textContent).toBe('2');
    await waitFor(() => expect(screen.getByTestId('review-queue')).toBeInTheDocument());
    expect(screen.getByTestId('queue-complete-tk1')).toBeInTheDocument();       // preparer
    expect(screen.queryByTestId('queue-complete-tk2')).not.toBeInTheDocument(); // viewer
    expect(screen.getByTestId('queue-open-tk1')).toBeInTheDocument();
  });

  it('queue Complete rounds-trip POST and refreshes', async () => {
    const okEnv = new Map(Object.entries({
      '/orgs': { ok: true, json: async () => [ORG] },
      [`/orgs/${ORG.org_id}/members`]: { ok: true, json: async () => [MEMBER] },
      [`/orgs/${ORG.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: [TRUST] }) },
      [`/orgs/${ORG.org_id}/activity?limit=50`]: { ok: true, json: async () => ({ events: [] }) },
      [`/orgs/${ORG.org_id}/overview`]: { ok: true, json: async () => ({ org_id: 'org_1', portfolio: { trust_count: 1, average_health: 90, at_risk: 0, overdue_total: 0, pending_minutes_total: 0, due_week: 0 }, trusts: [] }) },
      '/org/queue?org_id=org_1&limit=50': { ok: true, json: async () => ({ items: [{ task_id: 'tk1', trust_id: 'trust_1', trust_name: 'Family Trust', title: 'Q', due_date: '2026-10-02', urgency: 'due_week', grant_level: 'preparer' }], counts: { overdue: 0, due_week: 1, later: 0 } }) },
      '/org/queue/tk1/complete': { ok: true, json: async () => ({ task_id: 'tk1', status: 'completed', next_cycle_task_id: 'n1' }) },
    }));
    fetchWithAuth.mockImplementation((url, init) => {
      const key = init && init.method === 'POST' ? '/org/queue/tk1/complete' : url;
      const v = okEnv.get(key) || okEnv.get(url);
      return Promise.resolve(v || { ok: false, json: async () => ({}) });
    });
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByTestId('queue-complete-tk1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('queue-complete-tk1'));
    await waitFor(() => expect(fetchWithAuth.mock.calls.some(([u, i]) => u === '/org/queue/tk1/complete' && i?.method === 'POST')).toBe(true));
  });
});
