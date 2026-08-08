import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import StateCompliancePage from '@/pages/StateCompliancePage';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';

// --- Mock heavy / non-essential modules so the test focuses on the page's
// own null-safety logic, not the full app shell. ---
jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));

const noop = () => undefined;
const IconStub = ({ className, ...rest }) => <span data-testid="icon" className={className} {...rest} />;

const ICON_NAMES = [
  'MapPin','BookOpen','Gavel','Scale','Shield','AlertTriangle','CheckCircle2',
  'Clock','FileText','ChevronRight','Send','Paperclip','Loader2','AlertCircle',
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

  // Bug: "Cannot read properties of null (reading 'state_code')" — when the
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
