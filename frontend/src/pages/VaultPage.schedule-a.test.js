import React from 'react';
import { render, screen, waitFor, act, within } from '@testing-library/react';
import VaultPage from '@/pages/VaultPage';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('@/components/vault/VaultAddForm', () => () => <div data-testid="vault-add-form" />);
jest.mock('@/components/vault/VaultCategorySection', () => () => <div data-testid="vault-cat" />);
jest.mock('@/components/vault/CriticalDocumentsAlert', () => () => <div data-testid="crit" />);
jest.mock('@/components/vault/CloudBackupSection', () => () => <div data-testid="cloud-backup" />);
jest.mock('@/components/vault/useVaultUpload', () => ({
  useVaultUpload: () => ({
    showAdd: false, setShowAdd: jest.fn(), addMode: 'upload', setAddMode: jest.fn(),
    form: {}, setForm: jest.fn(), uploadFile: jest.fn(), handleFileSelect: jest.fn(),
    clearUploadFile: jest.fn(), handleUpload: jest.fn(), uploading: false, uploadProgress: 0,
    uploadError: null, resetForm: jest.fn(), fileInputRef: { current: null },
  }),
}));
jest.mock('@/components/PageHelpButton', () => () => <div data-testid="page-help" />);
jest.mock('@/components/trust/DissolvedTrustBanner', () => ({
  __esModule: true,
  default: ({ trust }) => (
    <div data-testid="dissolved-banner" data-dissolved={trust?.status === 'dissolved_archived'} />
  ),
  isTrustDissolved: (trust) => Boolean(trust && trust.status === 'dissolved_archived'),
}));

jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

const mockUseSearchParams = jest.fn();
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Navigate: ({ to }) => <span data-testid="navigate">{to}</span>,
  useNavigate: () => jest.fn(),
  useParams: () => ({}),
  useSearchParams: () => mockUseSearchParams(),
  useLocation: () => ({ pathname: '/', search: '' }),
  Routes: ({ children }) => <>{children}</>,
  Route: () => null,
  default: {},
}));

const SCHEDULE_A_ITEMS = [
  { item_id: 'sa_1', description: 'Family home', category: 'real_property', approximate_value: 500000, status: 'active' },
  { item_id: 'sa_2', description: 'Brokerage account', category: 'financial_accounts', approximate_value: 120000, status: 'active' },
];

describe('VaultPage Schedule A section', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseSearchParams.mockReturnValue([new URLSearchParams(), jest.fn()]);
    useAuth.mockReturnValue({ selectedTrust: { trust_id: 't1', status: 'active' } });
    fetchWithAuth.mockImplementation((url) => {
      if (String(url).startsWith('/schedule-a')) {
        return Promise.resolve({ ok: true, json: async () => ({ items: SCHEDULE_A_ITEMS, total: 2 }) });
      }
      if (String(url).startsWith('/vault/summary')) {
        return Promise.resolve({ ok: true, json: async () => ({ documents: [], by_category: {}, categories: {} }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ categories: {} }) });
    });
  });

  it('renders the Schedule A section with the trust\'s assets linked to /schedule-a', async () => {
    await act(async () => {
      render(<VaultPage />);
    });

    const section = await screen.findByTestId('vault-schedule-a');
    expect(within(section).getByText('Schedule A — Trust Assets')).toBeInTheDocument();
    expect(within(section).getByText('Family home')).toBeInTheDocument();
    expect(within(section).getByText('Brokerage account')).toBeInTheDocument();

    const item = within(section).getByTestId('vault-schedule-a-item-sa_1');
    expect(item.getAttribute('href')).toBe('/schedule-a');
    expect(within(section).getByTestId('vault-schedule-a-manage').getAttribute('href')).toBe('/schedule-a');
  });

  it('never renders schedule_a_items as vault documents', async () => {
    await act(async () => {
      render(<VaultPage />);
    });

    // The vault document list is empty, so the grid shows the empty state and
    // no vault document card carries the Schedule A item.
    await screen.findByTestId('vault-schedule-a');
    expect(screen.queryByTestId('vault-cat')).toBeNull();
    expect(screen.getByText('Vault is empty')).toBeInTheDocument();
    // The schedule-a item is rendered exactly once (inside the Schedule A section).
    expect(screen.getAllByText('Family home')).toHaveLength(1);
  });

  it('shows the empty state when the trust has no Schedule A assets', async () => {
    fetchWithAuth.mockImplementation((url) => {
      if (String(url).startsWith('/schedule-a')) {
        return Promise.resolve({ ok: true, json: async () => ({ items: [], total: 0 }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ documents: [], by_category: {}, categories: {} }) });
    });

    await act(async () => {
      render(<VaultPage />);
    });

    const section = await screen.findByTestId('vault-schedule-a');
    expect(within(section).getByText(/No Schedule A assets on file yet/)).toBeInTheDocument();
  });
});
