import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
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

// react-router-dom is mapped to the project stub via jest config; we only need
// useSearchParams to return focus=backup here.
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

describe('VaultPage ?focus=backup', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseSearchParams.mockReturnValue([new URLSearchParams(), jest.fn()]);
    useAuth.mockReturnValue({ selectedTrust: { trust_id: 't1', status: 'active' } });
    fetchWithAuth
      .mockResolvedValueOnce({ ok: true, json: async () => ({ documents: [], by_category: {} }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ categories: {} }) });
  });

  it('scrolls to + highlights the cloud backup card when ?focus=backup', async () => {
    mockUseSearchParams.mockReturnValue([new URLSearchParams('focus=backup'), jest.fn()]);
    // jsdom lacks scrollIntoView
    window.HTMLElement.prototype.scrollIntoView = jest.fn();

    await act(async () => {
      render(<VaultPage />);
    });

    await waitFor(() => {
      const target = screen.getByTestId('cloud-backup-focus-target');
      expect(target.className).toMatch(/ring-2/);
    });
  });

  it('does not highlight the backup card without ?focus=backup', async () => {
    await act(async () => {
      render(<VaultPage />);
    });
    const target = await screen.findByTestId('cloud-backup-focus-target');
    expect(target.className).not.toMatch(/ring-2/);
  });

  it('renders the dissolved banner when trust status is dissolved_archived', async () => {
    useAuth.mockReturnValue({ selectedTrust: { trust_id: 't1', status: 'dissolved_archived', dissolved_on: '2026-09-12T00:00:00Z' } });
    await act(async () => {
      render(<VaultPage />);
    });
    const banner = await screen.findByTestId('dissolved-banner');
    expect(banner.getAttribute('data-dissolved')).toBe('true');
  });
});
