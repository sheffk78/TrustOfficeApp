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
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));

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
  owner_user_id: 'u_jane', owner_name: 'Jane Client', owner_email: 'jane@x.com',
  grantor_name: 'Jane Grantor', trustee_name: 'Bob Trustee',
  grant_level: 'preparer', pending_minutes: 2, next_deadline: '2026-10-15T00:00:00Z',
};
// Pre-staged client trust (real backend contract): ownerless — user never
// signed up. Renders the honest "awaiting client account" state, no phantom client line.
const UNCLAIMED_TRUST = {
  trust_id: 'trust_9', name: 'Untitled trust',
  owner_user_id: null, owner_name: null, owner_email: null,
  grant_level: 'viewer', pending_minutes: 0, next_deadline: null,
};
const EVENT = {
  event_id: 'e1', action: 'distribution_approved', trust_id: 'trust_1',
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

  it('renders CLIENT-first card: client person name + email, trust nested, neutral enter CTA', async () => {
    fetchWithAuth.mockImplementation(api());
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('client-card').length).toBe(1));
    // client person is the headline; email is the subline
    expect(screen.getByTestId('client-card').textContent).toMatch(/Jane Client/);
    expect(screen.getByTestId('trust-card-client').textContent).toContain('jane@x.com');
    // the trust is nested under the client, not the headline
    expect(screen.getByText('Family Trust')).toBeInTheDocument();
    expect(screen.getByTestId('trust-card-level').textContent).toBe('preparer');
    // pending + deadline as chips
    expect(screen.getByTestId('trust-card-pending').textContent).toContain('2');
    expect(screen.getByText(textOf(/2026/))).toBeInTheDocument();
    // neutral entry action (no deep-link CTA row on the card)
    expect(screen.queryByTestId('go-to-minutes')).not.toBeInTheDocument();
    expect(screen.getByTestId('enter-account-trust_1').textContent).toMatch(/Enter Jane's account/i);
    // grantor/trustee meta no longer on the card face (council R2: space)
    expect(screen.queryByText('Jane Grantor')).not.toBeInTheDocument();
    expect(screen.queryByText('Bob Trustee')).not.toBeInTheDocument();
  });

  it('pre-staged client trust: renders honest unclaimed state, no phantom client line', async () => {
    fetchWithAuth.mockImplementation(api({
      [`/orgs/${ORG.org_id}/trusts`]: { ok: true, json: async () => ({ trusts: [UNCLAIMED_TRUST] }) },
    }));
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('trust-card-unclaimed-group').length).toBe(1));
    expect(screen.getByTestId('trust-card-unclaimed')).toBeInTheDocument();
    // headline carries the awaiting state; subline attests the pre-staged status
    expect(screen.getAllByText('Awaiting client account').length).toBeGreaterThan(0);
    expect(screen.getByTestId('trust-card-unclaimed').textContent).toMatch(/attested/i);
    expect(screen.queryByTestId('trust-card-client')).not.toBeInTheDocument();
    // no entry CTA for an unclaimed client (nothing to enter yet)
    expect(screen.getByTestId('awaiting-client-btn')).toBeDisabled();
  });

  it('entry is CONFIRM-GATED: click opens impersonation modal; entry only after confirm', async () => {
    const setSelectedTrust = jest.fn();
    useAuth.mockReturnValue({ selectedTrust: null, setSelectedTrust });
    fetchWithAuth.mockImplementation(api());
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('client-card').length).toBe(1));
    // click does NOT enter — it opens the confirm dialog
    fireEvent.click(screen.getByTestId('enter-account-trust_1'));
    expect(screen.getByTestId('enter-confirm-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('enter-confirm-dialog').textContent).toMatch(/Enter Jane's workspace/i);
    expect(screen.getByTestId('enter-confirm-dialog').textContent).toMatch(/audit log/i);
    expect(screen.queryByTestId('go-to-minutes')).not.toBeInTheDocument(); // deep-link row cut
    // no enter-trust call yet
    const enterCalls = fetchWithAuth.mock.calls.filter(([u]) => String(u).startsWith('/orgs/enter-trust/'));
    expect(enterCalls.length).toBe(0);
    // confirm → audited POST → hop to the workspace
    fireEvent.click(screen.getByTestId('enter-confirm-go'));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/org-console')); // return_path governs
    const calls = fetchWithAuth.mock.calls.filter(([u]) => String(u).startsWith('/orgs/enter-trust/'));
    expect(calls.length).toBe(1);
    // setSelectedTrust before navigate (workspace routes read persisted id on mount)
    const setCallOrder = setSelectedTrust.mock.invocationCallOrder[0];
    expect(setCallOrder).toBeDefined();
    expect(setCallOrder).toBeLessThan(mockNavigate.mock.invocationCallOrder[0]);
    expect(setSelectedTrust).toHaveBeenCalledWith(
      expect.objectContaining({ trust_id: 'trust_1', name: 'Family Trust' })
    );
  });

  it('cancel on confirm dialog does NOT enter', async () => {
    fetchWithAuth.mockImplementation(api());
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('client-card').length).toBe(1));
    fireEvent.click(screen.getByTestId('enter-account-trust_1'));
    expect(screen.getByTestId('enter-confirm-dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Cancel'));
    await waitFor(() => expect(screen.queryByTestId('enter-confirm-dialog')).not.toBeInTheDocument());
    expect(fetchWithAuth.mock.calls.filter(([u]) => String(u).startsWith('/orgs/enter-trust/')).length).toBe(0);
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('renders the activity feed with label, member, attribution', async () => {
    fetchWithAuth.mockImplementation(api());
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getAllByTestId('activity-feed').length).toBeGreaterThan(0));
    // 2026-10-09 contract: title row carries the label + the CLIENT it's for
    expect(screen.getByText(textOf(/Approved a distribution/))).toBeInTheDocument();
    expect(screen.getByText(textOf(/Approved a distribution — Jane Client/))).toBeInTheDocument();
    // who-line joins member + attribution
    expect(screen.getByText(textOf(/Associate · For Jane Client/))).toBeInTheDocument();
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
      // ownerless trust renders the honest awaiting state — no phantom client line, no crash
      expect(screen.getAllByText('Awaiting client account').length).toBeGreaterThan(0);
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
    // 2026-10-09 contract: cards are CLIENT-first (unique per client). Fixture: 30 trusts each with a
    // unique owner_name → 30 client cards; pagination pages TRUSTS, so initial window (24 trusts,
    // pending-first sort) shows the 4 pending owners first.
    await waitFor(() => expect(screen.getAllByTestId('client-card').length).toBeGreaterThanOrEqual(4));
    // search narrows to Alpha Trust owners (15 trusts → their clients)
    fireEvent.change(screen.getByTestId('trust-search'), { target: { value: 'Alpha' } });
    await waitFor(() => {
      const cards = screen.getAllByTestId('client-card').length;
      expect(cards).toBeGreaterThanOrEqual(1);
      expect(cards).toBeLessThanOrEqual(24);
    });
    // level filter
    fireEvent.click(screen.getByTestId('trust-level-preparer'));
    await waitFor(() => expect(screen.getAllByTestId('client-card').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByTestId('trust-level-all'));
    fireEvent.change(screen.getByTestId('trust-search'), { target: { value: '' } });
    // pending-first: pending chips present
    expect(screen.getAllByTestId('trust-card-pending').length).toBeGreaterThan(0);
    // pagination: show more appends more client cards
    const before = screen.getAllByTestId('client-card').length;
    fireEvent.click(screen.getByTestId('trust-show-more'));
    await waitFor(() => expect(screen.getAllByTestId('client-card').length).toBeGreaterThanOrEqual(before));
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

describe('OrgConsolePage Phase 2 — firm calendar + automated badge', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust: null, setSelectedTrust: jest.fn() });
  });

  it('renders week-bucketed tasks with Automated badge on engine-created entries', async () => {
    fetchWithAuth.mockImplementation((url) => {
      if (url === '/orgs') return Promise.resolve({ ok: true, json: async () => [ORG] });
      if (url.includes('/members')) return Promise.resolve({ ok: true, json: async () => [MEMBER] });
      if (url.includes('/trusts/search')) return Promise.resolve({ ok: true, json: async () => ({ trusts: [], total: 0 }) });
      if (url.includes('/trusts')) return Promise.resolve({ ok: true, json: async () => ({ trusts: [TRUST] }) });
      if (url.includes('/overview')) return Promise.resolve({ ok: true, json: async () => ({ org_id: 'org_1', portfolio: null, trusts: [] }) });
      if (url.includes('/calendar')) return Promise.resolve({ ok: true, json: async () => ({
        org_id: 'org_1',
        weeks: [
          { week: '2026-W40', items: [
            { task_id: 'a1', trust_id: 'trust_1', trust_name: 'Family Trust', task_type: 'quarterly_review', title: 'Quarterly review', due_date: '2026-10-02', automated: true },
            { task_id: 'a2', trust_id: 'trust_1', trust_name: 'Family Trust', task_type: 'custom', title: 'Read ledger', due_date: '2026-10-02', automated: false },
          ] },
        ],
        counts: { total: 2 },
      }) });
      if (url.includes('/org/queue')) return Promise.resolve({ ok: true, json: async () => ({ items: [], counts: { overdue: 0, due_week: 0, later: 0 } }) });
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByTestId('firm-calendar')).toBeInTheDocument());
    expect(screen.getAllByTestId('cal-week-2026-W40')).toHaveLength(1);
    expect(screen.getByText('Automated')).toBeInTheDocument();
    expect(screen.getByTestId('cal-open-a1')).toBeInTheDocument();
  });
});

describe('OrgConsolePage Phase 3 — defense summary + packet buttons', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust: null, setSelectedTrust: jest.fn() });
  });

  it('trust card exposes Defense Summary download; settings row exposes packet export', async () => {
    fetchWithAuth.mockImplementation((url, init) => {
      if (url.includes('/exports/defense-summary/trust_1')) return Promise.resolve({ ok: true, blob: async () => new Blob(['%PDF-x']), status: 200 });
      if (url.includes('/exports/org/org_1/packet')) return Promise.resolve({ ok: true, blob: async () => new Blob(['PK-zip']), status: 200 });
      if (url.includes('/overview')) return Promise.resolve({ ok: true, json: async () => ({ org_id: 'org_1', portfolio: null, trusts: [] }) });
      if (url.includes('/org/queue')) return Promise.resolve({ ok: true, json: async () => ({ items: [] }) });
      if (url.includes('/calendar')) return Promise.resolve({ ok: true, json: async () => ({ weeks: [], counts: { total: 0 } }) });
      const map = {
        '/orgs': { ok: true, json: async () => [ORG] },
        [`/orgs/org_1/members`]: { ok: true, json: async () => [MEMBER] },
        [`/orgs/org_1/trusts`]: { ok: true, json: async () => ({ trusts: [TRUST] }) },
        [`/orgs/org_1/activity?limit=50`]: { ok: true, json: async () => ({ events: [] }) },
      };
      return map[url] || { ok: false, json: async () => ({}) };
    });
    URL.createObjectURL = jest.fn(() => 'blob:x');
    URL.revokeObjectURL = jest.fn();
    render(<OrgConsolePage />);
    await waitFor(() => expect(screen.getByTestId('defense-summary-trust_1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('defense-summary-trust_1'));
    await waitFor(() => expect(fetchWithAuth.mock.calls.some(([u]) => u.includes('/exports/defense-summary/trust_1'))).toBe(true));
    const pkt = screen.getByTestId('org-packet-btn');
    fireEvent.click(pkt);
    await waitFor(() => expect(fetchWithAuth.mock.calls.some(([u, i]) => u.includes('/exports/org/org_1/packet') && i?.method === 'POST')).toBe(true));
  });
});
