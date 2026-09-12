import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import CancelFlowModal from '@/components/billing/CancelFlowModal';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

const noop = () => undefined;

describe('CancelFlowModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ user: { email: 'a@b.com' }, selectedTrust: { trust_id: 't1' }, loadSubscriptionState: noop });
  });

  it('renders the "Is your trust complete?" ask step when open', () => {
    render(<CancelFlowModal open onOpenChange={noop} trustId="t1" userEmail="a@b.com" loadSubscriptionState={noop} />);
    expect(screen.getByTestId('cancel-flow-modal')).toBeInTheDocument();
    expect(screen.getByText(/Is your trust complete/i)).toBeInTheDocument();
    expect(screen.getByTestId('cancel-keep-btn')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-leave-btn')).toBeInTheDocument();
  });

  it('Keep branch loads exit-summary and shows both repository purchase options', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ backup: { connected: true, last_backup_at: '2026-01-01T00:00:00Z' }, counts: { documents: 3 } }),
    });

    render(<CancelFlowModal open onOpenChange={noop} trustId="t1" userEmail="a@b.com" loadSubscriptionState={noop} />);

    fireEvent.click(screen.getByTestId('cancel-keep-btn'));

    expect(await screen.findByTestId('purchase-repo-annual-btn')).toBeInTheDocument();
    expect(screen.getByTestId('purchase-repo-lifetime-btn')).toBeInTheDocument();
    // exit-summary fetched
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledWith('/account/exit-summary'));
    // backup status text rendered
    expect(await screen.findByText(/last backup/i)).toBeInTheDocument();
  });

  it('Keep branch annual purchase posts {plan:"annual"} and redirects to checkout_url', async () => {
    fetchWithAuth
      .mockResolvedValueOnce({ ok: true, json: async () => ({ backup: { connected: false, last_backup_at: null } }) }) // exit-summary
      .mockResolvedValueOnce({ ok: true, json: async () => ({ checkout_url: 'https://checkout.example/abc' }) }); // purchase

    // Capture window.location.href assignment
    delete window.location;
    window.location = { href: '' };

    render(<CancelFlowModal open onOpenChange={noop} trustId="t1" userEmail="a@b.com" loadSubscriptionState={noop} />);
    fireEvent.click(screen.getByTestId('cancel-keep-btn'));

    // Wait until exit-summary has loaded and the annual button is enabled.
    await screen.findByText(/last backup|Not connected/i);
    const annualBtn = screen.getByTestId('purchase-repo-annual-btn');
    expect(annualBtn).not.toBeDisabled();
    fireEvent.click(annualBtn);

    await waitFor(() => {
      expect(fetchWithAuth).toHaveBeenCalledWith('/repository/purchase', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ plan: 'annual' }),
      }));
    });
  });

  it('Leave branch requires export + typed DELETE before bulk delete is enabled', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ backup: { connected: false, last_backup_at: null } }),
    });
    // archive-export returns a blob; bulk-delete returns ok
    global.URL.createObjectURL = jest.fn(() => 'blob:x');
    global.URL.revokeObjectURL = jest.fn();
    fetchWithAuth
      .mockResolvedValueOnce({ ok: true, json: async () => ({ backup: { connected: false, last_backup_at: null } }) }) // exit-summary
      .mockResolvedValueOnce({ ok: true, blob: async () => new Blob(['x']), status: 200 }) // archive-export
      .mockResolvedValueOnce({ ok: true, json: async () => ({ deleted: 5 }) }); // bulk delete

    render(<CancelFlowModal open onOpenChange={noop} trustId="t1" userEmail="a@b.com" loadSubscriptionState={noop} />);
    fireEvent.click(screen.getByTestId('cancel-leave-btn'));

    const exportBtn = await screen.findByTestId('export-archive-btn');
    fireEvent.click(exportBtn);
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledWith('/trusts/t1/archive-export'));

    // bulk-delete button disabled until DELETE typed
    const deleteBtn = await screen.findByTestId('bulk-delete-btn');
    expect(deleteBtn).toBeDisabled();

    const input = screen.getByTestId('bulk-delete-confirm-input');
    fireEvent.change(input, { target: { value: 'DELETE' } });
    expect(deleteBtn).toBeEnabled();

    fireEvent.click(deleteBtn);
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledWith('/vault/documents/bulk', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ confirm: 'DELETE' }),
    })));
  });

  it('Leave branch final cancel is blocked until export + delete complete', async () => {
    fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({ backup: { connected: false, last_backup_at: null } }) });
    render(<CancelFlowModal open onOpenChange={noop} trustId="t1" userEmail="a@b.com" loadSubscriptionState={noop} />);
    fireEvent.click(screen.getByTestId('cancel-leave-btn'));
    const finalCancel = await screen.findByTestId('leave-final-cancel-btn');
    expect(finalCancel).toBeDisabled();
  });
});
