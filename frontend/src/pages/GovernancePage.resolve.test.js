import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import GovernancePage from '@/pages/GovernancePage';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));
jest.mock('@/utils/errors', () => ({
  showError: jest.fn(),
}));
jest.mock('@/components/PageHeader', () => ({ __esModule: true, default: () => <div data-testid="page-header" /> }));
jest.mock('@/components/EducationalPanel', () => () => <div data-testid="edu" />);
jest.mock('@/components/ui/button', () => {
  const React = require('react');
  return {
    Button: ({ children, ...rest }) => <button {...rest}>{children}</button>,
  };
});

jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Navigate: ({ to }) => <span data-testid="navigate">{to}</span>,
  useNavigate: () => jest.fn(),
  useParams: () => ({}),
  useSearchParams: () => [new URLSearchParams(), jest.fn()],
  useLocation: () => ({ pathname: '/', search: '' }),
  Routes: ({ children }) => <>{children}</>,
  Route: () => null,
  default: {},
}));

const RISK_FINDING = {
  type: 'missing_document',
  title: 'Schedule A (Assets) not found in Document Vault',
  detail: 'No Trust Assets found in vault',
  severity: 'high',
  penalty: 5,
  deeplink: '/schedule-a',
};

const jsonResponse = (body, ok = true) => ({ ok, json: async () => body });

describe('GovernancePage risk-finding Resolve', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ selectedTrust: { trust_id: 't1', trust_name: 'Test Trust' } });
    fetchWithAuth.mockImplementation((url, opts) => {
      const u = String(url);
      if (u.startsWith('/insights/resolve')) {
        return Promise.resolve(jsonResponse({
          message: 'Insight resolved',
          criterion_name: 'risk:missing_document',
          receipt: 'resolved — reviewed, no action taken',
          resolved: true,
        }));
      }
      if (u.startsWith('/insights/dismissed')) {
        return Promise.resolve(jsonResponse({ dismissed_insights: [] }));
      }
      if (u.includes('/history')) {
        return Promise.resolve(jsonResponse({ history: [] }));
      }
      if (u.startsWith('/governance/')) {
        return Promise.resolve(jsonResponse({
          total_score: 70,
          risk_penalty: 5,
          risk_findings: [RISK_FINDING],
          criteria: [],
          health_color: 'yellow',
        }));
      }
      return Promise.resolve(jsonResponse({}));
    });
  });

  it('persists the resolution and shows the receipt', async () => {
    await act(async () => {
      render(<GovernancePage />);
    });

    const resolveBtn = await screen.findByTestId('resolve-risk-missing_document');
    await act(async () => {
      fireEvent.click(resolveBtn);
    });

    await waitFor(() => {
      expect(fetchWithAuth).toHaveBeenCalledWith(
        '/insights/resolve',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('risk:missing_document'),
        })
      );
    });

    const call = fetchWithAuth.mock.calls.find(([url]) => String(url).startsWith('/insights/resolve'));
    const body = JSON.parse(call[1].body);
    expect(body.trust_id).toBe('t1');
    expect(body.criterion_name).toBe('risk:missing_document');
    expect(body.alert_title).toBe('Schedule A (Assets) not found in Document Vault');

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('resolved — reviewed, no action taken');
    });
  });
});
