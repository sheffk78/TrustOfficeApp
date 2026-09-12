// DevicesSessionsCard test (FEATURE 5 item 2).
//
// Verifies:
//  - renders the list of active sessions (device label, IP, relative time)
//  - marks the current device with a "This device" badge and hides its sign-out button
//  - per-row "Sign out" calls DELETE /auth/sessions/<jti> and reloads
//  - "Sign out everywhere else" opens a confirm dialog; confirming calls POST /auth/sessions/revoke-all
//  - empty state renders when there are no sessions
//  - API errors show an error message with a retry affordance
//
// Mocks the network via fetchWithAuth so no real backend is touched.

import React from 'react';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import DevicesSessionsCard from '@/components/DevicesSessionsCard';

jest.mock('@/utils/api', () => ({
  fetchWithAuth: jest.fn(),
  getErrorMessage: async (res) => {
    try {
      const data = await res.json();
      return data.detail || 'Error';
    } catch {
      return 'Error';
    }
  },
}));
jest.mock('@/utils/errors', () => ({
  showError: jest.fn(),
}));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

// lucide icons resolve to stubs (real Dialog renders and needs them).
jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

// Dialog from shadcn/ui uses @radix-ui; give it a lightweight pass-through so
// content is rendered inline (open state driven by the component).
jest.mock('@/components/ui/dialog', () => {
  const ReactActual = require('react');
  const Pass = ({ children, open, onOpenChange, ...rest }) => {
    // Always render children (content) so the test can interact with the confirm flow.
    return <div data-testid="dialog">{typeof children === 'function' ? children({}) : children}</div>;
  };
  return {
    Dialog: Pass,
    DialogContent: ({ children }) => <div data-testid="dialog-content">{children}</div>,
    DialogHeader: ({ children }) => <div>{children}</div>,
    DialogTitle: ({ children }) => <h2>{children}</h2>,
    DialogDescription: ({ children }) => <p>{children}</p>,
    DialogFooter: ({ children }) => <div>{children}</div>,
    DialogTrigger: ({ children }) => <div>{children}</div>,
  };
});

import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';

const makeSessions = () => [
  {
    jti: 'current_jti',
    device_label: 'Chrome on macOS',
    ip: '1.2.3.4',
    created_at: '2026-09-01T00:00:00.000Z',
    last_seen_at: new Date(Date.now() - 60 * 1000).toISOString(),
    is_current: true,
  },
  {
    jti: 'other_jti',
    device_label: 'Safari on iOS',
    ip: '5.6.7.8',
    created_at: '2026-09-02T00:00:00.000Z',
    last_seen_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    is_current: false,
  },
];

describe('DevicesSessionsCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders active sessions with current-device badge and hides its sign-out', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ sessions: makeSessions() }),
    });

    render(<DevicesSessionsCard />);

    await waitFor(() => expect(screen.getByTestId('sessions-list')).toBeInTheDocument());

    // Both device labels present.
    expect(screen.getByText('Chrome on macOS')).toBeInTheDocument();
    expect(screen.getByText('Safari on iOS')).toBeInTheDocument();

    // Current device badge shown once.
    expect(screen.getByTestId('this-device-badge')).toBeInTheDocument();

    // IP rendered.
    expect(screen.getByText(/IP 1\.2\.3\.4/)).toBeInTheDocument();

    // Only one sign-out button (for the non-current device).
    const signOutButtons = screen.getAllByTestId('sign-out-btn');
    expect(signOutButtons).toHaveLength(1);

    // "Sign out everywhere else" button present (there is 1 other device).
    expect(screen.getByTestId('sign-out-everywhere-btn')).toBeInTheDocument();
  });

  it('signs out a single device via DELETE and reloads', async () => {
    fetchWithAuth
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ sessions: makeSessions() }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ message: 'Session revoked', jti: 'other_jti' }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ sessions: [makeSessions()[0]] }),
      });

    render(<DevicesSessionsCard />);
    await waitFor(() => expect(screen.getByTestId('sessions-list')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('sign-out-btn'));

    await waitFor(() =>
      expect(fetchWithAuth).toHaveBeenCalledWith('/auth/sessions/other_jti', { method: 'DELETE' })
    );
    // Reloaded after revoke -> now only the current device remains.
    await waitFor(() => {
      const rows = screen.queryAllByTestId('session-row');
      expect(rows).toHaveLength(1);
    });
    expect(toast.success).toHaveBeenCalled();
  });

  it('opens confirm dialog then revokes all other sessions via POST', async () => {
    fetchWithAuth
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ sessions: makeSessions() }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ revoked_count: 1, message: 'Revoked 1 other session(s)' }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ sessions: [makeSessions()[0]] }),
      });

    render(<DevicesSessionsCard />);
    await waitFor(() => expect(screen.getByTestId('sessions-list')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('sign-out-everywhere-btn'));
    // Confirm dialog appears.
    expect(screen.getByTestId('confirm-revoke-all')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('confirm-revoke-all'));

    await waitFor(() =>
      expect(fetchWithAuth).toHaveBeenCalledWith('/auth/sessions/revoke-all', { method: 'POST' })
    );
    await waitFor(() => {
      const rows = screen.queryAllByTestId('session-row');
      expect(rows).toHaveLength(1);
    });
  });

  it('renders empty state when there are no sessions', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      json: async () => ({ sessions: [] }),
    });
    render(<DevicesSessionsCard />);
    await waitFor(() => expect(screen.getByTestId('sessions-empty')).toBeInTheDocument());
    expect(screen.queryByTestId('session-row')).toBeNull();
  });

  it('shows an error with retry when the API fails', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Server blew up' }),
    });
    render(<DevicesSessionsCard />);
    await waitFor(() => expect(screen.getByTestId('sessions-error')).toBeInTheDocument());
    expect(screen.getByText(/Server blew up/)).toBeInTheDocument();
    expect(screen.getByTestId('sessions-retry')).toBeInTheDocument();
  });
});
