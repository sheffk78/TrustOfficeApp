// Regression: invite dialog must send org_id (not the org object) in the invite URL.
// Caught in WingPoint dogfood 2026-09-25: /orgs/[object Object]/invites -> 404 "Org not found".
// jest.mock hoisting note: factories must not reference out-of-scope vars unless `mock`-prefixed,
// or the factory throws and the mock silently never applies (real fetch runs in jsdom).
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ user: { user_id: 'u1', role: 'admin' } }),
}));
jest.mock('@/components/Sidebar', () => ({ Sidebar: () => <aside data-testid="side" /> }));

const mockCalls = [];
jest.mock('@/utils/api', () => ({
  fetchWithAuth: async (path, opts) => {
    mockCalls.push({ path, opts });
    if (path === '/orgs') {
      return { ok: true, json: async () => ([{ org_id: 'org_test123', name: 'WingPoint Trust Group' }]) };
    }
    if (path.includes('/members')) {
      return { ok: true, json: async () => ([{ member_id: 'm1', role: 'owner', name: 'Jeff' }]) };
    }
    if (path.includes('/trusts')) {
      return { ok: true, json: async () => ({ trusts: [] }) };
    }
    return { ok: true, json: async () => ({}) };
  },
}));

jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('@/utils/errors', () => ({ showError: jest.fn() }));

import OrgConsolePage from '../OrgConsolePage';

describe('OrgConsolePage invite', () => {
  beforeEach(() => { mockCalls.length = 0; });

  test('invite sends org_id, never [object Object]', async () => {
    render(<OrgConsolePage />);
    const btn = await screen.findByTestId('invite-org_test123', undefined, { timeout: 3000 });
    fireEvent.click(btn);
    const input = await screen.findByTestId('invite-email-input');
    fireEvent.change(input, { target: { value: 'btudsbury@fastmail.com' } });
    fireEvent.click(screen.getByTestId('send-invite-btn'));
    await waitFor(() => {
      const inviteCall = mockCalls.find(c => c.path.includes('/invites'));
      expect(inviteCall).toBeTruthy();
      expect(inviteCall.path).toBe('/orgs/org_test123/invites');
      expect(inviteCall.path).not.toContain('object');
    });
  });
});