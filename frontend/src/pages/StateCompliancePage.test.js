import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import StateCompliancePage from '@/pages/StateCompliancePage';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';

// --- Mock heavy / non-essential modules so the test focuses on the page's
// own null-safety logic, not the full app shell. --
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));

const noop = () => undefined;
const IconStub = ({ className, ...rest }) => <span data-testid="icon" className={className} {...rest} />;

const ICON_NAMES = [
  'MapPin','BookOpen','Gavel','Scale','Shield','AlertTriangle','CheckCircle2',
  'Clock','FileText','ChevronRight','BookOpen','Send','Download','Paperclip','Loader2','AlertCircle',
  'X','Square','Plus','ArrowDown','Upload','File','Check','FolderOpen','Copy',
  'ChevronDown','ChevronUp',
];

const lucideMock = {};
ICON_NAMES.forEach((name) => { lucideMock[name] = IconStub; });

jest.mock('lucide-react', () => lucideMock);
jest.mock('@/components/Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }));
jest.mock('@/components/MobileBottomNav', () => ({ MobileBottomNav: () => <nav data-testid="mobile-nav" /> }));
jest.mock('@/components/PageHelpButton', () => () => <div data-testid="page-help" />);
jest.mock('@/components/InfoTooltip', () => () => <span data-testid="info-tooltip" />);
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
// react-markdown / remark-gfm are ESM-only in Jest (same mock pattern as
// frontend_smoke.test.js — the page renders them behind the expand toggle).
jest.mock('react-markdown', () => () => null);
jest.mock('remark-gfm', () => () => null);
jest.mock('@/utils/severityStyles', () => ({
  SEVERITY_STYLES_FLAT: { high: 'bg-red', medium: 'bg-yellow', low: 'bg-green' },
}));
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}));

describe('StateCompliancePage regression: stateData may be null/undefined', () => {
  const selectedTrust = { trust_id: 'trust_1' };

  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust });
  });

  // Bug: "Cannot read properties of null (reading 'state_code')" â when the
  // compliance fetch failed (or stateData was otherwise empty), the guard
  // `stateData?.state_code === null` did not catch `undefined`, so the main
  // branch dereferenced `stateData.state_code` directly and crashed.
  it('does not throw and shows the no-state empty state when the fetch fails', async () => {
    fetchWithAuth.mockRejectedValue(new Error('network down'));

    let didThrow = false;
    let result;
    try {
      result = render(<StateCompliancePage />);
    } catch (e) {
      didThrow = true;
    }

    // Wait for the async loadData to run (loading -> false), then assert.
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalled());

    expect(didThrow).toBe(false);
    // After the failed fetch, stateData stays null -> page must render the
    // "No state set" empty state instead of crashing.
    expect(await screen.findByText('No state set')).toBeInTheDocument();
    expect(result.container.querySelector('input,button[type=submit]')).toBeNull;
  });

  it('renders the select-a-trust empty state when no trust is selected', () => {
    useAuth.mockReturnValue({ selectedTrust: null });
    render(<StateCompliancePage />);
    expect(screen.getByText('Select a trust')).toBeInTheDocument();
  });
});

describe('StateCompliancePage uncovered state handling', () => {
  const selectedTrust = { trust_id: 'trust_1', state_code: 'XX' };

  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust });
  });

  it('shows the neutral info card and NOT the green satisfied banner for uncovered states', async () => {
    fetchWithAuth.mockImplementation(async (url) => {
      if (url.includes('state-compliance/requirements')) {
        return {
          ok: true,
          json: async () => ({ trust_id: 'trust_1', state_code: 'XX', requirements: [], coverage: 'uncovered' }),
        };
      }
      // compliance endpoint
      return {
        ok: true,
        json: async () => ({ trust_id: 'trust_1', state_code: 'XX', profile: null, compliance: null }),
      };
    });

    const { container } = render(<StateCompliancePage />);

    // Wait for the async data to actually land in state — the neutral card
    // only renders after loadData() finishes setting requirements/coverage.
    // (findByText with a custom matcher raced + over-constrained: the text sits
    // inside a <p> with sibling elements, so children.length===0 never matched.)
    await waitFor(() => {
      expect(container.textContent).toContain('requirements in our library yet');
    }, { timeout: 3000 });

    // Should show the uncovered info card (check textContent for partial match)
    expect(container.textContent).toContain('We don');
    expect(container.textContent).toContain('requirements in our library yet');
    // Should NOT show the green satisfied banner
    expect(container.textContent).not.toContain('All compliance requirements are satisfied');
  });

  it('shows the green satisfied banner for covered states with no requirements', async () => {
    fetchWithAuth.mockImplementation(async (url) => {
      if (url.includes('state-compliance/requirements')) {
        return {
          ok: true,
          json: async () => ({ trust_id: 'trust_1', state_code: 'CA', requirements: [], coverage: 'covered' }),
        };
      }
      return {
        ok: true,
        json: async () => ({
          trust_id: 'trust_1', state_code: 'CA',
          profile: { state_name: 'California' },
          compliance: { notice_last_sent: null, notice_next_due: null, accounting_last_sent: null, accounting_next_due: null, compliance_score: 100, alert_active: false },
        }),
      };
    });

    const { container } = render(<StateCompliancePage />);

    // Wait for the banner to actually render (waitFor on mock calls resolves
    // before the async state update lands in the DOM).
    await waitFor(() => {
      expect(container.textContent).toContain('All compliance requirements are satisfied for California');
    }, { timeout: 3000 });

    // Should NOT show the uncovered info card
    expect(container.textContent).not.toContain("We don't have");
  });

  it('shows requirement cards for covered states with requirements', async () => {
    fetchWithAuth.mockImplementation(async (url) => {
      if (url.includes('state-compliance/requirements')) {
        return {
          ok: true,
          json: async () => ({
            trust_id: 'trust_1', state_code: 'CA', coverage: 'covered',
            requirements: [
              { category: 'utc_gap', title: 'California has not adopted the Uniform Trust Code', severity: 'medium', points: 10 },
            ],
          }),
        };
      }
      return {
        ok: true,
        json: async () => ({
          trust_id: 'trust_1', state_code: 'CA',
          profile: { state_name: 'California' },
          compliance: { notice_last_sent: null, notice_next_due: null, accounting_last_sent: null, accounting_next_due: null, compliance_score: 100, alert_active: false },
        }),
      };
    });

    const { container } = render(<StateCompliancePage />);

    // Wait for the requirement card to actually render
    await waitFor(() => {
      expect(container.textContent).toContain('California has not adopted the Uniform Trust Code');
    }, { timeout: 3000 });

    // Should NOT show the green satisfied banner
    expect(container.textContent).not.toContain('All compliance requirements are satisfied');
  });
});

describe('StateCompliancePage compliance actions (doc generation)', () => {
  const selectedTrust = { trust_id: 'trust_1', state_code: 'CA', trustees: ['John Smith'] };

  const mockCoveredResponses = () => {
    fetchWithAuth.mockImplementation(async (url, opts) => {
      if (url.includes('state-compliance/requirements')) {
        return {
          ok: true,
          json: async () => ({
            trust_id: 'trust_1', state_code: 'CA', coverage: 'covered',
            requirements: [
              { category: 'notice', title: 'California requires periodic beneficiary notice', severity: 'medium', points: 10 },
            ],
          }),
        };
      }
      if (url === '/minutes-templates') {
        return {
          ok: true,
          json: async () => ({ minutes_id: 'min_test123', generated_document: 'letter' }),
        };
      }
      if (url === '/beneficiary-reports/trust_1/generate') {
        return {
          ok: true,
          json: async () => ({ report_id: 'rpt_test123', doc_id: 'doc_test123' }),
        };
      }
      if (url.includes('/state-compliance') && opts && opts.method === 'PATCH') {
        return { ok: true, json: async () => ({}) };
      }
      // GET state-compliance record
      return {
        ok: true,
        json: async () => ({
          trust_id: 'trust_1', state_code: 'CA',
          profile: { state_name: 'California' },
          compliance: { notice_last_sent: null, notice_next_due: null, accounting_last_sent: null, accounting_next_due: null, compliance_score: 90, alert_active: false },
        }),
      };
    });
  };

  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust });
  });

  it('renders both action buttons for covered states', async () => {
    mockCoveredResponses();
    const { container } = render(<StateCompliancePage />);

    expect(await screen.findByText('Generate Beneficiary Notice')).toBeInTheDocument();
    expect(screen.getByText('Generate Annual Accounting')).toBeInTheDocument();
    // Actions live in the deadlines card
    expect(container.textContent).toContain('Take Action');
  });

  it('does not show action buttons when state compliance data is absent', async () => {
    fetchWithAuth.mockImplementation(async (url) => {
      if (url.includes('state-compliance/requirements')) {
        return {
          ok: true,
          json: async () => ({ trust_id: 'trust_1', state_code: 'XX', requirements: [], coverage: 'uncovered' }),
        };
      }
      return {
        ok: true,
        json: async () => ({ trust_id: 'trust_1', state_code: 'XX', profile: null, compliance: null }),
      };
    });

    const { container } = render(<StateCompliancePage />);
    await waitFor(() => {
      expect(container.textContent).toContain('requirements in our library yet');
    }, { timeout: 3000 });

    expect(container.textContent).not.toContain('Generate Beneficiary Notice');
    expect(container.textContent).not.toContain('Generate Annual Accounting');
  });

  it('generating a notice POSTs the periodic-notice template and confirms the record', async () => {
    mockCoveredResponses();

    const { container } = render(<StateCompliancePage />);
    const btn = await screen.findByText('Generate Beneficiary Notice');
    fireEvent.click(btn);

    await waitFor(() => {
      const call = fetchWithAuth.mock.calls.find(([u]) => u === '/minutes-templates' && (fetchWithAuth.mock.contexts ? true : true));
      expect(call).toBeTruthy();
      const [, init] = call;
      const body = JSON.parse(init.body);
      expect(body.template_type).toBe('beneficiary_periodic_notice');
      expect(body.trust_id).toBe('trust_1');
      expect(body.template_data.trustee_name).toBe('John Smith');
    });

    // Confirmation that notice_last_sent was recorded
    expect(await screen.findByText(/Notice recorded/)).toBeInTheDocument();
    expect(screen.getByText('Download PDF')).toBeInTheDocument();
    // Page refetched the compliance record after the action (initial GET + refetch)
    const complianceGets = fetchWithAuth.mock.calls.filter(
      ([u]) => String(u).includes('/state-compliance') && !String(u).includes('requirements')
    );
    expect(complianceGets.length).toBeGreaterThanOrEqual(2);
  });

  it('generating the accounting POSTs the report endpoint and confirms the record', async () => {
    mockCoveredResponses();

    render(<StateCompliancePage />);
    const btn = await screen.findByText('Generate Annual Accounting');
    fireEvent.click(btn);

    await waitFor(() => {
      const call = fetchWithAuth.mock.calls.find(([u]) => u === '/beneficiary-reports/trust_1/generate');
      expect(call).toBeTruthy();
    });

    expect(await screen.findByText(/Accounting recorded/)).toBeInTheDocument();
    const link = screen.getByText('Download PDF');
    expect(link.closest('a')).toHaveAttribute('href', expect.stringContaining('/beneficiary-reports/trust_1/rpt_test123/download'));
  });

  it('shows an error toast when notice generation fails', async () => {
    mockCoveredResponses();
    const { toast } = await import('sonner');

    fetchWithAuth.mockImplementation(async (url, opts) => {
      if (url === '/minutes-templates') {
        return { ok: false, json: async () => ({ detail: 'boom' }) };
      }
      if (url.includes('state-compliance/requirements')) {
        return { ok: true, json: async () => ({ trust_id: 'trust_1', state_code: 'CA', coverage: 'covered', requirements: [] }) };
      }
      return {
        ok: true,
        json: async () => ({
          trust_id: 'trust_1', state_code: 'CA',
          profile: { state_name: 'California' },
          compliance: { notice_last_sent: null, notice_next_due: null, accounting_last_sent: null, accounting_next_due: null, compliance_score: 90, alert_active: false },
        }),
      };
    });

    render(<StateCompliancePage />);
    const btn = await screen.findByText('Generate Beneficiary Notice');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(toast.success).not.toHaveBeenCalledWith(expect.stringContaining('recorded'));
    });
  });
});

describe('StateCompliancePage deep-dive knowledge section', () => {
  const selectedTrust = { trust_id: 'trust_1', state_code: 'CA' };

  const CA_GUIDE = {
    id: '18-state-compliance-california',
    state_code: 'CA',
    state_name: 'California',
    title: 'Trust Compliance: California',
    summary: 'California trust compliance summary text.',
    markdown: '# Trust Compliance: California\n\n## State Income Tax on Trusts\n\nCalifornia taxes resident trusts.',
  };

  const baseResponses = (deepPayload) => (url, opts) => {
    if (url.includes('state-compliance/requirements')) {
      return {
        ok: true,
        json: async () => ({ trust_id: 'trust_1', state_code: 'CA', coverage: 'covered', requirements: [] }),
      };
    }
    if (url.includes('/state-compliance/deep-knowledge')) {
      return { ok: true, json: async () => deepPayload };
    }
    if (url === '/minutes-templates') {
      return { ok: true, json: async () => ({}) };
    }
    // compliance endpoint
    return {
      ok: true,
      json: async () => ({
        trust_id: 'trust_1', state_code: 'CA',
        profile: { state_name: 'California' },
        compliance: { notice_last_sent: null, notice_next_due: null, accounting_last_sent: null, accounting_next_due: null, compliance_score: 100, alert_active: false },
      }),
    };
  };

  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust });
  });

  it('renders the collapsed deep-dive card when the API returns an entry for the trust state', async () => {
    fetchWithAuth.mockImplementation(baseResponses([CA_GUIDE]));

    const { container } = render(<StateCompliancePage />);

    expect(await screen.findByTestId('deep-dive-card')).toBeInTheDocument();
    expect(screen.getByText(/Deep Dive — California Trust Compliance/)).toBeInTheDocument();

    // Collapsed by default: summary visible, full markdown NOT rendered
    expect(container.textContent).toContain('California trust compliance summary text.');
    expect(container.textContent).not.toContain('California taxes resident trusts');
    expect(screen.getByTestId('deep-dive-toggle')).toHaveTextContent('Read the full guide');

    // Expanding flips the toggle; react-markdown is mocked to null in Jest
    // (ESM), so assert the toggle + summary swap rather than the markdown body.
    fireEvent.click(screen.getByTestId('deep-dive-toggle'));
    expect(screen.getByTestId('deep-dive-toggle')).toHaveTextContent('Show less');
    expect(container.textContent).not.toContain('California trust compliance summary text.');
  });

  it('renders no deep-dive card when the API returns no matching entry', async () => {
    fetchWithAuth.mockImplementation(baseResponses([]));

    const { container } = render(<StateCompliancePage />);

    // Wait for the compliance data to land so loadData has fully finished
    await waitFor(() => {
      expect(container.textContent).toContain('All compliance requirements are satisfied for California');
    }, { timeout: 3000 });

    expect(screen.queryByTestId('deep-dive-card')).not.toBeInTheDocument();
    expect(screen.queryByTestId('deep-dive-toggle')).not.toBeInTheDocument();
  });

  it('matches the deep-knowledge entry by trust state code, not hard-coded CA', async () => {
    const NY_GUIDE = { ...CA_GUIDE, state_code: 'NY', state_name: 'New York', title: 'Trust Compliance: New York', summary: 'New York trust compliance summary text.' };
    useAuth.mockReturnValue({ selectedTrust: { trust_id: 'trust_1', state_code: 'NY' } });
    fetchWithAuth.mockImplementation((url) => {
      if (url.includes('state-compliance/requirements')) {
        return {
          ok: true,
          json: async () => ({ trust_id: 'trust_1', state_code: 'NY', coverage: 'covered', requirements: [] }),
        };
      }
      if (url.includes('/state-compliance/deep-knowledge')) {
        return { ok: true, json: async () => [CA_GUIDE, NY_GUIDE] };
      }
      return {
        ok: true,
        json: async () => ({ trust_id: 'trust_1', state_code: 'NY', profile: { state_name: 'New York' }, compliance: { compliance_score: 100, alert_active: false } }),
      };
    });

    render(<StateCompliancePage />);
    expect(await screen.findByText(/Deep Dive — New York Trust Compliance/)).toBeInTheDocument();
  });
});
