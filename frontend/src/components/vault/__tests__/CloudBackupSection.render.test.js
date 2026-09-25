// Regression: CloudBackupSection must render with zero connected providers.
// Caught in prod 2026-09-25: PROVIDER_LABELS includes proton_drive but PROVIDER_ICONS
// has no proton_drive entry → Icon=undefined → React error #130 crash on /vault.
// (Proton has its own dedicated hardcoded button below the map, so it must NOT be in
// the generic provider map.)
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

jest.mock('@/utils/api', () => ({
  fetchWithAuth: jest.fn(async (path) => {
    if (path.startsWith('/backup/status')) {
      return { ok: true, json: async () => ({ connections: [] }) };
    }
    return { ok: true, json: async () => ({}) };
  }),
}));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: { user_id: 'u1' } }) }));

import CloudBackupSection from '@/components/vault/CloudBackupSection';

describe('CloudBackupSection', () => {
  test('renders provider buttons without crashing (no proton_drive in generic map)', async () => {
    render(<CloudBackupSection selectedTrust={{ trust_id: 't1' }} />);
    await waitFor(() => {
      // generic map buttons (3 providers with icons)
      expect(screen.queryByTestId('connect-google_drive')).toBeTruthy();
      expect(screen.queryByTestId('connect-dropbox')).toBeTruthy();
      expect(screen.queryByTestId('connect-onedrive')).toBeTruthy();
    });
    // dedicated Proton button
    expect(screen.queryByTestId('connect-proton_drive')).toBeTruthy();
    // if we got here, React error #130 did not throw
    expect(screen.queryByText(/Automatically back up your vault documents/)).toBeTruthy();
  });
});